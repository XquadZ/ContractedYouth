# -*- coding: utf-8 -*-
"""수정안 승인·반려·되돌리기·빠른 점검."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from rag.paths import APP
from rag.lawwatch.paths import APPLIED_LOG, CRITERIA_PROPOSALS, CRITERIA_VERSIONS, LAWWATCH_OUT
from rag.lawwatch.versions_io import dump_yaml, load_card_versions, save_card_versions
from rag.yamlutil import load as load_yaml

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_proposal(path: Path) -> dict:
    if path.suffix.lower() in (".yaml", ".yml"):
        return load_yaml(path) or {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_proposal(path: Path, data: dict) -> None:
    dump_yaml(data, path)


def _append_log(entry: dict) -> None:
    APPLIED_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if APPLIED_LOG.exists():
        log = json.loads(APPLIED_LOG.read_text(encoding="utf-8"))
    log.append(entry)
    APPLIED_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def _domain_for_card(card_id: str) -> str:
    if card_id.startswith("LAB"):
        return "LAB"
    if card_id.startswith("LEASE"):
        return "LEASE"
    if card_id.startswith("LOAN"):
        return "LOAN"
    return "LAB"


def _cards_file(domain: str) -> Path:
    return APP / "criteria" / f"{domain}_cards.yaml"


def _backup_file(path: Path, tag: str) -> Path | None:
    if not path.exists():
        return None
    # CLAUDE.md: *_v숫자 백업, 삭제 금지
    n = 1
    while True:
        cand = path.with_name(f"{path.stem}_v{n}{path.suffix}")
        if not cand.exists():
            shutil.copy2(path, cand)
            # also snapshot for revert with tag
            snap = path.with_name(f"{path.stem}.__lw_{tag}__{path.suffix}")
            shutil.copy2(path, snap)
            return cand
        n += 1


def reject_proposal(proposal_path: Path, *, reason: str = "") -> dict:
    data = _load_proposal(proposal_path)
    data["status"] = "반려"
    data["rejected_at"] = datetime.now().isoformat(timespec="seconds")
    data["reject_reason"] = reason
    _save_proposal(proposal_path, data)
    return {"status": "반려", "path": str(proposal_path)}


def _body_ok(data: dict) -> bool:
    v = data.get("validation") or {}
    if "body_ok" in v:
        return bool(v.get("body_ok"))
    if isinstance(v.get("body"), dict) and "ok" in v["body"]:
        return bool(v["body"]["ok"])
    # 구형식
    if v.get("manual"):
        return False
    return v.get("ok") is not False


def _rule_ok(data: dict) -> bool:
    v = data.get("validation") or {}
    if "rule_ok" in v:
        return bool(v.get("rule_ok"))
    if isinstance(v.get("rule"), dict) and "ok" in v["rule"]:
        return bool(v["rule"]["ok"])
    return bool(v.get("ok"))


def _proposal_approvable(
    data: dict,
    *,
    admin_apply_rule: str | None = None,
    admin_rule_index=None,
) -> tuple[bool, str]:
    """(가) 본문 실패 → 승인 불가.
    (가)만 통과 → 관리자가 적용 기준·근거를 고른 뒤에만 승인.
    둘 다 통과(대기) → 승인 가능.
    """
    status = (data.get("status") or "").strip()
    if not _body_ok(data) or status == "수동 수정 필요":
        return False, "본문 검사 실패(수동 수정 필요)"

    apply_rule = admin_apply_rule or data.get("apply_rule")
    rule_index = data.get("rule_index") if admin_rule_index is None else admin_rule_index
    rule_quote = data.get("rule_quote")
    admin_set = bool(data.get("admin_apply_set"))

    if status == "대기" and _rule_ok(data) and apply_rule not in (None, "", "unknown") and rule_quote:
        return True, ""

    # 본문만 통과 — 관리자 선택 필요
    if status.startswith("본문 승인 가능") or (not _rule_ok(data)):
        if admin_apply_rule:
            apply_rule = admin_apply_rule
        if admin_rule_index is not None or admin_set:
            if apply_rule and apply_rule != "unknown" and (rule_quote or admin_rule_index is not None):
                return True, ""
        if admin_set and apply_rule not in (None, "", "unknown") and rule_quote:
            return True, ""
        return False, "적용 기준을 관리자가 선택해야 함"

    if status == "대기":
        return True, ""
    return False, f"상태={status} — 승인 불가"


def set_proposal_apply_rule(
    proposal_path: Path,
    *,
    apply_rule: str,
    rule_index: int | None = None,
    who: str = "admin",
) -> dict:
    """관리자가 후보 목록에서 적용 기준·근거 문장을 직접 고른다."""
    from rag.lawwatch.byeol import fill_rule_from_index
    from rag.lawwatch.propose import APPLY_RULES

    data = _load_proposal(proposal_path)
    if not _body_ok(data):
        return {"ok": False, "error": "body_not_ok", "status": data.get("status")}
    if apply_rule not in APPLY_RULES or apply_rule == "unknown":
        return {"ok": False, "error": "apply_rule_invalid"}
    candidates = data.get("rule_candidates") or []
    filled = fill_rule_from_index(candidates, rule_index)
    if not filled["ok"]:
        return {"ok": False, "error": filled.get("reason") or "rule_index_invalid"}
    data["apply_rule"] = apply_rule
    data["rule_index"] = filled["rule_index"]
    data["rule_quote"] = filled["rule_quote"]
    data["admin_apply_set"] = True
    data["admin_apply_by"] = who
    data["admin_apply_at"] = datetime.now().isoformat(timespec="seconds")
    # 본문 통과 상태 유지·승인 대기로 승격 가능 표시
    data["status"] = "본문 승인 가능 · 적용 기준은 관리자가 선택"
    _save_proposal(proposal_path, data)
    return {
        "ok": True,
        "path": str(proposal_path),
        "apply_rule": apply_rule,
        "rule_index": filled["rule_index"],
        "rule_quote": filled["rule_quote"],
        "status": data["status"],
    }


def approve_proposal(
    proposal_path: Path,
    *,
    effective_from: str | None = None,
    who: str = "admin",
    update_current_cards: bool | None = None,
    admin_apply_rule: str | None = None,
    admin_rule_index=None,
) -> dict:
    data = _load_proposal(proposal_path)
    # 승인 직전 관리자 선택이 있으면 반영
    if admin_apply_rule is not None and admin_rule_index is not None:
        set_res = set_proposal_apply_rule(
            proposal_path, apply_rule=admin_apply_rule, rule_index=admin_rule_index, who=who
        )
        if not set_res.get("ok"):
            return {"ok": False, "error": "apply_rule_set_failed", "detail": set_res}
        data = _load_proposal(proposal_path)

    ok, reason = _proposal_approvable(
        data, admin_apply_rule=admin_apply_rule, admin_rule_index=admin_rule_index
    )
    if not ok:
        if not _body_ok(data):
            data["status"] = "수동 수정 필요"
            _save_proposal(proposal_path, data)
        return {
            "ok": False,
            "error": "not_approvable",
            "reason": reason,
            "status": data.get("status"),
            "path": str(proposal_path),
        }
    card_id = data["card_id"]
    proposed = data.get("proposed") or {}
    apply_rule = admin_apply_rule or data.get("apply_rule") or "unknown"
    rule_quote = data.get("rule_quote")
    ef = effective_from or data.get("effective_from") or date.today().isoformat()
    today = date.today().isoformat()

    # 버전 파일
    existing = load_card_versions(card_id) or {"card_id": card_id, "versions": []}
    versions = list(existing.get("versions") or [])
    # 이전 버전 effective_to 채우기
    from datetime import timedelta

    ef_d = date.fromisoformat(ef)
    prev_to = (ef_d - timedelta(days=1)).isoformat()
    for v in versions:
        if v.get("effective_to") in (None, "", "null"):
            # 새 버전보다 앞선 것만 닫음
            vf = v.get("effective_from")
            if vf and vf < ef:
                v["effective_to"] = prev_to
    new_ver_num = 1 + max([int(v.get("version") or 0) for v in versions] or [0])
    new_ver = {
        "version": new_ver_num,
        "effective_from": ef,
        "effective_to": None,
        "apply_rule": apply_rule,
        "rule_source": {
            "law": data.get("rule_law") or "",
            "quote": rule_quote or "",
        },
        "card": proposed,
        "status": "예약" if ef > today else "현행",
    }
    versions.append(new_ver)
    existing["versions"] = versions
    ver_path = save_card_versions(existing)

    # 시행일이 오늘 이전이면 현행 카드 파일 갱신
    did_update_cards = False
    backup = None
    domain = _domain_for_card(card_id)
    cards_path = _cards_file(domain)
    card_hash_before = _sha256_file(cards_path) if cards_path.exists() else None
    should_update = update_current_cards if update_current_cards is not None else (ef <= today)
    if should_update and cards_path.exists():
        backup = _backup_file(cards_path, tag=f"{card_id}_v{new_ver_num}")
        rows = load_yaml(cards_path) or []
        new_rows = []
        for row in rows:
            if isinstance(row, dict) and row.get("id") == card_id:
                updated = dict(row)
                for k, v in proposed.items():
                    updated[k] = v
                new_rows.append(updated)
            else:
                new_rows.append(row)
        if yaml is not None:
            cards_path.write_text(
                yaml.safe_dump(new_rows, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        did_update_cards = True

    data["status"] = "승인"
    data["approved_at"] = datetime.now().isoformat(timespec="seconds")
    data["approved_version"] = new_ver_num
    _save_proposal(proposal_path, data)

    entry = {
        "action": "approve",
        "who": who,
        "when": datetime.now().isoformat(timespec="seconds"),
        "card_id": card_id,
        "version": new_ver_num,
        "effective_from": ef,
        "proposal": str(proposal_path),
        "versions_file": str(ver_path),
        "updated_current_cards": did_update_cards,
        "backup": str(backup) if backup else None,
        "card_hash_before": card_hash_before,
        "card_hash_after": _sha256_file(cards_path) if did_update_cards and cards_path.exists() else card_hash_before,
    }
    _append_log(entry)
    return entry


def revert_last(*, card_id: str | None = None, who: str = "admin") -> dict:
    if not APPLIED_LOG.exists():
        return {"ok": False, "error": "log empty"}
    log = json.loads(APPLIED_LOG.read_text(encoding="utf-8"))
    target = None
    for entry in reversed(log):
        if entry.get("action") != "approve":
            continue
        if card_id and entry.get("card_id") != card_id:
            continue
        if entry.get("reverted"):
            continue
        target = entry
        break
    if not target:
        return {"ok": False, "error": "no approve entry"}

    cid = target["card_id"]
    domain = _domain_for_card(cid)
    cards_path = _cards_file(domain)
    # snapshot 복구
    tag = f"{cid}_v{target.get('version')}"
    snap = cards_path.with_name(f"{cards_path.stem}.__lw_{tag}__{cards_path.suffix}")
    restored_hash = None
    if snap.exists() and target.get("updated_current_cards"):
        shutil.copy2(snap, cards_path)
        restored_hash = _sha256_file(cards_path)
        if target.get("card_hash_before") and restored_hash != target["card_hash_before"]:
            return {
                "ok": False,
                "error": "hash_mismatch",
                "expected": target["card_hash_before"],
                "got": restored_hash,
            }

    # 버전 파일에서 해당 버전 제거 + 이전 effective_to 복구
    data = load_card_versions(cid)
    if data:
        vers = [v for v in (data.get("versions") or []) if int(v.get("version") or -1) != int(target.get("version") or -2)]
        # 마지막 열린 버전 effective_to 비우기
        if vers:
            vers = sorted(vers, key=lambda v: int(v.get("version") or 0))
            vers[-1]["effective_to"] = None
        data["versions"] = vers
        save_card_versions(data)

    target["reverted"] = True
    target["reverted_at"] = datetime.now().isoformat(timespec="seconds")
    target["reverted_by"] = who
    # rewrite log
    for i, e in enumerate(log):
        if e is target or (e.get("when") == target.get("when") and e.get("card_id") == cid and e.get("version") == target.get("version")):
            log[i] = target
            break
    APPLIED_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_log({"action": "revert", "who": who, "when": datetime.now().isoformat(timespec="seconds"), "target": target})
    return {
        "ok": True,
        "card_id": cid,
        "restored_hash": restored_hash,
        "matches_before": restored_hash == target.get("card_hash_before") if restored_hash else None,
        "versions_remaining": len((load_card_versions(cid) or {}).get("versions") or []),
    }


def activate_scheduled(*, today: str | None = None) -> list[dict]:
    """시행일이 된 예약 버전을 현행 카드에 반영."""
    today = today or date.today().isoformat()
    done = []
    if not CRITERIA_VERSIONS.exists():
        return done
    for path in CRITERIA_VERSIONS.glob("*.yaml"):
        data = load_yaml(path) or {}
        card_id = data.get("card_id") or path.stem
        for ver in data.get("versions") or []:
            if ver.get("status") == "예약" and (ver.get("effective_from") or "") <= today:
                # 가짜 proposal로 승인 흐름 재사용하지 않고 직접 갱신
                domain = _domain_for_card(card_id)
                cards_path = _cards_file(domain)
                if cards_path.exists():
                    _backup_file(cards_path, tag=f"{card_id}_sched_v{ver.get('version')}")
                    rows = load_yaml(cards_path) or []
                    proposed = ver.get("card") or {}
                    new_rows = []
                    for row in rows:
                        if isinstance(row, dict) and row.get("id") == card_id:
                            updated = dict(row)
                            updated.update(proposed)
                            new_rows.append(updated)
                        else:
                            new_rows.append(row)
                    if yaml is not None:
                        cards_path.write_text(
                            yaml.safe_dump(new_rows, allow_unicode=True, sort_keys=False),
                            encoding="utf-8",
                        )
                ver["status"] = "현행"
                done.append({"card_id": card_id, "version": ver.get("version")})
        dump_yaml(data, path)
    return done


def quick_regression(
    card_ids: list[str],
    *,
    before_cards: dict[str, dict] | None = None,
    after_cards: dict[str, dict] | None = None,
    max_n: int = 200,
    seed: int = 42,
    use_llm: bool = False,
) -> dict:
    """dev 조각 중 영향 카드가 고르는 것만 최대 200개. test 금지.
    use_llm=False면 카드 선택·키워드 통계만(빠른 점검 스모크).
    """
    import random

    from rag.criteria import select_cards
    from rag.paths import GOLD, SPLIT_FILE

    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    split = json.loads(SPLIT_FILE.read_text(encoding="utf-8")) if SPLIT_FILE.exists() else {}
    dev_ids = set(split.get("dev") or split.get("dev_ids") or [])
    # 도메인별 계약 조각 로드(텍스트만, 정답 문장 프롬프트 금지 — 여기선 선택 통계만)
    clauses = []
    for domain, conf in GOLD.items():
        path = conf.get("contract")
        if not path or not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rid = row.get("id") or row.get("doc_id") or row.get("계약서ID")
            if dev_ids and rid not in dev_ids:
                # 일부 데이터셋은 clause id
                cid = row.get("clause_id") or row.get("조항ID")
                if cid not in dev_ids and rid not in dev_ids:
                    continue
            text = row.get("text") or row.get("조항") or row.get("내용") or ""
            if not text:
                continue
            clauses.append({"id": rid or cid, "domain": domain, "text": text})

    rng = random.Random(seed)
    picked = []
    for row in clauses:
        cards = select_cards(row["text"], limit=2, domain=row["domain"])
        ids = {c.get("id") for c in cards}
        if ids & set(card_ids):
            picked.append(row)
    rng.shuffle(picked)
    picked = picked[:max_n]

    result = {
        "day": day,
        "seed": seed,
        "card_ids": card_ids,
        "n_candidates": len(picked),
        "use_llm": use_llm,
        "note": "LLM 재판정은 use_llm=True일 때만. 기본은 선택 통계.",
        "warning": False,
    }
    out_md = LAWWATCH_OUT / f"{day}_regression.md"
    lines = [
        f"# 빠른 점검 {day}",
        "",
        f"- 대상 카드: {', '.join(card_ids)}",
        f"- 선택 조각: {len(picked)} (max {max_n}, seed {seed})",
        f"- LLM: {use_llm}",
        "",
    ]
    if use_llm and picked:
        lines.append("LLM 재판정은 시연/승인 경로에서 별도 실행. 여기 스모크는 생략 가능.")
    else:
        lines.append("적용 전/후 경고 포착 비교는 카드 내용 해시로만 표시.")
        for cid in card_ids:
            b = json.dumps((before_cards or {}).get(cid) or {}, ensure_ascii=False, sort_keys=True)
            a = json.dumps((after_cards or {}).get(cid) or {}, ensure_ascii=False, sort_keys=True)
            lines.append(f"- `{cid}` before_sha={_sha256_text(b)[:12]} after_sha={_sha256_text(a)[:12]} changed={b != a}")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    result["path"] = str(out_md)
    (LAWWATCH_OUT / f"{day}_regression.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
