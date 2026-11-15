# -*- coding: utf-8 -*-
"""1장: 현행·연혁 법령을 data_local/law_versions 에 등록하고 사례 3개 버전 파일을 만든다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.criteria import load_domain_cards
from rag.lawwatch.byeol import resolve_apply_rule
from rag.lawwatch.paths import CRITERIA_VERSIONS, LAW_VERSIONS, LAWWATCH_OUT
from rag.lawwatch.store import bootstrap_from_law_api, current_version_entry, load_index, load_version, register_synthetic_past
from rag.lawwatch.versions_io import card_fields, dump_yaml


def _find_current_ident(law_name: str) -> str:
    entry = current_version_entry(law_name)
    if not entry:
        raise SystemExit(f"현행 버전 없음: {law_name}")
    return entry["id"]


def register_interest_case() -> dict:
    """최고이자율 24%→20%, 2021-07-07, contract_date."""
    law = "이자제한법 제2조제1항의 최고이자율에 관한 규정"
    cur_id = _find_current_ident(law)
    cur = load_version(law, cur_id)
    # 개정문(저장 원문): 본문 중 "연 24퍼센트"를 "연 20퍼센트"로 한다.
    after_text = (cur.get("articles") or [{}])[0].get("text") or ""
    before_text = after_text.replace("연 20퍼센트", "연 24퍼센트")
    if "24퍼센트" not in before_text:
        before_text = "「이자제한법」 제2조제1항에 따른 금전대차에 관한 계약상의 최고이자율은 연 24퍼센트로 한다."
    # 2017.11.7 부칙: 공포 후 3개월 → 2018-02-08 (부칙 원문은 저장소에 있음)
    byeol = resolve_apply_rule(
        cur.get("byeol") or [],
        announced="2021-04-06",
        effective="2021-07-07",
    )
    # 과거 버전 등록 (개정문 근거 재구성)
    past = register_synthetic_past(
        law,
        base_ident=cur_id,
        new_ident="past_20180208_24pct",
        effective="2018-02-08",
        announced="2017-11-07",
        article_text_map={((cur.get("articles") or [{}])[0].get("id") or "law:이자제한법 제2조제1항의 최고이자율에 관한 규정:0"): before_text},
        note="현행 파일 개정문 「본문 중 \"연 24퍼센트\"를 \"연 20퍼센트\"로 한다.」에서 재구성",
    )
    # 카드 버전
    card = next(c for c in load_domain_cards("LOAN") if c["id"] == "LOAN-INTEREST")
    quote = byeol.get("rule_quote")
    apply_rule = byeol.get("apply_rule") or "unknown"
    if not quote:
        # 원문에서 직접
        for u in cur.get("byeol") or []:
            if (u.get("announced") or "").startswith("2021-04-06") or (u.get("number") == "31593"):
                for ln in u.get("lines") or []:
                    if "적용례" in ln or "체결하거나 갱신" in ln:
                        quote = ln
                        apply_rule = "contract_date"
                        break
    v1_card = card_fields(card)
    # v1: 24% 표현
    v1_card = {
        **v1_card,
        "safe": [s.replace("20%", "24%").replace("연 20", "연 24") for s in (v1_card.get("safe") or [])],
        "violation": [s.replace("20%", "24%").replace("연 20", "연 24") for s in (v1_card.get("violation") or [])],
    }
    v2_card = card_fields(card)
    # 2017 부칙 적용례도 contract_date
    quote_2017 = None
    for u in cur.get("byeol") or []:
        if (u.get("announced") or "").startswith("2017-11-07"):
            for ln in u.get("lines") or []:
                if "적용례" in ln or "체결하거나 갱신" in ln:
                    quote_2017 = ln
                    break
    data = {
        "card_id": "LOAN-INTEREST",
        "versions": [
            {
                "version": 1,
                "effective_from": "2018-02-08",
                "effective_to": "2021-07-06",
                "apply_rule": "contract_date" if quote_2017 else "unknown",
                "rule_source": {
                    "law": law,
                    "quote": quote_2017 or "미확인",
                    "source_status": "원문" if quote_2017 else "미확인",
                },
                "card": v1_card,
            },
            {
                "version": 2,
                "effective_from": "2021-07-07",
                "effective_to": None,
                "apply_rule": apply_rule if quote else "unknown",
                "rule_source": {
                    "law": law,
                    "quote": quote or "미확인",
                    "source_status": byeol.get("status") if quote else "미확인",
                },
                "card": v2_card,
            },
        ],
    }
    path = CRITERIA_VERSIONS / "LOAN-INTEREST.yaml"
    dump_yaml(data, path)
    return {
        "card": "LOAN-INTEREST",
        "path": str(path),
        "apply_rule": data["versions"][1]["apply_rule"],
        "quote": data["versions"][1]["rule_source"]["quote"],
        "past": past,
        "effective": "2021-07-07",
    }


def register_lease_case() -> dict:
    """주택임대차보호법 2020-07-31, in_force."""
    law = "주택임대차보호법"
    cur_id = _find_current_ident(law)
    cur = load_version(law, cur_id)
    quote = None
    for u in cur.get("byeol") or []:
        if (u.get("announced") or "").startswith("2020-07-31") or u.get("number") == "17470":
            for ln in u.get("lines") or []:
                if "존속 중인 임대차" in ln or "제6조의3" in ln:
                    quote = ln
                    break
    byeol = resolve_apply_rule(cur.get("byeol") or [], announced="2020-07-31", effective="2020-07-31")
    if quote:
        apply_rule = "in_force"
    else:
        apply_rule = byeol.get("apply_rule") or "unknown"
        quote = byeol.get("rule_quote") or "미확인"

    results = []
    for card_id in ("LEASE-RENEW", "LEASE-RENT"):
        card = next(c for c in load_domain_cards("LEASE") if c["id"] == card_id)
        # 개정 전 버전: 계약갱신요구권/5% 상한 없는 약식(모의 표시는 데모에서)
        pre = card_fields(card)
        if card_id == "LEASE-RENEW":
            pre = {
                **pre,
                "safe": ["갱신 조항이 민법·약정에 따라 명시"],
                "violation": ["법령상 계약갱신요구권 규정이 없던 시기 — 약정·민법 기준"],
                "check_if": ["2020-07-31 개정 이후 기준과 다를 수 있음"],
            }
        data = {
            "card_id": card_id,
            "versions": [
                {
                    "version": 1,
                    "effective_from": "1981-03-05",
                    "effective_to": "2020-07-30",
                    "apply_rule": "unknown",
                    "rule_source": {"law": law, "quote": "미확인", "source_status": "미확인"},
                    "card": pre,
                    "note": "개정 전 카드 초안(부칙 적용례 미확인 → unknown)",
                },
                {
                    "version": 2,
                    "effective_from": "2020-07-31",
                    "effective_to": None,
                    "apply_rule": apply_rule if quote != "미확인" else "unknown",
                    "rule_source": {
                        "law": law,
                        "quote": quote,
                        "source_status": "원문" if quote != "미확인" else "미확인",
                    },
                    "card": card_fields(card),
                },
            ],
        }
        path = CRITERIA_VERSIONS / f"{card_id}.yaml"
        dump_yaml(data, path)
        results.append({"card": card_id, "path": str(path), "apply_rule": data["versions"][1]["apply_rule"], "quote": quote})
    return {"law": law, "effective": "2020-07-31", "cards": results, "quote": quote}


def register_minwage_case() -> dict:
    """최저임금 연도별 performance_period. 근거: 최저임금법 제10조제2항 원문."""
    law = "최저임금법"
    cur_id = _find_current_ident(law)
    cur = load_version(law, cur_id)
    quote = None
    for art in cur.get("articles") or []:
        if art.get("id", "").endswith(":10") or art.get("article_no") == "10":
            for ln in (art.get("text") or "").splitlines():
                if "다음 연도 1월 1일부터 효력이 발생한다" in ln:
                    quote = ln.strip()
                    break
            if not quote and "다음 연도 1월 1일부터 효력이 발생한다" in (art.get("text") or ""):
                # 항이 한 블록
                text = art["text"]
                for piece in text.split("②"):
                    if "다음 연도 1월 1일부터 효력이 발생한다" in piece:
                        quote = ("②" + piece).split("③")[0].strip()
                        if not quote.startswith("②"):
                            quote = "② " + piece.split("③")[0].strip()
                        break
    # 조문 원문에서 정확히
    if not quote:
        for art in cur.get("articles") or []:
            t = art.get("text") or ""
            if "다음 연도 1월 1일부터 효력이 발생한다" in t:
                # 해당 문장만
                for ln in t.replace("。", ".").splitlines():
                    if "다음 연도 1월 1일부터 효력이 발생한다" in ln:
                        quote = ln.strip()
                        break
                if not quote:
                    quote = "② 제1항에 따라 고시된 최저임금은 다음 연도 1월 1일부터 효력이 발생한다. 다만, 고용노동부장관은 사업의 종류별로 임금교섭시기 등을 고려하여 필요하다고 인정하면 효력발생 시기를 따로 정할 수 있다."
                    # 검증: 원문에 핵심 구절 포함?
                    if "다음 연도 1월 1일부터 효력이 발생한다" not in t:
                        quote = "미확인"

    card = next(c for c in load_domain_cards("LAB") if c["id"] == "LAB-MINWAGE")
    base = card_fields(card)
    versions = [
        {
            "version": 1,
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "apply_rule": "performance_period" if quote and quote != "미확인" else "unknown",
            "rule_source": {
                "law": "최저임금법 제10조제2항",
                "quote": quote or "미확인",
                "source_status": "원문" if quote and quote != "미확인" else "미확인",
                "amount": 10320,
                "year": 2026,
            },
            "card": {
                **base,
                "safe": [
                    "시간급이 2026년 최저임금(시간당 10,320원, config/min_wage.yaml) 이상",
                    "수습 감액은 1년↑계약·3개월 이내·단순노무 제외·10% 이내",
                ],
                "basis": ["law:최저임금법:5", "law:최저임금법:6:1", "law:최저임금법:10", "notice:최저임금고시:2026"],
            },
        },
        {
            "version": 2,
            "effective_from": "2027-01-01",
            "effective_to": None,
            "apply_rule": "performance_period" if quote and quote != "미확인" else "unknown",
            "rule_source": {
                "law": "최저임금법 제10조제2항",
                "quote": quote or "미확인",
                "source_status": "원문" if quote and quote != "미확인" else "미확인",
                "amount": 10700,
                "year": 2027,
            },
            "card": {
                **base,
                "safe": [
                    "시간급이 2027년 최저임금(시간당 10,700원, config/min_wage.yaml) 이상",
                    "수습 감액은 1년↑계약·3개월 이내·단순노무 제외·10% 이내",
                ],
                "basis": ["law:최저임금법:5", "law:최저임금법:6:1", "law:최저임금법:10", "notice:최저임금고시:2027"],
            },
        },
    ]
    data = {"card_id": "LAB-MINWAGE", "versions": versions}
    path = CRITERIA_VERSIONS / "LAB-MINWAGE.yaml"
    dump_yaml(data, path)
    return {
        "card": "LAB-MINWAGE",
        "path": str(path),
        "apply_rule": versions[0]["apply_rule"],
        "quote": quote,
        "amounts": {"2026": 10320, "2027": 10700},
    }


def main() -> None:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    CRITERIA_VERSIONS.mkdir(parents=True, exist_ok=True)
    print("bootstrap law_api → law_versions ...")
    report = bootstrap_from_law_api(include_history=True)
    cases = {
        "interest": register_interest_case(),
        "lease": register_lease_case(),
        "minwage": register_minwage_case(),
        "bootstrap_n": len(report.get("registered") or []),
        "bootstrap_errors": report.get("errors") or [],
        "n_laws": len(list(LAW_VERSIONS.glob("*/index.json"))),
    }
    out = LAWWATCH_OUT / "bootstrap_cases.json"
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "n_laws": cases["n_laws"], "bootstrap_n": cases["bootstrap_n"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
