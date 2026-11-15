# -*- coding: utf-8 -*-
"""계약서 파일 → 텍스트. 원문은 호출자가 메모리에서만 다루며 이 모듈은 디스크에 쓰지 않는다."""
from __future__ import annotations

import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_BYTES = 10 * 1024 * 1024
SCAN_CHARS_PER_PAGE = 50


class ExtractError(ValueError):
    pass


def extract_bytes(data: bytes, filename: str) -> dict:
    if not data:
        raise ExtractError("파일이 비어 있습니다.")
    if len(data) > MAX_BYTES:
        raise ExtractError("파일은 10MB 이하여야 합니다.")
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return _pdf(data)
    if name.endswith(".hwpx"):
        return _hwpx(data)
    if name.endswith(".hwp"):
        return _hwp(data)
    if name.endswith(".txt") or _looks_text(data):
        return _txt(data)
    raise ExtractError("지원 형식: PDF, HWP, HWPX, TXT")


def locate_quotes_pdf(data: bytes, quotes: list[str]) -> dict:
    """PDF에서 인용 문자열 위치(%). 디스크 저장 없음."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    found = 0
    items = []
    try:
        for raw in quotes:
            q = (raw or "").strip()
            if not q:
                continue
            hit = _search_doc(doc, q)
            if hit:
                found += 1
            items.append({"quote": q[:80], "found": bool(hit), "rects": hit or []})
    finally:
        doc.close()
    total = len(items)
    return {
        "n_quotes": total,
        "n_found": found,
        "ratio": (found / total) if total else 0.0,
        "items": items,
    }


def _search_doc(doc, quote: str) -> list[dict]:
    """인용문 → 30/20/15/10자, 공백 정규화본. 실패 시 페이지 텍스트에서 공통 부분으로 재시도."""
    import re

    raw = (quote or "").strip()
    spaced = re.sub(r"\s+", " ", raw)
    needles = []
    for src in (raw, spaced):
        for n in (30, 20, 15, 10):
            piece = src[:n].strip()
            if len(piece) >= 2 and piece not in needles:
                needles.append(piece)
    for needle in needles:
        rects = _search_needle(doc, needle)
        if rects:
            return rects

    # 추출 텍스트에 있는 최장 공통 연속 구간(공백 무시)으로 바늘 재구성
    norm_q = re.sub(r"\s+", "", raw)
    if len(norm_q) < 8:
        return []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_text = page.get_text("text") or ""
        norm_p = re.sub(r"\s+", "", page_text)
        best = ""
        for length in (30, 24, 18, 12):
            if len(norm_q) < length:
                continue
            for start in range(0, min(40, len(norm_q) - length + 1), 3):
                frag = norm_q[start : start + length]
                if frag in norm_p:
                    # 페이지 원문에서 공백 포함 바늘 복원
                    restored = _restore_spaced_fragment(page_text, frag)
                    if restored and len(restored) >= 6:
                        rects = _search_needle(doc, restored[:30], only_page=page_index)
                        if rects:
                            return rects
                        best = restored
            if best:
                break
    return []


def _restore_spaced_fragment(page_text: str, compact_frag: str) -> str:
    """compact_frag가 page_text의 공백 제거본에 있을 때, 대응되는 원문 구간을 돌려준다."""
    import re

    if not compact_frag:
        return ""
    chars = []
    mapping = []  # compact index -> page_text index
    for i, ch in enumerate(page_text):
        if not ch.isspace():
            mapping.append(i)
            chars.append(ch)
    joined = "".join(chars)
    j = joined.find(compact_frag)
    if j < 0:
        return ""
    a = mapping[j]
    b = mapping[j + len(compact_frag) - 1] + 1
    return re.sub(r"\s+", " ", page_text[a:b]).strip()


def _search_needle(doc, needle: str, only_page: int | None = None) -> list[dict]:
    needle = (needle or "").strip()
    if len(needle) < 2:
        return []
    rects = []
    pages = range(doc.page_count) if only_page is None else [only_page]
    for page_index in pages:
        page = doc.load_page(page_index)
        pw = page.rect.width or 1
        ph = page.rect.height or 1
        for r in page.search_for(needle):
            rects.append(
                {
                    "page": page_index + 1,
                    "x": round(r.x0 / pw * 100, 4),
                    "y": round(r.y0 / ph * 100, 4),
                    "width": round((r.x1 - r.x0) / pw * 100, 4),
                    "height": round((r.y1 - r.y0) / ph * 100, 4),
                }
            )
    return rects


def _pdf(data: bytes) -> dict:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    try:
        for i in range(doc.page_count):
            text = doc.load_page(i).get_text("text") or ""
            pages.append({"page": i + 1, "text": text})
    finally:
        doc.close()
    chars = sum(len(p["text"]) for p in pages)
    n = max(len(pages), 1)
    scanned = chars < SCAN_CHARS_PER_PAGE * n
    return {"pages": pages, "chars": chars, "kind": "pdf", "scanned": scanned}


def _txt(data: bytes) -> dict:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        text = data.decode("utf-8", errors="replace")
    return {"pages": [{"page": 1, "text": text}], "chars": len(text), "kind": "txt", "scanned": False}


def _looks_text(data: bytes) -> bool:
    sample = data[:2000]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            sample.decode("cp949")
            return True
        except UnicodeDecodeError:
            return False


def _hwpx(data: bytes) -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExtractError("HWPX(zip)를 열 수 없습니다.") from exc
    parts = []
    names = sorted(n for n in zf.namelist() if re.search(r"Contents/section\d+\.xml$", n.replace("\\", "/")))
    if not names:
        names = sorted(n for n in zf.namelist() if n.lower().endswith(".xml") and "section" in n.lower())
    for name in names:
        raw = zf.read(name)
        parts.append(_xml_text(raw))
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise ExtractError("HWPX에서 텍스트를 찾지 못했습니다.")
    return {"pages": [{"page": 1, "text": text}], "chars": len(text), "kind": "hwpx", "scanned": False}


def _xml_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="ignore"))
    chunks = []
    for el in root.iter():
        if el.text and el.text.strip():
            chunks.append(el.text.strip())
        if el.tail and el.tail.strip():
            chunks.append(el.tail.strip())
    return " ".join(chunks)


def _hwp(data: bytes) -> dict:
    """hwp5txt는 파일 경로가 필요하므로 임시 파일만 쓰고 즉시 삭제한다."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        # 임시 파일 사용 지점 — 처리 직후 삭제 (아래 finally)
        proc = subprocess.run(
            ["hwp5txt", str(tmp_path)],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:200]
            raise ExtractError(f"hwp5txt 실패: {err or proc.returncode}")
        text = proc.stdout.decode("utf-8", errors="replace")
        if not text.strip():
            raise ExtractError("HWP 텍스트가 비어 있습니다.")
        return {"pages": [{"page": 1, "text": text}], "chars": len(text), "kind": "hwp", "scanned": False}
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
