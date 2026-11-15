# -*- coding: utf-8 -*-
"""A.X 4.0 Light만 8082에 띄운다. Qwen은 올리지 않는다."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag.paths import APP, AX_GGUF, AX_HEALTH, LLAMA, SERVER  # noqa: E402

LOG = APP / "out"


def health() -> bool:
    try:
        with urllib.request.urlopen(AX_HEALTH, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> None:
    if health():
        print("ALREADY_UP 8082", flush=True)
        return
    if not SERVER.exists():
        raise SystemExit(f"missing {SERVER}")
    if not AX_GGUF.exists():
        raise SystemExit(f"missing {AX_GGUF}")
    LOG.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(SERVER),
        "-m",
        str(AX_GGUF),
        "--host",
        "127.0.0.1",
        "--port",
        "8082",
        "-c",
        "8192",
        "-ngl",
        "99",
        "-np",
        "1",
        "--cache-prompt",
        "--reasoning",
        "off",
        "--reasoning-budget",
        "0",
    ]
    logf = (LOG / "llama_8082.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "0"
    proc = subprocess.Popen(cmd, cwd=str(LLAMA), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for _ in range(180):
        if health():
            print("AX_UP 8082", flush=True)
            break
        if proc.poll() is not None:
            raise SystemExit(2)
        time.sleep(2)
    else:
        proc.kill()
        raise SystemExit("server_not_healthy")
    (LOG / "ax_up.json").write_text(json.dumps({"port": 8082, "gguf": str(AX_GGUF)}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        while True:
            time.sleep(30)
            if proc.poll() is not None:
                raise SystemExit(2)
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
