# -*- coding: utf-8 -*-
"""문서 → UTF-8 텍스트 추출 (hwp/hwpx/pdf)."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def extract_hwpx(path: Path) -> tuple[str, dict]:
    meta = {"tables_found": False, "method": "hwpx_zip_xml"}
    texts: list[str] = []
    table_texts: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        names = [n for n in zf.namelist() if re.search(r"Contents/section\d+\.xml$", n.replace("\\", "/"))]
        if not names:
            names = [n for n in zf.namelist() if "section" in n.lower() and n.endswith(".xml")]
        for name in sorted(names):
            raw = zf.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                # fallback strip tags
                txt = re.sub(rb"<[^>]+>", b" ", raw).decode("utf-8", errors="replace")
                texts.append(re.sub(r"\s+", " ", txt))
                continue
            # any table-like tags
            for elem in root.iter():
                tag = elem.tag.split("}")[-1].lower()
                if tag in ("tbl", "table", "tr", "tc", "cell"):
                    meta["tables_found"] = True
                if tag in ("t", "text") and elem.text:
                    texts.append(elem.text)
                # collect table cell text
                if tag in ("tc", "cell", "hp:tc"):
                    cell = "".join(elem.itertext()).strip()
                    if cell:
                        table_texts.append(cell)
            # also all text
            all_t = "".join(root.itertext())
            if all_t.strip():
                texts.append(all_t)
    body = "\n".join(t for t in texts if t and t.strip())
    if table_texts:
        meta["tables_found"] = True
        meta["table_cell_count"] = len(table_texts)
    meta["table_text_chars"] = sum(len(x) for x in table_texts)
    return body, meta


def extract_hwp(path: Path) -> tuple[str, dict]:
    meta: dict = {"method": None, "tables_found": False}
    # 1) hwp5txt
    hwp5txt = shutil.which("hwp5txt")
    if hwp5txt:
        r = subprocess.run([hwp5txt, str(path)], capture_output=True)
        # hwp5txt may output utf-8 or cp949
        out = r.stdout.decode("utf-8", errors="replace")
        if not out.strip():
            out = r.stdout.decode("cp949", errors="replace")
        meta["method"] = "hwp5txt"
        meta["returncode"] = r.returncode
        meta["stderr"] = (r.stderr.decode("utf-8", errors="replace") if r.stderr else "")[:500]
        # heuristic: tabs/| suggest table-ish
        if "\t" in out or re.search(r"\|.+\|", out):
            meta["tables_found"] = True
        if not out.strip() and r.returncode != 0:
            raise RuntimeError(f"hwp5txt failed rc={r.returncode}: {meta['stderr']}")
        return out, meta

    # 2) pyhwp module
    try:
        from hwp5.hwp5txt import main as hwp5_main  # type: ignore
        meta["method"] = "pyhwp_import_untested"
    except Exception:
        pass

    # 3) olefile crude (often fails for body text)
    try:
        import olefile
        meta["method"] = "olefile_crude"
        if not olefile.isOleFile(str(path)):
            raise RuntimeError("not OLE HWP")
        ole = olefile.OleFileIO(str(path))
        streams = []
        for s in ole.listdir():
            name = "/".join(s)
            if "BodyText" in name or "PrvText" in name:
                data = ole.openstream(s).read()
                # PrvText often utf-16le
                try:
                    streams.append(data.decode("utf-16le", errors="ignore"))
                except Exception:
                    streams.append(data.decode("utf-8", errors="ignore"))
        ole.close()
        text = "\n".join(streams)
        if not text.strip():
            raise RuntimeError("olefile extracted empty text")
        return text, meta
    except Exception as e:
        raise RuntimeError(f"hwp extract failed (no hwp5txt). last={type(e).__name__}: {e}")


def extract_pdf(path: Path) -> tuple[str, dict]:
    meta: dict = {"tables_found": False, "method": None}
    # pdftotext
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        r = subprocess.run([pdftotext, "-layout", str(path), "-"], capture_output=True)
        out = r.stdout.decode("utf-8", errors="replace")
        meta["method"] = "pdftotext"
        meta["returncode"] = r.returncode
        if re.search(r"(\S+\s+){3,}\S+", out) and ("  " in out or "\t" in out):
            # layout spaces may indicate columns/tables — not definitive
            meta["tables_layout_hint"] = True
        return out, meta

    try:
        import pdfplumber
        meta["method"] = "pdfplumber"
        parts = []
        table_cells = 0
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                parts.append(t)
                tables = page.extract_tables() or []
                if tables:
                    meta["tables_found"] = True
                    for tb in tables:
                        for row in tb:
                            for cell in row or []:
                                if cell and str(cell).strip():
                                    table_cells += 1
                                    parts.append(str(cell))
        meta["table_cell_count"] = table_cells
        return "\n".join(parts), meta
    except Exception as e:
        raise RuntimeError(f"pdf extract failed: {type(e).__name__}: {e}")


def extract_file(path: Path) -> tuple[str, dict]:
    ext = path.suffix.lower()
    if ext == ".hwpx":
        return extract_hwpx(path)
    if ext == ".hwp":
        return extract_hwp(path)
    if ext == ".pdf":
        return extract_pdf(path)
    if ext in (".txt", ".md", ".csv"):
        return path.read_text(encoding="utf-8", errors="replace"), {"method": "plaintext", "tables_found": False}
    raise RuntimeError(f"unsupported extension: {ext}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()
    path = args.input
    if not path.exists():
        print(f"NOT_FOUND {path}", file=sys.stderr)
        return 2
    try:
        text, meta = extract_file(path)
        out = args.output or path.with_suffix(path.suffix + ".extracted.txt")
        out.write_text(text, encoding="utf-8")
        print(json_dumps_safe({"ok": True, "chars": len(text), "out": str(out), "meta": meta}))
        return 0
    except Exception as e:
        print(json_dumps_safe({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1


def json_dumps_safe(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
