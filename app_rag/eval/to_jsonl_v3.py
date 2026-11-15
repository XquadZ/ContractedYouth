# -*- coding: utf-8 -*-
"""정답 JSONL을 eval/pairs.jsonl로 모은다. 옛 pretty JSON 경로는 쓰지 않는다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from rag.paths import GOLD  # noqa: E402

DEFAULT_SOURCES = [
    GOLD["LAB"]["contract"],
    GOLD["LEASE"]["contract"],
    GOLD["LOAN"]["contract"],
]


def find_pretty() -> Path | None:
    for path in DEFAULT_SOURCES:
        if path.exists():
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
            rows.extend([x for x in obj if isinstance(obj, dict) or isinstance(x, dict)])
        idx = end
    return rows


def load_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in text.splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
    return raw_decode_all(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=APP / "eval" / "pairs.jsonl")
    args = parser.parse_args()
    sources = [args.src] if args.src else [p for p in DEFAULT_SOURCES if p.exists()]
    if not sources:
        print("MISSING gold jsonl")
        print("searched", [str(p) for p in DEFAULT_SOURCES])
        raise SystemExit(2)
    rows = []
    for src in sources:
        part = load_rows(src)
        rows.extend(part)
        print("SRC", src, "n", len(part))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("WROTE", args.out)
    print("n", len(rows))


if __name__ == "__main__":
    main()
