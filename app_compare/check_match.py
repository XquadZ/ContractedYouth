# -*- coding: utf-8 -*-
"""T3 402문장을 /api/analyze 로 한 조항씩 보내 재생 일치율을 계산한다.

oracle_slot=1 은 gold check 조문(A1)을 넣는다.
include_articles=false 는 판정만 비교한다. 조문 선택 호출은 예시 점검에서 한다.
결과에는 조항 원문을 쓰지 않는다.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
T3 = WORK / "exp_v2" / "data" / "t3_clauses.jsonl"
LEFT = WORK / "exp_v2" / "runs" / "Q8B_T3_A4-BM25.jsonl"
RIGHT = WORK / "exp_v2" / "runs" / "AX7_T3_A1.jsonl"
OUT = APP / "logs"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def post(clause: str, oracle: bool) -> dict:
    body = json.dumps(
        {"text": clause, "oracle_slot": oracle, "include_articles": False},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8090/api/analyze",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=900) as response:
        raw = response.read().decode("utf-8")
    left = right = None
    for block in raw.split("\n\n"):
        if "event: clause" not in block:
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                left = payload["left"]["risky"]
                right = payload["right"]["risky"]
    return {"left": left, "right": right}


def run(mode: str, oracle: bool) -> dict:
    items = load(T3)
    gold_left = {}
    for row in load(LEFT):
        gold_left[row["id"]] = as_bool((row.get("parsed") or {}).get("risky")) if row.get("parse_ok") else None
    gold_right = {}
    for row in load(RIGHT):
        gold_right[row["id"]] = as_bool((row.get("parsed") or {}).get("risky")) if row.get("parse_ok") else None
    dest = OUT / f"match_{mode}.jsonl"
    done = {}
    if dest.exists():
        for row in load(dest):
            done[row["id"]] = row
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with dest.open("a", encoding="utf-8", newline="\n") as handle:
        for item in items:
            if item["id"] in done:
                continue
            if item["kind"] != "text" and mode == "oracle_text":
                continue
            got = post(item["clause"], oracle)
            row = {
                "id": item["id"],
                "kind": item["kind"],
                "left_match": got["left"] == gold_left.get(item["id"]),
                "right_match": got["right"] == gold_right.get(item["id"]),
                "left": got["left"],
                "right": got["right"],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            done[item["id"]] = row
            print(item["id"], int(row["left_match"]), int(row["right_match"]), flush=True)
    rows = list(done.values())
    text = [r for r in rows if r["kind"] == "text"]

    def rate(group, key):
        return (sum(1 for r in group if r[key]) / len(group)) if group else None

    return {
        "mode": mode,
        "n": len(rows),
        "left_all": rate(rows, "left_match"),
        "right_text": rate(text, "right_match"),
        "seconds": round(time.perf_counter() - t0, 1),
    }


if __name__ == "__main__":
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "oracle"
    oracle = which != "slot"
    summary = run(which, oracle)
    path = OUT / f"match_{which}_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    print("SUMMARY", json.dumps(summary), flush=True)
