# -*- coding: utf-8 -*-
"""법령 변경 감지. API 실패 시 오프라인 모드."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rag.lawwatch.parse import _ymd, basic_meta, load_mst
from rag.lawwatch.paths import LAWWATCH_OUT, LAW_VERSIONS, TARGET_LAWS_FILE
from rag.lawwatch.store import current_version_entry, list_laws, load_index, load_version, register_body

SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _oc() -> str | None:
    return os.environ.get("LAW_OC") or None


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ContractedYouth-LawWatch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def fetch_law_search(law_name: str, oc: str) -> dict:
    qs = urllib.parse.urlencode(
        {"OC": oc, "target": "law", "type": "JSON", "query": law_name, "display": "20", "search": "1"}
    )
    return _http_json(f"{SEARCH}?{qs}")


def fetch_law_body_mst(mst: str, oc: str) -> dict:
    qs = urllib.parse.urlencode({"OC": oc, "target": "law", "type": "JSON", "MST": mst})
    return _http_json(f"{SERVICE}?{qs}")


def _pick_search_row(payload: dict, law_name: str) -> dict | None:
    root = payload.get("LawSearch") or payload
    rows = root.get("law") or []
    if isinstance(rows, dict):
        rows = [rows]
    exact = [r for r in rows if (r.get("법령명한글") or r.get("법령명") or "") == law_name]
    pool = exact or list(rows)
    if not pool:
        return None
    # 현행 우선
    for r in pool:
        if (r.get("현행연혁구분") or "") == "현행":
            return r
    return pool[0]


def compare_meta(local: dict, remote: dict) -> str:
    """변경 없음 / 개정됨(시행 중) / 개정 예정(시행일이 미래)."""
    loc_mst = str(local.get("mst") or "")
    rem_mst = str(remote.get("mst") or "")
    loc_no = str(local.get("announce_no") or "")
    rem_no = str(remote.get("announce_no") or "")
    loc_ef = local.get("effective")
    rem_ef = remote.get("effective")
    changed = (loc_mst and rem_mst and loc_mst != rem_mst) or (loc_no and rem_no and loc_no != rem_no) or (loc_ef != rem_ef)
    if not changed:
        # mst 비어 있으면 시행일·공포번호만
        if loc_ef == rem_ef and loc_no == rem_no:
            return "변경 없음"
        if loc_ef != rem_ef or loc_no != rem_no:
            changed = True
        else:
            return "변경 없음"
    today = datetime.now().date().isoformat()
    if rem_ef and rem_ef > today:
        return "개정 예정(시행일이 미래)"
    return "개정됨(시행 중)"


def check_one(law_name: str, *, offline: bool = False) -> dict:
    entry = current_version_entry(law_name)
    local = {
        "mst": (entry or {}).get("mst") or "",
        "announce_no": (entry or {}).get("announce_no") or "",
        "effective": (entry or {}).get("effective"),
        "id": (entry or {}).get("id"),
    }
    result = {
        "law": law_name,
        "local": local,
        "remote": None,
        "status": "변경 없음",
        "mode": "online",
        "checked_at": _now_iso(),
        "note": "",
    }
    oc = _oc()
    if offline or not oc:
        result["mode"] = "offline"
        result["note"] = "API 키 없음 또는 오프라인 모드 — 저장소 버전끼리 비교"
        index = load_index(law_name)
        vers = index.get("versions") or []
        cur = [v for v in vers if v.get("status") == "현행"]
        past = [v for v in vers if v.get("status") == "과거"]
        scheduled = [v for v in vers if v.get("status") == "예정"]
        if scheduled:
            result["status"] = "개정 예정(시행일이 미래)"
            result["remote"] = scheduled[-1]
        elif past and cur:
            # 현행 vs 최신 과거: 시행일 다르면 개정됨으로 표시(이미 반영된 상태)
            result["status"] = "변경 없음"
            result["note"] += " | 저장소에 현행·과거 버전 있음(이미 등록된 차이)"
            result["remote"] = cur[-1]
            result["offline_pair"] = {"current": cur[-1].get("id"), "past": past[-1].get("id")}
        else:
            result["status"] = "변경 없음"
            result["note"] += " | 비교할 다른 버전 없음"
        return result

    try:
        search = fetch_law_search(law_name, oc)
        row = _pick_search_row(search, law_name)
        if not row:
            offline_res = check_one(law_name, offline=True)
            offline_res["note"] = "API 검색 결과 없음(법령명 미매칭·고시 등) → 오프라인 폴백"
            return offline_res
        ann_no = row.get("공포번호") or ""
        # API가 HTML 조각(dict)을 주는 경우가 있어 숫자만 추출
        if isinstance(ann_no, dict):
            flat = json.dumps(ann_no, ensure_ascii=False)
            import re as _re

            m = _re.search(r"\d{3,}", flat)
            ann_no = m.group(0) if m else ""
        remote = {
            "mst": str(row.get("법령일련번호") or row.get("MST") or ""),
            "announce_no": str(ann_no or ""),
            "effective": _ymd(row.get("시행일자")),
            "announced": _ymd(row.get("공포일자")),
            "name": row.get("법령명한글") or law_name,
        }
        result["remote"] = remote
        result["status"] = compare_meta(local, remote)
        return result
    except Exception as exc:
        result["mode"] = "offline"
        result["note"] = f"API 실패 → 오프라인: {type(exc).__name__}"
        offline_res = check_one(law_name, offline=True)
        offline_res["note"] = result["note"] + " | " + (offline_res.get("note") or "")
        return offline_res


def check_all(*, offline: bool = False, laws: list[str] | None = None) -> dict:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    if laws is None:
        if TARGET_LAWS_FILE.exists():
            laws = json.loads(TARGET_LAWS_FILE.read_text(encoding="utf-8")).get("laws") or list_laws()
        else:
            laws = list_laws()
    rows = [check_one(name, offline=offline) for name in laws]
    day = datetime.now().strftime("%Y%m%d")
    payload = {
        "checked_at": _now_iso(),
        "offline_forced": offline,
        "n": len(rows),
        "results": rows,
        "summary": {
            "변경 없음": sum(1 for r in rows if r["status"] == "변경 없음"),
            "개정됨(시행 중)": sum(1 for r in rows if r["status"] == "개정됨(시행 중)"),
            "개정 예정(시행일이 미래)": sum(1 for r in rows if r["status"] == "개정 예정(시행일이 미래)"),
            "offline": sum(1 for r in rows if r.get("mode") == "offline"),
        },
    }
    out_json = LAWWATCH_OUT / f"{day}_check.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # latest pointer
    (LAWWATCH_OUT / "latest_check.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="법령 변경 감지")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    payload = check_all(offline=args.offline)
    print(json.dumps({"n": payload["n"], "summary": payload["summary"], "out": str(LAWWATCH_OUT / "latest_check.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
