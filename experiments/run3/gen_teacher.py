# -*- coding: utf-8 -*-
"""3-2. 교사(Qwen3-32B) 해설 생성."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from common import (
    LLAMA_SERVER,
    QWEN3_GGUF,
    RUN3,
    TEACHER_SYSTEM,
    TEACHER_USER,
    append_jsonl,
    existing_ids,
    load_jsonl,
    log,
    make_tqdm,
)

PORT = 8080
BASE_URL = f"http://127.0.0.1:{PORT}"


def wait_ready(proc: subprocess.Popen, timeout: int = 900) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited early code={proc.returncode}")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("llama-server not ready")


def start_server(log_path: Path) -> subprocess.Popen:
    cmd = [
        str(LLAMA_SERVER),
        "-m", str(QWEN3_GGUF),
        "-ngl", "99",
        "--tensor-split", "1,1",
        "-c", "8192",
        "--port", str(PORT),
        "--host", "127.0.0.1",
        "--jinja",
    ]
    log("START: " + " ".join(cmd))
    logf = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd, stdout=logf, stderr=subprocess.STDOUT, cwd=str(LLAMA_SERVER.parent)
    )
    proc._logf = logf  # type: ignore[attr-defined]
    wait_ready(proc)
    log(f"server ready pid={proc.pid}")
    return proc


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=60)
    finally:
        logf = getattr(proc, "_logf", None)
        if logf:
            logf.close()
    # kill stragglers
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True,
    )


def chat(messages: list[dict]) -> tuple[str, int, float]:
    body = {
        "messages": messages,
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 900,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    content = payload["choices"][0]["message"].get("content") or ""
    usage = payload.get("usage") or {}
    out_tokens = int(usage.get("completion_tokens", -1))
    return content, out_tokens, elapsed


def nvidia_smi_snapshot() -> str:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"nvidia-smi failed: {e}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=Path, default=RUN3 / "items.jsonl")
    ap.add_argument("--out", type=Path, default=RUN3 / "teacher_outputs.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="0=all")
    ap.add_argument("--server-log", type=Path, default=RUN3 / "llama_server_teacher.log")
    args = ap.parse_args()

    if not LLAMA_SERVER.exists() or not QWEN3_GGUF.exists():
        log(f"missing llama or gguf: {LLAMA_SERVER.exists()} {QWEN3_GGUF.exists()}")
        return 1

    items = load_jsonl(args.items)
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    done = existing_ids(args.out, "id")
    todo = [r for r in items if str(r["id"]) not in done]
    log(f"items={len(items)} done={len(done)} todo={len(todo)}")

    if not todo:
        log("nothing to generate")
        return 0

    proc = None
    try:
        proc = start_server(args.server_log)
        pbar = make_tqdm(todo, desc="gen_teacher", unit="item")
        for r in pbar:
            pbar.set_postfix_str(r["id"], refresh=False)
            user = TEACHER_USER.format(question=r["question"], answer=r["answer"])
            user = user + "\n\n/no_think"
            messages = [
                {"role": "system", "content": TEACHER_SYSTEM},
                {"role": "user", "content": user},
            ]
            try:
                content, out_tokens, elapsed = chat(messages)
            except Exception as e:
                content = f"[ERROR] {type(e).__name__}: {e}"
                out_tokens, elapsed = -1, -1.0
                log(content)
            append_jsonl(args.out, {
                "id": r["id"],
                "domain": r["domain"],
                "question": r["question"],
                "answer": r["answer"],
                "output": content,
                "gen_sec": round(elapsed, 3) if elapsed >= 0 else elapsed,
                "out_tokens": out_tokens,
            })
            log(f"{r['id']} gen_sec={elapsed:.2f} tokens={out_tokens}")
        pbar.close()
    finally:
        stop_server(proc)
        time.sleep(3)
        smi = nvidia_smi_snapshot()
        log("nvidia-smi after stop:")
        log(smi)
        (RUN3 / "nvidia_smi_after_teacher.txt").write_text(smi + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
