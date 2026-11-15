# -*- coding: utf-8 -*-
import json
import random
import sys
from pathlib import Path

from sklearn.metrics import roc_auc_score

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
sys.path.insert(0, str(ROOT / "exp_gap2"))
from score2 import auroc_bootstrap, balanced_acc_cv, balanced_acc_fixed, load_jsonl  # noqa: E402

G1 = ROOT / "exp_gap1"
OUT = ROOT / "exp_gap2" / "out"
SEED = 42


def main():
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    gold = {r["id"]: r for r in e1}
    summary = {}
    for model in ("8B", "32B"):
        summary[model] = {}
        for cond in ("C1", "C2"):
            lp = load_jsonl(OUT / f"e1_logprob_{model}_{cond}.jsonl")
            yt, ys = [], []
            for r in lp:
                g = gold.get(r["id"])
                if not g or r.get("score") is None:
                    continue
                yt.append(1 if g["label_risky"] else 0)
                ys.append(float(r["score"]))
            au = auroc_bootstrap(yt, ys)
            ba05 = balanced_acc_fixed(yt, ys, 0.5)
            bacv = balanced_acc_cv(yt, ys)
            summary[model][cond] = {
                "n": len(yt),
                "auroc": au,
                "ba_0.5": ba05,
                "ba_cv": bacv,
                "point_auroc": float(roc_auc_score(yt, ys)),
            }
            print(
                model,
                cond,
                "AUROC",
                f"{au['mean']:.3f} [{au['lo']:.3f},{au['hi']:.3f}]",
                "BA05",
                f"{ba05:.3f}",
                "BACV",
                f"{bacv:.3f}",
            )
    for cond in ("C1", "C2"):
        lp8 = {r["id"]: r for r in load_jsonl(OUT / f"e1_logprob_8B_{cond}.jsonl")}
        lp32 = {r["id"]: r for r in load_jsonl(OUT / f"e1_logprob_32B_{cond}.jsonl")}
        ids = [
            g["id"]
            for g in e1
            if g["id"] in lp8
            and g["id"] in lp32
            and lp8[g["id"]].get("score") is not None
            and lp32[g["id"]].get("score") is not None
        ]
        yt = [1 if gold[i]["label_risky"] else 0 for i in ids]
        rng = random.Random(SEED)
        diffs = []
        for _ in range(1000):
            idx = [rng.randrange(len(ids)) for _ in range(len(ids))]
            ytb = [yt[j] for j in idx]
            if len(set(ytb)) < 2:
                continue
            s8 = [float(lp8[ids[j]]["score"]) for j in idx]
            s32 = [float(lp32[ids[j]]["score"]) for j in idx]
            diffs.append(roc_auc_score(ytb, s32) - roc_auc_score(ytb, s8))
        diffs.sort()
        d = {
            "mean": sum(diffs) / len(diffs),
            "lo": diffs[int(0.025 * len(diffs))],
            "hi": diffs[int(0.975 * len(diffs)) - 1],
            "n": len(ids),
        }
        verdict = "E1 갭은 문턱 차이로 설명됨" if d["lo"] <= 0 <= d["hi"] else "판별력 차이 있음"
        summary[f"diff_32_8_{cond}"] = d
        summary[f"verdict_{cond}"] = verdict
        print("DIFF", cond, d, verdict)
    (OUT / "e1_logprob_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
