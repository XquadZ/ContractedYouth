# -*- coding: utf-8 -*-
"""LEGAL_LEVEL C: review_sheet.csv 사람 채점 집계. 빈 시트도 동작한다."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = APP / "out" / "legal_level" / "review_sheet.csv"
COLS = ("판정_맞음", "이유_맞음", "근거_맞음", "수정문구_문제해소")
OK = {"Y", "y", "예", "O", "o", "1", "true", "True"}
NO = {"N", "n", "아니오", "X", "x", "0", "false", "False"}
AMB = {"애매", "?", "△", "partial", "PARTIAL"}


def norm(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return "빈칸"
    if s in OK:
        return "Y"
    if s in NO:
        return "N"
    if s in AMB:
        return "애매"
    return s


def tally(path: Path) -> dict:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    out = {
        "path": str(path),
        "n_rows": len(rows),
        "filled_rows": 0,
        "columns": {},
    }
    for col in COLS:
        ctr = Counter(norm(r.get(col) or "") for r in rows)
        answered = sum(v for k, v in ctr.items() if k != "빈칸")
        y = ctr.get("Y", 0)
        out["columns"][col] = {
            "counts": dict(ctr),
            "answered": answered,
            "y_rate": None if answered == 0 else round(100.0 * y / answered, 1),
            "y_over_answered": f"{y}/{answered}" if answered else "0/0",
            "note": "표본 적음" if 0 < answered < 5 else ("미채점" if answered == 0 else ""),
        }
    out["filled_rows"] = sum(
        1 for r in rows if any(norm(r.get(c) or "") != "빈칸" for c in COLS)
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if not args.sheet.exists():
        raise SystemExit(f"missing sheet: {args.sheet}")
    result = tally(args.sheet)
    out = args.out or (args.sheet.parent / "tally_result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
