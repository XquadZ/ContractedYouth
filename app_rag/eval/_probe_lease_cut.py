# -*- coding: utf-8 -*-
import shutil
import sys
import time
from pathlib import Path
import win32com.client

WORK = Path(r"C:/Users/DMLAB_Server1/Contracted_Youth")
sys.path.insert(0, str(WORK / "app_rag"))
from rag.extract import extract_bytes

OUT = WORK / "datasets" / "test_hwp_pdfs_v2"
src = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts" / "MONTHLY_010.hwpx"
tmp = OUT / "__lease_cut.hwpx"
pdf = OUT / "__lease_cut.pdf"
shutil.copy2(src, tmp)
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))

hwp.Run("MoveDocBegin")
hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
fr = hwp.HParameterSet.HFindReplace
fr.FindString = "제1조"
fr.IgnoreMessage = 1
fr.Direction = 1
fr.FindType = 1
print("find", bool(hwp.HAction.Execute("ForwardFind", fr.HSet)), hwp.KeyIndicator())

for cmd in ["MoveSelDocEnd", "MoveSelParaEnd", "Select", "Delete"]:
    try:
        if cmd == "Delete":
            continue
        hwp.Run(cmd)
        print("ok", cmd, hwp.KeyIndicator())
    except Exception as e:
        print("fail", cmd, e)

# reset and try MoveSelDocEnd then Delete
hwp.Run("Cancel")
hwp.Run("MoveDocBegin")
hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
fr = hwp.HParameterSet.HFindReplace
fr.FindString = "제1조"
fr.IgnoreMessage = 1
fr.Direction = 1
fr.FindType = 1
hwp.HAction.Execute("ForwardFind", fr.HSet)
try:
    hwp.Run("MoveSelDocEnd")
    print("selected to end?", hwp.KeyIndicator())
    hwp.Run("Delete")
    print("deleted", hwp.PageCount)
except Exception as e:
    print("cut fail", e)

# insert gold sample
act = hwp.CreateAction("InsertText")
ps = act.CreateSet()
ps.SetItem("Text", "\r\n임차주택 소재지: 서울특별시 노원구 봉천로 92.\r\n보증금 36,220,000원, 월차임 1,080,000원.\r\n※ 관련 법령에 따른 권리·의무는 주택임대차보호법 등에서 정하는 바에 따릅니다.\r\n")
act.Execute(ps)

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(tmp))
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("pages", len(ex["pages"]), "chars", len(text))
print("has 제2조 form?", "제2조(임대차기간)" in text)
print("has gold", "36,220,000" in text)
print("head", text[:300].replace("\n", " | "))
print("tail", text[-300:].replace("\n", " | "))
