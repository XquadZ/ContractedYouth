# -*- coding: utf-8 -*-
"""RULE_PII_FIX 회귀: 최저임금·휴게·PII·이자율."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.dates import min_wage_verdict  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.pii import mask_pii  # noqa: E402
from rag.verify import numeric_rules  # noqa: E402


def test_hourly_from_monthly_with_holiday_violation():
    text = "계약일 2025년 3월 1일. 1일 8시간, 주 40시간 근무. 월급은 2,000,000원"
    facts = extract_facts(text)
    assert facts["hourly_wage"] == 9569
    assert "주휴 8" in (facts.get("weekly_hours_formula") or "")
    assert "209시간" in (facts.get("weekly_hours_formula") or "")
    wage = min_wage_verdict(facts)
    assert wage and wage["verdict"] == "위반"
    rule = numeric_rules(text, facts)
    assert rule["verdict"] == "위반"
    assert "9569" in (rule.get("why") or "")


def test_hourly_from_monthly_ok():
    text = "계약일 2025년 3월 1일. 1일 8시간, 주 40시간 근무. 월급은 2,200,000원"
    facts = extract_facts(text)
    assert facts["hourly_wage"] == 10526
    wage = min_wage_verdict(facts)
    assert wage and wage["verdict"] == "문제 없음"


def test_break_time_range_weekly_40():
    text = "근무시간 09:00~18:00 (휴게 12:00~13:00), 주 5일"
    facts = extract_facts(text)
    assert facts["break_minutes"] == 60
    assert facts["weekly_scheduled_hours"] == 40


def test_rrn_compact_and_spaced():
    for raw in (
        "주민등록번호 9001011234567",
        "900101 - 1234567",
        "900101 1234567",
    ):
        masked, counts = mask_pii(raw)
        assert "900101-*******" in masked
        assert counts["rrn"] == 1


def test_kb_account_masked():
    masked, counts = mask_pii("국민은행 123456-01-234567")
    assert "123456-****-" in masked
    assert counts["account"] == 1


def test_role_name_field_trail():
    masked, counts = mask_pii("채무자 이기성 주민등록번호 900101-1234567")
    assert masked == "채무자 이** 주민등록번호 900101-*******"
    assert counts["name"] == 1
    assert counts["rrn"] == 1


def test_interest_year_25():
    facts = extract_facts("이자는 연 25%로 한다")
    assert facts["interest_rate"] == 0.25


def test_interest_month_with_year_paren():
    facts = extract_facts("이자는 월 3%(연 36%)로 한다")
    assert facts["interest_rate"] == 0.36


def test_interest_month_only():
    facts = extract_facts("이자는 월 2%로 한다")
    assert facts["interest_rate"] == 0.24
    assert facts["interest_rate_basis"] == "month"


def test_interest_from_amount_hangul():
    text = "일금 이천만원(₩20,000,000) 차용하여 매월 일십만원씩 이자를 상환한다"
    facts = extract_facts(text)
    assert facts["interest_rate"] == 0.06
    assert facts["principal"] == 20_000_000
    assert facts["interest_rate_basis"] == "amount"
    rule = numeric_rules(text, facts)
    assert rule.get("verdict") in (None, "문제 없음") or "interest" not in (rule.get("fired") or [])


def test_spaced_label_interest_rate():
    for text in (
        "이 자 10% 상환방법 매월 27일",
        "이 자\n10%\n상환방법\n매월 27일",
        "이자 10%",
    ):
        facts = extract_facts(text)
        assert facts["interest_rate"] == 0.1, text


def test_table_principal_and_spaced_interest():
    text = "차용금액 일금 이천만 원정 (₩ 20,000,000)\n이 자\n10%\n차용기간\n12개월"
    facts = extract_facts(text)
    assert facts["principal"] == 20_000_000
    assert facts["interest_rate"] == 0.1


def test_fullwidth_yen_amount_interest():
    text = "일금 이천만원(￦20,000,000) 차용하여 매월 일십만원씩 이자를 상환한다"
    facts = extract_facts(text)
    assert facts["principal"] == 20_000_000
    assert facts["interest_rate"] == 0.06


def test_multi_interest_rates_keeps_max():
    text = (
        "1. 일금 이천만원(₩20,000,000) 차용하여 매월 일십만원씩 이자를 상환한다\n"
        "이 자\n10%\n"
    )
    facts = extract_facts(text)
    rates = sorted({r["rate"] for r in (facts.get("interest_rates") or [])})
    assert 0.06 in rates and 0.1 in rates
    assert facts["interest_rate"] == 0.1


def test_pii_false_positives_unchanged():
    samples = [
        "차용금 20,000,000원",
        "2026-03-02",
        "제3조",
        "시급 10,030원",
        "1234567원",
        "계약일 2026년 3월 2일",
        "2026-03-02부터 2027-03-01까지",
    ]
    for s in samples:
        masked, _ = mask_pii(s)
        assert masked == s, (s, masked)
