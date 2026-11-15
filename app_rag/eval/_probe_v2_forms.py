# -*- coding: utf-8 -*-
"""Probe LAB form page titles and LEASE article structure."""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

import win32com.client

WORK = Path(__file__).resolve().parents[2]
OUT = WORK / "datasets" / "test_hwp_pdfs_v2"
OUT.mkdir(parents=True, exist_ok=True)
APP = WORK / "app_rag"
sys.path.insert(0, str(APP))
from rag.extract import extract_bytes  # noqa: E402


def hwp_obj():
    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    try:
        hwp.SetMessageBoxMode(0x00010000)
    except Exception:
        pass
    return hwp


def save_pdf(hwp, path: Path):
    if path.exists():
        path.unlink()
    hwp.SaveAs(str(path), "PDF")
    for _ in range(50):
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(0.1)


def lab_pages():
    src = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
    tmp = OUT / "__lab_pages.hwp"
    pdf = OUT / "__lab_pages.pdf"
    shutil.copy2(src, tmp)
    hwp = hwp_obj()
    hwp.Open(str(tmp))
    save_pdf(hwp, pdf)
    hwp.Quit()
    ex = extract_bytes(pdf.read_bytes(), pdf.name)
    report = []
    for i, p in enumerate(ex["pages"], 1):
        t = p.get("text") or ""
        head = re.sub(r"\s+", " ", t[:200])
        titles = []
        for kw in (
            "단시간근로자 표준근로계약서",
            "연소근로자 표준근로계약서",
            "건설일용근로자",
            "기간의 정함이 있는 근로계약서",
            "표준근로계약서",
            "외국인근로자",
            "가사근로자",
        ):
            if kw in t.replace(" ", ""):
                titles.append(kw)
            elif kw in t:
                titles.append(kw)
        report.append({"page": i, "chars": len(t), "titles": titles, "head": head})
    (OUT / "__lab_pages.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LAB pages", len(report), "->", OUT / "__lab_pages.json")
    for r in report:
        print(r["page"], r["titles"], r["head"][:80])


def lease_articles():
    src = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts" / "MONTHLY_010.hwpx"
    tmp = OUT / "__lease_pages.hwpx"
    pdf = OUT / "__lease_pages.pdf"
    shutil.copy2(src, tmp)
    hwp = hwp_obj()
    hwp.Open(str(tmp))
    save_pdf(hwp, pdf)
    hwp.Quit()
    ex = extract_bytes(pdf.read_bytes(), pdf.name)
    arts = []
    for i, p in enumerate(ex["pages"], 1):
        t = p.get("text") or ""
        found = re.findall(r"제\s*\d+\s*조[^\n]{0,40}", t)
        arts.append({"page": i, "chars": len(t), "articles": found[:15]})
        print("LEASE p", i, "chars", len(t), "arts", found[:8])
    (OUT / "__lease_pages.json").write_text(json.dumps(arts, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    lab_pages()
    lease_articles()
