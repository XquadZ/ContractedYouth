# -*- coding: utf-8 -*-
"""조원 pretty JSON(객체 이어붙임) → JSONL. 원본은 수정하지 않는다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DEFAULT_NAMES = (
    "labor_contract_synthetic_pairs_pretty.json",
    "labor_contract_synthetic_pairs.json",
)
SEARCH = [
    APP / "eval",
    APP.parent / "_incoming",
    APP.parent / "data_contract",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]


def find_pretty() -> Path | None:
    for folder in SEARCH:
        if not folder.exists():
            continue
        for name in DEFAULT_NAMES:
            path = folder / name
            if path.exists():
                return path
        for path in folder.glob("*synthetic*pairs*.json"):
            return path
    return None


def raw_decode_all(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    idx = 0
    n = len(text)
    rows = []
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, dict):
            rows.append(obj)
        elif isinstance(obj, list):
            rows.extend([x for x in obj if isinstance(x, dict)])
        idx = end
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=APP / "eval" / "pairs.jsonl")
    args = parser.parse_args()
    src = args.src or find_pretty()
    if src is None:
        print("MISSING labor_contract_synthetic_pairs_pretty.json")
        print("searched", [str(p) for p in SEARCH])
        raise SystemExit(2)
    text = src.read_text(encoding="utf-8")
    rows = raw_decode_all(text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("SRC", src)
    print("WROTE", args.out)
    print("n", len(rows))


if __name__ == "__main__":
    main()
