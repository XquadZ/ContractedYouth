# -*- coding: utf-8 -*-
"""JEONSE/MONTHLY HWPX에서 제N조(제목) 본문 최빈값을 공식 문구로 둔다."""
from __future__ import annotations

import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

WORK = Path(__file__).resolve().parents[2]
FORMS = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts"
OUT = WORK / "datasets" / "test_hwp_pdfs_v3"
OUT.mkdir(parents=True, exist_ok=True)


def hwpx_text(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.search(r"section\d*\.xml$", n, re.I))
        for name in names:
            raw = z.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            for t in root.iter():
                if t.tag.endswith("}t") or t.tag == "t":
                    if t.text:
                        parts.append(t.text)
                    if t.tail:
                        parts.append(t.tail)
            parts.append("\n")
    return "".join(parts)


def normalize_vars(s: str) -> str:
    """금액·날짜·이름 등 가변값을 치환해 구조 비교."""
    t = re.sub(r"\s+", "", s)
    t = re.sub(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일", "DATE", t)
    t = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", t)
    t = re.sub(r"\d{1,3}(?:,\d{3})+|\d{4,}", "NUM", t)
    t = re.sub(r"[김이박최정강조윤장임한오서신권황안송류전홍고문양손배]/허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부][가-힣]{1,3}", "NAME", t)
    return t


def split_articles(text: str) -> dict[str, str]:
    flat = re.sub(r"[ \t\r]+", " ", text)
    # only real article headers: 제N조(제목)
    pat = re.compile(r"제\s*([1-9]|1[0-5])\s*조\s*\([^)]+\)")
    matches = list(pat.finditer(flat))
    arts: dict[str, str] = {}
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
        body = re.sub(r"\n+", "\n", body).strip()
        # keep first header occurrence in main contract (skip later 별지 refs)
        if key not in arts and len(body) > 40:
            arts[key] = body
    return arts


def main() -> None:
    files = sorted(
        [f for f in FORMS.glob("*.hwpx") if f.name.startswith(("JEONSE_", "MONTHLY_"))]
    )
    by_art: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, dict[str, str]] = defaultdict(dict)
    per_file = {}
    for f in files:
        text = hwpx_text(f)
        arts = split_articles(text)
        per_file[f.name] = {k: v[:100] for k, v in arts.items()}
        for k, v in arts.items():
            nk = normalize_vars(v)
            by_art[k][nk] += 1
            samples[k].setdefault(nk, v)
        print(f.name, sorted(arts.keys(), key=lambda x: int(x[1:-1])))

    official = {}
    for art, ctr in sorted(by_art.items(), key=lambda x: int(x[0][1:-1])):
        nk, cnt = ctr.most_common(1)[0]
        text = samples[art][nk]
        official[art] = {
            "text": text,
            "count": cnt,
            "total": sum(ctr.values()),
            "variants": len(ctr),
            "title": re.match(r"제\s*\d+\s*조\s*\([^)]+\)", text).group(0) if re.match(r"제\s*\d+\s*조\s*\([^)]+\)", text) else art,
        }
        print(art, "top", cnt, "/", sum(ctr.values()), "var", len(ctr), official[art]["title"])

    path = OUT / "lease_official_articles.json"
    path.write_text(
        json.dumps({"n_files": len(files), "official": official, "per_file_heads": per_file}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("WROTE", path)


if __name__ == "__main__":
    main()
