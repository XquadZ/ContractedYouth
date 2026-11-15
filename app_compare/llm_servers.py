# -*- coding: utf-8 -*-
"""Qwen3-8B(8081)와 A.X 4.0 Light(8082)를 같은 4090에 띄운다.

ctx 8192, -np 1, cache-prompt. thinking 은 요청에서 켠다.
둘 다 올라가지 않으면 프로세스를 끄고 vram_fail.json 을 남긴 뒤 종료한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
LLAMA = WORK / "data_local" / "llama.cpp" / "b11755"
SERVER = LLAMA / "llama-server.exe"
APP = Path(__file__).resolve().parent
LOG = APP / "logs"
MODELS = {
    8081: WORK / "data_local" / "models" / "Qwen3-8B-Q8_0.gguf",
    8082: WORK / "data_local" / "models" / "A.X-4.0-Light-Q8_0.gguf",
}


def health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def smi() -> str:
    proc = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or proc.stderr or "").strip()


def start(port: int) -> subprocess.Popen:
    cmd = [
        str(SERVER),
        "-m",
        str(MODELS[port]),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        "8192",
        "-ngl",
        "99",
        "-np",
        "1",
        "--cache-prompt",
        "--reasoning",
        "auto",
    ]
    logf = (LOG / f"llama_{port}.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "0"
    return subprocess.Popen(cmd, cwd=str(LLAMA), stdout=logf, stderr=subprocess.STDOUT, env=env)


def wait(proc: subprocess.Popen, port: int) -> bool:
    for _ in range(180):
        if health(port):
            return True
        if proc.poll() is not None:
            return False
        time.sleep(2)
    return False


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    before = smi()
    first = start(8081)
    if not wait(first, 8081):
        (LOG / "vram_fail.json").write_text(
            json.dumps({"stage": "qwen", "before": before, "after": smi()}, ensure_ascii=False),
            encoding="utf-8",
        )
        raise SystemExit(2)
    mid = smi()
    second = start(8082)
    if not wait(second, 8082):
        first.terminate()
        (LOG / "vram_fail.json").write_text(
            json.dumps({"stage": "ax", "before": before, "after_qwen": mid, "after": smi()}, ensure_ascii=False),
            encoding="utf-8",
        )
        raise SystemExit(2)
    record = {"before": before, "after_qwen": mid, "after_both": smi(), "ports": [8081, 8082], "reasoning": "auto"}
    (LOG / "vram.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BOTH_UP", record["after_both"], flush=True)
    try:
        while True:
            time.sleep(30)
            if first.poll() is not None or second.poll() is not None:
                (LOG / "vram_fail.json").write_text(
                    json.dumps({"stage": "died", "qwen": first.poll(), "ax": second.poll(), "smi": smi()}),
                    encoding="utf-8",
                )
                raise SystemExit(2)
    except KeyboardInterrupt:
        first.terminate()
        second.terminate()


if __name__ == "__main__":
    main()
