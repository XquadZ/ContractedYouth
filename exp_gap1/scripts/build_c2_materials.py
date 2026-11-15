# -*- coding: utf-8 -*-
"""C2 고정 자료 블록 생성."""
from __future__ import annotations

import json
from pathlib import Path

EXP = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1")
DATA = EXP / "data"
RET = EXP / "retrieval"


def main():
    yak = (DATA / "law_yakgwan_6_14.txt").read_text(encoding="utf-8")
    # E1/E2 C2: 약관법 제6~14조 전문 전체
    c2_e12 = yak.strip()
    (RET / "c2_e1e2_material.txt").write_text(c2_e12, encoding="utf-8")

    labels = json.loads((DATA / "e3_labels.json").read_text(encoding="utf-8"))["labels"]
    defs = json.loads((DATA / "e3_label_defs.json").read_text(encoding="utf-8")).get("defs") or {}
    exemplars = json.loads((DATA / "e3_exemplars.json").read_text(encoding="utf-8"))
    empty_defs = all(not (defs.get(lb) or "").strip() for lb in labels)
    lines = []
    mode = "예시만" if empty_defs else "정의+예시"
    for lb in labels:
        d = (defs.get(lb) or "").strip()
        ex = (exemplars.get(lb) or {}).get("clause") or ""
        if d:
            lines.append(f"- {lb}: {d}\n  예시: {ex[:400]}")
        else:
            lines.append(f"- {lb}\n  예시: {ex[:400]}")
    material = "\n".join(lines)
    (RET / "c2_e3_material.txt").write_text(material, encoding="utf-8")
    (RET / "c2_e3_meta.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "empty_defs": empty_defs,
                "note": "사람 작성 필요" if empty_defs else "defs filled",
                "n_labels": len(labels),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # label list for prompts
    (RET / "e3_label_list.txt").write_text("\n".join(f"- {lb}" for lb in labels), encoding="utf-8")
    print("c2 e12 chars", len(c2_e12), "e3 mode", mode)


if __name__ == "__main__":
    main()
