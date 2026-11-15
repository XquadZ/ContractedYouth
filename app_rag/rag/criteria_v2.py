# -*- coding: utf-8 -*-
"""LAB 기준 카드 로드·매칭. A.X/검색 설정과 무관."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from rag.paths import APP
from rag.yamlutil import load as load_yaml

CARDS_PATH = APP / "criteria" / "LAB_cards.yaml"

# uses_facts / needs_fact 문자열 → facts.py 키
FACT_KEY = {
    "시급": "hourly_wage",
    "월급": "monthly_wage",
    "시급_또는_월급": "hourly_wage",
    "1주 소정근로시간": "weekly_scheduled_hours",
    "주_소정근로시간": "weekly_scheduled_hours",
    "주_근로시간": "weekly_scheduled_hours",
    "일_근로시간": "work_hours_per_day",
    "적용연도": "apply_year",
    "수습 기간": "probation_months",
    "수습여부": "probation_months",
    "감액률": "probation_cut_rate",
    "계약기간(개월)": "contract_months",
    "계약기간_1년이상": "contract_months",
    "시작일": "start_date",
    "종료일": "end_date",
    "상시근로자수": "regular_workers",
    "계속근로기간": "continuous_service_months",
    "단순노무여부": "is_simple_labor",
    "근로자성": "is_employee",
    "단시간여부": "is_part_time",
    "약정_소정근로": "agreed_scheduled_hours",
    "계약_유형": "domain",
    "소정근로시간": "weekly_scheduled_hours",
}


@lru_cache(maxsize=1)
def load_lab_cards() -> list[dict]:
    rows = load_yaml(CARDS_PATH) or []
    return [r for r in rows if isinstance(r, dict) and r.get("id")]


def select_cards(clause: str, limit: int = 2) -> list[dict]:
    """match_keywords 출현 수 상위 limit. 0점이면 빈 목록."""
    t = clause or ""
    scored = []
    for card in load_lab_cards():
        score = 0
        hits = []
        for kw in card.get("match_keywords") or []:
            if kw and kw in t:
                score += t.count(kw)
                hits.append(kw)
        if score > 0:
            scored.append((score, card, hits))
    scored.sort(key=lambda x: (-x[0], x[1].get("id") or ""))
    out = []
    for score, card, hits in scored[:limit]:
        row = dict(card)
        row["_match_score"] = score
        row["_match_hits"] = hits
        out.append(row)
    return out


def fact_value(facts: dict, label: str):
    key = FACT_KEY.get(label) or FACT_KEY.get(label.replace(" ", ""))
    if not key:
        # 느슨 매칭
        for name, k in FACT_KEY.items():
            if name in (label or "") or (label or "") in name:
                key = k
                break
    if not key:
        return None
    return facts.get(key)


def uses_facts_lines(card: dict, facts: dict) -> list[str]:
    lines = []
    for label in card.get("uses_facts") or []:
        val = fact_value(facts, label)
        if val is None:
            shown = "null"
        else:
            shown = str(val)
        lines.append(f"  - {label}: {shown}")
    return lines


def format_criteria_block(cards: list[dict], facts: dict) -> str:
    if not cards:
        return "(없음)"
    parts = []
    for card in cards:
        lines = [
            f"- id: {card.get('id')}",
            f"  title: {card.get('title')}",
            "  safe:",
        ]
        for s in card.get("safe") or []:
            lines.append(f"  - {s}")
        lines.append("  violation:")
        for s in card.get("violation") or []:
            lines.append(f"  - {s}")
        if not (card.get("violation") or []):
            lines.append("  - (없음)")
        lines.append("  check_if:")
        for s in card.get("check_if") or []:
            lines.append(f"  - {s}")
        if not (card.get("check_if") or []):
            lines.append("  - (없음)")
        lines.append("  uses_facts:")
        uf = uses_facts_lines(card, facts)
        lines.extend(uf if uf else ["  - (없음)"])
        parts.append("\n".join(lines))
    return "\n".join(parts)


def when_matches(rule: dict, clause: str) -> bool:
    t = clause or ""
    cues = rule.get("cues") or []
    if not cues:
        when = rule.get("when") or ""
        return bool(when and when in t)
    # 모든 cue 그룹이 적어도 하나는 맞아야 함(AND of ORs written as list of regexes — each must match)
    for cue in cues:
        if not re.search(cue, t):
            return False
    return True


def resolve_fact_labels(needs_fact: str) -> list[str]:
    """A.X needs_fact 문자열에서 카드 fact 라벨을 찾는다."""
    raw = (needs_fact or "").strip()
    if not raw:
        return []
    found = []
    for label in FACT_KEY:
        if label in raw:
            found.append(label)
    # 영문/키 직접
    for label, key in FACT_KEY.items():
        if key in raw and label not in found:
            found.append(label)
    return found


def needs_fact_available(needs_fact: str, facts: dict) -> bool:
    labels = resolve_fact_labels(needs_fact)
    if not labels:
        # 라벨을 못 풀면 키워드로 facts 값이 있는지 느슨히
        for key, val in (facts or {}).items():
            if val is None:
                continue
            if key in (needs_fact or ""):
                return True
        return False
    for label in labels:
        if fact_value(facts, label) is not None:
            return True
    return False


def _fact_matches_needs(fact: str, needs_fact: str, labels: set[str]) -> bool:
    fact = (fact or "").strip()
    if not fact:
        return False
    if fact in labels or fact in (needs_fact or ""):
        return True
    return any(fact in lb or lb in fact for lb in labels)


def is_blocking_fact(needs_fact: str, cards: list[dict] | None = None) -> bool:
    """needs_fact가 어떤 카드의 blocking_if.fact 와 맞는지(when 무관)."""
    labels = set(resolve_fact_labels(needs_fact))
    if not labels and needs_fact:
        labels = {needs_fact.strip()}
    pool = cards if cards is not None else load_lab_cards()
    for card in pool:
        for rule in card.get("blocking_if") or []:
            if _fact_matches_needs(rule.get("fact") or "", needs_fact or "", labels):
                return True
    return False


def blocking_triggered(needs_fact: str, clause: str, cards: list[dict] | None = None) -> bool:
    """needs_fact가 카드 blocking_if fact이고 when이 조항에 나타나면 True."""
    labels = set(resolve_fact_labels(needs_fact))
    if not labels and needs_fact:
        labels = {needs_fact.strip()}
    pool = cards if cards is not None else load_lab_cards()
    for card in pool:
        for rule in card.get("blocking_if") or []:
            if not _fact_matches_needs(rule.get("fact") or "", needs_fact or "", labels):
                continue
            if when_matches(rule, clause):
                return True
    return False
