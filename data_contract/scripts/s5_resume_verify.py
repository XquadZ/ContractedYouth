# -*- coding: utf-8 -*-
"""5단계: HF 모델 이어받기 + 파일목록/크기/해시 검증. GPU 미사용."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
MODELS = DC / "models"
OUT = DC / "s5_downloads.json"
VERIFY = DC / "s5_verify.json"


def disk_free_gb(letter="C") -> float:
    total, used, free = shutil.disk_usage(f"{letter}:\\")
    return round(free / (1024**3), 2)


def sha256_file(path: Path, chunk=1024 * 1024 * 8) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def list_files(dir_path: Path) -> list[dict]:
    rows = []
    if not dir_path.exists():
        return rows
    for f in sorted(dir_path.rglob("*")):
        if not f.is_file():
            continue
        if ".cache" in f.parts:
            continue
        if "incomplete" in f.name:
            continue
        rows.append({
            "rel": str(f.relative_to(dir_path)),
            "bytes": f.stat().st_size,
            "sha256": sha256_file(f) if f.stat().st_size < 2_000_000_000 else "SKIPPED_LARGE(>2GB)_COMPUTE_BELOW",
        })
    # always hash weight files even if large (user asked) — but can be slow; hash all non-skipped
    for r in rows:
        if r["sha256"].startswith("SKIPPED"):
            p = dir_path / r["rel"]
            print("hashing", r["rel"], r["bytes"])
            r["sha256"] = sha256_file(p)
    return rows


def download_one(repo_id: str, local_dir: Path) -> dict:
    from huggingface_hub import snapshot_download

    info = {
        "repo_id": repo_id,
        "local_dir": str(local_dir),
        "ok": False,
        "error": None,
        "disk_free_gb_before": disk_free_gb(),
        "HF_TOKEN_set": bool((os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()),
    }
    if info["disk_free_gb_before"] < 100:
        info["error"] = f"disk free {info['disk_free_gb_before']}GB < 100"
        return info
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        # resume via snapshot_download into same local_dir
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            resume_download=True,
            token=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or True,
        )
        p = Path(path)
        files = [f for f in p.rglob("*") if f.is_file() and ".cache" not in f.parts and "incomplete" not in f.name]
        size = sum(f.stat().st_size for f in files)
        info["bytes"] = size
        info["GB"] = round(size / (1024**3), 3)
        info["n_files"] = len(files)
        cfg = p / "config.json"
        if cfg.exists():
            cfgj = json.loads(cfg.read_text(encoding="utf-8"))
            info["config_summary"] = {
                "model_type": cfgj.get("model_type"),
                "vocab_size": cfgj.get("vocab_size"),
                "max_position_embeddings": cfgj.get("max_position_embeddings"),
                "architectures": cfgj.get("architectures"),
            }
        # license
        for name in ("LICENSE", "LICENSE.txt", "README.md"):
            f = p / name
            if f.exists():
                txt = f.read_text(encoding="utf-8", errors="replace")[:1500]
                info["license_file"] = name
                for line in txt.splitlines()[:50]:
                    if "license" in line.lower():
                        info["license"] = line.strip()[:200]
                        break
                break
        info["ok"] = True
        info["disk_free_gb_after"] = disk_free_gb()
    except Exception as e:
        info["error"] = repr(e)
        info["disk_free_gb_after"] = disk_free_gb()
    return info


def main():
    # ensure token from env (caller should inject)
    print("HF_TOKEN_set", bool((os.environ.get("HF_TOKEN") or "").strip()), "disk", disk_free_gb())
    MODELS.mkdir(parents=True, exist_ok=True)
    targets = [
        ("Qwen/Qwen3-8B", MODELS / "Qwen3-8B"),
        ("nlpai-lab/KURE-v1", MODELS / "KURE-v1"),
        ("BAAI/bge-m3", MODELS / "bge-m3"),
    ]
    downloads = []
    disk_before = {"C": disk_free_gb()}
    for repo, dest in targets:
        print("DOWNLOAD", repo, "free", disk_free_gb())
        if disk_free_gb() < 100:
            downloads.append({"repo_id": repo, "ok": False, "error": "disk < 100GB"})
            break
        info = download_one(repo, dest)
        downloads.append(info)
        OUT.write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
        print("DONE", repo, info.get("ok"), info.get("GB"), info.get("error"))

    verify = {"models": [], "disk_before_GB": disk_before, "disk_after_GB": {"C": disk_free_gb()}}
    for repo, dest in targets:
        if not dest.exists():
            verify["models"].append({"repo_id": repo, "path": str(dest), "exists": False})
            continue
        print("VERIFY", dest)
        files = list_files(dest)
        total = sum(f["bytes"] for f in files)
        # check incompletes remain
        incs = list(dest.rglob("*.incomplete"))
        verify["models"].append({
            "repo_id": repo,
            "path": str(dest),
            "exists": True,
            "n_files": len(files),
            "total_bytes": total,
            "total_GB": round(total / (1024**3), 3),
            "incomplete_remaining": len(incs),
            "files": files,
        })
        VERIFY.write_text(json.dumps(verify, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "disk_before_GB": disk_before,
        "disk_after_GB": {"C": disk_free_gb()},
        "downloads": downloads,
        "verify_path": str(VERIFY),
    }
    (DC / "s5_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE s5_results/verify")


if __name__ == "__main__":
    main()
