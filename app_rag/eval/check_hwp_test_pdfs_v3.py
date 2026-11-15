# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS_FIX2 확인: A-5 + 잘린문장/쪽번호/서명앞 위치."""
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
from build_hwp_test_pdfs_v3 import fill_placeholders  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs_v3"
MANIFEST = OUT_DIR / "manifest.json"
OFFICIAL = OUT_DIR / "lease_official_articles.json"
CHECK_MD = OUT / "test_hwp_pdfs_v3_check.md"
CHECK_JSON = OUT / "test_hwp_pdfs_v3_check.json"
PREVIEW = OUT / "test_hwp_pdfs_v3_preview"
FORBIDDEN = ["정답", "테스트", "toxic", "|---|"]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def overlap_ratio(needle: str, hay: str) -> float:
    n, h = norm(needle), norm(hay)
    if not n:
        return 1.0
    if n in h:
        return 1.0
    i = 0
    for ch in h:
        if i < len(n) and ch == n[i]:
            i += 1
    need = max(1, int(len(n) * 0.95))
    for start in range(0, max(0, len(n) - need) + 1):
        if n[start : start + need] in h:
            return len(n[start : start + need]) / len(n)
    return i / len(n)


def count_occurrences(needle: str, hay: str) -> int:
    n, h = norm(needle), norm(hay)
    if not n:
        return 1
    need = max(1, int(len(n) * 0.95))
    chunk = n[:need]
    return h.count(chunk)


def save_all_pages_png(pdf_path: Path, stem: str) -> int:
    import fitz

    doc = fitz.open(str(pdf_path))
    n = 0
    try:
        mat = fitz.Matrix(100 / 72, 100 / 72)
        for i in range(doc.page_count):
            pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
            pix.save(str(PREVIEW / f"{stem}_p{i+1}.png"))
            n += 1
    finally:
        doc.close()
    return n


def page_num_violations(pages: list[dict]) -> list[str]:
    bad = []
    for i, p in enumerate(pages, 1):
        t = p.get("text") or ""
        for m in re.finditer(r"(\d+)\s*/\s*(\d+)", t):
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                bad.append(f"p{i}:{a}/{b}")
    return bad


def extract_articles(text: str) -> dict[str, str]:
    flat = re.sub(r"[ \t\r]+", " ", text)
    pat = re.compile(r"제\s*([1-9]|1[0-5])\s*조\s*\([^)]+\)")
    matches = list(pat.finditer(flat))
    arts = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        key = f"제{num}조"
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        body = flat[start:end]
        for stop in ("특약사항", "별지1", "별지 1", "별지2", "중요확인사항", "계약갱신 거절"):
            j = body.find(stop)
            if j > 40:
                body = body[:j]
                break
        if key not in arts and len(body) > 30:
            arts[key] = body.strip()
    return arts


def main() -> None:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    official = json.loads(OFFICIAL.read_text(encoding="utf-8"))["official"]
    priv_path = OUT_DIR / "lease_official_articles_private.json"
    official_private = (
        json.loads(priv_path.read_text(encoding="utf-8"))["official"] if priv_path.exists() else {}
    )
    PREVIEW.mkdir(parents=True, exist_ok=True)
    rows = []
    lease_art_tables = {}
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
        gold_positions = []
        for s in segs:
            if is_meta(s) or s.get("label") not in ("toxic", "check", "safe"):
                continue
            filled = fill_placeholders(s.get("text") or "", dict(fake))
            occ = count_occurrences(filled, text)
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
                details.append({"segment_id": s.get("segment_id"), "occ": occ, "ratio": round(ratio, 3), "text40": filled[:40]})
            # position vs signature
            idx = norm(text).find(norm(filled)[: max(8, int(len(norm(filled)) * 0.5))])
            gold_positions.append((s.get("segment_id"), idx))

        # signature marker
        sig_idx = -1
        for kw in ("(서명)", "서명란", "임대인:", "채권자"):
            j = norm(text).find(norm(kw))
            # last signature-ish near end
        # use last occurrence of '서명'
        sig_idx = norm(text).rfind("서명")
        before_sig = True
        for sid, idx in gold_positions:
            if idx >= 0 and sig_idx >= 0 and idx > sig_idx:
                before_sig = False
                break

        bad = {k: text.count(k) for k in FORBIDDEN if k in text}
        if bad:
            forbid_hits.append({"doc_id": doc["doc_id"], "hits": bad})

        page_bad = page_num_violations(pages)
        stem = Path(doc["pdf"]).stem
        png_n = save_all_pages_png(pdf, stem)

        art_table = []
        if domain == "LEASE":
            arts = extract_articles(text)
            changed = {k for k, v in (doc.get("article_status") or {}).items() if v.get("status") == "정답 조각으로 바꿈"}
            use_off = official_private if "PRIVATE" in (doc.get("form") or "").upper() else official
            for n in range(1, 14):
                key = f"제{n}조"
                if key not in arts and key not in use_off:
                    continue
                body = arts.get(key, "")
                if key in changed:
                    status = "정답 조각으로 바꿈"
                else:
                    off = (use_off.get(key) or {}).get("text") or ""
                    # compare structure ignoring numbers/dates
                    def nv(s):
                        t = norm(s)
                        t = re.sub(r"\d{4}년\d{1,2}월\d{1,2}일", "DATE", t)
                        t = re.sub(r"\d{1,3}(?:,\d{3})+|\d{4,}", "NUM", t)
                        return t

                    if off and (nv(off)[:80] == nv(body)[:80] or overlap_ratio(off[:120], body) >= 0.9):
                        status = "공식 문구"
                    elif not body:
                        status = "다름"
                    else:
                        # if gold replaced but not in changed
                        status = "공식 문구" if overlap_ratio(off[:100], body) >= 0.85 else "다름"
                art_table.append({"art": key, "status": status})
            lease_art_tables[doc["doc_id"]] = art_table

        rows.append(
            {
                "doc_id": doc["doc_id"],
                "domain": domain,
                "kind": doc["kind"],
                "pdf": doc["pdf"],
                "pages": len(pages),
                "once": once,
                "zero": zero,
                "multi": multi,
                "forbid": bad,
                "page_num_bad": page_bad,
                "gold_before_sign": before_sig,
                "png_pages": png_n,
                "miss_sample": details[:5],
                "article_table": art_table,
            }
        )
        print(
            f"CHECK {doc['doc_id']} once={once} zero={zero} multi={multi} pages={len(pages)} "
            f"pagebad={page_bad} beforesig={before_sig} forbid={bad}",
            flush=True,
        )

    lines = [
        "# test_hwp_pdfs_v3 확인",
        "",
        "명령: `python eval/check_hwp_test_pdfs_v3.py`",
        f"- manifest: `{MANIFEST}`",
        f"- 미리보기: `{PREVIEW}`",
        "",
        "## 정답 조각 등장 (toxic/check/safe)",
        "",
        "| 도메인 | 종류 | doc_id | 한 번 | 0번 | 두 번+ | 쪽수 | 쪽번호위반 | 서명앞 |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['domain']} | {r['kind']} | {r['doc_id']} | {r['once']} | {r['zero']} | {r['multi']} | "
            f"{r['pages']} | {r['page_num_bad'] or '-'} | {r['gold_before_sign']} |"
        )

    lines += ["", "## 임대 조별 상태", ""]
    for did, table in lease_art_tables.items():
        lines.append(f"### {did}")
        lines.append("| 조 | 상태 |")
        lines.append("|---|---|")
        for a in table:
            lines.append(f"| {a['art']} | {a['status']} |")
        diff_n = sum(1 for a in table if a["status"] == "다름")
        lines.append(f"- 다름: {diff_n}")
        lines.append("")

    lines += [
        "## 금지 문자열",
        f"- 위반 문서 수: {len(forbid_hits)}",
    ]
    for f in forbid_hits:
        lines.append(f"  - {f}")

    CHECK_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    CHECK_JSON.write_text(
        json.dumps({"rows": rows, "lease_art_tables": lease_art_tables, "forbid_hits": forbid_hits}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("WROTE", CHECK_MD)
    print("WROTE", CHECK_JSON)


if __name__ == "__main__":
    main()
