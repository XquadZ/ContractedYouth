# -*- coding: utf-8 -*-
"""Downloads에서 G7 수동 파일을 찾아 복사·해제 후 해당 단계 재실행."""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
DOWNLOADS = [
    Path.home() / "Downloads",
    Path(r"C:\Users\DMLAB\Downloads"),
    Path(r"C:\Users\DMLAB\Desktop"),
]
NOW = datetime.now().strftime("%Y%m%d%H%M")


def is_complete(p: Path) -> bool:
    return p.is_file() and not p.name.endswith((".crdownload", ".part", ".tmp"))


def find_files(keywords):
    hits = []
    for d in DOWNLOADS:
        if not d.exists():
            continue
        for p in d.iterdir():
            if not is_complete(p):
                continue
            if any(k.lower() in p.name.lower() for k in keywords):
                hits.append(p)
    return hits


def main():
    log = {"ran_at": NOW, "actions": []}
    # G4 AI Hub 580
    hits = find_files(["580", "약관", "판결서", "terms"])
    dest = DC / "aihub_terms"
    dest.mkdir(parents=True, exist_ok=True)
    for h in hits:
        if h.suffix.lower() == ".zip":
            target = dest / h.name
            if not target.exists():
                shutil.copy2(h, target)
            try:
                with zipfile.ZipFile(target) as zf:
                    for n in zf.namelist():
                        if "약관" in n or "terms" in n.lower():
                            out = dest / Path(n).name
                            if not out.exists():
                                with zf.open(n) as src, open(out, "wb") as f:
                                    shutil.copyfileobj(src, f)
                log["actions"].append({"g4": str(h)})
            except Exception as e:
                log["actions"].append({"g4_error": repr(e)})

    # G5 금전대차
    hits = find_files(["금전대차", "71834"])
    dest5 = DC / "aihub_forms" / "manual_금전대차"
    dest5.mkdir(parents=True, exist_ok=True)
    for h in hits:
        shutil.copy2(h, dest5 / h.name)
        log["actions"].append({"g5": str(h)})

    # G3 manual folder hint
    man = LAW = DC / "law_api" / "연혁_g3" / "manual"
    man.mkdir(parents=True, exist_ok=True)

    # Re-run collection pieces if OC available
    try:
        from run_g1_g7 import oc, run_G1, run_G3, run_G4, run_G5, write_manual_html, MANUAL_ITEMS
        import run_g1_g7 as M
        M.MANUAL_ITEMS.clear()
        key = oc()
        if key:
            g1 = run_G1(key)
            g3 = run_G3(key)
            log["actions"].append({"rerun": "G1/G3", "g1_ok": bool(g1), "g3_ok": bool(g3)})
        g4 = run_G4()
        g5 = run_G5()
        write_manual_html(M.MANUAL_ITEMS)
        log["manual_remaining"] = len(M.MANUAL_ITEMS)
    except Exception as e:
        log["rerun_error"] = repr(e)

    out = DC / "after_manual_log.json"
    out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    print("See DATA_READY_REPORT.md / MANUAL_DOWNLOADS.html")


if __name__ == "__main__":
    main()
