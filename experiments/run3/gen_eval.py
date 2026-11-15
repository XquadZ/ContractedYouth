# -*- coding: utf-8 -*-
"""3-5. 평가셋 답변 생성 A/B/C."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from common import (
    PILOT,
    RUN3,
    SYSTEM_SFT,
    append_jsonl,
    load_jsonl,
    log,
    make_tqdm,
    resolve_student_model,
    write_jsonl,
)

BASE_MODEL = resolve_student_model()


def load_eval_items() -> list[dict]:
    items = []
    for src, path in [
        ("lawqa", PILOT / "eval_lawqa.jsonl"),
        ("aihub", PILOT / "eval_aihub_ood.jsonl"),
    ]:
        for r in load_jsonl(path):
            items.append({
                "eval_id": r["audit_id"],
                "source": src,
                "domain": r.get("domain"),
                "question": r["question"],
                "reference_answer": r.get("answer", ""),
            })
    return items


def generate_worker(model_tag: str, adapter: Path | None, gpu: str, items: list[dict], out: Path) -> int:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["PYTHONUNBUFFERED"] = "1"
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except Exception as e:
        err = f"import_failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        (RUN3 / f"gen_eval_{model_tag}_ERROR.txt").write_text(err, encoding="utf-8")
        log(err)
        return 2

    try:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb,
            device_map="auto",
            dtype=torch.float16,
            trust_remote_code=True,
        )
        if adapter is not None and adapter.exists() and (adapter / "adapter_config.json").exists():
            model = PeftModel.from_pretrained(model, str(adapter))
            log(f"[{model_tag}] loaded adapter {adapter}")
        else:
            if model_tag != "A":
                log(f"[{model_tag}] adapter missing, skip model")
                return 3
            log(f"[{model_tag}] base only")

        model.eval()
        done_pairs = {r["eval_id"] for r in load_jsonl(out) if r.get("model") == model_tag}
        todo = [it for it in items if it["eval_id"] not in done_pairs]
        log(f"[{model_tag}] todo={len(todo)}")

        pbar = make_tqdm(todo, desc=f"eval_{model_tag}", unit="q")
        for it in pbar:
            messages = [
                {"role": "system", "content": SYSTEM_SFT},
                {"role": "user", "content": it["question"]},
            ]
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tok(prompt, return_tensors="pt").to(model.device)
            t0 = time.perf_counter()
            with torch.no_grad():
                gen = model.generate(
                    **inputs,
                    max_new_tokens=768,
                    do_sample=False,
                    pad_token_id=tok.pad_token_id,
                )
            elapsed = time.perf_counter() - t0
            new_tokens = gen[0][inputs["input_ids"].shape[-1]:]
            text = tok.decode(new_tokens, skip_special_tokens=True)
            append_jsonl(out, {
                "eval_id": it["eval_id"],
                "source": it["source"],
                "domain": it["domain"],
                "question": it["question"],
                "reference_answer": it["reference_answer"],
                "model": model_tag,
                "output": text,
                "gen_sec": round(elapsed, 3),
            })
        pbar.close()
        return 0
    except Exception as e:
        err = f"gen_failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        (RUN3 / f"gen_eval_{model_tag}_ERROR.txt").write_text(err, encoding="utf-8")
        log(err)
        return 1


def build_compare_md(items: list[dict], outputs: list[dict], path: Path) -> None:
    by = {(o["eval_id"], o["model"]): o for o in outputs}
    lines = ["# EVAL_COMPARE", ""]
    for it in items:
        eid = it["eval_id"]
        lines.append(f"## {eid} | {it['source']} | {it['domain']}")
        lines.append("")
        lines.append("### [질문]")
        lines.append(it["question"])
        lines.append("")
        lines.append("### [참고 답변]")
        lines.append(it["reference_answer"])
        lines.append("")
        for m in ["A", "B", "C"]:
            lines.append(f"### [{m}]")
            o = by.get((eid, m))
            lines.append(o["output"] if o else "(미생성)")
            lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=RUN3 / "eval_outputs.jsonl")
    ap.add_argument("--worker", choices=["A", "B", "C"], default=None)
    ap.add_argument("--gpu", default=None)
    ap.add_argument("--items-json", type=Path, default=None)
    args = ap.parse_args()

    items = load_eval_items()
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    if args.worker:
        adapter = None if args.worker == "A" else RUN3 / f"adapter_{args.worker}"
        if args.items_json and args.items_json.exists():
            items = json.loads(args.items_json.read_text(encoding="utf-8"))
        return generate_worker(args.worker, adapter, args.gpu or "0", items, args.out)

    # Per-model shard files to avoid concurrent write races, then merge.
    items_path = RUN3 / "_eval_items_all.json"
    items_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    py = sys.executable

    def spawn(tag: str, gpu: str) -> subprocess.Popen:
        shard = RUN3 / f"eval_outputs_{tag}.jsonl"
        logp = RUN3 / f"gen_eval_{tag}_console.log"
        cmd = [
            py, str(Path(__file__).resolve()),
            "--worker", tag, "--gpu", gpu,
            "--out", str(shard),
            "--items-json", str(items_path),
        ]
        log(f"spawn {' '.join(cmd)}")
        lf = open(logp, "w", encoding="utf-8", errors="replace")
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(RUN3))
        p._lf = lf  # type: ignore
        p._shard = shard  # type: ignore
        return p

    p_c = None
    if (RUN3 / "adapter_C" / "adapter_config.json").exists():
        p_c = spawn("C", "1")
    else:
        log("[C] adapter missing — skip")

    p_a = spawn("A", "0")
    code_a = p_a.wait()
    try:
        p_a._lf.close()  # type: ignore
    except Exception:
        pass
    log(f"[A] exit={code_a}")

    code_b = 0
    if (RUN3 / "adapter_B" / "adapter_config.json").exists():
        p_b = spawn("B", "0")
        code_b = p_b.wait()
        try:
            p_b._lf.close()  # type: ignore
        except Exception:
            pass
        log(f"[B] exit={code_b}")
    else:
        log("[B] adapter missing — skip")
        code_b = 3

    code_c = 0
    if p_c is not None:
        code_c = p_c.wait()
        try:
            p_c._lf.close()  # type: ignore
        except Exception:
            pass
        log(f"[C] exit={code_c}")

    merged: list[dict] = []
    for tag in ["A", "B", "C"]:
        shard = RUN3 / f"eval_outputs_{tag}.jsonl"
        merged.extend(load_jsonl(shard))
    write_jsonl(args.out, merged)
    build_compare_md(items, merged, RUN3 / "EVAL_COMPARE.md")
    log(f"eval outputs: {len(merged)} -> {args.out}")
    return 0 if code_a == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
