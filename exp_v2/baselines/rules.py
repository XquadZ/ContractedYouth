# -*- coding: utf-8 -*-
"""T3 numeric 규칙 기준선.

휴게는 카탈로그 break_rule의 work_hours_gt(초과)를 쓰지 않는다.
제54조 문구에 맞추어 근로시간 4시간 이상이면 30분, 8시간 이상이면 1시간으로 판정한다.
월급 환산은 (주당 근로시간 + 주휴 8시간) * 365 / 7 / 12 이다. 주 40시간이면 약 208.57시간.
판정 불가이면 None 을 반환하고 채점에서는 N/A 로 센다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CAT_PATH = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\data_contract\catalog\catalog_v0.2.json")
TARGET_CHECKS = {"L-T01", "L-T02", "L-T05", "L-T06", "H-T01", "H-T03", "H-T04", "D-T01"}


def load_params(path: Path = CAT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["params"]


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _hourly_min(params: dict, text: str) -> int:
    years = [int(y) for y in re.findall(r"(20\d{2})\s*년", text)]
    table = {int(k): int(v) for k, v in params["min_wage_hourly"].items()}
    if len(years) == 1 and years[0] in table:
        return table[years[0]]
    return table[max(table)]


def judge_l_t01(text: str, params: dict):
    floor = _hourly_min(params, text)
    hourly = []
    for match in re.finditer(r"(?:시급|시간당)\s*(?:은|를|을|:)?\s*([\d,]{3,})\s*원", text):
        hourly.append(_num(match.group(1)))
    day = re.search(r"일급은\s*([\d,]+)\s*원", text)
    hours = re.search(r"1일\s*(\d+(?:\.\d+)?)\s*시간", text)
    if day and hours:
        hourly.append(_num(day.group(1)) / float(hours.group(1)))
    month = re.search(r"월\s*기본급은\s*([\d,]+)\s*원", text)
    week = re.search(r"주\s*(\d+(?:\.\d+)?)\s*시간", text)
    if month and week:
        weekly = float(week.group(1))
        holiday = weekly / 5.0 if "주휴" in text else 0.0
        monthly_hours = (weekly + holiday) * 365.0 / 7.0 / 12.0
        if monthly_hours > 0:
            hourly.append(_num(month.group(1)) / monthly_hours)
    if not hourly:
        return None
    return any(v < floor for v in hourly)


def judge_l_t02(text: str, params: dict):
    if "수습" not in text:
        return None
    if re.search(r"수습기간은 두지 않|별도의 수습기간은 두지", text):
        return False
    if re.search(r"동일하게 지급|전액을 지급", text):
        return False
    cut = params["probation_cut"]
    max_rate = float(cut["max_rate"])
    max_months = float(cut["max_months"])
    min_years = float(cut["min_contract_years"])
    risky = False
    seen = False
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        seen = True
        pay = float(match.group(1)) / 100.0
        if (1.0 - pay) > max_rate + 1e-9:
            risky = True
    months = re.search(r"수습기간\s*(\d+(?:\.\d+)?)\s*개월", text)
    if months:
        seen = True
        if float(months.group(1)) > max_months:
            risky = True
    contract = re.search(r"근로계약기간은\s*(\d+(?:\.\d+)?)\s*개월", text)
    if contract:
        seen = True
        if float(contract.group(1)) < min_years * 12:
            risky = True
    floor = _hourly_min(params, text)
    for match in re.finditer(r"시급\s*([\d,]{3,})\s*원", text):
        seen = True
        if _num(match.group(1)) < floor * (1.0 - max_rate):
            risky = True
    if not seen:
        return None
    return risky


def _break_minutes(text: str):
    if re.search(r"휴게시간(?:은|을|를)?\s*없", text):
        return 0
    match = re.search(r"휴게시간(?:은|을|를|:)?\s*(\d+(?:\.\d+)?)\s*(분|시간)", text)
    if not match:
        return None
    value = float(match.group(1))
    return int(value * 60) if match.group(2) == "시간" else int(value)


def _work_hours(text: str, break_min):
    explicit = re.search(r"1일(?:\s*근로시간(?:은)?)?\s*(\d+(?:\.\d+)?)\s*시간", text)
    if explicit and "휴게" not in explicit.group(0):
        return float(explicit.group(1))
    paren = re.search(r"\((\d+(?:\.\d+)?)\s*시간(?:\s*(\d+)\s*분)?\)", text)
    if paren:
        hours = float(paren.group(1))
        if paren.group(2):
            hours += int(paren.group(2)) / 60.0
        return hours
    clock = re.search(r"(\d{1,2}):(\d{2})\s*부터\s*(\d{1,2}):(\d{2})\s*까지", text)
    if clock:
        start = int(clock.group(1)) * 60 + int(clock.group(2))
        end = int(clock.group(3)) * 60 + int(clock.group(4))
        span = (end - start) / 60.0
        if break_min:
            span -= break_min / 60.0
        return span
    return None


def judge_l_t05(text: str, params: dict):
    # 4시간 이상 30분, 8시간 이상 60분. work_hours_gt 는 사용하지 않는다.
    if re.search(r"휴게.{0,40}(?:부여하지|주지|두지)\s*않", text):
        return True
    rest = _break_minutes(text)
    hours = _work_hours(text, rest if rest is not None else 0)
    if hours is None or rest is None:
        return None
    need = 0
    if hours >= 8:
        need = 60
    elif hours >= 4:
        need = 30
    return rest < need


def judge_l_t06(text: str, params: dict):
    days = re.search(r"주\s*(\d+)\s*일", text)
    per = re.search(r"1일\s*(\d+(?:\.\d+)?)\s*시간", text)
    if not (days and per):
        return None
    weekly = int(days.group(1)) * float(per.group(1))
    threshold = float(params["weekly_holiday_threshold_hours"])
    denies = bool(re.search(r"주휴(?:수당|일).{0,20}(?:지급하지 않|무급)", text))
    if weekly >= threshold and denies:
        return True
    if weekly < threshold and denies:
        return False
    if re.search(r"주휴수당을 지급한다", text):
        return False
    return None


def _first_term_years(text: str):
    match = re.search(r"(\d+(?:\.\d+)?)\s*(년|개월)", text)
    if not match:
        return None
    value = float(match.group(1))
    return value if match.group(2) == "년" else value / 12.0


def judge_h_t01(text: str, params: dict):
    years = _first_term_years(text)
    if years is None:
        return None
    waiver = bool(re.search(r"즉시 퇴거|주장할 수 없|주장하지 않", text))
    if years < 2 and waiver:
        return True
    if years >= 2 and not re.search(r"주장하지 않|주장할 수 없", text):
        return False
    if years < 2 and not waiver:
        return None
    return True


def judge_h_t03(text: str, params: dict):
    cap = float(params["lease_increase_cap"]) * 100.0
    if re.search(r"인상하지 않|증액하지 않", text):
        return False
    rates = [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text)]
    frac = re.search(r"(\d+)\s*분의\s*(\d+)", text)
    if frac and int(frac.group(1)):
        rates.append(100.0 * int(frac.group(2)) / int(frac.group(1)))
    if not rates:
        return None
    if not re.search(r"인상|증액", text):
        return None
    return any(rate > cap + 1e-9 for rate in rates)


def judge_h_t04(text: str, params: dict):
    if re.search(r"(?:1\s*회|하루|한\s*번|한번).{0,40}해지", text):
        return True
    if re.search(r"2\s*기.{0,40}해지|해지.{0,40}2\s*기", text):
        return False
    if "해지" not in text and "독촉" in text:
        return False
    return None


def judge_d_t01(text: str, params: dict):
    cap = float(params["max_interest_rate_annual"]["from_2021-07-07"]) * 100.0
    annual = None
    month = re.search(r"(?:월|매달)\s*(?:원금의\s*)?(\d+(?:\.\d+)?)\s*%", text)
    year = re.search(r"연\s*(\d+(?:\.\d+)?)\s*%", text)
    if year:
        annual = float(year.group(1))
    elif month:
        annual = float(month.group(1)) * 12.0
    if annual is None:
        return None
    return annual > cap + 1e-9


JUDGES = {
    "L-T01": judge_l_t01,
    "L-T02": judge_l_t02,
    "L-T05": judge_l_t05,
    "L-T06": judge_l_t06,
    "H-T01": judge_h_t01,
    "H-T03": judge_h_t03,
    "H-T04": judge_h_t04,
    "D-T01": judge_d_t01,
}


def judge_item(item: dict, params: dict | None = None):
    """Return True/False risky, or None if N/A."""
    if item.get("kind") != "numeric":
        return None
    check = item.get("check_id")
    if check not in JUDGES:
        return None
    params = params or load_params()
    return JUDGES[check](item.get("clause") or "", params)


if __name__ == "__main__":
    params = load_params()
    path = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\exp_v2\data\t3_clauses.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    decided = na = match = 0
    for row in rows:
        if row["surface"] != "0" or row["check_id"] not in TARGET_CHECKS or row["kind"] != "numeric":
            continue
        pred = judge_item(row, params)
        if pred is None:
            na += 1
            print("NA", row["id"], row["clause"][:80])
            continue
        decided += 1
        ok = pred == bool(row["risky"])
        match += int(ok)
        if not ok:
            print("MISS", row["id"], pred, row["clause"][:80])
    print("decided", decided, "match", match, "na", na)
