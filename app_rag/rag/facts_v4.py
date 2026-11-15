# -*- coding: utf-8 -*-
"""계약서 전체에서 사실표만 뽑는다. 정규식. 추측하지 않는다."""
from __future__ import annotations

import re

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
        "work_days_per_week": _to_int(_first(rf"주\s*{NUM}\s*일", t)),
        "work_hours_per_day": _to_int(_first(rf"(?:1일|일)\s*{NUM}\s*시간", t) or _first(rf"{NUM}\s*시간\s*근무", t)),
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
    }
    facts.update(extract_dates(t))
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
        "probation_months": "수습 기간(개월)",
        "probation_cut_rate": "수습 감액률",
        "contract_period": "계약 기간",
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
