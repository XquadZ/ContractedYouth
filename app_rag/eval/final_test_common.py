# -*- coding: utf-8 -*-
"""FINAL_TEST 공통 경로·고정 설정·해시."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rag.paths import APP, OUT

QTEST = OUT / "quant_test"
QDEV = QTEST / "dev"
QFAIR = OUT / "quant_fair"
DOMAINS = ("LAB", "LEASE", "LOAN")
VERSIONS = ("none", "neutral", "tuned")
MODELS = ("luna", "EXAONE", "AX")
COST_CAP_USD = 1.5
FIXED = {
    "axok": False,
    "num2way": True,
    "ne_risky_only": True,
    "num_year_doc": True,
    "clean_v2": True,
    "R": "R0",
    "K": 2,
}
LUNA_PRICE = {
    "model_id": "gpt-6-luna",
    "in": 0.10,
    "out": 0.50,
    "batch_in": 0.05,
    "batch_out": 0.25,
}
LUNA_EXTRA = {
    "max_completion_tokens": 512,
    "reasoning_effort": "none",
    "temperature": 0,
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict:
    out = {}
    for path in sorted((APP / "rag").glob("*.py")):
        out[str(path.relative_to(APP))] = sha256_file(path)
    for path in sorted((APP / "eval").glob("*.py")):
        out[str(path.relative_to(APP))] = sha256_file(path)
    for name in (
        "criteria/LAB_cards.yaml",
        "criteria/LEASE_cards.yaml",
        "criteria/LOAN_cards.yaml",
        "criteria/neutral/LAB_cards.yaml",
        "criteria/neutral/LEASE_cards.yaml",
        "criteria/neutral/LOAN_cards.yaml",
        "prompts/judge.txt",
        "prompts/judge_neutral.txt",
        "config/min_wage.yaml",
    ):
        path = APP / name
        if path.exists():
            out[name] = sha256_file(path)
    return out


def best_cell_to_settings(cell: dict | None) -> dict | None:
    if not cell:
        return None
    return {
        "axok": bool(cell.get("axok")),
        "num2way": bool(cell.get("num2way")),
        "ne_risky_only": bool(cell.get("ne_risky_only")),
        "num_year_doc": bool(cell.get("num_year_doc")),
        "clean_v2": bool(cell.get("clean_v2")),
        "R": cell.get("R") or "R0",
        "K": int(cell.get("K") or 2),
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
