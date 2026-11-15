# -*- coding: utf-8 -*-
"""A단계 후 freeze.json 작성. 이후 설정을 바꾸지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from replay import load_rows  # noqa: E402
from neutral_analyze import sweep_best  # noqa: E402
from final_test_common import (  # noqa: E402
    DOMAINS,
    FIXED,
    MODELS,
    QDEV,
    QFAIR,
    QTEST,
    VERSIONS,
    best_cell_to_settings,
    code_hashes,
    dump_json,
    load_json,
)


def _fair_best() -> dict:
    summary = load_json(QFAIR / "summary.json")
    best = summary.get("best") or {}
    out = {"neutral": {}, "tuned": {}}
    # fair summary keys are tuples serialized? Looking at fair_analyze: best[key] where key=(model,version,domain)
    # Actually in payload: "best": {f"{a}|{b}|{c}": ...} NO - looking at fair_analyze code:
    # best[key] = sweep_best(rows) with key=(model, version, domain)
    # payload doesn't dump best with string keys for nested - wait:
    # payload has "best" not stringified in fair_analyze!
    # Looking again at fair_analyze.py:
    # payload = { ..., "best" is NOT in payload! Only tables.
    # Wait - I need to re-read fair_analyze.
    return out


def main() -> None:
    # fair summary tables include best settings per domain in tables[version] rows with kind=best
    fair = load_json(QFAIR / "summary.json")
    best = {"none": {}, "neutral": {}, "tuned": {}}
    for version in ("neutral", "tuned"):
        for row in fair.get("tables", {}).get(version) or []:
            if row.get("kind") != "best":
                continue
            model = row["model"]
            best[version][model] = {}
            for domain in DOMAINS:
                info = row.get(domain) or {}
                # settings string in info['setting'] — re-parse from sweep by loading rows if needed
                # Prefer recomputing from fair rows for structured settings
                path = QFAIR / f"{model}_{version}_{domain}_rows.jsonl"
                if not path.exists():
                    continue
                cell = sweep_best(load_rows(path))
                best[version][model][domain] = best_cell_to_settings(cell)

    # none: from A-stage dev results
    for model in MODELS:
        best["none"][model] = {}
        for domain in DOMAINS:
            path = QDEV / f"{model}_none_{domain}_rows.jsonl"
            if not path.exists():
                best["none"][model][domain] = None
                continue
            cell = sweep_best(load_rows(path))
            best["none"][model][domain] = best_cell_to_settings(cell)

    freeze = {
        "fixed": dict(FIXED),
        "best": best,
        "code_hashes": code_hashes(),
        "score_formulas": ["current", "check_cap79"],
        "note": "이 파일 작성 이후 설정을 바꾸지 않는다. test에서 sweep_best를 쓰지 않는다.",
        "source": {
            "neutral_tuned_best": "out/quant_fair rows → sweep_best",
            "none_best": "out/quant_test/dev/{model}_none_* → sweep_best",
        },
    }
    out = QTEST / "freeze.json"
    dump_json(out, freeze)
    print("WROTE", out, flush=True)
    for version in VERSIONS:
        for model in MODELS:
            print(version, model, best.get(version, {}).get(model), flush=True)


if __name__ == "__main__":
    main()
