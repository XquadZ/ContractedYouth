# -*- coding: utf-8 -*-
"""계약서 → 항 분할 → 사실표 → BM25+bge RRF → A.X → 검증 → 리포트."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

from rag.corpus import load_corpus
from rag.facts import extract_facts
from rag.criteria import select_cards  # domain-aware


def _select_cards_dated(clause: str, facts: dict, *, domain: str, limit: int = 2) -> tuple[list[dict], list[str]]:
    try:
        from rag.lawwatch.select import select_cards_for_clause

        return select_cards_for_clause(
            clause,
            domain=domain,
            limit=limit,
            contract_date=facts.get("start_date") or facts.get("contract_date"),
            period_start=facts.get("start_date"),
            period_end=facts.get("end_date"),
        )
    except Exception:
        return select_cards(clause, limit=limit, domain=domain), []
from rag.generate import ax_up
from rag.llm_router import generate_finding_routed, is_switching
from rag.paths import ANALYZE_LOG, OUT, RETRIEVE_FLOOR, RETRIEVE_K
from rag.pii import mask_pii
from rag.report import build_report, to_markdown
from rag.retrieve import HybridIndex
from rag.settings import MODEL_VERIFY, get_analyze_model, model_label
from rag.split import judge_segments, split_contract, strip_placeholders
from rag.verify import verify_finding

_INDEX = None
_INDEX_N = -1
_SKIPPED = []


def _clause_interest_overlay(facts: dict, clause: str) -> dict:
    """프롬프트용: 조항 안·금액형 이율이 있으면 그 값으로 interest_rate를 덮어쓴다.
    문서 최대값(facts.interest_rate)은 숫자 규칙용으로 그대로 둔다."""
    out = dict(facts or {})
    t = clause or ""
    local = None
    try:
        from rag.facts import _collect_interest_rates

        found = _collect_interest_rates(t)
        if found:
            # 금액형이 있으면 그걸 우선(조항 자체 이율)
            amount = [r for r in found if r.get("basis") == "amount"]
            local = amount[0] if amount else found[0]
    except Exception:
        local = None
    if local and local.get("rate") is not None:
        out["interest_rate_doc_max"] = facts.get("interest_rate")
        out["interest_rate"] = local.get("rate")
        out["interest_rate_basis"] = local.get("basis")
    return out


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
    mode = get_analyze_model()
    # 저장·로그에는 마스킹 텍스트만
    text_masked, _ = mask_pii(text or "")
    segments = split_contract(text_masked)
    facts = extract_facts(text_masked)
    if domain in ("LAB", "LEASE", "LOAN"):
        facts["domain"] = domain
    else:
        domain = facts.get("domain") or "LAB"
    emit("split", {"n": len(segments), "segments": _public_segments(segments)})
    emit("facts", {"facts": facts, "domain": domain, "analyze_model": mode})
    if is_switching():
        emit("progress", {"phase": "model_switch", "message": "모델 전환 중"})
    index, skipped = get_index()
    llm_ok = False
    llm_error = None
    if not no_llm:
        if mode == "gpt":
            llm_ok = bool(os.environ.get("OPENAI_API_KEY"))
            if not llm_ok:
                llm_error = "OPENAI_API_KEY가 없습니다."
        else:
            try:
                from rag.llm_router import ensure_local_model

                ensure_local_model(mode, alone=True)
                llm_ok = ax_up()
            except Exception as exc:
                llm_error = str(exc)[:200]
            if not llm_ok and not llm_error:
                llm_error = f"{mode} 서버가 응답하지 않는다."

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
        # 기본: 도메인 카드+needs_fact(cards). FIX_ROUND3.
        use_c = True if use_criteria is None else bool(use_criteria)
        nf_mode = needs_fact_mode or ("cards" if use_c else "legacy")
        version_notices: list[str] = []
        cards = []
        if use_c:
            cards, version_notices = _select_cards_dated(row["text"], facts, domain=domain, limit=2)
        if not no_llm and llm_ok:
            facts_for_llm = _clause_interest_overlay(facts, row["text"])
            finding = generate_finding_routed(row["text"], facts_for_llm, hits, use_criteria=use_c)
            hits = finding.get("hits_for_verify") or hits
            # generate 경로 카드 메타(버전·안내) 우선
            if finding.get("cards"):
                cards = finding["cards"]
            for c in cards:
                if version_notices:
                    c.setdefault("_version_notices", version_notices)
        # 평가 경로(quant_run)와 같게: MODEL_VERIFY.axok (기본 False). 파싱 실패를 문제 없음으로 덮지 않음.
        axok = bool((MODEL_VERIFY.get(mode) or {}).get("axok", False))
        if finding.get("parse_ok") is False and not finding.get("error"):
            finding = {
                **finding,
                "verdict": "확인 필요",
                "why": finding.get("why") or "확인 필요(분석 실패)",
                "suggestion": finding.get("suggestion") or "확인 필요(분석 실패)",
            }
        elif finding.get("error") and not finding.get("parse_ok"):
            finding = {
                **finding,
                "verdict": "확인 필요",
                "why": "확인 필요(분석 실패)",
                "suggestion": "확인 필요(분석 실패)",
            }
        verified = verify_finding(
            row["text"],
            hits,
            finding,
            facts,
            needs_fact_mode=nf_mode,
            selected_cards=cards,
            ax_review_to_ok=axok,
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
            "card_versions": [
                {
                    "id": c.get("id"),
                    "version": c.get("_version"),
                    "effective_from": c.get("_effective_from"),
                    "apply_rule": c.get("_apply_rule"),
                }
                for c in cards
            ],
            "version_notices": list(
                dict.fromkeys(
                    list(version_notices)
                    + [n for c in cards for n in (c.get("_version_notices") or [])]
                )
            ),
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
    demo_notice = None
    if mode == "gpt":
        demo_notice = "시연 모드: 개인정보를 가린 뒤 외부 AI(OpenAI)로 분석해요"
    report = build_report(
        {
            "domain": domain,
            "facts": facts,
            "segments": segments,
            "findings": findings,
            "stats": stats,
            "model": model_label(mode),
            "analyze_model": mode,
            "demo_notice": demo_notice,
        }
    )
    report["stats"] = stats
    report["llm"] = stats["llm"]
    report["llm_error"] = llm_error
    report["n_records"] = stats["n_records"]
    report["findings"] = [_public_finding(f) for f in findings]
    report["segments"] = _public_segments(segments)
    report["masked_text"] = text_masked
    report["analyze_model"] = mode
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
