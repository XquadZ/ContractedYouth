# -*- coding: utf-8 -*-
"""LAW_WATCH 단위 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.lawwatch.byeol import quote_in_source, resolve_apply_rule
from rag.lawwatch.diff import diff_articles, find_impacted_cards
from rag.lawwatch.select import select_versions
from rag.lawwatch.versions_io import dump_yaml, load_card_versions, versions_path


def test_diff_add_delete_change_format():
    before = [
        {"id": "law:X:1", "text": "갑 을 병"},
        {"id": "law:X:2", "text": "동일"},
        {"id": "law:X:3", "text": "바뀌기 전"},
    ]
    after = [
        {"id": "law:X:2", "text": "동일"},
        {"id": "law:X:3", "text": "바뀐 후"},
        {"id": "law:X:4", "text": "새 조문"},
        {"id": "law:X:1", "text": "갑  을  병"},  # 형식만
    ]
    ch = {c["id"]: c["kind"] for c in diff_articles(before, after)}
    assert ch["law:X:4"] == "추가"
    assert ch["law:X:3"] == "변경"
    assert ch["law:X:1"] == "형식 변경"
    assert "law:X:2" not in ch


def test_impact_cards():
    cards = [
        {"id": "A", "basis": ["law:근로기준법:17"], "_domain": "LAB"},
        {"id": "B", "basis": ["law:민법:598"], "_domain": "LOAN"},
    ]
    hit = find_impacted_cards(["law:근로기준법:17"], cards)
    assert [h["card_id"] for h in hit] == ["A"]


def test_select_single_version_same(tmp_path, monkeypatch):
    from rag.lawwatch import versions_io

    monkeypatch.setattr(versions_io, "CRITERIA_VERSIONS", tmp_path)
    dump_yaml(
        {
            "card_id": "T1",
            "versions": [
                {
                    "version": 1,
                    "effective_from": "2020-01-01",
                    "effective_to": None,
                    "apply_rule": "contract_date",
                    "card": {"id": "T1", "safe": ["a"]},
                }
            ],
        },
        tmp_path / "T1.yaml",
    )
    # reload path
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", lambda cid: load_card_versions(cid) if False else versions_io.load_card_versions(cid))
    # patch sorted_versions/load in select module
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", versions_io.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", versions_io.sorted_versions)
    sel = select_versions("T1", contract_date="2024-01-01")
    assert sel["mode"] == "single"
    assert sel["cards"][0]["safe"] == ["a"]


def _write_two(tmp_path, rule: str):
    from rag.lawwatch import versions_io

    dump_yaml(
        {
            "card_id": "T2",
            "versions": [
                {
                    "version": 1,
                    "effective_from": "2018-02-08",
                    "effective_to": "2021-07-06",
                    "apply_rule": rule,
                    "card": {"id": "T2", "safe": ["v1"]},
                },
                {
                    "version": 2,
                    "effective_from": "2021-07-07",
                    "effective_to": None,
                    "apply_rule": rule,
                    "card": {"id": "T2", "safe": ["v2"]},
                },
            ],
        },
        tmp_path / "T2.yaml",
    )
    return versions_io


def test_select_contract_date(tmp_path, monkeypatch):
    vio = _write_two(tmp_path, "contract_date")
    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    a = select_versions("T2", contract_date="2021-06-01", today="2026-01-01")
    b = select_versions("T2", contract_date="2026-01-01", today="2026-01-01")
    assert a["cards"][0]["safe"] == ["v1"]
    assert b["cards"][0]["safe"] == ["v2"]


def test_select_in_force(tmp_path, monkeypatch):
    vio = _write_two(tmp_path, "in_force")
    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    # 계약일이 오래돼도 오늘 버전
    sel = select_versions("T2", contract_date="2019-01-01", today="2026-01-01")
    assert sel["cards"][0]["safe"] == ["v2"]


def test_select_performance_period(tmp_path, monkeypatch):
    from rag.lawwatch import versions_io as vio

    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    dump_yaml(
        {
            "card_id": "T3",
            "versions": [
                {"version": 1, "effective_from": "2026-01-01", "effective_to": "2026-12-31", "apply_rule": "performance_period", "card": {"safe": ["2026"]}},
                {"version": 2, "effective_from": "2027-01-01", "effective_to": None, "apply_rule": "performance_period", "card": {"safe": ["2027"]}},
            ],
        },
        tmp_path / "T3.yaml",
    )
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    sel = select_versions("T3", period_start="2026-06-01", period_end="2027-06-01", today="2026-11-01")
    safes = [c["safe"][0] for c in sel["cards"]]
    assert safes == ["2026", "2027"]


def test_select_unknown_need_check(tmp_path, monkeypatch):
    vio = _write_two(tmp_path, "unknown")
    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    sel = select_versions("T2", contract_date="2020-01-01", today="2026-01-01")
    assert sel["flags"]["need_check"] is True
    assert any("다를 수 있어요" in n for n in sel["notices"])


def test_select_no_contract_date(tmp_path, monkeypatch):
    vio = _write_two(tmp_path, "contract_date")
    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    sel = select_versions("T2", contract_date=None, today="2026-01-01")
    assert sel["flags"]["date_missing"] is True
    assert sel["cards"][0]["safe"] == ["v2"]


def test_select_scheduled_notice(tmp_path, monkeypatch):
    from rag.lawwatch import versions_io as vio

    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)
    dump_yaml(
        {
            "card_id": "T4",
            "versions": [
                {"version": 1, "effective_from": "2020-01-01", "effective_to": "2027-05-31", "apply_rule": "contract_date", "card": {"safe": ["now"]}, "summary": "이자 상한 변경"},
                {"version": 2, "effective_from": "2027-06-01", "effective_to": None, "apply_rule": "contract_date", "card": {"safe": ["soon"]}, "summary": "이자 상한 변경"},
            ],
        },
        tmp_path / "T4.yaml",
    )
    monkeypatch.setattr("rag.lawwatch.select.load_card_versions", vio.load_card_versions)
    monkeypatch.setattr("rag.lawwatch.select.sorted_versions", vio.sorted_versions)
    sel = select_versions("T4", contract_date="2026-01-01", period_start="2026-01-01", period_end="2027-12-31", today="2026-11-01")
    assert any("2027-06-01" in n for n in sel["notices"])


def test_byeol_quote_missing_unknown():
    units = [{"announced": "2021-04-06", "number": "31593", "lines": ["제2조(적용례) 이 영은 이 영 시행 이후 계약을 체결하거나 갱신하는 분부터 적용한다."], "text": "제2조(적용례) 이 영은 이 영 시행 이후 계약을 체결하거나 갱신하는 분부터 적용한다."}]
    ok = resolve_apply_rule(units, announced="2021-04-06")
    assert ok["apply_rule"] == "contract_date"
    assert quote_in_source(ok["rule_quote"], units[0]["text"])
    # 없는 문장
    bad = resolve_apply_rule(units, announced="2021-04-06", extra_quotes=["이 문장은 원문에 없다"])
    # extra가 매칭되면 그걸 쓸 수 있으나 quote_in_source가 원문+extra에 대해 검사
    # 가짜만 있고 패턴 미매칭이면 unknown — extra에 contract 패턴 없으면
    empty = resolve_apply_rule([{"lines": ["아무 내용 없음"], "text": "아무 내용 없음"}])
    assert empty["apply_rule"] == "unknown"


def test_no_version_file_equals_current():
    sel = select_versions("NO_SUCH_CARD", current_card={"id": "NO_SUCH_CARD", "safe": ["x"]})
    assert sel["mode"] == "current_only"
    assert sel["cards"][0]["safe"] == ["x"]


def test_offline_check_runs():
    from rag.lawwatch.check import check_all

    # 저장소가 비어 있어도 멈추지 않음
    payload = check_all(offline=True, laws=[])
    assert payload["n"] == 0


def test_announce_no_format_only_not_amendment():
    """형식만 다른 공포번호(HTML 강조 dict vs 평문)는 개정 아님."""
    from rag.lawwatch.check import compare_meta, normalize_announce_no

    highlighted = {"content": ["3", "593"], "strong": {"content": "1", "class": "tbl_tx_type"}}
    assert normalize_announce_no(highlighted) == "31593"
    assert normalize_announce_no("31593") == "31593"
    assert normalize_announce_no("제31593호") == "31593"

    local = {"mst": "230727", "announce_no": "31593", "effective": "2021-07-07", "announced": "2021-04-06"}
    remote = {
        "mst": "230727",
        "announce_no": normalize_announce_no(highlighted),
        "effective": "2021-07-07",
        "announced": "2021-04-06",
    }
    status, note = compare_meta(local, remote)
    assert status == "변경 없음"

    # MST 같고 시행일 같은데 공포번호 숫자만 어긋나도(참고) 개정 아님
    status2, _ = compare_meta(
        {"mst": "1", "announce_no": "31593", "effective": "2021-07-07", "announced": "2021-04-06"},
        {"mst": "1", "announce_no": "593", "effective": "2021-07-07", "announced": "2021-04-06"},
    )
    assert status2 == "변경 없음"


def test_mst_missing_filled_not_amendment():
    """저장본 MST 없으면 API/기준선으로 보충하며 개정으로 보지 않는다."""
    from rag.lawwatch.check import compare_meta, fill_local_mst

    local = {"mst": "", "announce_no": "31593", "effective": "2021-07-07", "announced": "2021-04-06"}
    remote = {"mst": "230727", "announce_no": "31593", "effective": "2021-07-07", "announced": "2021-04-06"}
    filled, note = fill_local_mst("이자제한법 제2조제1항의 최고이자율에 관한 규정", local, remote)
    assert filled.get("mst") == "230727"
    assert "MST 보충" in note
    status, _ = compare_meta(filled, remote)
    assert status == "변경 없음"


def test_approve_requires_admin_apply_rule(tmp_path, monkeypatch):
    """관리자 선택 없이는 승인 불가. AI 추천만으로는 통과하지 않는다."""
    from rag.lawwatch import apply as apply_mod
    from rag.lawwatch import versions_io as vio
    from rag.lawwatch.apply import _proposal_approvable, approve_proposal, set_proposal_apply_rule
    from rag.lawwatch.versions_io import dump_yaml

    monkeypatch.setattr(apply_mod, "CRITERIA_VERSIONS", tmp_path)
    monkeypatch.setattr(apply_mod, "APPLIED_LOG", tmp_path / "applied_log.json")
    monkeypatch.setattr(apply_mod, "LAWWATCH_OUT", tmp_path)
    monkeypatch.setattr(vio, "CRITERIA_VERSIONS", tmp_path)

    prop = {
        "card_id": "TEST-ADMIN-APPLY",
        "status": "AI 초안 · 적용 기준은 관리자가 정해요",
        "apply_rule": "contract_date",
        "ai_apply_rule": "contract_date",
        "rule_index": 1,
        "ai_rule_index": 1,
        "rule_quote": "제2조(적용례) 이 영은 시행 이후 계약부터 적용한다.",
        "ai_rule_quote": "제2조(적용례) 이 영은 시행 이후 계약부터 적용한다.",
        "admin_apply_set": False,
        "rule_candidates": [
            {"index": 1, "text": "제2조(적용례) 이 영은 시행 이후 계약부터 적용한다."},
        ],
        "proposed": {"safe": ["a"], "violation": ["b"], "check_if": [], "basis": ["law:X:1"]},
        "validation": {"body_ok": True, "rule_ok": True, "ok": True},
        "effective_from": "2099-01-01",
    }
    path = tmp_path / "prop.yaml"
    dump_yaml(prop, path)

    ok, reason = _proposal_approvable(prop)
    assert ok is False
    assert "관리자" in reason

    # 관리자 선택 없이 approve
    res = approve_proposal(path, who="test", update_current_cards=False)
    assert res.get("ok") is False
    assert res.get("error") == "not_approvable"

    # 관리자가 선택(추천 확인) 후 승인
    set_res = set_proposal_apply_rule(path, apply_rule="contract_date", rule_index=1, who="admin")
    assert set_res.get("ok") is True
    res2 = approve_proposal(path, who="admin", update_current_cards=False, effective_from="2099-01-01")
    assert res2.get("ok") is not False
    assert res2.get("error") != "not_approvable"
    assert res2.get("card_id") == "TEST-ADMIN-APPLY"
