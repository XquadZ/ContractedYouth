# -*- coding: utf-8 -*-
"""EXAONE 수정안 품질 확인(이자 24→20, 최저임금 10320→10700). 최대 3회.
프롬프트는 고치지 않는다. 결과는 out/lawwatch/proposal_review.md 에 이어 씀.
현행 카드 파일은 쓰지 않는다(proposals만).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.criteria import load_domain_cards
from rag.lawwatch.diff import diff_versions
from rag.lawwatch.paths import CRITERIA_PROPOSALS, LAWWATCH_OUT
from rag.lawwatch.propose import propose_for_card
from rag.lawwatch.store import current_version_entry, load_index, load_version
from rag.lawwatch.versions_io import dump_yaml


def _interest_case() -> dict:
    law = "이자제한법 제2조제1항의 최고이자율에 관한 규정"
    index = load_index(law)
    past = next(v for v in index["versions"] if v.get("id") == "past_20180208_24pct")
    cur = current_version_entry(law)
    diff = diff_versions(law, past["id"], cur["id"])
    ch = next(c for c in diff["changes"] if c["kind"] == "변경")
    byeol = "\n".join(u.get("text") or "" for u in load_version(law, cur["id"]).get("byeol") or [])
    card = next(c for c in load_domain_cards("LOAN") if c["id"] == "LOAN-INTEREST")
    return {
        "name": "최고이자율 24%→20%",
        "card": card,
        "before_text": ch["before"],
        "after_text": ch["after"],
        "byeol_text": byeol,
        "apply_rule_hint": (diff.get("byeol") or {}).get("apply_rule"),
        "rule_quote_hint": (diff.get("byeol") or {}).get("rule_quote"),
        "out_stem": "quality_LOAN-INTEREST",
    }


def _minwage_case() -> dict:
    # 조문 전/후는 고시 금액 변화로 구성(카드 LAB-MINWAGE)
    # 숫자 표기는 검사(number_not_in_law)가 \d+ 단위로 보므로 콤마 없는 원문형도 포함
    before_text = "2026년 적용 최저임금은 시간당 10320원(10,320원)으로 한다."
    after_text = "2027년 적용 최저임금은 시간당 10700원(10,700원)으로 한다."
    law = "최저임금법"
    cur = current_version_entry(law)
    body = load_version(law, cur["id"]) if cur else {"articles": [], "byeol": []}
    art10 = next((a for a in (body.get("articles") or []) if str(a.get("article_no")) == "10" or str(a.get("id") or "").endswith(":10")), None)
    quote = None
    if art10 and "다음 연도 1월 1일부터 효력이 발생한다" in (art10.get("text") or ""):
        for ln in (art10.get("text") or "").splitlines():
            if "다음 연도 1월 1일부터 효력이 발생한다" in ln:
                quote = ln.strip()
                break
        if not quote:
            quote = "② 제1항에 따라 고시된 최저임금은 다음 연도 1월 1일부터 효력이 발생한다. 다만, 고용노동부장관은 사업의 종류별로 임금교섭시기 등을 고려하여 필요하다고 인정하면 효력발생 시기를 따로 정할 수 있다. <개정 2010.6.4>"
    byeol = "\n".join(u.get("text") or "" for u in (body.get("byeol") or []))
    if quote:
        byeol = (byeol + "\n" + quote).strip()
    card = next(c for c in load_domain_cards("LAB") if c["id"] == "LAB-MINWAGE")
    return {
        "name": "최저임금 10,320→10,700",
        "card": card,
        "before_text": before_text,
        "after_text": after_text,
        "byeol_text": byeol,
        "apply_rule_hint": "performance_period",
        "rule_quote_hint": quote,
        "out_stem": "quality_LAB-MINWAGE",
    }


def run_case(case: dict, *, max_tries: int = 3) -> dict:
    attempts = []
    best = None
    for i in range(1, max_tries + 1):
        prop = propose_for_card(
            case["card"],
            before_text=case["before_text"],
            after_text=case["after_text"],
            byeol_text=case["byeol_text"],
            apply_rule_hint=case.get("apply_rule_hint"),
            rule_quote_hint=case.get("rule_quote_hint"),
            wait_gpu=True,
        )
        # 별도 파일로 보관(같은 날 LOAN 파일을 덮어쓰지 않음)
        out = CRITERIA_PROPOSALS / f"{prop['day']}_{case['out_stem']}_try{i}.yaml"
        dump_yaml({k: v for k, v in prop.items() if k != "path"}, out)
        prop["path"] = str(out)
        row = {
            "try": i,
            "path": str(out),
            "status": prop.get("status"),
            "validation": prop.get("validation"),
            "llm_parse_ok": prop.get("llm_parse_ok"),
            "reason": prop.get("reason"),
            "apply_rule": prop.get("apply_rule"),
            "rule_quote": prop.get("rule_quote"),
            "before_card": prop.get("before_card"),
            "proposed": prop.get("proposed"),
        }
        attempts.append(row)
        best = row
        if (prop.get("validation") or {}).get("ok"):
            break
    return {"name": case["name"], "attempts": attempts, "final": best}


def main() -> None:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    results = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "cases": [run_case(_interest_case()), run_case(_minwage_case())],
    }
    out_json = LAWWATCH_OUT / "proposal_quality.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out_json), "n_cases": 2}, ensure_ascii=False))


if __name__ == "__main__":
    main()
