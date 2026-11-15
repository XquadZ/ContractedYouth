# -*- coding: utf-8 -*-
"""증류 데이터 점검: 32B reason 길이·반복·구체성. GPU 미사용. 읽기 전용."""
from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
OUT = ROOT / "exp_gap2" / "out"
DATA2 = ROOT / "exp_gap2" / "data"
DATA1 = ROOT / "exp_gap1" / "data"
AUDIT = ROOT / "exp_gap2" / "distill_audit"
TOK_DIR = ROOT / "data_contract" / "models" / "Qwen3-8B"
LAW_PATH = DATA1 / "law_yakgwan_6_14.txt"

SKIPPED: list[str] = []
META: dict = {
    "tokenizer_path": str(TOK_DIR),
    "morph_analyzer": None,
    "content_token_method": None,
    "sentence_rule": (
        "문장 분리: 정규식 `(?<=다)\\.|[.。]` 로 분할 후 공백 제거·빈 조각 제외. "
        "즉 '다.' 직전 경계와 일반 마침표(./。)를 경계로 센다."
    ),
}

# --- helpers ---

def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def pctile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    k = (len(ys) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(ys[int(k)])
    return float(ys[f] * (c - k) + ys[c] * (k - f))


def stats_block(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None, "min": None, "max": None}
    return {
        "n": len(xs),
        "mean": round(statistics.mean(xs), 3),
        "median": round(statistics.median(xs), 3),
        "p10": round(pctile(xs, 10), 3),
        "p90": round(pctile(xs, 90), 3),
        "min": round(min(xs), 3),
        "max": round(max(xs), 3),
    }


def normalize_dup(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w가-힣]", "", s, flags=re.UNICODE)
    return s


def eojeols(s: str) -> list[str]:
    return [t for t in re.split(r"\s+", s.strip()) if t]


PARTICLES = (
    "으로부터", "에서부터", "에게서", "한테서", "으로부터의",
    "으로서", "으로써", "에서는", "에도", "이나마",
    "부터", "까지", "에게", "한테", "께서", "으로", "로서", "로써",
    "이나", "이나", "에서", "으로", "처럼", "만큼", "대로",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
)


def strip_particle(w: str) -> str:
    for p in sorted(PARTICLES, key=len, reverse=True):
        if len(w) > len(p) + 1 and w.endswith(p):
            return w[: -len(p)]
    return w


def content_tokens(text: str) -> list[str]:
    """kiwi 없음 → 2글자 이상 어절에서 조사 제거 후, 앞 2글자 매칭용 토큰."""
    out = []
    for w in eojeols(text):
        w = re.sub(r"[^\w가-힣]", "", w)
        if len(w) < 2:
            continue
        stem = strip_particle(w)
        if len(stem) < 2:
            continue
        out.append(stem[:2])  # 앞 2글자 매칭 키
    return out


def content_stems(text: str) -> list[str]:
    out = []
    for w in eojeols(text):
        w = re.sub(r"[^\w가-힣]", "", w)
        if len(w) < 2:
            continue
        stem = strip_particle(w)
        if len(stem) >= 2:
            out.append(stem)
    return out


def char_ngrams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+", "", s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def sentence_count(s: str) -> int:
    parts = re.split(r"(?<=다)\.|[.。]", s)
    parts = [p.strip() for p in parts if p.strip()]
    return max(1, len(parts)) if s.strip() else 0


def extract_articles_mentioned(reason: str) -> list[int]:
    return [int(x) for x in re.findall(r"제\s*(\d+)\s*조", reason)]


EXTERNAL_LAWS = [
    "민법", "상법", "형법", "근로기준법", "소비자기본법", "개인정보보호법",
    "개인정보 보호법", "전자상거래법", "전자상거래 등에서의 소비자보호에 관한 법률",
    "공정거래법", "독점규제", "하도급법", "주택법", "집합건물법", "상가건물임대차보호법",
    "임대차보호법", "신용정보법", "정보통신망법", "금융소비자보호법", "할부거래법",
    "방문판매법", "약관의규제에관한법률",  # 정식명 — 약관법 별칭과 구분용으로 목록만
]
# 약관법 / 약관의 규제에 관한 법률 은 "자료 안"으로 취급 → 외부 목록에서 약관법 제외


def find_external_laws(reason: str) -> list[str]:
    found = []
    for name in EXTERNAL_LAWS:
        if name in reason:
            found.append(name)
    # 약관법·약관의 규제에 관한 법률은 제외
    found = [f for f in found if f not in ("약관의규제에관한법률",)]
    return found


PROMPT_TERMS = ["<자료>", "자료에", "제공된", "</자료>", "<자료", "자료>"]


def has_prompt_term(reason: str) -> bool:
    return any(t in reason for t in PROMPT_TERMS)


SOFT_MARKERS = ["보인다", "추정", "가능성", "수 있다"]


def parse_law(path: Path) -> dict[int, dict]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^제\d+조)", text, flags=re.M)
    arts: dict[int, dict] = {}
    for b in blocks:
        m = re.match(r"제(\d+)조\(([^)]+)\)", b.strip())
        if not m:
            continue
        num = int(m.group(1))
        title = m.group(2)
        arts[num] = {"title": title, "body": b.strip(), "title_line": f"제{num}조({title})"}
    return arts


class UF:
    def __init__(self, n):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1


def main():
    t0 = time.time()
    AUDIT.mkdir(parents=True, exist_ok=True)
    META["morph_analyzer"] = "none (kiwipiepy not installed)"
    META["content_token_method"] = (
        "fallback: 2글자 이상 어절에서 조사 제거 후 앞 2글자로 clause/조문 매칭"
    )

    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(TOK_DIR / "tokenizer.json"))
    META["tokenizer_backend"] = "tokenizers.Tokenizer.from_file(tokenizer.json)"

    def n_tokens(s: str) -> int:
        return len(tok.encode(s).ids)

    law = parse_law(LAW_PATH)
    gold_rows = {r["id"]: r for r in load_jsonl(DATA2 / "e2_test1000.jsonl")}
    c4_cands = {r["id"]: r for r in load_jsonl(DATA2 / "e2_c4_candidates.jsonl")}
    gap1_e2 = load_jsonl(DATA1 / "e2.jsonl")

    def norm_clause(c: str) -> str:
        return re.sub(r"\s+", "", c or "")

    gap1_norms = {norm_clause(r["clause"]) for r in gap1_e2}
    gap1_sources = {r.get("source") for r in gap1_e2}

    sources_spec = [
        ("32B_C2", OUT / "32B_E2_C2.jsonl", "C2", "32B"),
        ("32B_C4", OUT / "32B_E2_C4.jsonl", "C4", "32B"),
        ("32B_C5", OUT / "32B_E2_C5.jsonl", "C5", "32B"),
        ("8B_C2", OUT / "8B_E2_C2.jsonl", "C2", "8B"),
        ("8B_C4", OUT / "8B_E2_C4.jsonl", "C4", "8B"),
    ]

    all_items: list[dict] = []
    parse_fail_counts: dict[str, int] = {}
    empty_reason_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}

    for src_key, path, cond, model in sources_spec:
        rows = load_jsonl(path)
        file_counts[src_key] = len(rows)
        pf = er = 0
        for r in rows:
            g = gold_rows.get(r["id"], {})
            parsed = r.get("parsed") or {}
            parse_ok = bool(r.get("parse_ok"))
            arts = parsed.get("articles") if isinstance(parsed, dict) else None
            reason = (parsed.get("reason") if isinstance(parsed, dict) else None) or ""
            if not parse_ok or arts is None:
                pf += 1
                continue
            if isinstance(arts, int):
                arts = [arts]
            elif not isinstance(arts, list):
                pf += 1
                continue
            if not str(reason).strip():
                er += 1
                continue
            reason = str(reason)
            top1 = arts[0] if arts else None
            gold = set(g.get("gold_articles") or [])
            correct = bool(top1 is not None and top1 in gold)
            cands = None
            if cond == "C4":
                cands = (c4_cands.get(r["id"]) or {}).get("candidates")
            clause = g.get("clause") or ""
            item = {
                "src": src_key,
                "model": model,
                "cond": cond,
                "id": r["id"],
                "correct": correct,
                "parse_ok": True,
                "reason": reason,
                "articles": arts,
                "top1": top1,
                "gold": list(gold),
                "clause": clause,
                "candidates": cands,
                "group": "정답" if correct else "오답",
            }
            all_items.append(item)
        parse_fail_counts[src_key] = pf
        empty_reason_counts[src_key] = er

    # per-item features
    for it in all_items:
        reason = it["reason"]
        it["n_char"] = len(reason)
        it["n_sent"] = sentence_count(reason)
        it["n_tok"] = n_tokens(reason)
        it["norm"] = normalize_dup(reason)
        it["eojs"] = eojeols(reason)
        it["cgrams"] = char_ngrams(reason, 3)
        ct = content_tokens(reason)
        clause_keys = set(content_tokens(it["clause"]))
        if ct:
            it["clause_cite"] = sum(1 for t in ct if t in clause_keys) / len(ct)
        else:
            it["clause_cite"] = 0.0
        art0 = it["top1"]
        law_text = ""
        if art0 in law:
            law_text = law[art0]["title_line"] + "\n" + law[art0]["body"]
        law_keys = set(content_tokens(law_text))
        if ct:
            it["law_repeat"] = sum(1 for t in ct if t in law_keys) / len(ct)
        else:
            it["law_repeat"] = 0.0
        it["generic_015_05"] = it["clause_cite"] < 0.15 and it["law_repeat"] >= 0.5
        it["generic_010_04"] = it["clause_cite"] < 0.10 and it["law_repeat"] >= 0.4
        it["generic_020_06"] = it["clause_cite"] < 0.20 and it["law_repeat"] >= 0.6
        mentioned = extract_articles_mentioned(reason)
        it["mentioned_arts"] = mentioned
        arts_set = set(it["articles"] or [])
        it["halluc_art"] = bool(mentioned) and any(a not in arts_set for a in mentioned)
        it["miss_top1_mention"] = art0 is not None and art0 not in mentioned
        ext = find_external_laws(reason)
        it["ext_laws"] = ext
        it["has_ext_law"] = bool(ext)
        it["has_prompt"] = has_prompt_term(reason)
        it["soft"] = any(m in reason for m in SOFT_MARKERS)
        if it["cond"] == "C4" and it["candidates"] is not None:
            cand_set = set(it["candidates"])
            it["c4_ood_mention"] = any(a not in cand_set for a in mentioned)
        else:
            it["c4_ood_mention"] = None
        it["gap1_overlap_norm"] = norm_clause(it["clause"]) in gap1_norms
        src_path = (gold_rows.get(it["id"]) or {}).get("source")
        it["gap1_overlap_source"] = src_path in gap1_sources if src_path else False

    # exact dup flags per (src, group)
    by_sg: dict[tuple, list] = defaultdict(list)
    for it in all_items:
        by_sg[(it["src"], it["group"])].append(it)

    for key, items in by_sg.items():
        cnt = Counter(it["norm"] for it in items)
        for it in items:
            it["exact_dup"] = cnt[it["norm"]] >= 2

    # similar clusters per (src, group)
    cluster_info: dict[tuple, dict] = {}
    for key, items in by_sg.items():
        n = len(items)
        uf = UF(n)
        grams = [it["cgrams"] for it in items]
        # O(n^2) — n<=1000 ok on CPU
        for i in range(n):
            for j in range(i + 1, n):
                if jaccard(grams[i], grams[j]) >= 0.7:
                    uf.union(i, j)
        roots = [uf.find(i) for i in range(n)]
        clusters: dict[int, list[int]] = defaultdict(list)
        for i, r in enumerate(roots):
            clusters[r].append(i)
        multi = {r: idxs for r, idxs in clusters.items() if len(idxs) >= 2}
        for i, it in enumerate(items):
            r = roots[i]
            it["in_sim_cluster"] = r in multi
            it["sim_cluster_size"] = len(clusters[r])
        # top 5 largest multi
        top5 = sorted(multi.values(), key=len, reverse=True)[:5]
        top5_rep = []
        for idxs in top5:
            reps = [items[i]["reason"] for i in idxs[:3]]
            top5_rep.append({"size": len(idxs), "examples": reps})
        cluster_info[key] = {
            "n_clusters_multi": len(multi),
            "n_items_in_multi": sum(len(v) for v in multi.values()),
            "ratio_in_multi": (sum(len(v) for v in multi.values()) / n) if n else 0.0,
            "top5": top5_rep,
        }

    # write items.csv
    csv_path = AUDIT / "items.csv"
    fields = [
        "src", "model", "cond", "id", "group", "correct", "parse_ok",
        "n_char", "n_sent", "n_tok", "exact_dup", "in_sim_cluster", "sim_cluster_size",
        "clause_cite", "law_repeat", "generic_015_05", "generic_010_04", "generic_020_06",
        "halluc_art", "miss_top1_mention", "has_ext_law", "ext_laws", "has_prompt", "soft",
        "c4_ood_mention", "gap1_overlap_norm", "gap1_overlap_source",
        "top1", "articles", "candidates", "reason", "clause_head150",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for it in all_items:
            row = {k: it.get(k) for k in fields}
            row["articles"] = json.dumps(it["articles"], ensure_ascii=False)
            row["candidates"] = json.dumps(it["candidates"], ensure_ascii=False) if it["candidates"] is not None else ""
            row["ext_laws"] = "|".join(it["ext_laws"])
            row["clause_head150"] = (it["clause"] or "")[:150]
            w.writerow(row)

    def group_items(src: str, group: str) -> list[dict]:
        return by_sg.get((src, group), [])

    def length_report(items: list[dict]) -> dict:
        chars = [it["n_char"] for it in items]
        sents = [it["n_sent"] for it in items]
        toks = [it["n_tok"] for it in items]
        hist = Counter((c // 10) * 10 for c in chars)
        hist_rows = sorted(hist.items())
        return {
            "char": stats_block(chars),
            "sent": stats_block([float(x) for x in sents]),
            "tok": stats_block([float(x) for x in toks]),
            "lt40": sum(1 for c in chars if c < 40) / len(chars) if chars else None,
            "lt80": sum(1 for c in chars if c < 80) / len(chars) if chars else None,
            "tok_ge250": sum(1 for t in toks if t >= 250),
            "hist_10": hist_rows,
        }

    def exact_dup_report(items: list[dict]) -> dict:
        if not items:
            return {"n_dup_texts": 0, "item_ratio": None, "top10": []}
        cnt = Counter(it["norm"] for it in items)
        dup_norms = {n for n, c in cnt.items() if c >= 2}
        # map norm -> one original reason
        orig = {}
        for it in items:
            orig.setdefault(it["norm"], it["reason"])
        top10 = sorted(
            [(orig[n], cnt[n]) for n in dup_norms],
            key=lambda x: -x[1],
        )[:10]
        n_items_dup = sum(1 for it in items if it["norm"] in dup_norms)
        return {
            "n_dup_texts": len(dup_norms),
            "item_ratio": n_items_dup / len(items),
            "top10": [{"reason": r, "freq": f} for r, f in top10],
        }

    def trigram_report(items: list[dict]) -> list[dict]:
        tri = Counter()
        for it in items:
            ws = it["eojs"]
            for i in range(len(ws) - 2):
                tri[" ".join(ws[i : i + 3])] += 1
        top = tri.most_common(30)
        out = []
        for tg, freq in top:
            ratio = sum(1 for it in items if tg in " ".join(it["eojs"])) / len(items) if items else 0
            out.append({"trigram": tg, "count": freq, "reason_ratio": round(ratio, 4)})
        return out

    def start_end_report(items: list[dict]) -> dict:
        starts = Counter((it["reason"][:8] if len(it["reason"]) >= 8 else it["reason"]) for it in items)
        ends = Counter((it["reason"][-8:] if len(it["reason"]) >= 8 else it["reason"]) for it in items)
        return {
            "start_top15": starts.most_common(15),
            "end_top15": ends.most_common(15),
        }

    def vocab_div(items: list[dict]) -> dict:
        all_e = []
        for it in items:
            all_e.extend(it["eojs"])
        full = (len(set(all_e)) / len(all_e)) if all_e else None
        # subsample 299
        rng = random.Random(42)
        if len(items) >= 299:
            sub = rng.sample(items, 299)
        else:
            sub = list(items)
        se = []
        for it in sub:
            se.extend(it["eojs"])
        sub_div = (len(set(se)) / len(se)) if se else None
        return {"full": full, "n_full": len(items), "sub299": sub_div, "n_sub": len(sub)}

    def specificity(items: list[dict]) -> dict:
        cites = [it["clause_cite"] for it in items]
        laws = [it["law_repeat"] for it in items]
        return {
            "clause_cite": stats_block(cites),
            "clause_cite_zero_ratio": sum(1 for x in cites if x == 0) / len(cites) if cites else None,
            "law_repeat": stats_block(laws),
            "generic_015_05": sum(1 for it in items if it["generic_015_05"]) / len(items) if items else None,
            "generic_010_04": sum(1 for it in items if it["generic_010_04"]) / len(items) if items else None,
            "generic_020_06": sum(1 for it in items if it["generic_020_06"]) / len(items) if items else None,
        }

    def consistency(items: list[dict]) -> dict:
        if not items:
            return {}
        return {
            "halluc_art_ratio": sum(1 for it in items if it["halluc_art"]) / len(items),
            "miss_top1_mention_ratio": sum(1 for it in items if it["miss_top1_mention"]) / len(items),
            "ext_law_ratio": sum(1 for it in items if it["has_ext_law"]) / len(items),
            "ext_law_list": sorted({e for it in items for e in it["ext_laws"]}),
            "prompt_ratio": sum(1 for it in items if it["has_prompt"]) / len(items),
            "soft_ratio": sum(1 for it in items if it["soft"]) / len(items),
            "c4_ood_ratio": (
                sum(1 for it in items if it["c4_ood_mention"]) / len(items)
                if items and items[0]["cond"] == "C4"
                else None
            ),
        }

    def samples(items: list[dict], rng: random.Random) -> dict:
        gen = [it for it in items if it["generic_015_05"]]
        by_cite = sorted(items, key=lambda x: -x["clause_cite"])
        rnd = list(items)
        rng.shuffle(rnd)

        def pack(lst, k=10):
            out = []
            for it in lst[:k]:
                out.append({
                    "id": it["id"],
                    "articles": it["articles"],
                    "clause_cite": round(it["clause_cite"], 4),
                    "law_repeat": round(it["law_repeat"], 4),
                    "clause_head150": (it["clause"] or "")[:150],
                    "reason": it["reason"],
                })
            return out

        return {
            "generic10": pack(gen),
            "top_cite10": pack(by_cite),
            "random10": pack(rnd),
        }

    # build full report structure
    report_groups = []
    summary_rows = []
    for src_key, _, _, _ in sources_spec:
        for group in ("정답", "오답"):
            items = group_items(src_key, group)
            if not items and src_key.startswith("8B") and group == "오답":
                pass
            lr = length_report(items) if items else None
            ed = exact_dup_report(items) if items else None
            ci = cluster_info.get((src_key, group), {})
            sp = specificity(items) if items else None
            cs = consistency(items) if items else None
            tg = trigram_report(items) if items else []
            se = start_end_report(items) if items else {}
            vd = vocab_div(items) if items else {}
            sm = samples(items, random.Random(42)) if items else {}
            block = {
                "src": src_key,
                "group": group,
                "n": len(items),
                "length": lr,
                "exact_dup": ed,
                "sim": ci,
                "trigrams": tg,
                "start_end": se,
                "vocab": vd,
                "spec": sp,
                "cons": cs,
                "samples": sm,
            }
            report_groups.append(block)
            if lr and ed and sp and ci is not None:
                summary_rows.append({
                    "src": src_key,
                    "group": group,
                    "n": len(items),
                    "mean_char": lr["char"]["mean"],
                    "median_char": lr["char"]["median"],
                    "lt40": round(lr["lt40"], 4) if lr["lt40"] is not None else None,
                    "exact_dup": round(ed["item_ratio"], 4) if ed["item_ratio"] is not None else None,
                    "sim_ratio": round(ci.get("ratio_in_multi", 0), 4),
                    "clause_cite_mean": sp["clause_cite"]["mean"],
                    "generic": round(sp["generic_015_05"], 4) if sp["generic_015_05"] is not None else None,
                    "ext_law": round(cs["ext_law_ratio"], 4) if cs else None,
                })

    # section 5: 32B correct & 8B wrong same id
    def index_by_id(src):
        return {it["id"]: it for it in all_items if it["src"] == src}

    distill_pairs = []
    for cond, s32, s8 in [("C2", "32B_C2", "8B_C2"), ("C4", "32B_C4", "8B_C4")]:
        a = index_by_id(s32)
        b = index_by_id(s8)
        ids = []
        for i in a:
            if i in b and a[i]["correct"] and not b[i]["correct"]:
                ids.append(i)
        distill_pairs.append({"cond": cond, "n": len(ids), "ids": ids})

    # section 6 learning candidates (32B only)
    learn_tables = {}
    for src in ("32B_C2", "32B_C4", "32B_C5"):
        items = [it for it in all_items if it["src"] == src]
        corr = [it for it in items if it["correct"]]
        def cnt(pred):
            return sum(1 for it in corr if pred(it))
        learn_tables[src] = {
            "정답": len(corr),
            "정답∧완전중복아님": cnt(lambda it: not it["exact_dup"]),
            "정답∧일반형아님": cnt(lambda it: not it["generic_015_05"]),
            "정답∧자료밖법령없음∧프롬프트없음": cnt(lambda it: not it["has_ext_law"] and not it["has_prompt"]),
            "위모두": cnt(lambda it: (not it["exact_dup"]) and (not it["generic_015_05"]) and (not it["has_ext_law"]) and (not it["has_prompt"])),
        }

    # id overlap across sources among "위모두"
    def keep_ids(src):
        return {
            it["id"]
            for it in all_items
            if it["src"] == src
            and it["correct"]
            and not it["exact_dup"]
            and not it["generic_015_05"]
            and not it["has_ext_law"]
            and not it["has_prompt"]
        }

    id_c2, id_c4, id_c5 = keep_ids("32B_C2"), keep_ids("32B_C4"), keep_ids("32B_C5")
    all_keep = id_c2 | id_c4 | id_c5
    overlap_counts = {
        "C2∩C4": len(id_c2 & id_c4),
        "C2∩C5": len(id_c2 & id_c5),
        "C4∩C5": len(id_c4 & id_c5),
        "C2∩C4∩C5": len(id_c2 & id_c4 & id_c5),
        "unique_ids": len(all_keep),
    }

    # GAP-1 overlap among correct 32B (any cond) by norm / source
    corr32 = [it for it in all_items if it["model"] == "32B" and it["correct"]]
    gap1_n_norm = len({it["id"] for it in corr32 if it["gap1_overlap_norm"]})
    gap1_n_src = len({it["id"] for it in corr32 if it["gap1_overlap_source"]})
    # among keep set
    keep_items = [it for it in corr32 if it["id"] in all_keep]
    gap1_keep_norm = len({it["id"] for it in keep_items if it["gap1_overlap_norm"]})
    gap1_keep_src = len({it["id"] for it in keep_items if it["gap1_overlap_source"]})

    # 32B ok 8B wrong samples
    pair_samples = {}
    rng = random.Random(42)
    for block in distill_pairs:
        a = index_by_id(f"32B_{block['cond']}")
        ids = list(block["ids"])
        rng.shuffle(ids)
        pair_samples[block["cond"]] = [
            {"id": i, "reason": a[i]["reason"], "articles": a[i]["articles"], "clause_head150": (a[i]["clause"] or "")[:150]}
            for i in ids[:10]
        ]

    # write DISTILL_AUDIT.md
    def fmt_pct(x):
        if x is None:
            return "—"
        return f"{x:.4f}"

    def fmt_stats(d):
        if not d or d.get("n") == 0:
            return "n=0"
        return (
            f"n={d['n']} mean={d['mean']} median={d['median']} "
            f"p10={d['p10']} p90={d['p90']} min={d['min']} max={d['max']}"
        )

    lines = []
    lines.append("# DISTILL_AUDIT — 32B reason 점검 (숫자·원문만)")
    lines.append("")
    lines.append("## 메타")
    lines.append(f"- 토크나이저: `{META['tokenizer_path']}` ({META.get('tokenizer_backend')})")
    lines.append(f"- 형태소 분석기: {META['morph_analyzer']}")
    lines.append(f"- 내용 어절 방식: {META['content_token_method']}")
    lines.append(f"- 문장 수 규칙: {META['sentence_rule']}")
    lines.append(f"- 임베딩: 미사용 (유사 중복은 문자 3-gram Jaccard)")
    lines.append(f"- 건너뛴 항목: {SKIPPED if SKIPPED else '없음'}")
    lines.append(f"- 파일 건수: {json.dumps(file_counts, ensure_ascii=False)}")
    lines.append(f"- parse 실패 제외: {json.dumps(parse_fail_counts, ensure_ascii=False)}")
    lines.append(f"- reason 빈값 제외: {json.dumps(empty_reason_counts, ensure_ascii=False)}")
    lines.append(f"- 소요초: {round(time.time()-t0,1)}")
    lines.append("")
    lines.append("## 요약표")
    lines.append("")
    lines.append("| 출처 | 그룹 | n | 평균 글자 | 중앙 글자 | 40자 미만 | 완전 중복 | 유사군집 소속 | 조항 인용률 | 일반형 | 자료 밖 법령 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in summary_rows:
        lines.append(
            f"| {r['src']} | {r['group']} | {r['n']} | {r['mean_char']} | {r['median_char']} | "
            f"{fmt_pct(r['lt40'])} | {fmt_pct(r['exact_dup'])} | {fmt_pct(r['sim_ratio'])} | "
            f"{r['clause_cite_mean']} | {fmt_pct(r['generic'])} | {fmt_pct(r['ext_law'])} |"
        )
    lines.append("")

    for block in report_groups:
        lines.append(f"## {block['src']} / {block['group']} (n={block['n']})")
        lines.append("")
        if block["n"] == 0:
            lines.append("(항목 없음)")
            lines.append("")
            continue
        lr = block["length"]
        lines.append("### 1. 길이")
        lines.append(f"- 글자: {fmt_stats(lr['char'])}")
        lines.append(f"- 문장: {fmt_stats(lr['sent'])}")
        lines.append(f"- 토큰: {fmt_stats(lr['tok'])}")
        lines.append(f"- 40자 미만 비율: {fmt_pct(lr['lt40'])}")
        lines.append(f"- 80자 미만 비율: {fmt_pct(lr['lt80'])}")
        lines.append(f"- 출력 토큰 ≥250: {lr['tok_ge250']}")
        lines.append("- 글자 히스토그램(10자 구간, bin시작=건수):")
        lines.append("")
        lines.append("| bin시작 | 건수 |")
        lines.append("|---|---|")
        for b, c in lr["hist_10"]:
            lines.append(f"| {b} | {c} |")
        lines.append("")

        ed = block["exact_dup"]
        lines.append("### 2. 반복")
        lines.append(f"- 완전 중복 문장 수(정규화 후 2회+): {ed['n_dup_texts']}")
        lines.append(f"- 완전 중복 항목 비율: {fmt_pct(ed['item_ratio'])}")
        lines.append("- 상위 10개 원문·빈도:")
        for i, t in enumerate(ed["top10"], 1):
            lines.append(f"  {i}. freq={t['freq']} | {t['reason']}")
        ci = block["sim"]
        lines.append(f"- 유사 군집(≥2, Jaccard≥0.7) 수: {ci.get('n_clusters_multi')}")
        lines.append(f"- 2개+ 군집 소속 항목 비율: {fmt_pct(ci.get('ratio_in_multi'))}")
        lines.append("- 가장 큰 군집 5개:")
        for i, c in enumerate(ci.get("top5") or [], 1):
            lines.append(f"  - #{i} size={c['size']}")
            for e in c["examples"]:
                lines.append(f"    - {e}")
        lines.append("- 어절 3-gram 상위 30:")
        lines.append("")
        lines.append("| 3-gram | count | reason_ratio |")
        lines.append("|---|---|---|")
        for t in block["trigrams"]:
            lines.append(f"| {t['trigram']} | {t['count']} | {t['reason_ratio']} |")
        lines.append("")
        se = block["start_end"]
        lines.append("- 첫 8글자 상위 15:")
        for s, c in se.get("start_top15") or []:
            lines.append(f"  - `{s}` × {c}")
        lines.append("- 끝 8글자 상위 15:")
        for s, c in se.get("end_top15") or []:
            lines.append(f"  - `{s}` × {c}")
        vd = block["vocab"]
        lines.append(f"- 어휘 다양성(고유어절/전체어절) full n={vd.get('n_full')}: {vd.get('full')}")
        lines.append(f"- 어휘 다양성 subsample299 n={vd.get('n_sub')} seed=42: {vd.get('sub299')}")
        lines.append("")

        sp = block["spec"]
        lines.append("### 3. 구체성")
        lines.append(f"- 조항 인용률: {fmt_stats(sp['clause_cite'])}")
        lines.append(f"- 조항 인용률=0 비율: {fmt_pct(sp['clause_cite_zero_ratio'])}")
        lines.append(f"- 조문 반복률: {fmt_stats(sp['law_repeat'])}")
        lines.append(f"- 일반형(0.15/0.5): {fmt_pct(sp['generic_015_05'])}")
        lines.append(f"- 일반형(0.10/0.4): {fmt_pct(sp['generic_010_04'])}")
        lines.append(f"- 일반형(0.20/0.6): {fmt_pct(sp['generic_020_06'])}")
        if block["group"] == "정답":
            sm = block["samples"]
            for title, key in [("일반형 10건", "generic10"), ("조항인용률 상위 10", "top_cite10"), ("무작위 10", "random10")]:
                lines.append(f"#### 샘플 — {title}")
                for j, s in enumerate(sm.get(key) or [], 1):
                    lines.append(f"**{j}. {s['id']}** articles={s['articles']} cite={s['clause_cite']} law={s['law_repeat']}")
                    lines.append(f"- clause[:150]: {s['clause_head150']}")
                    lines.append(f"- reason: {s['reason']}")
                    lines.append("")
        lines.append("")

        cs = block["cons"]
        lines.append("### 4. 일관성·환각")
        lines.append(f"- reason 제N조 ∉ articles 비율: {fmt_pct(cs.get('halluc_art_ratio'))}")
        lines.append(f"- articles[0] 미언급 비율: {fmt_pct(cs.get('miss_top1_mention_ratio'))}")
        lines.append(f"- 자료 밖 법령 비율: {fmt_pct(cs.get('ext_law_ratio'))}")
        lines.append(f"- 자료 밖 법령 목록: {cs.get('ext_law_list')}")
        lines.append(f"- 프롬프트 용어 노출 비율: {fmt_pct(cs.get('prompt_ratio'))}")
        if cs.get("c4_ood_ratio") is not None:
            lines.append(f"- C4 후보 외 조항 언급 비율: {fmt_pct(cs.get('c4_ood_ratio'))}")
        lines.append(f"- 단정완화(보인다/추정/가능성/수 있다) 비율: {fmt_pct(cs.get('soft_ratio'))}")
        lines.append("")

    lines.append("## 5. 정답/오답 비교표 (주요 지표)")
    lines.append("")
    lines.append("| 출처 | 지표 | 정답 | 오답 |")
    lines.append("|---|---|---|---|")
    for src_key, _, _, _ in sources_spec:
        b_ok = next(b for b in report_groups if b["src"] == src_key and b["group"] == "정답")
        b_ng = next(b for b in report_groups if b["src"] == src_key and b["group"] == "오답")
        def cell(b, path):
            if b["n"] == 0:
                return "—"
            if path == "mean_char":
                return b["length"]["char"]["mean"]
            if path == "exact_dup":
                return fmt_pct(b["exact_dup"]["item_ratio"])
            if path == "cite":
                return b["spec"]["clause_cite"]["mean"]
            if path == "generic":
                return fmt_pct(b["spec"]["generic_015_05"])
            if path == "ext":
                return fmt_pct(b["cons"]["ext_law_ratio"])
            return "?"
        for label, p in [
            ("평균 글자", "mean_char"),
            ("완전 중복 비율", "exact_dup"),
            ("조항 인용률", "cite"),
            ("일반형 비율", "generic"),
            ("자료 밖 법령 비율", "ext"),
        ]:
            lines.append(f"| {src_key} | {label} | {cell(b_ok,p)} | {cell(b_ng,p)} |")
    lines.append("")
    lines.append("### 32B 정답 ∧ 8B 오답 (같은 id)")
    for block in distill_pairs:
        lines.append(f"- {block['cond']}: n={block['n']}")
    lines.append("")
    for cond, samples_ in pair_samples.items():
        lines.append(f"#### {cond} 32B reason 무작위 10")
        for j, s in enumerate(samples_, 1):
            lines.append(f"**{j}. {s['id']}** articles={s['articles']}")
            lines.append(f"- clause[:150]: {s['clause_head150']}")
            lines.append(f"- reason: {s['reason']}")
            lines.append("")

    lines.append("## 6. 학습 후보 수 (32B)")
    lines.append("")
    lines.append("| 조건 | 32B_C2 | 32B_C4 | 32B_C5 |")
    lines.append("|---|---|---|---|")
    keys = ["정답", "정답∧완전중복아님", "정답∧일반형아님", "정답∧자료밖법령없음∧프롬프트없음", "위모두"]
    for k in keys:
        lines.append(
            f"| {k} | {learn_tables['32B_C2'][k]} | {learn_tables['32B_C4'][k]} | {learn_tables['32B_C5'][k]} |"
        )
    lines.append("")
    lines.append(f"- 출처 간 id 겹침(위모두 기준): {json.dumps(overlap_counts, ensure_ascii=False)}")
    lines.append(f"- GAP-1 E2 200건과 정규화 clause 겹침 (32B 정답 unique id): {gap1_n_norm}")
    lines.append(f"- GAP-1 E2 200건과 source 경로 겹침 (32B 정답 unique id): {gap1_n_src}")
    lines.append(f"- 위모두 unique 중 GAP-1 정규화 겹침: {gap1_keep_norm}")
    lines.append(f"- 위모두 unique 중 GAP-1 source 겹침: {gap1_keep_src}")
    lines.append("")
    lines.append("---")
    lines.append(f"생성: `distill_audit/audit.py` → `items.csv`, `DISTILL_AUDIT.md`")

    (AUDIT / "DISTILL_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    (AUDIT / "meta.json").write_text(
        json.dumps(
            {
                "meta": META,
                "file_counts": file_counts,
                "parse_fail_counts": parse_fail_counts,
                "empty_reason_counts": empty_reason_counts,
                "learn_tables": learn_tables,
                "overlap_counts": overlap_counts,
                "distill_pairs": [{"cond": b["cond"], "n": b["n"]} for b in distill_pairs],
                "skipped": SKIPPED,
                "elapsed_sec": round(time.time() - t0, 1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("DONE", round(time.time() - t0, 1), "sec", "items", len(all_items))
    print("wrote", csv_path)
    print("wrote", AUDIT / "DISTILL_AUDIT.md")


if __name__ == "__main__":
    main()
