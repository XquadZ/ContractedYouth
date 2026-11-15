# -*- coding: utf-8 -*-
"""짝 데이터 규격 검사. 문제를 목록으로 출력한다."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LEGAL = re.compile(r"(법|무효|금지)")
TOXIC_CUE = re.compile(r"(일체|무조건|포기)")
PLACE = re.compile(r"\{\{[^}]+\}\}")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def validate(rows: list[dict]) -> dict:
    issues = []
    required = ("std_item", "order", "label", "text")
    labels = Counter()
    for i, row in enumerate(rows):
        missing = [k for k in required if k not in row]
        if missing:
            issues.append({"i": i, "id": row.get("id"), "issue": "missing_fields", "fields": missing})
        labels[str(row.get("label"))] += 1
        if str(row.get("label")) in ("toxic", "독소", "risk") and not row.get("code") and not row.get("check_id"):
            issues.append({"i": i, "id": row.get("id"), "issue": "toxic_without_code"})
    by_key = defaultdict(list)
    for i, row in enumerate(rows):
        key = (row.get("std_item"), row.get("order"))
        by_key[key].append(i)
    unpaired = []
    for key, idxs in by_key.items():
        labs = {str(rows[j].get("label")) for j in idxs}
        if len(idxs) < 2:
            unpaired.append({"std_item": key[0], "order": key[1], "n": len(idxs)})
    legal_n = toxic_cue_n = place_n = 0
    for row in rows:
        text = str(row.get("text") or "")
        if LEGAL.search(text):
            legal_n += 1
        if TOXIC_CUE.search(text):
            toxic_cue_n += 1
        if PLACE.search(text):
            place_n += 1
    n = max(len(rows), 1)
    return {
        "n": len(rows),
        "labels": dict(labels),
        "issues": issues,
        "unpaired": unpaired[:50],
        "n_unpaired": len(unpaired),
        "cue_ratio": {
            "법/무효/금지": round(legal_n / n, 4),
            "일체/무조건/포기": round(toxic_cue_n / n, 4),
        },
        "placeholder_ratio": round(place_n / n, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=APP / "eval" / "pairs.jsonl")
    parser.add_argument("--out", type=Path, default=APP / "eval" / "validate.json")
    args = parser.parse_args()
    if not args.src.exists():
        print("MISSING", args.src)
        raise SystemExit(2)
    rows = load_jsonl(args.src)
    report = validate(rows)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", args.out)
    print("n", report["n"], "issues", len(report["issues"]), "unpaired", report["n_unpaired"])
    print("cue", report["cue_ratio"], "placeholder", report["placeholder_ratio"])
    for issue in report["issues"][:20]:
        print("ISSUE", json.dumps(issue, ensure_ascii=False))


if __name__ == "__main__":
    main()
