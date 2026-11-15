# -*- coding: utf-8 -*-
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
tmp = OUT / "__sel.hwpx"
pdf = OUT / "__sel.pdf"
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


def pos():
    return hwp.GetPos()  # (list, para, char)


# find start of 제5조, move to start of match
find("제5조(계약의 해제)")
# after find, selection may be on match; GetPos is end? try MoveLeft to start
print("after find", pos(), hwp.KeyIndicator())
# Use GetSelectedPos
try:
    print("selected", hwp.GetSelectedPos())
except Exception as e:
    print("GetSelectedPos", e)

# Set start at beginning of find: MoveLineBegin or select start
hwp.Run("Cancel")
find("제5조(계약의 해제)")
# MoveSelLeft until start - or SetPos to selected start
sp = hwp.GetSelectedPos()
print("sp", sp)
# docs say GetSelectedPos returns (slist,spara,spos,elist,epara,epos)
if sp and len(sp) >= 6:
    s = (sp[0], sp[1], sp[2])
else:
    s = pos()

# find end = start of 제6조
hwp.Run("Cancel")
find("제6조(채무불이행과 손해배상)")
ep = hwp.GetSelectedPos()
print("ep", ep)
if ep and len(ep) >= 6:
    e = (ep[0], ep[1], ep[2])  # start of 제6조
else:
    e = pos()

print("select", s, "->", e)
try:
    ok = hwp.SelectText(s[0], s[1], s[2], e[0], e[1], e[2])
    print("SelectText", ok, "mode", hwp.SelectionMode)
except Exception as ex:
    print("SelectText err", ex)
    # try alternate signature
    try:
        ok = hwp.SelectText(s, e)
        print("SelectText2", ok)
    except Exception as ex2:
        print("SelectText2 err", ex2)

hwp.Run("Delete")
act = hwp.CreateAction("InsertText")
ps = act.CreateSet()
ps.SetItem("Text", "제5조(계약의 해제) 계약의 해제는 관련 법령과 당사자 간 약정에 따른다.\r\n")
act.Execute(ps)

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("count5", text.count("제5조"), "count6", text.count("제6조(채무"))
j = text.find("제5조")
print(repr(text[j : j + 200]))
