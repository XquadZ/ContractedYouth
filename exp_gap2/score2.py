# -*- coding: utf-8 -*-
"""GAP-2 채점 유틸 + 리포트 조립용 지표."""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G2 = ROOT / "exp_gap2"
G1 = ROOT / "exp_gap1"
OUT = G2 / "out"
DATA = G2 / "data"
SEED = 42


def load_jsonl(p: Path):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def bootstrap_ci(values, n_boot=1000, alpha=0.05, rng=None):
    rng = rng or random.Random(SEED)
    if not values:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return {
        "mean": sum(values) / n,
        "lo": means[int(alpha / 2 * n_boot)],
        "hi": means[int((1 - alpha / 2) * n_boot) - 1],
        "n": n,
    }


def paired_diff_ci(a, b, n_boot=1000, rng=None):
    rng = rng or random.Random(SEED)
    assert len(a) == len(b)
    n = len(a)
    if n == 0:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    diffs = [a[i] - b[i] for i in range(n)]
    boots = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boots.append(sum(sample) / n)
    boots.sort()
    return {
        "mean": sum(diffs) / n,
        "lo": boots[int(0.025 * n_boot)],
        "hi": boots[int(0.975 * n_boot) - 1],
        "n": n,
    }


def gap_label(diff):
    if diff["mean"] is None:
        return "미확인"
    m, lo = diff["mean"], diff["lo"]
    if m >= 0.10 and lo is not None and lo > 0:
        return "갭 있음"
    if m >= 0.05 and lo is not None and lo > 0:
        return "약한 갭"
    return "불명확"


def index_preds(rows):
    """Normalize prediction rows to {id: {articles|risky, parse_ok, ...}}."""
    out = {}
    for r in rows:
        rid = r.get("id")
        if rid is None:
            continue
        parsed = r.get("parsed") if isinstance(r.get("parsed"), dict) else None
        arts = None
        risky = None
        if parsed:
            if "articles" in parsed:
                try:
                    arts = [int(x) for x in parsed["articles"]]
                except Exception:
                    arts = []
            if "risky" in parsed:
                risky = bool(parsed["risky"])
        if arts is None and "articles" in r:
            try:
                arts = [int(x) for x in r["articles"]]
            except Exception:
                arts = []
        if risky is None and "risky" in r:
            risky = bool(r["risky"])
        out[rid] = {
            "articles": arts,
            "risky": risky,
            "parse_ok": bool(r.get("parse_ok", arts is not None or risky is not None)),
            "score": r.get("score"),
            "raw": r,
        }
    return out


def score_e2(gold_rows, pred_rows, choice_set=None, exclude_mask=None):
    """exclude_mask: dict id->True to drop (e.g. neardup)."""
    preds = index_preds(pred_rows)
    choice_set = set(choice_set or range(6, 15))
    top1, any_hit, exact, ood, npred = [], [], [], [], []
    # per-article macro F1
    tp = Counter()
    fp = Counter()
    fn = Counter()
    ids_used = []
    for g in gold_rows:
        if exclude_mask and exclude_mask.get(g["id"]):
            continue
        ids_used.append(g["id"])
        gold = set(g["gold_articles"])
        p = preds.get(g["id"])
        ok = bool(p and p["parse_ok"] and p["articles"] is not None)
        if not ok:
            pred = set()
            top1.append(0.0)
            any_hit.append(0.0)
            exact.append(0.0)
            ood.append(0.0)
            npred.append(0.0)
        else:
            arts = p["articles"] or []
            pred = set(arts)
            top1.append(1.0 if arts and arts[0] in gold else 0.0)
            any_hit.append(1.0 if pred & gold else 0.0)
            exact.append(1.0 if pred == gold else 0.0)
            ood.append(1.0 if any(a not in choice_set for a in arts) else 0.0)
            npred.append(float(len(arts)))
        for a in pred & gold:
            tp[a] += 1
        for a in pred - gold:
            fp[a] += 1
        for a in gold - pred:
            fn[a] += 1
    # top1 excl6: gold != {6}
    top1_excl6 = []
    for g, v in zip([x for x in gold_rows if not (exclude_mask and exclude_mask.get(x["id"]))], top1):
        if set(g["gold_articles"]) == {6}:
            continue
        # need align - rebuild
        pass
    top1_excl6_vals = []
    for g in gold_rows:
        if exclude_mask and exclude_mask.get(g["id"]):
            continue
        if set(g["gold_articles"]) == {6}:
            continue
        p = preds.get(g["id"])
        ok = bool(p and p["parse_ok"] and p["articles"] is not None)
        arts = (p["articles"] or []) if ok else []
        top1_excl6_vals.append(1.0 if arts and arts[0] in set(g["gold_articles"]) else 0.0)

    labels = sorted(set(tp) | set(fp) | set(fn) | set(range(6, 15)))
    f1s = []
    for a in labels:
        prec = tp[a] / (tp[a] + fp[a]) if (tp[a] + fp[a]) else 0.0
        rec = tp[a] / (tp[a] + fn[a]) if (tp[a] + fn[a]) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    macro = sum(f1s) / len(f1s) if f1s else 0.0

    return {
        "ids": ids_used,
        "top1_vals": top1,
        "any_hit_vals": any_hit,
        "exact_vals": exact,
        "ood_vals": ood,
        "npred_vals": npred,
        "top1": bootstrap_ci(top1),
        "any_hit": bootstrap_ci(any_hit),
        "exact": bootstrap_ci(exact),
        "ood": bootstrap_ci(ood),
        "n_pred_mean": bootstrap_ci(npred),
        "macroF1_point": macro,
        "top1_excl6": bootstrap_ci(top1_excl6_vals),
        "top1_excl6_vals": top1_excl6_vals,
        "code": "exp_gap2/score2.py::score_e2",
    }


def score_e1(gold_rows, pred_rows, exclude_mask=None):
    preds = index_preds(pred_rows)
    acc, rec, fa, y_true, y_score = [], [], [], [], []
    ids = []
    for g in gold_rows:
        if exclude_mask and exclude_mask.get(g["id"]):
            continue
        ids.append(g["id"])
        truth = bool(g["label_risky"])
        p = preds.get(g["id"])
        ok = bool(p and p["parse_ok"] and p["risky"] is not None)
        pred = bool(p["risky"]) if ok else (not truth)
        score = p.get("score") if p and p.get("score") is not None else (1.0 if pred else 0.0)
        acc.append(1.0 if pred == truth else 0.0)
        if truth:
            rec.append(1.0 if pred else 0.0)
        else:
            fa.append(1.0 if pred else 0.0)
        y_true.append(1 if truth else 0)
        y_score.append(float(score))
    auroc = None
    try:
        from sklearn.metrics import roc_auc_score

        if len(set(y_true)) >= 2:
            auroc = float(roc_auc_score(y_true, y_score))
    except Exception:
        auroc = None
    return {
        "ids": ids,
        "acc_vals": acc,
        "rec_vals": rec,
        "fa_vals": fa,
        "y_true": y_true,
        "y_score": y_score,
        "accuracy": bootstrap_ci(acc),
        "recall": bootstrap_ci(rec),
        "false_alarm": bootstrap_ci(fa),
        "auroc_point": auroc,
        "code": "exp_gap2/score2.py::score_e1",
    }


def auroc_bootstrap(y_true, y_score, n_boot=1000, rng=None):
    rng = rng or random.Random(SEED)
    from sklearn.metrics import roc_auc_score

    if len(set(y_true)) < 2:
        return {"mean": None, "lo": None, "hi": None, "n": len(y_true)}
    n = len(y_true)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        yt = [y_true[i] for i in idx]
        ys = [y_score[i] for i in idx]
        if len(set(yt)) < 2:
            continue
        vals.append(roc_auc_score(yt, ys))
    vals.sort()
    if not vals:
        return {"mean": None, "lo": None, "hi": None, "n": n}
    return {
        "mean": sum(vals) / len(vals),
        "lo": vals[int(0.025 * len(vals))],
        "hi": vals[int(0.975 * len(vals)) - 1],
        "n": n,
    }


def balanced_acc_fixed(y_true, y_score, thr=0.5):
    tp = fp = tn = fn = 0
    for y, s in zip(y_true, y_score):
        pred = 1 if s > thr else 0
        if y == 1 and pred == 1:
            tp += 1
        elif y == 0 and pred == 1:
            fp += 1
        elif y == 0 and pred == 0:
            tn += 1
        else:
            fn += 1
    tpr = tp / (tp + fn) if (tp + fn) else 0
    tnr = tn / (tn + fp) if (tn + fp) else 0
    return (tpr + tnr) / 2


def balanced_acc_cv(y_true, y_score, n_seeds=5):
    """2-fold CV threshold selection, average over seeds."""
    n = len(y_true)
    scores = []
    for seed in range(n_seeds):
        rng = random.Random(SEED + seed)
        idx = list(range(n))
        rng.shuffle(idx)
        mid = n // 2
        folds = [idx[:mid], idx[mid:]]
        fold_scores = []
        for fi in range(2):
            val = folds[fi]
            train = folds[1 - fi]
            # pick thr on train maximizing balanced acc over grid
            best_thr, best = 0.5, -1
            for thr in [i / 100 for i in range(5, 96)]:
                yt = [y_true[i] for i in train]
                ys = [y_score[i] for i in train]
                ba = balanced_acc_fixed(yt, ys, thr)
                if ba > best:
                    best, best_thr = ba, thr
            yt = [y_true[i] for i in val]
            ys = [y_score[i] for i in val]
            fold_scores.append(balanced_acc_fixed(yt, ys, best_thr))
        scores.append(sum(fold_scores) / 2)
    return sum(scores) / len(scores)


def fmt_ci(d, pct=True):
    if not d or d.get("mean") is None:
        return "미확인"
    if pct:
        return f"{100*d['mean']:.1f}% [{100*d['lo']:.1f}, {100*d['hi']:.1f}] (n={d['n']})"
    return f"{d['mean']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}] (n={d['n']})"


if __name__ == "__main__":
    print("score2 helpers ready")
