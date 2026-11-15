# -*- coding: utf-8 -*-
"""01 정답 계약서를 파이프라인에 넣고 탐지율·오탐률·근거·검증 수를 낸다."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.paths import GOLD  # noqa: E402
from rag.pipeline import run  # noqa: E402
sys.path.insert(0, str(APP / "eval"))
from splitutil import load_split_ids  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def docs_from_gold(split: str | None, domain: str | None) -> tuple[list[dict], dict]:
    keep = load_split_ids(split, domain) if split else None
    domains = [domain] if domain else ["LEASE", "LOAN", "LAB"]
    docs = []
    golds = {}
    for name in domains:
        rows = load_jsonl(GOLD[name]["contract"])
        by_doc = defaultdict(list)
        for row in rows:
            by_doc[row["doc_id"]].append(row)
        for did, segs in by_doc.items():
            if keep is not None and did not in keep:
                continue
            segs = sorted(
                segs,
                key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
            )
            text = "\n".join(s.get("text") or "" for s in segs)
            docs.append({"id": did, "kind": name, "text": text})
            golds[did] = {
                "id": did,
                "kind": name,
                "answers": [
                    {
                        "std_item": s.get("std_item"),
                        "order": s.get("order"),
                        "toxic": s.get("label") == "toxic",
                        "label": s.get("label"),
                        "text": s.get("text") or "",
                        "evidence_hint": s.get("evidence_hint") or [],
                    }
                    for s in segs
                ],
            }
    return docs, golds


def _norm(s: str) -> str:
    return "".join((s or "").split())


def overlap(a: str, b: str) -> bool:
    aa, bb = _norm(a), _norm(b)
    if not aa or not bb:
        return False
    return aa in bb or bb in aa or (len(aa) >= 8 and aa[:8] in bb)


def eval_doc(doc: dict, gold: dict, no_llm: bool) -> dict:
    report = run(doc["text"], no_llm=no_llm)
    findings = report.get("findings") or []
    answers = gold.get("answers") or []
    tp = fp = fn = tn = review_tox = review_safe = 0
    hint_hit = hint_n = 0
    matched = []
    for ans in answers:
        target = ans.get("text") or ""
        hit = None
        for f in findings:
            blob = (f.get("text") or "") + (f.get("contract_quote") or "")
            if overlap(target, blob) or overlap(target, f.get("article_title") or ""):
                hit = f
                break
        pred = (hit or {}).get("verdict") or "확인 필요"
        risky_pred = pred in ("위반", "위험")
        toxic = bool(ans.get("toxic"))
        if toxic and risky_pred:
            tp += 1
        elif toxic and pred == "확인 필요":
            review_tox += 1
            fn += 1
        elif toxic:
            fn += 1
        elif risky_pred:
            fp += 1
        elif pred == "확인 필요":
            review_safe += 1
            tn += 1
        else:
            tn += 1
        if toxic:
            hint_n += 1
            hint = str(ans.get("evidence_hint") or "")
            titles = " ".join((e.get("title") or "") + (e.get("id") or "") for e in ((hit or {}).get("evidence") or []))
            if hint and any(tok and tok in titles for tok in hint.replace(",", " ").split()):
                hint_hit += 1
        matched.append({"std_item": ans.get("std_item"), "toxic": toxic, "pred": pred, "hit": bool(hit)})
    n_tox = sum(1 for a in answers if a.get("toxic"))
    n_safe = len(answers) - n_tox
    st = report.get("stats") or {}
    return {
        "id": doc["id"],
        "kind": doc.get("kind"),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "n_toxic": n_tox,
        "n_safe": n_safe,
        "detect": (tp / n_tox) if n_tox else None,
        "fp_rate": (fp / n_safe) if n_safe else None,
        "review_rate": ((review_tox + review_safe) / max(len(answers), 1)),
        "hint_hit": (hint_hit / hint_n) if hint_n else None,
        "quote_mismatch": st.get("quote_mismatch"),
        "dropped_ids": st.get("dropped_ids"),
        "parse_fail": st.get("parse_fail"),
        "parse_ok": st.get("parse_ok"),
        "summary": report.get("summary"),
        "matched": matched,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--gold", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=APP / "eval" / "eval_result.json")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--split", choices=["dev", "test"], default=None)
    parser.add_argument("--domain", choices=["LEASE", "LOAN", "LAB"], default=None)
    args = parser.parse_args()
    if args.docs and args.gold and args.docs.exists() and args.gold.exists():
        docs = json.loads(args.docs.read_text(encoding="utf-8"))
        golds = {g["id"]: g for g in json.loads(args.gold.read_text(encoding="utf-8"))}
        if args.split:
            keep = load_split_ids(args.split, args.domain)
            before = len(docs)
            docs = [d for d in docs if d.get("id") in keep]
            print("SPLIT", args.split, "kept", len(docs), "/", before)
    else:
        docs, golds = docs_from_gold(args.split, args.domain)
        print("FROM_GOLD", "split", args.split or "all", "n", len(docs))
    if args.limit:
        docs = docs[: args.limit]
    rows = []
    for doc in docs:
        gold = golds.get(doc["id"])
        if not gold:
            continue
        print("EVAL", doc["id"], flush=True)
        rows.append(eval_doc(doc, gold, args.no_llm))
    agg = _agg(rows)
    payload = {"docs": rows, "agg": agg}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", args.out)
    print(json.dumps(agg, ensure_ascii=False))


def _agg(rows: list[dict]) -> dict:
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    tn = sum(r["tn"] for r in rows)
    n_tox = sum(r["n_toxic"] for r in rows)
    n_safe = sum(r["n_safe"] for r in rows)
    return {
        "n_docs": len(rows),
        "detect": (tp / n_tox) if n_tox else None,
        "fp_rate": (fp / n_safe) if n_safe else None,
        "review_rate": (sum(r["review_rate"] * (r["n_toxic"] + r["n_safe"]) for r in rows) / max(n_tox + n_safe, 1)),
        "hint_hit": _mean([r["hint_hit"] for r in rows if r["hint_hit"] is not None]),
        "quote_mismatch": sum(r.get("quote_mismatch") or 0 for r in rows),
        "dropped_ids": sum(r.get("dropped_ids") or 0 for r in rows),
        "parse_fail": sum(r.get("parse_fail") or 0 for r in rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def _mean(vals: list) -> float | None:
    return (sum(vals) / len(vals)) if vals else None


if __name__ == "__main__":
    main()
