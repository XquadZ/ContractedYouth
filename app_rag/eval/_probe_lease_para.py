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
tmp = OUT / "__lease_para.hwpx"
pdf = OUT / "__lease_para.pdf"
shutil.copy2(src, tmp)
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))


def find(s):
    hwp.Run("Cancel")
    hwp.Run("MoveDocBegin")
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = s
    fr.IgnoreMessage = 1
    fr.Direction = 1
    fr.FindType = 1
    return bool(hwp.HAction.Execute("ForwardFind", fr.HSet))


def replace_article(start_needle: str, next_needle: str | None, new_text: str):
    if not find(start_needle):
        print("no", start_needle)
        return
    # select from here toward next article title
    hwp.Run("MoveSelLineEnd")
    # extend a few paragraphs
    for _ in range(8):
        try:
            hwp.Run("MoveSelNextPara")
        except Exception:
            break
        # stop if selection now contains next needle? hard to know
    # Instead: delete line and insert
    hwp.Run("Cancel")
    find(start_needle)
    hwp.Run("MoveLineBegin")
    # select whole paragraph repeatedly and delete until next title found by peek
    # Practical: AllReplace first 40 chars of original para — skip

    # Use: select current para, delete, insert new
    hwp.Run("MoveSelParaEnd")
    hwp.Run("Delete")
    act = hwp.CreateAction("InsertText")
    ps = act.CreateSet()
    ps.SetItem("Text", new_text + "\r\n")
    act.Execute(ps)
    print("replaced", start_needle)


# Break out of tables first at doc level for articles area
hwp.Run("MoveDocBegin")
find("제1조")
for cmd in ["MoveOutOfTable", "BreakTable"]:
    try:
        hwp.Run(cmd)
        print("ok", cmd)
    except Exception as e:
        print("fail", cmd, e)

# Try clearing by replacing known long unique form sentences with empty, then insert block at 특약
ex0 = None
# Save pdf first of original? skip

# Nuke distinctive form clauses via AllReplace of distinctive openings
snippets = [
    "위 부동산의 임대차에 관하여 임대인과 임차인은 합의하에",
    "임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는",
    "임대인과 임차인은 임차주택의 수리가 필요한 시설물",
    "임차인은 임대인의 동의 없이 임차주택의 구조",
    "임차인이 임대인에게 중도금",
    "당사자 일방이 채무를 이행하지 아니하는 때에는",
    "임차인은 본인의 과실 없이 임차주택의 일부가 멸실",
    "임차인은 임대차기간이 끝나기 6개월 전부터",
]
for sn in snippets:
    try:
        hwp.HAction.GetDefault("AllReplace", hwp.HParameterSet.HFindReplace.HSet)
        fr = hwp.HParameterSet.HFindReplace
        fr.FindString = sn
        fr.ReplaceString = ""
        fr.IgnoreMessage = 1
        fr.ReplaceMode = 1
        fr.FindType = 1
        hwp.HAction.Execute("AllReplace", fr.HSet)
        print("cleared snip", sn[:20])
    except Exception as e:
        print("snip fail", e)

# Insert gold at 특약사항
if find("특약사항"):
    hwp.Run("MoveLineEnd")
    act = hwp.CreateAction("InsertText")
    ps = act.CreateSet()
    ps.SetItem(
        "Text",
        "\r\n임차주택 소재지: 서울특별시 노원구 봉천로 92. 주택 유형: 아파트. 임차할 부분: 3층 302호 전부.\r\n"
        "보증금 36,220,000원, 계약금 3,622,000원, 중도금 0원, 잔금 32,598,000원. 월차임 1,080,000원, 관리비 60,000원.\r\n"
        "임대인은 물가상승 등을 고려하여 매년 차임 조정안을 통보하고 임차인은 성실하게 협의한다.\r\n",
    )
    act.Execute(ps)
    print("inserted at 특약")

if pdf.exists():
    pdf.unlink()
hwp.SaveAs(str(tmp))
hwp.SaveAs(str(pdf), "PDF")
time.sleep(0.4)
hwp.Quit()
ex = extract_bytes(pdf.read_bytes(), pdf.name)
text = "\n".join(p.get("text") or "" for p in ex["pages"])
print("pages", len(ex["pages"]))
print("제2조 form left", "임대차 목적대로 사용" in text)
print("gold once-ish", text.count("36,220,000"))
print("차임 조정", text.count("차임 조정안을 통보"))
