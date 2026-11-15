# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

LAW = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\data_contract\law_api\현행")
OUT = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\app_rag\criteria\_extract")
OUT.mkdir(parents=True, exist_ok=True)


def collect(node, acc, parent_jo=None):
    if isinstance(node, dict):
        jo = node.get("조문번호") or parent_jo
        title = node.get("조문제목") or ""
        if node.get("조문내용"):
            acc.append(
                {
                    "jo": str(jo or ""),
                    "hang": "",
                    "ho": "",
                    "title": str(title),
                    "body": str(node["조문내용"]).strip(),
                }
            )
        if node.get("항내용"):
            acc.append(
                {
                    "jo": str(jo or ""),
                    "hang": str(node.get("항번호") or ""),
                    "ho": "",
                    "title": str(title),
                    "body": str(node["항내용"]).strip(),
                }
            )
        if node.get("호내용"):
            acc.append(
                {
                    "jo": str(jo or ""),
                    "hang": str(node.get("항번호") or ""),
                    "ho": str(node.get("호번호") or ""),
                    "title": str(title),
                    "body": str(node["호내용"]).strip(),
                }
            )
        for v in node.values():
            collect(v, acc, jo)
    elif isinstance(node, list):
        for x in node:
            collect(x, acc, parent_jo)


def load(fname: str):
    data = json.loads((LAW / fname).read_text(encoding="utf-8"))
    acc = []
    collect(data, acc)
    return acc, fname


def by_jo(arts, jo: str):
    return [a for a in arts if a["jo"] == str(jo)]


def format_article(arts, jo: str) -> str:
    rows = by_jo(arts, jo)
    if not rows:
        return ""
    parts = []
    for r in rows:
        # skip bare title-only duplicate if longer hang exists? keep all unique bodies
        if r["body"] not in parts:
            parts.append(r["body"])
    return "\n".join(parts)


def main():
    labor, lf = load("근로기준법_body_MST.json")
    decree, df = load("근로기준법 시행령_body_MST.json")
    mw, mf = load("최저임금법_body_MST.json")
    mwd, mdf = load("최저임금법 시행령_body_MST.json")

    labor_jos = ["4", "11", "15", "17", "18", "20", "21", "22", "23", "26", "43", "50", "53", "54", "55", "56", "60", "67", "94"]
    decree_jos = ["2", "7", "8", "27", "30"]
    payload = {
        "files": {
            "labor": lf,
            "decree": df,
            "minwage": mf,
            "minwage_decree": mdf,
        },
        "labor": {j: by_jo(labor, j) for j in labor_jos},
        "labor_text": {j: format_article(labor, j) for j in labor_jos},
        "decree": {j: by_jo(decree, j) for j in decree_jos},
        "decree_text": {j: format_article(decree, j) for j in decree_jos},
        "minwage_text": {j: format_article(mw, j) for j in ["5", "6"]},
        "minwage_decree_text": {j: format_article(mwd, j) for j in ["3"]},
    }
    (OUT / "law_quotes_full.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 법령 원문 발췌", ""]
    for j in labor_jos:
        lines.append(f"## [법] 근로기준법 제{j}조 — 파일 `{lf}`")
        lines.append("```")
        lines.append(payload["labor_text"][j] or "(없음)")
        lines.append("```")
        lines.append("")
    for j in decree_jos:
        lines.append(f"## [법] 근로기준법 시행령 제{j}조 — 파일 `{df}`")
        lines.append("```")
        lines.append(payload["decree_text"][j] or "(없음)")
        lines.append("```")
        lines.append("")
    for j in ["5", "6"]:
        lines.append(f"## [법] 최저임금법 제{j}조 — 파일 `{mf}`")
        lines.append("```")
        lines.append(payload["minwage_text"][j] or "(없음)")
        lines.append("```")
        lines.append("")
    lines.append(f"## [법] 최저임금법 시행령 제3조 — 파일 `{mdf}`")
    lines.append("```")
    lines.append(payload["minwage_decree_text"]["3"] or "(없음)")
    lines.append("```")
    (OUT / "law_quotes_full.md").write_text("\n".join(lines), encoding="utf-8")

    print("art17_len", len(payload["labor_text"]["17"]))
    print("art54_len", len(payload["labor_text"]["54"]))
    print("art56_len", len(payload["labor_text"]["56"]))
    print("art11_len", len(payload["labor_text"]["11"]))
    print("decree7_len", len(payload["decree_text"]["7"]))
    print("mw5_len", len(payload["minwage_text"]["5"]))


if __name__ == "__main__":
    main()
