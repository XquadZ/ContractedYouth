# -*- coding: utf-8 -*-
"""Diag B: 8B Q8_0 single-GPU stress. Writes ONLY under exp_gap2/diag/.
Does not touch exp_gap2/out/. No auto-restart on crash.
Usage: python diag_8b_single_gpu.py --gpu 0|1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
DIAG = G2 / "diag"
DATA = G2 / "data"
PROMPTS = G2 / "prompts"

sys.path.insert(0, str(G1 / "scripts"))
from llm_server import HOST, MODELS, PORT, SERVER, chat, health, stop_server  # noqa: E402
from run_gap1 import parse_json_output  # noqa: E402

SYSTEM_RAG = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
USER_E2 = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with (DIAG / "b_run.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def start_8b_on_gpu(gpu: int):
    stop_server()
    gguf = MODELS["8B"]
    cmd = [
        str(SERVER),
        "-m", str(gguf),
        "--host", HOST,
        "--port", str(PORT),
        "-c", "8192",
        "-ngl", "99",
        "-np", "1",
        "--cache-ram", "8192",
        "--reasoning", "off",
        "--reasoning-budget", "0",
    ]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    log_path = DIAG / f"server_8B_gpu{gpu}.log"
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(SERVER.parent), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for _ in range(180):
        if health():
            log(f"server 8B up CUDA_VISIBLE_DEVICES={gpu}")
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early; see {log_path}")
        time.sleep(2)
    raise TimeoutError(f"not healthy; {log_path}")


def build_c5_messages(item, c2, choices, pack):
    material = (
        f"[약관법 조문]\n{c2}\n\n"
        f"[유사 판정 사례] 아래는 비슷한 조항이 과거에 어느 조항 문제로 판정되었는지 보여 주는 참고 사례다. "
        f"사례가 지금 조항과 다를 수 있으니 그대로 따르지 말고 조항 문구를 직접 판단하라.\n{pack}"
    )
    user_body = USER_E2.replace("{clause}", item["clause"]).replace("{choices}", choices) + "\n/no_think"
    user = f"<자료>\n{material}\n</자료>\n\n{user_body}"
    return [{"role": "system", "content": SYSTEM_RAG}, {"role": "user", "content": user}]


def gpu_query():
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,temperature.gpu,power.draw,power.limit,clocks.sm,memory.used", "--format=csv"],
        text=True,
        errors="replace",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", type=int, required=True, choices=[0, 1])
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--warmup-sec", type=int, default=60)
    args = ap.parse_args()
    DIAG.mkdir(parents=True, exist_ok=True)

    state = {
        "gpu": args.gpu,
        "started": datetime.now().isoformat(timespec="seconds"),
        "n_target": args.n,
        "n_done": 0,
        "last_id": None,
        "status": "starting",
    }
    state_path = DIAG / f"b_gpu{args.gpu}_state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    test = load_jsonl(DATA / "e2_test1000.jsonl")[: args.n]
    c2 = (G1 / "retrieval" / "c2_e1e2_material.txt").read_text(encoding="utf-8")
    choices = json.loads((G1 / "data" / "e2_choices.json").read_text(encoding="utf-8"))["choices_line"]
    packs = {}
    for p in (G2 / "retrieval" / "c5_neighbor_packs.json", DATA / "e2_c5_neighbors.json"):
        if p.exists():
            packs = json.loads(p.read_text(encoding="utf-8"))
            break

    outp = DIAG / f"b_8B_gpu{args.gpu}_C5_n{args.n}.jsonl"
    # resume within diag file only
    done = set()
    if outp.exists():
        for ln in outp.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                done.add(json.loads(ln)["id"])
            except Exception:
                pass

    log(f"warmup {args.warmup_sec}s before start GPU{args.gpu}")
    time.sleep(args.warmup_sec)
    (DIAG / f"b_gpu{args.gpu}_pre_query.txt").write_text(gpu_query(), encoding="utf-8")

    start_8b_on_gpu(args.gpu)
    state["status"] = "running"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    n_ok = 0
    max_temp = {0: None, 1: None}
    max_power = {0: None, 1: None}
    try:
        for item in test:
            if item["id"] in done:
                continue
            messages = build_c5_messages(item, c2, choices, packs.get(item["id"], ""))
            try:
                resp = chat(messages, temperature=0.0, max_tokens=256)
                raw = resp.get("content") or ""
                parsed, pok = parse_json_output(raw)
                row = {
                    "id": item["id"],
                    "gpu": args.gpu,
                    "raw_output": raw,
                    "parsed": parsed,
                    "parse_ok": pok,
                    "latency_total_ms": resp.get("latency_total_ms"),
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            except Exception as e:
                row = {
                    "id": item["id"],
                    "gpu": args.gpu,
                    "error": str(e),
                    "parse_ok": False,
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            with outp.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os_fsync = getattr(os, "fsync", None)
                if os_fsync:
                    os_fsync(f.fileno())
            n_ok += 1
            done.add(item["id"])
            state["n_done"] = n_ok
            state["last_id"] = item["id"]
            state["last_ts"] = row["ts"]
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            # sample nvidia-smi peaks
            try:
                q = gpu_query().strip().splitlines()[1:]
                for ln in q:
                    parts = [p.strip() for p in ln.split(",")]
                    idx = int(parts[0])
                    import re

                    def num(s):
                        m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
                        return float(m.group()) if m else None

                    t = num(parts[1])
                    p = num(parts[2])
                    if t is not None and (max_temp[idx] is None or t > max_temp[idx]):
                        max_temp[idx] = t
                    if p is not None and (max_power[idx] is None or p > max_power[idx]):
                        max_power[idx] = p
            except Exception:
                pass

            if n_ok % 10 == 0:
                log(f"GPU{args.gpu} done={n_ok}/{args.n} last={item['id']} maxT={max_temp} maxP={max_power}")
            time.sleep(2.0)
        state["status"] = "finished"
    finally:
        stop_server()
        state["ended"] = datetime.now().isoformat(timespec="seconds")
        state["max_temp"] = max_temp
        state["max_power"] = max_power
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        summary = {
            "gpu": args.gpu,
            "n_done": n_ok,
            "n_target": args.n,
            "max_temp": max_temp,
            "max_power": max_power,
            "out": str(outp),
            "ended": state.get("ended"),
        }
        (DIAG / f"b_gpu{args.gpu}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        log(f"SUMMARY {json.dumps(summary)}")


if __name__ == "__main__":
    main()
