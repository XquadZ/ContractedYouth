# -*- coding: utf-8 -*-
"""판정 JSON을 코드로 검증한다. 학습 모델 없음."""
from __future__ import annotations

import re

from rag.criteria import blocking_triggered, needs_fact_available
from rag.dates import min_wage_verdict
from rag.paths import LEASE_INCREASE_CAP, MAX_INTEREST

SOURCE_TAG = {
    "법률": "[법령]",
    "시행령": "[법령]",
    "고시": "[고시]",
    "판례": "[판례]",
    "표준계약서": "[표준계약서]",
    "해석례": "[해석례]",
}
INJECT_PATTERNS = ("판단하라", "무시하라", "안전하다고", "system", "이 지시", "ignore previous", "you are")
CRITICAL = ("최저임금", "위약금", "전입신고", "갱신요구", "이자")

# needs_fact 규칙 카운터 (평가 스크립트가 리셋·읽음)
NEEDS_FACT_STATS = {
    "fact_available": 0,
    "blocking_if": 0,
    "needs_fact_other": 0,
    "needs_fact_soft_skip": 0,
    "legacy_force": 0,
}


def reset_needs_fact_stats() -> None:
    for k in NEEDS_FACT_STATS:
        NEEDS_FACT_STATS[k] = 0


def verify_finding(
    clause: str,
    hits: list[dict],
    finding: dict,
    facts: dict,
    *,
    needs_fact_mode: str = "legacy",
    selected_cards: list[dict] | None = None,
) -> dict:
    """needs_fact_mode: legacy | cards"""
    allowed = {h["id"]: h for h in hits}
    dropped_ids = []
    kept = []
    for ev in finding.get("evidence") or []:
        eid = ev.get("id")
        if eid not in allowed:
            dropped_ids.append(eid)
            continue
        kept.append(ev)

    ax_raw_verdict = finding.get("verdict") or "확인 필요"
    verdict = ax_raw_verdict
    review_sources = []

    if not finding.get("parse_ok", True) and finding.get("parse_ok") is False:
        review_sources.append("parse_fail")

    if not kept:
        verdict = "확인 필요"
        review_sources.append("no_evidence")

    notes = []
    state = "ok"
    cq = finding.get("contract_quote") or ""
    if cq and not _contains(cq, clause):
        state = "needs_review"
        notes.append("quote_mismatch:contract")
        review_sources.append("quote_mismatch")
    for ev in kept:
        rec = allowed.get(ev["id"])
        if rec and ev.get("quote") and not _contains(ev["quote"], rec.get("text") or ""):
            state = "needs_review"
            notes.append(f"quote_mismatch:evidence:{ev['id']}")
            if "quote_mismatch" not in review_sources:
                review_sources.append("quote_mismatch")

    tagged = []
    for ev in kept:
        rec = allowed[ev["id"]]
        tagged.append(
            {
                "id": ev["id"],
                "quote": ev.get("quote") or "",
                "title": rec.get("title") or "",
                "source_tag": SOURCE_TAG.get(rec.get("doc_type") or "", "[자료]"),
                "doc_type": rec.get("doc_type") or "",
            }
        )

    needs_fact = finding.get("needs_fact")
    nf_action = None
    if needs_fact:
        if needs_fact_mode == "legacy":
            verdict = "확인 필요"
            notes.append("needs_fact_legacy")
            nf_action = "legacy_force"
            NEEDS_FACT_STATS["legacy_force"] += 1
            review_sources.append("needs_fact")
        else:
            # cards 모드
            if needs_fact_available(needs_fact, facts):
                notes.append("fact_available")
                nf_action = "fact_available"
                NEEDS_FACT_STATS["fact_available"] += 1
                # A.X 판정 유지 (이미 evidence로 바뀐 verdict 유지)
            elif blocking_triggered(needs_fact, clause, selected_cards):
                verdict = "확인 필요"
                notes.append("blocking_if")
                nf_action = "blocking_if"
                NEEDS_FACT_STATS["blocking_if"] += 1
                review_sources.append("needs_fact")
            else:
                verdict = "확인 필요"
                notes.append("needs_fact_other")
                nf_action = "needs_fact_other"
                NEEDS_FACT_STATS["needs_fact_other"] += 1
                review_sources.append("needs_fact")

    if ax_raw_verdict == "확인 필요" and "needs_fact" not in review_sources and "no_evidence" not in review_sources:
        review_sources.append("ax_verdict")

    anomaly = detect_injection(clause)

    rule = numeric_rules(clause, facts)
    ax_verdict = ax_raw_verdict
    if rule.get("verdict") and rule["verdict"] != verdict and rule["verdict"] != "문제 없음":
        verdict = rule["verdict"]
        notes.append("rule_override")

    return {
        "verdict": verdict,
        "ax_verdict": ax_verdict,
        "rule": rule,
        "contract_quote": cq,
        "gap": finding.get("gap") or "",
        "why": finding.get("why") or "",
        "suggestion": finding.get("suggestion") or "",
        "needs_fact": needs_fact,
        "needs_fact_action": nf_action,
        "review_sources": review_sources,
        "evidence": tagged,
        "dropped_ids": [x for x in dropped_ids if x],
        "state": state,
        "notes": notes,
        "anomaly": anomaly,
        "parse_ok": bool(finding.get("parse_ok")),
        "critical": is_critical(verdict, clause, facts, rule),
        "selected_cards": finding.get("selected_cards") or [],
        "prompt_tokens_est": finding.get("prompt_tokens_est"),
        "prompt_chars": finding.get("prompt_chars"),
    }


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _contains(needle: str, hay: str) -> bool:
    n, h = _norm(needle), _norm(hay)
    if not n:
        return True
    return n in h


def detect_injection(text: str) -> list[str]:
    hits = []
    low = text or ""
    for pat in INJECT_PATTERNS:
        if pat.lower() in low.lower():
            hits.append(pat)
    return hits


def numeric_rules(clause: str, facts: dict) -> dict:
    fired = []
    verdict = None
    why = ""
    wage = min_wage_verdict(facts)
    if wage and wage.get("verdict") in ("위반", "확인 필요") and any(k in clause for k in ("시급", "임금", "급여")):
        fired.extend(wage.get("fired") or ["min_wage"])
        verdict = wage["verdict"]
        why = wage.get("why") or ""
    hours = facts.get("work_hours_per_day")
    brk = facts.get("break_minutes")
    if hours is not None and brk is not None and any(k in clause for k in ("휴게", "근로시간", "근무시간")):
        need = 0
        if hours >= 8:
            need = 60
        elif hours >= 4:
            need = 30
        if brk < need:
            fired.append("break")
            verdict = "위반"
            why = (why + " " if why else "") + f"1일 {hours}시간 근로에 휴게 {brk}분은 기준 {need}분 미만이다."
    rate = facts.get("rent_increase_rate")
    if rate is not None and rate > LEASE_INCREASE_CAP and any(k in clause for k in ("증액", "인상")):
        fired.append("lease_increase")
        verdict = "위반"
        why = (why + " " if why else "") + f"증액률 {rate}는 상한 {LEASE_INCREASE_CAP}을 넘는다."
    interest = facts.get("interest_rate")
    delay = facts.get("delay_interest_rate")
    for name, val in (("이자율", interest), ("지연 이율", delay)):
        if val is not None and val > MAX_INTEREST and any(k in clause for k in ("이자", "이율")):
            fired.append("interest")
            verdict = "위반"
            why = (why + " " if why else "") + f"{name} {val}는 연 {MAX_INTEREST}를 넘는다."
    return {"fired": fired, "verdict": verdict, "why": why.strip()}


def is_critical(verdict: str, clause: str, facts: dict, rule: dict) -> list[str]:
    if verdict not in ("위반", "위험"):
        return []
    labels = []
    if "min_wage" in (rule.get("fired") or []) or (min_wage_verdict(facts) or {}).get("verdict") == "위반":
        if any(k in clause for k in ("시급", "임금")):
            labels.append("최저임금 미달")
    if re.search(r"위약금|벌금|손해배상액을?\s*예정", clause):
        labels.append("위약금 예정")
    if re.search(r"전입신고.{0,12}(금지|불가|하지\s*말)", clause):
        labels.append("전입신고 금지")
    if re.search(r"갱신(요구권)?.{0,16}(포기|포기한다|행사하지)", clause):
        labels.append("갱신요구권 포기")
    if "interest" in (rule.get("fired") or []):
        labels.append("이자 20% 초과")
    return labels
