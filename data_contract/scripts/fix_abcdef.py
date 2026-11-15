# -*- coding: utf-8 -*-
"""DATA_READY 수정 A~F. 성공=기대 JSON 구조. OC 미출력/저장시 REDACT."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import winreg
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
LAW = DC / "law_api"
OUT = DC / "fix_abcdef_results.json"
SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"

LAWS = [
    "근로기준법",
    "근로기준법 시행령",
    "최저임금법",
    "최저임금법 시행령",
    "주택임대차보호법",
    "주택임대차보호법 시행령",
    "민법",
    "이자제한법",
    "이자제한법 제2조제1항의 최고이자율에 관한 규정",
    "보증인 보호를 위한 특별법",
]

EXPC_KW = ["근로계약", "최저임금", "주휴", "수습", "임대차", "보증금", "이자"]
# guide: 중앙부처 1차 해석 targets
MINISTRY = {
    "고용노동부": "moelCgmExpc",
    "국토교통부": "molitCgmExpc",
    "법제처": "molegCgmExpc",
    # mojCgmExpc: 실측 미승인(HTML) — 아래 probe에서 기록
}
MINISTRY_UNAUTHORIZED = {"법무부": "mojCgmExpc"}
FTC_KW = ["임대차 약관", "임대차계약서"]
PREC_KW = [
    "임대차 특약 무효", "원상복구 특약", "임대차 위약금", "보증금 반환 특약", "계약갱신요구권 포기",
    "근로계약 위약금", "위약예정", "임금 공제", "수습기간 임금", "주휴수당", "휴게시간",
    "이자제한법 초과", "보증 서면", "차용증",
]

HTML_UNAUTH_MSG = (
    "국가법령정보 공동활용 미신청한 서비스/권한이 없는 서비스입니다. "
    "OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 서비스 중 이용범위를 체크해 주세요."
)


def oc() -> str:
    v = os.environ.get("LAW_OC", "").strip()
    if v:
        return v
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
        v, _ = winreg.QueryValueEx(k, "LAW_OC")
        return str(v).strip()


def redact(t: str) -> str:
    t = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", t or "")
    t = re.sub(r'("OC"\s*:\s*")[^"]+(")', r"\1REDACTED\2", t)
    return t


def save(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def http_get(params: dict, base: str = SEARCH) -> str:
    q = urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    t = raw.decode(enc)
                    break
                except Exception:
                    t = raw.decode("utf-8", "replace")
            time.sleep(0.65)
            return t
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"http_get failed after retries: {last_err}")


def is_html(t: str) -> bool:
    h = t.lstrip()[:80].lower()
    return h.startswith("<!doctype") or h.startswith("<html") or "<html" in t[:300].lower()


def html_message(t: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", t, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]


def parse_json(t: str):
    try:
        return json.loads(t)
    except Exception:
        return None


def json_ok_lawsearch(t: str) -> bool:
    j = parse_json(t)
    return isinstance(j, dict) and ("LawSearch" in j or "AdmRulSearch" in j or "PrecSearch" in j or "Ftc" in j or any(
        k.endswith("Search") or k.endswith("Service") for k in j
    ))


def extract_list_items(j, *container_keys):
    if not isinstance(j, dict):
        return []
    for ck in container_keys:
        if ck in j and isinstance(j[ck], dict):
            j = j[ck]
            break
    items = []
    for v in j.values() if isinstance(j, dict) else []:
        if isinstance(v, list):
            items.extend([x for x in v if isinstance(x, dict)])
        elif isinstance(v, dict) and any(k in v for k in ("법령명한글", "안건명", "사건명", "행정규칙명", "판례일련번호", "법령해석일련번호")):
            items.append(v)
    return items


def get_id(item: dict, keys=None):
    keys = keys or (
        "법령일련번호", "판례정보일련번호", "판례일련번호", "행정규칙일련번호", "행정규칙 일련번호",
        "법령해석일련번호", "법령해석례일련번호", "결정문일련번호", "결정문 일련번호", "ID", "id",
    )
    for k in keys:
        if item.get(k) not in (None, ""):
            return item.get(k)
    for link_key in ("법령해석상세링크", "판례상세링크", "행정규칙상세링크", "법령상세링크"):
        link = item.get(link_key) or ""
        m = re.search(r"[?&]ID=(\d+)", link) or re.search(r"[?&]MST=(\d+)", link)
        if m:
            return m.group(1)
    return None


def extract_cgm_items(j):
    if not isinstance(j, dict):
        return []
    node = j.get("CgmExpc") or {}
    items = node.get("cgmExpc") or node.get("expc") or []
    if isinstance(items, dict):
        items = [items]
    return [x for x in items if isinstance(x, dict)]


# ---------- A: inspect old + refetch ----------
def fix_A(key: str) -> dict:
    sec = {
        "old_html_errors": {},
        "guide_fix": {},
        "expc_unauthorized": None,
        "ministry": {},
        "ftc": {},
        "lstrm": {},
        "lstrmRlt": {},
    }
    # old HTML messages
    for sub, label in [("법령해석례", "3-5"), ("공정위", "3-6"), ("법령용어", "3-7")]:
        msgs = []
        d = LAW / sub
        if d.exists():
            for p in d.rglob("*"):
                if not p.is_file() or p.suffix.lower() in {".txt"}:
                    continue
                t = p.read_text(encoding="utf-8", errors="replace")
                if is_html(t):
                    msgs.append({"file": str(p.relative_to(LAW)), "error_text": html_message(t)})
                    if len(msgs) >= 3:
                        break
        sec["old_html_errors"][label] = msgs

    # expc still unauthorized?
    t = http_get({"OC": key, "target": "expc", "type": "JSON", "query": "근로계약", "display": 5})
    if is_html(t):
        sec["expc_unauthorized"] = {
            "target": "expc",
            "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide",
            "error_text": html_message(t),
            "conclusion": "target=expc 미승인. 중앙부처 1차 해석(moelCgmExpc 등)으로 대체 시도.",
        }
        save(LAW / "법령해석례" / "_error_expc_unauthorized.html.txt", html_message(t))
    else:
        sec["expc_unauthorized"] = {"unexpected_ok": True, "head": t[:200]}

    # ministry APIs (중앙부처 1차 해석 — expc 대체)
    mdir = LAW / "법령해석례" / "ministry_v2"
    mdir.mkdir(parents=True, exist_ok=True)
    for org, tgt in MINISTRY_UNAUTHORIZED.items():
        t0 = http_get({"OC": key, "target": tgt, "type": "JSON", "query": "근로", "display": 3, "search": 2})
        sec["ministry"][org] = {
            "target": tgt,
            "ok": False,
            "error_text": html_message(t0) if is_html(t0) else t0[:300],
            "guide": "https://open.law.go.kr/LSO/openApi/guideList.do (cgmExpc*ListGuide)",
            "conclusion": "미승인 target — 신청 필요",
        }
    for org, tgt in MINISTRY.items():
        t0 = http_get({"OC": key, "target": tgt, "type": "JSON", "query": "근로", "display": 3, "search": 2})
        if is_html(t0) or not parse_json(t0) or "CgmExpc" not in (parse_json(t0) or {}):
            sec["ministry"][org] = {
                "target_tried": tgt,
                "ok": False,
                "error_text": html_message(t0) if is_html(t0) else t0[:300],
                "guide_hint": f"cgmExpc*ListGuide / target={tgt}",
            }
            continue
        ids = {}
        n_list = 0
        n_body = 0
        sample = None
        for kw in EXPC_KW:
            page = 1
            while page <= 3:
                t = http_get({
                    "OC": key, "target": tgt, "type": "JSON", "query": kw,
                    "search": 2, "display": 100, "page": page,
                })
                j = parse_json(t)
                if is_html(t) or not j or "CgmExpc" not in j:
                    break
                save(mdir / f"{org}_{kw}_p{page}.json", t)
                n_list += 1
                items = extract_cgm_items(j)
                for it in items:
                    eid = it.get("법령해석일련번호") or it.get("법령해석례일련번호")
                    if not eid:
                        link = it.get("법령해석상세링크") or ""
                        m = re.search(r"[?&]ID=(\d+)", link)
                        eid = m.group(1) if m else None
                    if eid:
                        ids[str(eid)] = it
                total = j["CgmExpc"].get("totalCnt")
                if not items or (total and page * 100 >= int(total)) or len(items) < 100:
                    break
                page += 1
        for eid in list(ids.keys())[:100]:
            tb = http_get({"OC": key, "target": tgt, "type": "JSON", "ID": eid}, SERVICE)
            jb = parse_json(tb)
            if is_html(tb) or not jb or "CgmExpcService" not in jb:
                continue
            save(mdir / "bodies" / f"{org}_{eid}.json", tb)
            n_body += 1
            if sample is None:
                sample = redact(tb)[:300]
        sec["ministry"][org] = {
            "target": tgt,
            "ok": True,
            "guide": "https://open.law.go.kr/LSO/openApi/guideList.do → cgmExpc*ListGuide/InfoGuide",
            "list_responses_ok": n_list,
            "unique_ids": len(ids),
            "bodies_ok": n_body,
            "sample_head_300": sample,
            "success_criterion": "목록: JSON CgmExpc; 본문: JSON CgmExpcService",
        }

    # FTC JSON
    fdir = LAW / "공정위" / "v2"
    fdir.mkdir(parents=True, exist_ok=True)
    ftc_ids = {}
    n_list = n_body = 0
    sample = None
    ftc_err = None
    for kw in FTC_KW:
        t = http_get({"OC": key, "target": "ftc", "type": "JSON", "query": kw, "search": 2, "display": 50})
        if is_html(t):
            ftc_err = html_message(t)
            continue
        j = parse_json(t)
        if not j or "Ftc" not in j:
            ftc_err = t[:300]
            continue
        save(fdir / f"list_{kw.replace(' ', '_')}.json", t)
        n_list += 1
        raw = j["Ftc"].get("ftc") or []
        items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
        for it in items:
            fid = it.get("결정문일련번호")
            if fid:
                ftc_ids[str(fid)] = it
        if sample is None:
            sample = redact(t)[:300]
    for fid in list(ftc_ids.keys())[:80]:
        tb = http_get({"OC": key, "target": "ftc", "type": "JSON", "ID": fid}, SERVICE)
        jb = parse_json(tb)
        if is_html(tb) or not jb or "FtcService" not in jb:
            continue
        save(fdir / "bodies" / f"{fid}.json", tb)
        n_body += 1
        if sample is None or "FtcService" not in (sample or ""):
            sample = redact(tb)[:300]
    sec["ftc"] = {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cmtListGuide / cmtInfoGuide",
        "fix": "목록·본문 type=JSON 실측 성공 (Ftc / FtcService).",
        "list_responses_ok": n_list,
        "unique_ids": len(ftc_ids),
        "bodies_ok": n_body,
        "sample_head_300": sample,
        "error_if_any": ftc_err,
        "success_criterion": "목록 JSON Ftc; 본문 JSON FtcService",
    }

    # lstrm unauthorized; lstrmRlt ok
    t = http_get({"OC": key, "target": "lstrm", "type": "JSON", "query": "근로", "display": 5})
    sec["lstrm"] = {
        "target": "lstrm",
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsTrmListGuide",
        "ok": bool(parse_json(t)) and not is_html(t),
        "error_text": html_message(t) if is_html(t) else None,
        "conclusion": "미승인이면 lstrmRlt(법령용어-일상용어 연계)로 범위 내 수집",
    }
    rdir = LAW / "법령용어" / "lstrmRlt_v2"
    rdir.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    sample = None
    terms = ["근로계약", "임대차", "보증금", "위약금", "최저임금", "차용", "이자", "수습", "주휴", "약관", "특약", "원상복구"]
    for q in terms:
        # guide: lawService.do target=lstrmRlt (lawSearch 빈응답)
        t = http_get({"OC": key, "target": "lstrmRlt", "type": "JSON", "query": q}, SERVICE)
        j = parse_json(t)
        if is_html(t) or not j or "lstrmRltService" not in j:
            continue
        save(rdir / f"{q}.json", t)
        n_ok += 1
        if sample is None:
            sample = redact(t)[:300]
    sec["lstrmRlt"] = {
        "guide": "http://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide",
        "endpoint": "lawService.do (not lawSearch)",
        "list_or_service_ok": n_ok,
        "bodies_ok": n_ok,
        "sample_head_300": sample,
        "success_criterion": "JSON with lstrmRltService",
    }
    sec["guide_fix"] = {
        "expc": "미승인 → 중앙부처 1차 해석 moelCgmExpc 등",
        "ftc": "JSON 목록 사용",
        "lstrm": "미승인 → lstrmRlt",
    }
    return sec


# ---------- B: history exact name ----------
def fix_B(key: str) -> dict:
    sec = {
        "guide_history_api": {
            "guideList": "https://open.law.go.kr/LSO/openApi/guideList.do",
            "lsHistory_list": {
                "url": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide",
                "target": "lsHistory",
                "type": "HTML only",
                "params": ["query", "efYd", "display", "page", "sort"],
            },
            "lsHistory_body": {
                "url": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide",
                "target": "lsHistory",
                "type": "HTML only",
                "params": ["MST or ID"],
            },
            "also_used": "target=law JSON + efYd + 법령명한글 완전일치 필터 후 MST 본문(JSON) — 구조화 저장용",
        },
        "mismatched_previous_bodies": [],
        "laws": {},
    }
    # mark previous mismatches
    hist = LAW / "연혁"
    if hist.exists():
        for p in hist.glob("*_body_MST_*.json"):
            # filename {law}_body_MST_{id}.json — law may contain spaces
            t = p.read_text(encoding="utf-8", errors="replace")
            j = parse_json(t)
            name_in_file = p.name.split("_body_MST_")[0]
            # find 법령명 in body
            blob = t
            m = re.search(r'"법령명[^"]*"\s*:\s*"([^"]+)"', t)
            actual = m.group(1) if m else None
            if actual and actual.replace(" ", "") != name_in_file.replace(" ", ""):
                sec["mismatched_previous_bodies"].append({
                    "file": str(p.relative_to(LAW)),
                    "expected": name_in_file,
                    "actual_법령명": actual,
                })

    outd = LAW / "연혁_v2_exact"
    outd.mkdir(parents=True, exist_ok=True)
    # also fetch lsHistory HTML list as evidence
    for name in LAWS:
        rows = []
        # JSON path via law + efYd
        page = 1
        while page <= 20:
            t = http_get({
                "OC": key, "target": "law", "type": "JSON", "query": name,
                "efYd": "20220101~20301231", "display": 100, "page": page, "sort": "efasc",
            })
            j = parse_json(t)
            if is_html(t) or not j or "LawSearch" not in j:
                break
            save(outd / f"{name}_law_efYd_p{page}.json", t)
            items = extract_list_items(j, "LawSearch")
            exact = [it for it in items if it.get("법령명한글") == name]
            for it in exact:
                lid = it.get("법령일련번호")
                if not lid:
                    continue
                if any(r["MST"] == str(lid) for r in rows):
                    continue
                # filter 시행일 >= 20220101
                ef = str(it.get("시행일자") or "")
                if ef and ef.isdigit() and int(ef) < 20220101:
                    continue
                rows.append({
                    "법령명한글": it.get("법령명한글"),
                    "시행일": it.get("시행일자"),
                    "공포일": it.get("공포일자"),
                    "공포번호": it.get("공포번호"),
                    "MST": str(lid),
                    "현행연혁코드": it.get("현행연혁코드"),
                    "제개정구분명": it.get("제개정구분명"),
                })
            if not items or len(items) < 100:
                break
            page += 1

        # lsHistory HTML list (guide-official)
        th = http_get({
            "OC": key, "target": "lsHistory", "type": "HTML", "query": name,
            "efYd": "20220101~20301231", "display": 100,
        })
        save(outd / f"{name}_lsHistory.html", th)
        # bodies via MST JSON (structured)
        bodies = 0
        for r in rows:
            tb = http_get({"OC": key, "target": "law", "type": "JSON", "MST": r["MST"]}, SERVICE)
            if is_html(tb) or not parse_json(tb) or "없습니다" in tb[:80]:
                # try lsHistory HTML body
                thb = http_get({"OC": key, "target": "lsHistory", "type": "HTML", "MST": r["MST"]}, SERVICE)
                save(outd / "bodies_html" / f"{name}_{r['MST']}.html", thb)
                # validate name in html
                if name.replace(" ", "") in re.sub(r"\s+", "", thb):
                    bodies += 1
                    r["body_type"] = "lsHistory_HTML"
                continue
            # verify name in JSON
            m = re.search(r'"법령명[^"]*"\s*:\s*"([^"]+)"', tb)
            actual = m.group(1) if m else ""
            if actual == name:
                save(outd / "bodies" / f"{name}_{r['MST']}.json", tb)
                bodies += 1
                r["body_type"] = "law_JSON_MST"
            else:
                r["body_skipped_name"] = actual
        sec["laws"][name] = {
            "n_versions": len(rows),
            "bodies_ok": bodies,
            "table": rows,
            "sample_head_300": None,
        }
        if rows:
            bp = outd / "bodies" / f"{name}_{rows[0]['MST']}.json"
            if bp.exists():
                sec["laws"][name]["sample_head_300"] = bp.read_text(encoding="utf-8", errors="replace")[:300]
    return sec


# ---------- C: min wage ----------
def fix_C(key: str) -> dict:
    sec = {"query": "적용 최저임금 고시", "nw": [1, 2], "years": {}, "excluded_선원": []}
    adir = LAW / "행정규칙" / "최저임금_v2"
    adir.mkdir(parents=True, exist_ok=True)
    collected = []
    for nw in (1, 2):
        for page in range(1, 6):
            t = http_get({
                "OC": key, "target": "admrul", "type": "JSON",
                "query": "적용 최저임금 고시", "search": 1, "display": 100, "page": page, "nw": nw,
            })
            j = parse_json(t)
            if is_html(t) or not j:
                break
            save(adir / f"search_nw{nw}_p{page}.json", t)
            items = extract_list_items(j, "AdmRulSearch", "LawSearch")
            for it in items:
                nm = str(it.get("행정규칙명", ""))
                if "선원" in nm:
                    sec["excluded_선원"].append(nm)
                    continue
                if "최저임금" not in nm:
                    continue
                collected.append(it)
            if not items or len(items) < 100:
                break
    # dedupe by ID
    by_id = {}
    for it in collected:
        aid = get_id(it) or it.get("행정규칙ID")
        if aid:
            by_id[str(aid)] = it

    for year in range(2022, 2027):
        chosen = None
        for aid, it in by_id.items():
            nm = str(it.get("행정규칙명", ""))
            if str(year) in nm and "적용" in nm and "최저임금" in nm and "선원" not in nm:
                # prefer 고시
                if "고시" in nm:
                    chosen = (aid, it)
                    break
                if chosen is None:
                    chosen = (aid, it)
        if not chosen:
            sec["years"][str(year)] = {"ok": False, "note": "목록에서 연도 매칭 실패"}
            continue
        aid, it = chosen
        tb = http_get({"OC": key, "target": "admrul", "type": "JSON", "ID": aid}, SERVICE)
        if is_html(tb) or not parse_json(tb):
            sec["years"][str(year)] = {"ok": False, "error": tb[:200]}
            continue
        save(adir / f"body_{year}_{aid}.json", tb)
        # extract hourly
        patterns = [
            rf"{year}[^\n]{{0,40}}시간급[^\d]{{0,15}}([\d,]+)\s*원",
            r"시간급\s*(?:최저임금)?\s*[:：]?\s*([\d,]+)\s*원",
            r"시간급[^\d]{0,20}([\d,]+)\s*원",
        ]
        hourly = None
        evidence = None
        for pat in patterns:
            m = re.search(pat, tb)
            if m:
                hourly = m.group(1)
                evidence = m.group(0)
                break
        sec["years"][str(year)] = {
            "ok": True,
            "name": it.get("행정규칙명"),
            "ID": aid,
            "hourly": hourly,
            "evidence": evidence,
            "sample_head_300": redact(tb)[:300],
        }
    return sec


# ---------- D: precedents filter ----------
FILTER_CODE = '''
def passes_special_agreement_filter(판시사항: str, 판결요지: str) -> bool:
    blob = (판시사항 or "") + (판결요지 or "")
    return ("특약" in blob) or ("약정" in blob)
'''


def prec_fields_from_obj(obj) -> tuple[str, str]:
    if not isinstance(obj, dict):
        return "", ""
    # nested
    node = obj.get("PrecService") or obj.get("판례") or obj
    if isinstance(node, dict):
        return str(node.get("판시사항") or ""), str(node.get("판결요지") or "")
    return "", ""


def fix_D(key: str) -> dict:
    sec = {
        "filter_code": FILTER_CODE.strip(),
        "existing_400": {},
        "full_list_fetch": {},
        "by_keyword_pass": {},
    }
    bodies_dir = LAW / "판례" / "bodies"
    uniq_path = LAW / "판례" / "_unique_list.json"
    # count existing 400
    n_total = 0
    n_pass = 0
    if bodies_dir.exists():
        for p in bodies_dir.glob("*.json"):
            n_total += 1
            t = p.read_text(encoding="utf-8", errors="replace")
            j = parse_json(t) or {}
            a, b = prec_fields_from_obj(j)
            if ("특약" in a + b) or ("약정" in a + b):
                n_pass += 1
            elif ("특약" in t[:8000]) or ("약정" in t[:8000]):
                # fallback if fields elsewhere
                if "판시사항" in t and ("특약" in t or "약정" in t):
                    n_pass += 1
    sec["existing_400"] = {
        "n_files": n_total,
        "pass_판시사항_or_판결요지_특약_약정": n_pass,
    }

    # load unique list
    items = []
    if uniq_path.exists():
        items = json.loads(uniq_path.read_text(encoding="utf-8"))
    # also reload from list files to rebuild id->keyword map
    id_to_kws = defaultdict(set)
    prec_dir = LAW / "판례"
    for p in prec_dir.glob("list_*.json"):
        # list_{kw}_p{n}.json
        m = re.match(r"list_(.+)_p\d+\.json", p.name)
        kw = m.group(1).replace("_", " ") if m else "?"
        t = p.read_text(encoding="utf-8", errors="replace")
        j = parse_json(t)
        if not j:
            continue
        for it in extract_list_items(j, "PrecSearch"):
            pid = get_id(it)
            if pid:
                id_to_kws[str(pid)].add(kw)

    # if unique list incomplete vs 1986, rebuild from all list files
    all_items = {}
    for p in prec_dir.glob("list_*.json"):
        j = parse_json(p.read_text(encoding="utf-8", errors="replace"))
        if not j:
            continue
        for it in extract_list_items(j, "PrecSearch"):
            pid = get_id(it)
            if pid:
                all_items[str(pid)] = it
    sec["full_list_fetch"]["unique_list_n"] = len(all_items)

    out_bodies = LAW / "판례" / "bodies_filtered_v2"
    out_bodies.mkdir(parents=True, exist_ok=True)
    pass_ids = []
    kw_pass = Counter()
    # First check list fields; else fetch body
    n_fetched = 0
    n_pass_final = 0
    sample = None
    for pid, it in all_items.items():
        dest = out_bodies / f"{pid}.json"
        if dest.exists():
            body_text = dest.read_text(encoding="utf-8", errors="replace")
        else:
            old = bodies_dir / f"{pid}.json"
            if old.exists():
                body_text = old.read_text(encoding="utf-8", errors="replace")
            else:
                tb = http_get({"OC": key, "target": "prec", "type": "JSON", "ID": pid}, SERVICE)
                n_fetched += 1
                if is_html(tb) or not parse_json(tb):
                    continue
                body_text = tb
                # cache all bodies under bodies/ for resume (no delete)
                save(bodies_dir / f"{pid}.json", body_text)
        j = parse_json(body_text) or {}
        a2, b2 = prec_fields_from_obj(j)
        if ("특약" in a2 + b2) or ("약정" in a2 + b2):
            save(dest, body_text)
            n_pass_final += 1
            pass_ids.append(pid)
            for kw in id_to_kws.get(pid, {"?"}):
                kw_pass[kw] += 1
            if sample is None:
                sample = redact(body_text)[:300]
        if (n_fetched and n_fetched % 50 == 0) or (n_pass_final and n_pass_final % 100 == 0):
            print("D progress fetched_new", n_fetched, "pass", n_pass_final, "seen", len(pass_ids))

    sec["full_list_fetch"].update({
        "bodies_fetched_new_or_reused": n_fetched,
        "pass_count": n_pass_final,
        "sample_head_300": sample,
        "success_criterion": "PrecService/판례 JSON + 판시사항|판결요지 contains 특약|약정",
    })
    sec["by_keyword_pass"] = dict(kw_pass)
    return sec


# ---------- E ----------
def fix_E() -> dict:
    from collections import Counter
    OUT = DC / "aihub_forms"
    SRC = ROOT / "05.계약 법률 문서 서식 데이터"
    c = Counter()
    for p in OUT.rglob("*.json"):
        if not any(x.startswith(("TL_", "VL_")) for x in p.parts):
            continue
        if "금전" not in str(p) and "채권" not in str(p):
            continue
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cat = (((o.get("document") or {}).get("metadata") or {}).get("file_info") or {}).get("document_category") or {}
        c[(cat.get("main_category"), cat.get("sub_category"), cat.get("detail_category"))] += 1
    zips = []
    if SRC.exists():
        for z in sorted(SRC.rglob("*.zip")):
            zips.append({"zip": str(z.relative_to(SRC)), "bytes": z.stat().st_size})
    has = any("금전대차계약서" == (k[2] or "") for k in c)
    return {
        "has_금전대차계약서_detail": has,
        "money_taxonomy": [
            {"대": a, "중": b, "소": sub, "count": n}
            for (a, b, sub), n in c.most_common()
        ],
        "source_zips": zips,
        "conclusion": "개방 zip에 없음" if not has else "있음",
    }


# ---------- F ----------
def sha256_file(path: Path, chunk=8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fix_F() -> dict:
    from huggingface_hub import HfApi, hf_hub_url
    import requests

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    api = HfApi(token=token)
    models = [
        ("Qwen/Qwen3-8B", DC / "models" / "Qwen3-8B"),
        ("nlpai-lab/KURE-v1", DC / "models" / "KURE-v1"),
        ("BAAI/bge-m3", DC / "models" / "bge-m3"),
    ]
    rows = []
    for repo, local in models:
        info = api.model_info(repo, files_metadata=True)
        lfs_map = {}
        for s in info.siblings or []:
            name = s.rfilename
            if not name:
                continue
            # LFS oid is sha256
            oid = None
            if getattr(s, "lfs", None):
                oid = s.lfs.get("sha256") or s.lfs.get("oid")
                if isinstance(oid, str) and oid.startswith("sha256:"):
                    oid = oid.split(":", 1)[1]
            lfs_map[name] = {"size": s.size, "sha256": oid}
        # local weight files
        for f in sorted(local.rglob("*")):
            if not f.is_file():
                continue
            if ".cache" in f.parts or "incomplete" in f.name:
                continue
            if f.suffix.lower() not in {".safetensors", ".bin"} and "model" not in f.name:
                continue
            if f.suffix.lower() not in {".safetensors", ".bin"}:
                continue
            rel = str(f.relative_to(local)).replace("\\", "/")
            local_hash = sha256_file(f)
            remote = lfs_map.get(rel) or lfs_map.get(f.name)
            remote_hash = (remote or {}).get("sha256")
            rows.append({
                "repo": repo,
                "file": rel,
                "local_bytes": f.stat().st_size,
                "local_sha256": local_hash,
                "hf_lfs_sha256": remote_hash,
                "match": (local_hash == remote_hash) if remote_hash else None,
            })
            print("F hashed", repo, rel, "match", rows[-1]["match"])

    incs = []
    for f in (DC / "models").rglob("*.incomplete"):
        incs.append({"path": str(f), "bytes": f.stat().st_size})
    return {"hash_compare": rows, "incomplete_remaining_paths": incs, "incomplete_n": len(incs)}


def _dump(result: dict):
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    key = oc()
    assert key, "LAW_OC missing"
    result = {}
    if OUT.exists():
        try:
            result = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            result = {}
    result["oc_configured"] = True

    def run_step(name, fn):
        if name in result and result[name] and not result[name].get("_error"):
            print(name, "skip (cached)")
            return
        print(name + "...")
        try:
            result[name] = fn()
        except Exception as e:
            result[name] = {"_error": repr(e)}
            print(name, "ERROR", e)
        _dump(result)

    run_step("A", lambda: fix_A(key))
    run_step("B", lambda: fix_B(key))
    run_step("C", lambda: fix_C(key))
    run_step("D", lambda: fix_D(key))
    run_step("E", fix_E)
    if not os.environ.get("HF_TOKEN"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                v, _ = winreg.QueryValueEx(k, "HF_TOKEN")
                os.environ["HF_TOKEN"] = str(v)
        except Exception:
            pass
    run_step("F", fix_F)
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
