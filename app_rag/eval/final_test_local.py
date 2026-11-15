# -*- coding: utf-8 -*-
"""FINAL_TEST 로컬 실행. 한 번에 모델 하나. 남은 도메인만 이어 돌린다."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache  # noqa: E402
from final_test_common import DOMAINS, QDEV, QTEST, code_hashes  # noqa: E402
from quant_run import ensure_model, run_one  # noqa: E402


def out_path(split: str, model: str, version: str, domain: str) -> Path:
    root = QDEV if split == "dev" else QTEST
    return root / f"{model}_{version}_{domain}_rows.jsonl"


def run_version(model: str, version: str, *, split: str) -> None:
    os.environ["CARDS_VERSION"] = version
    clear_cards_cache()
    root = QDEV if split == "dev" else QTEST
    root.mkdir(parents=True, exist_ok=True)
    hashes = code_hashes()
    ensure_model(model, alone=True)
    for domain in DOMAINS:
        out = out_path(split, model, version, domain)
        meta_p = out.with_suffix(".meta.json")
        if out.exists() and meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            if int(meta.get("n_rows") or 0) > 0:
                print("SKIP_DONE", out, "rows=", meta.get("n_rows"), flush=True)
                continue
        last_err = None
        meta = None
        for attempt in range(2):
            try:
                print(f"RUN {split} {model} {version} {domain} attempt={attempt + 1}", flush=True)
                meta = run_one(model=model, domain=domain, out_jsonl=out, split=split)
                last_err = None
                break
            except SystemExit as exc:
                last_err = str(exc)
                print("FAIL", last_err, flush=True)
                traceback.print_exc()
            except Exception as exc:
                last_err = str(exc)
                print("FAIL", last_err, flush=True)
                traceback.print_exc()
        if meta is None:
            skip = root / f"skip_{model}_{version}_{domain}.json"
            skip.write_text(json.dumps({"error": last_err, "attempts": 2}, ensure_ascii=False, indent=2), encoding="utf-8")
            print("SKIP", skip, flush=True)
            continue
        meta.update(
            {
                "fair": True,
                "final_test": True,
                "split": split,
                "cards_version": version,
                "code_hashes": hashes,
                "ax_review_to_ok": False,
            }
        )
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("META", meta_p, flush=True)


def leave_exaone() -> None:
    sw = ensure_model("EXAONE", alone=True)
    print("EXAONE_LEFT_UP", round(sw, 2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--model", choices=["EXAONE", "AX"], required=False)
    parser.add_argument("--version", choices=["none", "neutral", "tuned"], required=False)
    parser.add_argument("--leave", action="store_true")
    args = parser.parse_args()
    if args.leave:
        leave_exaone()
        return
    if not args.model or not args.version:
        raise SystemExit("--model and --version required")
    run_version(args.model, args.version, split=args.split)


if __name__ == "__main__":
    main()
