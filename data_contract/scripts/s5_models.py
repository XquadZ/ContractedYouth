# -*- coding: utf-8 -*-
"""5단계: 로컬 모델 전수조사 + HF 다운로드(GPU 미사용) + 교사 후보 조사."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PILOT = Path(r"C:\Users\DMLAB\pilot_root")
DC = ROOT / "data_contract"
MODELS_OUT = DC / "models"
HF_CACHE = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))


def disk_free_gb(letter: str = "C") -> float:
    total, used, free = shutil.disk_usage(f"{letter}:\\")
    return round(free / (1024**3), 2)


def scan_models() -> list[dict]:
    hits = []
    roots = [ROOT, PILOT, HF_CACHE, Path.home() / ".cache" / "huggingface"]
    # also common locations
    for extra in [Path(r"C:\Users\DMLAB\models"), Path(r"D:\models"), Path(r"E:\models")]:
        if extra.exists():
            roots.append(extra)

    seen = set()
    # gguf files
    for base in roots:
        if not base.exists():
            continue
        try:
            it = base.rglob("*.gguf")
        except Exception:
            continue
        for p in it:
            try:
                key = str(p.resolve())
            except Exception:
                key = str(p)
            if key in seen:
                continue
            seen.add(key)
            name = p.name.lower()
            quant = None
            for q in ("q8_0", "q6_k", "q5_k", "q5_0", "q4_k", "q4_0", "q3_k", "iq4", "f16", "f32"):
                if q in name:
                    quant = q.upper()
                    break
            hits.append({
                "kind": "gguf",
                "path": str(p),
                "name": p.name,
                "bytes": p.stat().st_size,
                "GB": round(p.stat().st_size / (1024**3), 3),
                "quant_guess": quant,
            })

    # HF model dirs with config.json
    for base in [ROOT / "models", PILOT / "models", HF_CACHE / "hub"]:
        if not base.exists():
            continue
        for cfg in base.rglob("config.json"):
            # skip adapters tiny
            try:
                parent = cfg.parent
                size = sum(f.stat().st_size for f in parent.rglob("*") if f.is_file())
            except Exception:
                continue
            if size < 50_000_000:  # <50MB skip small
                # still record if looks like model
                pass
            try:
                cfgj = json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                cfgj = {}
            key = str(parent.resolve())
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                "kind": "hf_dir",
                "path": str(parent),
                "name": parent.name,
                "bytes": size,
                "GB": round(size / (1024**3), 3),
                "model_type": cfgj.get("model_type"),
                "vocab_size": cfgj.get("vocab_size"),
                "max_position_embeddings": cfgj.get("max_position_embeddings"),
                "architectures": cfgj.get("architectures"),
            })
    return hits


def download_repo(repo_id: str, local_dir: Path) -> dict:
    from huggingface_hub import snapshot_download

    info = {
        "repo_id": repo_id,
        "local_dir": str(local_dir),
        "ok": False,
        "error": None,
        "bytes": 0,
        "GB": 0,
        "config": {},
        "license": None,
    }
    free = disk_free_gb("C")
    info["disk_free_gb_before"] = free
    if free < 100:
        info["error"] = f"디스크 여유 {free}GB < 100GB — 다운로드 중단"
        return info
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
        )
        p = Path(path)
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        info["bytes"] = size
        info["GB"] = round(size / (1024**3), 3)
        cfg = p / "config.json"
        if cfg.exists():
            info["config"] = json.loads(cfg.read_text(encoding="utf-8"))
        # license files
        for name in ("LICENSE", "LICENSE.txt", "license", "README.md"):
            f = p / name
            if f.exists():
                txt = f.read_text(encoding="utf-8", errors="replace")[:2000]
                info["license_file"] = name
                info["license_head"] = txt[:500]
                # try extract license line
                for line in txt.splitlines()[:40]:
                    if "license" in line.lower() or "License" in line:
                        info["license"] = line.strip()[:200]
                        break
                break
        # model card via hub
        try:
            from huggingface_hub import ModelCard
            card = ModelCard.load(repo_id)
            if getattr(card, "data", None) is not None:
                info["license"] = info.get("license") or getattr(card.data, "license", None)
        except Exception as e:
            info["license_card_error"] = repr(e)
        info["ok"] = True
        info["disk_free_gb_after"] = disk_free_gb("C")
    except Exception as e:
        info["error"] = repr(e)
        info["disk_free_gb_after"] = disk_free_gb("C")
    return info


def survey_teacher_candidates() -> dict:
    """조사만 — 다운로드 금지."""
    from huggingface_hub import HfApi, model_info

    api = HfApi()
    result = {"models": [], "error": None}
    try:
        models = list(api.list_models(author="Qwen", search="35B", limit=50))
        # also filter name contains 35B
        models2 = list(api.list_models(author="Qwen", search="Qwen3", limit=100))
        ids = []
        for m in models + models2:
            mid = m.modelId if hasattr(m, "modelId") else m.id
            if "35B" in mid or "35b" in mid:
                ids.append(mid)
        ids = sorted(set(ids))
        for mid in ids:
            row = {"id": mid}
            try:
                mi = model_info(mid, files_metadata=True)
                row["siblings"] = [s.rfilename for s in (mi.siblings or [])][:40]
                row["has_gguf_in_repo"] = any(
                    (s.rfilename or "").lower().endswith(".gguf") for s in (mi.siblings or [])
                )
                row["license"] = getattr(mi, "cardData", None)
                card = getattr(mi, "card_data", None) or getattr(mi, "cardData", None)
                if card is not None:
                    if hasattr(card, "license"):
                        row["license"] = card.license
                    elif isinstance(card, dict):
                        row["license"] = card.get("license")
                # size estimate from safetensors
                total = 0
                for s in mi.siblings or []:
                    if s.size:
                        total += s.size
                row["total_bytes_listed"] = total
                row["total_GB_listed"] = round(total / (1024**3), 3) if total else None
                # tags
                row["tags"] = list(getattr(mi, "tags", []) or [])[:30]
                row["pipeline_tag"] = getattr(mi, "pipeline_tag", None)
            except Exception as e:
                row["error"] = repr(e)
            # try config for vocab
            try:
                from huggingface_hub import hf_hub_download
                cfg_path = hf_hub_download(mid, "config.json")
                cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
                row["model_type"] = cfg.get("model_type")
                row["vocab_size"] = cfg.get("vocab_size")
                row["max_position_embeddings"] = cfg.get("max_position_embeddings")
                row["num_parameters_config"] = {
                    k: cfg.get(k)
                    for k in (
                        "num_hidden_layers", "hidden_size", "num_attention_heads",
                        "num_experts", "num_experts_per_tok", "moe_intermediate_size",
                        "intermediate_size",
                    )
                    if k in cfg
                }
            except Exception as e:
                row["config_error"] = repr(e)
            result["models"].append(row)
            time.sleep(0.2)
    except Exception as e:
        result["error"] = repr(e)
    return result


def main():
    MODELS_OUT.mkdir(parents=True, exist_ok=True)
    disk_before = {"C": disk_free_gb("C")}
    local = scan_models()
    (DC / "s5_local_models.json").write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LOCAL_MODELS", len(local), "disk_before", disk_before)

    downloads = []
    targets = [
        ("Qwen/Qwen3-8B", MODELS_OUT / "Qwen3-8B"),
        ("nlpai-lab/KURE-v1", MODELS_OUT / "KURE-v1"),
        ("BAAI/bge-m3", MODELS_OUT / "bge-m3"),
    ]
    for repo, dest in targets:
        print("DOWNLOAD", repo, "free", disk_free_gb("C"))
        if disk_free_gb("C") < 100:
            downloads.append({
                "repo_id": repo,
                "ok": False,
                "error": f"디스크 여유 {disk_free_gb('C')}GB < 100GB — 중단",
                "disk_free_gb_before": disk_free_gb("C"),
            })
            break
        info = download_repo(repo, dest)
        downloads.append(info)
        print("DONE", repo, info.get("ok"), info.get("GB"), info.get("error"))
        # slim config for report
        cfg = info.get("config") or {}
        info["config_summary"] = {
            "model_type": cfg.get("model_type"),
            "vocab_size": cfg.get("vocab_size"),
            "max_position_embeddings": cfg.get("max_position_embeddings"),
            "architectures": cfg.get("architectures"),
            "hidden_size": cfg.get("hidden_size"),
            "num_hidden_layers": cfg.get("num_hidden_layers"),
        }
        # drop huge config from json later
        (DC / "s5_downloads.json").write_text(
            json.dumps([{**d, "config": d.get("config_summary", d.get("config"))} for d in downloads], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("SURVEY teacher candidates...")
    survey = survey_teacher_candidates()
    (DC / "s5_teacher_survey.json").write_text(json.dumps(survey, ensure_ascii=False, indent=2), encoding="utf-8")

    disk_after = {"C": disk_free_gb("C")}
    summary = {
        "disk_before_GB": disk_before,
        "disk_after_GB": disk_after,
        "n_local": len(local),
        "downloads": [{k: v for k, v in d.items() if k != "config"} | {"config": d.get("config_summary", {})} for d in downloads],
        "teacher_survey_n": len(survey.get("models") or []),
        "teacher_survey_error": survey.get("error"),
    }
    (DC / "s5_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE s5_results.json", summary["disk_after_GB"])


if __name__ == "__main__":
    main()
