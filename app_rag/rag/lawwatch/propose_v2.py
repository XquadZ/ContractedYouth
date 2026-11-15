# -*- coding: utf-8 -*-
"""카드 수정안 생성(EXAONE)과 코드 검사.

적용 근거 문장은 모델이 베끼지 않는다.
코드가 부칙 후보를 번호로 주고, 모델은 rule_index·apply_rule만 고른다.
rule_quote는 코드가 후보 원문에서 채운다.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rag.lawwatch.byeol import (
    extract_rule_candidates,
    fill_rule_from_index,
    format_candidates_for_prompt,
    quote_in_source,
)
from rag.lawwatch.paths import CRITERIA_PROPOSALS
from rag.lawwatch.versions_io import card_fields, dump_yaml

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

APPLY_RULES = ("contract_date", "in_force", "performance_period", "unknown")


def _card_char_len(proposed: dict) -> int:
    parts = []
    for key in ("safe", "violation", "check_if"):
        for line in proposed.get(key) or []:
            parts.append(str(line))
    return sum(len(p) for p in parts)


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def validate_card_body(
    proposed: dict,
    *,
    before_text: str,
    after_text: str,
    corpus_ids: set[str] | None = None,
) -> dict:
    """(가) 카드 본문 수정안 검사: YAML 키, 500자, basis, 숫자가 조문 전/후에 있음."""
    errors: list[str] = []
    if not isinstance(proposed, dict):
        return {"ok": False, "errors": ["proposed not dict"], "length": 0}
    for key in ("safe", "violation", "check_if", "basis"):
        if key not in proposed:
            errors.append(f"missing:{key}")
    length = _card_char_len(proposed) if isinstance(proposed, dict) else 0
    if length > 500:
        errors.append(f"length:{length}>500")
    basis = [str(x) for x in (proposed.get("basis") or [])] if isinstance(proposed, dict) else []
    if corpus_ids is not None:
        for bid in basis:
            if bid not in corpus_ids and not any(
                bid.startswith(i + ":") or i.startswith(bid + ":") for i in corpus_ids
            ):
                if bid not in corpus_ids:
                    errors.append(f"basis_missing:{bid}")
    prop_text = json.dumps(proposed, ensure_ascii=False) if isinstance(proposed, dict) else ""
    nums = _numbers_in(prop_text)
    allowed = _numbers_in(before_text) | _numbers_in(after_text)
    for n in nums:
        if len(n) >= 4 and n not in allowed:
            errors.append(f"number_not_in_law:{n}")
    return {"ok": not errors, "errors": errors, "length": length}


def validate_apply_rule(
    *,
    apply_rule: str | None,
    rule_index,
    rule_quote: str | None,
    candidates: list[dict],
) -> dict:
    """(나) 적용 근거 검사."""
    errors: list[str] = []
    filled = fill_rule_from_index(candidates, rule_index)
    if not filled["ok"]:
        errors.append(filled["reason"] or "rule_index_invalid")
        return {
            "ok": False,
            "errors": errors,
            "apply_rule": "unknown",
            "rule_index": None,
            "rule_quote": None,
        }
    quote = filled["rule_quote"]
    # 후보 원문과 일치해야 함(코드가 채웠으므로 기본적으로 참)
    cand_blob = "\n".join(c["text"] for c in candidates)
    if not quote_in_source(quote or "", cand_blob):
        errors.append("rule_quote_not_in_candidates")
    rule = (apply_rule or "unknown").strip()
    if rule not in APPLY_RULES:
        errors.append(f"apply_rule_invalid:{rule}")
        rule = "unknown"
    if rule == "unknown":
        errors.append("apply_rule_unknown")
    return {
        "ok": not errors,
        "errors": errors,
        "apply_rule": rule if not errors else "unknown",
        "rule_index": filled["rule_index"],
        "rule_quote": quote,
    }


def validate_proposal_split(
    proposed: dict,
    *,
    before_text: str,
    after_text: str,
    apply_rule: str | None,
    rule_index,
    candidates: list[dict],
    corpus_ids: set[str] | None = None,
) -> dict:
    body = validate_card_body(
        proposed, before_text=before_text, after_text=after_text, corpus_ids=corpus_ids
    )
    # rule_quote는 코드가 index로 채움
    filled = fill_rule_from_index(candidates, rule_index)
    if filled["rule_index"] is None:
        apply_rule_eff = "unknown"
    else:
        apply_rule_eff = apply_rule or "unknown"
    rule = validate_apply_rule(
        apply_rule=apply_rule_eff,
        rule_index=filled["rule_index"],
        rule_quote=filled["rule_quote"],
        candidates=candidates,
    )
    # 상태
    if not body["ok"]:
        status = "수동 수정 필요"
        approvable = False
    elif body["ok"] and not rule["ok"]:
        status = "본문 승인 가능 · 적용 기준은 관리자가 선택"
        approvable = "body_only"
    else:
        status = "대기"
        approvable = True
    return {
        "body": body,
        "rule": rule,
        "ok": body["ok"] and rule["ok"],
        "body_ok": body["ok"],
        "rule_ok": rule["ok"],
        "status": status,
        "approvable": approvable,
        "apply_rule": rule.get("apply_rule") or "unknown",
        "rule_index": rule.get("rule_index"),
        "rule_quote": rule.get("rule_quote"),
        # 하위 호환
        "errors": (body.get("errors") or []) + (rule.get("errors") or []),
        "manual": not body["ok"],
        "length": body.get("length"),
    }


# 하위 호환 이름
def validate_proposal(proposed: dict, **kwargs) -> dict:
    candidates = kwargs.get("candidates") or []
    return validate_proposal_split(
        proposed,
        before_text=kwargs.get("before_text") or "",
        after_text=kwargs.get("after_text") or "",
        apply_rule=kwargs.get("apply_rule"),
        rule_index=kwargs.get("rule_index"),
        candidates=candidates,
        corpus_ids=kwargs.get("corpus_ids"),
    )


def _exaone_url() -> str:
    return "http://127.0.0.1:8083/v1/chat/completions"


def _exaone_up() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8083/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def call_exaone_json(prompt: str, *, timeout: int = 120) -> dict:
    import urllib.request

    body = json.dumps(
        {
            "model": "exaone",
            "temperature": 0,
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": "당신은 한국 법령 카드 편집기다. JSON만 출력한다."},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        _exaone_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {"raw": text, "parse_ok": False}
    try:
        return {"raw": text, "parse_ok": True, "json": json.loads(m.group(0))}
    except json.JSONDecodeError:
        return {"raw": text, "parse_ok": False}


def build_prompt(card: dict, before: str, after: str, candidates_block: str) -> str:
    return (
        "다음 기준 카드를 법령 개정에 맞게 수정할지 판단하고 JSON으로만 답하라.\n"
        "제약: 바뀐 조문 관련만 수정, 카드 본문(safe+violation+check_if) 합 500자 이내, "
        "조문에 없는 내용·숫자 금지, 정답 데이터 문장 금지.\n"
        "적용 근거 문장을 직접 쓰지 마라. 아래 후보 번호만 골라라. "
        "맞는 후보가 없으면 rule_index는 null 이고 apply_rule은 unknown.\n"
        '형식: {"needs_change": bool, "reason": "...", '
        '"proposed": {"safe":[], "violation":[], "check_if":[], "basis":[]}, '
        '"rule_index": 번호또는null, '
        '"apply_rule": "contract_date|in_force|performance_period|unknown"}\n\n'
        f"<card>\n{json.dumps(card_fields(card), ensure_ascii=False, indent=2)}\n</card>\n\n"
        f"<before>\n{before}\n</before>\n\n"
        f"<after>\n{after}\n</after>\n\n"
        f"<rule_candidates>\n{candidates_block}\n</rule_candidates>\n"
    )


def propose_for_card(
    card: dict,
    *,
    before_text: str,
    after_text: str,
    byeol_text: str = "",
    byeol_units: list[dict] | None = None,
    announced: str | None = None,
    effective: str | None = None,
    extra_candidate_lines: list[str] | None = None,
    apply_rule_hint: str | None = None,
    rule_quote_hint: str | None = None,
    wait_gpu: bool = True,
    corpus_ids: set[str] | None = None,
    out_name: str | None = None,
) -> dict:
    CRITERIA_PROPOSALS.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    card_id = card.get("id") or "UNKNOWN"

    units = list(byeol_units or [])
    if not units and byeol_text:
        units = [{"lines": [ln.strip() for ln in byeol_text.splitlines() if ln.strip()], "text": byeol_text}]
    extra = list(extra_candidate_lines or [])
    if rule_quote_hint and rule_quote_hint not in extra:
        # hint는 후보에만 넣고 모델이 베끼게 하지 않음(번호로만)
        extra.append(rule_quote_hint)
    candidates = extract_rule_candidates(
        units, announced=announced, effective=effective, extra_lines=extra or None
    )
    cand_block = format_candidates_for_prompt(candidates)

    if wait_gpu:
        for _ in range(30):
            if _exaone_up():
                break
            time.sleep(2)

    llm = {"parse_ok": False, "skipped": True}
    proposed = None
    needs_change = True
    reason = "LLM 미사용 — 수동 초안"
    apply_rule = apply_rule_hint or "unknown"
    rule_index = None

    if _exaone_up():
        llm = call_exaone_json(build_prompt(card, before_text, after_text, cand_block))
        if llm.get("parse_ok"):
            j = llm["json"]
            needs_change = bool(j.get("needs_change", True))
            reason = j.get("reason") or ""
            proposed = j.get("proposed")
            apply_rule = j.get("apply_rule") or apply_rule
            rule_index = j.get("rule_index", None)

    if proposed is None:
        proposed = card_fields(card)
        if "24" in before_text and "20" in after_text:

            def repl_list(xs):
                return [
                    str(x)
                    .replace("24%", "20%")
                    .replace("연 24", "연 20")
                    .replace("24퍼센트", "20퍼센트")
                    for x in (xs or [])
                ]

            proposed["safe"] = repl_list(proposed.get("safe"))
            proposed["violation"] = repl_list(proposed.get("violation"))
            reason = reason or "휴리스틱: 24→20 치환"
        needs_change = True

    # rule_quote는 코드가 채움
    filled = fill_rule_from_index(candidates, rule_index)
    if not filled["ok"]:
        apply_rule = "unknown"
    check = validate_proposal_split(
        proposed,
        before_text=before_text,
        after_text=after_text,
        apply_rule=apply_rule,
        rule_index=filled["rule_index"],
        candidates=candidates,
        corpus_ids=corpus_ids,
    )

    payload = {
        "card_id": card_id,
        "day": day,
        "status": check["status"],
        "needs_change": needs_change,
        "reason": reason,
        "before_card": card_fields(card),
        "proposed": proposed,
        "rule_candidates": candidates,
        "rule_index": check.get("rule_index"),
        "rule_index_model": rule_index,
        "apply_rule": check.get("apply_rule") or "unknown",
        "apply_rule_model": apply_rule if filled["ok"] else (apply_rule if rule_index is not None else "unknown"),
        "rule_quote": check.get("rule_quote"),
        "validation": check,
        "validation_body": check.get("body"),
        "validation_rule": check.get("rule"),
        "llm_parse_ok": bool(llm.get("parse_ok")),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    fname = out_name or f"{day}_{card_id}.yaml"
    out = CRITERIA_PROPOSALS / fname
    dump_yaml(payload, out)
    payload["path"] = str(out)
    return payload


def propose_numeric_table(kind: str, rows: list[dict]) -> dict:
    CRITERIA_PROPOSALS.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    payload = {
        "kind": kind,
        "day": day,
        "status": "대기",
        "rows": rows,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    out = CRITERIA_PROPOSALS / f"{day}_{kind}_table.yaml"
    dump_yaml(payload, out)
    payload["path"] = str(out)
    return payload
