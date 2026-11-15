# -*- coding: utf-8 -*-
"""T2 KLUE-RoBERTa seed 42 를 다시 학습하고 체크포인트를 저장한다.

설정은 exp_v2/baselines/fit_roberta.py 의 T2와 같다.
lr 2e-5, epoch 3, batch 16, max_len 256, seed 42.
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
OUT = Path(__file__).resolve().parent / "models" / "roberta_t2_seed42"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def main() -> None:
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

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
    print("train sections", len(train), "labels", len(labels), flush=True)
    set_seed(42)
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
        total = 0.0
        n = 0
        for batch in loader:
            batch = {k: v.cuda() for k, v in batch.items()}
            loss = model(**batch).loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss)
            n += 1
        print("t2 epoch", epoch, "loss", round(total / max(1, n), 4), flush=True)
    model.eval()
    preds = []
    with torch.no_grad():
        for start in range(0, len(t2), 32):
            chunk = t2[start : start + 32]
            enc = tok(
                [r["clause"] for r in chunk],
                truncation=True,
                max_length=256,
                padding=True,
                return_tensors="pt",
            )
            enc = {k: v.cuda() for k, v in enc.items()}
            pred = model(**enc).logits.argmax(-1).cpu().tolist()
            preds.extend(labels[i] for i in pred)
    hit = 0
    for row, pred in zip(t2, preds):
        gold = {names.get(s, s) for s in row["slots"]}
        hit += int(pred in gold)
    top1 = hit / len(t2)
    print("top1", round(top1, 6), "n", len(t2), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.cpu()
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    (OUT / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    (OUT / "train_meta.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "lr": 2e-5,
                "epoch": 3,
                "batch": 16,
                "max_len": 256,
                "n_train": len(train),
                "n_labels": len(labels),
                "t2_top1": top1,
                "t2_n": len(t2),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
