# -*- coding: utf-8 -*-
"""GAP-1 데이터 준비: 약관법 + E1/E2/E3 표본. 원본 수정 금지."""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
import winreg
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
EXP = ROOT / "exp_gap1"
DATA = EXP / "data"
TERMS = ROOT / "data_contract" / "aihub_terms"
FORMS = ROOT / "data_contract" / "aihub_forms"
LAW_DIR = ROOT / "data_contract" / "law_api" / "현행"
SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"
SEED = 42

# S2_REPORT 예시 분야(우선 포함). 최종은 유리·불리 각 ≥10 자동 판정.
PREFERRED_FIELDS = [
    "임대차계약",
    "가맹계약",
    "공급계약",
    "분양계약",
    "매매계약",
    "체육시설",
    "예식업",
    "상조서비스",
    "국내외여행",
    "입소,입주,입점계약",
    "신용카드",
    "자동차리스및렌트",
    "렌트(자동차이외)",
    "교육",
    "상품권",
    "마일리지포인트",
]

E3_SUBCATS = {"아르바이트계약서", "근로(고용)계약서", "주거용부동산임대계약서"}
E3_EXCLUDE_LABELS = {"기타", "계약의 내용", "계약의 당사자"}


def oc() -> str:
    v = os.environ.get("LAW_OC", "").strip()
    if v:
        return v
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
        v, _ = winreg.QueryValueEx(k, "LAW_OC")
        return str(v).strip()


def redact(t: str) -> str:
    t = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", t or "")
    return t


def http_get(params, base=SEARCH):
    q = urllib.parse.urlencode(params)
    last = None
    for i in range(5):
        try:
            req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(str(last))


def domain_of(p: Path) -> str:
    m = p.stem
    if "_" in m:
        return m.split("_", 1)[1].replace("_가공", "")
    return m


def clause_text(o: dict) -> str:
    art = o.get("clauseArticle")
    if isinstance(art, list):
        return "\n".join(str(x) for x in art)
    return art if isinstance(art, str) else ""


def load_terms_rows():
    rows = []
    for lab in ("TL_2.약관", "VL_2.약관"):
        root = TERMS / lab
        if not root.exists():
            continue
        for p in root.rglob("*.json"):
            try:
                o = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows.append(
                {
                    "path": str(p),
                    "field": domain_of(p),
                    "clause": clause_text(o),
                    "adv": str(o.get("dvAntageous")),
                    "relate": o.get("relateLaword"),
                    "obj": o,
                }
            )
    return rows


def article_units(body: dict):
    arts = (((body.get("법령") or {}).get("조문") or {}).get("조문단위")) or []
    if isinstance(arts, dict):
        arts = [arts]
    return [a for a in arts if isinstance(a, dict) and a.get("조문여부") == "조문"]


def format_article(a: dict) -> str:
    title = (a.get("조문제목") or "").strip()
    num = a.get("조문번호")
    br = a.get("조문가지번호")
    br = "" if br in (None, "", "None") else str(br)
    head = f"제{num}조" + (f"의{br}" if br else "")
    if title:
        head += f"({title})"
    parts = [(a.get("조문내용") or "").strip()]
    hangs = a.get("항")
    if isinstance(hangs, dict):
        hangs = [hangs]
    for h in hangs or []:
        if not isinstance(h, dict):
            continue
        hc = (h.get("항내용") or "").strip()
        if hc:
            parts.append(hc)
        hos = h.get("호")
        if isinstance(hos, dict):
            hos = [hos]
        for ho in hos or []:
            if isinstance(ho, dict):
                parts.append((ho.get("호내용") or "").strip())
    body = "\n".join(p for p in parts if p)
    return f"{head}\n{body}".strip()


def fetch_or_load_law(name: str) -> dict:
    p = LAW_DIR / f"{name}_body_MST.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    key = oc()
    t = http_get({"OC": key, "target": "law", "type": "JSON", "query": name, "display": 50})
    js = json.loads(t)
    root = js.get("LawSearch") or js
    laws = root.get("law")
    if isinstance(laws, dict):
        laws = [laws]
    it = None
    for x in laws or []:
        if (x.get("법령명한글") or "").strip() == name:
            it = x
            break
    if not it and laws:
        it = laws[0]
    link = (it or {}).get("법령상세링크") or ""
    m = re.search(r"[?&](?:MST|ID)=(\d+)", link)
    mst = m.group(1) if m else str((it or {}).get("법령일련번호") or "")
    tb = http_get({"OC": key, "target": "law", "type": "JSON", "MST": mst}, SERVICE)
    tb = redact(tb)
    LAW_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(tb, encoding="utf-8")
    return json.loads(tb)


def prepare_yakgwan():
    name = "약관의 규제에 관한 법률"
    body = fetch_or_load_law(name)
    arts = article_units(body)
    selected = []
    for a in arts:
        num = str(a.get("조문번호") or "")
        br = a.get("조문가지번호")
        if br not in (None, "", "None"):
            continue
        if num.isdigit() and 6 <= int(num) <= 14:
            selected.append(a)
    selected.sort(key=lambda x: int(x.get("조문번호")))
    texts = [format_article(a) for a in selected]
    out = DATA / "law_yakgwan_6_14.txt"
    blob = "\n\n".join(texts)
    out.write_text(blob, encoding="utf-8")
    titles = {}
    for a in selected:
        n = int(a.get("조문번호"))
        titles[n] = (a.get("조문제목") or "").strip()
    meta = {
        "law": name,
        "articles": [int(a.get("조문번호")) for a in selected],
        "n_articles": len(selected),
        "n_chars": len(blob),
        "titles": titles,
        "path": str(out),
    }
    (DATA / "law_yakgwan_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # also dump full law for R1 corpus later
    full_path = DATA / "law_yakgwan_full_articles.json"
    full = []
    for a in arts:
        num = a.get("조문번호")
        br = a.get("조문가지번호")
        br = "" if br in (None, "", "None") else str(br)
        full.append(
            {
                "law": name,
                "article": f"제{num}조" + (f"의{br}" if br else ""),
                "num": int(num) if str(num).isdigit() else None,
                "branch": br,
                "title": a.get("조문제목"),
                "text": format_article(a),
            }
        )
    full_path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def stratified_sample(groups: dict, n_total: int, rng: random.Random):
    """비례 층화. groups: key -> list."""
    keys = [k for k, v in groups.items() if v]
    if not keys:
        return []
    sizes = {k: len(groups[k]) for k in keys}
    total = sum(sizes.values())
    alloc = {k: max(1, int(round(n_total * sizes[k] / total))) for k in keys}
    # fix sum
    while sum(alloc.values()) > n_total:
        k = max(alloc, key=lambda x: alloc[x])
        if alloc[k] > 1:
            alloc[k] -= 1
        else:
            break
    while sum(alloc.values()) < n_total:
        k = max(keys, key=lambda x: sizes[x] - alloc[x])
        if alloc[k] < sizes[k]:
            alloc[k] += 1
        else:
            # any leftover
            rem = [x for x in keys if alloc[x] < sizes[x]]
            if not rem:
                break
            alloc[rng.choice(rem)] += 1
    out = []
    for k in keys:
        pool = list(groups[k])
        rng.shuffle(pool)
        out.extend(pool[: alloc[k]])
    rng.shuffle(out)
    return out[:n_total]


def prepare_e1(rows, n=200):
    rng = random.Random(SEED)
    log = {"excluded_short_long": 0, "preferred_fields": PREFERRED_FIELDS}
    by_field_adv = defaultdict(lambda: {"1": [], "2": []})
    for r in rows:
        cl = (r["clause"] or "").strip()
        if len(cl) < 20 or len(cl) > 1500:
            log["excluded_short_long"] += 1
            continue
        if r["adv"] in ("1", "2"):
            by_field_adv[r["field"]][r["adv"]].append(r)
    # fields with both >=10 after length filter
    ok_fields = sorted(
        [
            f
            for f, d in by_field_adv.items()
            if len(d["1"]) >= 10 and len(d["2"]) >= 10
        ],
        key=lambda f: (0 if f in PREFERRED_FIELDS else 1, f),
    )
    log["ok_fields"] = ok_fields
    log["field_counts"] = {
        f: {"유리": len(by_field_adv[f]["1"]), "불리": len(by_field_adv[f]["2"])} for f in ok_fields
    }
    bad_groups = {f: by_field_adv[f]["2"] for f in ok_fields}
    good_groups = {f: by_field_adv[f]["1"] for f in ok_fields}
    bad = stratified_sample(bad_groups, n // 2, rng)
    good = stratified_sample(good_groups, n // 2, rng)
    items = []
    for i, r in enumerate(bad + good):
        items.append(
            {
                "id": f"E1-{i:04d}",
                "field": r["field"],
                "clause": r["clause"].strip(),
                "label_risky": r["adv"] == "2",
                "source": r["path"],
            }
        )
    rng.shuffle(items)
    # re-id after shuffle
    for i, it in enumerate(items):
        it["id"] = f"E1-{i:04d}"
    path = DATA / "e1.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    log["n"] = len(items)
    log["n_risky"] = sum(1 for x in items if x["label_risky"])
    log["n_safe"] = sum(1 for x in items if not x["label_risky"])
    log["field_dist"] = Counter(x["field"] for x in items)
    (DATA / "e1_meta.json").write_text(
        json.dumps({**log, "field_dist": dict(log["field_dist"])}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return items, log


ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조")


def extract_articles(relate) -> list[int]:
    texts = []
    if isinstance(relate, list):
        texts = [str(x) for x in relate]
    elif isinstance(relate, str):
        texts = [relate]
    found = []
    for t in texts:
        for m in ARTICLE_RE.finditer(t):
            found.append(int(m.group(1)))
    # unique preserve order, only 6-14 for 약관법 context mostly - keep all then filter later
    out = []
    for a in found:
        if a not in out:
            out.append(a)
    return out


def prepare_e2(rows, yak_meta, n=200):
    rng = random.Random(SEED)
    log = {"extract_fail": 0, "extract_ok": 0, "excluded_rare": 0}
    candidates = []
    for r in rows:
        if r["adv"] != "2":
            continue
        cl = (r["clause"] or "").strip()
        if len(cl) < 20 or len(cl) > 1500:
            continue
        arts = extract_articles(r["relate"])
        # keep only articles that exist in 약관법 6-14 choice set ideally
        arts = [a for a in arts if 6 <= a <= 14]
        if not arts:
            log["extract_fail"] += 1
            continue
        log["extract_ok"] += 1
        candidates.append({**r, "gold_articles": arts})
    # frequency by primary (first) and any
    freq = Counter()
    for c in candidates:
        for a in c["gold_articles"]:
            freq[a] += 1
    log["article_freq"] = dict(sorted(freq.items()))
    rare = {a for a, cnt in freq.items() if cnt < 15}
    filtered = []
    for c in candidates:
        # exclude if ALL gold articles are rare-only (<15)
        if all(a in rare for a in c["gold_articles"]):
            log["excluded_rare"] += 1
            continue
        filtered.append(c)
    # stratify by first gold article among those with >=15
    groups = defaultdict(list)
    for c in filtered:
        primary = next((a for a in c["gold_articles"] if freq[a] >= 15), c["gold_articles"][0])
        groups[primary].append(c)
    # drop groups with <15 available after filter? keep if any
    groups = {k: v for k, v in groups.items() if len(v) >= 1 and freq[k] >= 15}
    items_raw = stratified_sample(groups, n, rng)
    items = []
    for i, r in enumerate(items_raw):
        items.append(
            {
                "id": f"E2-{i:04d}",
                "field": r["field"],
                "clause": r["clause"].strip(),
                "gold_articles": r["gold_articles"],
                "source": r["path"],
            }
        )
    # choices from remaining article numbers in sample + yak titles
    used = sorted({a for it in items for a in it["gold_articles"] if 6 <= a <= 14})
    titles = yak_meta.get("titles") or {}
    # default titles fallback
    default_titles = {
        6: "일반원칙",
        7: "면책조항의 금지",
        8: "손해배상액의 예정",
        9: "계약의 해제·해지",
        10: "채무의 이행",
        11: "고객의 권익 보호",
        12: "의사표시의 의제",
        13: "대리인의 책임 가중",
        14: "소송 제기의 금지 등",
    }
    choice_nums = used if used else list(range(6, 15))
    choice_strs = []
    for a in sorted(choice_nums):
        t = titles.get(str(a)) or titles.get(a) or default_titles.get(a, "")
        choice_strs.append(f"제{a}조({t})" if t else f"제{a}조")
    choices_line = ", ".join(choice_strs)
    path = DATA / "e2.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    (DATA / "e2_choices.json").write_text(
        json.dumps(
            {"articles": sorted(choice_nums), "choices_line": choices_line, "titles": {str(k): titles.get(k) or titles.get(str(k)) or default_titles.get(int(k) if str(k).isdigit() else k, "") for k in choice_nums}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # update user_e2 is template with {choices} — runtime fills
    log["n"] = len(items)
    log["choice_articles"] = sorted(choice_nums)
    log["primary_dist"] = dict(Counter(it["gold_articles"][0] for it in items))
    (DATA / "e2_meta.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return items, log


def looks_like_title_only(text: str) -> bool:
    t = text.strip()
    if len(t) < 20:
        return True
    # 제N조(...) alone
    if re.fullmatch(r"제\s*\d+\s*조\s*(의\s*\d+)?\s*(\([^)]*\))?\s*", t):
        return True
    return False


def prepare_e3(n=200):
    rng = random.Random(SEED)
    log = {"excluded_short_title": 0, "docs": 0}
    sections = []  # with doc_id
    for p in FORMS.rglob("*.json"):
        # only TL/VL labeled typically have content_labels
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc = o.get("document") or {}
        meta = ((doc.get("metadata") or {}).get("file_info") or {})
        cat = meta.get("document_category") or {}
        detail = cat.get("detail_category") or ""
        if detail not in E3_SUBCATS:
            continue
        doc_id = meta.get("document_name") or p.stem
        log["docs"] += 1
        for sec in doc.get("sections") or []:
            content = sec.get("content") or {}
            labels = content.get("content_labels") or []
            desc = (content.get("description") or "").strip()
            if looks_like_title_only(desc) or len(desc) < 20:
                log["excluded_short_title"] += 1
                continue
            labels = [lb for lb in labels if lb not in E3_EXCLUDE_LABELS]
            if not labels:
                continue
            sections.append(
                {
                    "doc_id": doc_id,
                    "category": detail,
                    "clause": desc,
                    "gold_labels": labels,
                    "source": str(p),
                    "section_id": sec.get("id"),
                }
            )
    # label frequencies
    lab_freq = Counter()
    for s in sections:
        for lb in s["gold_labels"]:
            lab_freq[lb] += 1
    # labels with >=30 sections, top 25
    kept_labels = [lb for lb, c in lab_freq.most_common() if c >= 30][:25]
    (DATA / "e3_labels.json").write_text(
        json.dumps(
            {"labels": kept_labels, "freq": {lb: lab_freq[lb] for lb in kept_labels}, "all_freq": dict(lab_freq)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # empty defs for human
    defs = {lb: "" for lb in kept_labels}
    (DATA / "e3_label_defs.json").write_text(
        json.dumps({"defs": defs, "note": "사람 작성 필요 — 비어 있으면 C2는 예시만(라벨 이름만 사용)"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # filter sections to those with at least one kept label
    sections = [s for s in sections if any(lb in kept_labels for lb in s["gold_labels"])]
    for s in sections:
        s["gold_labels"] = [lb for lb in s["gold_labels"] if lb in kept_labels]

    # doc-level split 80/20
    docs = sorted({s["doc_id"] for s in sections})
    rng.shuffle(docs)
    n_train = int(len(docs) * 0.8)
    train_docs = set(docs[:n_train])
    test_docs = set(docs[n_train:])
    train_secs = [s for s in sections if s["doc_id"] in train_docs]
    test_secs = [s for s in sections if s["doc_id"] in test_docs]
    log["n_docs"] = len(docs)
    log["n_train_docs"] = len(train_docs)
    log["n_test_docs"] = len(test_docs)
    log["n_train_secs"] = len(train_secs)
    log["n_test_secs"] = len(test_secs)

    # C2 exemplars: per label median-length from train
    exemplars = {}
    by_lab = defaultdict(list)
    for s in train_secs:
        for lb in s["gold_labels"]:
            by_lab[lb].append(s)
    for lb in kept_labels:
        pool = by_lab.get(lb) or []
        if not pool:
            continue
        lengths = sorted(len(x["clause"]) for x in pool)
        med = lengths[len(lengths) // 2]
        best = min(pool, key=lambda x: abs(len(x["clause"]) - med))
        exemplars[lb] = {"clause": best["clause"], "doc_id": best["doc_id"], "len": len(best["clause"])}
    (DATA / "e3_exemplars.json").write_text(
        json.dumps(exemplars, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # test stratified: per label max 10, total 200
    test_by_lab = defaultdict(list)
    for s in test_secs:
        # primary = first gold label
        primary = s["gold_labels"][0]
        test_by_lab[primary].append(s)
    picked = []
    for lb in kept_labels:
        pool = list(test_by_lab.get(lb) or [])
        rng.shuffle(pool)
        picked.extend(pool[:10])
    rng.shuffle(picked)
    if len(picked) > n:
        picked = picked[:n]
    elif len(picked) < n:
        # fill from remaining test
        rem = [s for s in test_secs if s not in picked]
        rng.shuffle(rem)
        picked.extend(rem[: n - len(picked)])

    items = []
    for i, s in enumerate(picked[:n]):
        items.append(
            {
                "id": f"E3-{i:04d}",
                "doc_id": s["doc_id"],
                "category": s["category"],
                "clause": s["clause"],
                "gold_labels": s["gold_labels"],
                "source": s["source"],
            }
        )
    with (DATA / "e3.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    # save train corpus for R2
    with (DATA / "e3_train_sections.jsonl").open("w", encoding="utf-8") as f:
        for s in train_secs:
            f.write(
                json.dumps(
                    {
                        "doc_id": s["doc_id"],
                        "category": s["category"],
                        "clause": s["clause"],
                        "gold_labels": s["gold_labels"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    log["n"] = len(items)
    log["label_dist"] = dict(Counter(it["gold_labels"][0] for it in items))
    log["kept_labels"] = kept_labels
    (DATA / "e3_meta.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return items, log


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    print("1) yakgwan law")
    yak = prepare_yakgwan()
    print("  articles", yak["n_articles"], "chars", yak["n_chars"])
    print("2) load terms")
    rows = load_terms_rows()
    print("  rows", len(rows))
    print("3) E1")
    e1, m1 = prepare_e1(rows)
    print("  n", m1["n"], "risky", m1["n_risky"], "fields", m1["ok_fields"])
    print("4) E2")
    e2, m2 = prepare_e2(rows, yak)
    print("  n", m2["n"], "fail", m2["extract_fail"], "choices", m2["choice_articles"])
    print("5) E3")
    e3, m3 = prepare_e3()
    print("  n", m3["n"], "labels", len(m3["kept_labels"]), "docs", m3["n_docs"])
    summary = {
        "yakgwan": yak,
        "e1": {k: m1[k] for k in ("n", "n_risky", "n_safe", "ok_fields", "excluded_short_long")},
        "e2": {k: m2[k] for k in ("n", "extract_fail", "extract_ok", "excluded_rare", "choice_articles", "article_freq")},
        "e3": {k: m3[k] for k in ("n", "n_docs", "n_train_docs", "n_test_docs", "kept_labels", "excluded_short_title")},
    }
    (DATA / "prepare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("done", DATA)


if __name__ == "__main__":
    main()
