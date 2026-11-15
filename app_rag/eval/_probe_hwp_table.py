# -*- coding: utf-8 -*-
"""Probe Hangul table create + page delete."""
import time
from pathlib import Path
import win32com.client

OUT = Path(r"C:/Users/DMLAB_Server1/Contracted_Youth/datasets/test_hwp_pdfs_v2")
OUT.mkdir(parents=True, exist_ok=True)

hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Clear(1)

# title
act = hwp.CreateAction("InsertText")
p = act.CreateSet()
p.SetItem("Text", "금전차용계약서\r\n")
act.Execute(p)

# TableCreate via parameter set
try:
    hwp.HAction.GetDefault("TableCreate", hwp.HParameterSet.HTableCreation.HSet)
    tc = hwp.HParameterSet.HTableCreation
    tc.Rows = 3
    tc.Cols = 3
    tc.WidthType = 2  # fit to width?
    tc.HeightType = 0
    ok = hwp.HAction.Execute("TableCreate", tc.HSet)
    print("TableCreate", ok)
except Exception as e:
    print("TableCreate fail", e)
    # fallback TableInsert
    try:
        hwp.Run("TableInsert")
        print("TableInsert run")
    except Exception as e2:
        print("TableInsert fail", e2)

# insert text in cells by Tab
for cell_text in ["구분", "성명", "연락처", "채권자", "김민수", "010-0000-0001", "채무자", "이서연", "010-0000-0002"]:
    act = hwp.CreateAction("InsertText")
    p = act.CreateSet()
    p.SetItem("Text", cell_text)
    act.Execute(p)
    try:
        hwp.Run("TableRightCell")
    except Exception:
        pass

out = OUT / "__loan_table.pdf"
if out.exists():
    out.unlink()
hwp.SaveAs(str(OUT / "__loan_table.hwp"))
hwp.SaveAs(str(out), "PDF")
time.sleep(0.5)
hwp.Quit()
print("WROTE", out, out.exists(), out.stat().st_size if out.exists() else 0)
