# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS_FIX A-5: v2 PDF 추출·한 번 등장·금지어·쪽수·전체 PNG."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.extract import extract_bytes  # noqa: E402
from rag.paths import OUT, GOLD  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from splitutil import clean_twin_path  # noqa: E402
from dev_eval import is_meta  # noqa: E402
from build_hwp_test_pdfs_v2 import fill_placeholders  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs_v2"
MANIFEST = OUT_DIR / "manifest.json"
CHECK_MD = OUT / "test_hwp_pdfs_v2_check.md"
CHECK_JSON = OUT / "test_hwp_pdfs_v2_check.json"
PREVIEW = OUT / "test_hwp_pdfs_v2_preview"

FORBIDDEN = ["정답", "테스트", "toxic", "|---|"]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def overlap_ratio(needle: str, hay: str) -> float:
    n = norm(needle)
    h = norm(hay)
    if not n:
        return 1.0
    if n in h:
        return 1.0
    i = 0
    for ch in h:
        if i < len(n) and ch == n[i]:
            i += 1
    need = max(1, int(len(n) * 0.95))
    if len(n) >= need:
        for start in range(0, len(n) - need + 1):
            chunk = n[start : start + need]
            if chunk in h:
                return len(chunk) / len(n)
    return i / len(n)


def count_occurrences(needle: str, hay: str) -> int:
    """공백 무시 후 needle이 hay에 몇 번 연속 등장하는지(겹침 허용 비탐욕)."""
    n = norm(needle)
    h = norm(hay)
    if not n or len(n) < 8:
        # 짧은 문장은 95% 창으로
        if not n:
            return 1
        need = max(1, int(len(n) * 0.95))
        chunk = n[:need]
        if not chunk:
            return 1
        return h.count(chunk)
    # 95% 길이 창 하나가 몇 번 나오는지
    need = max(1, int(len(n) * 0.95))
    chunk = n[:need]
    return h.count(chunk)


def save_all_pages_png(pdf_path: Path, stem: str) -> int:
    import fitz

    doc = fitz.open(str(pdf_path))
    n = 0
    try:
        # 100 dpi ≈ zoom 100/72
        mat = fitz.Matrix(100 / 72, 100 / 72)
        for i in range(doc.page_count):
            pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
            out = PREVIEW / f"{stem}_p{i+1}.png"
            pix.save(str(out))
            n += 1
    finally:
        doc.close()
    return n


def main() -> None:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    PREVIEW.mkdir(parents=True, exist_ok=True)
    rows = []
    forbid_hits = []

    for doc in man["docs"]:
        pdf = WORK / doc["pdf"]
        ex = extract_bytes(pdf.read_bytes(), pdf.name)
        pages = ex.get("pages") or []
        text = "\n".join(p.get("text") or "" for p in pages)
        domain = doc["domain"]
        rows_all = load_jsonl(GOLD[domain]["contract"])
        twin = clean_twin_path(domain)
        if twin.exists():
            rows_all = rows_all + load_jsonl(twin)
        segs = [r for r in rows_all if r.get("doc_id") == doc["doc_id"]]
        segs = sorted(
            segs,
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        fake = doc.get("fake_values") or {}
        once = zero = multi = 0
        details = []
        for s in segs:
            if is_meta(s):
                continue
            if s.get("label") not in ("toxic", "check", "safe"):
                continue
            filled = fill_placeholders(s.get("text") or "", dict(fake))
            occ = count_occurrences(filled, text)
            # also require overlap >= 0.95 for "present"
            ratio = overlap_ratio(filled, text)
            if ratio < 0.95:
                occ = 0
            if occ == 1:
                once += 1
            elif occ == 0:
                zero += 1
            else:
                multi += 1
            if occ != 1:
                details.append(
                    {
                        "segment_id": s.get("segment_id"),
                        "occ": occ,
                        "ratio": round(ratio, 3),
                        "text40": filled[:40],
                    }
                )

        bad = {k: text.count(k) for k in FORBIDDEN if k in text}
        if bad:
            forbid_hits.append({"doc_id": doc["doc_id"], "hits": bad})

        stem = Path(doc["pdf"]).stem
        png_n = save_all_pages_png(pdf, stem)

        rows.append(
            {
                "doc_id": doc["doc_id"],
                "domain": domain,
                "kind": doc["kind"],
                "pdf": doc["pdf"],
                "pages": len(pages),
                "chars": ex.get("chars"),
                "scanned": ex.get("scanned"),
                "once": once,
                "zero": zero,
                "multi": multi,
                "forbid": bad,
                "png_pages": png_n,
                "miss_sample": details[:5],
                "form": doc.get("form"),
            }
        )
        print(
            f"CHECK {doc['doc_id']} once={once} zero={zero} multi={multi} pages={len(pages)} png={png_n} forbid={bad}",
            flush=True,
        )

    lines = [
        "# test_hwp_pdfs_v2 확인",
        "",
        "명령: `python eval/check_hwp_test_pdfs_v2.py`",
        f"- manifest: `{MANIFEST}`",
        f"- 미리보기: `{PREVIEW}`",
        "",
        "## 정답 조각 등장 횟수 (toxic/check/safe, 공백 무시 ≥95%)",
        "",
        "| 도메인 | 종류 | doc_id | 한 번 | 0번 | 두 번 이상 | 쪽수 | PDF |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['domain']} | {r['kind']} | {r['doc_id']} | {r['once']} | {r['zero']} | {r['multi']} | {r['pages']} | `{r['pdf']}` |"
        )
    lines += [
        "",
        "## 금지 문자열",
        "",
        f"- 대상: {FORBIDDEN}",
        f"- 위반 문서 수: {len(forbid_hits)}",
    ]
    for f in forbid_hits:
        lines.append(f"  - {f['doc_id']}: {f['hits']}")
    lines += [
        "",
        "## 쪽수 참고",
        "- 근로 목표: 1~2쪽",
        "- 임대 목표: 원 양식 쪽수 ±1",
        "",
        "## 미매칭 샘플",
        "",
    ]
    for r in rows:
        if r["miss_sample"]:
            lines.append(f"- {r['doc_id']}: `{r['miss_sample']}`")
    if not any(r["miss_sample"] for r in rows):
        lines.append("- 없음")

    CHECK_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    CHECK_JSON.write_text(
        json.dumps(
            {"rows": rows, "forbid_hits": forbid_hits, "check_md": str(CHECK_MD)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("WROTE", CHECK_MD)
    print("WROTE", CHECK_JSON)


if __name__ == "__main__":
    main()
