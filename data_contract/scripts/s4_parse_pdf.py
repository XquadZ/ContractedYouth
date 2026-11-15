# -*- coding: utf-8 -*-
"""4단계: 사례집 PDF 분석."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
CASES = ROOT / "data_contract" / "cases"
SRC_CANDIDATES = [
    CASES / "주택임대차분쟁조정사례집.pdf",
    *list((ROOT / "datasets").glob("*주택임대차*사례집*.pdf")),
    *list((ROOT / "datasets").glob("*분쟁조정*.pdf")),
]


def main():
    # prefer largest valid-looking pdf
    cands = [p for p in SRC_CANDIDATES if p.exists()]
    cands = sorted(cands, key=lambda p: p.stat().st_size, reverse=True)
    result = {"candidates": [{"path": str(p), "bytes": p.stat().st_size} for p in cands]}
    if not cands:
        result["status"] = "없음"
        (CASES / "s4_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("no pdf")
        return

    src = cands[0]
    dest = CASES / "주택임대차분쟁조정사례집.pdf"
    # if cases file is smaller/corrupt, copy from datasets (copy only, no delete/move of source)
    if src.resolve() != dest.resolve():
        if (not dest.exists()) or dest.stat().st_size < src.stat().st_size:
            shutil.copy2(src, dest)
            result["copied_from"] = str(src)
            result["copied_to"] = str(dest)
    pdf_path = dest if dest.exists() else src

    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        # extract text from early pages for TOC / first case
        early = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:30])
        full_markers = re.findall(r"사례\s*\d+", early)
        # broader patterns
        case_titles = re.findall(r"(사례\s*\d+\s*[^\n]{0,100})", early)
        # unique case numbers in whole doc (sample every page for count)
        nums = set()
        first_case_text = None
        first_case_title = None
        for i, pg in enumerate(pdf.pages):
            t = pg.extract_text() or ""
            for m in re.finditer(r"사례\s*(\d+)", t):
                nums.add(int(m.group(1)))
            if first_case_title is None:
                m = re.search(r"(사례\s*1[^\n]{0,120})", t)
                if m:
                    first_case_title = m.group(1).strip()
                    # collect following text from this and next pages
                    chunk = t[m.start():]
                    if i + 1 < n_pages:
                        chunk += "\n" + (pdf.pages[i + 1].extract_text() or "")
                    first_case_text = chunk[:300]

        result.update({
            "status": "parsed",
            "path": str(pdf_path),
            "bytes": pdf_path.stat().st_size,
            "n_pages": n_pages,
            "case_count_unique_markers": len(nums),
            "case_numbers_min_max": [min(nums), max(nums)] if nums else None,
            "toc_case_markers_first30pages": len(full_markers),
            "first_case_title": first_case_title,
            "first_case_text_head_300": first_case_text,
            "early_titles_sample": case_titles[:15],
            "text_head_300_doc": early[:300],
        })

    (CASES / "s4_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("pages", result.get("n_pages"), "cases", result.get("case_count_unique_markers"), "title", result.get("first_case_title"))


if __name__ == "__main__":
    main()
