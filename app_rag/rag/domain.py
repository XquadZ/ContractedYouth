# -*- coding: utf-8 -*-
"""계약서 종류 키워드 점수. A.X/검색 설정과 무관."""
from __future__ import annotations

import re

LABELS = {"LAB": "근로", "LEASE": "임대차", "LOAN": "차용"}

KEYWORDS = {
    "LAB": ["근로계약서", "사업주", "근로자", "임금", "근로시간"],
    "LEASE": ["임대차", "임대인", "임차인", "보증금", "차임"],
    "LOAN": ["차용증", "금전소비대차", "채권자", "채무자", "변제", "이자"],
}

OUT_OF_SCOPE = ["매매계약", "부동산 매매", "매도인", "매수인", "분양계약"]


def score_domain(text: str) -> dict:
    t = text or ""
    scores = {k: 0 for k in KEYWORDS}
    hits = {k: [] for k in KEYWORDS}
    for dom, words in KEYWORDS.items():
        for w in words:
            n = len(re.findall(re.escape(w), t))
            if n:
                scores[dom] += n
                hits[dom].append(w)
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top, second = ranked[0], ranked[1]
    out_hits = [w for w in OUT_OF_SCOPE if w in t]
    confident = True
    reason = ""
    if top[1] <= 0:
        confident = False
        reason = "키워드가 거의 없습니다."
    elif second[1] > 0 and top[1] < second[1] * 1.5:
        confident = False
        reason = "1등 점수가 2등의 1.5배 미만입니다."
    out_of_scope = False
    if out_hits and (top[1] == 0 or (scores.get("LEASE", 0) == 0 and "매매" in "".join(out_hits))):
        # 매매 키워드가 뚜렷하고 우리 도메인 점수가 약하면
        if top[1] < 2 and out_hits:
            out_of_scope = True
            confident = False
            reason = "매매 등 지원 범위 밖 계약으로 보입니다."
    domain = top[0] if top[1] > 0 else None
    return {
        "domain": domain,
        "label": LABELS.get(domain or "", ""),
        "scores": scores,
        "hits": hits,
        "confident": confident,
        "reason": reason,
        "out_of_scope": out_of_scope,
        "out_hits": out_hits,
        "choices": [{"id": k, "label": LABELS[k], "score": scores[k]} for k in ("LAB", "LEASE", "LOAN")],
    }
