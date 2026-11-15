# -*- coding: utf-8 -*-
"""실패(빈 raw / connection error) 행 제거 후 해당 조건만 재실행."""
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
from run_gap2 import load_ctx, load_jsonl, run_items  # noqa: E402


def is_ok(row: dict) -> bool:
    if row.get("parse_ok") and isinstance(row.get("parsed"), dict) and row["parsed"].get("articles") is not None:
        return True
    raw = (row.get("raw_output") or "").strip()
    return bool(raw) and not row.get("error")


def purge_bad(path: Path) -> tuple[int, int]:
    rows = load_jsonl(path) if path.exists() else []
    good = [r for r in rows if is_ok(r)]
    bad_n = len(rows) - len(good)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in good) + ("\n" if good else ""), encoding="utf-8")
    return len(good), bad_n


def main():
    targets = [
        ("32B", "C2", None),
        ("32B", "C5", None),
        ("32B", "C4", None),
    ]
    ctx = load_ctx()
    for model, cond, _ in targets:
        p = OUT / f"{model}_E2_{cond}.jsonl"
        kept, removed = purge_bad(p)
        print(f"purge {p.name}: kept={kept} removed={removed}", flush=True)

    # also report 8B just in case
    for cond in ("C2", "C5", "C4", "R"):
        p = OUT / f"8B_E2_{cond}.jsonl"
        if p.exists():
            kept, removed = purge_bad(p)
            if removed:
                print(f"purge 8B {cond}: kept={kept} removed={removed}", flush=True)

    start_server("32B")
    try:
        # C2 remaining
        test = ctx["test"]
        print("repair 32B C2", flush=True)
        print(run_items("32B", "C2", test, ctx), flush=True)
        print("repair 32B C5", flush=True)
        print(run_items("32B", "C5", test, ctx), flush=True)
        print("repair 32B C4", flush=True)
        print(run_items("32B", "C4", ctx["test500"], ctx), flush=True)
    finally:
        stop_server()

    # verify
    for cond, n_exp in (("C2", 1000), ("C5", 1000), ("C4", 500)):
        rows = load_jsonl(OUT / f"32B_E2_{cond}.jsonl")
        ok = sum(1 for r in rows if is_ok(r))
        print(f"VERIFY 32B {cond}: n={len(rows)} ok={ok} expected={n_exp}", flush=True)


if __name__ == "__main__":
    main()
