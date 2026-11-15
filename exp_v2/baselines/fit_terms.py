# -*- coding: utf-8 -*-
"""규칙 기준선과 TF-IDF + 로지스틱 회귀. GPU 를 쓰지 않는다.

약관 9,000건. 불리(dvAntageous==2)가 양성. 분야(clauseField) 층화, seed 42.
분할 80/10/10. 문자 2~4gram TF-IDF. 결정 문턱은 검증 F1 최대.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
sys.path.insert(0, str(EXP))
from baselines.rules import judge_item  # noqa: E402

ROOT = WORK / "data_local" / "aihub019"
OUT = EXP / "baselines" / "out"


def load_terms() -> list[dict]:
    rows = []
    seen = set()
    for path in ROOT.rglob("*_가공.json"):
        parts = path.parts
        if "라벨링데이터" not in parts or "약관" not in "".join(parts):
            continue
        key = path.name
        if key in seen:
            continue
        seen.add(key)
        obj = json.loads(path.read_text(encoding="utf-8"))
        art = obj.get("clauseArticle")
        if isinstance(art, list):
            text = "\n".join(str(x) for x in art)
        else:
            text = str(art or "")
        label = 1 if str(obj.get("dvAntageous")) == "2" else 0
        rows.append({"name": key, "field": str(obj.get("clauseField")), "text": text, "y": label})
    return rows


def best_threshold(prob, y) -> float:
    best_t, best_f = 0.5, -1.0
    for step in range(5, 96, 5):
        threshold = step / 100.0
        pred = (prob >= threshold).astype(int)
        score = f1_score(y, pred, zero_division=0)
        if score > best_f:
            best_t, best_f = threshold, score
    return best_t


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t3 = [
        json.loads(line)
        for line in (EXP / "data" / "t3_clauses.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with (OUT / "rule_t3.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in t3:
            pred = judge_item(row)
            handle.write(
                json.dumps(
                    {"id": row["id"], "pred": pred, "na": pred is None, "check_id": row["check_id"], "kind": row["kind"]},
                    ensure_ascii=False,
                )
                + "\n"
            )
    print("rules", len(t3))
    terms = load_terms()
    print("terms", len(terms), "pos", sum(r["y"] for r in terms), "fields", len({r["field"] for r in terms}))
    if len(terms) != 9000:
        raise SystemExit(f"expected 9000 terms, got {len(terms)}")
    y = np.array([r["y"] for r in terms])
    field = np.array([r["field"] for r in terms])
    idx = np.arange(len(terms))
    train_idx, temp_idx = train_test_split(idx, test_size=0.2, random_state=42, stratify=field)
    val_idx, test_idx = train_test_split(temp_idx, test_size=0.5, random_state=42, stratify=field[temp_idx])
    print("split", len(train_idx), len(val_idx), len(test_idx), Counter(y[train_idx].tolist()))
    texts = [r["text"] for r in terms]
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=2)
    x_train = vec.fit_transform([texts[i] for i in train_idx])
    x_val = vec.transform([texts[i] for i in val_idx])
    x_test = vec.transform([texts[i] for i in test_idx])
    clf = LogisticRegression(max_iter=200, solver="liblinear")
    clf.fit(x_train, y[train_idx])
    val_prob = clf.predict_proba(x_val)[:, 1]
    threshold = best_threshold(val_prob, y[val_idx])
    test_prob = clf.predict_proba(x_test)[:, 1]
    test_pred = (test_prob >= threshold).astype(int)
    t3_prob = clf.predict_proba(vec.transform([r["clause"] for r in t3]))[:, 1]
    t3_pred = t3_prob >= threshold
    with (OUT / "tfidf_t3.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row, pred, prob in zip(t3, t3_pred, t3_prob):
            handle.write(
                json.dumps({"id": row["id"], "pred": bool(pred), "prob": float(prob)}, ensure_ascii=False) + "\n"
            )
    meta = {
        "n_terms": len(terms),
        "n_train": int(len(train_idx)),
        "n_val": int(len(val_idx)),
        "n_test": int(len(test_idx)),
        "threshold": threshold,
        "val_f1": float(f1_score(y[val_idx], (val_prob >= threshold).astype(int), zero_division=0)),
        "test_f1": float(f1_score(y[test_idx], test_pred, zero_division=0)),
        "test_pos_rate": float(test_pred.mean()),
    }
    (OUT / "tfidf_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
