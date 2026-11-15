# -*- coding: utf-8 -*-
"""4단계: 국토부 페이지 HTML 파싱 + PDF 시도. redirect loop 시 수동 필요로 기록."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

CASES = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\cases")
PAGE_URL = "https://www.molit.go.kr/USR/policyData/m_34681/dtl.jsp?id=4599"


def fetch_via_powershell(url: str, dest: Path) -> tuple[bool, str]:
    ps = f"""
$ProgressPreference='SilentlyContinue'
try {{
  $r = Invoke-WebRequest -Uri '{url}' -MaximumRedirection 5 -UseBasicParsing -TimeoutSec 60
  [System.IO.File]::WriteAllText('{str(dest).replace("'", "''")}', $r.Content, [System.Text.UTF8Encoding]::new($false))
  Write-Output ('OK ' + $r.StatusCode + ' ' + $r.RawContentLength)
}} catch {{
  Write-Output ('ERR ' + $_.Exception.Message)
}}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    return out.strip().startswith("OK"), out.strip()


def main():
    CASES.mkdir(parents=True, exist_ok=True)
    html_path = CASES / "_page_full.html"
    ok, msg = fetch_via_powershell(PAGE_URL, html_path)
    result = {
        "page_url": PAGE_URL,
        "fetch_ok": ok,
        "fetch_msg": msg,
        "manual_click_url": PAGE_URL,
    }
    if not html_path.exists():
        # fallback snip
        alt = CASES / "_page_snip.html"
        if alt.exists():
            html_path = alt
            result["used_fallback_html"] = str(alt)
        else:
            result["status"] = "수동 필요"
            result["error"] = "HTML 없음"
            (CASES / "s4_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(result)
            return

    text = html_path.read_text(encoding="utf-8", errors="replace")
    titles = re.findall(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
    pdf_hrefs = [h for h in hrefs if ".pdf" in h.lower() or "FileDown" in h or "fileDown" in h or "atch" in h.lower()]
    # also onclick / file name patterns
    pdf_mentions = list(dict.fromkeys(re.findall(r"([^<>\n\r]{0,120}\.pdf)", text, flags=re.I)))[:50]
    # Korean attachment area
    idx = text.find("첨부")
    around = text[max(0, idx - 300) : idx + 2500] if idx >= 0 else ""
    # common molit file download pattern: /common/fileDownload.do?...
    file_downs = re.findall(r'["\']([^"\']*fileDownload[^"\']*)["\']', text, flags=re.I)
    file_downs += re.findall(r'["\']([^"\']*FileDown[^"\']*)["\']', text, flags=re.I)

    result.update({
        "title": re.sub(r"\s+", " ", titles[0]).strip() if titles else None,
        "pdf_hrefs": pdf_hrefs[:40],
        "file_download_hrefs": list(dict.fromkeys(file_downs))[:40],
        "pdf_mentions": pdf_mentions,
        "around_attach_html": around[:3000],
        "has_keywords": {
            "임대차": "임대차" in text,
            "분쟁조정": "분쟁조정" in text or "분쟁 조정" in text,
            "사례집": "사례집" in text,
        },
    })

    downloads = []
    candidates = list(dict.fromkeys(pdf_hrefs + file_downs))
    for h in candidates:
        if h.startswith("//"):
            url = "https:" + h
        elif h.startswith("/"):
            url = "https://www.molit.go.kr" + h
        elif h.startswith("http"):
            url = h
        else:
            url = "https://www.molit.go.kr/" + h.lstrip("./")
        if "molit.go.kr" not in url and "moj.go.kr" not in url:
            continue
        # try powershell download
        name = Path(url.split("?")[0]).name or "molit_case.pdf"
        if not name.lower().endswith(".pdf"):
            name = "molit_attach_" + str(len(downloads) + 1) + ".bin"
        dest = CASES / name
        ps = f"""
$ProgressPreference='SilentlyContinue'
try {{
  Invoke-WebRequest -Uri '{url}' -OutFile '{str(dest).replace("'", "''")}' -MaximumRedirection 5 -UseBasicParsing -TimeoutSec 120 -Headers @{{'Referer'='{PAGE_URL}'}}
  Write-Output ('OK ' + (Get-Item '{str(dest).replace("'", "''")}').Length)
}} catch {{ Write-Output ('ERR ' + $_.Exception.Message) }}
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        msg2 = (r.stdout or "").strip()
        ok2 = msg2.startswith("OK") and dest.exists()
        item = {"url": url, "ok": ok2, "msg": msg2, "path": str(dest) if dest.exists() else None}
        if ok2:
            data = dest.read_bytes()[:5]
            item["is_pdf"] = data.startswith(b"%PDF")
            item["bytes"] = dest.stat().st_size
            if not item["is_pdf"]:
                item["ok"] = False
                item["error"] = "not a PDF magic header"
                # peek
                try:
                    item["head_text"] = dest.read_text(encoding="utf-8", errors="replace")[:300]
                except Exception:
                    pass
            else:
                try:
                    import pdfplumber
                    with pdfplumber.open(dest) as pdf:
                        item["n_pages"] = len(pdf.pages)
                        t0 = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:4])
                        item["text_head_300"] = t0[:300]
                        full15 = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:15])
                        markers = re.findall(r"사례\s*\d+", full15)
                        item["toc_case_markers_first15pages"] = len(markers)
                        m = re.search(r"(사례\s*\d+[^\n]{0,100})", full15)
                        item["first_case_title_guess"] = m.group(1) if m else None
                except Exception as e:
                    item["pdf_parse_error"] = repr(e)
        downloads.append(item)

    result["downloads"] = downloads
    if any(d.get("ok") and d.get("is_pdf") for d in downloads):
        result["status"] = "downloaded"
    elif candidates:
        result["status"] = "수동 필요"
        result["reason"] = "첨부 링크 후보는 있으나 자동 다운로드 실패 또는 PDF 아님"
    else:
        result["status"] = "수동 필요"
        result["reason"] = "페이지 HTML에서 PDF/fileDownload 링크를 추출하지 못함. 브라우저에서 직접 클릭 필요."

    (CASES / "s4_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", result["status"], "n_candidates", len(candidates), "downloads", downloads)
    # also write human note
    (CASES / "MANUAL_URL.txt").write_text(
        f"수동 다운로드 URL:\n{PAGE_URL}\n\nstatus={result['status']}\nreason={result.get('reason')}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
