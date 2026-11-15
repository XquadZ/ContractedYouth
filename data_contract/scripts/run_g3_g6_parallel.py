# -*- coding: utf-8 -*-
"""G3~G6 only (while G2 runs). Writes g3_g6_partial.json then merges."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_g1_g7 import (  # noqa: E402
    MANUAL_ITEMS,
    OUT,
    dump,
    oc,
    run_G3,
    run_G4,
    run_G5,
    run_G6,
    write_after_manual,
    write_manual_html,
)

PARTIAL = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\g3_g6_partial.json")


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    key = oc()
    result = {}
    for name, fn in [("G3", lambda: run_G3(key)), ("G4", run_G4), ("G5", run_G5), ("G6", run_G6)]:
        print("=" * 40, name, flush=True)
        try:
            result[name] = fn()
            result[name]["_done"] = True
        except Exception as e:
            result[name] = {"_error": repr(e), "_done": False}
            print(name, "ERROR", e, flush=True)
        result["manual"] = list(MANUAL_ITEMS)
        PARTIAL.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_after_manual()
    # don't overwrite MANUAL html yet — merge later
    print("WROTE", PARTIAL, flush=True)


if __name__ == "__main__":
    main()
