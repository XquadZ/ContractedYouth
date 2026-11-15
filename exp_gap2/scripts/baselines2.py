# -*- coding: utf-8 -*-
"""GAP-2 LLM 없는 기준선 B0–B3 (E2), K1/K5 (E1)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
DATA = G2 / "data"
OUT = G2 / "out"


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def neardup_mask(qe, ce, thr=0.95):
    """True if top1 sim >= thr."""
    sims = ce @ qe.T  # [Nc, Nq]
    top = sims.max(axis=0)
    return top >= thr


def e2_baselines():
    test = load_jsonl(DATA / "e2_test1000.jsonl")
    train = load_jsonl(DATA / "e2_pool_train.jsonl")
    qe = np.load(DATA / "emb_e2_query.npy")
    ce = np.load(DATA / "emb_e2_corpus.npy")
    mask095 = neardup_mask(qe, ce, 0.95)

    # B1: most common gold set (as frozenset string of sorted)
    set_counts = Counter(tuple(sorted(t["gold_articles"])) for t in train)
    mode_set = list(set_counts.most_common(1)[0][0])

    # precompute neighbors
    sims = ce @ qe.T  # Nc x Nq
    top5_idx = np.argpartition(-sims, 5, axis=0)[:5, :]  # 5 x Nq

    preds = {"B0": [], "B1": [], "B2": [], "B3": []}
    for qi, ex in enumerate(test):
        preds["B0"].append({"id": ex["id"], "articles": [6], "parse_ok": True})
        preds["B1"].append({"id": ex["id"], "articles": mode_set, "parse_ok": True})
        # B2 top1
        j = int(np.argmax(sims[:, qi]))
        preds["B2"].append(
            {"id": ex["id"], "articles": list(train[j]["gold_articles"]), "parse_ok": True, "nn": train[j]["id"]}
        )
        # B3 top5 vote
        idxs = [int(i) for i in top5_idx[:, qi]]
        # order by score
        idxs = sorted(idxs, key=lambda i: -sims[i, qi])
        votes = Counter()
        for i in idxs:
            for a in train[i]["gold_articles"]:
                votes[a] += 1
        top_arts = [a for a, _ in votes.most_common(2)]
        preds["B3"].append({"id": ex["id"], "articles": top_arts, "parse_ok": True, "nn5": [train[i]["id"] for i in idxs]})

    # also store c5 neighbor packs for LLM C5
    packs = {}
    for qi, ex in enumerate(test):
        idxs = sorted([int(i) for i in top5_idx[:, qi]], key=lambda i: -sims[i, qi])
        blocks = []
        for rank, i in enumerate(idxs, 1):
            t = train[i]
            arts = ", ".join(f"제{a}조" for a in t["gold_articles"])
            blocks.append(f"{rank}. 조항: {t['clause'][:300]}\n   판정 조항: {arts}")
        packs[ex["id"]] = "\n".join(blocks)
    (DATA / "e2_c5_neighbors.json").write_text(json.dumps(packs, ensure_ascii=False), encoding="utf-8")
    ret = G2 / "retrieval"
    ret.mkdir(parents=True, exist_ok=True)
    (ret / "c5_neighbor_packs.json").write_text(json.dumps(packs, ensure_ascii=False), encoding="utf-8")

    for name, rows in preds.items():
        write_jsonl(OUT / f"baseline_e2_{name}.jsonl", rows)

    meta = {
        "B1_mode_set": mode_set,
        "n_test": len(test),
        "n_train": len(train),
        "n_neardup095": int(mask095.sum()),
        "neardup_ids": [test[i]["id"] for i in range(len(test)) if mask095[i]],
    }
    (OUT / "baseline_e2_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    np.save(DATA / "e2_neardup095_mask.npy", mask095)
    print("E2 baselines done", meta["B1_mode_set"], "neardup", meta["n_neardup095"])
    return preds, mask095


def e1_baselines():
    from sklearn.metrics import roc_auc_score

    test = load_jsonl(G1 / "data" / "e1.jsonl")
    train = load_jsonl(DATA / "e1_pool_train.jsonl")
    qe = np.load(DATA / "emb_e1_query.npy")
    ce = np.load(DATA / "emb_e1_corpus.npy")
    mask095 = neardup_mask(qe, ce, 0.95)
    sims = ce @ qe.T
    top5_idx = np.argpartition(-sims, 5, axis=0)[:5, :]

    k1, k5 = [], []
    scores_k5 = []
    y_true = []
    for qi, ex in enumerate(test):
        y = 1 if ex["label_risky"] else 0
        y_true.append(y)
        j = int(np.argmax(sims[:, qi]))
        pred1 = bool(train[j]["label_risky"])
        k1.append({"id": ex["id"], "risky": pred1, "parse_ok": True, "nn": train[j]["id"]})
        idxs = sorted([int(i) for i in top5_idx[:, qi]], key=lambda i: -sims[i, qi])
        votes = [1 if train[i]["label_risky"] else 0 for i in idxs]
        score = sum(votes) / len(votes)
        pred5 = score >= 0.5
        scores_k5.append(score)
        k5.append({"id": ex["id"], "risky": pred5, "score": score, "parse_ok": True, "nn5": [train[i]["id"] for i in idxs]})

    write_jsonl(OUT / "baseline_e1_K1.jsonl", k1)
    write_jsonl(OUT / "baseline_e1_K5.jsonl", k5)
    np.save(DATA / "e1_neardup095_mask.npy", mask095)

    def auroc(y, s, mask=None):
        if mask is not None:
            y = [yy for yy, m in zip(y, mask) if not m]
            s = [ss for ss, m in zip(s, mask) if not m]
        if len(set(y)) < 2:
            return None
        return float(roc_auc_score(y, s))

    meta = {
        "n": len(test),
        "n_neardup095": int(mask095.sum()),
        "K5_auroc_all": auroc(y_true, scores_k5),
        "K5_auroc_excl095": auroc(y_true, scores_k5, mask095),
        "code": "exp_gap2/scripts/baselines2.py::e1_baselines",
    }
    (OUT / "baseline_e1_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("E1 baselines", meta)
    return k1, k5, mask095


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    e2_baselines()
    e1_baselines()


if __name__ == "__main__":
    main()
