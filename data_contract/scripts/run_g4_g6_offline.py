# -*- coding: utf-8 -*-
"""G4/G5/G6 offline steps (no law API)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_g1_g7 import MANUAL_ITEMS, run_G4, run_G5, run_G6  # noqa: E402

PARTIAL = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\g4_g6_partial.json")


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    result = {}
    for name, fn in [("G4", run_G4), ("G5", run_G5), ("G6", run_G6)]:
        print("=" * 40, name, flush=True)
        try:
            result[name] = fn()
            result[name]["_done"] = True
        except Exception as e:
            result[name] = {"_error": repr(e), "_done": False}
            print(name, "ERROR", e, flush=True)
        result["manual"] = list(MANUAL_ITEMS)
        PARTIAL.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", PARTIAL, "manual", len(MANUAL_ITEMS), flush=True)


if __name__ == "__main__":
    main()
