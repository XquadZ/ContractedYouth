# -*- coding: utf-8 -*-
"""EXAONE 4.0 32B Q4_K_M 을 8083에 띄운다. A.X(8082)는 건드리지 않는다.
설정은 start_ax.py 와 동일(ctx 8192, ngl 99, reasoning off). 모델 없으면 중단.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag.paths import APP, LLAMA, SERVER, WORK  # noqa: E402

LOG = APP / "out"
MODELS = WORK / "data_local" / "models"
HEALTH = "http://127.0.0.1:8083/health"
PORT = 8083


def find_gguf() -> Path | None:
    patterns = (
        "*EXAONE*4*32B*Q4_K_M*.gguf",
        "*EXAONE*32B*Q4*.gguf",
        "*exaone*4*32B*Q4*.gguf",
        "*exaone*32B*Q4_K_M*.gguf",
        "*EXAONE*.gguf",
        "*exaone*.gguf",
    )
    hits: list[Path] = []
    for pat in patterns:
        hits.extend(MODELS.glob(pat))
        hits.extend(MODELS.rglob(pat))
    # 중복 제거, 큰 파일 우선
    uniq = sorted({p.resolve() for p in hits if p.is_file()}, key=lambda p: -p.stat().st_size)
    return uniq[0] if uniq else None


def health() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def port_listening(port: int) -> bool:
    """8083 등이 이미 LISTENING인지 netstat으로 확인."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
    except Exception:
        return False
    suffix = f":{port}"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[3] != "LISTENING":
            continue
        if parts[1].endswith(suffix):
            return True
    return False


def llama_server_running() -> bool:
    """llama-server.exe 프로세스가 하나라도 있는지."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/NH"],
            text=True,
            errors="replace",
        )
    except Exception:
        return False
    return "llama-server.exe" in out.lower()


def existing_instance() -> bool:
    return port_listening(PORT) or llama_server_running()


def wait_existing_health(max_rounds: int = 300) -> bool:
    """기존 인스턴스가 있으면 새 기동 없이 health 200까지 대기."""
    print("EXISTING_INSTANCE wait health 8083", flush=True)
    for i in range(max_rounds):
        if health():
            print("EXAONE_UP 8083 (existing)", flush=True)
            return True
        if not existing_instance():
            print("EXISTING_GONE", flush=True)
            return False
        if i % 15 == 0:
            print("WAIT_HEALTH_EXISTING", i * 2, "sec", flush=True)
        time.sleep(2)
    raise SystemExit("server_not_healthy_existing")


def main() -> None:
    if health():
        print("ALREADY_UP 8083", flush=True)
        return
    if existing_instance():
        if wait_existing_health():
            return
        # 기존 프로세스가 사라진 경우에만 아래로 내려가 새로 기동
    if not SERVER.exists():
        raise SystemExit(f"missing {SERVER}")
    gguf = find_gguf()
    if gguf is None:
        print("STOP missing EXAONE GGUF under", MODELS, flush=True)
        raise SystemExit(3)
    print("GGUF", gguf, "size_gb", round(gguf.stat().st_size / 1e9, 2), flush=True)
    LOG.mkdir(parents=True, exist_ok=True)
    # A.X start_ax.py 와 동일 플래그. 포트만 8083. CUDA는 같은 GPU 공유(동시 로드 시 VRAM 주의).
    cmd = [
        str(SERVER),
        "-m",
        str(gguf),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
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
    log_path = LOG / "llama_8083.log"
    logf = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "0"
    print("CMD", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=str(LLAMA), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for i in range(300):
        if health():
            print("EXAONE_UP 8083", flush=True)
            break
        if proc.poll() is not None:
            logf.flush()
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            print("STOP process_exited\n", tail, flush=True)
            # llama.cpp 업데이트 필요 신호가 로그에 있으면 호출자에게 알림
            low = tail.lower()
            if any(k in low for k in ("unknown model", "unsupported", "failed to load", "arch not")):
                print("ASK_LLAMA_UPDATE possible model load failure — check llama.cpp version", flush=True)
            raise SystemExit(2)
        if i % 15 == 0:
            print("WAIT_HEALTH", i * 2, "sec", flush=True)
        time.sleep(2)
    else:
        proc.kill()
        raise SystemExit("server_not_healthy")
    (LOG / "exaone_up.json").write_text(
        json.dumps({"port": PORT, "gguf": str(gguf), "cmd": cmd}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        while True:
            time.sleep(30)
            if proc.poll() is not None:
                raise SystemExit(2)
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
