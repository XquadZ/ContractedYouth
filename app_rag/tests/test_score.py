# -*- coding: utf-8 -*-
"""점수 공식 단위 테스트 5개."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.score import compute_score, score_from_findings


def test_all_clear_safe():
    s = compute_score()
    assert s["score"] == 100
    assert s["grade"] == "안전"


def test_one_violation_cap69():
    s = compute_score(n_violation=1)
    assert s["score"] == 69  # 100-20=80 but cap 69
    assert s["grade"] == "주의"


def test_check_cap20():
    s = compute_score(n_check=10, check_cap79=False)  # 10*4=40 → min 20
    assert s["deduction"] == 20
    assert s["score"] == 80
    assert s["grade"] == "안전"


def test_check_cap79_default():
    # 위반·위험 0 + 확인 필요 3 → 감점 12 → 88이지만 cap79 → 79, 주의
    s = compute_score(n_check=3)
    assert s["check_cap79"] is True
    assert s["score"] == 79
    assert s["grade"] == "주의"
    assert "확인할 조항이 3개 이상" in (s.get("score_note") or "")


def test_risk_grade():
    s = compute_score(n_violation=2, n_risk=1)  # 40+12=52 → 48, cap69 → 48
    assert s["score"] == 48
    assert s["grade"] == "위험"


def test_from_findings_missing_unreflected():
    findings = [
        {"verdict": "문제 없음"},
        {"verdict": "확인 필요"},
        {"verdict": "위험"},
    ]
    s = score_from_findings(findings)
    # 위험12 + 확인4 = 16 → 84 but risk present → cap 69
    assert s["score"] == 69
    assert s["missing_reflected"] is False
    assert s["mismatch_reflected"] is False
    print("PASS all 5 score tests")


if __name__ == "__main__":
    test_all_clear_safe()
    test_one_violation_cap69()
    test_check_cap20()
    test_risk_grade()
    test_from_findings_missing_unreflected()
    print("RESULT 5/5")
