# -*- coding: utf-8 -*-
"""계약서 → 항 분할 → 사실표 → BM25+bge RRF → A.X → 검증 → 리포트."""
from __future__ import annotations

import json
import os
import time
from typing import Callable

from rag.corpus import load_corpus
from rag.facts import extract_facts
from rag.generate import ax_up, generate_finding
from rag.paths import ANALYZE_LOG, OUT, RETRIEVE_FLOOR, RETRIEVE_K
from rag.report import build_report, to_markdown
from rag.retrieve import HybridIndex
from rag.split import judge_segments, split_contract, strip_placeholders
from rag.verify import verify_finding

_INDEX = None
_INDEX_N = -1
_SKIPPED = []


def _log(row: dict) -> None:
    ANALYZE_LOG.parent.mkdir(parents=True, exist_ok=True)
    safe = {
        "n_clauses": row.get("n_clauses"),
        "segment_id": row.get("segment_id"),
        "latency_ms": row.get("latency_ms"),
        "verdict": row.get("verdict"),
        "evidence_ids": row.get("evidence_ids"),
        "passed_ids": row.get("passed_ids"),
        "parse_ok": row.get("parse_ok"),
        "filter_mode": row.get("filter_mode"),
    }
    with ANALYZE_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(safe, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def get_index() -> tuple[HybridIndex, list[dict]]:
    global _INDEX, _INDEX_N, _SKIPPED
    records, skipped = load_corpus()
    _SKIPPED = skipped
    if _INDEX is None or _INDEX_N != len(records):
        _INDEX = HybridIndex(records)
        _INDEX_N = len(records)
    return _INDEX, skipped


def run(
    text: str,
    *,
    no_llm: bool = False,
    domain: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    use_criteria: bool | None = None,
    needs_fact_mode: str | None = None,
) -> dict:
    def emit(kind: str, data: dict) -> None:
        if on_event:
            on_event(kind, data)

    t_all = time.perf_counter()
    segments = split_contract(text)
    facts = extract_facts(text)
    if domain in ("LAB", "LEASE", "LOAN"):
        facts["domain"] = domain
    else:
        domain = facts.get("domain") or "LAB"
    emit("split", {"n": len(segments), "segments": _public_segments(segments)})
    emit("facts", {"facts": facts, "domain": domain})
    index, skipped = get_index()
    llm_ok = (not no_llm) and ax_up()
    llm_error = None
    if not no_llm and not llm_ok:
        llm_error = "A.X 서버가 8082에서 응답하지 않는다. python app_rag/start_ax.py"

    judge_rows = judge_segments(segments)
    emit("progress", {"phase": "judge", "n_clauses": len(judge_rows), "done": 0})
    findings = []
    parse_ok_n = 0
    parse_fail_n = 0
    quote_mismatch_n = 0
    dropped_n = 0
    for i, row in enumerate(judge_rows):
        t0 = time.perf_counter()
        retrieved = index.search(
            strip_placeholders(row["text"]),
            domain=domain,
            title=strip_placeholders(row.get("article_title") or ""),
        )
        hits = retrieved["hits"]
        finding = {
            "verdict": "확인 필요",
            "contract_quote": "",
            "gap": "",
            "why": "검색만 했다." if no_llm else (llm_error or ""),
            "evidence": [],
            "suggestion": "",
            "needs_fact": None,
            "parse_ok": False,
            "error": None,
        }
        # 기본: LAB이면 카드+새 needs_fact. 평가에서 플래그로 B0/B1/B2 고정 가능.
        use_c = (domain == "LAB") if use_criteria is None else bool(use_criteria)
        nf_mode = needs_fact_mode or ("cards" if use_c else "legacy")
        if not no_llm and llm_ok:
            finding = generate_finding(row["text"], facts, hits, use_criteria=use_c)
        verified = verify_finding(
            row["text"],
            hits,
            finding,
            facts,
            needs_fact_mode=nf_mode,
            selected_cards=None,
        )
        latency = (time.perf_counter() - t0) * 1000
        item = {
            **row,
            **verified,
            "hits": [{"id": h["id"], "title": h["title"], "score": h.get("score"), "bm25": h.get("bm25"), "cosine": h.get("cosine")} for h in hits],
            "std_items": retrieved["std_items"],
            "filter_mode": retrieved["filter_mode"],
            "candidates": retrieved["candidates"],
            "latency_ms": round(latency, 1),
            "parse_ok": finding.get("parse_ok"),
            "llm_error": finding.get("error"),
        }
        if finding.get("parse_ok"):
            parse_ok_n += 1
        else:
            parse_fail_n += 1
        if "quote_mismatch" in " ".join(item.get("notes") or []):
            quote_mismatch_n += 1
        dropped_n += len(item.get("dropped_ids") or [])
        findings.append(item)
        _log(
            {
                "n_clauses": len(judge_rows),
                "segment_id": row["segment_id"],
                "latency_ms": item["latency_ms"],
                "verdict": item["verdict"],
                "evidence_ids": item.get("used_ids") or [e["id"] for e in item.get("evidence") or []],
                "passed_ids": [h["id"] for h in hits],
                "parse_ok": item["parse_ok"],
                "filter_mode": item["filter_mode"],
            }
        )
        emit("clause", {"finding": _public_finding(item), "done": i + 1, "n_clauses": len(judge_rows)})
        emit("progress", {"phase": "judge", "n_clauses": len(judge_rows), "done": i + 1})

    stats = {
        "n_records": len(index.records),
        "skipped_records": skipped,
        "k": RETRIEVE_K,
        "floor": RETRIEVE_FLOOR,
        "embed_ok": index.embed.ok,
        "embed_error": index.embed.error,
        "llm": (not no_llm) and llm_ok,
        "llm_error": llm_error,
        "parse_ok": parse_ok_n,
        "parse_fail": parse_fail_n,
        "parse_total": len(findings),
        "quote_mismatch": quote_mismatch_n,
        "dropped_ids": dropped_n,
        "wall_ms": round((time.perf_counter() - t_all) * 1000, 1),
        "latencies_ms": [{"segment_id": f["segment_id"], "ms": f["latency_ms"]} for f in findings],
    }
    report = build_report(
        {
            "domain": domain,
            "facts": facts,
            "segments": segments,
            "findings": findings,
            "stats": stats,
        }
    )
    report["stats"] = stats
    report["llm"] = stats["llm"]
    report["llm_error"] = llm_error
    report["n_records"] = stats["n_records"]
    report["findings"] = [_public_finding(f) for f in findings]
    report["segments"] = _public_segments(segments)
    emit("done", {"report": report})
    return report


def _public_segments(segments: list[dict]) -> list[dict]:
    return [
        {
            "segment_id": s["segment_id"],
            "order": s["order"],
            "segment_type": s["segment_type"],
            "article_title": s.get("article_title") or "",
            "text": s["text"],
        }
        for s in segments
    ]


def _public_finding(row: dict) -> dict:
    keep = (
        "segment_id",
        "order",
        "segment_type",
        "article_title",
        "text",
        "verdict",
        "ax_verdict",
        "rule",
        "contract_quote",
        "gap",
        "why",
        "suggestion",
        "needs_fact",
        "evidence",
        "dropped_ids",
        "state",
        "notes",
        "anomaly",
        "parse_ok",
        "critical",
        "hits",
        "std_items",
        "filter_mode",
        "candidates",
        "latency_ms",
        "llm_error",
    )
    return {k: row.get(k) for k in keep}


def write_outputs(report: dict, dest=None) -> tuple:
    path = dest or (OUT / "report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    slim = dict(report)
    # 계약서 원문 전체는 저장하지 않는다. 인용·카드만 남긴다.
    slim.pop("segments", None)
    for card in slim.get("cards") or []:
        card.pop("clause_text", None)
    for finding in slim.get("findings") or []:
        finding.pop("text", None)
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = path.with_suffix(".md")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return path, md_path
