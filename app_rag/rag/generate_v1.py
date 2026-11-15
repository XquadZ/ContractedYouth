# -*- coding: utf-8 -*-
"""A.X 4.0 Light (llama-server 8082)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from rag.paths_v1 import AX_HEALTH, AX_URL, PROMPTS
from rag.retrieve_v1 import render_hits

SYSTEM_FINDING = (PROMPTS / "system_finding.txt").read_text(encoding="utf-8")
USER_FINDING = (PROMPTS / "user_finding.txt").read_text(encoding="utf-8")
SYSTEM_OVERVIEW = (PROMPTS / "system_overview.txt").read_text(encoding="utf-8")
USER_OVERVIEW = (PROMPTS / "user_overview.txt").read_text(encoding="utf-8")


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


def chat_ax(messages: list[dict], max_tokens: int = 512) -> dict:
    body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(AX_URL, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {"content": "", "error": detail[:500]}
    except Exception as exc:
        return {"content": "", "error": str(exc)}
    js = json.loads(raw)
    msg = js["choices"][0]["message"]
    return {"content": msg.get("content") or "", "error": None}


def _boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
    return None


def generate_finding(clause: str, hits: list[dict]) -> dict:
    allowed = {h["id"] for h in hits}
    material = render_hits(hits)
    user = USER_FINDING.replace("{clause}", clause)
    if material:
        user = f"<자료>\n{material}\n</자료>\n\n{user}"
    resp = chat_ax(
        [{"role": "system", "content": SYSTEM_FINDING}, {"role": "user", "content": user}],
        max_tokens=512,
    )
    if resp.get("error"):
        return {"risky": None, "reason": "모델 서버에 연결하지 못했다.", "used_ids": [], "parse_ok": False, "error": resp["error"]}
    parsed, ok = parse_json_output(resp["content"])
    risky = _boolish((parsed or {}).get("risky")) if ok else None
    used = []
    if ok:
        for item in (parsed or {}).get("used_ids") or []:
            sid = str(item).strip()
            if sid in allowed and sid not in used:
                used.append(sid)
    reason = str((parsed or {}).get("reason") or "").strip()
    if not ok:
        reason = "모델 출력을 JSON으로 읽지 못했다."
        risky = None
    return {"risky": risky, "reason": reason, "used_ids": used, "parse_ok": ok, "error": None}


def generate_overview(findings: list[dict]) -> dict:
    lines = []
    for row in findings:
        flag = {True: "위험", False: "문제없음", None: "판단보류"}.get(row.get("risky"), "판단보류")
        snippet = (row.get("clause") or "").replace("\n", " ")[:80]
        lines.append(f"- [{flag}] {snippet} | {row.get('reason') or ''}")
    user = USER_OVERVIEW.replace("{findings}", "\n".join(lines))
    resp = chat_ax(
        [{"role": "system", "content": SYSTEM_OVERVIEW}, {"role": "user", "content": user}],
        max_tokens=768,
    )
    if resp.get("error"):
        return {"overview": "", "parse_ok": False, "error": resp["error"]}
    parsed, ok = parse_json_output(resp["content"])
    overview = str((parsed or {}).get("overview") or "").strip() if ok else ""
    return {"overview": overview, "parse_ok": ok, "error": None}
