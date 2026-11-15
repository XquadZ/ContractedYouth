# -*- coding: utf-8 -*-
"""NEUTRAL_CARDS 실행: CARDS_VERSION=neutral → out/quant_neutral/."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

os.environ["CARDS_VERSION"] = "neutral"

from rag.criteria import clear_cards_cache  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.settings import get_cards_version  # noqa: E402

QN = OUT / "quant_neutral"
COST_CAP = 8.0


def run_gpt() -> None:
    import quant_gpt_run as qg

    clear_cards_cache()
    assert get_cards_version() == "neutral"
    qg.QGPT = QN
    qg.CACHE_DIR = QN / "cache"
    qg.COST_CAP_USD = COST_CAP
    qg.COST_STATE = {"usd": 0.0, "in_tok": 0, "out_tok": 0, "calls": 0, "cache_hits": 0}
    qg.QGPT.mkdir(parents=True, exist_ok=True)
    qg.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # reuse plan if present
    sys.argv = ["quant_gpt_run.py", "--phase", "run", "--workers", "4"]
    qg.main()


def run_local(model: str) -> None:
    """model=EXAONE|AX — quant_run 경로를 quant_neutral로."""
    from quant_run import ensure_model, run_one

    clear_cards_cache()
    assert get_cards_version() == "neutral"
    QN.mkdir(parents=True, exist_ok=True)
    domains = ["LAB", "LEASE", "LOAN"]
    sw = ensure_model(model, alone=True)
    metas = {}
    for i, d in enumerate(domains):
        out = QN / f"{model}_{d}_rows.jsonl"
        print(f"RUN {model}_{d}", flush=True)
        meta = run_one(model=model, domain=d, out_jsonl=out)
        meta["switch_sec"] = round(sw if i == 0 else 0.0, 2)
        meta["cards_version"] = "neutral"
        out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        metas[d] = meta
    (QN / f"{model}_run_meta.json").write_text(json.dumps(metas, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", model, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["gpt", "EXAONE", "AX", "all"], required=True)
    args = parser.parse_args()
    clear_cards_cache()
    if args.phase in ("gpt", "all"):
        run_gpt()
    if args.phase in ("EXAONE", "all"):
        run_local("EXAONE")
    if args.phase in ("AX", "all"):
        run_local("AX")
        # 끝나면 EXAONE 유지
        from quant_run import ensure_model

        ensure_model("EXAONE", alone=True)
        print("EXAONE left UP", flush=True)


if __name__ == "__main__":
    main()
