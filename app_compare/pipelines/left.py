# -*- coding: utf-8 -*-
"""나빴던 조합: Qwen3-8B T2 A0, BM25 상위 5, 규칙 없음, T4는 BM25 자료에서 선택."""
from __future__ import annotations

from pipelines.common import choice_line, render_nodes, world
from pipelines.llm import chat_qwen, parse_json_output


def _verdict(risky, parse_ok: bool) -> str:
    if not parse_ok or risky is None:
        return "review"
    return "risk" if risky else "safe"


def _two_sentences(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    parts = [p for p in raw.replace("!", ".").replace("?", ".").split(".") if p.strip()]
    if len(parts) <= 2:
        return raw
    return ". ".join(p.strip() for p in parts[:2]) + "."


def run_left(clause: str, include_articles: bool = True) -> dict:
    w = world()
    calls = 0
    latency = 0.0
    slot_name = ""
    if include_articles:
        user = w.user_t2.replace("{label_list}", w.label_list).replace("{clause}", clause)
        resp = chat_qwen(
            [{"role": "system", "content": w.system_norag}, {"role": "user", "content": user}],
            thinking=False,
        )
        calls += 1
        latency += resp["latency_ms"]
        parsed, ok = parse_json_output(resp["content"])
        if ok and parsed.get("labels"):
            slot_name = str(parsed["labels"][0])

    known = w.t3_by_clause.get(clause)
    if known and known["id"] in w.a4:
        part = (w.a4[known["id"]].get("bm25") or {})
        node_ids = list(part.get("node_ids") or [])
        material = part.get("text") or ""
    else:
        node_ids = w.bm25_ids(clause, 5)
        material = render_nodes(node_ids, w.law)

    user = w.user_t3.replace("{clause}", clause)
    if material:
        user = f"<자료>\n{material}\n</자료>\n\n{user}"
    resp = chat_qwen(
        [{"role": "system", "content": w.system_rag}, {"role": "user", "content": user}],
        thinking=False,
    )
    calls += 1
    latency += resp["latency_ms"]
    parsed, ok = parse_json_output(resp["content"])
    risky = parsed.get("risky") if ok else None
    if isinstance(risky, str):
        risky = True if risky.strip().lower() == "true" else False if risky.strip().lower() == "false" else None
    if not isinstance(risky, bool):
        risky = None
        ok = False
    reason = _two_sentences(str(parsed.get("reason") or "") if parsed else "")
    if resp.get("error"):
        reason = "모델 서버에 연결하지 못했습니다."
        ok = False
        risky = None

    articles = []
    if include_articles and node_ids:
        lines = []
        for node_id in sorted(node_ids):
            node = w.law.get(node_id)
            if node:
                lines.append(choice_line(node))
        user = w.user_t4.replace("{choices}", "\n".join(lines)).replace("{clause}", clause)
        if material:
            user = f"<자료>\n{material}\n</자료>\n\n{user}"
        resp4 = chat_qwen(
            [{"role": "system", "content": w.system_rag}, {"role": "user", "content": user}],
            thinking=False,
        )
        calls += 1
        latency += resp4["latency_ms"]
        parsed4, ok4 = parse_json_output(resp4["content"])
        picked = []
        if ok4:
            picked = [str(x).strip() for x in (parsed4.get("articles") or [])]
        by_line = {a["line"]: a for a in w.articles_of(node_ids)}
        for line in picked:
            if line in by_line:
                articles.append(by_line[line])
        if not articles:
            articles = w.articles_of(node_ids)

    return {
        "clause": clause,
        "verdict": _verdict(risky, ok),
        "risky": risky,
        "actor": "모델",
        "slot": slot_name,
        "articles": articles,
        "reason": reason,
        "catalog_title": "",
        "severity": "",
        "wage_note": "",
        "latency_ms": round(latency, 1),
        "calls": calls,
        "parse_ok": ok,
    }
