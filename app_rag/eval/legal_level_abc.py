# -*- coding: utf-8 -*-
"""LEGAL_LEVEL A~C: EXAONE_tuned rows + freeze fixed 재집계 (모델 호출 없음)."""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from final_test_analyze import apply_settings  # noqa: E402
from final_test_common import FIXED, QTEST, load_json  # noqa: E402
from metrics import RISKY, WARN  # noqa: E402
from rag.corpus import load_corpus  # noqa: E402
from rag.paths import GOLD  # noqa: E402
from recall_dev import (  # noqa: E402
    ART_RE,
    canon_from_id,
    compact,
    gold_in_corpus,
    hit_matches_gold,
    keys_from_gold,
    load_jsonl,
)
from replay import load_rows  # noqa: E402

OUT = APP / "out" / "legal_level"
DOMAINS = ("LAB", "LEASE", "LOAN")
SEED = 42


def pct(n: int, d: int) -> float | None:
    if d <= 0:
        return None
    return round(100.0 * n / d, 1)


def fmt_rate(n: int, d: int, *, small_note: bool = True) -> str:
    if d <= 0:
        return "— (0/0)"
    note = " · 표본 적음" if small_note and d < 5 else ""
    return f"{pct(n, d)}% ({n}/{d}){note}"


def load_code_names() -> dict[str, str]:
    """toxic_code → 최빈 violation_name."""
    out: dict[str, str] = {}
    for domain in DOMAINS:
        counts: dict[str, Counter] = defaultdict(Counter)
        for row in load_jsonl(GOLD[domain]["law"]):
            codes = row.get("toxic_code") or []
            if isinstance(codes, str):
                codes = [codes]
            vn = (row.get("violation_name") or "").strip() or "(이름 없음)"
            for c in codes:
                if c:
                    counts[c][vn] += 1
        for code, ctr in counts.items():
            out[code] = ctr.most_common(1)[0][0]
    return out


def load_law_by_segment() -> dict[str, dict]:
    m: dict[str, dict] = {}
    for domain in DOMAINS:
        for row in load_jsonl(GOLD[domain]["law"]):
            sid = row.get("segment_id")
            if sid:
                m[sid] = row
    return m


def grade_of(risky_n: int, warn_n: int, n: int) -> str:
    if n <= 0:
        return "—"
    risky_r = risky_n / n
    warn_r = warn_n / n
    if risky_r >= 0.70:
        return "확실히 잡음"
    if warn_r >= 0.80:
        return "경고는 함"
    return "놓치는 편"


def character_line(names: list[str], grade: str) -> str:
    blob = " ".join(names)
    if any(k in blob for k in ("최저임금", "이자", "연 ", "감액", "가산", "증액", "한도")):
        kind = "숫자·한도로 판단하는 조항"
    elif any(k in blob for k in ("포기", "배제", "금지", "강제", "위약", "공제", "사전")):
        kind = "금지·포기 문구가 비교적 분명한 조항"
    else:
        kind = "해석·맥락이 필요한 조항"
    return f"{grade}: {kind} — 예: " + ", ".join(names[:5]) + ("…" if len(names) > 5 else "")


def type_table(rows: list[dict], label: str, code_names: dict[str, str]) -> list[dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("label") != label:
            continue
        codes = r.get("gold_codes") or ["(none)"]
        for c in codes:
            by[c or "(none)"].append(r)
    table = []
    for code in sorted(by.keys()):
        rs = by[code]
        n = len(rs)
        risky = sum(1 for r in rs if r.get("verdict") in RISKY)
        check = sum(1 for r in rs if r.get("verdict") == "확인 필요")
        ok = sum(1 for r in rs if r.get("verdict") == "문제 없음")
        warn = risky + check
        table.append(
            {
                "code": code,
                "name": code_names.get(code, code),
                "n": n,
                "risky_n": risky,
                "check_n": check,
                "ok_n": ok,
                "warn_n": warn,
                "risky_pct": pct(risky, n),
                "check_pct": pct(check, n),
                "ok_pct": pct(ok, n),
                "warn_pct": pct(warn, n),
                "grade": grade_of(risky, warn, n),
                "small_n": n < 5,
            }
        )
    return table


def provision_key_from_any(text: str) -> list[tuple[str, str]]:
    return keys_from_gold(text or "")


def evidence_keys(ev: dict) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    eid = ev.get("id") or ""
    parsed = canon_from_id(eid) if eid else None
    if parsed:
        keys.append(parsed)
    title = ev.get("title") or ""
    keys.extend(provision_key_from_any(title))
    # title may include [법령] prefix
    title2 = re.sub(r"^\[.*?\]\s*", "", title)
    if title2 != title:
        keys.extend(provision_key_from_any(title2))
    return keys


def gold_keys_from_raws(raws: list[str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for g in raws:
        keys.update(keys_from_gold(g))
    return keys


def match_evidence_to_gold(evs: list[dict], gold_raws: list[str]) -> bool:
    gkeys = gold_keys_from_raws(gold_raws)
    for ev in evs:
        eid = ev.get("id") or ""
        if eid and hit_matches_gold(eid, gkeys, gold_raws):
            return True
        for k in evidence_keys(ev):
            if k in gkeys:
                return True
        # title-only compact overlap fallback (same as hit_matches_gold raw path)
        title = compact(ev.get("title") or "")
        if title and any(compact(g) and (compact(g) in title or title in compact(g)) for g in gold_raws):
            # require article number presence to avoid law-name-only false match
            if ART_RE.search(ev.get("title") or "") and any(ART_RE.search(g or "") for g in gold_raws):
                ev_arts = {a for _, a in evidence_keys(ev)}
                g_arts = {a for _, a in gold_keys_from_raws(gold_raws)}
                if ev_arts & g_arts:
                    return True
    return False


def matching_rule_source() -> str:
    return '''
def keys_from_gold(raw: str) -> list[tuple[str, str]]:
    # ART_RE = r"제\\s*(\\d+)\\s*조(?:의\\s*(\\d+))?"
    # return [(법령이름_공백제거, "56" | "428의2"), ...]  # 항은 무시, 조의는 구분

def match(evidence, gold_provisions) -> bool:
    # evidence_final 중 하나라도:
    #   canon_from_id(evidence.id) ∈ keys_from_gold(gold)
    #   또는 title에서 뽑은 (법령, 조)가 gold와 같으면 일치
    # 항(제N항)은 비교하지 않음. "제428조의2"는 "제428조"와 다름.
'''.strip()


def norm_examples(pairs: list[tuple[str, str]], n: int = 10) -> list[dict]:
    out = []
    for before, after in pairs[:n]:
        out.append({"before": before, "after": after})
    return out


def analyze_B(rows: list[dict], corpus_keys: set, corpus_ids: list[str]) -> dict:
    by_domain: dict[str, dict] = {}
    mismatches = []
    examples_raw: list[tuple[str, str]] = []

    for domain in DOMAINS:
        match = zero = wrong = eligible = corpus_miss = 0
        for r in rows:
            if r.get("domain") != domain:
                continue
            if r.get("label") != "toxic":
                continue
            if r.get("verdict") not in WARN:
                continue
            golds = list(r.get("gold_provisions") or [])
            if not golds:
                continue
            in_c = [g for g in golds if gold_in_corpus(g, corpus_keys, corpus_ids)]
            if not in_c:
                corpus_miss += 1
                continue
            eligible += 1
            for g in in_c:
                ks = keys_from_gold(g)
                if ks and len(examples_raw) < 20:
                    examples_raw.append((g, " | ".join(f"{n} 제{a}조" if "의" not in a else f"{n} 제{a.split('의')[0]}조의{a.split('의')[1]}" for n, a in ks)))
            evs = r.get("evidence_final") or []
            if not evs:
                zero += 1
                if len(mismatches) < 30:
                    mismatches.append(
                        {
                            "kind": "zero",
                            "domain": domain,
                            "doc_id": r.get("doc_id"),
                            "segment_id": r.get("segment_id"),
                            "text": (r.get("text") or "")[:200],
                            "model_evidence": [],
                            "gold_provisions": golds,
                            "verdict": r.get("verdict"),
                        }
                    )
                continue
            if match_evidence_to_gold(evs, in_c):
                match += 1
            else:
                wrong += 1
                if len(mismatches) < 40:
                    mismatches.append(
                        {
                            "kind": "wrong",
                            "domain": domain,
                            "doc_id": r.get("doc_id"),
                            "segment_id": r.get("segment_id"),
                            "text": (r.get("text") or "")[:200],
                            "model_evidence": [
                                {
                                    "id": e.get("id"),
                                    "title": e.get("title"),
                                    "norm": [
                                        f"{n}/제{a}조" if "의" not in a else f"{n}/제{a}조"
                                        for n, a in evidence_keys(e)
                                    ],
                                }
                                for e in evs[:5]
                            ],
                            "gold_provisions": golds,
                            "gold_norm": [
                                f"{n}/제{a}조" if "의" not in a else f"{n}/제{a}조"
                                for n, a in gold_keys_from_raws(in_c)
                            ],
                            "verdict": r.get("verdict"),
                        }
                    )
        by_domain[domain] = {
            "eligible": eligible,
            "match_n": match,
            "zero_n": zero,
            "wrong_n": wrong,
            "corpus_miss_n": corpus_miss,
            "match_rate": fmt_rate(match, eligible),
            "zero_rate": fmt_rate(zero, eligible),
            "wrong_rate": fmt_rate(wrong, eligible),
            "corpus_miss": corpus_miss,
        }
    # prefer wrong mismatches for the 10 reported cases
    wrong_cases = [m for m in mismatches if m["kind"] == "wrong"][:10]
    if len(wrong_cases) < 10:
        wrong_cases = wrong_cases + [m for m in mismatches if m["kind"] == "zero"][: 10 - len(wrong_cases)]
    return {
        "by_domain": by_domain,
        "mismatch_cases": wrong_cases,
        "norm_examples": norm_examples(examples_raw, 10),
        "matching_rule": matching_rule_source(),
    }


def build_review_sheet(rows: list[dict], law_by_seg: dict[str, dict], code_names: dict[str, str]) -> list[dict]:
    toxic = [r for r in rows if r.get("label") == "toxic"]
    by_dom: dict[str, list[dict]] = defaultdict(list)
    for r in toxic:
        by_dom[r.get("domain") or ""].append(r)
    rng = random.Random(SEED)
    picked = []
    for domain in DOMAINS:
        pool = list(by_dom.get(domain) or [])
        rng.shuffle(pool)
        picked.extend(pool[:10])
    sheet = []
    for r in picked:
        law = law_by_seg.get(r.get("segment_id") or "", {})
        codes = r.get("gold_codes") or []
        name = " / ".join(code_names.get(c, c) for c in codes) if codes else (law.get("violation_name") or "")
        ev_titles = []
        for e in r.get("evidence_final") or []:
            t = e.get("title") or e.get("id") or ""
            if t:
                ev_titles.append(t)
        sheet.append(
            {
                "분야": r.get("domain"),
                "doc_id": r.get("doc_id"),
                "segment_id": r.get("segment_id"),
                "조항 원문": (r.get("text") or "").replace("\n", " "),
                "모델 판정": r.get("verdict"),
                "모델 설명(why)": ((r.get("finding") or {}).get("why") or r.get("why") or ""),
                "모델 수정 문구(suggestion)": ((r.get("finding") or {}).get("suggestion") or ""),
                "모델 근거 조문 제목": " | ".join(ev_titles),
                "정답 유형 이름": name or law.get("violation_name") or "",
                "정답 설명(why)": law.get("why") or "",
                "정답 수정 예시(suggested_revision)": law.get("suggested_revision") or "",
                "정답 근거 조문": " | ".join(r.get("gold_provisions") or law.get("legal_provisions") or []),
                "판정_맞음": "",
                "이유_맞음": "",
                "근거_맞음": "",
                "수정문구_문제해소": "",
            }
        )
    return sheet


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    freeze = load_json(QTEST / "freeze.json")
    settings = dict(freeze.get("fixed") or FIXED)
    code_names = load_code_names()
    law_by_seg = load_law_by_segment()

    all_rows: list[dict] = []
    for domain in DOMAINS:
        path = QTEST / f"EXAONE_tuned_{domain}_rows.jsonl"
        raw = load_rows(path)
        tr = apply_settings(raw, settings)
        for r in tr:
            r["domain"] = domain
        all_rows.extend(tr)
        (OUT / f"transformed_{domain}_meta.json").write_text(
            json.dumps({"n": len(tr), "settings": settings, "path": str(path)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    toxic_table = type_table(all_rows, "toxic", code_names)
    check_table = type_table(all_rows, "check", code_names)

    def summarize_grades(table: list[dict]) -> dict:
        g: dict[str, list[str]] = defaultdict(list)
        for row in table:
            g[row["grade"]].append(f"{row['code']} {row['name']} (n={row['n']})")
        lines = {}
        for grade in ("확실히 잡음", "경고는 함", "놓치는 편"):
            names = [x.split(" ", 1)[-1].rsplit(" (n=", 1)[0] for x in g.get(grade, [])]
            lines[grade] = {
                "codes": g.get(grade, []),
                "n_types": len(g.get(grade, [])),
                "character": character_line(names, grade) if names else f"{grade}: (해당 유형 없음)",
            }
        return lines

    corpus, _ = load_corpus()
    corpus_ids = [c["id"] for c in corpus]
    corpus_keys: set[tuple[str, str]] = set()
    for c in corpus:
        k = canon_from_id(c["id"])
        if k:
            corpus_keys.add(k)

    b = analyze_B(all_rows, corpus_keys, corpus_ids)

    # more norm examples from gold+evidence mix if short
    if len(b["norm_examples"]) < 10:
        extra = []
        for r in all_rows:
            for g in r.get("gold_provisions") or []:
                ks = keys_from_gold(g)
                if ks:
                    after = " | ".join(
                        f"{n} 제{a.split('의')[0]}조의{a.split('의')[1]}" if "의" in a else f"{n} 제{a}조"
                        for n, a in ks
                    )
                    extra.append({"before": g, "after": after})
            if len(extra) >= 10:
                break
        b["norm_examples"] = (b["norm_examples"] + extra)[:10]

    sheet = build_review_sheet(all_rows, law_by_seg, code_names)
    sheet_path = OUT / "review_sheet.csv"
    with sheet_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sheet[0].keys()) if sheet else [])
        w.writeheader()
        w.writerows(sheet)

    # A totals for summary lines
    def grade_counts(table, grade):
        rows = [t for t in table if t["grade"] == grade]
        n = sum(t["n"] for t in rows)
        risky = sum(t["risky_n"] for t in rows)
        warn = sum(t["warn_n"] for t in rows)
        return {"types": len(rows), "n": n, "risky": risky, "warn": warn}

    result = {
        "settings": settings,
        "n_rows": len(all_rows),
        "A_toxic": toxic_table,
        "A_check": check_table,
        "A_toxic_grades": summarize_grades(toxic_table),
        "A_check_grades": summarize_grades(check_table),
        "A_toxic_grade_totals": {g: grade_counts(toxic_table, g) for g in ("확실히 잡음", "경고는 함", "놓치는 편")},
        "B": b,
        "C": {"sheet": str(sheet_path), "n_rows": len(sheet), "seed": SEED},
    }
    (OUT / "abc_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "n_rows": len(all_rows),
                "toxic_types": len(toxic_table),
                "check_types": len(check_table),
                "sheet_rows": len(sheet),
                "B_LAB": b["by_domain"]["LAB"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
