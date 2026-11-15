# -*- coding: utf-8 -*-
"""FINAL_TEST: test 조각 가리기 전/후. 모델 호출 없음."""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.pii import mask_pii  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402
from final_test_common import DOMAINS, QTEST  # noqa: E402


def _spans(before: str, after: str) -> list[tuple[str, str]]:
    sm = difflib.SequenceMatcher(a=before, b=after)
    return [(before[i1:i2], after[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def main() -> None:
    changed = []
    n = 0
    by_domain = {}
    keys = []
    for domain in DOMAINS:
        docs = load_domain_docs(domain, split="test")
        dn = 0
        for doc in docs:
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                raw = seg.get("text") or ""
                masked, counts = mask_pii(raw)
                n += 1
                dn += 1
                keys.append((domain, doc["doc_id"], seg.get("segment_id"), seg.get("label") or ""))
                if masked != raw:
                    changed.append(
                        {
                            "domain": domain,
                            "doc_id": doc["doc_id"],
                            "segment_id": seg.get("segment_id"),
                            "label": seg.get("label") or "",
                            "counts": counts,
                            "spans": _spans(raw, masked),
                            "before": raw,
                            "after": masked,
                        }
                    )
        by_domain[domain] = dn
    # 일반 단어 의심: name 카운트이면서 역할어 조사 패턴 등. 여기서는 spans의 before가
    # 전화·주민·계좌·이메일이 아닌데 *가 생기면 의심으로 표시.
    suspicious = []
    for row in changed:
        for a, b in row["spans"]:
            if "*" in b and not any(ch.isdigit() for ch in a) and "@" not in a:
                # 이름 칸(성명/이름/역할:)이면 OK로 본다
                head = row["before"][max(0, row["before"].find(a) - 8) : row["before"].find(a) + len(a)]
                if not any(k in head for k in ("성명", "이름", "임대인", "임차인", "근로자", "사업주", "채권자", "채무자", "보증인", "갑", "을", "대표자")):
                    suspicious.append({"domain": row["domain"], "doc_id": row["doc_id"], "segment_id": row["segment_id"], "a": a, "b": b})
    lines = [
        "# mask_check_test",
        "",
        "명령: `python -u -X utf8 eval/final_test_mask_check.py`",
        f"출력: `{QTEST / 'mask_check_test.md'}`",
        f"- test 조각 수: {n}",
        f"- 도메인별: {by_domain}",
        f"- 가리기로 바뀐 조각: {len(changed)}",
        f"- 일반 단어 의심(이름 칸·전화 등 아닌 *): {len(suspicious)}",
        "",
        "## 바뀐 곳",
        "",
    ]
    if not changed:
        lines.append("바뀐 조각 없음.")
    for i, row in enumerate(changed, 1):
        lines.append(f"### {i}. {row['domain']} {row['doc_id']} {row['segment_id']} label={row['label']} counts={row['counts']}")
        for a, b in row["spans"]:
            lines.append(f"- `{a}` → `{b}`")
        lines.append("")
    if suspicious:
        lines.append("## 일반 단어 의심")
        for s in suspicious:
            lines.append(f"- {s}")
    out = QTEST / "mask_check_test.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    keys_path = QTEST / "test_keys.json"
    keys_path.write_text(
        __import__("json").dumps({"n": n, "domains": by_domain, "keys": keys}, ensure_ascii=False),
        encoding="utf-8",
    )
    print("SEGS", n, "CHANGED", len(changed), "SUSPICIOUS", len(suspicious), flush=True)
    print("WROTE", out, flush=True)


if __name__ == "__main__":
    main()
