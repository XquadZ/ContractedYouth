# -*- coding: utf-8 -*-
"""로컬 test를 순서대로 실행: EXAONE none→neutral→tuned, AX none→neutral→tuned, EXAONE 유지."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(model: str, version: str) -> int:
    cmd = [
        PY,
        "-u",
        "-X",
        "utf8",
        str(APP / "eval" / "final_test_local.py"),
        "--split",
        "test",
        "--model",
        model,
        "--version",
        version,
    ]
    print("CHAIN", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(APP))


def main() -> None:
    # EXAONE none은 이미 돌고 있을 수 있음 — final_test_local이 완료 파일 스킵
    for version in ("none", "neutral", "tuned"):
        code = run("EXAONE", version)
        if code != 0:
            print("WARN EXAONE", version, "exit", code, flush=True)
    for version in ("none", "neutral", "tuned"):
        code = run("AX", version)
        if code != 0:
            print("WARN AX", version, "exit", code, flush=True)
    subprocess.call(
        [PY, "-u", "-X", "utf8", str(APP / "eval" / "final_test_local.py"), "--leave"],
        cwd=str(APP),
    )
    print("CHAIN_DONE", flush=True)


if __name__ == "__main__":
    main()
