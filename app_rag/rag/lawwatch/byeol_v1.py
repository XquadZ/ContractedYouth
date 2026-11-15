# -*- coding: utf-8 -*-
"""부칙에서 시행일·적용례·경과조치 문장 추출과 적용 기준 추정."""
from __future__ import annotations

import re
from typing import Iterable

APPLY_RULES = ("contract_date", "in_force", "performance_period", "unknown")

_CONTRACT_PAT = re.compile(
    r"(시행\s*이후|시행\s*후).{0,20}(체결|갱신)|"
    r"(최초로\s*)?(체결|갱신).{0,10}(분|임대차|계약).{0,10}적용|"
    r"계약을\s*체결하거나\s*갱신",
    re.I,
)
_IN_FORCE_PAT = re.compile(
    r"존속\s*중.{0,10}(임대차|계약).{0,15}적용|"
    r"시행\s*당시\s*존속|"
    r"시행\s*전에\s*성립한.{0,30}시행일\s*이후",
    re.I,
)
_PERF_PAT = re.compile(
    r"다음\s*연도\s*1월\s*1일부터\s*효력|"
    r"1월\s*1일부터\s*(적용|효력)|"
    r"적용\s*기간|"
    r"이행",
    re.I,
)


def classify_line(line: str) -> str | None:
    s = (line or "").strip()
    if not s:
        return None
    if "시행일" in s or re.search(r"부터\s*시행", s):
        return "시행일"
    if "적용례" in s or "적용한다" in s or "적용한다" in s:
        return "적용례"
    if "경과조치" in s or "경과" in s[:20]:
        return "경과조치"
    return None


def pick_relevant_byeol(byeol_units: list[dict], *, announced: str | None = None, effective: str | None = None) -> dict | None:
    """해당 개정에 가장 가까운 부칙 단위를 고른다."""
    if not byeol_units:
        return None
    target_anc = (announced or "").replace("-", "")[:8]
    target_ef = (effective or "").replace("-", "")[:8]
    best = None
    best_score = -1
    for u in byeol_units:
        score = 0
        anc = (u.get("announced") or "").replace("-", "")
        if target_anc and anc == target_anc:
            score += 5
        text = u.get("text") or ""
        if target_ef and target_ef in text.replace("-", ""):
            score += 2
        if "적용례" in text or "경과조치" in text or "시행일" in text:
            score += 1
        if score > best_score:
            best_score = score
            best = u
    return best or byeol_units[-1]


def extract_rule_sentences(byeol_units: list[dict], *, announced: str | None = None, effective: str | None = None) -> dict:
    unit = pick_relevant_byeol(byeol_units, announced=announced, effective=effective)
    out = {
        "byeol_announced": (unit or {}).get("announced"),
        "byeol_number": (unit or {}).get("number"),
        "시행일": [],
        "적용례": [],
        "경과조치": [],
        "all_lines": list((unit or {}).get("lines") or []),
    }
    if not unit:
        return out
    for line in unit.get("lines") or []:
        kind = classify_line(line)
        if kind == "시행일":
            out["시행일"].append(line)
        elif kind == "적용례":
            out["적용례"].append(line)
        elif kind == "경과조치":
            out["경과조치"].append(line)
        else:
            # 제n조(적용례) 다음 줄 형태 보완
            if re.search(r"적용", line) and re.search(r"(체결|갱신|존속|효력)", line):
                out["적용례"].append(line)
    return out


def infer_apply_rule(sentences: Iterable[str]) -> tuple[str, str | None]:
    """부칙 문장에서 apply_rule과 근거 quote를 고른다. 못 찾으면 unknown."""
    texts = [s.strip() for s in sentences if s and str(s).strip()]
    for s in texts:
        if _IN_FORCE_PAT.search(s):
            return "in_force", s
    for s in texts:
        if _CONTRACT_PAT.search(s):
            return "contract_date", s
    for s in texts:
        if _PERF_PAT.search(s):
            return "performance_period", s
    return "unknown", None


def quote_in_source(quote: str, source_text: str) -> bool:
    if not quote:
        return False
    return quote.strip() in (source_text or "")


def resolve_apply_rule(
    byeol_units: list[dict],
    *,
    announced: str | None = None,
    effective: str | None = None,
    extra_quotes: list[str] | None = None,
) -> dict:
    extracted = extract_rule_sentences(byeol_units, announced=announced, effective=effective)
    pool = list(extracted["적용례"]) + list(extracted["경과조치"]) + list(extracted["시행일"])
    if extra_quotes:
        pool = list(extra_quotes) + pool
    rule, quote = infer_apply_rule(pool)
    source_blob = "\n".join((u.get("text") or "") for u in byeol_units)
    if extra_quotes:
        source_blob += "\n" + "\n".join(extra_quotes)
    if quote and not quote_in_source(quote, source_blob):
        rule, quote = "unknown", None
    if rule == "unknown":
        return {
            "apply_rule": "unknown",
            "rule_quote": None,
            "status": "미확인",
            "extracted": extracted,
        }
    return {
        "apply_rule": rule,
        "rule_quote": quote,
        "status": "원문",
        "extracted": extracted,
    }
