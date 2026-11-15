# -*- coding: utf-8 -*-
"""최고 조합.

주제는 KLUE-RoBERTa. 숫자형 check 는 규칙. 못 뽑으면 모델.
문구 판정은 A.X 4.0 Light. 자료는 slot 의 check law_nodes.
oracle_slot=1 이면 분류를 건너뛰고, 같은 문장의 T3 항목 gold check 조문(A1)을 넣는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipelines.common import SEVERITY_KO, basis_ids, choice_line, render_nodes, world
from pipelines.llm import chat_ax, chat_qwen, parse_json_output

import sys

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
sys.path.insert(0, str(WORK / "exp_v2"))
from baselines.rules import TARGET_CHECKS, judge_item, load_params  # noqa: E402

CKPT = Path(__file__).resolve().parents[1] / "models" / "roberta_t2_seed42"
_MODEL = None


def roberta():
    global _MODEL
    if _MODEL is None:
        _MODEL = SlotModel(CKPT)
    return _MODEL


class SlotModel:
    def __init__(self, path: Path) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True)
        self.model.eval()
        self.labels = json.loads((path / "labels.json").read_text(encoding="utf-8"))

    def predict(self, text: str) -> str:
        enc = self.tok(text, truncation=True, max_length=256, return_tensors="pt")
        with self.torch.no_grad():
            idx = int(self.model(**enc).logits.argmax(-1))
        return self.labels[idx]


def ready() -> bool:
    return (CKPT / "labels.json").exists()


def _verdict(risky, parse_ok: bool) -> str:
    if risky is None or not parse_ok:
        return "review"
    return "risk" if risky else "safe"


def _two(text: str) -> str:
    raw = (text or "").strip()
    parts = [p for p in raw.replace("!", ".").replace("?", ".").split(".") if p.strip()]
    if len(parts) <= 2:
        return raw
    return ". ".join(p.strip() for p in parts[:2]) + "."


def _rule_on_slot(clause: str, checks: list[dict]) -> tuple[bool | None, list[dict]]:
    params = load_params()
    decided = []
    for check in checks:
        if check["id"] not in TARGET_CHECKS:
            continue
        pred = judge_item({"kind": "numeric", "check_id": check["id"], "clause": clause}, params)
        if pred is not None:
            decided.append((pred, check))
    if not decided:
        return None, []
    risky = any(flag for flag, _ in decided)
    used = [check for flag, check in decided if flag] or [check for _, check in decided]
    return risky, used


def run_right(clause: str, oracle_slot: bool = False, include_articles: bool = True) -> dict:
    w = world()
    calls = 0
    latency = 0.0
    known = w.t3_by_clause.get(clause)
    slot_id = ""
    slot_name = ""
    if oracle_slot and known:
        slot_id = known.get("slot") or ""
        slot_name = (w.slot_by_id.get(slot_id) or {}).get("name") or slot_id
    elif ready():
        slot_name = roberta().predict(clause)
        slot_id = w.slot_by_name.get(slot_name, "")
    checks = w.checks_for_slot(slot_id) if slot_id else []

    if oracle_slot and known:
        node_ids = list(known.get("gold_law_nodes") or [])
        packed = w.a1.get(known["id"]) or {}
        material = packed.get("text") or render_nodes(node_ids, w.law)
    else:
        node_ids = []
        for check in checks:
            for node_id in basis_ids(check):
                if node_id not in node_ids:
                    node_ids.append(node_id)
        material = render_nodes(node_ids, w.law) if node_ids else ""

    rule_risky, rule_checks = _rule_on_slot(clause, checks)
    actor = "모델"
    risky = None
    reason = ""
    parse_ok = True
    catalog_checks = rule_checks or checks[:1]
    if rule_risky is not None:
        risky = rule_risky
        actor = "규칙"
        titles = [c.get("title") or c["id"] for c in rule_checks]
        reason = "규칙으로 판정했다. " + " / ".join(titles)
    else:
        tried_rule = any(c["id"] in TARGET_CHECKS for c in checks)
        if tried_rule:
            actor = "규칙 N/A→모델"
        system = w.system_rag if material else w.system_norag
        user = w.user_t3.replace("{clause}", clause)
        if material:
            user = f"<자료>\n{material}\n</자료>\n\n{user}"
        resp = chat_ax([{"role": "system", "content": system}, {"role": "user", "content": user}])
        calls += 1
        latency += resp["latency_ms"]
        parsed, ok = parse_json_output(resp["content"])
        risky = parsed.get("risky") if ok else None
        if isinstance(risky, str):
            risky = True if risky.lower() == "true" else False if risky.lower() == "false" else None
        if not isinstance(risky, bool):
            risky = None
            ok = False
        parse_ok = ok
        reason = _two(str((parsed or {}).get("reason") or ""))
        if resp.get("error"):
            reason = "모델 서버에 연결하지 못했습니다."
            parse_ok = False

    articles = w.articles_of(node_ids)
    if include_articles and len(checks) > 1 and not (oracle_slot and known):
        lines = []
        for node_id in sorted(node_ids):
            node = w.law.get(node_id)
            if node:
                lines.append(choice_line(node))
        if lines:
            user = w.user_t4.replace("{choices}", "\n".join(lines)).replace("{clause}", clause)
            if material:
                user = f"<자료>\n{material}\n</자료>\n\n{user}"
            resp4 = chat_qwen(
                [{"role": "system", "content": w.system_rag}, {"role": "user", "content": user}],
                thinking=True,
            )
            calls += 1
            latency += resp4["latency_ms"]
            parsed4, ok4 = parse_json_output(resp4["content"])
            if ok4:
                by_line = {a["line"]: a for a in articles}
                picked = []
                for line in parsed4.get("articles") or []:
                    if str(line).strip() in by_line:
                        picked.append(by_line[str(line).strip()])
                if picked:
                    articles = picked

    title = " / ".join(c.get("title") or c["id"] for c in catalog_checks if c)
    severity = ""
    if catalog_checks:
        severity = SEVERITY_KO.get(catalog_checks[0].get("severity") or "", "")
    if title:
        reason = (reason + " 항목: " + title).strip()
    wage = ""
    if any(c["id"] == "L-T01" for c in checks) or (known and known.get("check_id") == "L-T01"):
        amount = w.params["min_wage_hourly"].get("2026")
        wage = f"기준: 2026년 고시 {int(amount):,}원" if amount else "기준: 2026년 고시"

    return {
        "clause": clause,
        "verdict": _verdict(risky, parse_ok if actor != "규칙" else True),
        "risky": risky,
        "actor": actor,
        "slot": slot_name,
        "articles": articles,
        "reason": reason,
        "catalog_title": title,
        "severity": severity,
        "wage_note": wage,
        "latency_ms": round(latency, 1),
        "calls": calls,
        "parse_ok": parse_ok if actor != "규칙" else True,
    }
