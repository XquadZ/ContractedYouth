# -*- coding: utf-8 -*-
"""Probe whole-article AllReplace using TEXT extract from Hangul."""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

import win32com.client

WORK = Path(r"C:/Users/DMLAB_Server1/Contracted_Youth")
sys.path.insert(0, str(WORK / "app_rag"))
from rag.extract import extract_bytes

OUT = WORK / "datasets" / "test_hwp_pdfs_v3"
OFF = json.loads((OUT / "lease_official_articles.json").read_text(encoding="utf-8"))["official"]
src = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts" / "MONTHLY_010.hwpx"
tmp = OUT / "__art_rep.hwpx"
pdf = OUT / "__art_rep.pdf"
shutil.copy2(src, tmp)

hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))

txt_path = OUT / "__art_rep.txt"
if txt_path.exists():
    txt_path.unlink()
hwp.SaveAs(str(txt_path), "TEXT")
time.sleep(0.5)
raw = txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else ""
print("TEXT len", len(raw))


def split_articles(text: str) -> dict[str, str]:
    flat = re.sub(r"[ \t\r]+", " ", text)
    pat = re.compile(r"제\s*([1-9]|1[0-5])\s*조\s*\([^)]+\)")
    matches = list(pat.finditer(flat))
    arts = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        key = f"제{num}조"
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        body = flat[start:end]
        for stop in ("특약사항", "별지1", "별지 1", "별지2", "중요확인사항"):
            j = body.find(stop)
            if j > 40:
                body = body[:j]
                break
        body = body.strip()
        if key not in arts and len(body) > 40:
            arts[key] = body
    return arts


arts = split_articles(raw)
print("found", list(arts.keys()))
print("제5조 old", arts.get("제5조", "")[:80])

# replace 제5조 with official (should be almost same) then with a gold marker
old5 = arts.get("제5조")
new5 = OFF["제5조"]["text"]
# gold-style replace for test
gold5 = "제5조(계약의 해제) 계약의 해제는 관련 법령과 당사자 간 약정에 따른다."


def replace_all(old: str, new: str) -> None:
    hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = old
    fr.ReplaceString = new
    fr.IgnoreMessage = 1
    fr.ReplaceMode = 1
    fr.FindType = 1
    fr.Direction = 0
    ok = hwp.HAction.Execute("AllReplace", fr.HSet)
    print("replace", bool(ok), "oldlen", len(old), "newlen", len(new))


if old5:
    # try shorter unique head if full fails
    replace_all(old5, gold5)

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("gold in pdf", gold5 in re.sub(r"\s+", "", text) or "계약의 해제는 관련 법령" in text)
# show around 제5조
j = text.find("제5조")
print(repr(text[j : j + 120] if j >= 0 else "no"))
# check broken mid sentence from v2 style
print("broken?", "하고 임차인은 성실하게 다" in text)
print("pages", len(ex["pages"]))
for p in ex["pages"]:
    m = re.search(r"(\d+)\s*/\s*(\d+)", p.get("text") or "")
    if m:
        print("page mark", m.group(0))
