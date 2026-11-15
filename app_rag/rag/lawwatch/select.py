# -*- coding: utf-8 -*-
"""날짜에 맞는 카드 버전 고르기."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from rag.lawwatch.versions_io import load_card_versions, sorted_versions

NOTE_UNKNOWN = "개정 전후 기준이 다를 수 있어요"
NOTE_NO_CONTRACT_DATE = "계약일을 찾지 못해 오늘 기준으로 봤어요"
NOTE_SCHEDULED = "계약기간 중 {date}부터 기준이 바뀌어요: {summary}"
NOTE_NEED_CHECK = "확인 필요"


def _parse_day(raw: str | None) -> date | None:
    if not raw:
        return None
    s = str(raw).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _today(today: str | date | None) -> date:
    if isinstance(today, date) and not isinstance(today, datetime):
        return today
    if today:
        d = _parse_day(str(today))
        if d:
            return d
    return date.today()


def _in_range(ver: dict, on: date) -> bool:
    start = _parse_day(ver.get("effective_from"))
    end = _parse_day(ver.get("effective_to"))
    if start and on < start:
        return False
    if end and on > end:
        return False
    if start is None:
        return False
    return True


def _active_on(versions: list[dict], on: date) -> dict | None:
    hit = [v for v in versions if _in_range(v, on)]
    if not hit:
        # 시행일 이전만 있으면 가장 이른 것 / 이후만 있으면 가장 늦은 것
        past = [v for v in versions if (_parse_day(v.get("effective_from")) or date.max) <= on]
        if past:
            past.sort(key=lambda v: _parse_day(v.get("effective_from")) or date.min)
            return past[-1]
        future = sorted(versions, key=lambda v: _parse_day(v.get("effective_from")) or date.max)
        return future[0] if future else None
    hit.sort(key=lambda v: _parse_day(v.get("effective_from")) or date.min)
    return hit[-1]


def _overlaps_period(ver: dict, start: date, end: date) -> bool:
    vs = _parse_day(ver.get("effective_from")) or date.min
    ve = _parse_day(ver.get("effective_to")) or date.max
    return not (ve < start or vs > end)


def _card_payload(ver: dict) -> dict:
    card = dict(ver.get("card") or {})
    card["_version"] = ver.get("version")
    card["_effective_from"] = ver.get("effective_from")
    card["_effective_to"] = ver.get("effective_to")
    card["_apply_rule"] = ver.get("apply_rule")
    return card


def select_versions(
    card_id: str,
    contract_date: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    today: str | date | None = None,
    *,
    current_card: dict | None = None,
) -> dict[str, Any]:
    """적용할 버전 목록과 안내 문구.

    버전 파일이 없으면 current_card(현행) 하나만 — 지금과 동일 동작.
    """
    today_d = _today(today)
    data = load_card_versions(card_id)
    notices: list[str] = []
    flags: dict[str, Any] = {"need_check": False, "date_missing": False}

    if not data or not (data.get("versions") or []):
        card = dict(current_card or {})
        if card and not card.get("id"):
            card["id"] = card_id
        return {
            "card_id": card_id,
            "versions": [{"version": None, "apply_rule": None, "card": card, "effective_from": None}] if card else [],
            "cards": [card] if card else [],
            "notices": notices,
            "flags": flags,
            "mode": "current_only",
        }

    versions = sorted_versions(card_id)
    if len(versions) == 1:
        ver = versions[0]
        return {
            "card_id": card_id,
            "versions": [ver],
            "cards": [_card_payload(ver)],
            "notices": notices,
            "flags": flags,
            "mode": "single",
        }

    # 대표 apply_rule: 최신 버전의 규칙(버전이 서로 다를 수 있으나 보통 동일)
    latest = versions[-1]
    rule = latest.get("apply_rule") or "unknown"
    # 계약기간 중 예정 개정 안내
    p0 = _parse_day(period_start)
    p1 = _parse_day(period_end)
    if p0 and p1:
        for ver in versions:
            ef = _parse_day(ver.get("effective_from"))
            if ef and p0 < ef <= p1 and ef > today_d:
                summary = (ver.get("summary") or ver.get("card", {}).get("title") or f"version {ver.get('version')}")
                notices.append(NOTE_SCHEDULED.format(date=ef.isoformat(), summary=summary))

    chosen: list[dict] = []

    if rule == "contract_date":
        cd = _parse_day(contract_date)
        if not cd:
            flags["date_missing"] = True
            notices.append(NOTE_NO_CONTRACT_DATE)
            cd = today_d
        ver = _active_on(versions, cd)
        if ver:
            chosen = [ver]

    elif rule == "in_force":
        ver = _active_on(versions, today_d)
        if ver:
            chosen = [ver]

    elif rule == "performance_period":
        start = _parse_day(period_start) or _parse_day(contract_date) or today_d
        end = _parse_day(period_end) or start
        if not _parse_day(period_start) and not _parse_day(contract_date):
            flags["date_missing"] = True
            notices.append(NOTE_NO_CONTRACT_DATE)
        hit = [v for v in versions if _overlaps_period(v, start, end)]
        if not hit:
            ver = _active_on(versions, start)
            hit = [ver] if ver else []
        chosen = hit

    else:  # unknown
        ver = _active_on(versions, today_d)
        cd = _parse_day(contract_date)
        if ver and cd:
            ef = _parse_day(ver.get("effective_from"))
            if ef and cd < ef:
                flags["need_check"] = True
                notices.append(NOTE_NEED_CHECK)
                notices.append(NOTE_UNKNOWN)
        if not cd:
            flags["date_missing"] = True
            notices.append(NOTE_NO_CONTRACT_DATE)
        if ver:
            chosen = [ver]

    # 개별 버전 apply_rule이 unknown인 경우도 확인
    for ver in chosen:
        if (ver.get("apply_rule") or "") == "unknown":
            cd = _parse_day(contract_date)
            ef = _parse_day(ver.get("effective_from"))
            if cd and ef and cd < ef:
                flags["need_check"] = True
                if NOTE_UNKNOWN not in notices:
                    notices.append(NOTE_NEED_CHECK)
                    notices.append(NOTE_UNKNOWN)

    return {
        "card_id": card_id,
        "versions": chosen,
        "cards": [_card_payload(v) for v in chosen],
        "notices": notices,
        "flags": flags,
        "mode": rule,
        "today": today_d.isoformat(),
        "contract_date": contract_date,
        "period_start": period_start,
        "period_end": period_end,
    }


def select_cards_for_clause(
    clause: str,
    *,
    domain: str = "LAB",
    limit: int = 2,
    contract_date: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    today: str | date | None = None,
) -> tuple[list[dict], list[str]]:
    """기존 select_cards와 같되, 버전 파일이 있으면 날짜에 맞는 카드 내용으로 교체."""
    from rag.criteria import select_cards

    base = select_cards(clause, limit=limit, domain=domain)
    notices: list[str] = []
    out: list[dict] = []
    for card in base:
        cid = card.get("id") or ""
        sel = select_versions(
            cid,
            contract_date=contract_date,
            period_start=period_start,
            period_end=period_end,
            today=today,
            current_card=card,
        )
        notices.extend(sel.get("notices") or [])
        cards = sel.get("cards") or [card]
        # 프롬프트에는 대표 1장(첫 버전). performance_period는 메타에 목록 보관
        chosen = dict(cards[0]) if cards else dict(card)
        for k in ("_match_score", "_match_hits"):
            if k in card:
                chosen[k] = card[k]
        if not chosen.get("id"):
            chosen["id"] = cid
        if len(cards) > 1:
            chosen["_period_versions"] = [
                {"version": c.get("_version"), "effective_from": c.get("_effective_from"), "effective_to": c.get("_effective_to")}
                for c in cards
            ]
        out.append(chosen)
    # 중복 안내 제거
    uniq = []
    for n in notices:
        if n not in uniq:
            uniq.append(n)
    return out, uniq
