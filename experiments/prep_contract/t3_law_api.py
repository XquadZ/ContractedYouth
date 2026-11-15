# -*- coding: utf-8 -*-
"""T3: 국가법령정보센터 Open API 확인. OC는 환경변수 LAW_OC만 사용(값 출력 금지)."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PREP = ROOT / "prep_contract"
LAW_DIR = PREP / "law" / "현행"

# Docs reference (no OC): https://open.law.go.kr/
# Typical endpoints (to be verified by response):
# - 현행법령: http://www.law.go.kr/DRF/lawService.do?OC={OC}&target=law&type=JSON&ID=...
# - or MST / LM query

LAWS = [
    "근로기준법",
    "근로기준법 시행령",
    "최저임금법",
    "주택임대차보호법",
    "주택임대차보호법 시행령",
    "민법",
    "이자제한법",
    "보증인 보호를 위한 특별법",
]


def http_get(url: str, timeout: int = 60) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "prep_contract/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def redact(s: str, oc: str) -> str:
    if not oc:
        return s
    return s.replace(oc, "<OC_REDACTED>")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    oc = os.environ.get("LAW_OC", "").strip()
    result: dict = {"oc_configured": bool(oc)}
    if not oc:
        result["status"] = "OC 미설정"
        result["note"] = "환경변수 LAW_OC 비어 있음. T3 전체 건너뜀."
        (PREP / "t3_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    LAW_DIR.mkdir(parents=True, exist_ok=True)
    result["laws"] = {}
    result["history_test"] = {}
    result["admin_rule_minwage"] = {}

    # Probe search API for 주택임대차보호법
    # DRF lawSearch.do
    q = urllib.parse.urlencode({
        "OC": oc,
        "target": "law",
        "type": "JSON",
        "query": "주택임대차보호법",
        "display": "10",
        "page": "1",
    })
    url = f"http://www.law.go.kr/DRF/lawSearch.do?{q}"
    status, body = http_get(url)
    result["probe_lawSearch"] = {
        "url_redacted": redact(url, oc),
        "http_status": status,
        "body_head": redact(body[:2000], oc),
    }

    if status != 200 or "오류" in body or "에러" in body or "승인" in body[:500]:
        result["status"] = "승인전_또는_오류"
        result["error_body"] = redact(body[:5000], oc)
        (PREP / "t3_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: result[k] for k in result if k != "error_body"}, ensure_ascii=False, indent=2))
        print("ERROR_BODY_HEAD:", redact(body[:500], oc))
        return 1

    # If search works, fetch each law service
    for name in LAWS:
        q = urllib.parse.urlencode({
            "OC": oc, "target": "law", "type": "JSON", "query": name, "display": "5", "page": "1",
        })
        st, bd = http_get(f"http://www.law.go.kr/DRF/lawSearch.do?{q}")
        entry = {"search_status": st, "search_body_head": redact(bd[:800], oc)}
        # try to parse MST/ID
        try:
            data = json.loads(bd)
            entry["search_json_keys"] = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        except Exception as e:
            entry["parse_error"] = f"{type(e).__name__}: {e}"
        # save raw search
        safe = name.replace(" ", "_")
        (LAW_DIR / f"{safe}_search.json").write_text(redact(bd, oc), encoding="utf-8")
        # attempt lawService by LM name
        q2 = urllib.parse.urlencode({"OC": oc, "target": "law", "type": "JSON", "LM": name})
        st2, bd2 = http_get(f"http://www.law.go.kr/DRF/lawService.do?{q2}")
        entry["service_status"] = st2
        entry["service_body_head"] = redact(bd2[:800], oc)
        (LAW_DIR / f"{safe}.json").write_text(redact(bd2, oc), encoding="utf-8")
        result["laws"][name] = entry

    # History / as-of date for 주택임대차보호법 2022-01-01
    # Common params in open.law.go.kr docs: efYd (시행일) — verify by call
    hist_attempts = []
    for params in [
        {"OC": oc, "target": "law", "type": "JSON", "LM": "주택임대차보호법", "efYd": "20220101"},
        {"OC": oc, "target": "law", "type": "JSON", "LM": "주택임대차보호법", "efYd": "2022-01-01"},
        {"OC": oc, "target": "law", "type": "JSON", "LM": "주택임대차보호법", "date": "20220101"},
        {"OC": oc, "target": "eflaw", "type": "JSON", "LM": "주택임대차보호법", "efYd": "20220101"},
    ]:
        qh = urllib.parse.urlencode(params)
        urlh = f"http://www.law.go.kr/DRF/lawService.do?{qh}"
        sth, bdh = http_get(urlh)
        hist_attempts.append({
            "params_keys": list(params.keys()),
            "url_redacted": redact(urlh, oc),
            "status": sth,
            "body_head": redact(bdh[:1000], oc),
        })
    result["history_test"]["attempts"] = hist_attempts
    result["history_test"]["doc_note"] = (
        "open.law.go.kr DRF 문서에서 시행일(efYd) 등 연혁 파라미터 존재 여부를 호출로 검증. "
        "문서 전문 오프라인 미보관 시 여기 호출 결과로만 판단."
    )

    # Admin rules: 최저임금 고시
    qad = urllib.parse.urlencode({
        "OC": oc, "target": "admrul", "type": "JSON", "query": "최저임금", "display": "20", "page": "1",
    })
    sta, bda = http_get(f"http://www.law.go.kr/DRF/lawSearch.do?{qad}")
    result["admin_rule_minwage"] = {
        "status": sta,
        "body_head": redact(bda[:3000], oc),
    }
    (LAW_DIR / "admin_minwage_search.json").write_text(redact(bda, oc), encoding="utf-8")

    result["status"] = "calls_completed"
    (PREP / "t3_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "oc_configured": True, "n_laws": len(result["laws"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
