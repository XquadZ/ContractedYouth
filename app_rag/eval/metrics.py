# -*- coding: utf-8 -*-
"""공통 채점·비율·문서 판정 (FIX_ROUND1-B). 기존 detect/fp/overwarn 지표는 유지."""
from __future__ import annotations

import math
from collections import Counter, defaultdict

RISKY = ("위반", "위험")
WARN = ("위반", "위험", "확인 필요")


def score_pair(label: str, verdict: str) -> str:
    if label == "toxic":
        if verdict in RISKY:
            return "detect"
        if verdict == "확인 필요":
            return "partial"
        return "miss"
    if label == "safe":
        if verdict in RISKY:
            return "fp"
        if verdict == "확인 필요":
            return "overwarn"
        return "safe_ok"
    if label == "check":
        if verdict == "확인 필요":
            return "check_ok"
        if verdict in RISKY:
            return "check_as_toxic"
        return "check_as_safe"
    return "other"


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return lo, hi


def rate(n: int, d: int) -> str:
    if d <= 0:
        return "n/a (0)"
    lo, hi = wilson_ci(n, d)
    return f"{n / d:.3f} ({n}/{d}) CI95[{lo:.3f},{hi:.3f}]"


def rate_plain(n: int, d: int) -> float | None:
    return (n / d) if d else None


def doc_headline(verdicts: list[str]) -> str:
    """리포트 맨 위 3단계 문구."""
    n_risky = sum(1 for v in verdicts if v in RISKY)
    n_check = sum(1 for v in verdicts if v == "확인 필요")
    if n_risky >= 1:
        return "고칠 조항 있음"
    if n_check >= 3:
        return "확인할 부분 있음"
    return "큰 문제 없음"


def is_clean_doc(rows_for_doc: list[dict]) -> bool:
    """원래 깨끗(독소 0) 또는 clean twin(doc_id에 -C 또는 twin 표시)."""
    did = (rows_for_doc[0].get("doc_id") or "") if rows_for_doc else ""
    if "-C" in did:  # LEASE-C001 / LOAN-C001 / WORK-C001
        return True
    if any(r.get("is_clean_twin") for r in rows_for_doc):
        return True
    return not any(r.get("label") == "toxic" for r in rows_for_doc)


def is_toxic_doc(rows_for_doc: list[dict]) -> bool:
    return any(r.get("label") == "toxic" for r in rows_for_doc)


def summarize_rows(rows: list[dict]) -> dict:
    tox = [r for r in rows if r.get("label") == "toxic"]
    saf = [r for r in rows if r.get("label") == "safe"]
    chk = [r for r in rows if r.get("label") == "check"]
    det = [r for r in tox if r.get("bucket") == "detect"]
    par = [r for r in tox if r.get("bucket") == "partial"]
    mis = [r for r in tox if r.get("bucket") == "miss"]
    warn_cap = [r for r in tox if r.get("verdict") in WARN]
    fp = [r for r in saf if r.get("bucket") == "fp"]
    ow = [r for r in saf if r.get("bucket") == "overwarn"]
    cok = [r for r in chk if r.get("bucket") == "check_ok"]

    # ax_review_to_ok 덮어쓰기: toxic vs safe
    ov = [r for r in rows if r.get("ax_review_to_ok")]
    ov_tox = [r for r in ov if r.get("label") == "toxic"]
    ov_saf = [r for r in ov if r.get("label") == "safe"]

    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_doc[r.get("doc_id") or ""].append(r)

    headlines = {}
    clean_pass = 0
    clean_n = 0
    tox_doc_warn = 0
    tox_doc_n = 0
    for did, rs in by_doc.items():
        if not did:
            continue
        hl = doc_headline([r.get("verdict") or "확인 필요" for r in rs])
        headlines[did] = hl
        if is_clean_doc(rs):
            clean_n += 1
            if hl == "큰 문제 없음":
                clean_pass += 1
        if is_toxic_doc(rs):
            tox_doc_n += 1
            if hl == "고칠 조항 있음":
                tox_doc_warn += 1

    headline_counts = Counter(headlines.values())
    return {
        "n": len(rows),
        "toxic": len(tox),
        "detect": len(det),
        "partial": len(par),
        "miss": len(mis),
        "warn_capture": len(warn_cap),
        "safe": len(saf),
        "fp": len(fp),
        "overwarn": len(ow),
        "check": len(chk),
        "check_ok": len(cok),
        "detect_rate": rate(len(det), len(tox)),
        "warn_capture_rate": rate(len(warn_cap), len(tox)),
        "partial_rate": rate(len(par), len(tox)),
        "miss_rate": rate(len(mis), len(tox)),
        "fp_rate": rate(len(fp), len(saf)),
        "overwarn_rate": rate(len(ow), len(saf)),
        "check_rate": rate(len(cok), len(chk)),
        "clean_doc_pass": clean_pass,
        "clean_doc_n": clean_n,
        "clean_doc_pass_rate": rate(clean_pass, clean_n),
        "toxic_doc_warn": tox_doc_warn,
        "toxic_doc_n": tox_doc_n,
        "toxic_doc_warn_rate": rate(tox_doc_warn, tox_doc_n),
        "ax_review_to_ok": len(ov),
        "ax_review_to_ok_toxic": len(ov_tox),
        "ax_review_to_ok_safe": len(ov_saf),
        "doc_headlines": dict(headline_counts),
        "doc_headline_by_id": headlines,
    }
