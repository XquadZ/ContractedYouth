# -*- coding: utf-8 -*-
"""계약서 쪼개기. 기본은 조·항 경계. 토큰 창으로 자르지 않는다."""
from __future__ import annotations

import re

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
# 제N조 / 원문자 항 / '1. ' 식 번호. app_compare.pipelines.common.split_clauses 와 같다.
_SPLIT = re.compile(rf"(?=^제\s*\d+\s*조)|(?=^[{CIRCLED}])|(?=^\d{{1,2}}\.\s)", re.M)


def split_contract(text: str, mode: str = "clause") -> list[str]:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    if mode == "whole":
        return [raw]
    if mode != "clause":
        raise ValueError(f"unknown split mode: {mode}")
    idxs = [m.start() for m in _SPLIT.finditer(raw)]
    if not idxs:
        return [raw]
    if idxs[0] != 0:
        idxs = [0] + idxs
    parts = []
    for i, start in enumerate(idxs):
        end = idxs[i + 1] if i + 1 < len(idxs) else len(raw)
        piece = raw[start:end].strip()
        if len(piece) >= 2:
            parts.append(piece)
    return parts or [raw]
