# -*- coding: utf-8 -*-
"""FreeLLMAPI OpenAI-compatible minimal client.

Already present at freellm/client.py (previous-PC copy; that copy defaulted
to http://127.0.0.1:31415/v1). Server1: key is UNI_API_KEY, else FREELLM_KEY.
Base is FREELLM_BASE, else http://127.0.0.1:3001/v1.
Key values are never written to logs or return payloads.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_FALLBACK_BASE = "http://127.0.0.1:3001/v1"


def _from_process(name: str) -> str:
    return os.environ.get(name, "").strip()


def _from_windows_registry(name: str) -> str:
    if os.name != "nt":
        return ""
    import winreg

    roots = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    for root, sub in roots:
        try:
            with winreg.OpenKey(root, sub) as key:
                val, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        text = str(val).strip() if val is not None else ""
        if text:
            return text
    return ""


def _read_named(name: str) -> str:
    return _from_process(name) or _from_windows_registry(name)


def get_base() -> str:
    return (_read_named("FREELLM_BASE") or _FALLBACK_BASE).rstrip("/")


def get_key() -> str:
    for name in ("UNI_API_KEY", "FREELLM_KEY"):
        value = _read_named(name)
        if value:
            return value
    raise RuntimeError("UNI_API_KEY and FREELLM_KEY are unset")


def key_source() -> str:
    """Which variable supplied the key. Does not return the key."""
    for name in ("UNI_API_KEY", "FREELLM_KEY"):
        if _from_process(name):
            return name + ":process"
        if _from_windows_registry(name):
            return name + ":registry"
    return "unset"


def _provider_headers(headers) -> dict[str, str]:
    """Header names that mention provider, route, or upstream. Values kept; no auth."""
    out: dict[str, str] = {}
    for hk, hv in headers.items():
        low = hk.lower()
        if any(tok in low for tok in ("provider", "upstream", "route", "routed", "freellm")):
            out[hk] = hv
    return out


def key_length() -> int:
    try:
        return len(get_key())
    except RuntimeError:
        return 0


def chat_completion(
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 512,
    base_url: str | None = None,
    extra_body: dict | None = None,
    max_retries: int = 5,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """고정 model id로 호출. 429/5xx 지수 대기 최대 max_retries회.
    반환: {http_status, latency_ms, response_json|None, error_text|None,
            requested_model, actual_model, usage, headers_subset}
    """
    if model == "auto":
        raise ValueError("model='auto' forbidden")
    key = get_key()
    url = (base_url or get_base()).rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra_body:
        body.update(extra_body)

    last: dict[str, Any] = {}
    for attempt in range(max_retries):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                latency_ms = (time.perf_counter() - t0) * 1000
                js = json.loads(raw) if raw else {}
                actual = js.get("model")
                usage = js.get("usage") or {}
                headers_subset = _provider_headers(resp.headers)
                return {
                    "http_status": resp.status,
                    "latency_ms": round(latency_ms, 1),
                    "response_json": js,
                    "error_text": None,
                    "requested_model": model,
                    "actual_model": actual,
                    "substituted": actual is not None and actual != model,
                    "usage": usage,
                    "headers_subset": headers_subset,
                    "attempt": attempt + 1,
                }
        except urllib.error.HTTPError as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            err_body = e.read().decode("utf-8", errors="replace")
            last = {
                "http_status": e.code,
                "latency_ms": round(latency_ms, 1),
                "response_json": None,
                "error_text": err_body[:2000],
                "requested_model": model,
                "actual_model": None,
                "usage": {},
                "headers_subset": {},
                "attempt": attempt + 1,
                "substituted": False,
            }
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(min(60, 2**attempt))
                continue
            return last
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            last = {
                "http_status": None,
                "latency_ms": round(latency_ms, 1),
                "response_json": None,
                "error_text": str(e)[:2000],
                "requested_model": model,
                "actual_model": None,
                "usage": {},
                "headers_subset": {},
                "attempt": attempt + 1,
                "substituted": False,
            }
            if attempt < max_retries - 1:
                time.sleep(min(60, 2**attempt))
                continue
            return last
    return last


def list_models(base_url: str | None = None, timeout_sec: float = 60.0) -> dict[str, Any]:
    key = get_key()
    url = (base_url or get_base()).rstrip("/") + "/models"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {
                "http_status": resp.status,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "body": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as e:
        return {
            "http_status": e.code,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "body": e.read().decode("utf-8", errors="replace")[:500],
        }


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_done_ids(path: Path, id_field: str = "id") -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            done.add(str(json.loads(ln).get(id_field)))
        except Exception:
            pass
    return done
