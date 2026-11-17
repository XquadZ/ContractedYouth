# -*- coding: utf-8 -*-
"""판정 JSON을 코드로 검증한다. 학습 모델 없음."""
from __future__ import annotations

import re
from pathlib import Path

from rag.criteria import blocking_triggered, is_blocking_fact, needs_fact_available
from rag.dates import min_wage_verdict
from rag.paths import APP, LEASE_INCREASE_CAP, MAX_INTEREST
from rag.yamlutil import load as load_yaml

_VERIFY_CFG = APP / "config" / "verify.yaml"


def load_verify_config() -> dict:
    if _VERIFY_CFG.exists():
        return load_yaml(_VERIFY_CFG) or {}
    return {"ax_review_to_ok": True}


def ax_review_to_ok_enabled(override: bool | None = None) -> bool:
    if override is not None:
        return bool(override)
    return bool(load_verify_config().get("ax_review_to_ok", True))

SOURCE_TAG = {
    "법률": "[법령]",
    "시행령": "[법령]",
    "고시": "[고시]",
    "판례": "[판례]",
    "표준계약서": "[표준계약서]",
    "해석례": "[해석례]",
}
INJECT_PATTERNS = ("판단하라", "무시하라", "안전하다고", "system", "이 지시", "ignore previous", "you are")
CRITICAL = ("최저임금", "위약금", "전입신고", "갱신요구", "이자")

# needs_fact 규칙 카운터 (평가 스크립트가 리셋·읽음)
NEEDS_FACT_STATS = {
    "fact_available": 0,
    "blocking_if": 0,
    "doc_question": 0,
    "ax_review_to_ok": 0,  # AX 확인필요 + 비blocking needs_fact → 문제 없음 덮어쓰기
    "needs_fact_other": 0,
    "needs_fact_soft_skip": 0,
    "legacy_force": 0,
}


def reset_needs_fact_stats() -> None:
    for k in NEEDS_FACT_STATS:
        NEEDS_FACT_STATS[k] = 0


def verify_finding(
    clause: str,
    hits: list[dict],
    finding: dict,
    facts: dict,
    *,
    needs_fact_mode: str = "legacy",
    selected_cards: list[dict] | None = None,
    ax_review_to_ok: bool | None = None,
) -> dict:
    """needs_fact_mode: legacy | cards. ax_review_to_ok=None이면 config/verify.yaml."""
    allowed = {h["id"]: h for h in hits}
    dropped_ids = []
    kept = []
    for ev in finding.get("evidence") or []:
        eid = ev.get("id")
        if eid not in allowed:
            dropped_ids.append(eid)
            continue
        kept.append(ev)

    ax_raw_verdict = finding.get("verdict") or "확인 필요"
    verdict = ax_raw_verdict
    review_sources = []
    notes = []
    state = "ok"

    if not finding.get("parse_ok", True) and finding.get("parse_ok") is False:
        review_sources.append("parse_fail")

    if not kept:
        if ax_raw_verdict == "문제 없음":
            notes.append("no_evidence_keep_ok")
        else:
            verdict = "확인 필요"
            review_sources.append("no_evidence")
    cq = finding.get("contract_quote") or ""
    if cq and not _contains(cq, clause):
        state = "needs_review"
        notes.append("quote_mismatch:contract")
        review_sources.append("quote_mismatch")
    for ev in kept:
        rec = allowed.get(ev["id"])
        if rec and ev.get("quote") and not _contains(ev["quote"], rec.get("text") or ""):
            state = "needs_review"
            notes.append(f"quote_mismatch:evidence:{ev['id']}")
            if "quote_mismatch" not in review_sources:
                review_sources.append("quote_mismatch")

    tagged = []
    for ev in kept:
        rec = allowed[ev["id"]]
        tagged.append(
            {
                "id": ev["id"],
                "quote": ev.get("quote") or "",
                "title": rec.get("title") or "",
                "source_tag": SOURCE_TAG.get(rec.get("doc_type") or "", "[자료]"),
                "doc_type": rec.get("doc_type") or "",
            }
        )

    needs_fact = finding.get("needs_fact")
    nf_action = None
    doc_question = None
    if needs_fact:
        if needs_fact_mode == "legacy":
            verdict = "확인 필요"
            notes.append("needs_fact_legacy")
            nf_action = "legacy_force"
            NEEDS_FACT_STATS["legacy_force"] += 1
            review_sources.append("needs_fact")
        else:
            # cards 모드: blocking_if 사실(+when)만 조항 판정을 바꾼다.
            if needs_fact_available(needs_fact, facts):
                notes.append("fact_available")
                nf_action = "fact_available"
                NEEDS_FACT_STATS["fact_available"] += 1
            elif is_blocking_fact(needs_fact, selected_cards) and blocking_triggered(
                needs_fact, clause, selected_cards
            ):
                verdict = "확인 필요"
                notes.append("blocking_if")
                nf_action = "blocking_if"
                NEEDS_FACT_STATS["blocking_if"] += 1
                review_sources.append("needs_fact")
            else:
                # 비-blocking needs_fact: 조항 판정은 바꾸지 않되,
                # AX가 '확인 필요'만 낸 경우는 '문제 없음'으로 두고 문서 질문으로 옮긴다.
                notes.append("doc_question")
                nf_action = "doc_question"
                NEEDS_FACT_STATS["doc_question"] += 1
                doc_question = {"fact": needs_fact, "ax_verdict": ax_raw_verdict}
                if (
                    ax_review_to_ok_enabled(ax_review_to_ok)
                    and ax_raw_verdict == "확인 필요"
                    and not is_blocking_fact(needs_fact, selected_cards)
                ):
                    verdict = "문제 없음"
                    notes.append("ax_review_to_ok")
                    nf_action = "ax_review_to_ok"
                    NEEDS_FACT_STATS["ax_review_to_ok"] += 1
                    # review_sources에서 ax/needs_fact로 '확인 필요' 출처가 남지 않게
                    review_sources[:] = [s for s in review_sources if s not in ("needs_fact", "ax_verdict")]

    if ax_raw_verdict == "확인 필요" and "needs_fact" not in review_sources and "no_evidence" not in review_sources:
        review_sources.append("ax_verdict")

    anomaly = detect_injection(clause)

    rule = numeric_rules(clause, facts)
    ax_verdict = ax_raw_verdict
    why = finding.get("why") or ""
    # violation 목록이 비어 있는 카드만 맞았을 때 A.X 위반·위험은 확인 필요로 낮춘다
    cards = selected_cards or []
    if verdict in ("위반", "위험") and cards:
        if all(not (c.get("violation") or []) for c in cards) and not (rule.get("fired") or []):
            verdict = "확인 필요"
            notes.append("empty_violation_downgrade")
            if "needs_fact" not in review_sources:
                review_sources.append("ax_verdict")
    if rule.get("verdict") and rule["verdict"] != verdict and rule["verdict"] != "문제 없음":
        # 숫자 규칙이 A.X보다 강한 판정일 때만. min_wage는 금액 조항에만 적용됨.
        verdict = rule["verdict"]
        notes.append("rule_override")
        if rule.get("why"):
            why = rule["why"]
            notes.append("rule_why")

    numeric_lock = _numeric_violation_locked(rule, verdict)

    # 최저임금·이자 숫자 규칙 위반: corpus에서 조문을 직접 붙이고 위반 고정
    if numeric_lock:
        law_ev = _rule_law_evidence(rule)
        if law_ev:
            have = {e.get("id") for e in tagged}
            for ev in law_ev:
                if ev.get("id") not in have:
                    tagged.append(ev)
                    have.add(ev.get("id"))
            notes.append("rule_evidence_attached")
        notes.append("rule_numeric_lock")
        verdict = "위반"
    elif verdict == "위반" and not tagged:
        # 그 외 위반+근거0개 → 확인 필요
        verdict = "확인 필요"
        notes.append("no_evidence")
        if "no_evidence" not in review_sources:
            review_sources.append("no_evidence")

    return {
        "verdict": verdict,
        "ax_verdict": ax_verdict,
        "rule": rule,
        "contract_quote": cq,
        "gap": finding.get("gap") or "",
        "why": why,
        "suggestion": finding.get("suggestion") or "",
        "needs_fact": needs_fact,
        "needs_fact_action": nf_action,
        "doc_question": doc_question,
        "review_sources": review_sources,
        "evidence": tagged,
        "dropped_ids": [x for x in dropped_ids if x],
        "state": state,
        "notes": notes,
        "anomaly": anomaly,
        "parse_ok": bool(finding.get("parse_ok")),
        "critical": is_critical(verdict, clause, facts, rule),
        "selected_cards": finding.get("selected_cards") or [c.get("id") for c in (selected_cards or []) if c.get("id")],
        "prompt_tokens_est": finding.get("prompt_tokens_est"),
        "prompt_chars": finding.get("prompt_chars"),
    }


def _norm(text: str) -> str:
    """인용 대조용. 공백·문장부호·따옴표·자리표시·조문 번호·래퍼 태그 차이를 줄인다."""
    t = text or ""
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    # 모델이 붙이는 <contract>…</contract> 등 래퍼
    t = re.sub(r"</?(?:contract|quote|clause|evidence|text)[^>]*>", "", t, flags=re.I)
    t = re.sub(r"[\"'`“”‘’「」『』]", "", t)
    # 제2조 제1항 → 제2조제1항
    t = re.sub(r"제\s*(\d+)\s*조\s*제\s*(\d+)\s*항", r"제\1조제\2항", t)
    t = re.sub(r"제\s*(\d+)\s*조", r"제\1조", t)
    t = re.sub(r"[\s.,，、;；:：!?？·…\-_/\\()（）\[\]【】{}<>《》]", "", t)
    return t


def _contains(needle: str, hay: str) -> bool:
    n, h = _norm(needle), _norm(hay)
    if not n:
        return True
    return n in h


def detect_injection(text: str) -> list[str]:
    hits = []
    low = text or ""
    for pat in INJECT_PATTERNS:
        if pat.lower() in low.lower():
            hits.append(pat)
    return hits


def _is_wage_amount_clause(clause: str) -> bool:
    """시급·월급 금액/최저임금 조항만. 지급일·퇴직금 지급기한 등은 제외."""
    t = clause or ""
    if re.search(r"시급|시간급|시간당|1시간당|시간\s*단위\s*임금|최저임금", t):
        return True
    if re.search(r"(월급|월\s*급여|월\s*임금).{0,16}\d", t):
        return True
    # '임금 … 원' 금액이 있고, 지급일·이내 지급만 말하는 문장은 제외
    if re.search(r"(임금|급여|기본급).{0,24}\d[\d,]*\s*원", t):
        wage_kw = r"시급|시간급|시간당|1시간당|월급|월\s*급여|월\s*임금|시간급"
        if re.search(r"지급일|이내\s*지급|매월\s*\d{1,2}\s*일", t) and not re.search(wage_kw, t):
            return False
        return True
    return False


def _clause_local_wage_facts(clause: str, doc_facts: dict) -> dict | None:
    """조항 문장에 시급·월급 금액이 있을 때만 로컬 facts. 연도는 문서 사실표를 보강."""
    if not _is_wage_amount_clause(clause):
        return None
    from rag.facts import extract_facts

    local = extract_facts(clause or "")
    if local.get("hourly_wage") is None and local.get("monthly_wage") is None:
        return None
    # 적용 연도·계약일은 문서 값 우선(조항 단독에 날짜가 없는 경우)
    out = dict(local)
    for k in ("start_date", "end_date", "apply_year", "date_missing", "date_invalid"):
        if out.get(k) is None and (doc_facts or {}).get(k) is not None:
            out[k] = doc_facts.get(k)
    return out


def _clause_local_interest_values(clause: str) -> list[tuple[str, float]]:
    """조항 자체에서 읽은 이율·지연이율만. 문서 전체 이율은 쓰지 않는다."""
    t = clause or ""
    if not any(k in t for k in ("이자", "이율")):
        return []
    out: list[tuple[str, float]] = []
    try:
        from rag.facts import _collect_interest_rates, extract_facts

        for r in _collect_interest_rates(t):
            rate = r.get("rate")
            if rate is not None:
                out.append(("이자율", float(rate)))
        local = extract_facts(t)
        delay = local.get("delay_interest_rate")
        if delay is not None:
            out.append(("지연 이율", float(delay)))
    except Exception:
        pass
    return out


def numeric_rules(clause: str, facts: dict) -> dict:
    fired = []
    verdict = None
    why = ""
    # 최저임금: 조항 안에 시급·월급 금액이 직접 있을 때만
    local_wage = _clause_local_wage_facts(clause, facts)
    if local_wage is not None:
        wage = min_wage_verdict(local_wage)
        if wage and wage.get("verdict") in ("위반", "확인 필요"):
            fired.extend(wage.get("fired") or ["min_wage"])
            verdict = wage["verdict"]
            why = wage.get("why") or ""
    hours = facts.get("work_hours_per_day")
    brk = facts.get("break_minutes")
    if hours is not None and brk is not None and any(k in clause for k in ("휴게", "근로시간", "근무시간")):
        need = 0
        if hours >= 8:
            need = 60
        elif hours >= 4:
            need = 30
        if brk < need:
            fired.append("break")
            verdict = "위반"
            why = (why + " " if why else "") + f"1일 {hours}시간 근로에 휴게 {brk}분은 기준 {need}분 미만이다."
    rate = facts.get("rent_increase_rate")
    if rate is not None and rate > LEASE_INCREASE_CAP and any(k in clause for k in ("증액", "인상")):
        fired.append("lease_increase")
        verdict = "위반"
        why = (why + " " if why else "") + f"증액률 {rate}는 상한 {LEASE_INCREASE_CAP}을 넘는다."
    # 이자: 조항 로컬(금액형 포함) 이율만. 문서 max로 위반을 만들지 않음.
    for name, val in _clause_local_interest_values(clause):
        if val is not None and val > MAX_INTEREST:
            fired.append("interest")
            verdict = "위반"
            pct = _pct_label(val)
            cap = _pct_label(MAX_INTEREST)
            why = (why + " " if why else "") + f"연 {pct}로 최고이자율 연 {cap}를 넘습니다"
            break
    return {"fired": fired, "verdict": verdict, "why": why.strip()}


def _pct_label(rate: float) -> str:
    pct = float(rate) * 100.0
    if abs(pct - round(pct)) < 1e-9:
        return f"{int(round(pct))}%"
    return f"{pct:g}%"


_NUMERIC_LOCK_FIRED = frozenset({"min_wage", "interest"})
_CORPUS_EV_CACHE: dict[str, dict | None] = {}


def _numeric_violation_locked(rule: dict | None, verdict: str | None = None) -> bool:
    """최저임금·이자 숫자 규칙이 위반을 낸 경우. 이후 단계에서 내리면 안 된다."""
    if not rule:
        return False
    if verdict is not None and verdict != "위반" and rule.get("verdict") != "위반":
        return False
    fired = set(rule.get("fired") or [])
    if not (fired & _NUMERIC_LOCK_FIRED):
        return False
    return rule.get("verdict") == "위반" or verdict == "위반"


def _corpus_evidence_by_id(rec_id: str) -> dict | None:
    """검색 없이 corpus 레코드를 근거 형태로 반환."""
    if rec_id in _CORPUS_EV_CACHE:
        return dict(_CORPUS_EV_CACHE[rec_id]) if _CORPUS_EV_CACHE[rec_id] else None
    try:
        import json

        from rag.paths import CORPUS

        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        records = data.get("records") or data if isinstance(data, list) else (data.get("records") or [])
        for rec in records:
            if rec.get("id") == rec_id:
                item = {
                    "id": rec.get("id"),
                    "quote": (rec.get("text") or "").strip(),
                    "title": rec.get("title") or rec_id,
                    "source_tag": "[법령]",
                    "doc_type": rec.get("doc_type") or "법률",
                }
                _CORPUS_EV_CACHE[rec_id] = item
                return dict(item)
    except Exception:
        pass
    _CORPUS_EV_CACHE[rec_id] = None
    return None


def _rule_law_evidence(rule: dict) -> list[dict]:
    """숫자 규칙 위반에 붙일 법령 근거. 검색 설정은 건드리지 않는다."""
    fired = rule.get("fired") or []
    out: list[dict] = []
    if "min_wage" in fired:
        ev = _corpus_evidence_by_id("law:최저임금법:6:1")
        if ev:
            out.append(ev)
    if "interest" in fired:
        art2 = _corpus_evidence_by_id("law:이자제한법:2")
        if art2:
            out.append(art2)
        notice = _corpus_evidence_by_id("notice:이자제한법 제2조제1항의 최고이자율에 관한 규정:본문")
        if notice:
            out.append(notice)
    return out


def is_critical(verdict: str, clause: str, facts: dict, rule: dict) -> list[str]:
    if verdict not in ("위반", "위험"):
        return []
    labels = []
    if "min_wage" in (rule.get("fired") or []) or (min_wage_verdict(facts) or {}).get("verdict") == "위반":
        if any(k in clause for k in ("시급", "임금")):
            labels.append("최저임금 미달")
    if re.search(r"위약금|벌금|손해배상액을?\s*예정", clause):
        labels.append("위약금 예정")
    if re.search(r"전입신고.{0,12}(금지|불가|하지\s*말)", clause):
        labels.append("전입신고 금지")
    if re.search(r"갱신(요구권)?.{0,16}(포기|포기한다|행사하지)", clause):
        labels.append("갱신요구권 포기")
    if "interest" in (rule.get("fired") or []):
        labels.append("이자 20% 초과")
    return labels
