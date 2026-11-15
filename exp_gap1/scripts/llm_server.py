# -*- coding: utf-8 -*-
"""llama-server 기동/종료 헬퍼. 한글 경로는 pilot_root GGUF 사용."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
LLAMA_DIR = ROOT / "tools" / "llama.cpp"
SERVER = LLAMA_DIR / "llama-server.exe"
HOST = "127.0.0.1"
PORT = 8080

MODELS = {
    "8B": Path(r"C:\Users\DMLAB\pilot_root\models\Qwen3-8B-GGUF\Qwen3-8B-Q8_0.gguf"),
    "32B": Path(r"C:\Users\DMLAB\pilot_root\models\Qwen3-32B-GGUF\Qwen3-32B-Q6_K.gguf"),
}


def health(port=PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{port}/v1/models", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False


def stop_server():
    # kill by port
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{PORT}"', shell=True, text=True, errors="replace"
        )
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    except Exception:
        pass
    time.sleep(1)


def start_server(model_key: str, port=PORT, ctx=8192, cache_ram: int | None = None, stable: bool = False) -> subprocess.Popen:
    stop_server()
    gguf = MODELS[model_key]
    if not gguf.exists():
        raise FileNotFoundError(str(gguf))
    if not SERVER.exists():
        raise FileNotFoundError(str(SERVER))
    # 32B Q6_K ~25GB → TITAN RTX 24GB×2에 텐서 분할. 8B는 GPU0.
    # KV/prompt prefix cache: --cache-ram; Qwen3 thinking 끔: --reasoning off
    # stable=True: GPU 드라이버 행 완화용(출력 품질과 무관한 서버 메모리/환경만 조정)
    if cache_ram is None:
        cache_ram = 2048 if (stable and model_key == "32B") else 8192
    cmd = [
        str(SERVER),
        "-m",
        str(gguf),
        "--host",
        HOST,
        "--port",
        str(port),
        "-c",
        str(ctx),
        "-ngl",
        "99",
        "-np",
        "1",
        "--cache-ram",
        str(cache_ram),
        "--reasoning",
        "off",
        "--reasoning-budget",
        "0",
    ]
    env = os.environ.copy()
    if stable:
        env["CUDA_DEVICE_MAX_CONNECTIONS"] = "1"
    if model_key == "32B":
        env["CUDA_VISIBLE_DEVICES"] = "0,1"
        cmd.extend(["-ts", "0.5,0.5"])
    else:
        env["CUDA_VISIBLE_DEVICES"] = "0"
    log_path = ROOT / "exp_gap1" / "out" / f"server_{model_key}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(LLAMA_DIR), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for i in range(180):
        if health(port):
            print(f"server {model_key} up on {port}")
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early; see {log_path}")
        time.sleep(2)
    raise TimeoutError(f"server not healthy; see {log_path}")


def chat(messages, temperature=0.0, max_tokens=256, port=PORT) -> dict:
    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "repeat_penalty": 1.05,
        "chat_template_kwargs": {"enable_thinking": False},
        "enable_thinking": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1200) as r:
        raw = r.read().decode("utf-8")
    t1 = time.perf_counter()
    js = json.loads(raw)
    usage = js.get("timings") or js.get("usage") or {}
    msg = js["choices"][0]["message"]
    content = msg.get("content") or ""
    # some servers put answer only after stripping reasoning_content
    if not content.strip() and msg.get("reasoning_content"):
        content = ""  # thinking-only = fail empty
    return {
        "content": content,
        "raw_response": js,
        "latency_total_ms": (t1 - t0) * 1000,
        "latency_prompt_ms": usage.get("prompt_ms") or usage.get("prompt_n") or None,
        "latency_gen_ms": usage.get("predicted_ms") or usage.get("predicted_n") or None,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["8B", "32B"])
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    if args.stop:
        stop_server()
    else:
        start_server(args.model)
        print("running; Ctrl+C to stop")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            stop_server()
