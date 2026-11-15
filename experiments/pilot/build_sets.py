# -*- coding: utf-8 -*-
"""1단계: 평가셋 고정 + LawQA 학습풀 구축 + 파일럿 샘플링."""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from datasets import load_from_disk

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PILOT = ROOT / "pilot"
SEED = 42

OUT_DOMAIN_WORDS = [
    "고소", "형법", "처벌", "징역", "벌금", "배임", "횡령", "절도", "장물", "공갈", "사기죄",
    "상고", "항소", "공시송달", "재심", "경매", "배당", "공탁", "가압류", "압류", "추심",
    "개인회생", "파산", "산업재해", "산재", "유족급여", "부가가치세", "소득세", "행정심판", "취소소송",
]

DOMAIN_KEYWORDS = {
    "고용": [
        "아르바이트", "알바", "근로계약", "임금", "월급", "시급", "주휴", "최저임금",
        "퇴직금", "해고", "퇴사", "사직", "연차", "수습", "근로자",
    ],
    "계약": [
        "임대차", "임대인", "임차인", "집주인", "세입자", "전세", "월세",
        "보증금", "원룸", "자취", "계약갱신", "원상복구",
    ],
    "채권채무": [
        "빌려", "빌린", "대여금", "차용", "갚", "변제", "지급명령", "차용증",
    ],
}
DOMAIN_PRIORITY = ["고용", "계약", "채권채무"]

OLD_LAW_PATTERNS = [
    re.compile(r"구\s?[「」『』\w]*법"),
    re.compile(r"개정되기 전의 것"),
    re.compile(r"개정 전"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_question(q: str) -> str:
    s = q.lower()
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s


def char_ngrams(text: str, n: int = 3) -> set[str]:
    t = re.sub(r"\s+", "", text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def assign_domain(question: str) -> str | None:
    for domain in DOMAIN_PRIORITY:
        for kw in DOMAIN_KEYWORDS[domain]:
            if kw in question:
                return domain
    return None


def has_out_domain(text: str) -> bool:
    return any(w in text for w in OUT_DOMAIN_WORDS)


def has_old_law(answer: str) -> bool:
    return any(p.search(answer) for p in OLD_LAW_PATTERNS)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    PILOT.mkdir(parents=True, exist_ok=True)

    # ----- load inputs -----
    audit_df = pd.read_csv(ROOT / "AUDIT_RESULTS.csv", encoding="utf-8-sig")
    samples: dict[str, dict] = {}
    with (ROOT / "AUDIT_SAMPLES.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            samples[rec["audit_id"]] = rec

    ds = load_from_disk(str(ROOT / "datasets" / "LawQA-Ko"))
    train = ds["train"]
    log(f"LawQA train rows: {len(train)}")

    # ----- 1-1 eval set -----
    # 관련성 ∈ {R, N} and 문제코드 empty
    def is_empty_code(v) -> bool:
        if pd.isna(v):
            return True
        return str(v).strip() == ""

    eval_mask = audit_df["관련성"].isin(["R", "N"]) & audit_df["문제코드"].apply(is_empty_code)
    eval_rows_df = audit_df.loc[eval_mask]

    eval_lawqa: list[dict] = []
    eval_aihub: list[dict] = []
    missing_sample = 0
    for _, row in eval_rows_df.iterrows():
        aid = row["audit_id"]
        sample = samples.get(aid)
        if sample is None:
            missing_sample += 1
            continue
        out = {
            "audit_id": aid,
            "domain": row["domain"],
            "관련성": row["관련성"],
            "question": sample["question"],
            "answer": sample["answer"],
            "origin_ref": sample.get("origin_ref"),
        }
        if row["source"] == "lawqa":
            eval_lawqa.append(out)
        elif row["source"] == "aihub":
            eval_aihub.append(out)

    write_jsonl(PILOT / "eval_lawqa.jsonl", eval_lawqa)
    write_jsonl(PILOT / "eval_aihub_ood.jsonl", eval_aihub)
    log(f"[1-1] eval_lawqa: {len(eval_lawqa)} (expected 54)")
    log(f"[1-1] eval_aihub_ood: {len(eval_aihub)} (expected 35)")
    log(f"[1-1] missing_sample_ids: {missing_sample}")

    # ----- 1-2 exclude list -----
    exclude_refs: set[int] = set()
    for rec in samples.values():
        if rec.get("source") == "lawqa":
            exclude_refs.add(int(rec["origin_ref"]))
    log(f"[1-2] exclude origin_ref count: {len(exclude_refs)}")

    # ----- 1-3 train pool filter -----
    counts: list[tuple[str, int]] = []
    # start with all indices
    candidates: list[int] = list(range(len(train)))
    counts.append(("start", len(candidates)))

    # a) answer missing
    candidates = [
        i for i in candidates
        if train[i]["answer"] is not None and str(train[i]["answer"]).strip() != ""
    ]
    counts.append(("a_answer_not_null", len(candidates)))

    # b) exclude audited lawqa 100
    candidates = [i for i in candidates if i not in exclude_refs]
    counts.append(("b_exclude_audit_lawqa", len(candidates)))

    # c) exact duplicate on normalized question
    seen_norm: set[str] = set()
    deduped: list[int] = []
    for i in candidates:
        nq = normalize_question(train[i]["question"] or "")
        if nq in seen_norm:
            continue
        seen_norm.add(nq)
        deduped.append(i)
    candidates = deduped
    counts.append(("c_exact_dedup", len(candidates)))

    # d) near-dup vs eval_lawqa (3-gram Jaccard >= 0.6)
    eval_grams = [
        (e["question"], char_ngrams(e["question"])) for e in eval_lawqa
    ]
    kept: list[int] = []
    removed_pairs: list[tuple[float, str, str, int]] = []
    for i in candidates:
        q = train[i]["question"] or ""
        g = char_ngrams(q)
        max_sim = 0.0
        max_eq = ""
        for eq, eg in eval_grams:
            sim = jaccard(g, eg)
            if sim > max_sim:
                max_sim = sim
                max_eq = eq
        if max_sim >= 0.6:
            removed_pairs.append((max_sim, q, max_eq, i))
        else:
            kept.append(i)
    candidates = kept
    counts.append(("d_near_dedup_vs_eval", len(candidates)))
    removed_pairs.sort(key=lambda x: -x[0])
    top10 = removed_pairs[:10]

    # e) answer length < 150
    candidates = [i for i in candidates if len(str(train[i]["answer"])) >= 150]
    counts.append(("e_answer_len_ge_150", len(candidates)))

    # f) old law signals
    candidates = [i for i in candidates if not has_old_law(str(train[i]["answer"]))]
    counts.append(("f_no_old_law", len(candidates)))

    # g) out-of-domain words
    candidates = [
        i for i in candidates
        if not has_out_domain(str(train[i]["question"]) + str(train[i]["answer"]))
    ]
    counts.append(("g_no_out_domain_words", len(candidates)))

    # h) domain assign
    pool: list[dict] = []
    unassigned = 0
    for i in candidates:
        q = train[i]["question"]
        a = train[i]["answer"]
        domain = assign_domain(q)
        if domain is None:
            unassigned += 1
            continue
        pool.append({
            "row_idx": i,
            "domain": domain,
            "question": q,
            "answer": a,
        })
    counts.append(("h_domain_assigned", len(pool)))
    log(f"[1-3] unassigned (dropped): {unassigned}")

    write_jsonl(PILOT / "train_pool_lawqa.jsonl", pool)

    domain_counts = Counter(r["domain"] for r in pool)
    log("[1-3] filter stage counts:")
    for name, cnt in counts:
        log(f"  {name}: {cnt}")
    log(f"[1-3] domain counts: {dict(domain_counts)}")

    # domain examples (3 random each)
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in pool:
        by_domain[r["domain"]].append(r)
    examples: dict[str, list[dict]] = {}
    for d in DOMAIN_PRIORITY:
        items = by_domain.get(d, [])
        sample_n = min(3, len(items))
        examples[d] = random.sample(items, sample_n) if sample_n else []

    # ----- 1-4 pilot set -----
    pilot_set: list[dict] = []
    pilot_notes: list[str] = []
    for d in DOMAIN_PRIORITY:
        items = by_domain.get(d, [])
        if len(items) <= 150:
            chosen = list(items)
            pilot_notes.append(f"{d}: pool={len(items)} < 150 → took all {len(chosen)}")
        else:
            chosen = random.sample(items, 150)
            pilot_notes.append(f"{d}: pool={len(items)} → sampled 150")
        pilot_set.extend(chosen)

    write_jsonl(PILOT / "pilot_set.jsonl", pilot_set)
    log(f"[1-4] pilot_set total: {len(pilot_set)}")
    for note in pilot_notes:
        log(f"  {note}")

    # overlap check
    pilot_idxs = {r["row_idx"] for r in pilot_set}
    eval_refs = {int(e["origin_ref"]) for e in eval_lawqa if e.get("origin_ref") is not None}
    overlap_exclude = pilot_idxs & exclude_refs
    overlap_eval = pilot_idxs & eval_refs
    log(f"[1-4] pilot ∩ exclude: {len(overlap_exclude)}")
    log(f"[1-4] pilot ∩ eval_lawqa origin_ref: {len(overlap_eval)}")

    # save report sidecar for PILOT_REPORT
    report = {
        "eval_lawqa": len(eval_lawqa),
        "eval_aihub": len(eval_aihub),
        "exclude_refs": len(exclude_refs),
        "stage_counts": counts,
        "unassigned": unassigned,
        "domain_counts": dict(domain_counts),
        "near_dup_removed": len(removed_pairs),
        "near_dup_top10": [
            {
                "sim": round(sim, 4),
                "candidate_row_idx": idx,
                "candidate_question": cq,
                "eval_question": eq,
            }
            for sim, cq, eq, idx in top10
        ],
        "examples": {
            d: [
                {"row_idx": x["row_idx"], "question": x["question"], "answer": x["answer"]}
                for x in examples[d]
            ]
            for d in DOMAIN_PRIORITY
        },
        "pilot_total": len(pilot_set),
        "pilot_notes": pilot_notes,
        "pilot_domain_counts": dict(Counter(r["domain"] for r in pilot_set)),
        "overlap_exclude": len(overlap_exclude),
        "overlap_eval": len(overlap_eval),
    }
    with (PILOT / "build_sets_stats.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"wrote {PILOT / 'build_sets_stats.json'}")


if __name__ == "__main__":
    main()
