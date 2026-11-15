# -*- coding: utf-8 -*-
"""5-3 only: Qwen 35B teacher candidates survey (no download)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from huggingface_hub import HfApi, model_info, hf_hub_download

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
OUT = DC / "s5_teacher_survey.json"


def main():
    api = HfApi()
    result = {"models": [], "error": None, "qwen3_8b_vocab": None}
    try:
        # Qwen3-8B vocab for compare
        try:
            cfg8 = json.loads(Path(hf_hub_download("Qwen/Qwen3-8B", "config.json")).read_text(encoding="utf-8"))
            result["qwen3_8b_vocab"] = cfg8.get("vocab_size")
            result["qwen3_8b_model_type"] = cfg8.get("model_type")
            result["qwen3_8b_max_pos"] = cfg8.get("max_position_embeddings")
        except Exception as e:
            result["qwen3_8b_vocab_error"] = repr(e)

        models = list(api.list_models(author="Qwen", search="35B", limit=80))
        models2 = list(api.list_models(author="Qwen", search="Qwen3", limit=120))
        ids = sorted({(m.id if hasattr(m, "id") else m.modelId) for m in models + models2 if "35B" in ((m.id if hasattr(m, "id") else m.modelId) or "")})
        result["ids_found"] = ids
        for mid in ids:
            row = {"id": mid}
            try:
                mi = model_info(mid, files_metadata=True)
                sibs = mi.siblings or []
                row["n_files"] = len(sibs)
                row["has_gguf_in_repo"] = any((s.rfilename or "").lower().endswith(".gguf") for s in sibs)
                total = sum(s.size or 0 for s in sibs)
                row["total_bytes_listed"] = total
                row["total_GB_listed"] = round(total / (1024**3), 3) if total else None
                # rough Q4/Q6 from FP16 size if listed
                if total:
                    row["est_Q4_GB"] = round(total * 0.25 / (1024**3), 2)
                    row["est_Q6_GB"] = round(total * 0.375 / (1024**3), 2)
                card = getattr(mi, "card_data", None)
                if card is not None and hasattr(card, "license"):
                    row["license"] = card.license
                row["tags"] = list(getattr(mi, "tags", []) or [])[:40]
                row["is_moe_tag"] = any("moe" in (t or "").lower() for t in row["tags"])
            except Exception as e:
                row["error"] = repr(e)
            try:
                cfg_path = hf_hub_download(mid, "config.json")
                cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
                row["model_type"] = cfg.get("model_type")
                row["vocab_size"] = cfg.get("vocab_size")
                row["max_position_embeddings"] = cfg.get("max_position_embeddings")
                row["num_experts"] = cfg.get("num_experts") or cfg.get("num_local_experts")
                row["num_experts_per_tok"] = cfg.get("num_experts_per_tok")
                row["hidden_size"] = cfg.get("hidden_size")
                row["num_hidden_layers"] = cfg.get("num_hidden_layers")
                row["vocab_match_qwen3_8b"] = (
                    row.get("vocab_size") == result.get("qwen3_8b_vocab")
                    if result.get("qwen3_8b_vocab") is not None
                    else None
                )
                # param note from README if present
            except Exception as e:
                row["config_error"] = repr(e)
            # check separate GGUF repos
            gguf_id = mid + "-GGUF" if not mid.endswith("-GGUF") else mid
            try:
                gi = model_info(gguf_id)
                row["gguf_official_repo"] = gguf_id
                row["gguf_repo_exists"] = True
            except Exception:
                # try Qwen/Qwen3-xxx-GGUF patterns
                alt = mid.replace("Qwen/", "Qwen/") + "-GGUF"
                row["gguf_repo_exists"] = False
                row["gguf_official_repo"] = None
            result["models"].append(row)
            time.sleep(0.15)
    except Exception as e:
        result["error"] = repr(e)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("n", len(result.get("models") or []), "err", result.get("error"))
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
