# -*- coding: utf-8 -*-
"""T2: standard_forms 전체 추출 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PREP = ROOT / "prep_contract"
FORMS = ROOT / "standard_forms"
OUT_DIR = PREP / "t2_out"

sys.path.insert(0, str(PREP))
from extract import extract_file  # noqa: E402


def looks_like_table_missing(text: str, meta: dict, ext: str) -> str:
    """표 추출 여부 판정 문자열."""
    if meta.get("tables_found"):
        if meta.get("table_cell_count", 0) > 0 or meta.get("table_text_chars", 0) > 0:
            return "표 추출됨(셀/테이블 텍스트 감지)"
        if meta.get("tables_layout_hint"):
            return "표 가능(레이아웃 공백 힌트) — 셀 단위 확정 아님"
        return "표 태그/힌트 있음"
    # HWP often loses tables with crude extractors
    if ext == ".hwp" and meta.get("method") in ("olefile_crude", None):
        return "표 누락(가능) — hwp 조추출, 테이블 구조 미확인"
    if ext == ".hwp" and meta.get("method") == "hwp5txt":
        # without structure, uncertain
        if "\t" in text or text.count("  ") > 50:
            return "표 가능(공백/탭) — 구조 미확인"
        return "표 누락(가능) — hwp5txt 평문, 테이블 구조 없음"
    if ext == ".pdf" and meta.get("method") == "pdfplumber" and not meta.get("tables_found"):
        return "표 누락(pdfplumber tables 0)"
    if ext == ".hwpx" and not meta.get("tables_found"):
        return "표 누락(hwpx section xml에서 tbl/tc 미검출)"
    return "표 여부 미확인"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    if FORMS.exists():
        for ext in ("*.hwp", "*.hwpx", "*.pdf"):
            files.extend(FORMS.rglob(ext))
        # exclude _excluded? User said 전부 if exists — include all under standard_forms
        files = sorted({p.resolve() for p in files if p.is_file()})
    else:
        # fallback search
        files = []
    rows = []
    tool_status = {
        "hwp5txt": __import__("shutil").which("hwp5txt"),
        "pdftotext": __import__("shutil").which("pdftotext"),
    }
    try:
        import pdfplumber  # noqa
        tool_status["pdfplumber"] = True
    except Exception as e:
        tool_status["pdfplumber"] = f"False ({e})"
    try:
        import olefile  # noqa
        tool_status["olefile"] = True
    except Exception as e:
        tool_status["olefile"] = f"False ({e})"

    for path in files:
        rel = str(path.relative_to(ROOT)) if str(path).startswith(str(ROOT)) else str(path)
        rec = {
            "path": str(path),
            "rel": rel,
            "ext": path.suffix.lower(),
            "size": path.stat().st_size,
        }
        try:
            text, meta = extract_file(path)
            out_path = OUT_DIR / (path.stem + path.suffix.replace(".", "_") + ".txt")
            # avoid collisions
            i = 1
            while out_path.exists():
                out_path = OUT_DIR / f"{path.stem}_{i}{path.suffix.replace('.', '_')}.txt"
                i += 1
            out_path.write_text(text, encoding="utf-8")
            rec["ok"] = True
            rec["chars"] = len(text)
            rec["preview_300"] = text[:300]
            rec["meta"] = meta
            rec["table_status"] = looks_like_table_missing(text, meta, path.suffix.lower())
            rec["out"] = str(out_path)
        except Exception as e:
            rec["ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["chars"] = 0
            rec["preview_300"] = ""
            rec["table_status"] = "표 누락(추출 실패)"
        rows.append(rec)
        print(f"{'OK' if rec['ok'] else 'FAIL'} {rec['ext']} chars={rec.get('chars')} {rel}", flush=True)

    report = {"tool_status": tool_status, "n_files": len(files), "rows": rows}
    (PREP / "t2_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tool_status": tool_status, "n_files": len(files), "ok": sum(1 for r in rows if r["ok"]), "fail": sum(1 for r in rows if not r["ok"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
