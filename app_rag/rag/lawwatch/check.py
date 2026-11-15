# -*- coding: utf-8 -*-
"""법령 변경 감지. API 실패 시 오프라인 모드."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.lawwatch.parse import _ymd, basic_meta, load_mst
from rag.lawwatch.paths import LAWWATCH_OUT, LAW_API_CURRENT, LAW_VERSIONS, TARGET_LAWS_FILE
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


def fetch_admrul_search(name: str, oc: str) -> dict:
    """행정규칙(고시 등) 검색. target=admrul."""
    qs = urllib.parse.urlencode(
        {"OC": oc, "target": "admrul", "type": "JSON", "query": name, "display": "20", "search": "1"}
    )
    return _http_json(f"{SEARCH}?{qs}")


def fetch_law_body_mst(mst: str, oc: str) -> dict:
    qs = urllib.parse.urlencode({"OC": oc, "target": "law", "type": "JSON", "MST": mst})
    return _http_json(f"{SERVICE}?{qs}")


def normalize_announce_no(value: Any) -> str:
    """공포번호·발령번호를 숫자만 남긴 문자열로 정규화.

    law.go.kr 검색 JSON이 검색어 강조용으로
    {'content': ['3','593'], 'strong': {'content': '1'}} 형태를 주면
    잘못 파싱하면 593만 남는다. content[0]+strong+content[1:] → 31593.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return re.sub(r"\D", "", str(int(value)))
    if isinstance(value, dict):
        content = value.get("content")
        strong = value.get("strong")
        strong_txt = ""
        if isinstance(strong, dict):
            strong_txt = str(strong.get("content") or "")
        elif strong is not None:
            strong_txt = str(strong)
        if isinstance(content, list) and content:
            if strong_txt and len(content) >= 1:
                # ['3','593'] + strong '1' → 3 + 1 + 593
                joined = str(content[0]) + strong_txt + "".join(str(x) for x in content[1:])
            else:
                joined = "".join(str(x) for x in content) + strong_txt
            digits = re.sub(r"\D", "", joined)
            if digits:
                return digits
        # fallback: 모든 숫자 조각을 등장 순으로 이어 붙임(짧은 조각 우선 매칭 방지)
        flat = json.dumps(value, ensure_ascii=False)
        # strong content first insertion already handled; last resort concatenate all digit runs
        runs = re.findall(r"\d+", flat)
        return "".join(runs) if runs else ""
    return re.sub(r"\D", "", str(value))


def _pick_search_row(payload: dict, law_name: str) -> dict | None:
    root = payload.get("LawSearch") or payload
    rows = root.get("law") or []
    if isinstance(rows, dict):
        rows = [rows]
    exact = [r for r in rows if (r.get("법령명한글") or r.get("법령명") or "") == law_name]
    pool = exact or list(rows)
    if not pool:
        return None
    for r in pool:
        if (r.get("현행연혁구분") or r.get("현행연혁코드") or "") == "현행":
            return r
    return pool[0]


def _pick_admrul_row(payload: dict, law_name: str) -> dict | None:
    root = payload.get("AdmRulSearch") or payload
    rows = root.get("admrul") or root.get("행정규칙") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return None
    # 이름 매칭: 정확 → 포함. 선원고시 등 제외 우선
    def score(r: dict) -> tuple:
        name = r.get("행정규칙명") or ""
        cur = 1 if (r.get("현행연혁구분") or "") == "현행" else 0
        labor = 1 if (r.get("소관부처명") or "") == "고용노동부" else 0
        exact = 1 if name == law_name else 0
        has = 1 if law_name.replace(" ", "") in name.replace(" ", "") or "최저임금" in name else 0
        sailor = 0 if "선원" in name else 1
        return (exact, cur, labor, sailor, has)

    ranked = sorted(rows, key=score, reverse=True)
    best = ranked[0]
    # 너무 엉뚱한 결과면 거부
    name = best.get("행정규칙명") or ""
    if law_name == "최저임금고시":
        if "최저임금" not in name or "선원" in name:
            # 고용노동부·최저임금·현행만
            for r in ranked:
                n = r.get("행정규칙명") or ""
                if "최저임금" in n and "선원" not in n and (r.get("소관부처명") or "") == "고용노동부":
                    if (r.get("현행연혁구분") or "") == "현행":
                        return r
            for r in ranked:
                n = r.get("행정규칙명") or ""
                if "최저임금" in n and "선원" not in n:
                    return r
            return None
    return best


def _remote_from_law_row(row: dict, law_name: str) -> dict:
    return {
        "mst": str(row.get("법령일련번호") or row.get("MST") or ""),
        "announce_no": normalize_announce_no(row.get("공포번호")),
        "announce_no_raw": row.get("공포번호"),
        "effective": _ymd(row.get("시행일자")),
        "announced": _ymd(row.get("공포일자")),
        "name": row.get("법령명한글") or law_name,
        "source": "law",
    }


def _remote_from_admrul_row(row: dict, law_name: str) -> dict:
    return {
        "mst": str(row.get("행정규칙일련번호") or ""),
        "announce_no": normalize_announce_no(row.get("발령번호")),
        "announce_no_raw": row.get("발령번호"),
        "effective": _ymd(row.get("시행일자")),
        "announced": _ymd(row.get("발령일자")),
        "name": row.get("행정규칙명") or law_name,
        "source": "admrul",
    }


def _mst_from_baseline(law_name: str, local: dict) -> str:
    """기준선(현행 MST 파일·source_path)에서 법령일련번호 보충."""
    paths: list[Path] = []
    sp = (local.get("source_path") or "").strip()
    if sp:
        paths.append(Path(sp))
    # index 현행 source_path
    entry = current_version_entry(law_name) or {}
    if entry.get("source_path"):
        paths.append(Path(entry["source_path"]))
    cand = LAW_API_CURRENT / f"{law_name}_body_MST.json"
    paths.append(cand)
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        try:
            law = load_mst(path)
            meta = basic_meta(law)
            mst = str(meta.get("mst") or "").strip()
            if mst:
                return mst
        except Exception:
            continue
    return ""


def fill_local_mst(law_name: str, local: dict, remote: dict | None) -> tuple[dict, str]:
    """저장본 MST가 없으면 기준선 → API 순으로 채움. 개정으로 보지 않음."""
    out = dict(local)
    if str(out.get("mst") or "").strip():
        return out, ""
    baseline = _mst_from_baseline(law_name, out)
    if baseline:
        out["mst"] = baseline
        return out, "MST 보충(기준선)"
    rem = (remote or {}).get("mst") or ""
    if rem:
        out["mst"] = str(rem)
        return out, "MST 보충"
    return out, ""


def compare_meta(local: dict, remote: dict) -> tuple[str, str]:
    """변경 없음 / 개정됨(시행 중) / 개정 예정(시행일이 미래).

    개정 판단:
      ① MST가 둘 다 있고 다름, 또는
      ② 시행일·공포일(발령일)이 둘 다 있고 다름.
    공포번호는 숫자 정규화 후 참고만 — 형식만 다르면 개정 아님.
    """
    loc_mst = str(local.get("mst") or "").strip()
    rem_mst = str(remote.get("mst") or "").strip()
    loc_ef = local.get("effective") or None
    rem_ef = remote.get("effective") or None
    loc_anc = local.get("announced") or None
    rem_anc = remote.get("announced") or None
    loc_no = normalize_announce_no(local.get("announce_no"))
    rem_no = normalize_announce_no(remote.get("announce_no"))

    notes: list[str] = []
    mst_changed = bool(loc_mst and rem_mst and loc_mst != rem_mst)
    date_changed = bool(
        (loc_ef and rem_ef and loc_ef != rem_ef)
        or (loc_anc and rem_anc and loc_anc != rem_anc)
    )

    if mst_changed or date_changed:
        today = datetime.now().date().isoformat()
        if rem_ef and rem_ef > today:
            return "개정 예정(시행일이 미래)", ""
        return "개정됨(시행 중)", ""

    if loc_no and rem_no and loc_no != rem_no:
        notes.append(f"공포번호 참고만 불일치({loc_no}≠{rem_no}) — 개정 아님")
    return "변경 없음", "; ".join(notes)


def _is_admrul_target(law_name: str) -> bool:
    return "고시" in (law_name or "")


def check_one(law_name: str, *, offline: bool = False) -> dict:
    entry = current_version_entry(law_name)
    local = {
        "mst": (entry or {}).get("mst") or "",
        "announce_no": (entry or {}).get("announce_no") or "",
        "announced": (entry or {}).get("announced"),
        "effective": (entry or {}).get("effective"),
        "id": (entry or {}).get("id"),
        "source_path": (entry or {}).get("source_path") or "",
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
            result["status"] = "변경 없음"
            result["note"] += " | 저장소에 현행·과거 버전 있음(이미 등록된 차이)"
            result["remote"] = cur[-1]
            result["offline_pair"] = {"current": cur[-1].get("id"), "past": past[-1].get("id")}
        else:
            result["status"] = "변경 없음"
            result["note"] += " | 비교할 다른 버전 없음"
        return result

    try:
        remote = None
        if _is_admrul_target(law_name):
            search = fetch_admrul_search(law_name, oc)
            row = _pick_admrul_row(search, law_name)
            if not row:
                offline_res = check_one(law_name, offline=True)
                offline_res["note"] = "행정규칙(admrul) 검색 결과 없음 → 오프라인 폴백"
                return offline_res
            remote = _remote_from_admrul_row(row, law_name)
        else:
            search = fetch_law_search(law_name, oc)
            row = _pick_search_row(search, law_name)
            if not row:
                offline_res = check_one(law_name, offline=True)
                offline_res["note"] = "API 검색 결과 없음(법령명 미매칭) → 오프라인 폴백"
                return offline_res
            remote = _remote_from_law_row(row, law_name)

        local_filled, mst_note = fill_local_mst(law_name, local, remote)
        # 저장본이 아예 없으면 개정으로 단정하지 않음
        if not (local_filled.get("effective") or local_filled.get("announce_no") or (entry and entry.get("id"))):
            result["local"] = local_filled
            result["remote"] = remote
            result["status"] = "변경 없음"
            notes = [mst_note] if mst_note else []
            notes.append("저장본 없음 · API 현행만 확인")
            result["note"] = " · ".join(n for n in notes if n)
            return result

        status, cmp_note = compare_meta(local_filled, remote)
        result["local"] = local_filled
        result["remote"] = {
            k: v for k, v in remote.items() if k != "announce_no_raw"
        }
        result["status"] = status
        notes = [n for n in (mst_note, cmp_note) if n]
        result["note"] = " · ".join(notes)
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
    (LAWWATCH_OUT / "latest_check.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="법령 변경 감지")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    payload = check_all(offline=args.offline)
    print(
        json.dumps(
            {"n": payload["n"], "summary": payload["summary"], "out": str(LAWWATCH_OUT / "latest_check.json")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
