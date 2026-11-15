# -*- coding: utf-8 -*-
"""FAIR_RERUN 2-4: dev 799조각·데모 PDF 가리기 전/후. LLM 없음."""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.extract import extract_bytes  # noqa: E402
from rag.pii import mask_pii  # noqa: E402
from rag.pii_v1 import mask_pii as mask_pii_v1  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402

OUT = APP / "out" / "quant_fair" / "mask_check.md"
DEMO = APP.parent / "datasets" / "demo_pdfs"


def _spans(before: str, after: str) -> list[tuple[str, str]]:
    sm = difflib.SequenceMatcher(a=before, b=after)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rows.append((before[i1:i2], after[j1:j2]))
    return rows


def _load_segments() -> list[dict]:
    rows = []
    for domain in ("LAB", "LEASE", "LOAN"):
        for doc in load_domain_docs(domain):
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                rows.append(
                    {
                        "domain": domain,
                        "doc_id": doc["doc_id"],
                        "segment_id": seg.get("segment_id"),
                        "label": seg.get("label") or "",
                        "text": seg.get("text") or "",
                    }
                )
    return rows


def main() -> None:
    segs = _load_segments()
    old_changed = []
    new_changed = []
    for seg in segs:
        raw = seg["text"]
        old, _ = mask_pii_v1(raw)
        new, counts = mask_pii(raw)
        if old != raw:
            old_changed.append(seg)
        if new != raw:
            new_changed.append({**seg, "masked": new, "counts": counts, "spans": _spans(raw, new)})

    lines = ["# mask_check", ""]
    lines.append(f"- 명령: `python -u -X utf8 eval/fair_mask_check.py`")
    lines.append(f"- 출력: `{OUT}`")
    lines.append(f"- dev 조각 수: {len(segs)}")
    lines.append(f"- 옛 가리기(pii_v1)로 바뀐 조각: {len(old_changed)} (문서에 적힌 266과 나란히)")
    lines.append(f"- 새 가리기로 바뀐 조각: {len(new_changed)}")
    lines.append("")
    lines.append("## 새 가리기 바뀐 곳 전부")
    lines.append("")
    if not new_changed:
        lines.append("바뀐 조각 없음.")
    for i, seg in enumerate(new_changed, 1):
        lines.append(f"### {i}. {seg['domain']} {seg['doc_id']} {seg['segment_id']} label={seg['label']} counts={seg['counts']}")
        lines.append("")
        lines.append("전:")
        lines.append("```")
        lines.append(seg["text"])
        lines.append("```")
        lines.append("후:")
        lines.append("```")
        lines.append(seg["masked"])
        lines.append("```")
        lines.append("차이:")
        for a, b in seg["spans"]:
            lines.append(f"- `{a}` → `{b}`")
        lines.append("")

    lines.append("## 데모 PDF")
    lines.append("")
    pdfs = sorted(DEMO.glob("*.pdf"))
    lines.append(f"- 디렉터리: `{DEMO}`")
    lines.append(f"- PDF {len(pdfs)}개")
    lines.append("")
    for path in pdfs:
        data = path.read_bytes()
        extracted = extract_bytes(data, path.name)
        pages = extracted.get("pages") or []
        joined = "\n".join(p.get("text") or "" for p in pages)
        masked, counts = mask_pii(joined)
        lines.append(f"### {path.name}")
        lines.append(f"- chars={extracted.get('chars')} scanned={extracted.get('scanned')} counts={counts}")
        if masked == joined:
            lines.append("- 바뀐 곳 없음")
        else:
            lines.append("전/후 차이:")
            for a, b in _spans(joined, masked):
                lines.append(f"- `{a}` → `{b}`")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("SEGS", len(segs), flush=True)
    print("OLD_CHANGED", len(old_changed), flush=True)
    print("NEW_CHANGED", len(new_changed), flush=True)
    print("PDFS", len(pdfs), flush=True)
    print("WROTE", OUT, flush=True)


if __name__ == "__main__":
    main()
