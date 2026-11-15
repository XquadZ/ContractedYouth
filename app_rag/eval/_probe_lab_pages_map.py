# -*- coding: utf-8 -*-
import shutil
from pathlib import Path
import win32com.client

WORK = Path(r"C:/Users/DMLAB_Server1/Contracted_Youth")
src = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
tmp = WORK / "datasets" / "test_hwp_pdfs_v2" / "__lab_map.hwp"
shutil.copy2(src, tmp)
hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.SetMessageBoxMode(0x00010000)
hwp.Open(str(tmp))
print("pages", hwp.PageCount)

titles = [
    "표준근로계약서(기간의 정함이 없는 경우)",
    "기간의 정함이 있는 근로계약서",
    "단시간근로자 표준근로계약서",
    "연소근로자(18세 미만인 자) 표준근로계약서",
    "건설일용근로자 표준근로계약서",
    "외국인근로자",
    "가사근로자",
]
for t in titles:
    hwp.Run("MoveDocBegin")
    hwp.Run("Cancel")
    hwp.HAction.GetDefault("ForwardFind", hwp.HParameterSet.HFindReplace.HSet)
    fr = hwp.HParameterSet.HFindReplace
    fr.FindString = t
    fr.IgnoreMessage = 1
    fr.Direction = 1
    fr.FindType = 1
    ok = bool(hwp.HAction.Execute("ForwardFind", fr.HSet))
    print(ok, t, "->", hwp.KeyIndicator() if ok else None)

# Also try navigating page by page
print("--- page starts ---")
for pg in range(1, hwp.PageCount + 1):
    try:
        # MovePage
        hwp.Run("MoveDocBegin")
        for _ in range(pg - 1):
            hwp.Run("MovePageDown")
        ki = hwp.KeyIndicator()
        # grab a bit of text via select line?
        print("pageIdx", pg, "ki", ki)
    except Exception as e:
        print("page fail", pg, e)

hwp.Quit()
