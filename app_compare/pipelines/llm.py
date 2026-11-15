# -*- coding: utf-8 -*-
"""로컬 llama-server 호출. 요청 본문은 exp_v2/run_v2.py 와 같다."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

QWEN_URL = "http://127.0.0.1:8081/v1/chat/completions"
AX_URL = "http://127.0.0.1:8082/v1/chat/completions"
_QWEN = threading.Lock()
_AX = threading.Lock()


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


def _post(url: str, body: dict, timeout: int, lock: threading.Lock) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with lock:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {"content": "", "reasoning": "", "latency_ms": (time.perf_counter() - t0) * 1000, "error": detail[:500]}
    except Exception as exc:
        return {"content": "", "reasoning": "", "latency_ms": (time.perf_counter() - t0) * 1000, "error": str(exc)}
    js = json.loads(raw)
    msg = js["choices"][0]["message"]
    return {
        "content": msg.get("content") or "",
        "reasoning": msg.get("reasoning_content") or "",
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "error": None,
    }


def chat_qwen(messages: list[dict], thinking: bool = False) -> dict:
    if thinking:
        body = {
            "messages": messages,
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "seed": 42,
            "max_tokens": 4096,
            "chat_template_kwargs": {"enable_thinking": True},
            "enable_thinking": True,
        }
        timeout = 900
    else:
        body = {
            "messages": messages,
            "temperature": 0,
            "max_tokens": 256,
            "repeat_penalty": 1.05,
            "chat_template_kwargs": {"enable_thinking": False},
            "enable_thinking": False,
        }
        timeout = 300
    return _post(QWEN_URL, body, timeout, _QWEN)


def chat_ax(messages: list[dict]) -> dict:
    body = {"messages": messages, "temperature": 0, "max_tokens": 256}
    return _post(AX_URL, body, 300, _AX)


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False
