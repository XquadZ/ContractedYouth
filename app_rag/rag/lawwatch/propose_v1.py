# -*- coding: utf-8 -*-
"""카드 수정안 생성(EXAONE)과 코드 검사."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rag.lawwatch.byeol import quote_in_source
from rag.lawwatch.paths import CRITERIA_PROPOSALS, LAWWATCH_OUT
from rag.lawwatch.versions_io import card_fields, dump_yaml
from rag.yamlutil import load as load_yaml

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


def _card_char_len(proposed: dict) -> int:
    parts = []
    for key in ("safe", "violation", "check_if"):
        for line in proposed.get(key) or []:
            parts.append(str(line))
    return sum(len(p) for p in parts)


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def validate_proposal(
    proposed: dict,
    *,
    before_text: str,
    after_text: str,
    byeol_text: str,
    rule_quote: str | None,
    corpus_ids: set[str] | None = None,
) -> dict:
    errors = []
    if not isinstance(proposed, dict):
        return {"ok": False, "errors": ["proposed not dict"], "apply_rule": "unknown"}
    for key in ("safe", "violation", "check_if", "basis"):
        if key not in proposed:
            errors.append(f"missing:{key}")
    length = _card_char_len(proposed)
    if length > 500:
        errors.append(f"length:{length}>500")
    basis = [str(x) for x in (proposed.get("basis") or [])]
    if corpus_ids is not None:
        for bid in basis:
            if bid not in corpus_ids and not any(bid.startswith(i + ":") or i.startswith(bid + ":") for i in corpus_ids):
                # 새 법령 모음에 없으면 오류 — 느슨: prefix 법령명만 있어도 통과하지 않음
                if bid not in corpus_ids:
                    errors.append(f"basis_missing:{bid}")
    # 수정안 숫자가 전/후 조문에 존재
    prop_text = json.dumps(proposed, ensure_ascii=False)
    nums = _numbers_in(prop_text)
    allowed = _numbers_in(before_text) | _numbers_in(after_text) | _numbers_in(byeol_text)
    # 조문 번호·연도 등은 카드에 원래 있던 값일 수 있어, 새 숫자만 엄격히 보려면 호출측에서
    strange = [n for n in nums if n not in allowed and len(n) >= 2]
    # 너무 엄격하면 전부 실패 → 전후에 없는 4자리 이상 금액/%만 체크
    for n in nums:
        if len(n) >= 4 and n not in allowed:
            errors.append(f"number_not_in_law:{n}")
    apply_rule = proposed.get("apply_rule") or "unknown"
    rq = rule_quote or proposed.get("rule_quote")
    if rq and not quote_in_source(str(rq), byeol_text):
        errors.append("rule_quote_not_in_byeol")
        apply_rule = "unknown"
        rq = None
    if errors:
        apply_rule = "unknown"
    return {
        "ok": not errors,
        "errors": errors,
        "length": length,
        "apply_rule": apply_rule,
        "rule_quote": rq,
        "manual": bool(errors),
    }


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


def build_prompt(card: dict, before: str, after: str, byeol: str) -> str:
    return (
        "다음 기준 카드를 법령 개정에 맞게 수정할지 판단하고 JSON으로만 답하라.\n"
        "제약: 바뀐 조문 관련만 수정, 카드 본문(safe+violation+check_if) 합 500자 이내, "
        "조문에 없는 내용·숫자 금지, 정답 데이터 문장 금지.\n"
        '형식: {"needs_change": bool, "reason": "...", "proposed": {"safe":[], "violation":[], "check_if":[], "basis":[]}, '
        '"apply_rule": "contract_date|in_force|performance_period|unknown", "rule_quote": "부칙 문장"}\n\n'
        f"<card>\n{json.dumps(card_fields(card), ensure_ascii=False, indent=2)}\n</card>\n\n"
        f"<before>\n{before}\n</before>\n\n"
        f"<after>\n{after}\n</after>\n\n"
        f"<byeol>\n{byeol}\n</byeol>\n"
    )


def propose_for_card(
    card: dict,
    *,
    before_text: str,
    after_text: str,
    byeol_text: str,
    apply_rule_hint: str | None = None,
    rule_quote_hint: str | None = None,
    wait_gpu: bool = True,
    corpus_ids: set[str] | None = None,
) -> dict:
    CRITERIA_PROPOSALS.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    card_id = card.get("id") or "UNKNOWN"
    if wait_gpu:
        # 간단 대기: health만 확인 (다른 분석 점유는 별도 잠금 없음)
        for _ in range(30):
            if _exaone_up():
                break
            time.sleep(2)

    llm = {"parse_ok": False, "skipped": True}
    proposed = None
    needs_change = True
    reason = "LLM 미사용 — 수동 초안"
    apply_rule = apply_rule_hint or "unknown"
    rule_quote = rule_quote_hint

    if _exaone_up():
        llm = call_exaone_json(build_prompt(card, before_text, after_text, byeol_text))
        if llm.get("parse_ok"):
            j = llm["json"]
            needs_change = bool(j.get("needs_change", True))
            reason = j.get("reason") or ""
            proposed = j.get("proposed")
            apply_rule = j.get("apply_rule") or apply_rule
            rule_quote = j.get("rule_quote") or rule_quote

    if proposed is None:
        # 휴리스틱 초안: 숫자만 치환
        proposed = card_fields(card)
        if "24" in before_text and "20" in after_text:
            def repl_list(xs):
                return [str(x).replace("24%", "20%").replace("연 24", "연 20").replace("24퍼센트", "20퍼센트") for x in (xs or [])]
            proposed["safe"] = repl_list(proposed.get("safe"))
            proposed["violation"] = repl_list(proposed.get("violation"))
            reason = reason or "휴리스틱: 24→20 치환"
        needs_change = True

    rule_quote_raw = rule_quote
    check = validate_proposal(
        {**proposed, "apply_rule": apply_rule, "rule_quote": rule_quote},
        before_text=before_text,
        after_text=after_text,
        byeol_text=byeol_text,
        rule_quote=rule_quote,
        corpus_ids=corpus_ids,
    )
    status = "대기"
    if check.get("manual"):
        status = "수동 수정 필요"
        apply_rule = "unknown"

    payload = {
        "card_id": card_id,
        "day": day,
        "status": status,
        "needs_change": needs_change,
        "reason": reason,
        "before_card": card_fields(card),
        "proposed": proposed,
        "apply_rule": check.get("apply_rule") or apply_rule,
        "rule_quote": check.get("rule_quote"),
        "rule_quote_raw": rule_quote_raw,
        "validation": check,
        "llm_parse_ok": bool(llm.get("parse_ok")),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    out = CRITERIA_PROPOSALS / f"{day}_{card_id}.yaml"
    dump_yaml(payload, out)
    payload["path"] = str(out)
    return payload


def propose_numeric_table(kind: str, rows: list[dict]) -> dict:
    """최저임금·최고이자율 표 수정안."""
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
