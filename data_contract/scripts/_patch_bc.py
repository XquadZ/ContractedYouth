# -*- coding: utf-8 -*-
"""Patch B (현행 fallback) and C (PDF 시간급) into fix_abcdef_results.json."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
LAW = DC / "law_api"
OUT = DC / "fix_abcdef_results.json"
SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"
OC = os.environ["LAW_OC"]

LAWS_ZERO = ["최저임금법", "최저임금법 시행령", "이자제한법 제2조제1항의 최고이자율에 관한 규정"]


def redact(t: str) -> str:
    return re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", t or "")


def http_get(params, base=SEARCH):
    q = urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            t = raw.decode("utf-8", "replace")
            time.sleep(0.65)
            return t
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("http fail")


def patch_B(result):
    outd = LAW / "연혁_v2_exact"
    outd.mkdir(parents=True, exist_ok=True)
    B = result["B"]
    B.setdefault("note_현행_fallback", (
        "2022-01-01 이후 신규 시행판이 없는 법령은 현행(시행일<2022) 본문을 포함. "
        "해당 기간에 적용되는 동일 텍스트임."
    ))
    for name in LAWS_ZERO:
        t = http_get({"OC": OC, "target": "law", "type": "JSON", "query": name, "display": 20, "sort": "efdesc"})
        j = json.loads(t)
        items = []
        ls = j.get("LawSearch") or {}
        for v in ls.values():
            if isinstance(v, list):
                items.extend([x for x in v if isinstance(x, dict)])
            elif isinstance(v, dict) and "법령명한글" in v:
                items.append(v)
        exact = [it for it in items if it.get("법령명한글") == name]
        # prefer 현행
        exact.sort(key=lambda it: (0 if it.get("현행연혁코드") == "현행" else 1, it.get("시행일자") or ""))
        rows = []
        bodies = 0
        for it in exact[:3]:
            lid = str(it.get("법령일련번호") or "")
            if not lid:
                continue
            row = {
                "법령명한글": it.get("법령명한글"),
                "시행일": it.get("시행일자"),
                "공포일": it.get("공포일자"),
                "공포번호": it.get("공포번호") if not isinstance(it.get("공포번호"), dict) else str(it.get("공포번호")),
                "MST": lid,
                "현행연혁코드": it.get("현행연혁코드"),
                "제개정구분명": it.get("제개정구분명"),
                "note": "현행_fallback (2022 이후 신규 시행판 없음)",
            }
            tb = http_get({"OC": OC, "target": "law", "type": "JSON", "MST": lid}, SERVICE)
            if tb.strip().startswith("{") and name in tb:
                (outd / "bodies").mkdir(parents=True, exist_ok=True)
                (outd / "bodies" / f"{name}_{lid}.json").write_text(redact(tb), encoding="utf-8")
                bodies += 1
                row["body_type"] = "law_JSON_MST_현행"
            rows.append(row)
        B["laws"][name] = {
            "n_versions": len(rows),
            "bodies_ok": bodies,
            "table": rows,
            "sample_head_300": None,
            "fallback": True,
        }
        if rows and (outd / "bodies" / f"{name}_{rows[0]['MST']}.json").exists():
            B["laws"][name]["sample_head_300"] = (
                (outd / "bodies" / f"{name}_{rows[0]['MST']}.json").read_text(encoding="utf-8")[:300]
            )
        print("B patched", name, rows)


def patch_C(result):
    from pypdf import PdfReader

    C = result["C"]
    adir = LAW / "행정규칙" / "최저임금_v2"
    pdfdir = adir / "pdfs"
    pdfdir.mkdir(parents=True, exist_ok=True)
    for year in range(2022, 2027):
        info = C["years"].get(str(year)) or {}
        aid = info.get("ID")
        if not aid:
            continue
        t = http_get({"OC": OC, "target": "admrul", "type": "JSON", "ID": aid}, SERVICE)
        j = json.loads(t)
        svc = j.get("AdmRulService") or {}
        # try 제개정이유 first
        blob = json.dumps(svc.get("제개정이유") or {}, ensure_ascii=False) + "\n" + str(svc.get("조문내용") or "")
        m = re.search(rf"{year}[^\n]{{0,40}}시간급[^\d]{{0,15}}([\d,]+)\s*원", blob) or re.search(
            r"시간급[^\d]{0,20}([\d,]+)\s*원", blob
        )
        evidence = m.group(0) if m else None
        hourly = m.group(1) if m else None
        source = "제개정이유/조문내용"
        if not hourly:
            att = svc.get("첨부파일") or {}
            links = att.get("첨부파일링크") or []
            names = att.get("첨부파일명") or []
            if isinstance(links, str):
                links = [links]
            if isinstance(names, str):
                names = [names]
            for link, name in zip(links, names):
                if not str(name).lower().endswith(".pdf"):
                    continue
                if "서식" in name:
                    continue
                dest = pdfdir / f"{year}_{re.sub(r'[\\\\/:*?\"<>|]', '_', name)}"
                if not dest.exists():
                    urllib.request.urlretrieve(link, dest)
                text = "\n".join((p.extract_text() or "") for p in PdfReader(str(dest)).pages)
                (dest.with_suffix(dest.suffix + ".txt")).write_text(text, encoding="utf-8")
                m = re.search(r"시간급\s*모\s*든\s*산\s*업\s*([\d,]+)\s*원", text) or re.search(
                    r"시간급[^\d]{0,40}([\d,]+)\s*원", text
                )
                if m:
                    hourly = m.group(1)
                    # evidence sentence
                    m2 = re.search(r".{0,40}시간급.{0,40}" + re.escape(hourly) + r"\s*원.{0,40}", text)
                    evidence = (m2.group(0) if m2 else m.group(0)).replace("\n", " ")
                    source = f"첨부 PDF: {name}"
                    break
        C["years"][str(year)] = {
            **info,
            "ok": True,
            "hourly": hourly,
            "evidence": evidence,
            "evidence_source": source,
            "sample_head_300": redact(t)[:300],
        }
        print("C", year, hourly, source)


def main():
    result = json.loads(OUT.read_text(encoding="utf-8"))
    patch_B(result)
    patch_C(result)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("patched", OUT)


if __name__ == "__main__":
    main()
