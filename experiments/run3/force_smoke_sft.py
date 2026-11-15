# -*- coding: utf-8 -*-
"""Smoke-only: build sft_B/C from raw teacher_outputs when validation passes 0."""
from common import RUN3, SYSTEM_SFT, load_jsonl, log, write_jsonl

rows = load_jsonl(RUN3 / "teacher_outputs.jsonl")
out_b, out_c = [], []
for i, r in enumerate(rows):
    split = "train"
    if len(rows) > 1 and i == 0:
        split = "val"
    out_b.append({
        "id": r["id"],
        "domain": r.get("domain"),
        "split": split,
        "messages": [
            {"role": "system", "content": SYSTEM_SFT},
            {"role": "user", "content": r["question"]},
            {"role": "assistant", "content": r["answer"]},
        ],
    })
    out_c.append({
        "id": r["id"],
        "domain": r.get("domain"),
        "split": split,
        "messages": [
            {"role": "system", "content": SYSTEM_SFT},
            {"role": "user", "content": r["question"]},
            {"role": "assistant", "content": r.get("output") or r["answer"]},
        ],
    })
write_jsonl(RUN3 / "sft_B.jsonl", out_b)
write_jsonl(RUN3 / "sft_C.jsonl", out_c)
log(f"forced smoke sft n={len(out_b)}")
