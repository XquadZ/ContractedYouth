# -*- coding: utf-8 -*-
"""Merge G1–G6 partials, fix G3 verify, write MANUAL html + report."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_g1_g7 import MANUAL_ITEMS, write_after_manual, write_manual_html, add_manual  # noqa: E402
from build_report_g1_g7 import main as build_report  # noqa: E402

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
OUT = DC / "g1_g7_results.json"
G3P = DC / "g3_partial.json"
G46 = DC / "g4_g6_partial.json"


def article_full(j, art_no, title_hint=None):
    units = j["법령"]["조문"]["조문단위"]
    if isinstance(units, dict):
        units = [units]
    for u in units:
        if str(u.get("조문번호")) != str(art_no):
            continue
        if u.get("조문가지번호"):
            continue
        if title_hint and title_hint not in str(u.get("조문제목") or ""):
            continue
        parts = [str(u.get("조문내용") or "")]
        hang = u.get("항")
        if isinstance(hang, dict):
            hang = hang.get("항단위") or hang
        if isinstance(hang, dict):
            hang = [hang]
        if isinstance(hang, list):
            for h in hang:
                parts.append(str(h.get("항내용") or ""))
                ho = h.get("호") if isinstance(h, dict) else None
                if isinstance(ho, dict):
                    ho = ho.get("호단위") or ho
                if isinstance(ho, list):
                    for x in ho:
                        parts.append(str(x.get("호내용") or ""))
        return re.sub(r"\s+", " ", " ".join(parts)).strip()
    return ""


def fix_g3_verify(g3: dict) -> dict:
    bodies = DC / "law_api" / "연혁_g3" / "bodies"
    verify = {}
    for law_name, art_no, hint, label in [
        ("주택임대차보호법", "7", "증감", "제7조"),
        ("근로기준법", "17", "명시", "제17조"),
    ]:
        rows = []
        for ver in (g3.get("laws") or {}).get(law_name, {}).get("versions") or []:
            p = bodies / f"{law_name}_{ver['MST']}.json"
            text = ""
            if p.exists():
                j = json.loads(p.read_text(encoding="utf-8"))
                text = article_full(j, art_no, hint)
            rows.append({"시행일": ver.get("시행일"), "MST": ver.get("MST"), "조문텍스트": text})
        texts = [r["조문텍스트"] for r in rows if r["조문텍스트"]]
        verify[f"{law_name}_{label}"] = {
            "rows": rows,
            "changes_detected": len(set(texts)) > 1,
            "note": "2022-01-01 이후 법령명 완전일치 시행판이 1건이면 비교 대상 단일 행",
        }
    g3["verify"] = verify
    g3["lsHistory_status"] = {
        "ok": False,
        "error_text": "국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. … 법제처 공동활용 유지보수팀(02-2109-6446)",
        "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide",
    }
    return g3


def main():
    MANUAL_ITEMS.clear()
    result = {}
    if OUT.exists():
        result = json.loads(OUT.read_text(encoding="utf-8"))

    # G3
    if G3P.exists():
        g3 = json.loads(G3P.read_text(encoding="utf-8"))
        g3 = fix_g3_verify(g3)
        g3["_done"] = True
        result["G3"] = g3
        add_manual({
            "id": "g1_lsHistory",
            "title": "Open API target=lsHistory 승인 확인",
            "why": "법령 연혁 목록/본문 HTML API(lsHistory) — G3 연혁 판 목록 보조에 필요",
            "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
            "action": "마이페이지에서 target=lsHistory 승인 상태 확인",
            "dest": "승인 후 python data_contract\\scripts\\after_manual.py",
            "targets": ["lsHistory"],
        })

    # G4-G6
    if G46.exists():
        g46 = json.loads(G46.read_text(encoding="utf-8"))
        for k in ("G4", "G5", "G6"):
            if k in g46:
                result[k] = g46[k]
        for m in g46.get("manual") or []:
            if not any(x.get("id") == m.get("id") for x in MANUAL_ITEMS):
                MANUAL_ITEMS.append(m)

    # G1 manuals from probe
    probe = (result.get("G1") or {}).get("probe") or {}
    for tname, info in probe.items():
        tgt = tname.replace("_XML", "")
        if info.get("ok"):
            continue
        if info.get("unauthorized") or (info.get("kind") == "HTML" and "미신청" in (info.get("error_text") or "")):
            if not any(tgt in (m.get("targets") or []) for m in MANUAL_ITEMS):
                add_manual({
                    "id": f"g1_{tgt}",
                    "title": f"Open API target={tgt} 승인 확인",
                    "why": f"target={tgt} 권한 없음/실패",
                    "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
                    "action": f"open.law.go.kr 마이페이지에서 target={tgt} 승인 상태 확인",
                    "dest": "승인 후 python data_contract\\scripts\\after_manual.py",
                    "targets": [tgt],
                })

    # wait: if G2 not done, still merge what we have
    result["manual"] = MANUAL_ITEMS
    result["manual_count"] = len(MANUAL_ITEMS)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_after_manual()
    write_manual_html(MANUAL_ITEMS)
    build_report()
    print("merged manual", len(MANUAL_ITEMS), "G2_done", (result.get("G2") or {}).get("_done"))


if __name__ == "__main__":
    main()
