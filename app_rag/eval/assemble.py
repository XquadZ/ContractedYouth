# -*- coding: utf-8 -*-
"""짝 데이터에서 계약서를 만든다. 독소 비율 깨끗한/1~2/3~5 = 1:1:1, seed 42."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SEED = 42
META_HEAD = """단시간 근로계약서

사업주 김사용(이하 "사업주")과 근로자 이알바(이하 "근로자")은 다음과 같이 근로계약을 체결한다.
"""
META_TAIL = """
2026년 3월 1일
사업주 김사용 (서명)
근로자 이알바 (서명)
"""


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def pair_rows(rows: list[dict]) -> dict:
    buckets = defaultdict(lambda: {"safe": None, "toxic": None, "meta": None})
    for row in rows:
        key = (str(row.get("std_item")), row.get("order"))
        label = str(row.get("label") or "").lower()
        if label in ("toxic", "독소", "risk", "unsafe"):
            buckets[key]["toxic"] = row
        elif label in ("safe", "안전", "ok", "clean"):
            buckets[key]["safe"] = row
        else:
            buckets[key]["meta"] = row
    pairs = []
    for key, sides in buckets.items():
        if sides["safe"] is None and sides["toxic"] is None:
            continue
        pairs.append({"std_item": key[0], "order": key[1], **sides})
    pairs.sort(key=lambda p: (str(p["std_item"]), p["order"] if p["order"] is not None else 0))
    return pairs


def pick_text(pair: dict, toxic: bool) -> tuple[str, dict]:
    row = pair["toxic"] if toxic and pair.get("toxic") else pair.get("safe") or pair.get("toxic")
    return str(row.get("text") or ""), row


def build_docs(pairs: list[dict], n_each: int = 1) -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    n = min(n_each, max(1, len(pairs) // 3 or 1))
    plans = [("clean", 0)] * n + [("few", rng.choice([1, 2])) for _ in range(n)] + [("many", rng.choice([3, 4, 5])) for _ in range(n)]
    docs = []
    gold = []
    for di, (kind, n_tox) in enumerate(plans, start=1):
        n_tox = min(n_tox, len(pairs))
        tox_idx = set(rng.sample(range(len(pairs)), n_tox)) if n_tox else set()
        clauses = []
        answers = []
        for i, pair in enumerate(pairs):
            toxic = i in tox_idx and pair.get("toxic") is not None
            text, src = pick_text(pair, toxic)
            clauses.append(text)
            answers.append(
                {
                    "std_item": pair["std_item"],
                    "order": pair["order"],
                    "toxic": toxic,
                    "label": "toxic" if toxic else "safe",
                    "evidence_hint": src.get("evidence_hint") or src.get("law") or src.get("hint") or "",
                    "text": text,
                }
            )
        body = META_HEAD + "\n".join(f"{i+1}. {c}" for i, c in enumerate(clauses)) + META_TAIL
        doc_id = f"asm-{kind}-{di:02d}"
        docs.append({"id": doc_id, "kind": kind, "n_toxic": n_tox, "text": body})
        gold.append({"id": doc_id, "kind": kind, "n_toxic": n_tox, "answers": answers})
    return docs, gold


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=APP / "eval" / "pairs.jsonl")
    parser.add_argument("--out-docs", type=Path, default=APP / "eval" / "assembled_docs.json")
    parser.add_argument("--out-gold", type=Path, default=APP / "eval" / "assembled_gold.json")
    parser.add_argument("--n-each", type=int, default=1)
    args = parser.parse_args()
    if not args.src.exists():
        print("MISSING", args.src)
        raise SystemExit(2)
    pairs = pair_rows(load_jsonl(args.src))
    docs, gold = build_docs(pairs, n_each=args.n_each)
    args.out_docs.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_gold.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", args.out_docs, "n", len(docs))
    print("WROTE", args.out_gold)
    print("pairs", len(pairs), "kinds", [d["kind"] for d in docs])


if __name__ == "__main__":
    main()
