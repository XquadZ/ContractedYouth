# -*- coding: utf-8 -*-
"""LAB·LEASE dev — A.X(8082) vs EXAONE(8083) 동일 카드·동일 규칙 비교.
A.X 기본 설정/서버는 건드리지 않는다. EXAONE은 start_exaone.py로 8083에 띄운 뒤 실행.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, generate_finding, set_llm_endpoint  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import NEEDS_FACT_STATS, reset_needs_fact_stats, verify_finding  # noqa: E402
from recall_dev import (  # noqa: E402
    canon_from_id,
    gold_in_corpus,
    hit_matches_gold,
    keys_from_gold,
    load_jsonl,
)
from splitutil import load_split_ids  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta, rate, score_pair  # noqa: E402

ENDPOINTS = {
    "AX": {
        "url": "http://127.0.0.1:8082/v1/chat/completions",
        "health": "http://127.0.0.1:8082/health",
        "label": "A.X-4.0-Light",
    },
    "EXAONE": {
        "url": "http://127.0.0.1:8083/v1/chat/completions",
        "health": "http://127.0.0.1:8083/health",
        "label": "EXAONE-4.0-32B-Q4_K_M",
    },
}


def load_domain_docs(domain: str) -> list[dict]:
    keep = load_split_ids("dev", domain)
    contracts = load_jsonl(GOLD[domain]["contract"])
    law_map = {r["segment_id"]: r for r in load_jsonl(GOLD[domain]["law"])}
    by_doc = defaultdict(list)
    for row in contracts:
        if row.get("doc_id") in keep:
            by_doc[row["doc_id"]].append(row)
    docs = []
    for did in sorted(by_doc):
        segs = sorted(
            by_doc[did],
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        docs.append({"domain": domain, "doc_id": did, "segs": segs, "law_map": law_map})
    return docs


def eval_doc(doc: dict, index, corpus_keys, corpus_ids) -> dict:
    domain = doc["domain"]
    # LAB만 카드. LEASE는 카드 없음(동일 규칙 verify, use_criteria=False).
    use_criteria = domain == "LAB"
    needs_fact_mode = "cards" if use_criteria else "legacy"
    segs = doc["segs"]
    full = "\n".join(s.get("text") or "" for s in segs)
    facts = extract_facts(full)
    facts["domain"] = domain
    rows = []
    for seg in segs:
        if is_meta(seg):
            continue
        text = seg.get("text") or ""
        law = doc["law_map"].get(seg.get("segment_id") or "") or {}
        t0 = time.perf_counter()
        retrieved = index.search(strip_placeholders(text), domain=domain, title="")
        hits = retrieved.get("hits") or []
        finding = generate_finding(text, facts, hits, use_criteria=use_criteria)
        cards = select_cards(text, limit=2) if use_criteria else []
        verified = verify_finding(
            text,
            hits,
            finding,
            facts,
            needs_fact_mode=needs_fact_mode,
            selected_cards=cards,
        )
        ms = (time.perf_counter() - t0) * 1000
        used_ids = [e.get("id") for e in (verified.get("evidence") or []) if e.get("id")]
        gold_raw = gold_provisions(seg, law)
        gold_keys = {k for raw in gold_raw for k in keys_from_gold(raw)}
        in_corpus = [raw for raw in gold_raw if gold_in_corpus(raw, corpus_keys, corpus_ids)]
        all_missing = bool(gold_raw) and not in_corpus
        ev_ok = any(hit_matches_gold(eid, gold_keys, gold_raw) for eid in used_ids) if (gold_keys or gold_raw) else False
        verdict = verified.get("verdict") or "확인 필요"
        label = seg.get("label") or ""
        rows.append(
            {
                "domain": domain,
                "doc_id": doc["doc_id"],
                "segment_id": seg.get("segment_id"),
                "label": label,
                "verdict": verdict,
                "ax_verdict": verified.get("ax_verdict"),
                "bucket": score_pair(label, verdict),
                "needs_fact": verified.get("needs_fact"),
                "needs_fact_action": verified.get("needs_fact_action"),
                "notes": verified.get("notes") or [],
                "ax_review_to_ok": verified.get("needs_fact_action") == "ax_review_to_ok",
                "ev_ok": ev_ok,
                "gold_missing_from_corpus": all_missing,
                "parse_ok": bool(verified.get("parse_ok")),
                "text60": (text.replace("\n", " ")[:60]),
                "latency_ms": round(ms, 1),
                "gold_codes": gold_codes(seg, law),
                "selected_cards": finding.get("selected_cards") or [],
            }
        )
    return {"doc_id": doc["doc_id"], "domain": domain, "rows": rows}


def summarize(rows: list[dict]) -> dict:
    tox = [r for r in rows if r["label"] == "toxic"]
    saf = [r for r in rows if r["label"] == "safe"]
    chk = [r for r in rows if r["label"] == "check"]
    det = [r for r in tox if r["bucket"] == "detect"]
    par = [r for r in tox if r["bucket"] == "partial"]
    mis = [r for r in tox if r["bucket"] == "miss"]
    fp = [r for r in saf if r["bucket"] == "fp"]
    ow = [r for r in saf if r["bucket"] == "overwarn"]
    cok = [r for r in chk if r["bucket"] == "check_ok"]
    overrides = [r for r in rows if r.get("ax_review_to_ok")]
    return {
        "n": len(rows),
        "toxic": len(tox),
        "detect": len(det),
        "partial": len(par),
        "miss": len(mis),
        "safe": len(saf),
        "fp": len(fp),
        "overwarn": len(ow),
        "check": len(chk),
        "check_ok": len(cok),
        "detect_rate": rate(len(det), len(tox)),
        "fp_rate": rate(len(fp), len(saf)),
        "overwarn_rate": rate(len(ow), len(saf)),
        "check_rate": rate(len(cok), len(chk)),
        "miss_rate": rate(len(mis), len(tox)),
        "ax_review_to_ok": len(overrides),
        "ax_review_to_ok_toxic": sum(1 for r in overrides if r["label"] == "toxic"),
        "parse_ok_rate": rate(sum(1 for r in rows if r["parse_ok"]), len(rows)),
        "mean_latency_ms": round(sum(r["latency_ms"] for r in rows) / max(1, len(rows)), 1),
    }


def run_model(name: str, docs: list[dict], index, corpus_keys, corpus_ids) -> dict:
    ep = ENDPOINTS[name]
    set_llm_endpoint(ep["url"], ep["health"])
    if not ax_up():
        set_llm_endpoint(None, None)
        raise SystemExit(f"STOP {name} down at {ep['health']}")
    reset_needs_fact_stats()
    t0 = time.perf_counter()
    all_rows = []
    by_domain = defaultdict(list)
    for doc in docs:
        pack = eval_doc(doc, index, corpus_keys, corpus_ids)
        all_rows.extend(pack["rows"])
        by_domain[pack["domain"]].extend(pack["rows"])
        print(f"  [{name}] {pack['domain']} {pack['doc_id']} n={len(pack['rows'])}", flush=True)
    wall = time.perf_counter() - t0
    out = {
        "model": ep["label"],
        "endpoint": ep["url"],
        "wall_sec": round(wall, 2),
        "needs_fact_stats": dict(NEEDS_FACT_STATS),
        "summary_all": summarize(all_rows),
        "summary_by_domain": {d: summarize(rs) for d, rs in by_domain.items()},
        "rows": all_rows,
    }
    set_llm_endpoint(None, None)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="AX,EXAONE", help="comma list: AX,EXAONE")
    parser.add_argument("--domains", default="LAB,LEASE")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    docs = []
    for d in domains:
        docs.extend(load_domain_docs(d))
    judge_n = sum(1 for doc in docs for s in doc["segs"] if not is_meta(s))
    print("DOCS", len(docs), "JUDGE", judge_n, "MODELS", models, flush=True)
    # 대략 2.6s/seg * models
    est_min = judge_n * len(models) * 2.64 / 60
    print("EST_MIN", round(est_min, 1), flush=True)
    if est_min > 90:
        print("STOP_ASK over 90min estimate", flush=True)
        sys.exit(3)

    index, _skipped = get_index()
    corpus_ids = [r["id"] for r in index.records]
    corpus_keys = set()
    for rec in index.records:
        key = canon_from_id(rec["id"])
        if key:
            corpus_keys.add(key)

    results = {}
    for name in models:
        print("MODEL", name, flush=True)
        results[name] = run_model(name, docs, index, corpus_keys, corpus_ids)
        s = results[name]["summary_all"]
        print(
            "DONE",
            name,
            "detect",
            s["detect_rate"],
            "fp",
            s["fp_rate"],
            "overwarn",
            s["overwarn_rate"],
            flush=True,
        )

    # 나란히 비교표
    compare = {}
    for d in domains + ["ALL"]:
        compare[d] = {}
        for name in models:
            src = results[name]["summary_all"] if d == "ALL" else results[name]["summary_by_domain"].get(d, {})
            compare[d][name] = {
                k: src.get(k)
                for k in (
                    "n",
                    "detect_rate",
                    "fp_rate",
                    "overwarn_rate",
                    "check_rate",
                    "miss_rate",
                    "ax_review_to_ok",
                    "ax_review_to_ok_toxic",
                    "mean_latency_ms",
                    "parse_ok_rate",
                )
            }

    payload = {
        "domains": domains,
        "models": models,
        "judge_n": judge_n,
        "compare": compare,
        "results": results,
        "note": "동일 verify 규칙·LAB은 B2 카드(cards needs_fact). LEASE는 카드 없음+legacy needs_fact(도메인에 LAB 카드만 존재).",
    }
    dest = args.out or (OUT / "ax_vs_exaone_lab_lease.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest, flush=True)


if __name__ == "__main__":
    main()
