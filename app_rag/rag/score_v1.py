# -*- coding: utf-8 -*-
"""조장 점수 공식. 백엔드·프론트 공통."""
from __future__ import annotations

from typing import Any


GRADE_SAFE = "안전"
GRADE_CAUTION = "주의"
GRADE_RISK = "위험"


def count_verdicts(items: list[dict] | None) -> dict[str, int]:
    """리포트 카드/조항 목록에서 판정 개수. missing·mismatch는 키가 없으면 0."""
    n = {"위반": 0, "위험": 0, "확인 필요": 0, "누락": 0, "불일치": 0, "문제 없음": 0}
    for it in items or []:
        v = str(it.get("verdict") or it.get("grade_tag") or "").strip()
        if v in n:
            n[v] += 1
        # 명시 필드
        n["누락"] += int(it.get("missing") or 0) if "missing" in it else 0
        n["불일치"] += int(it.get("mismatch") or 0) if "mismatch" in it else 0
    return n


def compute_score(
    *,
    n_violation: int = 0,
    n_risk: int = 0,
    n_check: int = 0,
    n_missing: int = 0,
    n_mismatch: int = 0,
    missing_reflected: bool = True,
    mismatch_reflected: bool = True,
    check_cap79: bool = False,
) -> dict[str, Any]:
    """
    감점 = 위반×20 + 위험×12 + min(확인필요×4,20) + min(누락×5,20) + min(불일치×3,9)
    점수 = max(0, 100 − 감점). 위반+위험이 1개 이상이면 최대 69점.
    check_cap79: 확인 필요 3개 이상이면 최대 79점(수정안).
    등급: 80+ 안전, 50~79 주의, ≤49 위험
    """
    miss = n_missing if missing_reflected else 0
    mism = n_mismatch if mismatch_reflected else 0
    deduction = (
        n_violation * 20
        + n_risk * 12
        + min(n_check * 4, 20)
        + min(miss * 5, 20)
        + min(mism * 3, 9)
    )
    score = max(0, 100 - deduction)
    if (n_violation + n_risk) >= 1:
        score = min(score, 69)
    if check_cap79 and n_check >= 3:
        score = min(score, 79)
    if score >= 80:
        grade = GRADE_SAFE
    elif score >= 50:
        grade = GRADE_CAUTION
    else:
        grade = GRADE_RISK
    return {
        "score": int(score),
        "grade": grade,
        "deduction": int(deduction),
        "counts": {
            "위반": n_violation,
            "위험": n_risk,
            "확인 필요": n_check,
            "누락": n_missing,
            "불일치": n_mismatch,
        },
        "missing_reflected": missing_reflected,
        "mismatch_reflected": mismatch_reflected,
        "check_cap79": check_cap79,
        "disclaimer": "법 기준을 어긴 조항을 찾지 못했다는 뜻이며, 법률 자문이 아니에요."
        if grade == GRADE_SAFE
        else "",
    }


def score_from_findings(
    findings: list[dict],
    *,
    missing_reflected: bool = False,
    mismatch_reflected: bool = False,
    check_cap79: bool = False,
) -> dict[str, Any]:
    """문서 조항 판정 목록 → 점수. 누락·불일치 미반영이 기본(계산 못하면 0·미반영)."""
    n_v = n_r = n_c = 0
    for f in findings or []:
        v = str(f.get("verdict") or "").strip()
        if v == "위반":
            n_v += 1
        elif v == "위험":
            n_r += 1
        elif v == "확인 필요":
            n_c += 1
    return compute_score(
        n_violation=n_v,
        n_risk=n_r,
        n_check=n_c,
        n_missing=0,
        n_mismatch=0,
        missing_reflected=missing_reflected,
        mismatch_reflected=mismatch_reflected,
        check_cap79=check_cap79,
    )
