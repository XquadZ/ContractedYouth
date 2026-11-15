# -*- coding: utf-8 -*-
"""32B C5·C4만 재개 (기존 성공 행은 유지)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
SCRIPTS = G2 / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "exp_gap1" / "scripts"))

from llm_server import start_server, stop_server  # noqa: E402
from repair_failed_e2 import is_ok, purge_bad  # noqa: E402
from run_gap2 import load_ctx, load_jsonl, run_items  # noqa: E402


def main():
    for cond in ("C5", "C4"):
        p = OUT / f"32B_E2_{cond}.jsonl"
        kept, removed = purge_bad(p)
        print(f"purge 32B {cond}: kept={kept} removed={removed}", flush=True)

    ctx = load_ctx()
    start_server("32B")
    try:
        print("resume 32B C5", flush=True)
        print(run_items("32B", "C5", ctx["test"], ctx), flush=True)
        print("resume 32B C4", flush=True)
        print(run_items("32B", "C4", ctx["test500"], ctx), flush=True)
    finally:
        stop_server()

    for cond, n_exp in (("C2", 1000), ("C5", 1000), ("C4", 500)):
        rows = load_jsonl(OUT / f"32B_E2_{cond}.jsonl")
        ok = sum(1 for r in rows if is_ok(r))
        print(f"VERIFY 32B {cond}: n={len(rows)} ok={ok} expected={n_exp}", flush=True)
        (OUT / "resume_32b_verify.json").write_text(
            json.dumps(
                {
                    cond: {"n": len(load_jsonl(OUT / f"32B_E2_{cond}.jsonl")), "ok": sum(1 for r in load_jsonl(OUT / f"32B_E2_{cond}.jsonl") if is_ok(r)), "expected": n_exp}
                    for cond, n_exp in (("C2", 1000), ("C5", 1000), ("C4", 500))
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
