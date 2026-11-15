# -*- coding: utf-8 -*-
"""T2 조건 K: train 분할에서 bge-m3 유사 조항 5개. 같은 문서는 뺀다. 입력 파일은 쓰지 않는다."""
from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

EXP = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth\exp_v2")
sys.path.insert(0, str(EXP))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from build_evalset import (  # noqa: E402
    CAT_PATH,
    DETAIL_DOMAIN,
    FORMS,
    TITLE_ONLY,
)

BGE_SNAP = Path(
    r"C:\Users\DMLAB_Server1\.cache\huggingface\hub\models--BAAI--bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181"
)
OUT = EXP / "runs" / "t2_neighbors.jsonl"


def load_sections(cat: dict) -> list[dict]:
    label_to_slots = defaultdict(lambda: defaultdict(list))
    for slot in cat["slots"]:
        for label in slot.get("aihub_labels") or []:
            label_to_slots[slot["domain"]][label].append(slot["id"])
    sections = []
    for path in FORMS.rglob("*.json"):
        if not (path.parent.name.startswith("TL_") or path.parent.name.startswith("VL_")):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc = obj.get("document") or {}
        meta = ((doc.get("metadata") or {}).get("file_info") or {})
        detail = ((meta.get("document_category") or {}).get("detail_category")) or ""
        if detail not in DETAIL_DOMAIN:
            continue
        sec_list = doc.get("sections") or []
        if not any(isinstance((sec.get("content") or {}).get("content_labels"), list) for sec in sec_list):
            continue
        doc_name = meta.get("document_name") or path.stem
        domain = DETAIL_DOMAIN[detail]
        for idx, sec in enumerate(sec_list):
            content = sec.get("content") or {}
            desc = content.get("description") or ""
            if not isinstance(desc, str):
                continue
            desc = desc.strip()
            if len(desc) < 20 or TITLE_ONLY.fullmatch(desc):
                continue
            labels = [str(x) for x in (content.get("content_labels") or [])]
            mapped = []
            unmapped = []
            for label in labels:
                hit = label_to_slots[domain].get(label) or []
                if hit:
                    for slot_id in hit:
                        if slot_id not in mapped:
                            mapped.append(slot_id)
                else:
                    unmapped.append(label)
            primary = mapped[0] if mapped else "기타"
            sections.append(
                {
                    "doc_id": doc_name,
                    "path": str(path),
                    "clause": desc,
                    "primary_slot": primary,
                    "section_index": idx,
                }
            )
    return sections


def train_test_paths(sections: list[dict]) -> tuple[set[str], set[str]]:
    docs = sorted({s["path"] for s in sections})
    rng = random.Random(42)
    rng.shuffle(docs)
    n_train = int(len(docs) * 0.8)
    return set(docs[:n_train]), set(docs[n_train:])


def build(force: bool = False) -> dict[str, list[dict]]:
    if OUT.exists() and not force:
        rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(rows) == 330 and all(len(r.get("neighbors") or []) == 5 for r in rows):
            return {r["id"]: r["neighbors"] for r in rows}
    cat = json.loads(CAT_PATH.read_text(encoding="utf-8"))
    names = {s["id"]: s["name"] for s in cat["slots"]}
    names["기타"] = "기타"
    sections = load_sections(cat)
    train_paths, test_paths = train_test_paths(sections)
    t2 = [
        json.loads(line)
        for line in (EXP / "data" / "t2_clauses.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    test_sections = [s for s in sections if s["path"] in test_paths]
    # t2 행은 (doc_id, section_index, clause) 로 train 이 아닌 섹션과 맞춘다.
    key_to_sec = {(s["doc_id"], s["section_index"], s["clause"]): s for s in test_sections}
    queries = []
    for row in t2:
        sec = key_to_sec.get((row["doc_id"], None, row["clause"]))
        queries.append(row)
    # section_index 가 t2에 없다. 조항 문자열과 doc_id 로 맞춘다.
    by_doc_clause = defaultdict(list)
    for sec in test_sections:
        by_doc_clause[(sec["doc_id"], sec["clause"])].append(sec)
    train = [s for s in sections if s["path"] in train_paths]
    from sentence_transformers import SentenceTransformer
    import numpy as np

    model = SentenceTransformer(str(BGE_SNAP), local_files_only=True)
    train_vec = model.encode(
        [s["clause"] for s in train],
        normalize_embeddings=True,
        batch_size=16,
        show_progress_bar=False,
    )
    query_vec = model.encode(
        [r["clause"] for r in t2],
        normalize_embeddings=True,
        batch_size=16,
        show_progress_bar=False,
    )
    sims = np.matmul(query_vec, np.asarray(train_vec).T)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mapped = {}
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for i, row in enumerate(t2):
            order = list(np.argsort(-sims[i]))
            picked = []
            for j in order:
                sec = train[int(j)]
                if sec["doc_id"] == row["doc_id"]:
                    continue
                picked.append(
                    {
                        "doc_id": sec["doc_id"],
                        "primary_slot": sec["primary_slot"],
                        "slot_name": names.get(sec["primary_slot"], sec["primary_slot"]),
                        "clause": sec["clause"],
                    }
                )
                if len(picked) == 5:
                    break
            mapped[row["id"]] = picked
            handle.write(json.dumps({"id": row["id"], "neighbors": picked}, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    # 맞춤 확인용. 출력만 하고 입력은 그대로 둔다.
    hit = 0
    for row in t2:
        if (row["doc_id"], row["clause"]) in by_doc_clause:
            hit += 1
    print("t2_neighbor_matched", hit, "of", len(t2), "train", len(train))
    return mapped


if __name__ == "__main__":
    build(force=True)
