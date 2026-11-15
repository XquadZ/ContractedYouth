# -*- coding: utf-8 -*-
"""Try extracting only one LAB form via find + select + copy."""
import shutil
import sys
import time
from pathlib import Path

import win32com.client

WORK = Path(r"C:/Users/DMLAB_Server1/Contracted_Youth")
sys.path.insert(0, str(WORK / "app_rag"))
from rag.extract import extract_bytes

OUT = WORK / "datasets" / "test_hwp_pdfs_v2"
src = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
tmp = OUT / "__lab_one.hwp"
pdf = OUT / "__lab_one.pdf"
shutil.copy2(src, tmp)

hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))
print("PageCount", hwp.PageCount)


def find(s: str) -> bool:
    hwp.Run("Cancel")
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = s
    fr.IgnoreMessage = 1
    fr.Direction = 1  # forward
    fr.FindType = 1
    try:
        return bool(hwp.HAction.Execute("ForwardFind", fr.HSet))
    except Exception as e:
        print("find err", s, e)
        return False


# Locate 단시간 title
hwp.Run("MoveDocBegin")
ok = find("단시간근로자 표준근로계약서")
print("find 단시간", ok, "pos", hwp.KeyIndicator())

# Try DeletePage from end until we have 2 pages — inspect what remains
n0 = hwp.PageCount
for i in range(n0):
    try:
        # go to last page and delete
        hwp.Run("MoveDocEnd")
        before = hwp.PageCount
        hwp.Run("DeletePage")
        after = hwp.PageCount
        print("del", i, before, "->", after)
        if after <= 2:
            break
        if after >= before:
            print("no shrink")
            break
    except Exception as e:
        print("DeletePage fail", e)
        break

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(tmp))
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.5)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
print("pages", len(ex["pages"]), "chars", ex.get("chars"))
for i, p in enumerate(ex["pages"], 1):
    t = (p.get("text") or "")[:120].replace("\n", " ")
    print(i, t)
