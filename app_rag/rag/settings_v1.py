# -*- coding: utf-8 -*-
"""시연/분석 설정. ANALYZE_MODEL: ax | exaone | gpt."""
from __future__ import annotations

import os

# 기본값: 사용자가 A장 결과로 정하기 전까지 exaone
ANALYZE_MODEL = (os.environ.get("ANALYZE_MODEL") or "exaone").strip().lower()
GPT_MODEL = (os.environ.get("GPT_MODEL") or "gpt-4o-mini").strip()  # G1 기본
FILE_TTL_MINUTES = int(os.environ.get("FILE_TTL_MINUTES") or "1440")
# 카드·판정 프롬프트 버전: tuned(지금) | neutral(모델 튜닝 전)
CARDS_VERSION = (os.environ.get("CARDS_VERSION") or "tuned").strip().lower()

# 모델별 최적 검증 조합 (QUANT/FIX_ROUND3 + A장 후 갱신 가능)
MODEL_VERIFY = {
    "ax": {"axok": False, "num2way": True, "ne_risky_only": True, "num_year_doc": True, "R": "R0", "K": 2},
    "exaone": {"axok": False, "num2way": True, "ne_risky_only": True, "num_year_doc": True, "R": "R0", "K": 2},
    "gpt": {"axok": False, "num2way": True, "ne_risky_only": True, "num_year_doc": True, "R": "R0", "K": 2},
}


def get_analyze_model() -> str:
    m = (os.environ.get("ANALYZE_MODEL") or ANALYZE_MODEL or "exaone").strip().lower()
    if m not in ("ax", "exaone", "gpt"):
        return "exaone"
    return m


def get_cards_version() -> str:
    m = (os.environ.get("CARDS_VERSION") or CARDS_VERSION or "tuned").strip().lower()
    if m not in ("tuned", "neutral"):
        return "tuned"
    return m


def model_label(m: str | None = None) -> str:
    m = (m or get_analyze_model()).lower()
    return {
        "ax": "A.X-4.0-Light",
        "exaone": "EXAONE-4.0-32B",
        "gpt": f"OpenAI/{GPT_MODEL}",
    }.get(m, m)
