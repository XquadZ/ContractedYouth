# -*- coding: utf-8 -*-
import re
from pathlib import Path

root = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
n = 0
for p in root.rglob("*"):
    if not p.is_file():
        continue
    if p.suffix.lower() not in {".json", ".xml", ".html", ".txt", ".md", ".log"}:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    newt = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", t)
    newt = re.sub(r'("OC"\s*:\s*")[^"]+(")', r"\1REDACTED\2", newt)
    if newt != t:
        p.write_text(newt, encoding="utf-8")
        n += 1
print("redacted_files", n)
