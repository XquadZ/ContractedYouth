# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
LAW = WORK / "data_contract" / "law_api" / "현행"
OUT = WORK / "app_rag" / "criteria" / "_extract"
FORMS = WORK / "app_rag" / "criteria" / "_std_forms"
OUT.mkdir(parents=True, exist_ok=True)


def save_three_forms():
    raw = (FORMS / "_raw_all.txt").read_text(encoding="utf-8")
    # Split carefully: part-time form is broken by an inner <표>
    # Indefinite: first block after first <표>
    blocks = raw.split("<표>")
    # blocks[1]=indefinite, [2]=fixed, [3]=youth, [4]=consent, [5]=fixed-detailed?, [6]=part start, [7]=part rest
    indefinite = blocks[1].strip()
    fixed = blocks[2].strip()
    # reconstruct part-time from blocks 6+7
    part = (blocks[6] + "\n" + blocks[7]).strip() if len(blocks) > 7 else blocks[6].strip()
    # Prefer the clearly labeled part-time (초과근로에 대한 가산임금률)
    if "초과근로에 대한 가산임금률" not in part:
        # search all
        for b in blocks:
            if "초과근로에 대한 가산임금률" in b and "단시간근로자" in b:
                part = b.strip()
                break
        else:
            # stitch any block containing 가산임금률 with previous
            for i, b in enumerate(blocks):
                if "초과근로에 대한 가산임금률" in b:
                    part = (blocks[i - 1] + "\n" + b).strip() if i else b.strip()
                    break
    mapping = {
        "01_기간정함없음.txt": indefinite,
        "02_기간정함있음.txt": fixed,
        "03_단시간근로자.txt": part,
    }
    rows = []
    for fname, text in mapping.items():
        (FORMS / fname).write_text(text, encoding="utf-8")
        items = []
        for m in re.finditer(r"(?m)^(\d+)\.\s*(.+)$", text):
            title = re.split(r"\s{2,}", m.group(2).strip())[0].strip(" :")
            items.append((m.group(1), title))
        rows.append((fname, items, len(text)))
    lines = ["# 표준근로계약서 3종 항목", ""]
    for fname, items, n in rows:
        lines.append(f"## {fname} ({n}자)")
        lines.append("| 번호 | 항목 |")
        lines.append("|---|---|")
        for a, b in items:
            lines.append(f"| {a} | {b} |")
        lines.append("")
    (OUT / "forms_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return {k: v for k, v in mapping.items()}


def extract_jo(text: str, jo: str) -> str:
    """Extract article starting at 제N조 until next 제M조 or 부칙."""
    # patterns in MST JSON escaped
    pat = rf"제{jo}조(?:의\d+)?(?:\([^)]+\))?"
    # find in decoded content strings
    # Better: parse JSON and walk 조문내용
    return ""


def walk_jomun(node, acc):
    if isinstance(node, dict):
        body = node.get("조문내용")
        no = node.get("조문번호")
        title = node.get("조문제목") or ""
        yeobu = node.get("조문여부") or ""
        if body:
            acc.append({"no": str(no or ""), "title": str(title), "yeobu": str(yeobu), "body": str(body).strip()})
        for v in node.values():
            walk_jomun(v, acc)
    elif isinstance(node, list):
        for x in node:
            walk_jomun(x, acc)


def load_law(fname: str):
    data = json.loads((LAW / fname).read_text(encoding="utf-8"))
    acc = []
    walk_jomun(data, acc)
    return acc, fname


def pick(arts, numbers):
    out = {}
    for n in numbers:
        hits = [a for a in arts if a["no"] == n or a["no"].startswith(n + " ") or a["body"].startswith(f"제{n}조")]
        if not hits:
            hits = [a for a in arts if re.match(rf"^제{n}조", a["body"])]
        out[n] = hits
    return out


def byeolpyo_info(fname: str):
    data = json.loads((LAW / fname).read_text(encoding="utf-8"))
    raw = json.dumps(data, ensure_ascii=False)
    info = {
        "file": fname,
        "has_별표_key": "별표" in data.get("법령", {}) if isinstance(data.get("법령"), dict) else ("별표" in raw[:5000]),
        "별표_count": raw.count("별표"),
        "has_별표1_title": ("별표 1" in raw) or ("별표1" in raw),
        "has_본문_text_sample": None,
    }
    # try extract 별표 structure
    byeol = None
    if isinstance(data.get("법령"), dict):
        byeol = data["법령"].get("별표")
    info["별표_type"] = type(byeol).__name__ if byeol is not None else None
    if isinstance(byeol, dict):
        units = byeol.get("별표단위") or []
        titles = []
        bodies = []
        for u in units[:5]:
            if isinstance(u, dict):
                titles.append(u.get("별표제목") or u.get("별표키") or "")
                # any text body fields?
                for k, v in u.items():
                    if isinstance(v, str) and len(v) > 80 and "Download" not in v:
                        bodies.append(v[:200])
        info["titles"] = titles
        info["text_bodies_found"] = bodies
        info["has_본문_text_sample"] = bool(bodies)
    return info


def main():
    forms = save_three_forms()
    labor, lf = load_law("근로기준법_body_MST.json")
    decree, df = load_law("근로기준법 시행령_body_MST.json")
    mw, mf = load_law("최저임금법_body_MST.json")
    mwd, mdf = load_law("최저임금법 시행령_body_MST.json")

    labor_pick = pick(
        labor,
        ["11", "15", "17", "18", "20", "21", "22", "23", "26", "43", "50", "53", "54", "55", "56", "60", "67", "94", "4"],
    )
    decree_pick = pick(decree, ["7", "8", "27", "30", "2"])
    mw_pick = pick(mw, ["5", "6"])
    mwd_pick = pick(mwd, ["3", "5"])

    # also grab 제60조 subsections by body start
    labor_60 = [a for a in labor if a["no"].startswith("60") or a["body"].startswith("제60조")]
    labor_pick["60_all"] = labor_60

    payload = {
        "labor_file": lf,
        "decree_file": df,
        "minwage_file": mf,
        "minwage_decree_file": mdf,
        "labor": {k: [{"no": x["no"], "title": x["title"], "body": x["body"]} for x in v] for k, v in labor_pick.items()},
        "decree": {k: [{"no": x["no"], "title": x["title"], "body": x["body"]} for x in v] for k, v in decree_pick.items()},
        "minwage": {k: [{"no": x["no"], "title": x["title"], "body": x["body"]} for x in v] for k, v in mw_pick.items()},
        "minwage_decree": {k: [{"no": x["no"], "title": x["title"], "body": x["body"]} for x in v] for k, v in mwd_pick.items()},
        "byeol": byeolpyo_info("근로기준법 시행령_body_MST.json"),
        "form_chars": {k: len(v) for k, v in forms.items()},
        "form_heads": {k: v[:120] for k, v in forms.items()},
    }
    (OUT / "law_quotes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("forms", payload["form_chars"])
    print("byeol", payload["byeol"])
    print("labor17", bool(payload["labor"].get("17")))
    print("labor54", bool(payload["labor"].get("54")))
    for k, v in payload["labor"].items():
        if v:
            print("OK", k, "n", len(v), "body0", v[0]["body"][:60].replace("\n", " "))


if __name__ == "__main__":
    main()
