# -*- coding: utf-8 -*-
"""Resume 32B C5 only (A-stage). PYTHONUTF8. ASCII logs. log every 50."""
from __future__ import annotations

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
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
RUN_LOG = G2 / "run_log.md"
GPU_LOG = G2 / "out" / "gpu_log.csv"
SCRIPTS = G2 / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "exp_gap1" / "scripts"))

from llm_server import chat, health, start_server, stop_server  # noqa: E402
from resume_a_stage import (  # noqa: E402
    SLEEP_S,
    SETTING,
    append_jsonl_fsync,
    append_run_log,
    existing_ok_ids,
    gpu_peak_from_log,
    log,
)
from run_gap1 import parse_json_output  # noqa: E402
from run_gap2 import build_messages_e2, load_ctx, load_jsonl  # noqa: E402


def safe_progress_log(msg: str):
    try:
        append_run_log(msg + "\n")
        log(msg)
    except Exception as e:
        try:
            sys.stderr.write(f"progress_log_fail: {e}\n")
        except Exception:
            pass


def ensure_server():
    if health():
        return
    start_server("32B", ctx=8192, cache_ram=8192, stable=False)
    time.sleep(3)


def main():
    q = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,power.limit,clocks.max.sm,clocks.sm,temperature.gpu", "--format=csv"],
        text=True,
        errors="replace",
    )
    append_run_log(f"\n## C5 resume precheck @ {datetime.now().isoformat(timespec='seconds')}\n```\n{q}\n```\n")
    print(q, flush=True)
    for ln in q.strip().splitlines()[1:]:
        if "220" not in ln.split(",")[1]:
            raise SystemExit(f"ABORT power.limit not 220: {ln}")

    ctx = load_ctx()
    if not health():
        start_server("32B", ctx=8192, cache_ram=8192, stable=False)

    outp = OUT / "32B_E2_C5.jsonl"
    done = existing_ok_ids(outp)
    pending = [x for x in ctx["test"] if x["id"] not in done]
    log(f"C5: done={len(done)} pending={len(pending)} total=1000")
    append_run_log(f"\n### C5 resume done={len(done)} pending={len(pending)}\n")

    lat_window = []
    n_ok = n_fail = 0
    t0 = time.time()
    for i, item in enumerate(pending):
        ensure_server()
        messages = build_messages_e2("C5", item, ctx)
        try:
            resp = chat(messages, temperature=0.0, max_tokens=256)
            raw = resp.get("content") or ""
            parsed, pok = parse_json_output(raw)
            lat = resp.get("latency_total_ms")
            if lat:
                lat_window.append(float(lat))
            row = {
                "id": item["id"],
                "cond": "C5",
                "setting": SETTING,
                "raw_output": raw,
                "parsed": parsed,
                "parse_ok": bool(pok and isinstance(parsed, dict) and parsed.get("articles") is not None),
                "latency_total_ms": lat,
                "error": None,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            if row["parse_ok"]:
                n_ok += 1
            else:
                n_fail += 1
            append_jsonl_fsync(outp, row)
        except Exception as e:
            n_fail += 1
            append_jsonl_fsync(
                outp,
                {
                    "id": item["id"],
                    "cond": "C5",
                    "setting": SETTING,
                    "raw_output": "",
                    "parsed": None,
                    "parse_ok": False,
                    "error": str(e),
                    "ts": datetime.now().isoformat(timespec="seconds"),
                },
            )
            log(f"C5 {item['id']} ERROR {e}")
            stop_server()
            time.sleep(2)
            ensure_server()

        if (n_ok + n_fail) % 50 == 0:
            peak = gpu_peak_from_log(400)
            mean_lat = sum(lat_window[-50:]) / len(lat_window[-50:]) if lat_window else None
            msg = (
                f"- C5 progress ok={n_ok} fail={n_fail} file_n={len(load_jsonl(outp))} "
                f"elapsed_min={(time.time()-t0)/60:.1f} mean_lat_ms_last50={mean_lat} "
                f"gpu_max_temp={peak.get('max_temp')} gpu_max_power={peak.get('max_power')} "
                f"@ {datetime.now().isoformat(timespec='seconds')}"
            )
            safe_progress_log(msg)
        time.sleep(SLEEP_S)

    summary = {"n_ok": n_ok, "n_fail": n_fail, "file_n": len(load_jsonl(outp))}
    append_run_log(f"\n### C5 end {json.dumps(summary)}\n")
    log(f"DONE C5 {summary}")


if __name__ == "__main__":
    main()
