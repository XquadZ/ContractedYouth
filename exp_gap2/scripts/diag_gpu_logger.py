# -*- coding: utf-8 -*-
"""2초 간격 GPU 로그 → exp_gap2/diag/gpu_log.csv (out/ 미사용)."""
from __future__ import annotations

import csv
import subprocess
import time
from datetime import datetime
from pathlib import Path

DIAG = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap2\diag")
OUT = DIAG / "gpu_log.csv"
HEADER = [
    "ts",
    "gpu0_temp",
    "gpu0_power",
    "gpu0_mem",
    "gpu1_temp",
    "gpu1_power",
    "gpu1_mem",
]


def query():
    raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,temperature.gpu,power.draw,memory.used",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        errors="replace",
    )
    rows = {}
    for ln in raw.strip().splitlines():
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) >= 4:
            rows[int(parts[0])] = parts[1:4]
    return rows


def main():
    DIAG.mkdir(parents=True, exist_ok=True)
    new = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
            f.flush()
        while True:
            try:
                r = query()
                g0 = r.get(0, ["", "", ""])
                g1 = r.get(1, ["", "", ""])
                w.writerow(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        g0[0],
                        g0[1],
                        g0[2],
                        g1[0],
                        g1[1],
                        g1[2],
                    ]
                )
                f.flush()
            except Exception as e:
                w.writerow([datetime.now().isoformat(timespec="seconds"), f"ERR:{e}", "", "", "", "", ""])
                f.flush()
            time.sleep(2)


if __name__ == "__main__":
    main()
