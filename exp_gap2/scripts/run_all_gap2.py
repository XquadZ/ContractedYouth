# -*- coding: utf-8 -*-
"""GAP-2 전체 파이프라인 오케스트레이터.
순서: prepare(이미 했으면 스킵) → baselines → e1_logprob → run_gap2 → thinking → audit/report
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable


def run(script: str, args=None):
    cmd = [PY, str(SCRIPTS / script)] + (args or [])
    print("\n====", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(SCRIPTS))
    if r.returncode != 0:
        print("FAILED", script, "code", r.returncode, flush=True)
        return False
    return True


def main():
    data = SCRIPTS.parent / "data"
    # 1 prepare if missing
    if not (data / "e2_test1000.jsonl").exists() or not (data / "emb_e2_corpus.npy").exists():
        if not run("prepare_data2.py"):
            sys.exit(1)
    else:
        print("skip prepare (data exists)")

    # 2 baselines
    if not (SCRIPTS.parent / "out" / "baseline_e2_B0.jsonl").exists():
        if not run("baselines2.py"):
            sys.exit(1)
    else:
        print("skip baselines")

    # 3 e1 logprob
    if not run("run_e1_logprob.py"):
        print("logprob failed — continue other stages")

    # 4 E2 LLM runs
    if not run("run_gap2.py", ["--mode", "full", "--model", "both"]):
        print("run_gap2 failed")
        sys.exit(1)

    # 5 thinking
    if not run("run_thinking.py"):
        print("thinking failed — continue to report")

    # 6 audit + report
    if not run("build_audit_and_report.py"):
        sys.exit(1)
    print("GAP-2 ALL DONE")


if __name__ == "__main__":
    main()
