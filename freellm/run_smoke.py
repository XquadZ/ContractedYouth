# -*- coding: utf-8 -*-
"""Connection smoke for FreeLLMAPI. Console output is ASCII. Logs are UTF-8.

Prompts are read from exp_gap1/prompts (already on this PC).
law_yakgwan_6_14.txt is not on this PC; the <자료> block is omitted and flagged.
Choices use prepare_data.py default titles for articles 6-14, because
exp_gap1/data/e2_choices.json is absent.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import client

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PROMPTS = REPO / "exp_gap1" / "prompts"
LAW = REPO / "exp_gap1" / "data" / "law_yakgwan_6_14.txt"
INPUTS = ROOT / "smoke_inputs.jsonl"
RESULTS = ROOT / "smoke_results_law.jsonl"
CHOICES_PATH = REPO / "exp_gap1" / "data" / "e2_choices.json"

# Exact ids from models_raw.json. gemma: one retry (2 attempts).
MODELS = [
    {"id": "gpt-oss-120b", "reasoning_effort": "low", "max_retries": 5},
    {"id": "nemotron-3-super-120b", "reasoning_effort": None, "max_retries": 5},
    {"id": "qwen3.8-27b", "reasoning_effort": None, "max_retries": 5},
    {"id": "gemma-4-31b", "reasoning_effort": None, "max_retries": 2},
]


def _norm_model(name: str | None) -> str:
    if not name:
        return ""
    s = str(name).strip().lower()
    if "/" in s:
        s = s.split("/", 1)[1]
    if s.endswith(":free"):
        s = s[: -len(":free")]
    return s


def _scrub(text: str, secret: str) -> str:
    if not text:
        return ""
    if secret:
        text = text.replace(secret, "****")
    return text


def _content(js: dict | None) -> str:
    if not js:
        return ""
    choices = js.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return "" if content is None else str(content)


def _parse_json(text: str):
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None, False
    try:
        return json.loads(raw[start : end + 1]), True
    except json.JSONDecodeError:
        return None, False


def _hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text or "")


def _provider(result: dict, actual: str | None) -> str:
    headers = result.get("headers_subset") or {}
    for key in ("x-freellmapi-provider", "x-provider"):
        if headers.get(key):
            return str(headers[key])
    if actual and "/" in actual:
        return actual.split("/", 1)[0]
    return "unknown"


def _usage(result: dict) -> tuple[int | None, int | None]:
    usage = result.get("usage") or {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return prompt, completion


def main() -> int:
    secret = client.get_key()
    print("key_source=" + client.key_source())
    print("key_len=" + str(len(secret)))
    print("base=" + client.get_base())
    system = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
    user_t = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")
    choices = json.loads(CHOICES_PATH.read_text(encoding="utf-8"))["choices_line"]
    law = ""
    law_used = LAW.is_file()
    if law_used:
        law = LAW.read_text(encoding="utf-8")
    print("law_file=" + ("yes" if law_used else "no"))
    print("law_chars=" + str(len(law)))
    print("choices_len=" + str(len(choices)))

    done = client.load_done_ids(RESULTS, "id")
    rows_in = []
    for line in INPUTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows_in.append(json.loads(line))

    for spec in MODELS:
        model = spec["id"]
        effort = spec["reasoning_effort"]
        for item in rows_in:
            row_id = item["id"] + "|" + model
            if row_id in done:
                print("skip id=" + row_id)
                continue
            user_body = user_t.replace("{clause}", item["clause"]).replace("{choices}", choices)
            if law_used:
                user = "<자료>\n" + law + "\n</자료>\n\n" + user_body
            else:
                user = user_body
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            extra = {"reasoning_effort": effort} if effort else None
            applied = bool(effort)
            result = client.chat_completion(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=512,
                extra_body=extra,
                max_retries=spec["max_retries"],
            )
            err = result.get("error_text") or ""
            if effort and result.get("http_status") == 400 and "reasoning" in err.lower():
                applied = False
                result = client.chat_completion(
                    model=model,
                    messages=messages,
                    temperature=0,
                    max_tokens=512,
                    extra_body=None,
                    max_retries=spec["max_retries"],
                )
            output = _scrub(_content(result.get("response_json")), secret)
            if not output and result.get("error_text"):
                output = _scrub(result.get("error_text") or "", secret)
            parsed, json_ok = _parse_json(output)
            if not (
                result.get("http_status") == 200
                and isinstance(parsed, dict)
                and "articles" in parsed
                and "error" not in parsed
            ):
                json_ok = False
            reason = ""
            if json_ok and isinstance(parsed, dict):
                reason = str(parsed.get("reason") or "")
            prompt_tok, completion_tok = _usage(result)
            actual = result.get("actual_model")
            headers = result.get("headers_subset") or {}
            provider = _provider(result, None)
            if provider == "unknown":
                provider = "unconfirmed"
            row = {
                "id": row_id,
                "sample_id": item["id"],
                "requested_model": model,
                "actual_model": actual,
                "substituted_raw": bool(result.get("substituted")),
                "substituted": bool(actual) and _norm_model(actual) != _norm_model(model),
                "provider": provider,
                "provider_headers": headers,
                "http_status": result.get("http_status"),
                "latency_ms": result.get("latency_ms"),
                "prompt_tokens": prompt_tok,
                "completion_tokens": completion_tok,
                "output": output,
                "json_ok": json_ok,
                "reason_ko": _hangul(reason),
                "reasoning_effort": effort,
                "reasoning_effort_applied": applied,
                "law_file_used": law_used,
                "attempt": result.get("attempt"),
            }
            client.append_jsonl(RESULTS, row)
            done.add(row_id)
            hdr = ",".join(sorted(headers)) if headers else "-"
            print(
                "id={id} model={model} http={http} ms={ms} subst={subst} json={js} ko={ko} prov={prov} hdr={hdr}".format(
                    id=item["id"],
                    model=model,
                    http=row["http_status"],
                    ms=row["latency_ms"],
                    subst=1 if row["substituted"] else 0,
                    js=1 if json_ok else 0,
                    ko=1 if row["reason_ko"] else 0,
                    prov=row["provider"],
                    hdr=hdr,
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
