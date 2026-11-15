# -*- coding: utf-8 -*-
"""32B C5/C4 재개 — 체크포인트·서버 주기 재시작·실패 행 미기록.

원천 원인(nvlddmkm / DPC_WATCHDOG)은 OS·드라이버 쪽이라 소프트웨어만으로
완전 차단은 불가. 아래는 재발 완화 + 끊겨도 이어서 가능하게 함:
- 성공 행만 append (연결 실패를 done으로 고정하지 않음)
- N건마다 llama-server 재시작 (GPU 드라이버 상태 리셋)
- 배치 사이 cooldown
- heartbeat JSON 매 건 갱신
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
SCRIPTS = G2 / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "exp_gap1" / "scripts"))

from llm_server import chat, health, start_server, stop_server  # noqa: E402
from repair_failed_e2 import is_ok, purge_bad  # noqa: E402
from run_gap1 import parse_json_output  # noqa: E402
from run_gap2 import append_jsonl, build_messages_e2, load_ctx, load_jsonl  # noqa: E402

RESTART_EVERY = 10          # 성공 N건마다 서버 재시작 (크래시 완화)
COOLDOWN_S = 15             # 재시작 후 대기
RETRY_PER_ITEM = 3
BATCH_SLEEP_S = 1.5         # 건 사이 휴식
POWER_LIMIT_W = 220         # 관리자일 때만 적용됨
HEARTBEAT = OUT / "resume_heartbeat.json"
ABORT_IF_GPU_LOST = True


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def set_gpu_power_limit(watts: int):
    try:
        for i in (0, 1):
            r = subprocess.run(
                ["nvidia-smi", "-i", str(i), "-pl", str(watts)],
                capture_output=True,
                text=True,
            )
            log(f"power limit GPU{i}={watts}W rc={r.returncode} {(r.stdout or r.stderr or '')[:80]}")
    except Exception as e:
        log(f"power limit skip: {e}")


def gpu_ok() -> bool:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 or "GPU is lost" in out or "Unable to determine" in out:
            log(f"GPU NOT OK: {out[:200]}")
            return False
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        if len(lines) < 2:
            log(f"GPU count < 2: {lines}")
            return False
        return True
    except Exception as e:
        log(f"gpu_ok check failed: {e}")
        return False


def ensure_gpu_or_abort():
    if ABORT_IF_GPU_LOST and not gpu_ok():
        heartbeat({"status": "abort_gpu_lost"})
        raise RuntimeError("GPU lost/unavailable — reboot required. Aborting cleanly.")


def heartbeat(payload: dict):
    payload = dict(payload)
    payload["ts"] = datetime.now().isoformat(timespec="seconds")
    HEARTBEAT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_server(model="32B"):
    ensure_gpu_or_abort()
    if health():
        return
    log("server down → restart")
    start_server(model, stable=True)
    time.sleep(COOLDOWN_S)


def run_cond(model: str, cond: str, items: list, ctx: dict):
    outp = OUT / f"{model}_E2_{cond}.jsonl"
    kept, removed = purge_bad(outp)
    log(f"purge {outp.name}: kept={kept} removed={removed}")
    done = {r["id"] for r in load_jsonl(outp) if is_ok(r)}
    pending = [x for x in items if x["id"] not in done]
    log(f"{cond}: pending={len(pending)} / total={len(items)}")

    ok_since_restart = 0
    n_ok = 0
    n_fail = 0
    t0 = time.time()

    for i, item in enumerate(pending):
        ensure_server(model)
        messages = build_messages_e2(cond, item, ctx)
        row = None
        last_err = None
        for attempt in range(1, RETRY_PER_ITEM + 1):
            try:
                if not health():
                    ensure_gpu_or_abort()
                    start_server(model, stable=True)
                    time.sleep(COOLDOWN_S)
                resp = chat(messages, temperature=0.0, max_tokens=256)
                raw = resp.get("content") or ""
                parsed, pok = parse_json_output(raw)
                if pok and isinstance(parsed, dict) and parsed.get("articles") is not None:
                    row = {
                        "id": item["id"],
                        "cond": cond,
                        "raw_output": raw,
                        "parsed": parsed,
                        "parse_ok": True,
                        "latency_total_ms": resp.get("latency_total_ms"),
                        "error": None,
                        "attempt": attempt,
                    }
                    break
                last_err = f"parse_fail raw={raw[:80]!r}"
            except Exception as e:
                last_err = str(e)
                log(f"{cond} {item['id']} attempt {attempt} err: {last_err[:120]}")
                # connection / server death → restart and retry, do NOT append
                stop_server()
                time.sleep(2)
                try:
                    ensure_gpu_or_abort()
                    start_server(model, stable=True)
                    time.sleep(COOLDOWN_S)
                except Exception as e2:
                    log(f"restart failed: {e2}")
                    time.sleep(10)

        if row is None:
            n_fail += 1
            heartbeat(
                {
                    "cond": cond,
                    "id": item["id"],
                    "status": "fail_skip",
                    "error": last_err,
                    "done_ok": len(done) + n_ok,
                    "pending_left": len(pending) - i - 1,
                    "n_ok": n_ok,
                    "n_fail": n_fail,
                }
            )
            log(f"SKIP {cond} {item['id']} after retries: {last_err}")
            continue

        append_jsonl(outp, row)
        done.add(item["id"])
        n_ok += 1
        ok_since_restart += 1
        heartbeat(
            {
                "cond": cond,
                "id": item["id"],
                "status": "ok",
                "done_ok": len(done),
                "pending_left": len(pending) - i - 1,
                "n_ok": n_ok,
                "n_fail": n_fail,
                "elapsed_min": round((time.time() - t0) / 60, 1),
                "file": str(outp),
            }
        )
        if (n_ok % 10) == 0 or i == 0:
            log(f"{cond} ok={n_ok} fail={n_fail} id={item['id']} file_n={len(load_jsonl(outp))}")

        if ok_since_restart >= RESTART_EVERY:
            log(f"periodic restart after {ok_since_restart} ok")
            stop_server()
            time.sleep(5)
            ensure_gpu_or_abort()
            start_server(model, stable=True)
            time.sleep(COOLDOWN_S)
            ok_since_restart = 0
        else:
            time.sleep(BATCH_SLEEP_S)

    return {"cond": cond, "n_ok": n_ok, "n_fail": n_fail, "file_n": len(load_jsonl(outp))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_gpu_or_abort()
    set_gpu_power_limit(POWER_LIMIT_W)
    ctx = load_ctx()
    stop_server()
    start_server("32B", stable=True)
    time.sleep(COOLDOWN_S)
    results = {}
    try:
        results["C5"] = run_cond("32B", "C5", ctx["test"], ctx)
        results["C4"] = run_cond("32B", "C4", ctx["test500"], ctx)
    finally:
        stop_server()

    verify = {}
    for cond, n_exp in (("C2", 1000), ("C5", 1000), ("C4", 500)):
        rows = [r for r in load_jsonl(OUT / f"32B_E2_{cond}.jsonl") if is_ok(r)]
        verify[cond] = {"ok": len(rows), "expected": n_exp}
        log(f"VERIFY 32B {cond}: ok={len(rows)} expected={n_exp}")
    (OUT / "resume_32b_verify.json").write_text(
        json.dumps({"results": results, "verify": verify, "ts": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    heartbeat({"status": "finished", "verify": verify})
    log("DONE")


if __name__ == "__main__":
    main()
