# -*- coding: utf-8 -*-
"""시연: 감지→비교→영향→수정안→승인→점검→되돌리기 + 날짜별 버전 선택 표.
시연 후 현행 카드·법령 모음은 원래대로 복구. 버전 파일은 남긴다.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.lawwatch.apply import approve_proposal, quick_regression, revert_last
from rag.lawwatch.check import check_all
from rag.lawwatch.diff import diff_versions, write_changes_report
from rag.lawwatch.paths import CRITERIA_PROPOSALS, LAWWATCH_OUT
from rag.lawwatch.propose import propose_for_card
from rag.lawwatch.select import select_versions
from rag.lawwatch.store import current_version_entry, load_index, load_version
from rag.criteria import load_domain_cards
from rag.yamlutil import load as load_yaml

DEMO = LAWWATCH_OUT / "demo"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scene_select_table() -> list[dict]:
    rows = []
    # 1) 최저임금 2026-2027
    sel = select_versions(
        "LAB-MINWAGE",
        contract_date="2026-03-01",
        period_start="2026-03-01",
        period_end="2027-12-31",
        today="2026-11-01",
        current_card=next(c for c in load_domain_cards("LAB") if c["id"] == "LAB-MINWAGE"),
    )
    rows.append(
        {
            "scene": "최저임금 2026~2027 근로계약",
            "contract_date": "2026-03-01",
            "period": "2026-03-01~2027-12-31",
            "rule": sel.get("mode"),
            "versions": [c.get("_version") for c in sel.get("cards") or []],
            "safe_heads": [(c.get("safe") or [""])[0][:60] for c in sel.get("cards") or []],
            "notices": sel.get("notices"),
        }
    )
    # 2) 이자 22% — 계약일 전/후
    for cd in ("2021-06-01", "2026-01-15"):
        sel = select_versions(
            "LOAN-INTEREST",
            contract_date=cd,
            today="2026-11-01",
            current_card=next(c for c in load_domain_cards("LOAN") if c["id"] == "LOAN-INTEREST"),
        )
        card = (sel.get("cards") or [{}])[0]
        rows.append(
            {
                "scene": f'차용 "연 22%" 계약일 {cd}',
                "contract_date": cd,
                "period": None,
                "rule": sel.get("mode"),
                "versions": [card.get("_version")],
                "safe_heads": [(card.get("safe") or [""])[0][:60]],
                "hint": "당시 24% 상한 → 22% 이내" if cd.startswith("2021-06") else "현행 20% 상한 → 22% 위반",
                "notices": sel.get("notices"),
            }
        )
    # 3) 주임법 in_force — 2019 계약
    sel = select_versions(
        "LEASE-RENEW",
        contract_date="2019-05-01",
        period_start="2019-05-01",
        period_end="2021-04-30",
        today="2026-11-01",
        current_card=next(c for c in load_domain_cards("LEASE") if c["id"] == "LEASE-RENEW"),
    )
    rows.append(
        {
            "scene": "2019년 임대차 + 계약갱신요구권(in_force)",
            "contract_date": "2019-05-01",
            "period": "2019-05-01~2021-04-30",
            "rule": sel.get("mode"),
            "versions": [c.get("_version") for c in sel.get("cards") or []],
            "safe_heads": [(c.get("safe") or [""])[0][:60] for c in sel.get("cards") or []],
            "notices": sel.get("notices"),
        }
    )
    return rows


def flow_interest() -> dict:
    """과거→현행 이자규정 비교 흐름 + 승인/되돌리기."""
    law = "이자제한법 제2조제1항의 최고이자율에 관한 규정"
    index = load_index(law)
    past = next(v for v in index["versions"] if "24" in str(v.get("id")) or v.get("id") == "past_20180208_24pct")
    cur = current_version_entry(law)
    diff = diff_versions(law, past["id"], cur["id"])
    paths = write_changes_report(diff, day=datetime.now().strftime("%Y%m%d"))

    card = next(c for c in load_domain_cards("LOAN") if c["id"] == "LOAN-INTEREST")
    before = next((c for c in diff["changes"] if "변경" in c["kind"] or c["kind"] == "변경"), None)
    before_text = (before or {}).get("before") or ""
    after_text = (before or {}).get("after") or ""
    byeol_text = "\n".join(u.get("text") or "" for u in load_version(law, cur["id"]).get("byeol") or [])
    # 승인 전 카드 해시 백업
    cards_path = APP / "criteria" / "LOAN_cards.yaml"
    hash_before = _sha(cards_path)
    backup_copy = DEMO / "LOAN_cards.yaml.before_demo"
    shutil.copy2(cards_path, backup_copy)

    prop = propose_for_card(
        card,
        before_text=before_text,
        after_text=after_text,
        byeol_text=byeol_text,
        apply_rule_hint=(diff.get("byeol") or {}).get("apply_rule"),
        rule_quote_hint=(diff.get("byeol") or {}).get("rule_quote"),
        wait_gpu=False,
    )
    validation_ok = bool((prop.get("validation") or {}).get("ok"))
    approve = None
    rev = None
    # 코드 검사 실패한 수정안은 승인하지 않는다.
    if validation_ok:
        approve = approve_proposal(
            Path(prop["path"]),
            effective_from="2021-07-07",
            who="demo",
            update_current_cards=True,
        )
        if approve.get("ok") is False and approve.get("error") == "not_approvable":
            approve = approve  # 그대로 기록
        else:
            rev = revert_last(card_id="LOAN-INTEREST", who="demo")
    else:
        approve = {
            "ok": False,
            "skipped": True,
            "reason": "validation_failed",
            "status": prop.get("status"),
            "errors": (prop.get("validation") or {}).get("errors"),
        }
    reg = quick_regression(
        ["LOAN-INTEREST"],
        before_cards={"LOAN-INTEREST": card},
        after_cards={"LOAN-INTEREST": prop.get("proposed") or {}},
        use_llm=False,
    )
    hash_after = _sha(cards_path)
    # 강제 복구(현행 카드는 건드리지 않는 것이 원칙 — 승인했을 때만 복구)
    if hash_after != hash_before:
        shutil.copy2(backup_copy, cards_path)
        hash_after = _sha(cards_path)
    return {
        "check": check_all(offline=True, laws=[law]),
        "diff_n": diff.get("n_changes"),
        "impacted": [c["card_id"] for c in diff.get("impacted_cards") or []],
        "proposal": prop.get("path"),
        "validation_ok": validation_ok,
        "approve": approve,
        "regression": reg.get("path"),
        "revert": rev,
        "card_hash_before": hash_before,
        "card_hash_after_restore": hash_after,
        "hash_match": hash_before == hash_after,
        "changes_report": paths,
    }


def mock_detect_flow() -> dict:
    """연혁에 없는 조문 1개를 고친 모의 파일로 감지 흐름."""
    from copy import deepcopy

    from rag.lawwatch.store import law_dir, register_body, save_index, load_index

    law = "이자제한법"
    cur = current_version_entry(law)
    if not cur:
        return {"skipped": True, "reason": "이자제한법 현행 없음"}
    body = load_version(law, cur["id"])
    mock = deepcopy(body)
    arts = mock.get("articles") or []
    if not arts:
        return {"skipped": True, "reason": "조문 없음"}
    # 모의: 카드 basis에 걸리는 조문(이자제한법 제2조)만 변경. "모의" 표시 유지.
    target_idx = None
    for i, art in enumerate(arts):
        aid = str(art.get("id") or "")
        if aid.endswith(":2") or str(art.get("article_no") or "") == "2":
            target_idx = i
            break
    if target_idx is None:
        return {"skipped": True, "reason": "이자제한법 제2조 없음", "label": "모의"}
    arts[target_idx] = dict(arts[target_idx])
    arts[target_idx]["text"] = (arts[target_idx].get("text") or "") + "\n【모의】이 문구는 시연용 변경입니다."
    mock["articles"] = arts
    mock_meta = dict(mock.get("meta") or {})
    mock_meta["status"] = "예정"
    mock_meta["synthetic"] = True
    mock_meta["synthetic_note"] = "모의"
    mock_id = "mock_demo_change"
    out = law_dir(law) / f"{mock_id}.json"
    mock["meta"] = mock_meta
    out.write_text(json.dumps(mock, ensure_ascii=False, indent=2), encoding="utf-8")
    index = load_index(law)
    versions = [v for v in index.get("versions") or [] if v.get("id") != mock_id]
    versions.append(
        {
            "id": mock_id,
            "status": "예정",
            "effective": "2099-01-01",
            "announced": datetime.now().strftime("%Y-%m-%d"),
            "file": out.name,
            "synthetic": True,
            "note": "모의",
        }
    )
    index["versions"] = versions
    save_index(law, index)
    diff = diff_versions(law, cur["id"], mock_id)
    return {"mock_id": mock_id, "label": "모의", "n_changes": diff.get("n_changes"), "changes": diff.get("changes")[:3]}


def main() -> None:
    DEMO.mkdir(parents=True, exist_ok=True)
    # corpus 해시(법령 모음) — 건드리지 않았는지 확인
    corpus = APP / "corpus" / "records.json"
    corpus_hash_before = _sha(corpus) if corpus.exists() else None

    flow = flow_interest()
    table = scene_select_table()
    mock = mock_detect_flow()

    corpus_hash_after = _sha(corpus) if corpus.exists() else None
    report = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "flow": flow,
        "select_table": table,
        "mock": mock,
        "corpus_hash_before": corpus_hash_before,
        "corpus_hash_after": corpus_hash_after,
        "corpus_unchanged": corpus_hash_before == corpus_hash_after,
        "loan_cards_restored": flow.get("hash_match"),
    }
    out = DEMO / "demo_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = DEMO / "demo_report.md"
    lines = ["# LAW_WATCH 시연", "", f"- 시각: {report['ran_at']}", f"- 카드 해시 복구: {flow.get('hash_match')}", f"- corpus 유지: {report['corpus_unchanged']}", "", "## 흐름", ""]
    lines.append(f"| 단계 | 결과 |")
    lines.append(f"|---|---|")
    lines.append(f"| 감지(offline) | {(flow.get('check') or {}).get('summary')} |")
    lines.append(f"| 비교 변경 수 | {flow.get('diff_n')} |")
    lines.append(f"| 영향 카드 | {flow.get('impacted')} |")
    lines.append(f"| 수정안 | `{flow.get('proposal')}` ok={flow.get('validation_ok')} |")
    lines.append(f"| 승인 | version={((flow.get('approve') or {}).get('version'))} |")
    lines.append(f"| 점검 | `{flow.get('regression')}` |")
    lines.append(f"| 되돌리기 | {flow.get('revert')} |")
    lines.append("")
    lines.append("## 날짜별 버전 선택")
    lines.append("")
    lines.append("| 장면 | 계약일 | 규칙 | 버전 | 안내 |")
    lines.append("|---|---|---|---|---|")
    for row in table:
        lines.append(
            f"| {row['scene']} | {row.get('contract_date')} | {row.get('rule')} | {row.get('versions')} | {row.get('hint') or row.get('notices')} |"
        )
    lines.append("")
    lines.append(f"## 모의 감지: {mock}")
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"out": str(out), "md": str(md), "hash_match": flow.get("hash_match"), "corpus_unchanged": report["corpus_unchanged"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
