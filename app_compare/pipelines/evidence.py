# -*- coding: utf-8 -*-
"""RUN_REPORT.md 에서 비교 표에 넣을 수치를 읽는다. 숫자는 손으로 적지 않는다."""
from __future__ import annotations

import re
from pathlib import Path

REPORT = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\exp_v2\RUN_REPORT.md")


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start + len(heading) :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


def _rows(block: str) -> list[list[str]]:
    out = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):
            continue
        if cells[0] in ("모델", "대비", "check", "문항"):
            continue
        out.append(cells)
    return out


def _point(cell: str) -> str:
    if not cell:
        return ""
    match = re.search(r"[-+]?\d+\.\d+", cell)
    return match.group(0) if match else cell


def load() -> dict:
    text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    t3 = _rows(_section(text, "## 표 1."))
    t4 = _rows(_section(text, "## 표 2."))
    t2 = _rows(_section(text, "## T2"))
    num = _rows(_section(text, "## numeric / text"))

    def find(rows, name):
        for row in rows:
            if row and row[0] == name:
                return row
        return []

    q8b = find(t3, "Q8B")
    ax = find(t3, "AX7")
    rule = find(t3, "규칙(R) numeric")
    q8b_t4 = find(t4, "Q8B")
    q8bt_t4 = find(t4, "Q8B-T")
    t2_q = next((r for r in t2 if len(r) > 2 and r[0] == "Q8B" and r[1] == "A0"), [])
    t2_r = next((r for r in t2 if r and r[0].startswith("RoBERTa T2 seed 42")), [])
    ax_text = next((r for r in num if len(r) > 3 and r[0] == "AX7" and r[1] == "A1" and r[2] == "text"), [])
    return {
        "source": str(REPORT),
        "t2_q8b_a0": _point(t2_q[2]) if len(t2_q) > 2 else "",
        "t2_roberta42": _point(t2_r[2]) if len(t2_r) > 2 else "",
        "t3_q8b_a4bm25": _point(q8b[5]) if len(q8b) > 5 else "",
        "t3_ax7_a1": _point(ax[2]) if len(ax) > 2 else "",
        "t3_rule": _point(rule[1]) if len(rule) > 1 else "",
        "t3_ax7_a1_text": _point(ax_text[3]) if len(ax_text) > 3 else "",
        "t4_q8b_a4bm25": _point(q8b_t4[5]) if len(q8b_t4) > 5 else "",
        "t4_q8bt_a3": _point(q8bt_t4[4]) if len(q8bt_t4) > 4 else "",
        "note": "실서비스의 조문 연결은 정답 조문을 모르므로 A1(정답만)보다 A2/A3(정답과 같은 slot의 다른 조문)에 가깝다. 재생 일치 검사의 oracle_slot=1 만 gold check 조문(A1)을 넣는다.",
    }
