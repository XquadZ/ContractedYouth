# -*- coding: utf-8 -*-
"""A.X 4.0 Light (llama-server 8082). temperature/max_tokens/ctx는 기존 값 유지."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from rag.facts import facts_for_prompt
from rag.paths import AX_HEALTH, AX_MAX_TOKENS, AX_TEMPERATURE, AX_TIMEOUT, AX_URL, JUDGE_PROMPT

JUDGE_TMPL = JUDGE_PROMPT.read_text(encoding="utf-8")


def ax_up() -> bool:
    try:
        with urllib.request.urlopen(AX_HEALTH, timeout=2) as response:
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
    req = urllib.request.Request(AX_URL, data=data, headers={"Content-Type": "application/json"}, method="POST")
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
    }


def generate_finding(clause: str, facts: dict, hits: list[dict]) -> dict:
    material = []
    for hit in hits:
        material.append(f"- id: {hit['id']}\n  title: {hit['title']}\n  text: {hit['text']}")
    user = (
        JUDGE_TMPL.replace("{clause}", clause)
        .replace("{facts}", facts_for_prompt(facts))
        .replace("{evidence}", "\n".join(material) if material else "(없음)")
    )
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
