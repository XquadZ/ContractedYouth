# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS 확인: 추출·가리기·첫 쪽 PNG. 모델/GPU 없음."""
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
from rag.paths import OUT  # noqa: E402
from rag.pii import mask_pii  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs"
CHECK_MD = OUT / "test_hwp_pdfs_check.md"
PREVIEW = OUT / "test_hwp_pdfs_preview"
MANIFEST = OUT_DIR / "manifest.json"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def overlap_ratio(needle: str, hay: str) -> float:
    """공백 무시 후, needle 글자가 hay에 연속 포함되면 1. 아니면 최장 공통 부분 근사."""
    n = norm(needle)
    h = norm(hay)
    if not n:
        return 1.0
    if n in h:
        return 1.0
    # sliding: fraction of needle chars found in order
    i = 0
    for ch in h:
        if i < len(n) and ch == n[i]:
            i += 1
    # also try chunk containment of 95% window
    need = max(1, int(len(n) * 0.95))
    if len(n) >= need:
        for start in range(0, len(n) - need + 1):
            chunk = n[start : start + need]
            if chunk in h:
                return len(chunk) / len(n)
    return i / len(n)


def first_page_png(pdf_path: Path, out_png: Path) -> bool:
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        try:
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            out_png.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(out_png))
            return out_png.exists()
        finally:
            doc.close()
    except Exception as exc:
        print("PNG fail", pdf_path.name, exc)
        return False


def colonless_name_hits(text: str) -> list[str]:
    """'임대인 ○○○과' 형태 등 콜론 없는 이름 후보."""
    pats = [
        r"(임대인|임차인|사업주|근로자|채권자|채무자|보증인)\s*([가-힣]{2,4})(?=\s*(?:과|와|은|는|이|가|\())",
    ]
    found = []
    for p in pats:
        for m in re.finditer(p, text or ""):
            found.append(m.group(0))
    return found


def main() -> None:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    PREVIEW.mkdir(parents=True, exist_ok=True)
    rows = []
    pii_rows = []
    colonless_unmasked = 0
    colonless_total = 0

    for doc in man["docs"]:
        pdf = WORK / doc["pdf"]
        data = pdf.read_bytes()
        ex = extract_bytes(data, pdf.name)
        text = "\n".join(p.get("text") or "" for p in (ex.get("pages") or []))
        # gold texts from placements — reload filled from manifest places only has place;
        # use fake applied by reading segment texts from selection? Better: re-read gold and apply fake_values
        # For check, use text as stored in HWP via placements count vs extract.
        # Reconstruct expected texts from original jsonl + fake_values
        from splitutil import clean_twin_path, load_split_ids, SPLIT_FILE_V2
        from recall_dev import load_jsonl
        from rag.paths import GOLD
        from build_hwp_test_pdfs import fill_placeholders

        domain = doc["domain"]
        rows_all = load_jsonl(GOLD[domain]["contract"])
        twin = clean_twin_path(domain)
        if twin.exists():
            rows_all = rows_all + load_jsonl(twin)
        segs = [r for r in rows_all if r.get("doc_id") == doc["doc_id"]]
        segs = sorted(segs, key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""))
        fake = doc.get("fake_values") or {}
        found = 0
        total = 0
        miss = []
        for s in segs:
            total += 1
            filled = fill_placeholders(s.get("text") or "", dict(fake))
            ratio = overlap_ratio(filled, text)
            if ratio >= 0.95:
                found += 1
            else:
                miss.append({"segment_id": s.get("segment_id"), "ratio": round(ratio, 3), "text40": filled[:40]})
        rows.append(
            {
                "doc_id": doc["doc_id"],
                "domain": domain,
                "kind": doc["kind"],
                "pdf": doc["pdf"],
                "extract_chars": ex.get("chars"),
                "extract_kind": ex.get("kind"),
                "scanned": ex.get("scanned"),
                "found": found,
                "total": total,
                "ratio": f"{found}/{total}",
                "miss_n": len(miss),
                "miss_sample": miss[:3],
            }
        )

        masked, counts = mask_pii(text)
        # colonless names
        hits = colonless_name_hits(text)
        still = []
        for h0 in hits:
            colonless_total += 1
            # if still present identically in masked → not masked
            if h0 in masked:
                still.append(h0)
                colonless_unmasked += 1
        pii_rows.append(
            {
                "doc_id": doc["doc_id"],
                "counts": counts,
                "colonless_name_patterns": len(hits),
                "colonless_unmasked": len(still),
                "colonless_examples": still[:5],
            }
        )

        png = PREVIEW / f"{domain}_{doc['kind']}_{doc['doc_id']}_p1.png"
        first_page_png(pdf, png)
        print(f"CHECK {doc['doc_id']} {found}/{total} chars={ex.get('chars')} png={png.exists()}", flush=True)

    # markdown
    lines = []
    lines.append("# test_hwp_pdfs 확인")
    lines.append("")
    lines.append("명령: `python eval/check_hwp_test_pdfs.py`")
    lines.append(f"- manifest: `{MANIFEST}`")
    lines.append(f"- 미리보기: `{PREVIEW}`")
    lines.append("")
    lines.append("## 추출 확인 (공백 무시, 겹침 ≥95%)")
    lines.append("")
    lines.append("| 도메인 | 종류 | doc_id | 찾은/전체 | chars | scanned | PDF |")
    lines.append("|---|---|---|---|---:|---|---|")
    for r in rows:
        lines.append(
            f"| {r['domain']} | {r['kind']} | {r['doc_id']} | {r['ratio']} | {r['extract_chars']} | {r['scanned']} | `{r['pdf']}` |"
        )
    lines.append("")
    lines.append("## 가리기 확인 (rag/pii.py)")
    lines.append("")
    lines.append("| doc_id | name | phone | address | 콜론없는이름패턴 | 그중 미가림 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for p in pii_rows:
        c = p["counts"]
        lines.append(
            f"| {p['doc_id']} | {c.get('name',0)} | {c.get('phone',0)} | {c.get('address',0)} | {p['colonless_name_patterns']} | {p['colonless_unmasked']} |"
        )
    lines.append("")
    lines.append(
        f"- 콜론 없는 이름 패턴 총 {colonless_total}건 중 미가림 **{colonless_unmasked}**건 (고치지 않음, 보고만)."
    )
    lines.append("")
    lines.append("## 미확인/문제")
    bad = [r for r in rows if r["found"] < r["total"]]
    if not bad:
        lines.append("- 추출 누락 없음")
    else:
        for r in bad:
            lines.append(f"- {r['doc_id']}: 누락 {r['miss_n']} / 샘플 {r['miss_sample']}")
    if any(r.get("scanned") for r in rows):
        lines.append("- 스캔 PDF 감지됨")
    else:
        lines.append("- 스캔 PDF 아님(텍스트 PDF)")

    CHECK_MD.parent.mkdir(parents=True, exist_ok=True)
    CHECK_MD.write_text("\n".join(lines), encoding="utf-8")
    summary = {
        "extract": rows,
        "pii": pii_rows,
        "colonless_total": colonless_total,
        "colonless_unmasked": colonless_unmasked,
        "check_md": str(CHECK_MD),
    }
    (OUT / "test_hwp_pdfs_check.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", CHECK_MD)
    print("WROTE", OUT / "test_hwp_pdfs_check.json")


if __name__ == "__main__":
    main()
