# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_g1_g7 import MANUAL_ITEMS, oc, run_G3

OUT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\g3_partial.json")

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    key = oc()
    print("G3 start", flush=True)
    try:
        result = run_G3(key)
        result["_done"] = True
    except Exception as e:
        result = {"_error": repr(e), "_done": False}
        print("ERROR", e, flush=True)
    result["manual_extra"] = list(MANUAL_ITEMS)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, flush=True)

if __name__ == "__main__":
    main()
