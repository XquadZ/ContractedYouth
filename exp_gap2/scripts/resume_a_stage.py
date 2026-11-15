# -*- coding: utf-8 -*-
"""GAP-2 A단계: 32B C4 → C5. 출력 무영향 부하 완화만.
- sleep 2
- append + flush + fsync
- llama-server 원 설정(cache-ram 8192, -np 1, -ts 0.5,0.5)
- 크래시 시 자동 재시작 금지(프로세스만 종료)
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
RUN_LOG = G2 / "run_log.md"
# C:\gpu_log.csv may be access-denied; prefer project out/
GPU_LOG = G2 / "out" / "gpu_log.csv"
GPU_LOG_FALLBACK = Path(r"C:\gpu_log.csv")
SCRIPTS = G2 / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "exp_gap1" / "scripts"))

from llm_server import chat, health, start_server, stop_server  # noqa: E402
from run_gap1 import parse_json_output  # noqa: E402
from run_gap2 import build_messages_e2, load_ctx, load_jsonl  # noqa: E402

SLEEP_S = 2.0
SETTING = "A"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("cp949", errors="replace").decode("cp949"), flush=True)


def append_run_log(text: str):
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_jsonl_fsync(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def existing_ok_ids(path: Path) -> set:
    ids = set()
    for r in load_jsonl(path):
        if not isinstance(r, dict) or "id" not in r:
            continue
        if r.get("parse_ok") and isinstance(r.get("parsed"), dict) and r["parsed"].get("articles") is not None:
            ids.add(r["id"])
        elif (r.get("raw_output") or "").strip() and not r.get("error"):
            # keep any non-empty successful-looking row
            if r.get("parse_ok"):
                ids.add(r["id"])
    return ids


def gpu_peak_from_log(n_rows=200):
    """Return max temp/power from last n_rows of gpu_log.csv."""
    path = GPU_LOG if GPU_LOG.exists() and GPU_LOG.stat().st_size > 0 else GPU_LOG_FALLBACK
    if not path.exists() or path.stat().st_size == 0:
        return {"max_temp": None, "max_power": None, "n": 0, "path": str(path)}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # skip header if present
        body = lines[1:] if lines and "timestamp" in lines[0].lower() else lines
        tail = body[-n_rows:]
        max_t = None
        max_p = None
        for ln in tail:
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) < 5:
                continue
            try:
                # timestamp,index,temperature.gpu,power.draw,power.limit,...
                t = float(parts[2])
                p = float(parts[3].replace(" W", "").replace("[N/A]", "nan"))
            except Exception:
                continue
            if max_t is None or t > max_t:
                max_t = t
            if max_p is None or (p == p and p > max_p):  # not nan
                max_p = p
        return {"max_temp": max_t, "max_power": max_p, "n": len(tail)}
    except Exception as e:
        return {"max_temp": None, "max_power": None, "n": 0, "err": str(e)}


def ensure_server():
    if health():
        return
    # A단계: 원 설정 그대로 (stable=False → cache-ram 8192)
    start_server("32B", ctx=8192, cache_ram=8192, stable=False)
    time.sleep(3)


def run_cond(cond: str, items: list, ctx: dict):
    outp = OUT / f"32B_E2_{cond}.jsonl"
    done = existing_ok_ids(outp)
    pending = [x for x in items if x["id"] not in done]
    log(f"{cond}: done={len(done)} pending={len(pending)} total={len(items)}")
    append_run_log(f"\n### start {cond} done={len(done)} pending={len(pending)} total={len(items)} @ {datetime.now().isoformat()}\n")

    lat_window = []
    n_ok = 0
    n_fail = 0
    t0 = time.time()

    for i, item in enumerate(pending):
        ensure_server()
        messages = build_messages_e2(cond, item, ctx)
        try:
            resp = chat(messages, temperature=0.0, max_tokens=256)
            raw = resp.get("content") or ""
            parsed, pok = parse_json_output(raw)
            lat = resp.get("latency_total_ms")
            if lat:
                lat_window.append(lat)
            row = {
                "id": item["id"],
                "cond": cond,
                "setting": SETTING,
                "raw_output": raw,
                "parsed": parsed,
                "parse_ok": bool(pok and isinstance(parsed, dict) and parsed.get("articles") is not None),
                "latency_total_ms": lat,
                "error": None,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            if not row["parse_ok"]:
                # still save raw for audit but do not count as done for resume skip
                # Spec: append every item. Keep it; resume uses parse_ok articles check.
                n_fail += 1
            else:
                n_ok += 1
            append_jsonl_fsync(outp, row)
        except Exception as e:
            n_fail += 1
            row = {
                "id": item["id"],
                "cond": cond,
                "setting": SETTING,
                "raw_output": "",
                "parsed": None,
                "parse_ok": False,
                "latency_total_ms": None,
                "error": str(e),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            append_jsonl_fsync(outp, row)
            log(f"{cond} {item['id']} ERROR {e}")
            # do not auto-restart experiment loop forever; try server once
            stop_server()
            time.sleep(2)
            try:
                ensure_server()
            except Exception as e2:
                log(f"server restart failed: {e2}")
                append_run_log(f"\nABORT server restart failed: {e2}\n")
                raise

        done_n = len(done) + n_ok  # approximate
        if (n_ok + n_fail) % 100 == 0:
            peak = gpu_peak_from_log(300)
            mean_lat = (sum(lat_window[-100:]) / len(lat_window[-100:])) if lat_window else None
            msg = (
                f"- progress {cond}: ok={n_ok} fail={n_fail} file_n={len(load_jsonl(outp))} "
                f"elapsed_min={(time.time()-t0)/60:.1f} mean_lat_ms_last100={mean_lat} "
                f"gpu_max_temp={peak.get('max_temp')} gpu_max_power={peak.get('max_power')} "
                f"@ {datetime.now().isoformat(timespec='seconds')}"
            )
            append_run_log(msg + "\n")
            log(msg)

        time.sleep(SLEEP_S)

    summary = {
        "cond": cond,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "file_n": len(load_jsonl(outp)),
        "setting": SETTING,
    }
    append_run_log(f"\n### end {cond}: {json.dumps(summary)}\n")
    return summary


def main():
    # gate: power limit must be 220
    q = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,power.limit", "--format=csv,noheader"],
        text=True,
        errors="replace",
    )
    log(f"power.limit query:\n{q}")
    for ln in q.strip().splitlines():
        if "220" not in ln:
            raise SystemExit(f"ABORT: power.limit not 220W: {ln}")

    ctx = load_ctx()
    stop_server()
    start_server("32B", ctx=8192, cache_ram=8192, stable=False)
    append_run_log(f"\n## server started A-stage @ {datetime.now().isoformat()}\n")

    results = {}
    try:
        results["C4"] = run_cond("C4", ctx["test500"], ctx)
        results["C5"] = run_cond("C5", ctx["test"], ctx)
    finally:
        stop_server()

    (OUT / "a_stage_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    peak = gpu_peak_from_log(5000)
    append_run_log(
        f"\n## A-stage finished @ {datetime.now().isoformat()}\n"
        f"results={json.dumps(results)}\n"
        f"gpu_peak={json.dumps(peak)}\n"
    )
    log(f"DONE {results} peak={peak}")


if __name__ == "__main__":
    main()
