# -*- coding: utf-8 -*-
"""Qwen3-8B HF -> Q8_0 GGUF. 실패 시 HF GGUF 다운로드 폴백을 리포트에 기록."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
EXP = ROOT / "exp_gap1"
SRC = ROOT / "data_contract" / "models" / "Qwen3-8B"
# ASCII path for llama tools
OUT_DIR = Path(r"C:\Users\DMLAB\pilot_root\models\Qwen3-8B-GGUF")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "Qwen3-8B-Q8_0.gguf"
VENDOR = EXP / "vendor" / "llama.cpp"
LOG = EXP / "data" / "gguf_convert_log.json"


def try_local_convert() -> dict:
    script = VENDOR / "convert_hf_to_gguf.py"
    if not script.exists():
        return {"ok": False, "error": f"missing {script}"}
    # ensure gguf / deps
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "gguf", "sentencepiece", "protobuf"])
    cmd = [
        sys.executable,
        str(script),
        str(SRC),
        "--outfile",
        str(OUT),
        "--outtype",
        "q8_0",
    ]
    print("RUN", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "ok": p.returncode == 0 and OUT.exists(),
        "returncode": p.returncode,
        "stdout_tail": (p.stdout or "")[-2000:],
        "stderr_tail": (p.stderr or "")[-2000:],
        "path": str(OUT) if OUT.exists() else None,
        "method": "convert_hf_to_gguf.py local",
    }


def try_hf_download() -> dict:
    """폴백: 공개 GGUF Q8_0."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"])
        from huggingface_hub import hf_hub_download

    # candidates
    repos = [
        ("Qwen/Qwen3-8B-GGUF", "Qwen3-8B-Q8_0.gguf"),
        ("bartowski/Qwen3-8B-GGUF", "Qwen3-8B-Q8_0.gguf"),
        ("unsloth/Qwen3-8B-GGUF", "Qwen3-8B-Q8_0.gguf"),
    ]
    last_err = None
    for repo, fname in repos:
        try:
            print("download", repo, fname)
            path = hf_hub_download(repo_id=repo, filename=fname, local_dir=str(OUT_DIR))
            dest = Path(path)
            if dest.resolve() != OUT.resolve():
                # copy/rename
                import shutil

                shutil.copy2(dest, OUT)
            return {
                "ok": OUT.exists(),
                "method": f"hf_hub_download {repo}/{fname}",
                "path": str(OUT),
                "bytes": OUT.stat().st_size if OUT.exists() else 0,
            }
        except Exception as e:
            last_err = str(e)
            print("fail", repo, e)
    return {"ok": False, "method": "hf_download", "error": last_err}


def main():
    if OUT.exists() and OUT.stat().st_size > 1_000_000_000:
        info = {"ok": True, "method": "already_exists", "path": str(OUT), "bytes": OUT.stat().st_size}
        LOG.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print("exists", OUT)
        return
    info = try_local_convert()
    if not info.get("ok"):
        print("local convert failed, fallback HF download")
        fb = try_hf_download()
        info = {"local_convert": info, "fallback": fb, "ok": fb.get("ok"), "path": fb.get("path"), "method": fb.get("method")}
    else:
        info["bytes"] = OUT.stat().st_size
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: info.get(k) for k in ("ok", "method", "path", "bytes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
