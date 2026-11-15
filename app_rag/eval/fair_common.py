# -*- coding: utf-8 -*-
"""FAIR_RERUN 공통 경로·해시·재사용 판정."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rag.paths import APP, OUT

QFAIR = OUT / "quant_fair"
QNEU = OUT / "quant_neutral"
DOMAINS = ("LAB", "LEASE", "LOAN")
COST_CAP_USD = 1.0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict:
    files: list[Path] = sorted((APP / "rag").glob("*.py"))
    files.append(APP / "eval" / "quant_run.py")
    for name in (
        "criteria/LAB_cards.yaml",
        "criteria/LEASE_cards.yaml",
        "criteria/LOAN_cards.yaml",
        "criteria/neutral/LAB_cards.yaml",
        "criteria/neutral/LEASE_cards.yaml",
        "criteria/neutral/LOAN_cards.yaml",
        "prompts/judge.txt",
        "prompts/judge_neutral.txt",
    ):
        files.append(APP / name)
    out = {}
    for path in files:
        if path.exists():
            out[str(path.relative_to(APP))] = sha256_file(path)
    return out


def load_hash(when: str) -> dict:
    return json.loads((QFAIR / f"prompt_hash_{when}.json").read_text(encoding="utf-8"))


def neutral_prompt_hashes_equal() -> tuple[bool, int]:
    before = load_hash("before")
    after = load_hash("after")
    bmap = {(r["doc_id"], r["segment_id"]): r["neutral_sha256"] for r in before["items"]}
    amap = {(r["doc_id"], r["segment_id"]): r["neutral_sha256"] for r in after["items"]}
    same = sum(1 for k, v in bmap.items() if amap.get(k) == v)
    return same == len(bmap) == len(amap) == 799, same


def label_set(payload: dict) -> set[tuple]:
    return {(r["domain"], r["doc_id"], r["segment_id"], r["label"]) for r in payload["items"]}
