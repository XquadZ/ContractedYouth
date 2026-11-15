# -*- coding: utf-8 -*-
"""T1: Qwen2.5-14B-Instruct 4bit HF 문맥 길이별 실측."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PREP = ROOT / "prep_contract"
MODEL = Path(r"C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct")
CTXS = [4096, 8192, 16384]
OUT_TOKENS = 512


def nvidia_smi() -> str:
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
         "--format=csv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (r.stdout or r.stderr or "").strip()


def build_korean_text(n_chars: int) -> str:
    chunks = []
    for p in [ROOT / "run3" / "items.jsonl", ROOT / "pilot" / "train_pool_lawqa.jsonl"]:
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
    text = "\n\n".join(chunks) if chunks else ("계약 조항 텍스트. " * 3000)
    while len(text) < n_chars:
        text += "\n" + text
    return text[:n_chars]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results = []
    PREP.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except Exception as e:
        err = f"import_failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        (PREP / "t1_student_results.json").write_text(
            json.dumps({"error": err}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(err)
        return 2

    if not MODEL.exists():
        (PREP / "t1_student_results.json").write_text(
            json.dumps({"error": f"model missing: {MODEL}"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1

    # load once at max needed? User asked each ctx separately - reload or set max_position.
    # For fair VRAM measure per ctx, we set model max and truncate inputs to 80% ctx.
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    print("loading tokenizer+model 4bit...", flush=True)
    t_load0 = time.perf_counter()
    try:
        tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL),
            quantization_config=bnb,
            device_map="auto",
            dtype=torch.float16,
            trust_remote_code=True,
        )
        model.eval()
        load_sec = time.perf_counter() - t_load0
        load_ok = True
        load_err = None
        vram_load = nvidia_smi()
    except Exception as e:
        load_ok = False
        load_sec = time.perf_counter() - t_load0
        load_err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        vram_load = nvidia_smi()
        (PREP / "t1_student_results.json").write_text(
            json.dumps({
                "model_path": str(MODEL),
                "load_ok": False,
                "load_sec": load_sec,
                "error": load_err,
                "vram": vram_load,
                "quant": {
                    "load_in_4bit": True,
                    "bnb_4bit_quant_type": "nf4",
                    "bnb_4bit_use_double_quant": True,
                    "bnb_4bit_compute_dtype": "float16",
                },
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(load_err)
        return 1

    print(f"loaded in {load_sec:.1f}s", flush=True)
    print(vram_load, flush=True)

    for ctx in CTXS:
        rec = {
            "model": "Qwen2.5-14B-Instruct",
            "model_path": str(MODEL),
            "ctx": ctx,
            "target_input_tokens": int(ctx * 0.8),
            "max_new_tokens": OUT_TOKENS,
            "load_ok": load_ok,
            "load_sec_once": round(load_sec, 2),
            "vram_after_load": vram_load,
            "quant": {
                "load_in_4bit": True,
                "bnb_4bit_quant_type": "nf4",
                "bnb_4bit_use_double_quant": True,
                "bnb_4bit_compute_dtype": "float16",
            },
        }
        target = int(ctx * 0.8)
        # grow text until ~target tokens
        chars = int(target * 1.8)
        text = build_korean_text(chars)
        messages = [
            {"role": "system", "content": "너는 계약서 조항을 검토하는 안내 AI다."},
            {"role": "user", "content": text + "\n\n위 내용을 바탕으로 핵심 쟁점 5개를 짧게 나열하세요."},
        ]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        # adjust
        for _ in range(6):
            ids = tok(prompt, return_tensors="pt", add_special_tokens=False)["input_ids"]
            n = ids.shape[-1]
            if abs(n - target) < max(32, target * 0.03):
                break
            if n > target:
                chars = int(chars * (target / n) * 0.98)
            else:
                chars = int(chars * (target / max(n, 1)) * 1.02)
            text = build_korean_text(max(500, chars))
            messages[1]["content"] = text + "\n\n위 내용을 바탕으로 핵심 쟁점 5개를 짧게 나열하세요."
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        inputs = tok(prompt, return_tensors="pt")
        # move to device
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        n_in = inputs["input_ids"].shape[-1]
        rec["input_tokens_measured"] = int(n_in)
        rec["input_chars"] = len(text)

        # if input exceeds model capacity, record failure
        try:
            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t0 = time.perf_counter()
            # rough prompt eval timing: forward prefill by generate
            with torch.no_grad():
                # time prompt by running generate with max_new_tokens=1 first? Better single generate
                gen = model.generate(
                    **inputs,
                    max_new_tokens=OUT_TOKENS,
                    do_sample=False,
                    pad_token_id=tok.pad_token_id,
                )
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - t0
            new_n = int(gen.shape[-1] - n_in)
            rec["infer_ok"] = True
            rec["elapsed_sec"] = round(elapsed, 3)
            rec["completion_tokens"] = new_n
            # transformers doesn't split prompt/gen tok/s easily without hooks
            rec["prompt_tok_s"] = "미확인(HF generate 단일 호출 — 분리 미측정)"
            rec["gen_tok_s"] = "미확인(HF generate 단일 호출 — 분리 미측정)"
            rec["overall_tok_s"] = round((n_in + new_n) / max(elapsed, 1e-6), 3)
            # approximate: measure prompt-only with max_new_tokens=1
            t1 = time.perf_counter()
            with torch.no_grad():
                _ = model.generate(**inputs, max_new_tokens=1, do_sample=False, pad_token_id=tok.pad_token_id)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            prefill = time.perf_counter() - t1
            rec["prompt_tok_s_approx_via_max1"] = round(n_in / max(prefill, 1e-6), 3)
            gen_time_approx = max(elapsed - prefill, 1e-6)
            rec["gen_tok_s_approx"] = round(new_n / gen_time_approx, 3)
            rec["vram_after_infer"] = nvidia_smi()
            out_text = tok.decode(gen[0][n_in:], skip_special_tokens=True)
            rec["content_preview"] = out_text[:200]
        except Exception as e:
            rec["infer_ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            rec["vram_after_error"] = nvidia_smi()
        results.append(rec)
        (PREP / "t1_student_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"DONE ctx={ctx} ok={rec.get('infer_ok')} in_tok={n_in}", flush=True)

    # free
    del model
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
