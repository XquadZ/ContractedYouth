# -*- coding: utf-8 -*-
"""GAP-2 6단계: thinking 켠 E2 C2 비교 (GAP-1 E2 200건)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
PROMPTS = G2 / "prompts"

sys.path.insert(0, str(G1 / "scripts"))
from llm_server import HOST, MODELS, PORT, SERVER, health, stop_server  # noqa: E402
from run_gap1 import parse_json_output  # noqa: E402

SYSTEM_RAG = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
USER_E2 = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(p, row):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def start_server_thinking(model_key: str):
    stop_server()
    gguf = MODELS[model_key]
    cmd = [
        str(SERVER),
        "-m", str(gguf),
        "--host", HOST,
        "--port", str(PORT),
        "-c", "8192",
        "-ngl", "99",
        "-np", "1",
        "--cache-ram", "8192",
        # no --reasoning off
    ]
    env = os.environ.copy()
    if model_key == "32B":
        env["CUDA_VISIBLE_DEVICES"] = "0,1"
        cmd.extend(["-ts", "0.5,0.5"])
    else:
        env["CUDA_VISIBLE_DEVICES"] = "0"
    log_path = OUT / f"server_{model_key}_thinking.log"
    logf = open(log_path, "w", encoding="utf-8")
    LLAMA_DIR = SERVER.parent
    proc = subprocess.Popen(cmd, cwd=str(LLAMA_DIR), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for _ in range(180):
        if health():
            print(f"thinking server {model_key} up")
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"server exited; see {log_path}")
        time.sleep(2)
    raise TimeoutError(f"not healthy; {log_path}")


def chat_thinking(messages):
    body = {
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "seed": 42,
        "max_tokens": 4096,
        "chat_template_kwargs": {"enable_thinking": True},
        "enable_thinking": True,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r:
        js = json.loads(r.read().decode("utf-8"))
    lat = (time.perf_counter() - t0) * 1000
    msg = js["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    # also extract <think> from content
    m = re.search(r"<think>([\s\S]*?)</think>", content)
    think_from_content = m.group(1) if m else ""
    thinking = reasoning or think_from_content
    # final answer without think
    final = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    return {
        "content": content,
        "final": final,
        "thinking": thinking,
        "thinking_len": len(thinking or ""),
        "latency_ms": lat,
        "raw": js,
    }


def build_msg(item, c2, choices):
    user_body = USER_E2.replace("{clause}", item["clause"]).replace("{choices}", choices)
    # no /no_think
    user = f"<자료>\n{c2}\n</자료>\n\n{user_body}"
    return [{"role": "system", "content": SYSTEM_RAG}, {"role": "user", "content": user}]


def smoke_thinking(model, items, c2, choices, need=3):
    """Reuse prior smoke rows; only run until need successes with thinking_len>0."""
    smoke_p = OUT / f"smoke_thinking_{model}.jsonl"
    existing = load_jsonl(smoke_p)
    done_ids = {r["id"] for r in existing}
    ok = sum(1 for r in existing if (r.get("thinking_len") or 0) > 0)
    lats = [r["latency_ms"] for r in existing if r.get("latency_ms")]
    print(f"smoke reuse {model}: existing={len(existing)} ok={ok}", flush=True)
    for item in items:
        if ok >= need:
            break
        if item["id"] in done_ids:
            continue
        resp = chat_thinking(build_msg(item, c2, choices))
        has = resp["thinking_len"] > 0
        print("think smoke", model, item["id"], "len", resp["thinking_len"], "has", has, "ms", resp["latency_ms"], flush=True)
        if has:
            ok += 1
        if resp.get("latency_ms"):
            lats.append(resp["latency_ms"])
        append_jsonl(smoke_p, {
            "id": item["id"],
            "thinking": (resp["thinking"] or "")[:2000],
            "thinking_len": resp["thinking_len"],
            "final": (resp["final"] or "")[:500],
            "latency_ms": resp["latency_ms"],
        })
        done_ids.add(item["id"])
    mean_lat = (sum(lats) / len(lats)) if lats else None
    return ok >= 1, mean_lat


def run_model(model, n=200, time_budget_h=6, mean_lat_hint=None):
    e2_all = load_jsonl(G1 / "data" / "e2.jsonl")
    c2 = (G1 / "retrieval" / "c2_e1e2_material.txt").read_text(encoding="utf-8")
    choices = json.loads((G1 / "data" / "e2_choices.json").read_text(encoding="utf-8"))["choices_line"]
    outp = OUT / f"{model}_E2_C2_thinking.jsonl"
    done = {r["id"] for r in load_jsonl(outp)}
    notes = {"planned_n": n}
    start_server_thinking(model)
    try:
        smoke_ok, mean_lat = smoke_thinking(model, e2_all, c2, choices, need=3)
        if not smoke_ok:
            meta = {"ok": False, "reason": "thinking text empty in smoke"}
            (OUT / f"thinking_FAIL_{model}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print("THINKING FAIL", model, flush=True)
            return meta
        lat = mean_lat or mean_lat_hint or 300000.0
        est_h_200 = lat * 200 / 1000 / 3600
        est_h_100 = lat * 100 / 1000 / 3600
        n_use = n
        notes = {
            "planned_n": n,
            "smoke_mean_lat_ms": lat,
            "est_h_200": est_h_200,
            "est_h_100": est_h_100,
            "budget_h": time_budget_h,
            "resume_done": len(done),
        }
        if est_h_200 > time_budget_h:
            n_use = 100
            notes["reduced_to"] = 100
            print("reducing n to 100; est_h_200=", est_h_200, flush=True)
            if est_h_100 > time_budget_h:
                n_fit = max(10, int((time_budget_h * 0.85) * 3600 * 1000 / lat))
                n_use = min(100, n_fit)
                notes["reduced_further"] = n_use
                print("further reduce n to", n_use, "to fit budget", flush=True)
        (OUT / f"thinking_plan_{model}.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
        (OUT / "thinking_n_reduced.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
        e2 = e2_all[:n_use]
        t_start = time.time()
        for item in e2:
            if item["id"] in done:
                continue
            elapsed_h = (time.time() - t_start) / 3600
            if elapsed_h > time_budget_h:
                print("time budget hit", model, "elapsed_h", elapsed_h, flush=True)
                notes["stopped_early"] = True
                notes["completed_before_stop"] = len(load_jsonl(outp))
                (OUT / f"thinking_plan_{model}.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
                break
            resp = chat_thinking(build_msg(item, c2, choices))
            parsed, ok = parse_json_output(resp["final"] or resp["content"])
            think_tokens = max(1, resp["thinking_len"] // 2) if resp["thinking"] else 0
            row = {
                "id": item["id"],
                "thinking": resp["thinking"],
                "thinking_len_chars": resp["thinking_len"],
                "thinking_tokens_est": think_tokens,
                "raw_output": resp["content"],
                "final": resp["final"],
                "parsed": parsed,
                "parse_ok": ok,
                "latency_ms": resp["latency_ms"],
            }
            append_jsonl(outp, row)
            done.add(item["id"])
            print(model, item["id"], "think_len", resp["thinking_len"], "ok", ok, "ms", resp["latency_ms"], flush=True)
    finally:
        stop_server()
    return {"ok": True, "n": len(load_jsonl(outp)), "out": str(outp), "plan": notes}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # total stage budget 6h shared across both models
    results = {}
    stage_start = time.time()
    remaining = 6.0
    for model in ("8B", "32B"):
        remaining = 6.0 - (time.time() - stage_start) / 3600
        if remaining < 0.25:
            print("stage budget nearly exhausted; skip", model, flush=True)
            results[model] = {"ok": False, "reason": "stage_budget"}
            break
        results[model] = run_model(model, n=200, time_budget_h=remaining)
        # record global reduce note
        plans = list(OUT.glob("thinking_plan_*.json"))
        if plans:
            (OUT / "thinking_n_reduced.json").write_text(
                json.dumps({p.stem: json.loads(p.read_text(encoding="utf-8")) for p in plans}, indent=2),
                encoding="utf-8",
            )
    (OUT / "thinking_meta.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(results, flush=True)


if __name__ == "__main__":
    main()
