# -*- coding: utf-8 -*-
"""QUANT_FULL 2~7장: 저장 rows 오프라인 재계산 (LLM 없음)."""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import is_blocking_fact, select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.paths import LEASE_INCREASE_CAP, MAX_INTEREST, OUT  # noqa: E402
from rag.verify import numeric_rules, verify_finding  # noqa: E402
from rag.dates import min_wage_verdict  # noqa: E402
from metrics import WARN, rate, rate_plain, score_pair, wilson_ci  # noqa: E402
from relax_check import (  # noqa: E402
    K_GRID,
    classify_review_source,
    counts_as_review_for_doc,
    doc_headline_from_counts,
)
from recall_dev import canon_from_id, gold_in_corpus, hit_matches_gold, keys_from_gold  # noqa: E402
from rag.corpus import load_corpus  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from rag.paths import GOLD  # noqa: E402
from dev_eval import gold_provisions, is_meta  # noqa: E402

RISKY = ("위반", "위험")
RISK_WORDS = ("공제", "차감", "가산", "포함", "없이", "위약", "벌금", "수습", "주휴", "배상", "포기")
AXOK_OPTS = (False, True)
NUM2WAY_OPTS = (False, True)
NE_RISKY_OPTS = (False, True)  # True=위반·위험일 때만 no_evidence
CLEAN_V2_OPTS = (False, True)  # True=toxic0 & check0
NUM_YEAR_DOC_OPTS = (False, True)  # True=NUM2WAY 최저임금 연도에 문서 start_date 허용
R_OPTS = ("R0", "R1")


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _cards_from_row(row: dict) -> list[dict]:
    full = row.get("selected_cards_full") or []
    if full:
        return full
    # fallback: id only
    return [{"id": cid} for cid in (row.get("selected_cards") or [])]


def _hits_for_verify(row: dict) -> list[dict]:
    """verify용 hits: id→text 매핑이 필요. 저장본 text 사용."""
    out = []
    for h in row.get("hits") or []:
        out.append(
            {
                "id": h.get("id"),
                "title": h.get("title") or "",
                "doc_type": h.get("doc_type") or "",
                "text": h.get("text") or "",
                "score": h.get("score"),
            }
        )
    return out


def replay_verify(row: dict, *, ax_review_to_ok: bool, ne_risky_only: bool | None = None) -> dict:
    """ne_risky_only:
    - None: verify_finding 그대로(재현용)
    - True: no_evidence는 위반·위험일 때만(문제 없음 유지, 확인 필요는 태그 안 함)
    - False: 근거 0이면 문제 없음도 확인 필요 강제
    """
    finding = dict(row.get("finding") or {})
    cards = _cards_from_row(row)
    hits = _hits_for_verify(row)
    facts = row.get("facts") or {}
    domain = row.get("domain") or "LAB"
    nf_mode = "cards" if domain == "LAB" else "legacy"
    text = row.get("text") or ""
    verified = verify_finding(
        text,
        hits,
        finding,
        facts,
        needs_fact_mode=nf_mode,
        selected_cards=cards if domain == "LAB" else [],
        ax_review_to_ok=ax_review_to_ok,
    )
    if ne_risky_only is None:
        return verified
    verified = dict(verified)
    notes = list(verified.get("notes") or [])
    rs = list(verified.get("review_sources") or [])
    ax_raw = finding.get("verdict") or "확인 필요"
    no_ev_path = ("no_evidence" in rs) or ("no_evidence_keep_ok" in notes) or (not (verified.get("evidence") or []))
    # 최저임금·이자 숫자 규칙 위반은 내리지 않음
    locked = ("rule_numeric_lock" in notes) or (
        verified.get("verdict") == "위반"
        and set((verified.get("rule") or {}).get("fired") or []) & {"min_wage", "interest"}
    )

    if locked:
        verified["verdict"] = "위반"
    elif ne_risky_only:
        # 위반·위험만 확인 필요로. 문제 없음 유지. 확인 필요에는 no_evidence 태그 제거(규칙 미적용).
        if no_ev_path and ax_raw == "문제 없음":
            verified["verdict"] = "문제 없음"
            notes = [n for n in notes if n != "no_evidence"]
            if "no_evidence_keep_ok" not in notes:
                notes.append("no_evidence_keep_ok")
            rs = [s for s in rs if s != "no_evidence"]
        elif no_ev_path and ax_raw in RISKY:
            verified["verdict"] = "확인 필요"
            if "no_evidence" not in rs:
                rs.append("no_evidence")
            notes = [n for n in notes if n != "no_evidence_keep_ok"]
        elif no_ev_path and ax_raw == "확인 필요":
            # 판정은 유지하되 no_evidence 규칙은 적용하지 않음 → R1에서 빼지 않음
            rs = [s for s in rs if s != "no_evidence"]
            notes = [n for n in notes if n not in ("no_evidence", "no_evidence_keep_ok")]
            notes.append("no_evidence_skip_check_verdict")
    else:
        # 끔: 근거 0이면 문제 없음도 확인 필요
        if no_ev_path and ax_raw == "문제 없음":
            verified["verdict"] = "확인 필요"
            if "no_evidence" not in rs:
                rs.append("no_evidence")
            notes = [n for n in notes if n != "no_evidence_keep_ok"]
            notes.append("no_evidence_force_ok")
    verified["notes"] = notes
    verified["review_sources"] = rs
    return verified


def check_reproducibility(rows: list[dict]) -> dict:
    """실행 시 ax_review_to_ok=False 와 동일 설정으로 100% 재현 확인."""
    n = 0
    mism = []
    for r in rows:
        v = replay_verify(r, ax_review_to_ok=False)
        n += 1
        got = v.get("verdict") or "확인 필요"
        exp = r.get("verdict") or "확인 필요"
        if got != exp:
            mism.append(
                {
                    "doc_id": r.get("doc_id"),
                    "segment_id": r.get("segment_id"),
                    "stored": exp,
                    "replay": got,
                    "notes_stored": r.get("notes"),
                    "notes_replay": v.get("notes"),
                }
            )
    return {"n": n, "mismatch": len(mism), "examples": mism[:20], "ok": len(mism) == 0}


# --- NUM2WAY ---
def _clause_local_ok(clause: str, *, doc_facts: dict | None = None, allow_doc_year: bool = False) -> dict:
    """조항 문장 값으로 숫자 규칙이 완전히 계산되고 기준 충족이면 ok=True.
    allow_doc_year=True면 최저임금 연도만 문서 사실표 start_date를 허용.
    """
    facts = extract_facts(clause or "")
    details = []
    complete_checks = 0
    fail = False
    year_source = "clause"

    # 최저임금: 금액은 조항에서, 연도는 옵션으로 문서 사실표
    if any(k in (clause or "") for k in ("시급", "시간급", "최저임금", "월급", "월 급여", "임금")):
        hourly = facts.get("hourly_wage")
        monthly = facts.get("monthly_wage")
        year = None
        if facts.get("start_date"):
            try:
                year = int(str(facts["start_date"])[:4])
                year_source = "clause"
            except Exception:
                year = None
        if year is None and allow_doc_year and doc_facts and doc_facts.get("start_date"):
            try:
                year = int(str(doc_facts["start_date"])[:4])
                year_source = "doc_facts"
                # min_wage_verdict용으로 연도만 문서에서 보강
                facts = dict(facts)
                facts["start_date"] = doc_facts.get("start_date")
                facts["date_missing"] = doc_facts.get("date_missing", False)
                if doc_facts.get("end_date") is not None:
                    facts["end_date"] = doc_facts.get("end_date")
            except Exception:
                year = None
        wage = min_wage_verdict(facts) if (hourly is not None) else None
        if (hourly is not None or monthly is not None) and year is not None and wage:
            complete_checks += 1
            details.append(
                {
                    "rule": "min_wage",
                    "wage": wage,
                    "year": year,
                    "year_source": year_source,
                    "hourly": hourly,
                    "monthly": monthly,
                }
            )
            if wage.get("verdict") in ("위반", "확인 필요"):
                fail = True
        # 불완전 → NUM2WAY 적용 안 함

    # 휴게
    hours = facts.get("work_hours_per_day")
    brk = facts.get("break_minutes")
    if any(k in (clause or "") for k in ("휴게", "근로시간", "근무시간")):
        if hours is not None and brk is not None:
            complete_checks += 1
            need = 60 if hours >= 8 else (30 if hours >= 4 else 0)
            details.append({"rule": "break", "hours": hours, "break": brk, "need": need})
            if brk < need:
                fail = True

    # 임대 증액
    rate_v = facts.get("rent_increase_rate")
    if any(k in (clause or "") for k in ("증액", "인상")):
        if rate_v is not None:
            complete_checks += 1
            details.append({"rule": "lease_increase", "rate": rate_v, "cap": LEASE_INCREASE_CAP})
            if rate_v > LEASE_INCREASE_CAP:
                fail = True

    # 이자
    interest = facts.get("interest_rate")
    delay = facts.get("delay_interest_rate")
    if any(k in (clause or "") for k in ("이자", "이율")):
        vals = [(n, v) for n, v in (("interest", interest), ("delay", delay)) if v is not None]
        if vals:
            complete_checks += 1
            for n, v in vals:
                details.append({"rule": "interest", "name": n, "val": v, "cap": MAX_INTEREST})
                if v > MAX_INTEREST:
                    fail = True

    has_risk = any(w in (clause or "") for w in RISK_WORDS)
    ok = complete_checks >= 1 and not fail and not has_risk
    return {
        "ok": ok,
        "complete_checks": complete_checks,
        "fail": fail,
        "has_risk_word": has_risk,
        "details": details,
        "local_facts": {k: facts.get(k) for k in (
            "hourly_wage", "monthly_wage", "work_hours_per_day", "break_minutes",
            "rent_increase_rate", "interest_rate", "delay_interest_rate", "start_date",
        )},
    }


def apply_num2way(
    verdict: str,
    clause: str,
    *,
    doc_facts: dict | None = None,
    allow_doc_year: bool = False,
) -> tuple[str, dict | None]:
    if verdict not in ("위반", "위험", "확인 필요"):
        return verdict, None
    info = _clause_local_ok(clause, doc_facts=doc_facts, allow_doc_year=allow_doc_year)
    if info["ok"]:
        return "문제 없음", info
    return verdict, info if info["complete_checks"] else None


def transform_row(
    row: dict,
    *,
    axok: bool,
    num2way: bool,
    ne_risky_only: bool = False,
    num_year_doc: bool = False,
) -> dict:
    verified = replay_verify(row, ax_review_to_ok=axok, ne_risky_only=ne_risky_only)
    verdict = verified.get("verdict") or "확인 필요"
    num_info = None
    flipped = False
    locked = ("rule_numeric_lock" in (verified.get("notes") or [])) or (
        verdict == "위반"
        and set((verified.get("rule") or {}).get("fired") or []) & {"min_wage", "interest"}
    )
    if num2way and not locked:
        new_v, num_info = apply_num2way(
            verdict,
            row.get("text") or "",
            doc_facts=row.get("facts") or {},
            allow_doc_year=num_year_doc,
        )
        if new_v != verdict:
            flipped = True
            verdict = new_v
            notes = list(verified.get("notes") or [])
            notes.append("num2way_to_ok")
            if num_info and any(d.get("year_source") == "doc_facts" for d in (num_info.get("details") or [])):
                notes.append("num2way_year_from_doc")
            verified = dict(verified)
            verified["notes"] = notes
    cards = _cards_from_row(row)
    nf = verified.get("needs_fact")
    blocking = bool(nf) and is_blocking_fact(nf, cards) if cards else False
    out = dict(row)
    out["verdict"] = verdict
    out["ax_verdict"] = verified.get("ax_verdict")
    out["notes"] = verified.get("notes") or []
    out["review_sources"] = verified.get("review_sources") or []
    out["review_source"] = classify_review_source(verified, verdict)
    out["needs_fact"] = nf
    out["needs_fact_action"] = verified.get("needs_fact_action")
    out["needs_fact_is_blocking_if"] = blocking if nf else None
    out["dropped_ids"] = verified.get("dropped_ids") or []
    out["quote_mismatch"] = "quote_mismatch" in (out["review_sources"]) or any(
        "quote_mismatch" in str(n) for n in out["notes"]
    )
    out["parse_ok"] = bool(verified.get("parse_ok"))
    out["evidence_final"] = verified.get("evidence") or []
    out["rule"] = verified.get("rule") or {}
    out["bucket"] = score_pair(row.get("label") or "", verdict)
    out["axok"] = axok
    out["num2way"] = num2way
    out["ne_risky_only"] = ne_risky_only
    out["num_year_doc"] = num_year_doc
    out["num2way_flipped"] = flipped
    out["num2way_info"] = num_info
    out["ax_review_to_ok"] = "ax_review_to_ok" in (out["notes"]) or verified.get("needs_fact_action") == "ax_review_to_ok"
    return out


# --- metrics ---
def clause_metrics(rows: list[dict]) -> dict:
    tox = [r for r in rows if r.get("label") == "toxic"]
    saf = [r for r in rows if r.get("label") == "safe"]
    chk = [r for r in rows if r.get("label") == "check"]
    det = sum(1 for r in tox if r.get("verdict") in RISKY)
    warn = sum(1 for r in tox if r.get("verdict") in WARN)
    miss = sum(1 for r in tox if r.get("verdict") == "문제 없음")
    fp = sum(1 for r in saf if r.get("verdict") in RISKY)
    ow = sum(1 for r in saf if r.get("verdict") == "확인 필요")
    cok = sum(1 for r in chk if r.get("verdict") == "확인 필요")

    # 독소 코드별
    by_code: dict[str, Counter] = defaultdict(Counter)
    for r in tox:
        codes = r.get("gold_codes") or ["(none)"]
        v = r.get("verdict")
        for c in codes:
            by_code[c]["n"] += 1
            if v in RISKY:
                by_code[c]["risky"] += 1
            elif v == "확인 필요":
                by_code[c]["check"] += 1
            else:
                by_code[c]["miss"] += 1

    return {
        "n": len(rows),
        "toxic_n": len(tox),
        "safe_n": len(saf),
        "check_n": len(chk),
        "detect": det,
        "warn_capture": warn,
        "miss": miss,
        "fp": fp,
        "overwarn": ow,
        "check_ok": cok,
        "detect_rate": rate(det, len(tox)),
        "warn_capture_rate": rate(warn, len(tox)),
        "miss_rate": rate(miss, len(tox)),
        "fp_rate": rate(fp, len(saf)),
        "overwarn_rate": rate(ow, len(saf)),
        "check_rate": rate(cok, len(chk)),
        "detect_p": rate_plain(det, len(tox)),
        "warn_capture_p": rate_plain(warn, len(tox)),
        "fp_p": rate_plain(fp, len(saf)),
        "overwarn_p": rate_plain(ow, len(saf)),
        "by_code": {k: dict(v) for k, v in sorted(by_code.items())},
    }


def doc_label_bucket(rs: list[dict], *, clean_v2: bool) -> str:
    """toxic | check_only | clean. clean_v2면 toxic0&check0만 clean, check만 있으면 check_only."""
    labs = {r.get("label") for r in rs}
    if "toxic" in labs:
        return "toxic"
    if clean_v2:
        if "check" in labs:
            return "check_only"
        return "clean"
    # v1: 기존 is_clean_doc 플래그(독소 없으면 clean, check 포함 가능)
    if rs and rs[0].get("is_clean_doc"):
        return "clean"
    return "toxic"


def doc_metrics(rows: list[dict], method: str, k: int, *, clean_v2: bool = False) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["doc_id"]].append(r)
    clean_pass = clean_n = tox_warn = tox_n = 0
    check_ok = check_n = 0
    misses = []
    check_wrong = []
    headlines = {}
    for did, rs in by.items():
        bucket = doc_label_bucket(rs, clean_v2=clean_v2)
        n_risky = sum(1 for r in rs if r.get("verdict") in RISKY)
        n_review = sum(1 for r in rs if counts_as_review_for_doc(r, method))
        hl = doc_headline_from_counts(n_risky, n_review, k)
        headlines[did] = hl
        if bucket == "clean":
            clean_n += 1
            if hl == "큰 문제 없음":
                clean_pass += 1
        elif bucket == "check_only":
            check_n += 1
            if hl == "확인할 부분 있음":
                check_ok += 1
            else:
                check_wrong.append({"doc_id": did, "headline": hl})
        else:
            tox_n += 1
            if hl != "큰 문제 없음":
                tox_warn += 1
            else:
                misses.append(did)
    return {
        "method": method,
        "K": k,
        "clean_v2": clean_v2,
        "clean_pass": clean_pass,
        "clean_n": clean_n,
        "clean_pass_rate": rate(clean_pass, clean_n),
        "clean_pass_p": rate_plain(clean_pass, clean_n),
        "check_doc_ok": check_ok,
        "check_doc_n": check_n,
        "check_doc_rate": rate(check_ok, check_n),
        "check_doc_p": rate_plain(check_ok, check_n),
        "check_doc_wrong": check_wrong,
        "toxic_warn": tox_warn,
        "toxic_n": tox_n,
        "toxic_warn_rate": rate(tox_warn, tox_n),
        "toxic_miss_n": len(misses),
        "toxic_misses": misses,
        "headlines": headlines,
    }


def verify_stats(rows: list[dict]) -> dict:
    tox = [r for r in rows if r.get("label") == "toxic"]
    saf = [r for r in rows if r.get("label") == "safe"]
    qm_t = sum(1 for r in tox if r.get("quote_mismatch"))
    qm_s = sum(1 for r in saf if r.get("quote_mismatch"))
    dropped = sum(len(r.get("dropped_ids") or []) for r in rows)
    zero_ev = sum(1 for r in rows if not (r.get("evidence_final") or r.get("finding", {}).get("evidence")))
    parse_fail = sum(1 for r in rows if r.get("parse_ok") is False)
    return {
        "quote_mismatch_toxic": rate(qm_t, len(tox)),
        "quote_mismatch_safe": rate(qm_s, len(saf)),
        "dropped_ids_total": dropped,
        "dropped_per_row": round(dropped / max(1, len(rows)), 3),
        "zero_evidence_rate": rate(zero_ev, len(rows)),
        "parse_fail_rate": rate(parse_fail, len(rows)),
    }


def timing_stats(rows: list[dict], switch_sec: float = 0.0) -> dict:
    ms = sorted(float(r.get("latency_ms") or 0) for r in rows)
    n = len(ms)
    mean = sum(ms) / max(1, n)
    p90 = ms[int(0.9 * (n - 1))] if n else 0
    by = defaultdict(float)
    for r in rows:
        by[r["doc_id"]] += float(r.get("latency_ms") or 0)
    doc_means = list(by.values())
    doc_avg = sum(doc_means) / max(1, len(doc_means))
    return {
        "mean_ms": round(mean, 1),
        "p90_ms": round(p90, 1),
        "doc_mean_ms": round(doc_avg, 1),
        "doc_mean_sec": round(doc_avg / 1000, 2),
        "switch_sec": switch_sec,
        "n_docs": len(by),
        "n_rows": n,
    }


def evidence_match_rate(rows: list[dict], corpus_keys: set, corpus_ids: list[str]) -> dict:
    """최종 근거 법이름+조가 gold legal_provisions와 하나라도 겹침. corpus 없는 gold는 제외."""
    eligible = matched = skipped = 0
    for r in rows:
        if r.get("label") not in ("toxic", "check"):
            continue
        golds = r.get("gold_provisions") or []
        if not golds:
            continue
        in_c = [g for g in golds if gold_in_corpus(g, corpus_keys, corpus_ids)]
        if not in_c:
            skipped += 1
            continue
        eligible += 1
        gold_keys = set()
        for g in in_c:
            gold_keys.update(keys_from_gold(g))
        evs = r.get("evidence_final") or []
        hit = False
        for ev in evs:
            eid = ev.get("id") or ""
            if hit_matches_gold(eid, gold_keys, in_c):
                hit = True
                break
        if hit:
            matched += 1
    return {
        "match_rate": rate(matched, eligible),
        "matched": matched,
        "eligible": eligible,
        "skipped_not_in_corpus": skipped,
    }


def recall_at_3(domain: str) -> dict:
    """검색 recall@3 (모델 무관)."""
    ids = load_split_ids("dev", domain, SPLIT_FILE_V2)
    contracts = load_jsonl(GOLD[domain]["contract"])
    twin_p = clean_twin_path(domain)
    if twin_p.exists():
        contracts = contracts + load_jsonl(twin_p)
    law_map = {r["segment_id"]: r for r in load_jsonl(GOLD[domain]["law"])} if GOLD[domain]["law"].exists() else {}
    index, _ = get_index()
    corpus, _skipped = load_corpus()
    corpus_ids = [c["id"] for c in corpus]
    corpus_keys = set()
    for c in corpus:
        k = canon_from_id(c["id"])
        if k:
            corpus_keys.add(k)

    hit_n = tot = skip = 0
    for seg in contracts:
        if seg.get("doc_id") not in ids or is_meta(seg):
            continue
        if seg.get("label") not in ("toxic", "check"):
            continue
        law = law_map.get(seg.get("segment_id") or "", {})
        golds = gold_provisions(seg, law)
        if not golds:
            continue
        in_c = [g for g in golds if gold_in_corpus(g, corpus_keys, corpus_ids)]
        if not in_c:
            skip += 1
            continue
        tot += 1
        gold_keys = set()
        for g in in_c:
            gold_keys.update(keys_from_gold(g))
        hits = (index.search(strip_placeholders(seg.get("text") or ""), domain=domain, title="") or {}).get("hits") or []
        top = hits[:3]
        if any(hit_matches_gold(h.get("id") or "", gold_keys, in_c) for h in top):
            hit_n += 1
    return {"domain": domain, "recall_at_3": rate(hit_n, tot), "hit": hit_n, "n": tot, "skipped": skip}


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar exact p-value (binomial n=b+c, p=0.5), two-sided."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # P(X<=k) * 2, cap 1
    # sum_{i=0..k} C(n,i) / 2^n
    p = 0.0
    for i in range(k + 1):
        p += math.comb(n, i)
    p = (p / (2 ** n)) * 2
    return min(1.0, p)


def mcnemar_compare(rows_a: list[dict], rows_b: list[dict], *, kind: str) -> dict:
    """kind=warn_capture(toxic) or fp(safe)."""
    ka = {(r["doc_id"], r["segment_id"]): r for r in rows_a}
    kb = {(r["doc_id"], r["segment_id"]): r for r in rows_b}
    keys = sorted(set(ka) & set(kb))
    b = c = 0  # b: A yes B no; c: A no B yes
    n = 0
    for k in keys:
        ra, rb = ka[k], kb[k]
        lab = ra.get("label")
        if kind == "warn_capture":
            if lab != "toxic":
                continue
            ya = ra.get("verdict") in WARN
            yb = rb.get("verdict") in WARN
        else:
            if lab != "safe":
                continue
            ya = ra.get("verdict") in RISKY
            yb = rb.get("verdict") in RISKY
        n += 1
        if ya and not yb:
            b += 1
        elif (not ya) and yb:
            c += 1
    return {"n": n, "b": b, "c": c, "p": round(mcnemar_exact(b, c), 6)}


def pick_best(combo_results: list[dict]) -> dict | None:
    """독소놓침0 → warn_cap max → clean_pass max → fp min."""
    cand = [x for x in combo_results if x.get("toxic_miss_n", 1) == 0]
    if not cand:
        cand = list(combo_results)
        # still pick by miss then others
        cand.sort(key=lambda x: (
            x.get("toxic_miss_n", 99),
            -(x.get("warn_capture_p") or 0),
            -(x.get("clean_pass_p") or 0),
            x.get("fp_p") if x.get("fp_p") is not None else 9,
        ))
        return cand[0] if cand else None
    cand.sort(key=lambda x: (
        -(x.get("warn_capture_p") or 0),
        -(x.get("clean_pass_p") or 0),
        x.get("fp_p") if x.get("fp_p") is not None else 9,
    ))
    return cand[0]


def goals_flags(m: dict) -> dict:
    return {
        "warn_ge_90": (m.get("warn_capture_p") or 0) >= 0.90,
        "fp_le_5": (m.get("fp_p") or 1) <= 0.05,
        "ow_le_20": (m.get("overwarn_p") or 1) <= 0.20,
        "clean_ge_80": (m.get("clean_pass_p") or 0) >= 0.80,
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def sweep_all(rows: list[dict]) -> list[dict]:
    out = []
    for axok in AXOK_OPTS:
        for num2way in NUM2WAY_OPTS:
            transformed = [transform_row(r, axok=axok, num2way=num2way) for r in rows]
            cm = clause_metrics(transformed)
            # num2way flip stats
            flips = [t for t in transformed if t.get("num2way_flipped")]
            flip_by_label = Counter(t.get("label") for t in flips)
            toxic_flips = [
                {
                    "doc_id": t["doc_id"],
                    "segment_id": t["segment_id"],
                    "ax_verdict": t.get("ax_verdict"),
                    "text40": (t.get("text") or "")[:40],
                }
                for t in flips
                if t.get("label") == "toxic"
            ]
            for method in R_OPTS:
                for k in K_GRID:
                    dm = doc_metrics(transformed, method, k)
                    cell = {
                        "axok": axok,
                        "num2way": num2way,
                        "R": method,
                        "K": k,
                        **{kk: cm[kk] for kk in (
                            "detect_rate", "warn_capture_rate", "miss_rate", "fp_rate",
                            "overwarn_rate", "check_rate", "detect_p", "warn_capture_p",
                            "fp_p", "overwarn_p", "toxic_n", "safe_n",
                        )},
                        "clean_pass_rate": dm["clean_pass_rate"],
                        "clean_pass_p": dm["clean_pass_p"],
                        "clean_pass": dm["clean_pass"],
                        "clean_n": dm["clean_n"],
                        "toxic_warn_rate": dm["toxic_warn_rate"],
                        "toxic_miss_n": dm["toxic_miss_n"],
                        "toxic_misses": dm["toxic_misses"],
                        "num2way_flips": dict(flip_by_label),
                        "num2way_toxic_flips": toxic_flips if (num2way and method == "R0" and k == 0) else [],
                        "by_code": cm["by_code"] if (method == "R0" and k == 0) else {},
                    }
                    out.append(cell)
    return out


def cascade_rows(ax_rows: list[dict], ex_rows: list[dict], ax_cfg: dict, ex_cfg: dict) -> list[dict]:
    """A.X가 위반·위험·확인 필요인 조항만 EXAONE 판정."""
    ax_t = {
        (r["doc_id"], r["segment_id"]): transform_row(r, axok=ax_cfg["axok"], num2way=ax_cfg["num2way"])
        for r in ax_rows
    }
    ex_t = {
        (r["doc_id"], r["segment_id"]): transform_row(r, axok=ex_cfg["axok"], num2way=ex_cfg["num2way"])
        for r in ex_rows
    }
    out = []
    n_ex = 0
    for k, ar in ax_t.items():
        if k not in ex_t:
            continue
        if ar.get("verdict") in WARN:
            merged = dict(ex_t[k])
            merged["cascade_source"] = "EXAONE"
            n_ex += 1
        else:
            merged = dict(ar)
            merged["cascade_source"] = "AX"
        out.append(merged)
    return out, n_ex


if __name__ == "__main__":
    # smoke: reproducibility on one file if present
    p = OUT / "quant" / "AX_LAB_rows.jsonl"
    if p.exists():
        rows = load_rows(p)
        print(json.dumps(check_reproducibility(rows[:5]), ensure_ascii=False, indent=2))
    else:
        print("no rows yet")
