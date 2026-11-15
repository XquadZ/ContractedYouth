# -*- coding: utf-8 -*-
"""A.X 4.0 Light (llama-server 8082). temperature/max_tokens/ctx는 기존 값 유지."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request

from rag.criteria import format_criteria_block, merge_hits_with_card_basis, select_cards
from rag.facts import facts_for_prompt
from rag.paths import APP, AX_HEALTH, AX_MAX_TOKENS, AX_TEMPERATURE, AX_TIMEOUT, AX_URL, JUDGE_PROMPT, PROMPTS

JUDGE_TMPL = JUDGE_PROMPT.read_text(encoding="utf-8")
JUDGE_NEUTRAL = (PROMPTS / "judge_neutral.txt").read_text(encoding="utf-8")

# 평가용 엔드포인트 오버라이드(기본 None → A.X 8082). 기본 설정/AX_URL은 바꾸지 않는다.
_LLM_URL_OVERRIDE: str | None = None
_LLM_HEALTH_OVERRIDE: str | None = None


def set_llm_endpoint(url: str | None = None, health: str | None = None) -> None:
    """비교 평가 때만 호출. None이면 A.X 기본(8082)으로 복귀."""
    global _LLM_URL_OVERRIDE, _LLM_HEALTH_OVERRIDE
    _LLM_URL_OVERRIDE = url
    _LLM_HEALTH_OVERRIDE = health


def ax_up() -> bool:
    health = _LLM_HEALTH_OVERRIDE or AX_HEALTH
    try:
        with urllib.request.urlopen(health, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def parse_json_output(text: str):
    if not text:
        return None, False
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None, False
    blob = match.group(0)
    try:
        return json.loads(blob), True
    except json.JSONDecodeError:
        try:
            blob2 = re.sub(r",\s*}", "}", blob)
            blob2 = re.sub(r",\s*]", "]", blob2)
            return json.loads(blob2), True
        except json.JSONDecodeError:
            return None, False


def chat_ax(messages: list[dict], max_tokens: int = AX_MAX_TOKENS) -> dict:
    body = {"messages": messages, "temperature": AX_TEMPERATURE, "max_tokens": max_tokens}
    data = json.dumps(body).encode("utf-8")
    url = _LLM_URL_OVERRIDE or AX_URL
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=AX_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {"content": "", "error": detail[:500]}
    except Exception as exc:
        return {"content": "", "error": str(exc)}
    js = json.loads(raw)
    choice = js["choices"][0]
    msg = choice["message"]
    return {
        "content": msg.get("content") or "",
        "error": None,
        "finish_reason": choice.get("finish_reason"),
    }


def _blank_finding() -> dict:
    return {
        "verdict": "확인 필요",
        "contract_quote": "",
        "gap": "애매",
        "why": "",
        "evidence": [],
        "suggestion": "",
        "needs_fact": None,
        "parse_ok": False,
        "raw": "",
        "error": None,
        "selected_cards": [],
        "prompt_chars": 0,
        "prompt_tokens_est": 0,
    }


# tuned: A.X 실험 중 추가된 2줄 포함. neutral: 처음 설계 2줄만.
CRITERIA_EXTRA_RULES_NEUTRAL = (
    '- 조항이 criteria의 safe에 해당하고 violation·check_if에 해당하지 않으면 "문제 없음"으로 답한다.\n'
    '- check_if에 해당할 때만 "확인 필요"로 답하고, needs_fact에 그 사실을 적는다.\n'
)
CRITERIA_EXTRA_RULES_TUNED = (
    CRITERIA_EXTRA_RULES_NEUTRAL
    + '- criteria의 violation 목록이 비어 있으면 "위반"·"위험"으로 답하지 않는다.\n'
    + '- 근거 id가 부족해도 safe에 해당하면 "문제 없음"으로 답한다.\n'
)
# 하위 호환 이름
CRITERIA_EXTRA_RULES = CRITERIA_EXTRA_RULES_TUNED


def _judge_tmpl_and_extra() -> tuple[str, str]:
    try:
        from rag.settings import get_cards_version

        ver = get_cards_version()
    except Exception:
        ver = "tuned"
    if ver == "neutral":
        return JUDGE_NEUTRAL, CRITERIA_EXTRA_RULES_NEUTRAL
    return JUDGE_TMPL, CRITERIA_EXTRA_RULES_TUNED


def build_judge_prompt(clause: str, facts: dict, hits: list[dict], *, use_criteria: bool = False) -> tuple[str, list[dict], list[dict]]:
    cards: list[dict] = []
    domain = facts.get("domain") or "LAB"
    if use_criteria:
        cards = select_cards(clause, limit=2, domain=domain)
        # 검색 상위 + 카드 basis (최대 3개 추가). FIX_ROUND3 의도적 설계 변경.
        hits = merge_hits_with_card_basis(hits, cards, max_extra=3)
        criteria = format_criteria_block(cards, facts)
    else:
        criteria = "(없음)"
    material = []
    for hit in hits:
        material.append(f"- id: {hit['id']}\n  title: {hit.get('title')}\n  text: {hit.get('text')}")
    user, rules = _judge_tmpl_and_extra()
    # 카드가 실제로 붙을 때만 카드 전용 지시를 넣는다.
    extra = rules if cards else ""
    if "{criteria}" not in user:
        user = user.replace("근거(이 id 중에서만 고른다):", "기준 카드:\n<criteria>\n{criteria}\n</criteria>\n\n근거(이 id 중에서만 고른다):")
    user = (
        user.replace("{clause}", clause)
        .replace("{facts}", facts_for_prompt(facts))
        .replace("{criteria}", criteria)
        .replace("{criteria_extra_rules}", extra)
        .replace("{evidence}", "\n".join(material) if material else "(없음)")
    )
    return user, cards, hits


def generate_finding(clause: str, facts: dict, hits: list[dict], *, use_criteria: bool = False) -> dict:
    user, cards, hits = build_judge_prompt(clause, facts, hits, use_criteria=use_criteria)
    last_error = None
    last_raw = ""
    last_finish = None
    parsed = None
    ok = False
    for _attempt in range(2):
        resp = chat_ax([{"role": "user", "content": user}], max_tokens=AX_MAX_TOKENS)
        last_finish = resp.get("finish_reason")
        if resp.get("error"):
            last_error = resp["error"]
            last_raw = ""
            continue
        last_raw = resp.get("content") or ""
        parsed, ok = parse_json_output(last_raw)
        if ok:
            break
    row = _blank_finding()
    row["raw"] = last_raw
    row["error"] = last_error
    row["finish_reason"] = last_finish
    row["prompt_sha256"] = hashlib.sha256(user.encode("utf-8")).hexdigest()
    row["selected_cards"] = [c.get("id") for c in cards]
    row["hits_for_verify"] = hits  # basis 병합 후 목록
    row["prompt_chars"] = len(user)
    # 한국어 대략 토큰 ≈ chars/2 ~ chars/1.5; 보수적으로 chars/2
    row["prompt_tokens_est"] = max(1, len(user) // 2)
    if not ok or not isinstance(parsed, dict):
        row["why"] = "모델 출력을 JSON으로 읽지 못했다."
        row["parse_ok"] = False
        return row
    verdict = str(parsed.get("verdict") or "확인 필요").strip()
    if verdict not in ("위반", "위험", "확인 필요", "문제 없음"):
        verdict = "확인 필요"
    evidence = []
    for item in parsed.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if eid:
            evidence.append({"id": eid, "quote": quote})
    needs = parsed.get("needs_fact")
    if needs in ("", "null", "None"):
        needs = None
    elif needs is not None:
        needs = str(needs).strip() or None
    row.update(
        {
            "verdict": verdict,
            "contract_quote": str(parsed.get("contract_quote") or "").strip(),
            "gap": str(parsed.get("gap") or "").strip(),
            "why": str(parsed.get("why") or "").strip(),
            "evidence": evidence,
            "suggestion": str(parsed.get("suggestion") or "").strip(),
            "needs_fact": needs,
            "parse_ok": True,
            "error": None,
        }
    )
    return row
