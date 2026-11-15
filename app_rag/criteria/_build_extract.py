# -*- coding: utf-8 -*-
"""Extract 3 standard forms + law snippets + toxic codes for LAB guide."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
CRIT = WORK / "app_rag" / "criteria"
FORMS = CRIT / "_std_forms"
LAW = WORK / "data_contract" / "law_api" / "현행"
OUT = CRIT / "_extract"


def split_forms(raw: str) -> list[str]:
    parts = re.split(r"<표>\s*", raw)
    return [p.strip() for p in parts if p.strip() and "근로계약을 체결한다" in p]


def classify(form: str) -> str | None:
    # order matters
    if "단시간" in form or "시간외 근로수당" in form and "해당자에 한함" in form:
        # part-time form has overtime allowance lines and 해당자에 한함 on 주휴
        if "시간외 근로수당" in form and "주휴일은 1주간" in form:
            return "part_time"
    if "근로계약기간" in form and "년   월   일부터      년" in form:
        # fixed term - has end date field as primary item 1
        if form.lstrip().startswith("1. 근로계약기간"):
            return "fixed_term"
    if "근로개시일" in form and "근로계약기간을 정하는 경우에는" not in form[:200]:
        # indefinite - first form style
        if form.lstrip().startswith("1. 근로개시일") and "취직인허증" not in form:
            return "indefinite"
    # youth form has 가족관계증명서
    if "가족관계증명서" in form or "취직인허증" in form:
        return "youth"
    if "건설일용" in form or "일용" in form:
        return "daily"
    return "other"


def item_table(form: str) -> list[tuple[str, str]]:
    items = []
    for m in re.finditer(r"(?m)^(\d+)\.\s*(.+)$", form):
        num, title = m.group(1), m.group(2).strip()
        # title up to first newline already; strip trailing colon blanks
        title = re.split(r"\s{2,}|\n", title)[0].strip(" :")
        items.append((num, title))
    return items


def load_mst(name_substr: str) -> dict:
    files = [p for p in LAW.iterdir() if name_substr in p.name and p.name.endswith("_body_MST.json")]
    if not files:
        raise FileNotFoundError(name_substr)
    # prefer exact law over decree when both match? caller passes distinct
    data = json.loads(files[0].read_text(encoding="utf-8"))
    return {"path": files[0].name, "data": data}


def flatten_articles(mst: dict) -> list[dict]:
    """Best-effort flatten common law.go.kr MST shapes."""
    out = []

    def walk(node, path=""):
        if isinstance(node, dict):
            jo = node.get("조문번호") or node.get("조번호") or node.get("항번호")
            title = node.get("조문여부") or node.get("조문제목") or ""
            body = node.get("조문내용") or node.get("항내용") or node.get("호내용") or ""
            if body and (jo or "조문내용" in node):
                out.append(
                    {
                        "no": str(jo or ""),
                        "title": str(title or ""),
                        "body": str(body).strip(),
                        "keys": list(node.keys())[:12],
                    }
                )
            for v in node.values():
                walk(v, path)
        elif isinstance(node, list):
            for x in node:
                walk(x, path)

    walk(mst)
    return out


def find_article(arts: list[dict], want: str) -> dict | None:
    # want like "17" or "54" or "별표"
    for a in arts:
        no = a["no"].replace(" ", "")
        if no == want or no.startswith(want + "(") or no == f"제{want}조":
            return a
        if want in a["body"][:30] and "별표" in want:
            return a
    # fallback contains
    for a in arts:
        if f"제{want}조" in (a["body"][:40] + a["no"]):
            return a
    return None


def toxic_codes() -> list[tuple[str, str]]:
    path = WORK / "datasets" / "work" / "v3_1" / "02_법률근거.jsonl"
    codes = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        for c in o.get("toxic_code") or []:
            vn = o.get("violation_name") or ""
            if c not in codes:
                codes[c] = vn
    return sorted(codes.items())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = (FORMS / "_raw_all.txt").read_text(encoding="utf-8")
    forms = split_forms(raw)
    classified = []
    for i, f in enumerate(forms):
        kind = classify(f)
        classified.append((i, kind, f))
        (OUT / f"form_{i}_{kind or 'unk'}.txt").write_text(f, encoding="utf-8")

    # pick three
    by = {k: f for _, k, f in classified if k}
    mapping = {
        "indefinite": "01_기간정함없음.txt",
        "fixed_term": "02_기간정함있음.txt",
        "part_time": "03_단시간근로자.txt",
    }
    summary = []
    for key, fname in mapping.items():
        if key not in by:
            summary.append(f"MISSING {key}")
            continue
        text = by[key]
        (FORMS / fname).write_text(text, encoding="utf-8")
        items = item_table(text)
        summary.append(f"## {key} -> {fname}")
        for n, t in items:
            summary.append(f"| {n} | {t} |")
        summary.append("")

    (OUT / "forms_summary.md").write_text("\n".join(summary), encoding="utf-8")
    (OUT / "classified.json").write_text(
        json.dumps([{"i": i, "kind": k, "chars": len(f), "head": f[:80]} for i, k, f in classified], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # laws
    for label, sub in [
        ("labor", "근로기준법_body_MST"),
        ("labor_decree", "근로기준법 시행령_body_MST"),
        ("minwage", "최저임금법_body_MST"),
        ("minwage_decree", "최저임금법 시행령_body_MST"),
    ]:
        files = [p for p in LAW.iterdir() if p.name.startswith(sub.replace("_body_MST", "")) and p.name.endswith("_body_MST.json")]
        # more reliable: exact
        files = list(LAW.glob(f"*{label}*"))  # may fail
    # direct names from listing
    name_map = {
        "labor": "근로기준법_body_MST.json",
        "labor_decree": "근로기준법 시행령_body_MST.json",
        "minwage": "최저임금법_body_MST.json",
        "minwage_decree": "최저임금법 시행령_body_MST.json",
    }
    snippets = {}
    for key, fname in name_map.items():
        p = LAW / fname
        data = json.loads(p.read_text(encoding="utf-8"))
        arts = flatten_articles(data)
        (OUT / f"{key}_articles.json").write_text(
            json.dumps([{"no": a["no"], "title": a["title"], "body": a["body"][:500]} for a in arts[:80]], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        snippets[key] = {"file": fname, "n": len(arts), "arts": arts}
        # search byeolpyo
        byeol = [a for a in arts if "별표" in (a["no"] + a["title"] + a["body"][:80])]
        (OUT / f"{key}_byeol.json").write_text(json.dumps(byeol[:20], ensure_ascii=False, indent=2), encoding="utf-8")

    # pull key articles from labor
    want_nums = ["11", "15", "17", "18", "20", "21", "22", "23", "26", "43", "50", "53", "54", "55", "56", "60", "67", "94"]
    picked = {}
    for num in want_nums:
        hits = [a for a in snippets["labor"]["arts"] if a["no"] == num or a["no"].startswith(num) or a["body"].startswith(f"제{num}조")]
        if not hits:
            hits = [a for a in snippets["labor"]["arts"] if f"제{num}조" in a["body"][:20]]
        picked[num] = hits[:3]
    # decree 별표1 / 제7조 등
    decree_pick = {}
    for a in snippets["labor_decree"]["arts"]:
        if "별표" in a["no"] or "별표" in a["title"] or (a["body"].startswith("■") and "별표" in a["body"][:30]):
            decree_pick.setdefault("byeol", []).append(a)
        if a["no"] in {"7", "8", "30"} or a["body"].startswith("제7조") or a["body"].startswith("제8조") or a["body"].startswith("제30조"):
            decree_pick.setdefault(a["no"] or a["body"][:10], []).append(a)
    # minwage art 5,6
    mw_pick = {}
    for a in snippets["minwage"]["arts"]:
        if a["no"] in {"5", "6"} or a["body"].startswith("제5조") or a["body"].startswith("제6조"):
            mw_pick.setdefault(a["no"] or "x", []).append({"no": a["no"], "body": a["body"][:800]})

    (OUT / "picked_labor.json").write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "picked_decree.json").write_text(json.dumps(decree_pick, ensure_ascii=False, indent=2)[:200000], encoding="utf-8")
    (OUT / "picked_minwage.json").write_text(json.dumps(mw_pick, ensure_ascii=False, indent=2), encoding="utf-8")

    codes = toxic_codes()
    (OUT / "toxic_codes.json").write_text(json.dumps(codes, ensure_ascii=False, indent=2), encoding="utf-8")
    print("forms", [(i, k) for i, k, _ in classified])
    print("picked_keys", list(mapping.keys()), "present", [k for k in mapping if k in by])
    print("labor_arts", snippets["labor"]["n"], "decree", snippets["labor_decree"]["n"])
    print("byeol_count", len(decree_pick.get("byeol", [])))
    print("toxic", len(codes))


if __name__ == "__main__":
    main()
