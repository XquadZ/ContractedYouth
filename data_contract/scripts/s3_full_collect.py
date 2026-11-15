# -*- coding: utf-8 -*-
"""3단계: 법령 Open API 전체 수집. OC는 env LAW_OC만 사용(절대 출력 금지)."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
OUT = ROOT / "data_contract" / "law_api"
REPORT = ROOT / "data_contract" / "s3_results.json"

SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"

# Official guide evidence (htmlName pages on open.law.go.kr)
GUIDE = {
    "portal_list": "https://open.law.go.kr/LSO/openApi/guideList.do",
    "law_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=law&type=1",
        "url": SEARCH,
        "target": "law",
        "key_params": ["OC", "target=law", "type", "search(1명/2본문)", "query", "display<=100", "page", "efYd", "ancYd", "date", "nb"],
    },
    "law_body": {
        "guide_candidates_tried": [
            "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lawInfoGuide",
            "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsInfoGuide",
            "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsBodInfoGuide",
        ],
        "note": "본문 가이드 htmlName 페이지는 404. 목록 API 응답의 법령상세링크가 lawService.do?target=law&MST={법령일련번호} 형태임을 확인(실측). ID 파라미터는 '일치하는 법령이 없습니다' 응답. 따라서 MST=법령일련번호로 본문 조회.",
        "url": SERVICE,
        "target": "law",
        "params_confirmed_by_list_link": ["OC", "target=law", "MST=법령일련번호", "type"],
        "evidence": "LawSearch.law[].법령상세링크 실측 필드",
    },
    "prec_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide",
        "url": SEARCH,
        "target": "prec",
        "key_params": ["search=2 본문검색", "query", "display", "page"],
    },
    "prec_body": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide",
        "url": SERVICE,
        "target": "prec",
        "key_params": ["ID(판례일련번호)", "type"],
    },
    "admrul_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide",
        "url": SEARCH,
        "target": "admrul",
        "key_params": ["nw(1현행/2연혁)", "query", "knd", "search", "prmlYd"],
    },
    "admrul_body": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide",
        "url": SERVICE,
        "target": "admrul",
        "key_params": ["ID", "LID", "LM"],
    },
    "expc_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide",
        "url": SEARCH,
        "target": "expc",
        "key_params": ["search", "query", "inq", "rpl"],
    },
    "expc_body": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcInfoGuide",
        "url": SERVICE,
        "target": "expc",
        "key_params": ["ID"],
    },
    "ftc_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cmtListGuide",
        "url": SEARCH,
        "target": "ftc",
        "key_params": ["search", "query", "type=HTML|XML (가이드상 JSON 미기재)"],
        "type_note": "가이드 표기는 HTML/XML. JSON 시도 후 실패 시 XML 저장.",
    },
    "ftc_body": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cmtInfoGuide",
        "url": SERVICE,
        "target": "ftc",
        "key_params": ["ID", "type=HTML|XML"],
    },
    "lstrm_list": {
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsTrmListGuide",
        "url": SEARCH,
        "target": "lstrm",
    },
    "lstrmRlt": {
        "guide": "http://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide",
        "url": SERVICE,
        "target": "lstrmRlt",
        "key_params": ["query|MST", "trmRltCd"],
    },
    "history": {
        "efYd_list": "법령 목록 API efYd 범위 필터 문서화됨 (law list guide)",
        "asof_body": "특정일 시점 본문 전용 파라미터는 가이드에서 미확인. 연혁 목록(시행일>=20220101) 저장 후 각 법령일련번호로 본문 조회 시도.",
        "admrul_nw": "행정규칙 목록 nw=2 연혁 (admrulListGuide)",
    },
}

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

PREC_KW = [
    "임대차 특약 무효", "원상복구 특약", "임대차 위약금", "보증금 반환 특약", "계약갱신요구권 포기",
    "근로계약 위약금", "위약예정", "임금 공제", "수습기간 임금", "주휴수당", "휴게시간",
    "이자제한법 초과", "보증 서면", "차용증",
]

EXPC_ORGS = [
    ("고용노동부", None),
    ("법무부", None),
    ("국토교통부", None),
    ("법제처", None),
]
EXPC_KW = ["근로계약", "최저임금", "주휴", "수습", "임대차", "보증금", "이자"]
FTC_KW = ["임대차 약관", "임대차계약서"]


def oc() -> str:
    return os.environ.get("LAW_OC", "").strip()


def http_get(params: dict, base: str = SEARCH) -> tuple[bool, str, str]:
    """Return ok, text, error. Never log OC."""
    safe = {k: v for k, v in params.items() if k != "OC"}
    q = urllib.parse.urlencode(params, doseq=True, encoding="utf-8")
    url = f"{base}?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
        # decode
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                text = raw.decode("utf-8", "replace")
        time.sleep(0.55)
        return True, text, ""
    except Exception as e:
        time.sleep(0.55)
        return False, "", repr(e)


def redact(text: str) -> str:
    """Never persist OC values from detail links or payloads."""
    text = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", text or "")
    text = re.sub(r'("OC"\s*:\s*")[^"]+(")', r"\1REDACTED\2", text)
    return text


def save(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def parse_jsonish(text: str):
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        # sometimes wrapped
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def pick_law_item(data, name: str):
    """Pick best matching law from search JSON (구조 변형 대응)."""
    if data is None:
        return None
    cands = []
    node = data
    if isinstance(data, dict) and "LawSearch" in data:
        node = data["LawSearch"]
    if isinstance(node, dict):
        law = node.get("law")
        if isinstance(law, list):
            cands.extend([x for x in law if isinstance(x, dict)])
        elif isinstance(law, dict):
            cands.append(law)
        else:
            for v in node.values():
                if isinstance(v, list):
                    cands.extend([x for x in v if isinstance(x, dict)])
                elif isinstance(v, dict) and "법령명한글" in v:
                    cands.append(v)
    exact = [c for c in cands if c.get("법령명한글") == name]
    pool = exact or [
        c for c in cands
        if name.replace(" ", "") in str(c.get("법령명한글", "")).replace(" ", "")
    ]
    if not pool:
        return cands[0] if cands else None
    for c in pool:
        code = str(c.get("현행연혁코드", ""))
        if code == "현행" or "현행" in code:
            return c
    return pool[0]


def get_id(item: dict):
    for k in ("법령일련번호", "판례일련번호", "판례정보일련번호", "행정규칙일련번호", "행정규칙 일련번호",
              "법령해석례일련번호", "결정문일련번호", "결정문 일련번호", "id", "ID"):
        if item.get(k) not in (None, ""):
            return item.get(k)
    return None


def sample_head(text: str, n=300) -> str:
    return (text or "")[:n]


def main():
    key = oc()
    result = {
        "oc_configured": bool(key),
        "guide": GUIDE,
        "status": None,
        "sections": {},
    }
    (OUT / "_guide_evidence.json").write_text(json.dumps(GUIDE, ensure_ascii=False, indent=2), encoding="utf-8")
    if not key:
        result["status"] = "OC 미설정"
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OC missing")
        return

    # ---- 3-1 current laws ----
    sec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "sample_head_300": None}
    cur = OUT / "현행"
    cur.mkdir(parents=True, exist_ok=True)
    law_ids = {}  # name -> {일련번호, 법령ID, 시행일자}
    for name in LAWS:
        params = {"OC": key, "target": "law", "type": "JSON", "query": name, "display": 50}
        sec["요청수"] += 1
        ok, text, err = http_get(params, SEARCH)
        sp = cur / f"{name}_search.json"
        if not ok:
            sec["실패수"] += 1
            sec["실패"].append({"step": "search", "name": name, "error": err})
            continue
        save(sp, text)
        sec["성공수"] += 1
        sec["저장"].append(str(sp))
        data = parse_jsonish(text)
        item = pick_law_item(data, name)
        if not item:
            sec["실패"].append({"step": "parse", "name": name, "error": "no item", "head": sample_head(text)})
            continue
        lid = item.get("법령일련번호") or get_id(item)
        law_code = item.get("법령ID") or item.get("법령Id")
        # detail link uses MST=<법령일련번호>
        mst_for_body = lid
        law_ids[name] = {
            "법령일련번호": lid,
            "법령ID": law_code,
            "시행일자": item.get("시행일자"),
            "공포번호": item.get("공포번호"),
            "현행연혁코드": item.get("현행연혁코드"),
            "body_param": "MST",
        }
        body_ok = False
        if mst_for_body:
            sec["요청수"] += 1
            ok2, text2, err2 = http_get({"OC": key, "target": "law", "type": "JSON", "MST": mst_for_body}, SERVICE)
            bp = cur / f"{name}_body_MST.json"
            if ok2 and text2 and "없습니다" not in text2[:120]:
                save(bp, text2)
                sec["성공수"] += 1
                sec["저장"].append(str(bp))
                if sec["sample_head_300"] is None:
                    sec["sample_head_300"] = sample_head(text2)
                body_ok = True
            else:
                sec["실패수"] += 1
                sec["실패"].append({"step": "body_MST", "name": name, "error": err2 or sample_head(text2, 200)})
        if not body_ok:
            sec["실패"].append({"step": "body", "name": name, "error": "MST body failed"})
    result["sections"]["3-1"] = {**sec, "law_ids": law_ids}

    # ---- 3-2 history: efYd list + body per 일련번호 after 2022-01-01 ----
    hsec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "note": GUIDE["history"], "sample_head_300": None}
    hist = OUT / "연혁"
    hist.mkdir(parents=True, exist_ok=True)
    for name in LAWS:
        params = {
            "OC": key, "target": "law", "type": "JSON", "query": name,
            "efYd": "20220101~20301231", "display": 100, "sort": "efasc",
        }
        hsec["요청수"] += 1
        ok, text, err = http_get(params, SEARCH)
        sp = hist / f"{name}_efYd_list.json"
        if not ok:
            hsec["실패수"] += 1
            hsec["실패"].append({"name": name, "error": err})
            continue
        save(sp, text)
        hsec["성공수"] += 1
        hsec["저장"].append(str(sp))
        if hsec["sample_head_300"] is None:
            hsec["sample_head_300"] = sample_head(text)
        data = parse_jsonish(text)
        # collect items
        items = []
        if isinstance(data, dict):
            node = data.get("LawSearch") or data
            for v in (node.values() if isinstance(node, dict) else []):
                if isinstance(v, list):
                    items.extend([x for x in v if isinstance(x, dict)])
        # save revision table
        rev = []
        for it in items:
            if name.replace(" ", "") not in str(it.get("법령명한글", "")).replace(" ", ""):
                continue
            rev.append({
                "법령명한글": it.get("법령명한글"),
                "시행일자": it.get("시행일자"),
                "공포일자": it.get("공포일자"),
                "공포번호": it.get("공포번호"),
                "법령일련번호": get_id(it),
                "현행연혁코드": it.get("현행연혁코드"),
                "제개정구분명": it.get("제개정구분명"),
            })
        save(hist / f"{name}_revision_table.json", json.dumps(rev, ensure_ascii=False, indent=2))
        # fetch bodies for up to 8 unique IDs
        seen = set()
        for r in rev:
            lid = r.get("법령일련번호")
            if not lid or lid in seen:
                continue
            seen.add(lid)
            if len(seen) > 8:
                break
            hsec["요청수"] += 1
            ok2, text2, err2 = http_get({"OC": key, "target": "law", "type": "JSON", "MST": lid}, SERVICE)
            bp = hist / f"{name}_body_MST_{lid}.json"
            if ok2:
                save(bp, text2)
                hsec["성공수"] += 1
                hsec["저장"].append(str(bp))
            else:
                hsec["실패수"] += 1
                hsec["실패"].append({"name": name, "ID": lid, "error": err2})
    result["sections"]["3-2"] = hsec

    # ---- 3-3 admin rules 최저임금 고시 ----
    asec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "hourly_table": [], "sample_head_300": None}
    adm = OUT / "행정규칙"
    adm.mkdir(parents=True, exist_ok=True)
    for year in [2022, 2023, 2024, 2025, 2026]:
        q = f"{year}년 적용 최저임금"
        asec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "admrul", "type": "JSON", "query": "최저임금", "display": 100, "search": 1}, SEARCH)
        # also year-specific
        asec["요청수"] += 1
        ok2, text2, err2 = http_get({"OC": key, "target": "admrul", "type": "JSON", "query": f"최저임금고시", "display": 100}, SEARCH)
        for label, okx, textx, errx in [(f"최저임금_{year}", ok, text, err), (f"최저임금고시_{year}", ok2, text2, err2)]:
            if not okx:
                asec["실패수"] += 1
                asec["실패"].append({"q": label, "error": errx})
                continue
            sp = adm / f"{label}_search.json"
            # only save once per unique content year folder
            if year == 2022 or "고시" in label:
                save(sp, textx)
                asec["성공수"] += 1
                asec["저장"].append(str(sp))
                if asec["sample_head_300"] is None:
                    asec["sample_head_300"] = sample_head(textx)
        # pick items mentioning year and 최저임금
        data = parse_jsonish(text2 if ok2 else text)
        items = []
        if isinstance(data, dict):
            node = data.get("AdmRulSearch") or data.get("LawSearch") or data
            if isinstance(node, dict):
                for v in node.values():
                    if isinstance(v, list):
                        items.extend([x for x in v if isinstance(x, dict)])
        chosen = None
        for it in items:
            nm = str(it.get("행정규칙명", ""))
            if "최저임금" in nm and str(year) in nm:
                chosen = it
                break
        if chosen:
            aid = get_id(chosen) or chosen.get("행정규칙ID")
            asec["요청수"] += 1
            okb, textb, errb = http_get({"OC": key, "target": "admrul", "type": "JSON", "ID": aid}, SERVICE)
            if okb:
                bp = adm / f"최저임금_{year}_body.json"
                save(bp, textb)
                asec["성공수"] += 1
                asec["저장"].append(str(bp))
                # extract hourly wage
                m = re.search(r"시간급[^\d]{0,10}([\d,]+)\s*원", textb)
                if not m:
                    m = re.search(r"([\d,]+)\s*원", textb)
                asec["hourly_table"].append({
                    "year": year,
                    "name": chosen.get("행정규칙명"),
                    "ID": aid,
                    "hourly": m.group(1) if m else "미추출",
                    "evidence": (m.group(0) if m else sample_head(textb, 120)),
                })
            else:
                asec["실패수"] += 1
                asec["실패"].append({"year": year, "error": errb})
        else:
            asec["hourly_table"].append({"year": year, "name": None, "hourly": "미확인", "note": "검색 목록에서 연도 매칭 실패"})
    result["sections"]["3-3"] = asec

    # ---- 3-4 precedents ----
    psec = {
        "요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [],
        "by_keyword": {}, "unique_list": 0, "bodies_saved": 0, "sample_head_300": None,
    }
    prec_dir = OUT / "판례"
    prec_dir.mkdir(parents=True, exist_ok=True)
    all_items = {}  # id -> item
    for kw in PREC_KW:
        items_kw = []
        page = 1
        while len(items_kw) < 200:
            psec["요청수"] += 1
            ok, text, err = http_get({
                "OC": key, "target": "prec", "type": "JSON", "search": 2,
                "query": kw, "display": 100, "page": page,
            }, SEARCH)
            if not ok:
                psec["실패수"] += 1
                psec["실패"].append({"kw": kw, "page": page, "error": err})
                break
            sp = prec_dir / f"list_{kw.replace(' ', '_')}_p{page}.json"
            save(sp, text)
            psec["성공수"] += 1
            psec["저장"].append(str(sp))
            if psec["sample_head_300"] is None:
                psec["sample_head_300"] = sample_head(text)
            data = parse_jsonish(text)
            batch = []
            if isinstance(data, dict):
                node = data.get("PrecSearch") or data
                if isinstance(node, dict):
                    for v in node.values():
                        if isinstance(v, list):
                            batch.extend([x for x in v if isinstance(x, dict)])
            if not batch:
                break
            for it in batch:
                pid = get_id(it) or it.get("판례정보일련번호")
                if pid is None:
                    continue
                items_kw.append(it)
                all_items[str(pid)] = it
            # totalCnt
            total = None
            if isinstance(data, dict):
                node = data.get("PrecSearch") or data
                if isinstance(node, dict):
                    total = node.get("totalCnt") or node.get("총건수")
            if total is not None and page * 100 >= int(total):
                break
            if len(batch) < 100:
                break
            page += 1
            if page > 3:  # max 200 with display 100
                break
        psec["by_keyword"][kw] = len(items_kw)
    psec["unique_list"] = len(all_items)
    save(prec_dir / "_unique_list.json", json.dumps(list(all_items.values())[:500], ensure_ascii=False, indent=2))

    # bodies: only if 판시사항/판결요지 contains 특약 or 약정 — need body or list fields
    bodies = 0
    for pid, it in list(all_items.items()):
        # if list already has 판시사항
        summary = str(it.get("판시사항", "")) + str(it.get("판결요지", ""))
        need_body = True
        if summary and (("특약" in summary) or ("약정" in summary)):
            fetch = True
        elif summary:
            fetch = False
        else:
            fetch = True  # unknown, fetch then filter
        if not fetch:
            continue
        psec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "prec", "type": "JSON", "ID": pid}, SERVICE)
        if not ok:
            psec["실패수"] += 1
            psec["실패"].append({"ID": pid, "error": err})
            continue
        if ("특약" in text) or ("약정" in text):
            # check in 판시/요지 preferentially
            data = parse_jsonish(text) or {}
            blob = text
            if isinstance(data, dict):
                prec = data.get("PrecService") or data.get("판례") or data
                if isinstance(prec, dict):
                    blob = str(prec.get("판시사항", "")) + str(prec.get("판결요지", ""))
            if ("특약" in blob) or ("약정" in blob) or (("특약" in text[:5000]) or ("약정" in text[:5000])):
                bp = prec_dir / "bodies" / f"{pid}.json"
                save(bp, text)
                bodies += 1
                psec["성공수"] += 1
                psec["저장"].append(str(bp))
            else:
                psec["성공수"] += 1  # call ok but filtered
        else:
            psec["성공수"] += 1
        if bodies >= 400:
            break
    psec["bodies_saved"] = bodies
    result["sections"]["3-4"] = psec

    # ---- 3-5 법령해석례 ----
    esec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "sample_head_300": None, "bodies": 0}
    ed = OUT / "법령해석례"
    ed.mkdir(parents=True, exist_ok=True)
    expc_ids = {}
    for kw in EXPC_KW:
        for org_name, _ in EXPC_ORGS:
            esec["요청수"] += 1
            ok, text, err = http_get({
                "OC": key, "target": "expc", "type": "JSON", "search": 2,
                "query": kw, "display": 50, "page": 1,
            }, SEARCH)
            # org filter not clearly documented as name; save all and tag
            tag = f"{org_name}_{kw}".replace(" ", "_")
            if not ok:
                esec["실패수"] += 1
                esec["실패"].append({"tag": tag, "error": err})
                continue
            sp = ed / f"list_{tag}.json"
            save(sp, text)
            esec["성공수"] += 1
            esec["저장"].append(str(sp))
            if esec["sample_head_300"] is None:
                esec["sample_head_300"] = sample_head(text)
            data = parse_jsonish(text)
            items = []
            if isinstance(data, dict):
                node = data.get("ExpcSearch") or data
                if isinstance(node, dict):
                    for v in node.values():
                        if isinstance(v, list):
                            items.extend([x for x in v if isinstance(x, dict)])
            for it in items[:10]:
                # filter by org name fields if present
                org_fields = str(it.get("질의기관명", "")) + str(it.get("회신기관명", "")) + str(it.get("해석기관명", ""))
                if org_name not in org_fields and org_fields.strip():
                    continue
                eid = get_id(it)
                if eid:
                    expc_ids[str(eid)] = it
    # bodies
    for eid in list(expc_ids.keys())[:80]:
        esec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "expc", "type": "JSON", "ID": eid}, SERVICE)
        if ok:
            save(ed / "bodies" / f"{eid}.json", text)
            esec["성공수"] += 1
            esec["bodies"] += 1
            esec["저장"].append(str(ed / "bodies" / f"{eid}.json"))
        else:
            esec["실패수"] += 1
            esec["실패"].append({"ID": eid, "error": err})
    result["sections"]["3-5"] = esec

    # ---- 3-6 FTC ----
    fsec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "sample_head_300": None, "bodies": 0, "type_used": None}
    fd = OUT / "공정위"
    fd.mkdir(parents=True, exist_ok=True)
    ftc_ids = {}
    for kw in FTC_KW:
        for typ in ("XML", "HTML", "JSON"):
            fsec["요청수"] += 1
            ok, text, err = http_get({
                "OC": key, "target": "ftc", "type": typ, "search": 2,
                "query": kw, "display": 50, "page": 1,
            }, SEARCH)
            if ok and text and len(text) > 50:
                sp = fd / f"list_{kw.replace(' ','_')}_{typ}.xml" if typ != "JSON" else fd / f"list_{kw.replace(' ','_')}.json"
                if typ == "HTML":
                    sp = fd / f"list_{kw.replace(' ','_')}.html"
                save(sp, text)
                fsec["성공수"] += 1
                fsec["저장"].append(str(sp))
                fsec["type_used"] = typ
                if fsec["sample_head_300"] is None:
                    fsec["sample_head_300"] = sample_head(text)
                # extract IDs from XML/HTML
                for m in re.findall(r"<결정문일련번호>(\d+)</결정문일련번호>", text):
                    ftc_ids[m] = kw
                for m in re.findall(r"ID=(\d+)", text):
                    ftc_ids[m] = kw
                break
            else:
                fsec["실패수"] += 1
                fsec["실패"].append({"kw": kw, "type": typ, "error": err or sample_head(text, 120)})
    for fid in list(ftc_ids.keys())[:40]:
        fsec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "ftc", "type": "XML", "ID": fid}, SERVICE)
        if ok:
            save(fd / "bodies" / f"{fid}.xml", text)
            fsec["성공수"] += 1
            fsec["bodies"] += 1
            fsec["저장"].append(str(fd / "bodies" / f"{fid}.xml"))
        else:
            fsec["실패수"] += 1
            fsec["실패"].append({"ID": fid, "error": err})
    result["sections"]["3-6"] = fsec

    # ---- 3-7 terminology linkage ----
    tsec = {"요청수": 0, "성공수": 0, "실패수": 0, "실패": [], "저장": [], "sample_head_300": None}
    td = OUT / "법령용어"
    td.mkdir(parents=True, exist_ok=True)
    # list dump pages of lstrm
    for page in range(1, 6):
        tsec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "lstrm", "type": "JSON", "display": 100, "page": page, "query": ""}, SEARCH)
        # empty query may fail; try gana
        if not ok or len(text) < 20:
            tsec["요청수"] += 1
            ok, text, err = http_get({"OC": key, "target": "lstrm", "type": "JSON", "display": 100, "page": page, "gana": "ga"}, SEARCH)
        if ok:
            save(td / f"lstrm_list_p{page}.json", text)
            tsec["성공수"] += 1
            tsec["저장"].append(str(td / f"lstrm_list_p{page}.json"))
            if tsec["sample_head_300"] is None:
                tsec["sample_head_300"] = sample_head(text)
        else:
            tsec["실패수"] += 1
            tsec["실패"].append({"page": page, "error": err})
    # linkage samples for contract terms
    for q in ["근로계약", "임대차", "보증금", "위약금", "최저임금", "차용", "이자"]:
        tsec["요청수"] += 1
        ok, text, err = http_get({"OC": key, "target": "lstrmRlt", "type": "JSON", "query": q}, SERVICE)
        if ok:
            save(td / f"lstrmRlt_{q}.json", text)
            tsec["성공수"] += 1
            tsec["저장"].append(str(td / f"lstrmRlt_{q}.json"))
        else:
            tsec["실패수"] += 1
            tsec["실패"].append({"query": q, "error": err})
    result["sections"]["3-7"] = tsec

    result["status"] = "calls_completed"
    # strip any accidental OC from stored? we don't put OC in result
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE status=calls_completed")
    for k, v in result["sections"].items():
        print(k, "req", v.get("요청수"), "ok", v.get("성공수"), "fail", v.get("실패수"), "saved", len(v.get("저장") or []))


if __name__ == "__main__":
    main()
