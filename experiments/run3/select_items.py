# -*- coding: utf-8 -*-
"""3-1. 학습 문항 선정."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import PILOT, ROOT, RUN3, SEED, load_jsonl, log, write_jsonl

DEBT_EXCLUDE = [
    "가등기", "근저당", "저당권", "양도담보", "소유권이전등기", "말소등기",
    "회복등기", "표현대리", "대물변제", "어음", "수표", "가처분",
]
DOMAINS = ["고용", "계약", "채권채무"]
MAX_PER_DOMAIN = 300


def debt_hit(text: str) -> bool:
    return any(w in text for w in DEBT_EXCLUDE)


def load_forbidden_refs() -> set[int]:
    forbidden: set[int] = set()
    with (ROOT / "AUDIT_SAMPLES.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("source") == "lawqa" and r.get("origin_ref") is not None:
                forbidden.add(int(r["origin_ref"]))
    for r in load_jsonl(PILOT / "eval_lawqa.jsonl"):
        if r.get("origin_ref") is not None:
            forbidden.add(int(r["origin_ref"]))
    return forbidden


def interleave(by_domain: dict[str, list[dict]]) -> list[dict]:
    queues = {d: list(by_domain.get(d, [])) for d in DOMAINS}
    out: list[dict] = []
    while any(queues[d] for d in DOMAINS):
        for d in DOMAINS:
            if queues[d]:
                out.append(queues[d].pop(0))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RUN3 / "items.jsonl")
    ap.add_argument("--max-per-domain", type=int, default=MAX_PER_DOMAIN)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    random.seed(args.seed)
    RUN3.mkdir(parents=True, exist_ok=True)

    pool = load_jsonl(PILOT / "train_pool_lawqa.jsonl")
    log(f"train_pool: {len(pool)}")

    before = Counter(r["domain"] for r in pool)
    filtered: dict[str, list[dict]] = defaultdict(list)
    dropped_debt = 0
    for r in pool:
        d = r["domain"]
        if d == "채권채무" and debt_hit(str(r["question"]) + str(r["answer"])):
            dropped_debt += 1
            continue
        filtered[d].append(r)
    after = {d: len(filtered[d]) for d in DOMAINS}
    log(f"채권채무 extra-filter dropped: {dropped_debt}")
    log(f"domain before: {dict(before)}")
    log(f"domain after filter: {after}")

    chosen: dict[str, list[dict]] = {}
    for d in DOMAINS:
        items = list(filtered[d])
        random.shuffle(items)
        take = items[: args.max_per_domain]
        chosen[d] = take
        log(f"{d}: sampled {len(take)} / pool_after={len(items)}")

    ordered = interleave(chosen)
    out_rows = []
    for i, r in enumerate(ordered, 1):
        out_rows.append({
            "id": f"R{i:04d}",
            "row_idx": int(r["row_idx"]),
            "domain": r["domain"],
            "question": r["question"],
            "answer": r["answer"],
        })
    write_jsonl(args.out, out_rows)
    log(f"wrote {args.out} n={len(out_rows)}")

    forbidden = load_forbidden_refs()
    overlap = {r["row_idx"] for r in out_rows} & forbidden
    log(f"forbidden refs: {len(forbidden)}")
    log(f"items ∩ (audit_lawqa ∪ eval_lawqa) origin_ref: {len(overlap)}")
    if overlap:
        log(f"OVERLAP examples: {sorted(list(overlap))[:10]}")
        return 1

    final_dom = Counter(r["domain"] for r in out_rows)
    log(f"final domain counts: {dict(final_dom)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
