# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

OUT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\fix_abcdef_results.json")
r = json.loads(OUT.read_text(encoding="utf-8"))
name = "이자제한법 제2조제1항의 최고이자율에 관한 규정"
for row in r["B"]["laws"][name]["table"]:
    row["공포번호"] = "31593"  # API split: 3 + strong(1) + 593
text = json.dumps(r, ensure_ascii=False, indent=2)
text = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", text)
OUT.write_text(text, encoding="utf-8")
print("patched")
