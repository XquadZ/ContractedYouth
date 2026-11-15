# -*- coding: utf-8 -*-
"""계약서 전체에서 사실표만 뽑는다. 정규식. 추측하지 않는다."""
from __future__ import annotations

import re
from datetime import date

from rag.dates import extract_dates

NUM = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)"


def _to_int(raw: str | None):
    if raw is None:
        return None
    s = raw.replace(",", "")
    try:
        if "." in s:
            val = float(s)
            return int(val) if val.is_integer() else val
        return int(s)
    except ValueError:
        return None


def _first(pattern: str, text: str, flags=0):
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


def _won(pattern: str, text: str):
    raw = _first(pattern, text)
    return _to_int(raw) if raw else None


def extract_facts(text: str) -> dict:
    t = text or ""
    facts = {
        "domain": guess_domain(t),
        "hourly_wage": _won(rf"시급(?:은|을|:)?\s*{NUM}\s*원", t),
        "monthly_wage": _won(rf"(?:월급|월\s*급여|월\s*임금)(?:은|을|:)?\s*{NUM}\s*원", t),
        "work_days_per_week": _work_days_per_week(t),
        "work_hours_per_day": _work_hours_per_day(t),
        "break_minutes": _break_minutes(t),
        "probation_months": _to_int(_first(rf"수습(?:\s*기간)?(?:은|:)?\s*{NUM}\s*(?:개월|달)", t)),
        "probation_cut_rate": _rate(_first(rf"수습.{{0,12}}(?:감액|감급|최저임금).{{0,12}}{NUM}\s*%", t)),
        "contract_period": _period(t, r"근로(?:개시일|계약기간|기간)"),
        "deposit": _won(rf"(?:임차)?보증금(?:은|을|:)?\s*{NUM}\s*원", t),
        "down_payment": _won(rf"계약금(?:은|을|:)?\s*{NUM}\s*원", t),
        "balance": _won(rf"잔금(?:은|을|:)?\s*{NUM}\s*원", t),
        "monthly_rent": _won(rf"(?:월세|월\s*차임|차임)(?:은|을|:)?\s*{NUM}\s*원", t),
        "maintenance_fee": _won(rf"관리비(?:은|는|를|:)?\s*{NUM}\s*원", t),
        "lease_period": _period(t, r"임대차(?:기간)?"),
        "rent_increase_rate": _rate(_first(rf"(?:증액|인상).{{0,12}}{NUM}\s*%", t)),
        "principal": _won(rf"(?:원금|차용금|대여금)(?:은|을|:)?\s*{NUM}\s*원", t),
        "interest_rate": _rate(_first(rf"(?:이자(?:율)?|연이율)(?:은|:)?\s*(?:연\s*)?{NUM}\s*%", t)),
        "delay_interest_rate": _rate(_first(rf"(?:지연(?:손해금|이자)|연체이자)(?:율|은|:)?\s*(?:연\s*)?{NUM}\s*%", t)),
        "repay_date": _date(_first(r"변제기(?:일)?(?:은|:)?\s*(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)", t)),
        # 보강 필드 — 못 뽑으면 null
        "regular_workers": _regular_workers(t),
        "weekly_scheduled_hours": None,
        "weekly_hours_formula": None,
        "contract_months": None,
        "apply_year": None,
        "continuous_service_months": None,
        "is_simple_labor": None,
        "is_employee": None,
        "is_part_time": None,
        "agreed_scheduled_hours": None,
    }
    facts.update(extract_dates(t))
    _fill_weekly_hours(facts, t)
    _fill_contract_months(facts)
    _fill_apply_year(facts)
    # 약정 소정 = 주 소정과 동일하게 적을 수 있으면 복사(추측 없이 값이 있을 때만)
    if facts.get("weekly_scheduled_hours") is not None:
        facts["agreed_scheduled_hours"] = facts["weekly_scheduled_hours"]
    return facts


def guess_domain(text: str) -> str:
    t = text or ""
    scores = {
        "LAB": len(re.findall(r"근로|시급|월급|알바|휴게|해고|주휴|연차", t)),
        "LEASE": len(re.findall(r"임대|임차|보증금|월세|전입|차임|원상회복", t)),
        "LOAN": len(re.findall(r"차용|원금|이자|변제|대여금|연체이자", t)),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "LAB"


def _work_days_per_week(text: str):
    n = _to_int(_first(rf"주\s*{NUM}\s*일", text))
    if n is not None:
        return n
    # 월~금 / 월요일~금요일 등 (주 5일)
    if re.search(r"(?:매주\s*)?(?:월|월요일)\s*[~～\-]\s*(?:금|금요일)", text):
        return 5
    if re.search(r"(?:매주\s*)?(?:월|월요일)\s*[~～\-]\s*(?:토|토요일)", text):
        return 6
    return None


def _hhmm_to_hours(h: str, m: str) -> float:
    return int(h) + int(m) / 60.0


def _work_hours_per_day(text: str):
    n = _to_int(_first(rf"(?:1일|일)\s*{NUM}\s*시간", text) or _first(rf"{NUM}\s*시간\s*근무", text))
    if n is not None:
        return n
    # 13:00~17:30 / 22:00-07:00 (야간 익일 허용)
    m = re.search(
        r"(?<!\d)([01]?\d|2[0-3])\s*:\s*([0-5]\d)\s*[~～\-]\s*([01]?\d|2[0-3])\s*:\s*([0-5]\d)",
        text,
    )
    if not m:
        return None
    start = _hhmm_to_hours(m.group(1), m.group(2))
    end = _hhmm_to_hours(m.group(3), m.group(4))
    if end <= start:
        end += 24.0
    hours = end - start
    return int(hours) if float(hours).is_integer() else round(hours, 2)


def _regular_workers(text: str):
    patterns = [
        rf"상시\s*근로자\s*수\s*[:：]?\s*{NUM}\s*명",
        rf"상시근로자\s*수\s*[:：]?\s*{NUM}\s*명",
        rf"상시\s*{NUM}\s*명",
        rf"근로자\s*{NUM}\s*인",
        rf"상시\s*근로자\s*{NUM}\s*명",
    ]
    for pat in patterns:
        val = _to_int(_first(pat, text))
        if val is not None:
            return val
    return None


def _fill_weekly_hours(facts: dict, text: str) -> None:
    # 명시 "주 N시간"
    explicit = _to_int(_first(rf"주\s*{NUM}\s*시간", text))
    if explicit is not None:
        facts["weekly_scheduled_hours"] = explicit
        facts["weekly_hours_formula"] = f"주 {explicit}시간(명시)"
        return
    days = facts.get("work_days_per_week")
    hours = facts.get("work_hours_per_day")
    brk = facts.get("break_minutes")
    if days is None or hours is None:
        return
    # 휴게를 모르면 일 시간을 그대로 씀(추측으로 휴게를 넣지 않음)
    if brk is None:
        weekly = days * hours
        facts["weekly_scheduled_hours"] = weekly if isinstance(weekly, (int, float)) else None
        facts["weekly_hours_formula"] = f"{days}일 × {hours}시간(휴게 null)"
        return
    day_net = hours - (brk / 60.0)
    if day_net < 0:
        return
    weekly = days * day_net
    facts["weekly_scheduled_hours"] = int(weekly) if float(weekly).is_integer() else round(weekly, 2)
    facts["weekly_hours_formula"] = f"{days}일 × ({hours}시간 − 휴게{brk}분)"


def _fill_contract_months(facts: dict) -> None:
    start = facts.get("start_date")
    end = facts.get("end_date")
    if not start:
        # contract_period dict
        cp = facts.get("contract_period") or {}
        start = cp.get("start")
        end = end or cp.get("end")
    if not start or not end:
        facts["contract_months"] = None
        return
    try:
        y1, m1, d1 = [int(x) for x in start.split("-")]
        y2, m2, d2 = [int(x) for x in end.split("-")]
        a = date(y1, m1, d1)
        b = date(y2, m2, d2)
        months = (b.year - a.year) * 12 + (b.month - a.month)
        if b.day < a.day:
            months -= 1
        facts["contract_months"] = max(months, 0)
    except Exception:
        facts["contract_months"] = None


def _fill_apply_year(facts: dict) -> None:
    start = facts.get("start_date")
    if not start:
        cp = facts.get("contract_period") or {}
        start = cp.get("start")
    if start and len(start) >= 4 and start[:4].isdigit():
        facts["apply_year"] = int(start[:4])
    else:
        facts["apply_year"] = None


def _break_minutes(text: str):
    if re.search(r"휴게(?:시간)?(?:은|를)?\s*(?:없|두지\s*않|없는\s*것)", text):
        return 0
    mins = _to_int(_first(rf"휴게(?:시간)?(?:은|:)?\s*{NUM}\s*분", text))
    if mins is not None:
        return mins
    hours = _to_int(_first(rf"휴게(?:시간)?(?:은|:)?\s*{NUM}\s*시간", text))
    if hours is not None:
        return int(hours * 60)
    return None


def _rate(raw: str | None):
    if raw is None:
        return None
    val = _to_int(raw)
    if val is None:
        return None
    return float(val) / 100.0


def _period(text: str, head: str):
    match = re.search(
        rf"{head}[^.\n]{{0,40}}(\d{{4}}\s*년\s*\d{{1,2}}\s*월\s*\d{{1,2}}\s*일).{{0,20}}(\d{{4}}\s*년\s*\d{{1,2}}\s*월\s*\d{{1,2}}\s*일)",
        text,
    )
    if not match:
        match = re.search(
            r"(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일).{0,8}부터.{0,8}(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)",
            text,
        )
    if not match:
        return None
    return {"start": _date(match.group(1)), "end": _date(match.group(2))}


def _date(raw: str | None):
    if not raw:
        return None
    match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", raw)
    if not match:
        return None
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def facts_for_prompt(facts: dict) -> str:
    labels = {
        "domain": "계약 유형",
        "hourly_wage": "시급(원)",
        "monthly_wage": "월급(원)",
        "work_days_per_week": "주 근로일",
        "work_hours_per_day": "일 근로시간",
        "break_minutes": "휴게(분)",
        "weekly_scheduled_hours": "1주 소정근로시간",
        "weekly_hours_formula": "1주 시간 계산식",
        "regular_workers": "상시근로자수",
        "probation_months": "수습 기간(개월)",
        "probation_cut_rate": "수습 감액률",
        "contract_period": "계약 기간",
        "contract_months": "계약기간(개월)",
        "apply_year": "적용연도",
        "deposit": "보증금(원)",
        "down_payment": "계약금(원)",
        "balance": "잔금(원)",
        "monthly_rent": "월세(원)",
        "maintenance_fee": "관리비(원)",
        "lease_period": "임대차 기간",
        "rent_increase_rate": "증액률",
        "principal": "원금(원)",
        "interest_rate": "이자율",
        "delay_interest_rate": "지연 이율",
        "repay_date": "변제기",
        "start_date": "시작일",
        "end_date": "종료일",
        "date_source": "날짜 출처 문장",
        "date_missing": "날짜 없음",
        "date_invalid": "없는 날짜",
    }
    lines = []
    for key, label in labels.items():
        val = facts.get(key)
        if val is None:
            shown = "null"
        elif isinstance(val, dict):
            shown = f"{val.get('start')} ~ {val.get('end')}"
        else:
            shown = str(val)
        lines.append(f"- {label}: {shown}")
    return "\n".join(lines)
