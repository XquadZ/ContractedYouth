# -*- coding: utf-8 -*-
import json
from pathlib import Path

m = json.loads(Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap2\out\e2_metrics.json").read_text(encoding="utf-8"))
for k, v in m.get("baselines", {}).items():
    if "excl" in k:
        continue
    t = v["top1"]
    print("BL", k, f"{100*t['mean']:.1f}% [{100*t['lo']:.1f},{100*t['hi']:.1f}]")
for model in ("8B", "32B"):
    for cond, v in m["models"][model].items():
        t = v["top1"]
        print(model, cond, f"{100*t['mean']:.1f}% [{100*t['lo']:.1f},{100*t['hi']:.1f}]", "macro", f"{v['macroF1_point']:.3f}")
for cond, d in m.get("diffs", {}).items():
    dd = d["top1_diff"]
    print("DIFF", cond, f"{100*dd['mean']:.1f}% [{100*dd['lo']:.1f},{100*dd['hi']:.1f}]", d["gap"])
