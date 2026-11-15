# -*- coding: utf-8 -*-
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_g1_g7 import MANUAL_ITEMS, write_manual_html

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
OUT = DC / "g1_g7_results.json"
r = json.loads(OUT.read_text(encoding="utf-8"))
manual = [
    m
    for m in (r.get("manual") or [])
    if m.get("id") != "g1_ftc" and m.get("targets") != ["ftc"]
]
r["manual"] = manual
r["manual_count"] = len(manual)
OUT.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
MANUAL_ITEMS.clear()
MANUAL_ITEMS.extend(manual)
write_manual_html(manual)

rep = DC / "DATA_READY_REPORT.md"
t = rep.read_text(encoding="utf-8")
t = re.sub(
    r"(\| AIHub 판결서·약관 \| )[^|]+",
    r"\1대기(G7 수동)",
    t,
    count=1,
)
t = re.sub(
    r"(\| 임대차분쟁조정사례집 PDF \| )[^|]+",
    r"\1OCR_low_quality",
    t,
    count=1,
)
marker = "## 사람이 할 일"
if marker in t:
    head = t.split(marker)[0].rstrip() + "\n\n"
    items = "\n".join(f"  - {m['title']}" for m in manual)
    # also trim trailing old G section 사람이 할 일 duplicates inside G section
    g7_marker = "### §G7. 수동 다운로드"
    if g7_marker in head:
        before_g7, _, after_g7 = head.partition(g7_marker)
        # rebuild G7 tail briefly
        g7 = (
            "### §G7. 수동 다운로드\n\n"
            f"- 파일: `data_contract/MANUAL_DOWNLOADS.html`\n"
            f"- after_manual: `python data_contract\\scripts\\after_manual.py`\n"
            f"- 항목 수: **{len(manual)}**\n"
            + "".join(f"  - {m['title']}\n" for m in manual)
            + "\n"
        )
        head = before_g7 + g7
    t = (
        head
        + marker
        + "\n\n"
        + f"- `MANUAL_DOWNLOADS.html` 항목 **{len(manual)}**개:\n"
        + items
        + "\n"
    )
rep.write_text(t, encoding="utf-8")
print("manual", len(manual))
for m in manual:
    print("-", m["title"])
