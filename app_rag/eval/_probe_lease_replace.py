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
tmp = OUT / "__lease_rep.hwpx"
pdf = OUT / "__lease_rep.pdf"
shutil.copy2(src, tmp)
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))


def find(s: str) -> bool:
    hwp.Run("Cancel")
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = s
    fr.IgnoreMessage = 1
    fr.Direction = 1
    fr.FindType = 1
    try:
        return bool(hwp.HAction.Execute("ForwardFind", fr.HSet))
    except Exception:
        return False


for s in ["제1조", "제1조(보증금", "특약사항", "별지", "중요확인사항", "【특약", "특 약"]:
    hwp.Run("MoveDocBegin")
    ok = find(s)
    print("find", s, ok, hwp.KeyIndicator() if ok else None)

# Strategy: find 제1조, set pos, then select to 별지 and delete
hwp.Run("MoveDocBegin")
ok1 = find("제1조")
print("start", ok1, hwp.KeyIndicator())
# Start selection here - MoveSelBegin? In Hangul: Run("MoveSelRight") etc.
# Alternative: replace large chunks via AllReplace of known first article start

# Try: from 제1조 insert page break and new content after, then delete old by selecting
# Simpler test: Move to 제1조, insert marker, then delete until 별지 using Select + Delete in a loop

hwp.Run("MoveDocBegin")
find("제1조")
# Insert before 제1조 a section break and our content, then delete old articles
act = hwp.CreateAction("InsertText")
ps = act.CreateSet()
ps.SetItem("Text", "\r\n<<<CLAUSE_START>>>\r\n조항테스트문장 한 번만\r\n<<<CLAUSE_END>>>\r\n")
act.Execute(ps)

# Now delete from original 제1조 (after our insert) to 별지 - find next 제1조
if find("제1조"):
    print("found original 제1조 after insert", hwp.KeyIndicator())
    # select to 별지
    # Use Extend selection: in HWP, Shift+End style via MoveSel*
    try:
        # mark start by selecting current word then extend
        hwp.Run("MoveSelWordEnd")
    except Exception as e:
        print("sel", e)

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(tmp))
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("has marker", "<<<CLAUSE_START>>>" in text)
print("pages", len(ex["pages"]), "chars", len(text))
idx = text.find("<<<CLAUSE")
print(repr(text[idx : idx + 80] if idx >= 0 else text[:200]))
