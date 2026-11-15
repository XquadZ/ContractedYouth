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
    """kind=exaone만 허용. A.X(8082)를 자동 기동·전환하지 않는다."""
    global _SWITCHING
    if kind != "exaone":
        # FINAL_POLISH B: ax 자동 기동/전환 금지
        set_llm_endpoint(ENDPOINTS["exaone"]["url"], ENDPOINTS["exaone"]["health"])
        return
    ep = ENDPOINTS["exaone"]
    _SWITCHING = True
    try:
        # alone이어도 A.X를 내리지 않음(전환 금지). EXAONE만 확인·기동.
        if _health(ep["health"]):
            set_llm_endpoint(ep["url"], ep["health"])
            return
        log = (APP / "out" / "start_exaone_serve.log").open("w", encoding="utf-8")
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
        raise RuntimeError("exaone start timeout")
    finally:
        _SWITCHING = False


def _chat_local(
    messages: list[dict],
    max_tokens: int = AX_MAX_TOKENS,
    *,
    temperature: float | None = None,
    timeout: float | None = None,
) -> dict:
    body = {
        "messages": messages,
        "temperature": AX_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(body).encode("utf-8")
    from rag import generate as gen

    url = gen._LLM_URL_OVERRIDE or ENDPOINTS["exaone"]["url"]
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout or AX_TIMEOUT) as response:
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
    """마스킹 후 EXAONE 판정."""
    mode = "exaone"
    # 계약서 조각만 가린다. 법 조문·카드·지시가 들어 있는 프롬프트 전체는 가리지 않는다.
    masked, _ = mask_pii(clause or "")
    user, cards, hits2 = build_judge_prompt(masked, facts, hits, use_criteria=use_criteria)
    ensure_local_model("exaone", alone=False)
    resp = _chat_local([{"role": "user", "content": user}])
    row = _blank_finding()
    row["raw"] = resp.get("content") or ""
    row["error"] = resp.get("error")
    row["selected_cards"] = [c.get("id") for c in cards]
    row["cards"] = cards
    row["hits_for_verify"] = hits2
    row["analyze_model"] = mode
    parsed, ok = parse_json_output(row["raw"])
    if not ok or not isinstance(parsed, dict):
        row["why"] = "확인 필요(분석 실패)"
        row["verdict"] = "확인 필요"
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


def _helper_chat_fallback() -> str:
    return (
        "지금은 안내 도우미 모드예요. 리포트 카드의 근거 조문과 확인 질문을 먼저 살펴봐 주세요. "
        "법률 자문이 아니에요. 중요한 결정 전에는 고용노동부 1350, 대한법률구조공단 132에 상담하세요."
    )


def chat_answer(*, question: str, report: dict, mode: str | None = None) -> str:
    """채팅 답변: EXAONE. 실패·60초 초과 시 안내 도우미 + 안내 문구."""
    q_m, _ = mask_pii(question or "")
    footer = (
        "법률 자문이 아니에요. 중요한 결정 전에는 고용노동부 1350, 대한법률구조공단 132에 상담하세요."
    )
    masked_contract, _ = mask_pii((report.get("masked_text") or "")[:3500])
    cards_ctx = []
    for c in (report.get("cards") or [])[:12]:
        evidence = []
        for e in c.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            evidence.append(
                {
                    "id": e.get("id"),
                    "title": e.get("title") or e.get("source_tag") or "",
                    "quote": (e.get("quote") or "")[:180],
                }
            )
        cards_ctx.append(
            {
                "verdict": c.get("verdict"),
                "why": (c.get("why") or "")[:220],
                "suggestion": (c.get("suggestion") or "")[:180],
                "evidence": evidence,
            }
        )
    ctx = {
        "domain": report.get("domain"),
        "grade": report.get("grade"),
        "score": report.get("score"),
        "summary": report.get("summary"),
        "cards": cards_ctx,
        "masked_contract_excerpt": masked_contract,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "계약서 리포트와 가린 계약서 문장만 근거로 짧게 한국어로 답하세요. "
                "추측으로 조항을 만들어내지 마세요. 법률 자문이 아니라고 분명히 하세요."
            ),
        },
        {
            "role": "user",
            "content": f"리포트(요약 JSON):\n{json.dumps(ctx, ensure_ascii=False)}\n\n질문: {q_m}",
        },
    ]
    try:
        ensure_local_model("exaone", alone=False)
        resp = _chat_local(messages, max_tokens=400, temperature=0.2, timeout=60)
    except Exception:
        return "AI가 바빠서 기본 안내로 답했어요\n\n" + _helper_chat_fallback()
    if resp.get("error") or not (resp.get("content") or "").strip():
        return "AI가 바빠서 기본 안내로 답했어요\n\n" + _helper_chat_fallback()
    text = (resp.get("content") or "").strip()
    if footer not in text:
        text = text + "\n\n" + footer
    return text
