# -*- coding: utf-8 -*-
"""4단계: 국토부 주택임대차분쟁조정사례집 PDF."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

CASES = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\cases")
PAGE_URL = "https://www.molit.go.kr/USR/policyData/m_34681/dtl.jsp?id=4599"


def main():
    CASES.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    (CASES / "_page_full.html").write_bytes(raw)
    text = raw.decode("utf-8", "replace")

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
    pdf_hrefs = [h for h in hrefs if ".pdf" in h.lower() or "FileDown" in h or "fileDown" in h or "atchFile" in h]
    titles = re.findall(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    pdf_mentions = list(dict.fromkeys(re.findall(r"([^<>\n]{0,100}\.pdf)", text, flags=re.I)))[:40]
    idx = text.find("첨부")
    around = text[max(0, idx - 200) : idx + 2000] if idx >= 0 else text[:2000]

    result = {
        "page_url": PAGE_URL,
        "title": titles[0].strip() if titles else None,
        "pdf_hrefs": pdf_hrefs[:40],
        "pdf_mentions": pdf_mentions,
        "around_attach_html": around,
        "downloads": [],
        "status": None,
    }

    # absolutize and try download
    downloaded = []
    for h in pdf_hrefs:
        if h.startswith("//"):
            url = "https:" + h
        elif h.startswith("/"):
            url = "https://www.molit.go.kr" + h
        elif h.startswith("http"):
            url = h
        else:
            url = "https://www.molit.go.kr/" + h.lstrip("./")
        # only official molit/moj
        if not any(d in url for d in ("molit.go.kr", "moj.go.kr", "law.go.kr")):
            result.setdefault("skipped_nonofficial", []).append(url)
            continue
        name = Path(url.split("?")[0]).name or "download.pdf"
        if not name.lower().endswith(".pdf"):
            name = name + ".pdf"
        dest = CASES / name
        try:
            r2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": PAGE_URL})
            data = urllib.request.urlopen(r2, timeout=120).read()
            # if html, not pdf
            if data[:4] != b"%PDF" and b"<html" in data[:500].lower():
                downloaded.append({"url": url, "ok": False, "error": "HTML returned, not PDF", "head": data[:300].decode("utf-8", "replace")})
                continue
            dest.write_bytes(data)
            downloaded.append({"url": url, "ok": True, "path": str(dest), "bytes": len(data)})
        except Exception as e:
            downloaded.append({"url": url, "ok": False, "error": repr(e)})

    result["downloads"] = downloaded
    if any(d.get("ok") for d in downloaded):
        result["status"] = "downloaded"
        # try pdfplumber/pypdf for page count
        for d in downloaded:
            if not d.get("ok"):
                continue
            p = Path(d["path"])
            try:
                import pdfplumber
                with pdfplumber.open(p) as pdf:
                    d["n_pages"] = len(pdf.pages)
                    # first pages text
                    t0 = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:3])
                    d["text_head_300"] = t0[:300]
                    # crude case count from TOC
                    full = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:15])
                    cases = re.findall(r"(사례\s*\d+|【사례|사례\s*[0-9]+)", full)
                    d["toc_case_markers_first15pages"] = len(cases)
                    d["first_case_title_guess"] = None
                    m = re.search(r"(사례\s*\d+[^\n]{0,80})", full)
                    if m:
                        d["first_case_title_guess"] = m.group(1)
            except Exception as e:
                d["pdf_parse_error"] = repr(e)
    elif pdf_hrefs:
        result["status"] = "수동 필요 (링크는 있으나 자동 다운로드 실패)"
    else:
        result["status"] = "수동 필요 (페이지에서 PDF 링크 미추출)"
        result["manual_click_url"] = PAGE_URL

    (CASES / "s4_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", result["status"], "downloads", downloaded)
    print("WROTE", CASES / "s4_results.json")


if __name__ == "__main__":
    main()
