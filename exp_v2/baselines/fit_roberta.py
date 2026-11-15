# -*- coding: utf-8 -*-
"""KLUE-RoBERTa-base 미세조정.

약관 이진 분류: lr 2e-5, epoch 3, batch 16, max_len 256, seed 42/43/44.
문턱은 검증 F1 최대. 약관 시험 분할과 T3 402건을 평가한다.
T2는 같은 학습 설정으로 train 분할의 primary slot 을 맞춘다. 예측은 argmax.
로컬 모델만 쓴다.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import numpy as np

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
sys.path.insert(0, str(EXP))
MODEL_DIR = WORK / "data_local" / "models" / "klue__roberta-base"
OUT = EXP / "baselines" / "out"
SEEDS = (42, 43, 44)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_terms():
    # fit_terms 와 같은 파일 집합. 분할도 같은 seed.
    from baselines.fit_terms import load_terms as _load
    from sklearn.model_selection import train_test_split

    terms = _load()
    if len(terms) != 9000:
        raise SystemExit(f"expected 9000, got {len(terms)}")
    y = np.array([r["y"] for r in terms])
    field = np.array([r["field"] for r in terms])
    idx = np.arange(len(terms))
    train_idx, temp_idx = train_test_split(idx, test_size=0.2, random_state=42, stratify=field)
    val_idx, test_idx = train_test_split(temp_idx, test_size=0.5, random_state=42, stratify=field[temp_idx])
    return terms, y, train_idx, val_idx, test_idx


def best_threshold(prob, y) -> float:
    from sklearn.metrics import f1_score

    best_t, best_f = 0.5, -1.0
    for step in range(5, 96, 5):
        threshold = step / 100.0
        score = f1_score(y, (prob >= threshold).astype(int), zero_division=0)
        if score > best_f:
            best_t, best_f = threshold, float(score)
    return best_t


def train_binary(seed: int, terms, y, train_idx, val_idx, test_idx, t3_text: list[str]) -> dict:
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    set_seed(seed)
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR), num_labels=2, local_files_only=True)
    model.cuda()
    model.train()

    class DS(Dataset):
        def __init__(self, ids, labels=None):
            self.ids = ids
            self.labels = labels

        def __len__(self):
            return len(self.ids)

        def __getitem__(self, i):
            text = terms[self.ids[i]]["text"] if self.labels is not None else t3_text[self.ids[i]]
            enc = tok(text, truncation=True, max_length=256, padding="max_length")
            item = {k: torch.tensor(v) for k, v in enc.items()}
            if self.labels is not None:
                item["labels"] = torch.tensor(int(self.labels[i]))
            return item

    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    loader = DataLoader(DS(train_idx, y[train_idx]), batch_size=16, shuffle=True)
    for epoch in range(3):
        total = 0.0
        for batch in loader:
            batch = {k: v.cuda() for k, v in batch.items()}
            loss = model(**batch).loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss)
        print("epoch", epoch, "loss", round(total / max(1, len(loader)), 4), flush=True)

    def predict(ids, texts_are_t3=False):
        model.eval()
        probs = []
        bs = 32
        with torch.no_grad():
            for start in range(0, len(ids), bs):
                chunk = ids[start : start + bs]
                if texts_are_t3:
                    texts = [t3_text[i] for i in chunk]
                else:
                    texts = [terms[i]["text"] for i in chunk]
                enc = tok(texts, truncation=True, max_length=256, padding=True, return_tensors="pt")
                enc = {k: v.cuda() for k, v in enc.items()}
                logit = model(**enc).logits
                prob = torch.softmax(logit, dim=-1)[:, 1].detach().cpu().numpy()
                probs.append(prob)
        return np.concatenate(probs)

    val_prob = predict(val_idx)
    threshold = best_threshold(val_prob, y[val_idx])
    test_prob = predict(test_idx)
    t3_prob = predict(list(range(len(t3_text))), texts_are_t3=True)
    from sklearn.metrics import f1_score

    meta = {
        "seed": seed,
        "threshold": threshold,
        "val_f1": float(f1_score(y[val_idx], (val_prob >= threshold).astype(int), zero_division=0)),
        "test_f1": float(f1_score(y[test_idx], (test_prob >= threshold).astype(int), zero_division=0)),
    }
    pred_path = OUT / f"roberta_t3_seed{seed}.jsonl"
    with pred_path.open("w", encoding="utf-8", newline="\n") as handle:
        for i, prob in enumerate(t3_prob):
            handle.write(json.dumps({"id": t3_ids[i], "pred": bool(prob >= threshold), "prob": float(prob)}) + "\n")
    (OUT / f"roberta_meta_seed{seed}.json").write_text(json.dumps(meta), encoding="utf-8")
    print("binary", meta, flush=True)
    del model
    torch.cuda.empty_cache()
    return meta


t3_ids: list[str] = []


def main() -> None:
    global t3_ids
    OUT.mkdir(parents=True, exist_ok=True)
    t3 = [
        json.loads(line)
        for line in (EXP / "data" / "t3_clauses.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    t3_ids = [r["id"] for r in t3]
    t3_text = [r["clause"] for r in t3]
    terms, y, train_idx, val_idx, test_idx = load_terms()
    only = sys.argv[1] if len(sys.argv) > 1 else "terms"
    if only in ("terms", "all"):
        for seed in SEEDS:
            if (OUT / f"roberta_meta_seed{seed}.json").exists():
                print("skip", seed, flush=True)
                continue
            train_binary(seed, terms, y, train_idx, val_idx, test_idx, t3_text)
    if only in ("t2", "all"):
        train_t2()


def train_t2() -> None:
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    sys.path.insert(0, str(EXP))
    from t2_neighbors import load_sections, train_test_paths

    cat = json.loads((WORK / "data_contract" / "catalog" / "catalog_v0.2.json").read_text(encoding="utf-8"))
    names = {s["id"]: s["name"] for s in cat["slots"]}
    names["기타"] = "기타"
    sections = load_sections(cat)
    train_paths, _ = train_test_paths(sections)
    train = [s for s in sections if s["path"] in train_paths]
    labels = sorted({names[s["primary_slot"]] for s in train})
    lab2i = {name: i for i, name in enumerate(labels)}
    t2 = [
        json.loads(line)
        for line in (EXP / "data" / "t2_clauses.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for seed in SEEDS:
        dest = OUT / f"roberta_t2_seed{seed}.jsonl"
        if dest.exists():
            print("skip t2", seed, flush=True)
            continue
        set_seed(seed)
        tok = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            str(MODEL_DIR), num_labels=len(labels), local_files_only=True
        )
        model.cuda()

        class DS(Dataset):
            def __len__(self):
                return len(train)

            def __getitem__(self, i):
                enc = tok(train[i]["clause"], truncation=True, max_length=256, padding="max_length")
                item = {k: torch.tensor(v) for k, v in enc.items()}
                item["labels"] = torch.tensor(lab2i[names[train[i]["primary_slot"]]])
                return item

        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        loader = DataLoader(DS(), batch_size=16, shuffle=True)
        model.train()
        for epoch in range(3):
            for batch in loader:
                batch = {k: v.cuda() for k, v in batch.items()}
                loss = model(**batch).loss
                opt.zero_grad()
                loss.backward()
                opt.step()
            print("t2 epoch", seed, epoch, flush=True)
        model.eval()
        with dest.open("w", encoding="utf-8", newline="\n") as handle:
            with torch.no_grad():
                for start in range(0, len(t2), 32):
                    chunk = t2[start : start + 32]
                    enc = tok([r["clause"] for r in chunk], truncation=True, max_length=256, padding=True, return_tensors="pt")
                    enc = {k: v.cuda() for k, v in enc.items()}
                    pred = model(**enc).logits.argmax(-1).cpu().tolist()
                    for row, pi in zip(chunk, pred):
                        handle.write(json.dumps({"id": row["id"], "label": labels[pi]}, ensure_ascii=False) + "\n")
        del model
        torch.cuda.empty_cache()
        print("t2 wrote", dest, flush=True)


if __name__ == "__main__":
    main()
