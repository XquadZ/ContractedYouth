# -*- coding: utf-8 -*-
"""T4: run3 adapter/checkpoint·대용량 파일 목록 (삭제 없음)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
RUN3 = ROOT / "run3"
PREP = ROOT / "prep_contract"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    out: dict = {"adapters": {}, "gen_eval_load_path": {}, "files_ge_1gb": []}

    # gen_eval.py source evidence
    ge = (RUN3 / "gen_eval.py").read_text(encoding="utf-8")
    out["gen_eval_py_excerpt"] = []
    for i, ln in enumerate(ge.splitlines(), 1):
        if "adapter" in ln or "PeftModel" in ln or "from_pretrained" in ln or "BASE_MODEL" in ln:
            out["gen_eval_py_excerpt"].append(f"{i}: {ln}")

    for side in ["B", "C"]:
        base = RUN3 / f"adapter_{side}"
        info = {
            "adapter_dir": str(base),
            "has_adapter_config": (base / "adapter_config.json").exists(),
            "checkpoints": [],
        }
        if (base / "adapter_config.json").exists():
            info["root_adapter_config"] = json.loads((base / "adapter_config.json").read_text(encoding="utf-8"))
            info["root_adapter_mtime"] = (base / "adapter_config.json").stat().st_mtime
            info["root_adapter_model_size"] = (base / "adapter_model.safetensors").stat().st_size if (base / "adapter_model.safetensors").exists() else None
        ckpt_root = base / "checkpoints"
        if ckpt_root.exists():
            for d in sorted(ckpt_root.iterdir()):
                if not d.is_dir():
                    continue
                cfg = d / "adapter_config.json"
                entry = {
                    "name": d.name,
                    "path": str(d),
                    "has_adapter_config": cfg.exists(),
                    "mtime": d.stat().st_mtime,
                }
                if cfg.exists():
                    entry["adapter_config_head"] = {
                        k: json.loads(cfg.read_text(encoding="utf-8")).get(k)
                        for k in ["base_model_name_or_path", "r", "lora_alpha", "peft_type"]
                    }
                am = d / "adapter_model.safetensors"
                if am.exists():
                    entry["adapter_model_size"] = am.stat().st_size
                # trainer_state
                ts = d / "trainer_state.json"
                if ts.exists():
                    st = json.loads(ts.read_text(encoding="utf-8"))
                    entry["trainer_global_step"] = st.get("global_step")
                    entry["trainer_epoch"] = st.get("epoch")
                info["checkpoints"].append(entry)

        # Which one did eval load?
        # gen_eval: PeftModel.from_pretrained(model, str(adapter)) where adapter = RUN3/adapter_{tag}
        # That loads ROOT adapter_config + weights, NOT a checkpoint-* subfolder unless linked.
        info["eval_load_path_used_by_gen_eval"] = str(base)
        info["eval_loads_checkpoint_subdir"] = False
        info["eval_note"] = (
            "gen_eval.py uses RUN3/adapter_{B|C} directory directly via PeftModel.from_pretrained; "
            "does not pass checkpoints/checkpoint-*. "
            "Root adapter_* is what trainer.save_pretrained wrote after train (final), "
            "typically equivalent to last checkpoint (106) if save at end."
        )
        # Compare file sizes root vs checkpoint-106
        root_w = base / "adapter_model.safetensors"
        c106 = base / "checkpoints" / "checkpoint-106" / "adapter_model.safetensors"
        c53 = base / "checkpoints" / "checkpoint-53" / "adapter_model.safetensors"
        info["size_compare"] = {
            "root": root_w.stat().st_size if root_w.exists() else None,
            "checkpoint-106": c106.stat().st_size if c106.exists() else None,
            "checkpoint-53": c53.stat().st_size if c53.exists() else None,
        }
        out["adapters"][side] = info

    # large files >= 1GB under ROOT
    large = []
    for p in ROOT.rglob("*"):
        try:
            if p.is_file():
                sz = p.stat().st_size
                if sz >= 1_000_000_000:
                    large.append({"path": str(p), "bytes": sz, "GB": round(sz / (1024**3), 3)})
        except Exception:
            continue
    large.sort(key=lambda x: -x["bytes"])
    out["files_ge_1gb"] = large

    (PREP / "t4_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "adapters": {k: {
            "checkpoints": [c["name"] for c in v.get("checkpoints", [])],
            "eval_load_path": v.get("eval_load_path_used_by_gen_eval"),
            "size_compare": v.get("size_compare"),
        } for k, v in out["adapters"].items()},
        "n_files_ge_1gb": len(large),
        "top": large[:15],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
