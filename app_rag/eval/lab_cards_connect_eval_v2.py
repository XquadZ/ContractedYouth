# -*- coding: utf-8 -*-
"""근로 LAB dev 8장 — B0/B1/B2 카드 연결 전후 비교. test 금지."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, build_judge_prompt, generate_finding  # noqa: E402
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
from dev_eval import (  # noqa: E402
    gold_codes,
    gold_provisions,
    is_meta,
    rate,
    score_pair,
)

RISKY = ("위반", "위험")
SETTINGS = {
    "B0": {"use_criteria": False, "needs_fact_mode": "legacy", "label": "카드 없음 + 옛 needs_fact"},
    "B1": {"use_criteria": True, "needs_fact_mode": "legacy", "label": "카드 있음 + 옛 needs_fact"},
    "B2": {"use_criteria": True, "needs_fact_mode": "cards", "label": "카드 있음 + 새 needs_fact"},
}


def load_lab_docs() -> list[dict]:
    keep = load_split_ids("dev", "LAB")
    contracts = load_jsonl(GOLD["LAB"]["contract"])
    law_map = {r["segment_id"]: r for r in load_jsonl(GOLD["LAB"]["law"])}
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
        docs.append({"domain": "LAB", "doc_id": did, "segs": segs, "law_map": law_map})
    return docs


def eval_doc(doc: dict, index, corpus_keys, corpus_ids, *, use_criteria: bool, needs_fact_mode: str) -> dict:
    segs = doc["segs"]
    full = "\n".join(s.get("text") or "" for s in segs)
    facts = extract_facts(full)
    facts["domain"] = "LAB"
    rows = []
    max_prompt_tokens = 0
    max_prompt_chars = 0
    for seg in segs:
        if is_meta(seg):
            continue
        text = seg.get("text") or ""
        law = doc["law_map"].get(seg.get("segment_id") or "") or {}
        t0 = time.perf_counter()
        retrieved = index.search(strip_placeholders(text), domain="LAB", title="")
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
        hit_ids = [h["id"] for h in hits]
        gold_raw = gold_provisions(seg, law)
        gold_keys = {k for raw in gold_raw for k in keys_from_gold(raw)}
        in_corpus = [raw for raw in gold_raw if gold_in_corpus(raw, corpus_keys, corpus_ids)]
        all_missing = bool(gold_raw) and not in_corpus
        ev_ok = any(hit_matches_gold(eid, gold_keys, gold_raw) for eid in used_ids) if (gold_keys or gold_raw) else False
        verdict = verified.get("verdict") or "확인 필요"
        label = seg.get("label") or ""
        bucket = score_pair(label, verdict)
        pt = int(finding.get("prompt_tokens_est") or 0)
        pc = int(finding.get("prompt_chars") or 0)
        max_prompt_tokens = max(max_prompt_tokens, pt)
        max_prompt_chars = max(max_prompt_chars, pc)
        # 확인 필요 출처 (최종 판정이 확인 필요일 때만 1차 분류)
        src = "other"
        if verdict == "확인 필요":
            rs = verified.get("review_sources") or []
            if "parse_fail" in rs or not verified.get("parse_ok"):
                src = "parse_fail"
            elif "no_evidence" in rs:
                src = "no_evidence"
            elif "needs_fact" in rs:
                src = "needs_fact"
            elif "quote_mismatch" in rs:
                src = "quote_mismatch"
            elif "ax_verdict" in rs or verified.get("ax_verdict") == "확인 필요":
                src = "ax_verdict"
            else:
                src = "other"
        rows.append(
            {
                "doc_id": doc["doc_id"],
                "segment_id": seg.get("segment_id"),
                "label": label,
                "verdict": verdict,
                "ax_verdict": verified.get("ax_verdict"),
                "bucket": bucket,
                "why": (verified.get("why") or "")[:300],
                "selected_cards": finding.get("selected_cards") or [],
                "needs_fact": verified.get("needs_fact"),
                "needs_fact_action": verified.get("needs_fact_action"),
                "doc_question": verified.get("doc_question"),
                "notes": verified.get("notes") or [],
                "rule_fired": (verified.get("rule") or {}).get("fired") or [],
                "review_source": src,
                "review_sources": verified.get("review_sources") or [],
                "ev_ok": ev_ok,
                "gold_missing_from_corpus": all_missing,
                "parse_ok": bool(verified.get("parse_ok")),
                "quote_mismatch": any(str(n).startswith("quote_mismatch") for n in (verified.get("notes") or [])),
                "prompt_tokens_est": pt,
                "text60": (text.replace("\n", " ")[:60]),
                "latency_ms": round(ms, 1),
                "gold_codes": gold_codes(seg, law),
                "ax_ok_to_violation": (
                    verified.get("ax_verdict") == "문제 없음" and verdict == "위반"
                ),
            }
        )
    return {"doc_id": doc["doc_id"], "rows": rows, "facts": {k: facts.get(k) for k in (
        "regular_workers", "weekly_scheduled_hours", "weekly_hours_formula",
        "contract_months", "probation_months", "probation_cut_rate", "apply_year",
        "start_date", "end_date", "hourly_wage", "monthly_wage",
    )}, "max_prompt_tokens": max_prompt_tokens, "max_prompt_chars": max_prompt_chars}


def summarize(rows: list[dict]) -> dict:
    tox = [r for r in rows if r["label"] == "toxic"]
    saf = [r for r in rows if r["label"] == "safe"]
    chk = [r for r in rows if r["label"] == "check"]
    det = [r for r in tox if r["bucket"] == "detect"]
    par = [r for r in tox if r["bucket"] == "partial"]
    mis = [r for r in tox if r["bucket"] == "miss"]
    fp = [r for r in saf if r["bucket"] == "fp"]
    ow = [r for r in saf if r["bucket"] == "overwarn"]
    # 과잉 경고 분리: 조항 확인 필요(blocking_if) vs 문서 질문(doc_question) vs 기타
    ow_clause = [r for r in ow if r.get("needs_fact_action") == "blocking_if"]
    ow_docq = [r for r in ow if r.get("needs_fact_action") == "doc_question"]
    ow_other = [r for r in ow if r.get("needs_fact_action") not in ("blocking_if", "doc_question")]
    flips = [r for r in rows if r.get("ax_ok_to_violation")]
    cok = [r for r in chk if r["bucket"] == "check_ok"]
    ev_all = tox + chk
    ev_inc = [r for r in ev_all if not r["gold_missing_from_corpus"]]
    review = Counter(r["review_source"] for r in rows if r["verdict"] == "확인 필요")
    return {
        "n": len(rows),
        "toxic": len(tox),
        "detect": len(det),
        "partial": len(par),
        "miss": len(mis),
        "safe": len(saf),
        "fp": len(fp),
        "overwarn": len(ow),
        "overwarn_clause_check": len(ow_clause),
        "overwarn_doc_question": len(ow_docq),
        "overwarn_other": len(ow_other),
        "ax_ok_to_violation": len(flips),
        "check": len(chk),
        "check_ok": len(cok),
        "detect_rate": rate(len(det), len(tox)),
        "partial_rate": rate(len(par), len(tox)),
        "miss_rate": rate(len(mis), len(tox)),
        "fp_rate": rate(len(fp), len(saf)),
        "overwarn_rate": rate(len(ow), len(saf)),
        "overwarn_clause_check_rate": rate(len(ow_clause), len(saf)),
        "overwarn_doc_question_rate": rate(len(ow_docq), len(saf)),
        "check_rate": rate(len(cok), len(chk)),
        "ev_rate": rate(sum(1 for r in ev_all if r["ev_ok"]), len(ev_all)),
        "ev_rate_inc": rate(sum(1 for r in ev_inc if r["ev_ok"]), len(ev_inc)),
        "review_sources": dict(review),
        "missed": [
            {
                "text60": r["text60"],
                "gold": r["label"],
                "verdict": r["verdict"],
                "cards": r["selected_cards"],
                "why": r["why"],
                "segment_id": r["segment_id"],
            }
            for r in mis[:10]
        ],
        "overwarn_samples": [
            {
                "text60": r["text60"],
                "gold": r["label"],
                "verdict": r["verdict"],
                "cards": r["selected_cards"],
                "why": r["why"],
                "segment_id": r["segment_id"],
                "needs_fact_action": r.get("needs_fact_action"),
                "kind": (
                    "조항 확인 필요"
                    if r.get("needs_fact_action") == "blocking_if"
                    else ("문서 질문" if r.get("needs_fact_action") == "doc_question" else "기타")
                ),
            }
            for r in ow[:10]
        ],
        "ax_ok_to_violation_samples": [
            {
                "segment_id": r["segment_id"],
                "text60": r["text60"],
                "verdict": r["verdict"],
                "ax_verdict": r.get("ax_verdict"),
                "notes": r.get("notes"),
                "rule_fired": r.get("rule_fired"),
            }
            for r in flips[:10]
        ],
        "overwarn_split": {
            "조항_확인_필요": len(ow_clause),
            "문서_질문": len(ow_docq),
            "기타": len(ow_other),
        },
    }


def gold_regular_workers(meta_text: str):
    m = re.search(r"상시\s*근로자\s*수\s*[:：]?\s*([0-9]+)\s*명", meta_text or "")
    if m:
        return int(m.group(1))
    m = re.search(r"상시\s*([0-9]+)\s*명", meta_text or "")
    return int(m.group(1)) if m else None


def facts_accuracy(docs: list[dict]) -> dict:
    rows = []
    for doc in docs:
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        meta = next((s for s in doc["segs"] if is_meta(s)), None)
        meta_text = (meta or {}).get("text") or ""
        gold_n = gold_regular_workers(meta_text)
        pred = facts.get("regular_workers")
        rows.append(
            {
                "doc_id": doc["doc_id"],
                "gold_regular_workers": gold_n,
                "pred_regular_workers": pred,
                "regular_match": (gold_n is not None and pred == gold_n),
                "weekly_scheduled_hours": facts.get("weekly_scheduled_hours"),
                "weekly_hours_formula": facts.get("weekly_hours_formula"),
                "contract_months": facts.get("contract_months"),
                "probation_months": facts.get("probation_months"),
                "probation_cut_rate": facts.get("probation_cut_rate"),
                "apply_year": facts.get("apply_year"),
                "meta60": meta_text.replace("\n", " ")[:80],
            }
        )
    with_pred = sum(1 for r in rows if r["pred_regular_workers"] is not None)
    with_weekly = sum(1 for r in rows if r["weekly_scheduled_hours"] is not None)
    with_months = sum(1 for r in rows if r["contract_months"] is not None)
    with_prob = sum(1 for r in rows if r["probation_months"] is not None)
    with_year = sum(1 for r in rows if r["apply_year"] is not None)
    gold_have = [r for r in rows if r["gold_regular_workers"] is not None]
    match_n = sum(1 for r in gold_have if r["regular_match"])
    return {
        "docs": len(rows),
        "regular_workers_extracted": with_pred,
        "weekly_hours_extracted": with_weekly,
        "contract_months_extracted": with_months,
        "probation_extracted": with_prob,
        "apply_year_extracted": with_year,
        "gold_regular_n": len(gold_have),
        "regular_match": match_n,
        "regular_match_rate": rate(match_n, len(gold_have)),
        "rows": rows,
    }


def prompt_length_probe(docs: list[dict], index) -> dict:
    """가장 긴 프롬프트 추정 토큰이 ctx 8192 안인지."""
    max_tok = 0
    max_chars = 0
    worst = None
    for doc in docs:
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = "LAB"
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            hits = index.search(strip_placeholders(text), domain="LAB", title="").get("hits") or []
            user, cards = build_judge_prompt(text, facts, hits, use_criteria=True)
            tok = max(1, len(user) // 2)
            if tok > max_tok:
                max_tok = tok
                max_chars = len(user)
                worst = {
                    "doc_id": doc["doc_id"],
                    "segment_id": seg.get("segment_id"),
                    "cards": [c.get("id") for c in cards],
                    "chars": len(user),
                    "tokens_est": tok,
                }
    return {
        "max_chars": max_chars,
        "max_tokens_est": max_tok,
        "ctx": 8192,
        "fits_ctx": max_tok < 8192,
        "worst": worst,
        "method": "chars/2 (보수 추정)",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts-only", action="store_true")
    parser.add_argument("--setting", choices=["B0", "B1", "B2", "ALL"], default="ALL")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    docs = load_lab_docs()
    print("LAB_DEV_DOCS", len(docs), [d["doc_id"] for d in docs])
    judge_n = sum(1 for d in docs for s in d["segs"] if not is_meta(s))
    print("JUDGE_SEGS", judge_n, "EST_ONE_MIN", round(judge_n * 2.64 / 60, 2), "EST_THREE_MIN", round(judge_n * 2.64 * 3 / 60, 2))

    fact_acc = facts_accuracy(docs)
    print("FACTS_ACC", json.dumps({k: fact_acc[k] for k in fact_acc if k != "rows"}, ensure_ascii=False))

    if args.facts_only:
        dest = args.out or (OUT / "lab_cards_facts_acc.json")
        dest.write_text(json.dumps(fact_acc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", dest)
        return

    if not ax_up():
        print("STOP A.X down")
        sys.exit(2)

    index, skipped = get_index()
    corpus_ids = [r["id"] for r in index.records]
    corpus_keys = set()
    for rec in index.records:
        key = canon_from_id(rec["id"])
        if key:
            corpus_keys.add(key)

    probe = prompt_length_probe(docs, index)
    print("PROMPT_PROBE", json.dumps(probe, ensure_ascii=False))

    settings = list(SETTINGS) if args.setting == "ALL" else [args.setting]
    # 3회 × 112 ≈ 15분 < 60 → 질문 없이 진행
    if judge_n * len(settings) * 2.64 > 3600:
        print("STOP_ASK over 60min")
        sys.exit(3)

    results = {}
    for name in settings:
        cfg = SETTINGS[name]
        print("SETTING", name, cfg)
        reset_needs_fact_stats()
        t0 = time.perf_counter()
        all_rows = []
        per_doc = []
        max_tok = 0
        for doc in docs:
            pack = eval_doc(
                doc,
                index,
                corpus_keys,
                corpus_ids,
                use_criteria=cfg["use_criteria"],
                needs_fact_mode=cfg["needs_fact_mode"],
            )
            all_rows.extend(pack["rows"])
            per_doc.append({"doc_id": pack["doc_id"], "n": len(pack["rows"]), "facts": pack["facts"]})
            max_tok = max(max_tok, pack["max_prompt_tokens"])
            print(f"  DOC {pack['doc_id']} n={len(pack['rows'])}")
        wall = time.perf_counter() - t0
        summary = summarize(all_rows)
        # 깨끗한 계약서 (toxic 0)
        tox_by_doc = Counter()
        for r in all_rows:
            if r["label"] == "toxic":
                tox_by_doc[r["doc_id"]] += 1
        clean_ids = [d["doc_id"] for d in docs if tox_by_doc[d["doc_id"]] == 0]
        clean_rows = [r for r in all_rows if r["doc_id"] in clean_ids]
        clean_counts = {
            "docs": clean_ids,
            "n": len(clean_rows),
            "위반": sum(1 for r in clean_rows if r["verdict"] == "위반"),
            "위험": sum(1 for r in clean_rows if r["verdict"] == "위험"),
            "확인 필요": sum(1 for r in clean_rows if r["verdict"] == "확인 필요"),
            "문제 없음": sum(1 for r in clean_rows if r["verdict"] == "문제 없음"),
        }
        results[name] = {
            "config": cfg,
            "wall_sec": round(wall, 2),
            "summary": summary,
            "needs_fact_stats": dict(NEEDS_FACT_STATS),
            "clean_docs": clean_counts,
            "max_prompt_tokens_est": max_tok,
            "per_doc": per_doc,
            "rows": all_rows,
        }
        print(
            "DONE",
            name,
            "wall",
            round(wall, 2),
            "detect",
            summary["detect_rate"],
            "overwarn",
            summary["overwarn_rate"],
            "nf_stats",
            NEEDS_FACT_STATS,
        )

    payload = {
        "domain": "LAB",
        "split": "dev",
        "docs": [d["doc_id"] for d in docs],
        "judge_n": judge_n,
        "facts_accuracy": fact_acc,
        "prompt_probe": probe,
        "settings": results,
    }
    dest = args.out or (OUT / "lab_cards_connect.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
