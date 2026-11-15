# -*- coding: utf-8 -*-
"""수정안 구조 변경 후 품질 재확인 → out/lawwatch/proposal_review2.md

- 이자 24→20%, 최저임금 10320→10700: 각 3회 (조기 중단 없음)
- 주임법 제7조 증액상한 20분의1→10분의1 모의: 3회
- 프롬프트는 고치지 않음. 현행 카드·corpus 파일은 쓰지 않음.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.criteria import load_domain_cards
from rag.lawwatch.byeol import extract_rule_candidates
from rag.lawwatch.diff import diff_versions
from rag.lawwatch.paths import CRITERIA_PROPOSALS, LAWWATCH_OUT
from rag.lawwatch.propose import propose_for_card
from rag.lawwatch.store import current_version_entry, load_index, load_version
from rag.lawwatch.versions_io import dump_yaml, load_card_versions
from rag.paths import APP as APP_ROOT
from rag.yamlutil import load as load_yaml


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _norm(s: str | None) -> str:
    return " ".join((s or "").split())


def _expected_from_versions(card_id: str) -> dict:
    data = load_card_versions(card_id) or {}
    vers = sorted(data.get("versions") or [], key=lambda v: int(v.get("version") or 0))
    if not vers:
        return {"apply_rule": None, "quote": None, "version": None}
    # 최신(열린) 버전
    last = vers[-1]
    rs = last.get("rule_source") or {}
    return {
        "apply_rule": last.get("apply_rule"),
        "quote": rs.get("quote"),
        "version": last.get("version"),
    }


def _match_candidate_index(candidates: list[dict], expected_quote: str | None) -> int | None:
    if not expected_quote:
        return None
    en = _norm(expected_quote)
    for c in candidates:
        if en and (_norm(c.get("text")) == en or en in _norm(c.get("text")) or _norm(c.get("text")) in en):
            return int(c["index"])
    return None


def _interest_case() -> dict:
    law = "이자제한법 제2조제1항의 최고이자율에 관한 규정"
    index = load_index(law)
    past = next(v for v in index["versions"] if v.get("id") == "past_20180208_24pct")
    cur = current_version_entry(law)
    diff = diff_versions(law, past["id"], cur["id"])
    ch = next(c for c in diff["changes"] if c["kind"] == "변경")
    body = load_version(law, cur["id"])
    byeol_units = body.get("byeol") or []
    byeol_text = "\n".join(u.get("text") or "" for u in byeol_units)
    card = next(c for c in load_domain_cards("LOAN") if c["id"] == "LOAN-INTEREST")
    exp = _expected_from_versions("LOAN-INTEREST")
    return {
        "name": "최고이자율 24%→20%",
        "card": card,
        "before_text": ch["before"],
        "after_text": ch["after"],
        "byeol_text": byeol_text,
        "byeol_units": byeol_units,
        "apply_rule_hint": None,
        "rule_quote_hint": exp.get("quote"),
        "out_stem": "review2_LOAN-INTEREST",
        "expected": exp,
        "label": None,
    }


def _minwage_case() -> dict:
    before_text = "2026년 적용 최저임금은 시간당 10320원(10,320원)으로 한다."
    after_text = "2027년 적용 최저임금은 시간당 10700원(10,700원)으로 한다."
    law = "최저임금법"
    cur = current_version_entry(law)
    body = load_version(law, cur["id"]) if cur else {"articles": [], "byeol": []}
    art10 = next(
        (
            a
            for a in (body.get("articles") or [])
            if str(a.get("article_no")) == "10" or str(a.get("id") or "").endswith(":10")
        ),
        None,
    )
    quote = None
    if art10 and "다음 연도 1월 1일부터 효력이 발생한다" in (art10.get("text") or ""):
        for ln in (art10.get("text") or "").splitlines():
            if "다음 연도 1월 1일부터 효력이 발생한다" in ln:
                quote = ln.strip()
                break
    byeol_units = list(body.get("byeol") or [])
    byeol_text = "\n".join(u.get("text") or "" for u in byeol_units)
    exp = _expected_from_versions("LAB-MINWAGE")
    if not quote:
        quote = exp.get("quote")
    card = next(c for c in load_domain_cards("LAB") if c["id"] == "LAB-MINWAGE")
    return {
        "name": "최저임금 10,320→10,700",
        "card": card,
        "before_text": before_text,
        "after_text": after_text,
        "byeol_text": byeol_text,
        "byeol_units": byeol_units,
        "apply_rule_hint": None,
        "rule_quote_hint": quote,
        "out_stem": "review2_LAB-MINWAGE",
        "expected": exp,
        "label": None,
    }


def _lease_rent_mock_case() -> dict:
    """모의: 주택임대차보호법 제7조 증액 상한 20분의 1 → 10분의 1."""
    law = "주택임대차보호법"
    cur = current_version_entry(law)
    body = load_version(law, cur["id"]) if cur else {"articles": [], "byeol": []}
    art7 = next(
        (
            a
            for a in (body.get("articles") or [])
            if str(a.get("id") or "").endswith(":7") and "제7조의" not in (a.get("text") or "")[:20]
        ),
        None,
    )
    before = (art7 or {}).get("text") or ""
    if "20분의 1" not in before:
        before = (
            "제7조(차임 등의 증감청구권)\n"
            "② 제1항에 따른 증액청구는 약정한 차임이나 보증금의 20분의 1의 금액을 초과하지 못한다."
        )
    after = before.replace("20분의 1", "10분의 1") + "\n【모의】증액 상한 시연용 변경(20분의 1→10분의 1)."
    # 현행 카드 파일은 건드리지 않고, 메모리상 카드에 숫자 문구를 넣어 본문 수정 능력 확인
    base = next(c for c in load_domain_cards("LEASE") if c["id"] == "LEASE-RENT")
    card = dict(base)
    card["safe"] = [
        "차임·보증금 증액이 법정 상한(20분의 1) 이내이거나 일방 확정 증액 없음"
    ]
    card["violation"] = [
        "증액이 20분의 1을 초과하거나 임대인 일방 인상 확정"
    ]
    card["check_if"] = list(base.get("check_if") or [])
    card["basis"] = list(base.get("basis") or [])
    # 2020 적용례(versions에 등록된 문구)를 후보에 포함
    exp_quote = (
        "제2조(계약갱신 요구 등에 관한 적용례) ① 제6조의3 및 제7조의 개정규정은 "
        "이 법 시행 당시 존속 중인 임대차에 대하여도 적용한다."
    )
    byeol_units = list(body.get("byeol") or [])
    # 모의 부칙 적용례 한 줄 추가(후보 추출용, 저장소 파일 미기록)
    mock_byeol = {
        "announced": "2020-07-31",
        "number": "mock",
        "lines": [
            "제1조(시행일) 이 법은 공포한 날부터 시행한다.",
            exp_quote,
            "제3조(경과조치) 이 법 시행 전에 체결된 임대차에 대하여는 종전의 규정에 따른다.",
        ],
        "text": "\n".join(
            [
                "부칙 <모의>",
                "제1조(시행일) 이 법은 공포한 날부터 시행한다.",
                exp_quote,
                "제3조(경과조치) 이 법 시행 전에 체결된 임대차에 대하여는 종전의 규정에 따른다.",
            ]
        ),
    }
    byeol_units = byeol_units + [mock_byeol]
    return {
        "name": "모의 주임법 제7조 증액상한 20분의1→10분의1",
        "card": card,
        "before_text": before,
        "after_text": after,
        "byeol_text": mock_byeol["text"],
        "byeol_units": [mock_byeol],
        "apply_rule_hint": None,
        "rule_quote_hint": exp_quote,
        "out_stem": "review2_LEASE-RENT_mock",
        "expected": {
            "apply_rule": "in_force",
            "quote": exp_quote,
            "version": "모의",
            "body_new_number": "10분의 1",
            "body_old_number": "20분의 1",
        },
        "label": "모의",
    }


def run_case(case: dict, *, tries: int = 3) -> dict:
    attempts = []
    exp = case.get("expected") or {}
    for i in range(1, tries + 1):
        prop = propose_for_card(
            case["card"],
            before_text=case["before_text"],
            after_text=case["after_text"],
            byeol_text=case.get("byeol_text") or "",
            byeol_units=case.get("byeol_units"),
            apply_rule_hint=case.get("apply_rule_hint"),
            rule_quote_hint=case.get("rule_quote_hint"),
            wait_gpu=True,
            out_name=f"{datetime.now().strftime('%Y%m%d')}_{case['out_stem']}_try{i}.yaml",
        )
        out = CRITERIA_PROPOSALS / f"{prop['day']}_{case['out_stem']}_try{i}.yaml"
        dump_yaml({k: v for k, v in prop.items() if k != "path"}, out)
        prop["path"] = str(out)

        cands = prop.get("rule_candidates") or []
        expected_idx = _match_candidate_index(cands, exp.get("quote"))
        v = prop.get("validation") or {}
        body_ok = bool(v.get("body_ok"))
        rule_ok = bool(v.get("rule_ok"))
        model_idx = prop.get("rule_index_model")
        if model_idx is None:
            model_idx = prop.get("rule_index")
        model_rule = prop.get("apply_rule_model") or prop.get("apply_rule")
        filled_quote = prop.get("rule_quote")
        apply_match = (model_rule == exp.get("apply_rule")) if exp.get("apply_rule") else None
        # index가 기대 후보와 같은지 (채워진 quote 기준)
        idx_match = None
        if expected_idx is not None:
            try:
                idx_match = int(prop.get("rule_index") or -1) == int(expected_idx)
            except (TypeError, ValueError):
                idx_match = False
        quote_match = bool(
            filled_quote and exp.get("quote") and _norm(filled_quote) == _norm(exp.get("quote"))
            or (
                filled_quote
                and exp.get("quote")
                and (_norm(exp["quote"]) in _norm(filled_quote) or _norm(filled_quote) in _norm(exp["quote"]))
            )
        )
        proposed = prop.get("proposed") or {}
        prop_blob = json.dumps(proposed, ensure_ascii=False)
        body_has_new = None
        body_still_old = None
        if exp.get("body_new_number"):
            body_has_new = exp["body_new_number"] in prop_blob
            body_still_old = exp.get("body_old_number") in prop_blob and not body_has_new

        row = {
            "try": i,
            "path": str(out),
            "status": prop.get("status"),
            "body_ok": body_ok,
            "rule_ok": rule_ok,
            "llm_parse_ok": prop.get("llm_parse_ok"),
            "reason": prop.get("reason"),
            "model_rule_index": model_idx,
            "filled_rule_index": prop.get("rule_index"),
            "expected_rule_index": expected_idx,
            "model_apply_rule": model_rule,
            "filled_apply_rule": prop.get("apply_rule"),
            "expected_apply_rule": exp.get("apply_rule"),
            "apply_rule_match": apply_match,
            "rule_index_match": idx_match,
            "rule_quote_match": quote_match,
            "rule_quote": filled_quote,
            "body_has_new_number": body_has_new,
            "body_still_old_only": body_still_old,
            "proposed": proposed,
            "before_card": prop.get("before_card"),
            "n_candidates": len(cands),
            "validation_errors": v.get("errors") or [],
            "label": case.get("label"),
        }
        attempts.append(row)
    body_pass = sum(1 for a in attempts if a["body_ok"])
    rule_pass = sum(1 for a in attempts if a["rule_ok"])
    return {
        "name": case["name"],
        "label": case.get("label"),
        "expected": exp,
        "attempts": attempts,
        "body_pass": body_pass,
        "rule_pass": rule_pass,
        "n": len(attempts),
    }


def _md_table_case(case_res: dict) -> list[str]:
    lines = [
        f"## {case_res['name']}" + (f" ({case_res['label']})" if case_res.get("label") else ""),
        "",
        f"- 기대 apply_rule (versions): `{case_res['expected'].get('apply_rule')}`",
        f"- 기대 quote (versions): `{_norm(case_res['expected'].get('quote'))[:120]}`",
        f"- (가) 본문 통과: **{case_res['body_pass']}/{case_res['n']}**",
        f"- (나) 적용근거 통과: **{case_res['rule_pass']}/{case_res['n']}**",
        "",
        "| 시도 | (가) body_ok | (나) rule_ok | 모델 rule_index | 기대 index | index일치 | 모델 apply_rule | 기대 apply_rule | apply일치 | quote일치 | 상태 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a in case_res["attempts"]:
        lines.append(
            "| {n} | {body} | {rule} | {mi} | {ei} | {im} | {mar} | {ear} | {am} | {qm} | {st} |".format(
                n=a["try"],
                body="통과" if a["body_ok"] else "실패",
                rule="통과" if a["rule_ok"] else "실패",
                mi=a["model_rule_index"],
                ei=a["expected_rule_index"],
                im=("예" if a["rule_index_match"] else "아니오") if a["rule_index_match"] is not None else "-",
                mar=a["model_apply_rule"],
                ear=a["expected_apply_rule"],
                am=("예" if a["apply_rule_match"] else "아니오") if a["apply_rule_match"] is not None else "-",
                qm="예" if a["rule_quote_match"] else "아니오",
                st=a["status"],
            )
        )
    if case_res["expected"].get("body_new_number"):
        lines.append("")
        lines.append(
            "| 시도 | 본문에 새 숫자(10분의 1) | 옛 숫자만 | proposed 요약 |"
        )
        lines.append("|---|---|---|---|")
        for a in case_res["attempts"]:
            safe = (a.get("proposed") or {}).get("safe") or []
            viol = (a.get("proposed") or {}).get("violation") or []
            summary = " / ".join(str(x) for x in (safe[:1] + viol[:1]))[:100]
            lines.append(
                f"| {a['try']} | {'예' if a.get('body_has_new_number') else '아니오'} | "
                f"{'예' if a.get('body_still_old_only') else '아니오'} | {summary} |"
            )
    lines.append("")
    return lines


def write_review_md(results: dict, hashes: list[dict], live: dict) -> Path:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    out = LAWWATCH_OUT / "proposal_review2.md"
    lines = [
        "# 수정안 구조 변경 후 리뷰 (proposal_review2)",
        "",
        f"- 실행: `{results['ran_at']}`",
        "- 명령: `python -X utf8 eval/lawwatch_proposal_review2.py`",
        "- 프롬프트 미변경. 현행 카드·corpus 미기록.",
        "",
        "## 요약",
        "",
    ]
    for c in results["cases"]:
        lines.append(
            f"- {c['name']}: (가) {c['body_pass']}/{c['n']} · (나) {c['rule_pass']}/{c['n']}"
        )
    lines.append("")
    for c in results["cases"]:
        lines.extend(_md_table_case(c))

    lines.append("## live_check")
    lines.append("")
    if live.get("has_key"):
        lines.append(f"- LAW_OC 있음 → 실제 API 감지 실행. 상세: `{live.get('path')}`")
        lines.append(f"- summary: `{live.get('summary')}`")
    else:
        lines.append("- **키 없음** (LAW_OC 환경변수 미설정). 키 값은 출력하지 않음.")
        lines.append(f"- 기록: `{live.get('path')}`")
    lines.append("")
    lines.append("## 현행 카드·corpus 해시")
    lines.append("")
    lines.append("| 파일 | 기대 | 현재 | 일치 |")
    lines.append("|---|---|---|---|")
    for h in hashes:
        lines.append(
            f"| `{h['file']}` | `{h['expected'][:16]}…` | `{h['got'][:16]}…` | {'예' if h['match'] else '아니오'} |"
        )
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def verify_hashes(expected: dict[str, str]) -> list[dict]:
    rows = []
    for rel, exp in expected.items():
        path = APP_ROOT / rel
        got = _sha256_file(path) if path.exists() else ""
        rows.append({"file": rel, "expected": exp, "got": got, "match": got == exp})
    return rows


def run_live_check() -> dict:
    key = os.environ.get("LAW_OC")
    out_md = LAWWATCH_OUT / "live_check.md"
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    if not key:
        text = (
            "# 실제 API 감지\n\n"
            "- **키 없음** (`LAW_OC` 환경변수 미설정)\n"
            "- 키 값은 출력하지 않음\n"
            f"- 확인 시각: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        out_md.write_text(text, encoding="utf-8")
        return {"has_key": False, "path": str(out_md)}

    from rag.lawwatch.check import check_all

    payload = check_all(offline=False)
    # 키 값 제거 보장
    summary = payload.get("summary") or {}
    lines = [
        "# 실제 API 감지 (live)",
        "",
        f"- 실행: {datetime.now().isoformat(timespec='seconds')}",
        "- LAW_OC 설정됨(값은 출력하지 않음)",
        f"- offline_forced: {payload.get('offline_forced')}",
        f"- summary: {json.dumps(summary, ensure_ascii=False)}",
        "",
        "| 법령 | mode | status | note |",
        "|---|---|---|---|",
    ]
    for r in payload.get("results") or payload.get("rows") or []:
        lines.append(
            f"| {r.get('law') or r.get('name')} | {r.get('mode')} | {r.get('status')} | "
            f"{(r.get('note') or '')[:80]} |"
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    (LAWWATCH_OUT / "latest_check.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"has_key": True, "path": str(out_md), "summary": summary}


def main() -> None:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    # 기대 해시(이전 검증 기준)
    expected_hashes = {
        "criteria/LAB_cards.yaml": "b56aea668284c9229292d6376c1e257df36279548cedd9983431855eff997e50",
        "criteria/LEASE_cards.yaml": "8e8556c87a19257eb2908e10af7acd3ca11bbd5802c498379f5e232e84a6bcff",
        "criteria/LOAN_cards.yaml": "aa80c747fc6f175c4e5613a1402fa5d72e99fdeab565ad655eb09188a43c8998",
        "corpus/records.json": "3502e28d6a079936f0935bf2feb3f6056c981b6126d879ff85d4c3027998b367",
    }

    cases = [
        run_case(_interest_case(), tries=3),
        run_case(_minwage_case(), tries=3),
        run_case(_lease_rent_mock_case(), tries=3),
    ]
    results = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "cases": cases,
    }
    (LAWWATCH_OUT / "proposal_review2.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    live = run_live_check()
    hashes = verify_hashes(expected_hashes)
    (LAWWATCH_OUT / "hash_verify_review2.json").write_text(
        json.dumps({"hashes": hashes, "live": {"has_key": live.get("has_key")}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = write_review_md(results, hashes, live)
    print(
        json.dumps(
            {
                "md": str(md),
                "json": str(LAWWATCH_OUT / "proposal_review2.json"),
                "body_rule": [(c["name"], c["body_pass"], c["rule_pass"]) for c in cases],
                "hashes_ok": all(h["match"] for h in hashes),
                "live_has_key": live.get("has_key"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
