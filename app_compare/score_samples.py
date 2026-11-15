# -*- coding: utf-8 -*-
"""예시 3개를 /api/analyze 로 점검하고 맞힘/놓침/오탐을 센다."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent


def analyze(text: str) -> dict:
    body = json.dumps({"text": text, "include_articles": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8090/api/analyze",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=1800) as response:
        raw = response.read().decode("utf-8")
    clauses = []
    done = {}
    for block in raw.split("\n\n"):
        event = ""
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if event == "clause" and data:
            clauses.append(data)
        if event == "done" and data:
            done = data
    return {"clauses": clauses, "done": done}


def score(clauses: list[dict], risky: list[str]) -> dict:
    out = {}
    for side in ("left", "right"):
        hit = miss = fp = 0
        for sentence in risky:
            cards = [c[side] for c in clauses if sentence in (c[side].get("clause") or "")]
            if any(c.get("verdict") == "risk" for c in cards):
                hit += 1
            else:
                miss += 1
        for card in clauses:
            text = card[side].get("clause") or ""
            if card[side].get("verdict") == "risk" and not any(s in text for s in risky):
                fp += 1
        out[side] = {"hit": hit, "miss": miss, "fp": fp, "n_risk_gold": len(risky)}
    return out


def main() -> None:
    answers = json.loads((APP / "samples" / "answers.json").read_text(encoding="utf-8"))
    report = {}
    for name in ("alba_cafe", "oneroom_lease", "clean_alba"):
        text = (APP / "samples" / f"{name}.txt").read_text(encoding="utf-8")
        got = analyze(text)
        risky = answers[name]["risky_clauses"]
        report[name] = {
            "score": score(got["clauses"], risky),
            "done": got["done"],
            "n": len(got["clauses"]),
        }
        if name == "alba_cafe":
            (APP / "static" / "demo_alba.json").write_text(
                json.dumps(got["clauses"], ensure_ascii=False),
                encoding="utf-8",
            )
        print(name, report[name]["score"], "n", report[name]["n"], "ms", got["done"].get("left_ms"), got["done"].get("right_ms"), flush=True)
    (APP / "logs" / "sample_scores.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
