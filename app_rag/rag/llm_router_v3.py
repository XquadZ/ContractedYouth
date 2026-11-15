# -*- coding: utf-8 -*-
"""ANALYZE_MODEL에 따라 로컬(A.X/EXAONE) 또는 OpenAI로 판정."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from rag.generate import (
    ax_up,
    build_judge_prompt,
    parse_json_output,
    set_llm_endpoint,
    _blank_finding,
)
from rag.paths import AX_MAX_TOKENS, AX_TEMPERATURE, AX_TIMEOUT
from rag.pii import mask_pii
from rag.settings import GPT_MODEL, get_analyze_model, model_label

APP = Path(__file__).resolve().parents[1]
ENDPOINTS = {
    "ax": {
        "url": "http://127.0.0.1:8082/v1/chat/completions",
        "health": "http://127.0.0.1:8082/health",
        "port": 8082,
        "start": "start_ax.py",
    },
    "exaone": {
        "url": "http://127.0.0.1:8083/v1/chat/completions",
        "health": "http://127.0.0.1:8083/health",
        "port": 8083,
        "start": "start_exaone.py",
    },
}

_SWITCHING = False


def is_switching() -> bool:
    return _SWITCHING


def _health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _stop_port(port: int) -> None:
    cmd = (
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        f"Select-Object -First 1; if($c -and $c.OwningProcess -gt 0)"
        f"{{ Stop-Process -Id $c.OwningProcess -Force }}"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)


def ensure_local_model(kind: str, *, alone: bool = True) -> None:
    """kind=ax|exaone. GPU 단독 로드."""
    global _SWITCHING
    ep = ENDPOINTS[kind]
    other = "exaone" if kind == "ax" else "ax"
    _SWITCHING = True
    try:
        if alone and _health(ENDPOINTS[other]["health"]):
            _stop_port(ENDPOINTS[other]["port"])
            time.sleep(2)
        if _health(ep["health"]):
            set_llm_endpoint(ep["url"], ep["health"])
            return
        log = (APP / "out" / f"start_{kind}_serve.log").open("w", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, str(APP / ep["start"])],
            cwd=str(APP),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(180):
            if _health(ep["health"]):
                set_llm_endpoint(ep["url"], ep["health"])
                return
            time.sleep(2)
        raise RuntimeError(f"{kind} start timeout")
    finally:
        _SWITCHING = False


def _chat_local(messages: list[dict], max_tokens: int = AX_MAX_TOKENS) -> dict:
    body = {"messages": messages, "temperature": AX_TEMPERATURE, "max_tokens": max_tokens}
    data = json.dumps(body).encode("utf-8")
    url = ENDPOINTS[get_analyze_model() if get_analyze_model() in ENDPOINTS else "ax"]["url"]
    # use override if set
    from rag import generate as gen

    url = gen._LLM_URL_OVERRIDE or url
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=AX_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        return {"content": "", "error": str(exc)[:400]}
    js = json.loads(raw)
    return {"content": (js["choices"][0]["message"].get("content") or ""), "error": None}


def _chat_openai(messages: list[dict], max_tokens: int = 512) -> dict:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return {"content": "", "error": "OPENAI_API_KEY missing"}
    body = {
        "model": GPT_MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return {"content": "", "error": exc.read().decode("utf-8", "replace")[:400]}
    except Exception as exc:
        return {"content": "", "error": str(exc)[:400]}
    js = json.loads(raw)
    return {"content": (js["choices"][0]["message"].get("content") or ""), "error": None}


def generate_finding_routed(clause: str, facts: dict, hits: list[dict], *, use_criteria: bool = True) -> dict:
    """마스킹 후 모델 호출. gpt 모드면 OpenAI, 아니면 로컬."""
    mode = get_analyze_model()
    # 계약서 조각만 가린다. 법 조문·카드·지시가 들어 있는 프롬프트 전체는 가리지 않는다.
    masked, _ = mask_pii(clause or "")
    user, cards, hits2 = build_judge_prompt(masked, facts, hits, use_criteria=use_criteria)
    messages = [{"role": "user", "content": user}]
    if mode == "gpt":
        messages = [
            {"role": "system", "content": "당신은 계약서 조항 판정기입니다. 반드시 JSON 객체만 출력하세요."},
            {"role": "user", "content": user},
        ]
        resp = _chat_openai(messages)
    else:
        if mode in ENDPOINTS:
            ensure_local_model(mode, alone=True)
        resp = _chat_local([{"role": "user", "content": user}])
    row = _blank_finding()
    row["raw"] = resp.get("content") or ""
    row["error"] = resp.get("error")
    row["selected_cards"] = [c.get("id") for c in cards]
    row["hits_for_verify"] = hits2
    row["analyze_model"] = mode
    err = (resp.get("error") or "").lower()
    if mode == "gpt" and err and any(
        x in err for x in ("insufficient_quota", "invalid_api_key", "billing", "credit", "401", "429")
    ):
        row["verdict"] = "확인 필요"
        row["why"] = "외부 AI를 지금 쓸 수 없어요. 로컬 모델로 분석해 주세요."
        row["suggestion"] = "외부 AI를 지금 쓸 수 없어요. 로컬 모델로 분석해 주세요."
        row["parse_ok"] = True
        row["error"] = None
        row["gpt_unavailable"] = True
        return row
    parsed, ok = parse_json_output(row["raw"])
    if not ok or not isinstance(parsed, dict):
        row["why"] = "모델 출력을 JSON으로 읽지 못했다."
        if mode == "gpt" and resp.get("error"):
            row["why"] = "외부 AI를 지금 쓸 수 없어요. 로컬 모델로 분석해 주세요."
            row["suggestion"] = row["why"]
            row["verdict"] = "확인 필요"
            row["parse_ok"] = True
            row["error"] = None
            row["gpt_unavailable"] = True
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


def chat_answer(*, question: str, report: dict, mode: str | None = None) -> str:
    """채팅 답변. gpt 모드만 외부 호출. 끝 mid 면책."""
    mode = (mode or get_analyze_model()).lower()
    q_m, _ = mask_pii(question or "")
    disclaimer = "법률 자문이 아니에요."
    if mode != "gpt":
        return (
            "지금은 안내 도우미 모드예요. 리포트 카드의 근거 조문과 확인 질문을 먼저 살펴봐 주세요. "
            + disclaimer
        )
    ctx = {
        "domain": report.get("domain"),
        "grade": report.get("grade"),
        "score": report.get("score"),
        "summary": report.get("summary"),
        "cards": [
            {
                "verdict": c.get("verdict"),
                "why": (c.get("why") or "")[:200],
                "evidence": c.get("evidence") or [],
            }
            for c in (report.get("cards") or [])[:12]
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "계약서 리포트를 바탕으로 짧게 한국어로 답하세요. "
                "법률 자문이 아니라고 분명히 하세요. 추측으로 조항을 만들어내지 마세요."
            ),
        },
        {
            "role": "user",
            "content": f"리포트(요약 JSON):\n{json.dumps(ctx, ensure_ascii=False)}\n\n질문: {q_m}",
        },
    ]
    # chat은 json_object 강제하지 않음
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return "시연 모드 키가 없어 답할 수 없어요. " + disclaimer
    body = {
        "model": GPT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 400,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8")
        js = json.loads(raw)
        text = (js["choices"][0]["message"].get("content") or "").strip()
    except Exception as exc:
        return f"답변을 만들지 못했어요 ({str(exc)[:120]}). " + disclaimer
    if disclaimer not in text:
        text = text + "\n\n" + disclaimer
    return text
