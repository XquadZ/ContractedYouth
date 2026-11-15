# -*- coding: utf-8 -*-
"""3-4. QLoRA 학습 B(GPU0)·C(GPU1) 동시 실행."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from common import RUN3, SEED, log, resolve_student_model

BASE_MODEL = resolve_student_model()


def train_one(side: str, data_path: Path, out_dir: Path, gpu: str, max_steps: int) -> int:
    """side in {'B','C'}. Returns exit code."""
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["PYTHONUNBUFFERED"] = "1"

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "train_log.jsonl"
    meta_path = out_dir / "train_meta.json"

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            Trainer,
            TrainingArguments,
            TrainerCallback,
        )
    except Exception as e:
        err = f"import_failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        (out_dir / "ERROR.txt").write_text(err, encoding="utf-8")
        log(err)
        return 2

    try:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb,
            device_map="auto",
            dtype=torch.float16,
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

        lora = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        )
        model = get_peft_model(model, lora)

        rows = []
        with data_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        train_rows = [r for r in rows if r.get("split") == "train"]
        val_rows = [r for r in rows if r.get("split") == "val"]
        if not train_rows:
            train_rows = rows
        log(f"[{side}] train={len(train_rows)} val={len(val_rows)}")

        resp_token = "assistant"
        # Prefer chat template marker for Qwen
        try:
            probe = tokenizer.apply_chat_template(
                [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
                tokenize=False,
            )
            # Qwen2.5 uses <|im_start|>assistant
            marker = "<|im_start|>assistant"
            if marker not in probe:
                marker = "assistant\n"
        except Exception:
            marker = "<|im_start|>assistant"

        def encode_row(ex):
            messages = ex["messages"]
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            tok = tokenizer(
                text,
                truncation=True,
                max_length=2048,
                padding=False,
                return_tensors=None,
            )
            input_ids = tok["input_ids"]
            labels = list(input_ids)
            # mask everything before assistant content
            full = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            # find last assistant marker
            idx = full.rfind(marker)
            if idx >= 0:
                prefix = full[: idx + len(marker)]
                prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
                n_mask = min(len(prefix_ids), len(labels))
                for i in range(n_mask):
                    labels[i] = -100
            else:
                # fallback: mask first half
                for i in range(len(labels) // 2):
                    labels[i] = -100
            return {"input_ids": input_ids, "attention_mask": tok["attention_mask"], "labels": labels}

        train_ds = Dataset.from_list(train_rows).map(encode_row, remove_columns=list(train_rows[0].keys()))
        eval_ds = None
        if val_rows:
            eval_ds = Dataset.from_list(val_rows).map(encode_row, remove_columns=list(val_rows[0].keys()))

        class JsonlLossCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if not logs:
                    return
                rec = {"step": state.global_step, **{k: float(v) for k, v in logs.items() if isinstance(v, (int, float))}}
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        class NewlinePctCallback(TrainerCallback):
            """HF 기본 \\r tqdm 대신 줄바꿈 % 막대 (tail/Get-Content -Wait용)."""

            def on_step_end(self, args, state, control, **kwargs):
                total = state.max_steps or 0
                step = state.global_step
                if total <= 0:
                    return
                pct = 100.0 * step / total
                filled = int(pct // 2.5)  # 40 chars
                bar = "#" * filled + "-" * (40 - filled)
                print(
                    f"train_{side}: {pct:5.1f}%|{bar}| {step}/{total}",
                    flush=True,
                )

        from transformers import DataCollatorForSeq2Seq
        collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True, label_pad_token_id=-100)

        # transformers 5.x: warmup_ratio removed from TrainingArguments in some builds
        n_train = max(len(train_rows), 1)
        steps_per_epoch = max(1, (n_train + 16 - 1) // 16)  # batch1 * grad_accum16
        total_steps = steps_per_epoch * (2 if max_steps <= 0 else 1)
        if max_steps > 0:
            total_steps = max_steps
        warmup_steps = max(1, int(total_steps * 0.03))

        ta_kwargs = dict(
            output_dir=str(out_dir / "checkpoints"),
            num_train_epochs=2 if max_steps <= 0 else 1,
            max_steps=max_steps if max_steps > 0 else -1,
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=16,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_steps=warmup_steps,
            logging_steps=10 if max_steps <= 0 else 1,
            save_strategy="epoch" if max_steps <= 0 else "no",
            fp16=True,
            bf16=False,
            optim="paged_adamw_8bit",
            report_to=[],
            seed=SEED,
            gradient_checkpointing=True,
            remove_unused_columns=False,
            dataloader_pin_memory=False,
        )
        # eval strategy key differs across versions
        eval_val = "epoch" if eval_ds is not None and max_steps <= 0 else "no"
        try:
            args_tr = TrainingArguments(**ta_kwargs, eval_strategy=eval_val)
        except TypeError:
            try:
                args_tr = TrainingArguments(**ta_kwargs, evaluation_strategy=eval_val)
            except TypeError:
                args_tr = TrainingArguments(**ta_kwargs)

        trainer = Trainer(
            model=model,
            args=args_tr,
            train_dataset=train_ds,
            eval_dataset=eval_ds,
            data_collator=collator,
            callbacks=[JsonlLossCallback(), NewlinePctCallback()],
            disable_tqdm=True,
        )

        meta = {
            "side": side,
            "base_model": BASE_MODEL,
            "gpu": gpu,
            "max_steps": max_steps,
            "train_n": len(train_rows),
            "val_n": len(val_rows),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
        }
        # revision if available
        try:
            from huggingface_hub import hf_hub_download
            # store model name only; revision from config
            meta["model_revision"] = getattr(model.config, "_name_or_path", BASE_MODEL)
            meta["transformers_model_type"] = model.config.model_type
        except Exception:
            pass
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        log(f"[{side}] training start max_steps={max_steps}")
        trainer.train()
        model.save_pretrained(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))
        log(f"[{side}] saved adapter to {out_dir}")
        return 0
    except Exception as e:
        err = f"train_failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        (out_dir / "ERROR.txt").write_text(err, encoding="utf-8")
        log(err)
        return 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-steps", type=int, default=0, help=">0 for smoke; 0=full epochs")
    ap.add_argument("--only", choices=["B", "C", "both"], default="both")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--worker", choices=["B", "C"], default=None, help=argparse.SUPPRESS)
    ap.add_argument("--gpu", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    # worker mode
    if args.worker:
        side = args.worker
        data = RUN3 / f"sft_{side}.jsonl"
        out = RUN3 / f"adapter_{side}"
        return train_one(side, data, out, args.gpu or ("0" if side == "B" else "1"), args.max_steps)

    py = sys.executable
    jobs = []
    if args.only in ("B", "both"):
        jobs.append(("B", "0"))
    if args.only in ("C", "both"):
        jobs.append(("C", "1"))

    procs = []
    for side, gpu in jobs:
        out = RUN3 / f"adapter_{side}"
        if (out / "adapter_config.json").exists() and not args.force and args.max_steps <= 0:
            log(f"[{side}] adapter exists, skip (use --force to retrain)")
            continue
        if not (RUN3 / f"sft_{side}.jsonl").exists():
            log(f"[{side}] missing sft file, skip")
            continue
        cmd = [
            py, str(Path(__file__).resolve()),
            "--worker", side, "--gpu", gpu,
            "--max-steps", str(args.max_steps),
        ]
        if args.force:
            cmd.append("--force")
        log_path = RUN3 / f"train_{side}_console.log"
        log(f"spawn {' '.join(cmd)} log={log_path}")
        lf = open(log_path, "w", encoding="utf-8", errors="replace")
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(RUN3))
        p._lf = lf  # type: ignore
        procs.append((side, p))

    codes = {}
    for side, p in procs:
        codes[side] = p.wait()
        try:
            p._lf.close()  # type: ignore
        except Exception:
            pass
        log(f"[{side}] exit={codes[side]}")

    if not procs:
        return 0
    # success if at least one ok? require all spawned
    return 0 if all(c == 0 for c in codes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
