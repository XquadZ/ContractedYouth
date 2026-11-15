# -*- coding: utf-8 -*-
"""Find article header, delete until next header, insert replacement."""
from __future__ import annotations

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
src = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts" / "MONTHLY_010.hwpx"
tmp = OUT / "__art_rep2.hwpx"
pdf = OUT / "__art_rep2.pdf"
shutil.copy2(src, tmp)
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))


def find(s: str) -> bool:
    hwp.Run("Cancel")
    hwp.Run("MoveDocBegin")
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = s
    fr.IgnoreMessage = 1
    fr.Direction = 1
    fr.FindType = 1
    return bool(hwp.HAction.Execute("ForwardFind", fr.HSet))


def replace_between(start_h: str, end_h: str, new_text: str) -> bool:
    if not find(start_h):
        print("no start", start_h)
        return False
    # start selection at beginning of found text - MoveLeft to start of selection?
    hwp.Run("MoveSelStart") if False else None
    # Select from current find highlight: extend until end header by char?
    # Approach: copy start pos via KeyIndicator, select by deleting line by line
    # Use Replace with wildcard? 
    # Practical: AllReplace start_h + known body opening
    # Get short unique: replace start_h alone first with STARTMARK, end with ENDMARK
    return False


# Marker approach: wrap article
if not find("제5조(계약의 해제)"):
    print("fail find 5")
else:
    print("found 5", hwp.KeyIndicator())

# AllReplace using first sentence only then rest - try replace full visible PDF text without newlines
old = (
    "제5조(계약의 해제) 임차인이 임대인에게 중도금(중도금이 없을 때는 잔금)을 지급하기 전까지, "
    "임대인은 계약금의 배액을 상환하고, 임차인은 계약금을 포기하고 이 계약을 해제할 수 있다."
)
# try with possible soft hyphen / line break variants
variants = [
    old,
    old.replace("지급하기 전까지", "지급하기 \n전까지"),
    old.replace(" ", ""),
]
new = "제5조(계약의 해제) 계약의 해제는 관련 법령과 당사자 간 약정에 따른다."
for i, oldv in enumerate(variants):
    hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = oldv
    fr.ReplaceString = new
    fr.IgnoreMessage = 1
    fr.ReplaceMode = 1
    fr.FindType = 1
    ok = hwp.HAction.Execute("AllReplace", fr.HSet)
    print("try", i, "ok", bool(ok))

# Another approach: find start, insert NEW before it, then find old start again and delete until 제6조
if find("제5조(계약의 해제)"):
    act = hwp.CreateAction("InsertText")
    ps = act.CreateSet()
    ps.SetItem("Text", new + "\r\n")
    act.Execute(ps)
    print("inserted before")
    # now delete old 제5조: find again (second occurrence)
    hwp.Run("Cancel")
    # ForwardFind from current
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = "제5조(계약의 해제)"
    fr.IgnoreMessage = 1
    fr.Direction = 1
    fr.FindType = 1
    if hwp.HAction.Execute("ForwardFind", fr.HSet):
        print("found old again", hwp.KeyIndicator())
        # select to 제6조
        # Use set Pos: select while MoveRight until we would hit 제6조 - hard
        # Delete by replace from 제5조 through before 제6조 using a medium chunk
        chunk = "제5조(계약의 해제) 임차인이 임대인에게 중도금"
        hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
        fr = hwp.HParameterSet.HFindReplace
        fr.FindString = chunk
        fr.ReplaceString = ""
        fr.IgnoreMessage = 1
        fr.ReplaceMode = 1
        fr.FindType = 1
        print("clear head", bool(hwp.HAction.Execute("AllReplace", fr.HSet)))

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(tmp))
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("count 제5조", text.count("제5조"))
j = text.find("제5조")
print(repr(text[j : j + 150]))
print("official leftover", "중도금(중도금이 없을" in text)
print("gold", "관련 법령과 당사자" in text)
