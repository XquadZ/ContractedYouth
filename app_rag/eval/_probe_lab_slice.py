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
src = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"


def slice_pages(start: int, end: int, tag: str):
    tmp = OUT / f"__lab_slice_{tag}.hwp"
    pdf = OUT / f"__lab_slice_{tag}.pdf"
    shutil.copy2(src, tmp)
    hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    hwp.SetMessageBoxMode(0x00010000)
    hwp.Open(str(tmp))
    # delete after end
    while hwp.PageCount > end:
        hwp.Run("MoveDocEnd")
        hwp.Run("DeletePage")
    # delete before start
    for _ in range(start - 1):
        hwp.Run("MoveDocBegin")
        hwp.Run("DeletePage")
    print(tag, "final pages", hwp.PageCount)
    if pdf.exists():
        pdf.unlink()
    hwp.SaveAs(str(tmp))
    hwp.SaveAs(str(pdf), "PDF")
    time.sleep(0.3)
    hwp.Quit()
    ex = extract_bytes(pdf.read_bytes(), pdf.name)
    print(tag, "pdf pages", len(ex["pages"]), "chars", ex.get("chars"))
    print(tag, "head", (ex["pages"][0].get("text") or "")[:100].replace("\n", " "))


slice_pages(6, 7, "dan")
slice_pages(1, 2, "std")
slice_pages(3, 4, "youth")
slice_pages(5, 5, "const")
