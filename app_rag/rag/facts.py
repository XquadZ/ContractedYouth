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
    # 화면·마스킹 원문은 그대로 두고, 사실 추출용으로만 표 항목명 정규화
    t = _normalize_spaced_labels(text or "")
    facts = {
        "domain": guess_domain(t),
        "hourly_wage": _hourly_wage(t),
        "monthly_wage": _monthly_wage(t),
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
        "principal": None,
        "principals": [],
        "interest_rate": None,
        "interest_rate_basis": None,
        "interest_rates": [],
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
    _fill_principals(facts, t)
    _fill_interest_rate(facts, t)
    _fill_weekly_hours(facts, t)
    _fill_contract_months(facts)
    _fill_apply_year(facts)
    _fill_hourly_from_monthly(facts, t)
    # 약정 소정 = 주 소정과 동일하게 적을 수 있으므로 복사(추측 없이 값이 있을 때만)
    if facts.get("weekly_scheduled_hours") is not None:
        facts["agreed_scheduled_hours"] = facts["weekly_scheduled_hours"]
    return facts


# 표 서식에서 한 글자씩 띄어 쓴 항목명(사실 추출 전용). 목록에 있는 것만 붙인다.
_TABLE_LABELS_COMPACT = (
    "이자",
    "이율",
    "성명",
    "주소",
    "차용금액",
    "상환방법",
    "상환일자",
    "차용기간",
    "변제기",
    "원금",
    "월급",
    "시급",
    "보증금",
    "차임",
    "임금",
)


def _normalize_spaced_labels(text: str) -> str:
    """이 자 → 이자 등. 한글 1글자씩 공백 하나로 띄운 표 항목명만 붙인다."""
    t = text or ""
    for label in sorted(_TABLE_LABELS_COMPACT, key=len, reverse=True):
        spaced = " ".join(label)
        if spaced in t:
            t = t.replace(spaced, label)
    return t


def _paid_weekly_holiday_hours(weekly_scheduled: float) -> float:
    """1주 소정근로시간 기준 주휴시간. 15시간 미만이면 0."""
    if weekly_scheduled < 15:
        return 0.0
    return min(8.0, weekly_scheduled / 40.0 * 8.0)


def _monthly_excludes_holiday_pay(text: str) -> bool:
    """월급에 주휴수당이 빠졌다고 명시된 경우."""
    return bool(
        re.search(
            r"주휴수당\s*(?:별도|미포함|제외)|주휴\s*(?:수당)?\s*(?:별도\s*지급|포함하지\s*않)",
            text or "",
        )
    )


def _fill_hourly_from_monthly(facts: dict, text: str = "") -> None:
    """월급 + 1주 소정근로시간이 있으면 시급 환산. 이미 시급이 있으면 건드리지 않음."""
    if facts.get("hourly_wage") is not None:
        return
    monthly = facts.get("monthly_wage")
    weekly = facts.get("weekly_scheduled_hours")
    if monthly is None or weekly is None:
        return
    try:
        weekly_f = float(weekly)
        monthly_f = float(monthly)
    except (TypeError, ValueError):
        return
    if weekly_f <= 0:
        return
    # 월 환산시간 = (1주 소정 + 주휴) × (365/7/12), 소수 첫째 자리 반올림
    holiday = 0.0
    holiday_note = ""
    if _monthly_excludes_holiday_pay(text):
        holiday_note = "주휴수당 별도(주휴시간 미가산)"
        m = re.search(
            r".{0,20}주휴수당\s*(?:별도|미포함|제외).{0,20}|.{0,20}주휴\s*(?:수당)?\s*(?:별도\s*지급|포함하지\s*않).{0,20}",
            text or "",
        ) or re.search(r"주휴수당.{0,12}", text or "")
        if m:
            facts["holiday_pay_separate_quote"] = m.group(0).strip()
    else:
        holiday = _paid_weekly_holiday_hours(weekly_f)
    factor = 365.0 / 7.0 / 12.0  # ≈ 4.345
    hours_per_month = round((weekly_f + holiday) * factor)
    if hours_per_month <= 0:
        return
    hourly = monthly_f / hours_per_month
    facts["hourly_wage"] = int(round(hourly))
    facts["hourly_from_monthly"] = True
    if holiday > 0:
        formula = f"({_fmt_num(weekly_f)} + 주휴 {_fmt_num(holiday)}) × 4.345 = {hours_per_month}시간"
    else:
        formula = f"({_fmt_num(weekly_f)} + 주휴 0) × 4.345 = {hours_per_month}시간"
        if holiday_note:
            formula += f" · {holiday_note}"
    formula += f" | 월급÷월환산→시급 {facts['hourly_wage']}"
    prev = facts.get("weekly_hours_formula") or ""
    facts["weekly_hours_formula"] = (prev + " | " + formula).strip(" |") if prev else formula


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


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


def _hourly_wage(text: str):
    """시급·시간급·시간당·1시간당·시간 단위 임금."""
    patterns = [
        rf"시급(?:은|을|:)?\s*{NUM}\s*원",
        rf"시간급(?:은|을|:)?\s*{NUM}\s*원",
        rf"시간당\s*{NUM}\s*원",
        rf"1시간당\s*{NUM}\s*원",
        rf"시간\s*단위\s*임금(?:은|을|:)?\s*{NUM}\s*원",
        rf"임금\s*\(\s*시간급\s*\)\s*[:：]?\s*{NUM}\s*원",
        rf"임금(?:은|을|:)?\s*시간당\s*{NUM}\s*원",
        rf"기본급\s*[:：]?\s*시간당\s*{NUM}\s*원",
        rf"(?:시급|시간급)\s*[:：]\s*{NUM}\s*원",
    ]
    for pat in patterns:
        val = _won(pat, text)
        if val is not None:
            return val
    return None


def _monthly_wage(text: str):
    patterns = [
        rf"(?:월급|월\s*급여|월\s*임금)(?:은|을|:)?\s*{NUM}\s*원",
        rf"월\s*{NUM}\s*원(?:의)?\s*(?:월급|급여|임금)",
        rf"(?:월급|월급여)\s*[:：]\s*{NUM}\s*원",
    ]
    for pat in patterns:
        val = _won(pat, text)
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
    # 휴게 12:00~13:00 / 휴게시간 12시~13시
    m = re.search(
        r"휴게(?:시간)?(?:은|:)?\s*([01]?\d|2[0-3])\s*:\s*([0-5]\d)\s*[~～\-]\s*([01]?\d|2[0-3])\s*:\s*([0-5]\d)",
        text or "",
    )
    if m:
        start = _hhmm_to_hours(m.group(1), m.group(2))
        end = _hhmm_to_hours(m.group(3), m.group(4))
        if end <= start:
            end += 24.0
        return int(round((end - start) * 60))
    m = re.search(
        r"휴게(?:시간)?(?:은|:)?\s*([01]?\d|2[0-3])\s*시(?:\s*([0-5]?\d)\s*분)?\s*[~～\-]\s*([01]?\d|2[0-3])\s*시(?:\s*([0-5]?\d)\s*분)?",
        text or "",
    )
    if m:
        start = _hhmm_to_hours(m.group(1), m.group(2) or "0")
        end = _hhmm_to_hours(m.group(3), m.group(4) or "0")
        if end <= start:
            end += 24.0
        return int(round((end - start) * 60))
    return None


def _rate(raw: str | None):
    if raw is None:
        return None
    val = _to_int(raw)
    if val is None:
        return None
    return float(val) / 100.0


_HANGUL_DIGITS = {
    "영": 0,
    "공": 0,
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "오": 5,
    "육": 6,
    "칠": 7,
    "팔": 8,
    "구": 9,
}
_HANGUL_SMALL = {"십": 10, "백": 100, "천": 1000}
_HANGUL_BIG = {"만": 10_000, "억": 100_000_000}


def hangul_amount_to_int(text: str) -> int | None:
    """한글 금액 → 정수. 예: 일십만원→100000, 이천만원→20000000, 삼백오십만원→3500000."""
    if not text:
        return None
    s = re.sub(r"\s+", "", text)
    s = s.replace("원정", "").replace("원", "").replace("금", "")
    if not s or not re.fullmatch(r"[영공일이삼사오육칠팔구십백천만억]+", s):
        return None
    total = 0
    big_chunk = 0
    small = 0
    num = 0
    for ch in s:
        if ch in _HANGUL_DIGITS:
            num = _HANGUL_DIGITS[ch]
        elif ch in _HANGUL_SMALL:
            unit = _HANGUL_SMALL[ch]
            small += (num if num else 1) * unit
            num = 0
        elif ch in _HANGUL_BIG:
            unit = _HANGUL_BIG[ch]
            chunk = small + num
            if chunk == 0:
                chunk = 1
            big_chunk += chunk
            total += big_chunk * unit
            big_chunk = 0
            small = 0
            num = 0
        else:
            return None
    total += big_chunk + small + num
    return total if total > 0 else None


def _parse_amount_chunk(chunk: str) -> int | None:
    """금액 조각에서 아라비아(₩·￦·원) 우선, 없으면 한글 금액."""
    if not chunk:
        return None
    pm = re.search(rf"[₩￦]\s*{NUM}", chunk)
    if pm:
        return _to_int(pm.group(1))
    pm = re.search(rf"({NUM})\s*원", chunk)
    if pm:
        return _to_int(pm.group(1))
    # 일금·금 접두만 잡지 않도록 단위(십·백·천·만·억)가 있는 한글 금액만
    hm = re.search(r"([가-힣]*[십백천만억][가-힣]*)", chunk)
    if hm:
        return hangul_amount_to_int(hm.group(1))
    return None


def _principal_hangul(text: str) -> int | None:
    # 일금 이천만원(₩20,000,000) / 한글금액 원정
    patterns = (
        rf"(?:일금|원금|차용금|대여금|빌린\s*돈)\s*[가-힣]+\s*(?:원정|원)?\s*\(\s*[₩￦]?\s*{NUM}\s*\)",
        rf"(?:일금|원금|차용금|대여금|빌린\s*돈)\s*[가-힣]+\s*(?:원정|원)",
        rf"금\s*[가-힣]+\s*원정(?:\s*\(\s*[₩￦]?\s*{NUM}\s*\))?",
        rf"차용금액\s*[가-힣]+\s*(?:원정|원)?(?:\s*\(\s*[₩￦]?\s*{NUM}\s*\))?",
    )
    for pat in patterns:
        m = re.search(pat, text or "")
        if m:
            val = _parse_amount_chunk(m.group(0))
            if val is not None:
                return val
    return None


_INTEREST_SUBJ = r"(?:이자율|연이율|약정이율|이율|금리|이자)"
_PCT = rf"(?:%|퍼\s*센\s*트)"


def _page_at(text: str, idx: int) -> int | None:
    """쪽 추정: '금전차용증서' 헤더 또는 폼피드 기준."""
    if not text or idx < 0:
        return None
    if "\f" in text:
        return text[:idx].count("\f") + 1
    starts = [m.start() for m in re.finditer(r"(?m)^금전차용증서\s*$", text)]
    if not starts:
        return None
    page = 1
    for i, s in enumerate(starts, start=1):
        if s <= idx:
            page = i
        else:
            break
    return page


def _snippet(text: str, start: int, end: int, pad: int = 40) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return re.sub(r"\s+", " ", (text[a:b] or "").strip())


def _fill_principals(facts: dict, text: str) -> None:
    t = text or ""
    found: list[dict] = []
    seen: set[int] = set()

    def _add(val: int | None, start: int, end: int) -> None:
        if val is None or val <= 0 or val in seen:
            return
        seen.add(int(val))
        found.append(
            {
                "value": int(val),
                "snippet": _snippet(t, start, end),
                "page": _page_at(t, start),
            }
        )

    for m in re.finditer(rf"(?:원금|차용금|대여금)(?:은|을|:)?\s*{NUM}\s*원", t):
        _add(_to_int(m.group(1)), m.start(), m.end())
    for m in re.finditer(
        rf"(?:일금|원금|차용금(?!액)|대여금|빌린\s*돈|(?<![가-힣])금)\s*[가-힣0-9,₩￦\s()]{{2,80}}?\s*(?:을|를)?\s*(?:차용|대여|빌)",
        t,
    ):
        _add(_parse_amount_chunk(m.group(0)), m.start(), m.end())
    for m in re.finditer(
        rf"(?:일금|원금|차용금|대여금|빌린\s*돈|차용금액)\s*[가-힣]+\s*(?:원정|원)?(?:\s*\(\s*[₩￦]?\s*{NUM}\s*\))?",
        t,
    ):
        _add(_parse_amount_chunk(m.group(0)), m.start(), m.end())

    facts["principals"] = found
    if found:
        facts["principal"] = max(x["value"] for x in found)
    else:
        facts["principal"] = None


def _fill_interest_rate(facts: dict, text: str) -> None:
    t = text or ""
    rates = _collect_interest_rates(t)
    facts["interest_rates"] = rates
    if rates:
        best = max(rates, key=lambda r: float(r.get("rate") or 0.0))
        facts["interest_rate"] = best.get("rate")
        facts["interest_rate_basis"] = best.get("basis")
        if best.get("note"):
            facts["interest_rate_note"] = best["note"]
    else:
        facts["interest_rate"] = None
        facts["interest_rate_basis"] = None
    if facts.get("principal") is None:
        p = _principal_from_loan_sentence(t)
        if p is not None:
            facts["principal"] = p


def _extract_interest_rate(text: str) -> tuple[float | None, str | None, str | None]:
    rates = _collect_interest_rates(text or "")
    if not rates:
        return None, None, None
    best = max(rates, key=lambda r: float(r.get("rate") or 0.0))
    return best.get("rate"), best.get("basis"), best.get("note")


def _collect_interest_rates(text: str) -> list[dict]:
    t = _normalize_spaced_labels(text or "")
    out: list[dict] = []

    def _push(rate: float | None, basis: str, start: int, end: int, note: str | None = None) -> None:
        if rate is None:
            return
        # 비정상적으로 큰 값(금액 오파싱) 제외: 연 이율로 10(1000%) 초과면 무시
        if rate > 10:
            return
        item = {
            "rate": rate,
            "basis": basis,
            "snippet": _snippet(t, start, end),
            "page": _page_at(t, start),
            "_pos": start,
        }
        if note:
            item["note"] = note
        for prev in out:
            if prev.get("rate") == rate and prev.get("basis") == basis and abs((prev.get("_pos") or 0) - start) < 20:
                return
        out.append(item)

    for m in re.finditer(
        rf"{_INTEREST_SUBJ}\s*[은는이가를:]?\s*[:：|｜]?\s*(월|일)\s*{NUM}\s*{_PCT}\s*"
        rf"\(\s*연\s*{NUM}\s*{_PCT}\s*\)",
        t,
    ):
        period, raw_p, raw_y = m.group(1), m.group(2), m.group(3)
        period_rate = _rate(raw_p)
        year_rate = _rate(raw_y)
        if period_rate is None or year_rate is None:
            continue
        converted = period_rate * (12.0 if period == "월" else 365.0)
        chosen = max(converted, year_rate)
        note = None
        if abs(converted - year_rate) > 1e-9:
            note = f"월/일 환산 {converted:.4f} vs 표기 연 {year_rate:.4f} → 큰 값 사용"
        basis = "year" if abs(chosen - year_rate) <= abs(chosen - converted) else ("month" if period == "월" else "day")
        _push(chosen, basis, m.start(), m.end(), note)

    for m in re.finditer(
        rf"{_INTEREST_SUBJ}\s*[은는이가를:]?\s*[:：|｜]?\s*(?:\n\s*){{0,2}}(?:연\s*)?{NUM}\s*{_PCT}",
        t,
    ):
        _push(_rate(m.group(1)), "year", m.start(), m.end())

    for m in re.finditer(rf"연\s*{NUM}\s*{_PCT}\s*의\s*이자", t):
        _push(_rate(m.group(1)), "year", m.start(), m.end())

    for m in re.finditer(
        rf"{_INTEREST_SUBJ}\s*[은는이가를:]?\s*[:：|｜]?\s*(월|일)\s*{NUM}\s*{_PCT}",
        t,
    ):
        period, raw = m.group(1), m.group(2)
        period_rate = _rate(raw)
        if period_rate is None:
            continue
        if period == "월":
            _push(period_rate * 12.0, "month", m.start(), m.end())
        else:
            _push(period_rate * 365.0, "day", m.start(), m.end())
    for m in re.finditer(rf"(월|일)\s*{NUM}\s*{_PCT}\s*(?:의\s*)?이자", t):
        period, raw = m.group(1), m.group(2)
        period_rate = _rate(raw)
        if period_rate is None:
            continue
        if period == "월":
            _push(period_rate * 12.0, "month", m.start(), m.end())
        else:
            _push(period_rate * 365.0, "day", m.start(), m.end())

    for item in _interest_from_amount_all(t):
        _push(item["rate"], "amount", item["start"], item["end"])

    for item in out:
        item.pop("_pos", None)
    return out


def _principal_from_loan_sentence(text: str) -> int | None:
    m = re.search(
        rf"(?:일금|원금|차용금(?!액)|대여금|빌린\s*돈|(?<![가-힣])금)\s*([가-힣0-9,₩￦\s()]+?)\s*(?:을|를)?\s*(?:차용|대여|빌)",
        text or "",
    )
    if not m:
        return _principal_hangul(text)
    return _parse_amount_chunk(m.group(0))


def _interest_from_amount(text: str) -> float | None:
    items = _interest_from_amount_all(text or "")
    if not items:
        return None
    return max(x["rate"] for x in items)


def _interest_from_amount_all(text: str) -> list[dict]:
    t = text or ""
    period_map = {"매월": 12, "매달": 12, "매주": 52, "매년": 1}
    out: list[dict] = []
    patterns = (
        rf"(매월|매달|매주|매년)\s*([가-힣]+?|{NUM})\s*원?\s*씩\s*(?:의\s*)?이자",
        rf"(매월|매달|매주|매년)\s*([가-힣]+?|{NUM})\s*원\s*(?:의\s*)?이자",
    )
    for pat in patterns:
        for m in re.finditer(pat, t):
            # 같은 줄(조항) 안 원금을 우선 — 표의 다른 차용금액과 섞지 않음
            line_start = t.rfind("\n", 0, m.start()) + 1
            window = t[line_start : m.end()]
            principal = _won(rf"(?:원금|차용금|대여금|빌린\s*돈)(?:은|을|:)?\s*{NUM}\s*원", window)
            if principal is None:
                principal = _principal_from_loan_sentence(window) or _principal_hangul(window)
            if not principal or principal <= 0:
                continue
            per = period_map[m.group(1)]
            amt_raw = m.group(2)
            amt = _to_int(amt_raw) if re.search(r"\d", amt_raw) else hangul_amount_to_int(amt_raw)
            if not amt or amt <= 0:
                continue
            rate = (amt * per) / float(principal)
            out.append({"rate": rate, "start": line_start, "end": m.end(), "principal": principal})
    return out


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
        "principals": "원금 목록",
        "interest_rate": "이자율",
        "interest_rate_basis": "이자율 산출근거",
        "interest_rates": "이자율 목록",
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
