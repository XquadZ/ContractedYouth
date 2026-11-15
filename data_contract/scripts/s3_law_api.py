# -*- coding: utf-8 -*-
"""3단계: 국가법령정보센터 Open API 수집. LAW_OC 없으면 가이드 근거만 저장하고 호출 건너뜀."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
OUT = ROOT / "data_contract" / "law_api"
REPORT = ROOT / "data_contract" / "s3_results.json"

# Guide evidence collected from open.law.go.kr (do not invent targets)
GUIDE = {
    "portal": "https://open.law.go.kr/",
    "law_list": {
        "url": "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=law&type=1",
        "request_url": "http://www.law.go.kr/DRF/lawSearch.do",
        "target": "law",
        "params": {
            "OC": "필수",
            "target": "law",
            "type": "JSON/XML/HTML",
            "search": "1=법령명(기본), 2=본문검색",
            "query": "검색어",
            "display": "max=100",
            "page": "페이지",
            "efYd": "시행일자 범위 20090101~20090130",
            "ancYd": "공포일자 범위",
            "date": "공포일자",
            "nb": "공포번호",
        },
        "response_fields_note": "현행연혁코드, 법령ID, 시행일자, 공포번호 등",
    },
    "law_body": {
        "note": "목록 API와 별도 본문 API가 있음. 가이드에서 lawService.do 형태가 흔히 안내됨.",
        "candidate_url_documented_elsewhere": "http://www.law.go.kr/DRF/lawService.do",
        "params_typical": {"OC": "필수", "target": "law", "ID": "법령ID 또는 MST", "type": "JSON"},
        "status": "가이드 페이지 WebFetch가 target 파라미터와 무관하게 동일 HTML을 반환해 본문 API 표는 미확인. OC 승인 후 가이드 UI에서 재확인 필요.",
    },
    "history_asof": {
        "efYd_on_list": "목록 검색의 시행일자 범위 필터는 문서화됨",
        "single_date_body": "2022-01-01 시점 본문 단건 조회 전용 파라미터가 가이드 HTML에서 확인되지 않음 → 연혁 조회 방법 미확인",
        "conclusion": "OC 없으면 실호출 불가. 문서상 efYd는 범위 필터. 시점 본문 단건은 미확인.",
    },
    "other_targets_attempted_fetch": [
        "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=prec&type=1",
        "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=admrul&type=1",
    ],
    "other_targets_fetch_result": "WebFetch 결과가 법령(law) 가이드와 동일 본문으로 돌아와 prec/admrul 표는 미확인",
}


LAWS_CURRENT = [
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


def oc() -> str:
    return os.environ.get("LAW_OC", "").strip()


def get_json(url: str) -> tuple[int, object, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    text = raw.decode("utf-8", "replace")
    try:
        return r.status if hasattr(r, "status") else 200, json.loads(text), text[:500]
    except Exception:
        return 200, None, text[:2000]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_guide_evidence.json").write_text(json.dumps(GUIDE, ensure_ascii=False, indent=2), encoding="utf-8")
    key = oc()
    result = {
        "oc_configured": bool(key),
        "guide": GUIDE,
        "status": None,
        "sections": {},
    }
    if not key:
        result["status"] = "OC 미설정"
        result["note"] = "환경변수 LAW_OC 비어 있음. 3-1~3-7 API 호출 전부 건너뜀. OC 값은 기록하지 않음."
        for name in ["현행", "연혁", "행정규칙", "판례", "법령해석례", "공정위", "법령용어"]:
            (OUT / name).mkdir(parents=True, exist_ok=True)
            (OUT / name / "SKIPPED_OC.txt").write_text("LAW_OC not set; no API calls.\n", encoding="utf-8")
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OC not set - skipped calls")
        return

    # If OC set: perform documented calls only
    base_search = "http://www.law.go.kr/DRF/lawSearch.do"
    sec = {"요청수": 0, "성공수": 0, "실패": [], "저장": []}

    # 3-1 current law list+try body
    cur_dir = OUT / "현행"
    cur_dir.mkdir(parents=True, exist_ok=True)
    for name in LAWS_CURRENT:
        q = urllib.parse.urlencode({"OC": key, "target": "law", "type": "JSON", "query": name, "display": 20})
        url = f"{base_search}?{q}"
        sec["요청수"] += 1
        try:
            time.sleep(0.55)
            # manual request to avoid printing OC
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8", "replace")
            path = cur_dir / f"{name}_search.json"
            path.write_text(text, encoding="utf-8")
            sec["성공수"] += 1
            sec["저장"].append(str(path))
            sample = text[:300]
        except Exception as e:
            sec["실패"].append({"name": name, "error": repr(e)})
    result["sections"]["3-1"] = {**sec, "sample_head_300": sample if sec["저장"] else None}

    # 3-2 history: try efYd range list for each law from 20220101
    hist_dir = OUT / "연혁"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hsec = {"요청수": 0, "성공수": 0, "실패": [], "저장": [], "note": "목록 efYd 범위만 시도. 시점 본문은 가이드 미확인으로 단건 본문 시점조회 안 함."}
    for name in LAWS_CURRENT:
        q = urllib.parse.urlencode({
            "OC": key, "target": "law", "type": "JSON", "query": name,
            "efYd": "20220101~20301231", "display": 100,
        })
        url = f"{base_search}?{q}"
        hsec["요청수"] += 1
        try:
            time.sleep(0.55)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8", "replace")
            path = hist_dir / f"{name}_efYd_20220101plus_search.json"
            path.write_text(text, encoding="utf-8")
            hsec["성공수"] += 1
            hsec["저장"].append(str(path))
        except Exception as e:
            hsec["실패"].append({"name": name, "error": repr(e)})
    result["sections"]["3-2"] = hsec

    # Remaining sections: only if we can confirm targets — mark 미확인 without guessing
    for code, title in [
        ("3-3", "행정규칙"),
        ("3-4", "판례"),
        ("3-5", "법령해석례"),
        ("3-6", "공정위"),
        ("3-7", "법령용어"),
    ]:
        d = OUT / title
        d.mkdir(parents=True, exist_ok=True)
        result["sections"][code] = {
            "status": "미확인",
            "reason": "open.law 가이드 WebFetch가 target별 표를 반환하지 않아 추측 호출 금지. 가이드 UI에서 target 확인 후 재실행 필요.",
        }
        (d / "SKIPPED_GUIDE_UNCONFIRMED.txt").write_text(result["sections"][code]["reason"] + "\n", encoding="utf-8")

    result["status"] = "partial"
    # strip any accidental OC from saved? we don't put OC in result
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", result["status"])


if __name__ == "__main__":
    main()
