# -*- coding: utf-8 -*-
"""E2 지표 사전 계산 → out/e2_metrics.json"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
sys.path.insert(0, str(ROOT / "exp_gap2"))
from score2 import fmt_ci, gap_label, load_jsonl, paired_diff_ci, score_e2  # noqa: E402

G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
DATA = G2 / "data"


def score_baseline(name, gold, excl_ids=None):
    rows = load_jsonl(OUT / f"baseline_e2_{name}.jsonl")
    pred = [{"id": r["id"], "parsed": {"articles": r["articles"]}, "parse_ok": True} for r in rows]
    mask = {i: True for i in (excl_ids or [])} if excl_ids else None
    return score_e2(gold, pred, exclude_mask=mask)


def pack(sc):
    return {
        "top1": sc["top1"],
        "any_hit": sc["any_hit"],
        "exact": sc["exact"],
        "macroF1_point": sc["macroF1_point"],
        "top1_excl6": sc["top1_excl6"],
        "n_pred_mean": sc["n_pred_mean"],
        "ood": sc["ood"],
        "top1_vals": sc["top1_vals"],
        "code": sc["code"],
    }


def main():
    gold = load_jsonl(DATA / "e2_test1000.jsonl")
    meta = json.loads((OUT / "baseline_e2_meta.json").read_text(encoding="utf-8")) if (OUT / "baseline_e2_meta.json").exists() else {}
    excl = meta.get("neardup_ids", [])
    out = {"baselines": {}, "models": {}, "diffs": {}}
    for name in ("B0", "B1", "B2", "B3"):
        if not (OUT / f"baseline_e2_{name}.jsonl").exists():
            continue
        sc = score_baseline(name, gold)
        out["baselines"][name] = pack(sc)
        print(name, "top1", fmt_ci(sc["top1"]))
        if excl:
            sc2 = score_baseline(name, gold, excl_ids=excl)
            out["baselines"][f"{name}_excl095"] = pack(sc2)
            print(name, "excl095", fmt_ci(sc2["top1"]))

    for model in ("8B", "32B"):
        out["models"][model] = {}
        for cond in ("C2", "C5", "C4", "R"):
            p = OUT / f"{model}_E2_{cond}.jsonl"
            if not p.exists():
                continue
            if cond == "R":
                g = load_jsonl(G1 / "data" / "e2.jsonl")
            elif cond == "C4":
                g = gold[:500]
            elif cond == "C5":
                preds = load_jsonl(p)
                ids = {r["id"] for r in preds}
                g = [x for x in gold if x["id"] in ids]
            else:
                g = gold
            sc = score_e2(g, load_jsonl(p))
            out["models"][model][cond] = pack(sc)
            print(model, cond, "top1", fmt_ci(sc["top1"]), "any", fmt_ci(sc["any_hit"]), "macroF1", f"{sc['macroF1_point']:.3f}")

    for cond in ("C2", "C5", "C4", "R"):
        if cond in out["models"].get("32B", {}) and cond in out["models"].get("8B", {}):
            a = out["models"]["32B"][cond]["top1_vals"]
            b = out["models"]["8B"][cond]["top1_vals"]
            n = min(len(a), len(b))
            diff = paired_diff_ci(a[:n], b[:n])
            out["diffs"][cond] = {"top1_diff": diff, "gap": gap_label(diff)}
            print("DIFF", cond, fmt_ci(diff), gap_label(diff))

    # drop vals from saved to keep file smaller? keep for report pairing
    (OUT / "e2_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote e2_metrics.json")


if __name__ == "__main__":
    main()
