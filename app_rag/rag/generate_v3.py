# -*- coding: utf-8 -*-
"""A.X 4.0 Light (llama-server 8082). temperature/max_tokens/ctx는 기존 값 유지."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from rag.criteria import format_criteria_block, select_cards
from rag.facts import facts_for_prompt
from rag.paths import AX_HEALTH, AX_MAX_TOKENS, AX_TEMPERATURE, AX_TIMEOUT, AX_URL, JUDGE_PROMPT

JUDGE_TMPL = JUDGE_PROMPT.read_text(encoding="utf-8")

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
    msg = js["choices"][0]["message"]
    return {"content": msg.get("content") or "", "error": None}


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


def build_judge_prompt(clause: str, facts: dict, hits: list[dict], *, use_criteria: bool = False) -> tuple[str, list[dict]]:
    material = []
    for hit in hits:
        material.append(f"- id: {hit['id']}\n  title: {hit['title']}\n  text: {hit['text']}")
    cards: list[dict] = []
    if use_criteria and (facts.get("domain") or "") == "LAB":
        cards = select_cards(clause, limit=2)
        criteria = format_criteria_block(cards, facts)
    else:
        criteria = "(없음)"
    # 구 템플릿에 {criteria}가 없으면 그냥 둠
    user = JUDGE_TMPL
    if "{criteria}" not in user:
        user = user.replace("근거(이 id 중에서만 고른다):", "기준 카드:\n<criteria>\n{criteria}\n</criteria>\n\n근거(이 id 중에서만 고른다):")
    user = (
        user.replace("{clause}", clause)
        .replace("{facts}", facts_for_prompt(facts))
        .replace("{criteria}", criteria)
        .replace("{evidence}", "\n".join(material) if material else "(없음)")
    )
    return user, cards


def generate_finding(clause: str, facts: dict, hits: list[dict], *, use_criteria: bool = False) -> dict:
    user, cards = build_judge_prompt(clause, facts, hits, use_criteria=use_criteria)
    last_error = None
    last_raw = ""
    parsed = None
    ok = False
    for _attempt in range(2):
        resp = chat_ax([{"role": "user", "content": user}], max_tokens=AX_MAX_TOKENS)
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
    row["selected_cards"] = [c.get("id") for c in cards]
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
