# -*- coding: utf-8 -*-
"""Hold llama-server idle 15 minutes; log GPU temps. ASCII only."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

G2 = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap2")
RUN_LOG = G2 / "run_log.md"
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def q():
    return subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,temperature.gpu,power.draw,power.limit,clocks.sm",
            "--format=csv",
        ],
        text=True,
        errors="replace",
    )


def append(text: str):
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    start = datetime.now().isoformat(timespec="seconds")
    q0 = q()
    append(f"\n## Cooldown 15min START @ {start}\n```\n{q0}```\n")
    print("cooldown start", start, flush=True)
    print(q0, flush=True)
    for i in range(15):
        time.sleep(60)
        print(f"cooldown min {i+1}/15", datetime.now().isoformat(timespec="seconds"), flush=True)
    end = datetime.now().isoformat(timespec="seconds")
    q1 = q()
    append(f"\n## Cooldown 15min END @ {end}\n```\n{q1}```\n")
    print("cooldown end", end, flush=True)
    print(q1, flush=True)
    (G2 / "out" / "cooldown_done.json").write_text(
        f'{{"start":"{start}","end":"{end}"}}\n', encoding="utf-8"
    )


if __name__ == "__main__":
    main()
