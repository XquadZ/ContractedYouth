# -*- coding: utf-8 -*-
"""도메인별 기준 카드 로드·매칭. A.X/검색 설정과 무관."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from rag.paths import APP
from rag.yamlutil import load as load_yaml

CARDS_PATH_TUNED = {
    "LAB": APP / "criteria" / "LAB_cards.yaml",
    "LEASE": APP / "criteria" / "LEASE_cards.yaml",
    "LOAN": APP / "criteria" / "LOAN_cards.yaml",
}
CARDS_PATH_NEUTRAL = {
    "LAB": APP / "criteria" / "neutral" / "LAB_cards.yaml",
    "LEASE": APP / "criteria" / "neutral" / "LEASE_cards.yaml",
    "LOAN": APP / "criteria" / "neutral" / "LOAN_cards.yaml",
}
# 하위 호환: 기본은 tuned
CARDS_PATH = CARDS_PATH_TUNED
GENERAL_IDS = {"LAB-GENERAL", "LEASE-GENERAL", "LOAN-GENERAL"}


def _cards_path_map():
    try:
        from rag.settings import get_cards_version

        return CARDS_PATH_NEUTRAL if get_cards_version() == "neutral" else CARDS_PATH_TUNED
    except Exception:
        return CARDS_PATH_TUNED


def clear_cards_cache() -> None:
    load_domain_cards.cache_clear()

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
    "보증금": "deposit",
    "월세": "monthly_rent",
    "증액률": "rent_increase_rate",
    "원금": "principal",
    "이자율": "interest_rate",
    "지연이율": "delay_interest_rate",
}


@lru_cache(maxsize=32)
def _load_domain_cards_cached(domain: str, version: str) -> tuple:
    paths = CARDS_PATH_NEUTRAL if version == "neutral" else CARDS_PATH_TUNED
    path = paths.get(domain) or paths["LAB"]
    if not path.exists():
        return tuple()
    rows = load_yaml(path) or []
    return tuple(r for r in rows if isinstance(r, dict) and r.get("id"))


def load_domain_cards(domain: str = "LAB") -> list[dict]:
    try:
        from rag.settings import get_cards_version

        version = get_cards_version()
    except Exception:
        version = "tuned"
    return list(_load_domain_cards_cached(domain or "LAB", version))


def load_lab_cards() -> list[dict]:
    return load_domain_cards("LAB")


# 구 API 호환
load_domain_cards.cache_clear = _load_domain_cards_cached.cache_clear  # type: ignore[attr-defined]


def _general_excluded(clause: str, card: dict) -> bool:
    """GENERAL 카드: exclude_keywords가 있으면 해당 조항에는 쓰지 않음."""
    t = clause or ""
    for kw in card.get("exclude_keywords") or []:
        if kw and kw in t:
            return True
    return False


def select_cards(clause: str, limit: int = 2, domain: str = "LAB") -> list[dict]:
    """match_keywords 출현 수 상위 limit. 일반 카드는 다른 카드가 0점일 때만."""
    t = clause or ""
    domain = domain or "LAB"
    scored = []
    general = None
    for card in load_domain_cards(domain):
        cid = card.get("id") or ""
        if cid in GENERAL_IDS or cid.endswith("-GENERAL"):
            general = card
            continue
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
    if not out and general is not None and not _general_excluded(t, general):
        row = dict(general)
        row["_match_score"] = 0
        row["_match_hits"] = ["(general)"]
        out.append(row)
    return out


def fact_value(facts: dict, label: str):
    key = FACT_KEY.get(label) or FACT_KEY.get(label.replace(" ", ""))
    if not key:
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
        shown = "null" if val is None else str(val)
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
    for cue in cues:
        if not re.search(cue, t):
            return False
    return True


def resolve_fact_labels(needs_fact: str) -> list[str]:
    raw = (needs_fact or "").strip()
    if not raw:
        return []
    found = []
    for label in FACT_KEY:
        if label in raw:
            found.append(label)
    for label, key in FACT_KEY.items():
        if key in raw and label not in found:
            found.append(label)
    return found


def needs_fact_available(needs_fact: str, facts: dict) -> bool:
    labels = resolve_fact_labels(needs_fact)
    if not labels:
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


def _corpus_by_id() -> dict[str, dict]:
    try:
        from rag.corpus import load_corpus

        recs, _ = load_corpus()
        return {r["id"]: r for r in recs if r.get("id")}
    except Exception:
        return {}


def merge_hits_with_card_basis(hits: list[dict], cards: list[dict], *, max_extra: int = 3) -> list[dict]:
    """검색 상위 + 카드 basis(중복 제거, 최대 max_extra 추가). FIX_ROUND3 설계 변경."""
    out = list(hits or [])
    seen = {h.get("id") for h in out if h.get("id")}
    corpus = _corpus_by_id()
    added = 0
    for card in cards or []:
        for bid in card.get("basis") or []:
            if added >= max_extra:
                return out
            eid = bid if isinstance(bid, str) else (bid.get("id") if isinstance(bid, dict) else None)
            if not eid or eid in seen:
                continue
            rec = corpus.get(eid) or {}
            out.append(
                {
                    "id": eid,
                    "title": rec.get("title") or eid,
                    "doc_type": rec.get("doc_type") or ("법률" if str(eid).startswith("law:") else "자료"),
                    "text": rec.get("text") or "",
                    "score": 0.0,
                    "from_card_basis": True,
                }
            )
            seen.add(eid)
            added += 1
    return out
