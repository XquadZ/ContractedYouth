# -*- coding: utf-8 -*-
"""T1: Qwen3-32B GGUF llama-server 문맥 길이별 실측."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
RUNTIME = Path(r"C:\Users\DMLAB\pilot_root")
PREP = ROOT / "prep_contract"
LLAMA = RUNTIME / "tools" / "llama.cpp" / "llama-server.exe"
GGUF = RUNTIME / "models" / "Qwen3-32B-GGUF" / "Qwen3-32B-Q6_K.gguf"
PORT = 8088
CTXS = [4096, 8192, 16384]
OUT_TOKENS = 512


def nvidia_smi() -> str:
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
         "--format=csv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (r.stdout or r.stderr or "").strip()


def stop_llama() -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True,
    )
    time.sleep(2)


def build_korean_prompt(n_chars: int) -> str:
    # reuse existing Korean text
    chunks = []
    for p in [
        ROOT / "run3" / "items.jsonl",
        ROOT / "pilot" / "train_pool_lawqa.jsonl",
        ROOT / "AUDIT_SAMPLES.jsonl",
    ]:
        if not p.exists():
            continue
        with p.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                chunks.append(str(r.get("question", "")) + "\n" + str(r.get("answer", "")))
                if sum(len(c) for c in chunks) > n_chars + 5000:
                    break
        if sum(len(c) for c in chunks) > n_chars + 5000:
            break
    text = "\n\n".join(chunks) if chunks else ("계약서 조항 검토 문장. " * 2000)
    while len(text) < n_chars:
        text += "\n" + text
    return text[:n_chars]


def wait_ready(timeout: int = 600) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def start_server(ctx: int, log_path: Path) -> subprocess.Popen:
    cmd = [
        str(LLAMA),
        "-m", str(GGUF),
        "-ngl", "99",
        "--tensor-split", "1,1",
        "-c", str(ctx),
        "--port", str(PORT),
        "--host", "127.0.0.1",
        "--jinja",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(log_path, "w", encoding="utf-8", errors="replace")
    lf.write("CMD: " + " ".join(cmd) + "\n")
    lf.flush()
    proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(LLAMA.parent))
    proc._lf = lf  # type: ignore
    return proc


def chat(prompt: str, max_tokens: int = OUT_TOKENS) -> dict:
    body = {
        "messages": [
            {"role": "system", "content": "너는 계약서 조항을 검토하는 안내 AI다. /no_think"},
            {"role": "user", "content": prompt + "\n\n위 내용을 바탕으로 핵심 쟁점 5개를 짧게 나열하세요.\n/no_think"},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    usage = payload.get("usage") or {}
    # timings may be in llama.cpp extensions
    timings = payload.get("timings") or {}
    return {
        "elapsed_sec": round(elapsed, 3),
        "usage": usage,
        "timings": timings,
        "content_preview": ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")[:200],
        "raw_keys": list(payload.keys()),
    }


def estimate_chars_for_tokens(target_tokens: int) -> int:
    # Korean ~1.5-2 chars/token rough; use 1.7 and refine via /tokenize if available
    return int(target_tokens * 1.8)


def tokenize_len(text: str) -> int:
    try:
        data = json.dumps({"content": text}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/tokenize",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        tokens = payload.get("tokens") or payload.get("tokens")
        if isinstance(tokens, list):
            return len(tokens)
    except Exception:
        pass
    # fallback heuristic
    return max(1, int(len(text) / 1.8))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results = []
    PREP.mkdir(parents=True, exist_ok=True)
    if not LLAMA.exists() or not GGUF.exists():
        print(f"missing llama or gguf: {LLAMA.exists()} {GGUF.exists()}")
        (PREP / "t1_teacher_results.json").write_text(
            json.dumps({"error": "missing binaries", "llama": str(LLAMA), "gguf": str(GGUF)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1

    for ctx in CTXS:
        rec = {
            "model": "Qwen3-32B-Q6_K.gguf",
            "model_path": str(GGUF),
            "ctx": ctx,
            "target_input_tokens": int(ctx * 0.8),
            "max_new_tokens": OUT_TOKENS,
        }
        stop_llama()
        log_path = PREP / "t1_logs" / f"llama_ctx{ctx}.log"
        print(f"=== START ctx={ctx} ===", flush=True)
        try:
            proc = start_server(ctx, log_path)
            ready = wait_ready(900)
            rec["load_ok"] = ready
            rec["server_pid"] = proc.pid
            rec["vram_after_load"] = nvidia_smi()
            if not ready:
                # capture log tail
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                log_txt = read_tail(log_path, 80)
                rec["error"] = "server not ready"
                rec["server_log_tail"] = log_txt
                if proc.poll() is None:
                    stop_llama()
                results.append(rec)
                print(json.dumps(rec, ensure_ascii=False)[:500], flush=True)
                continue

            # build prompt ~80% tokens
            target_tok = int(ctx * 0.8)
            # binary search char length
            lo, hi = 1000, estimate_chars_for_tokens(target_tok) * 2
            best = build_korean_prompt(estimate_chars_for_tokens(target_tok))
            for _ in range(8):
                mid = (lo + hi) // 2
                cand = build_korean_prompt(mid)
                n = tokenize_len(cand)
                if n < target_tok:
                    lo = mid
                    best = cand
                else:
                    hi = mid
                    best = cand
                if abs(n - target_tok) < max(50, target_tok * 0.02):
                    break
            n_in = tokenize_len(best)
            rec["input_tokens_measured"] = n_in
            rec["input_chars"] = len(best)

            try:
                out = chat(best, OUT_TOKENS)
                rec["infer_ok"] = True
                rec.update(out)
                # derive tok/s
                timings = out.get("timings") or {}
                usage = out.get("usage") or {}
                prompt_n = usage.get("prompt_tokens") or n_in
                gen_n = usage.get("completion_tokens") or OUT_TOKENS
                if timings.get("prompt_per_second") is not None:
                    rec["prompt_tok_s"] = timings.get("prompt_per_second")
                elif timings.get("prompt_ms") and prompt_n:
                    rec["prompt_tok_s"] = round(prompt_n / (timings["prompt_ms"] / 1000.0), 3)
                else:
                    rec["prompt_tok_s"] = "미확인"
                if timings.get("predicted_per_second") is not None:
                    rec["gen_tok_s"] = timings.get("predicted_per_second")
                elif timings.get("predicted_ms") and gen_n:
                    rec["gen_tok_s"] = round(gen_n / (timings["predicted_ms"] / 1000.0), 3)
                else:
                    # fallback from total elapsed (underestimates prompt share)
                    rec["gen_tok_s"] = "미확인(total_elapsed만 있음)"
                    rec["approx_overall_tok_s"] = round((prompt_n + gen_n) / max(out["elapsed_sec"], 1e-6), 3)
                rec["vram_after_infer"] = nvidia_smi()
            except Exception as e:
                rec["infer_ok"] = False
                rec["error"] = f"{type(e).__name__}: {e}"
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        rec["error_body"] = e.read().decode("utf-8", errors="replace")[:2000]
                    except Exception:
                        pass
                rec["server_log_tail"] = read_tail(log_path, 80)
                rec["vram_after_error"] = nvidia_smi()
        except Exception as e:
            rec["load_ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["vram"] = nvidia_smi()
        finally:
            stop_llama()
            time.sleep(3)
            rec["vram_after_stop"] = nvidia_smi()
        results.append(rec)
        (PREP / "t1_teacher_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"DONE ctx={ctx} load={rec.get('load_ok')} infer={rec.get('infer_ok')}", flush=True)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def read_tail(path: Path, n: int) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


if __name__ == "__main__":
    raise SystemExit(main())
