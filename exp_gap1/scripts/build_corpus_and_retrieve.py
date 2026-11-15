# -*- coding: utf-8 -*-
"""R1/R2 검색 평가. LLM 없음."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
EXP = ROOT / "exp_gap1"
DATA = EXP / "data"
RET = EXP / "retrieval"
LAW_DIR = ROOT / "data_contract" / "law_api" / "현행"
KURE = ROOT / "data_contract" / "models" / "KURE-v1"
BGE = ROOT / "data_contract" / "models" / "bge-m3"


def load_law(name: str):
    p = LAW_DIR / f"{name}_body_MST.json"
    return json.loads(p.read_text(encoding="utf-8"))


def article_units(body):
    arts = (((body.get("법령") or {}).get("조문") or {}).get("조문단위")) or []
    if isinstance(arts, dict):
        arts = [arts]
    return [a for a in arts if isinstance(a, dict) and a.get("조문여부") == "조문"]


def format_article(a: dict) -> str:
    title = (a.get("조문제목") or "").strip()
    num = a.get("조문번호")
    br = a.get("조문가지번호")
    br = "" if br in (None, "", "None") else str(br)
    head = f"제{num}조" + (f"의{br}" if br else "")
    if title:
        head += f"({title})"
    parts = [(a.get("조문내용") or "").strip()]
    hangs = a.get("항")
    if isinstance(hangs, dict):
        hangs = [hangs]
    for h in hangs or []:
        if not isinstance(h, dict):
            continue
        hc = (h.get("항내용") or "").strip()
        if hc:
            parts.append(hc)
        hos = h.get("호")
        if isinstance(hos, dict):
            hos = [hos]
        for ho in hos or []:
            if isinstance(ho, dict):
                parts.append((ho.get("호내용") or "").strip())
    return f"{head}\n" + "\n".join(p for p in parts if p)


def art_num(a):
    try:
        return int(a.get("조문번호"))
    except Exception:
        return None


def build_r1_corpus():
    chunks = []
    # 약관법 full
    yak = json.loads((DATA / "law_yakgwan_full_articles.json").read_text(encoding="utf-8"))
    for it in yak:
        chunks.append(
            {
                "id": f"약관법:{it['article']}",
                "law": "약관의 규제에 관한 법률",
                "article": it["article"],
                "num": it.get("num"),
                "text": it["text"],
            }
        )
    # 주임법, 근기법 full
    for name in ("주택임대차보호법", "근로기준법"):
        body = load_law(name)
        for a in article_units(body):
            n = art_num(a)
            br = a.get("조문가지번호")
            br = "" if br in (None, "", "None") else str(br)
            art = f"제{a.get('조문번호')}조" + (f"의{br}" if br else "")
            chunks.append(
                {
                    "id": f"{name}:{art}",
                    "law": name,
                    "article": art,
                    "num": n,
                    "text": format_article(a),
                }
            )
    # 민법: 계약 일반·소비대차·임대차 범위
    # 계약총칙 대략 535–553, 소비대차 598–608, 임대차 618–654, 준용 등 포함해 535–654
    body = load_law("민법")
    for a in article_units(body):
        n = art_num(a)
        if n is None or not (535 <= n <= 654):
            continue
        br = a.get("조문가지번호")
        br = "" if br in (None, "", "None") else str(br)
        art = f"제{a.get('조문번호')}조" + (f"의{br}" if br else "")
        chunks.append(
            {
                "id": f"민법:{art}",
                "law": "민법",
                "article": art,
                "num": n,
                "text": format_article(a),
            }
        )
    RET.mkdir(parents=True, exist_ok=True)
    (RET / "r1_chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunks


def bigrams(text: str):
    t = re.sub(r"\s+", "", text.lower())
    if len(t) < 2:
        return [t] if t else []
    return [t[i : i + 2] for i in range(len(t) - 1)]


class BM25:
    def __init__(self, docs: list[list[str]], k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.N = len(docs)
        self.df = Counter()
        self.doc_len = [len(d) for d in docs]
        self.avgdl = sum(self.doc_len) / max(1, self.N)
        for d in docs:
            for t in set(d):
                self.df[t] += 1

    def score(self, q: list[str], idx: int) -> float:
        d = self.docs[idx]
        tf = Counter(d)
        score = 0.0
        dl = self.doc_len[idx]
        for t in q:
            if t not in tf:
                continue
            n = self.df.get(t, 0)
            idf = math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            freq = tf[t]
            score += idf * (freq * (self.k1 + 1)) / (
                freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
        return score

    def topk(self, q: list[str], k=5):
        scores = [(i, self.score(q, i)) for i in range(self.N)]
        scores.sort(key=lambda x: -x[1])
        return scores[:k]


def embed_texts(model_path: Path, texts: list[str], batch=8):
    """sentence-transformers 없이 transformers AutoModel mean-pool."""
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    model = AutoModel.from_pretrained(str(model_path), trust_remote_code=True)
    model.eval().to(device)
    outs = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            batch_texts = texts[i : i + batch]
            enc = tok(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc)
            # mean pool with attention mask
            last = out.last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).expand(last.size()).float()
            summed = (last * mask).sum(1)
            counts = mask.sum(1).clamp(min=1e-9)
            emb = F.normalize(summed / counts, p=2, dim=1)
            outs.append(emb.cpu().numpy())
            if (i // batch) % 10 == 0:
                print(f"  embed {i}/{len(texts)}")
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return np.vstack(outs)


def dense_topk(q_emb, doc_emb, k=5, exclude_mask=None):
    # cosine since normalized
    sims = doc_emb @ q_emb
    if exclude_mask is not None:
        sims = sims.copy()
        sims[exclude_mask] = -1e9
    idx = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
    idx = idx[np.argsort(-sims[idx])]
    return [(int(i), float(sims[i])) for i in idx]


def eval_r1(chunks):
    e2 = [json.loads(l) for l in (DATA / "e2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    # index map: 약관법 article num -> chunk idxs
    yak_idx = defaultdict(list)
    for i, c in enumerate(chunks):
        if c["law"] == "약관의 규제에 관한 법률" and c.get("num") is not None:
            yak_idx[int(c["num"])].append(i)

    texts = [c["text"] for c in chunks]
    bm_docs = [bigrams(t) for t in texts]
    bm25 = BM25(bm_docs)

    results = {}
    # BM25
    hits = {1: 0, 3: 0, 5: 0}
    for ex in e2:
        q = bigrams(ex["clause"])
        top = bm25.topk(q, 5)
        gold = set(ex["gold_articles"])
        retrieved_nums = []
        for i, _ in top:
            n = chunks[i].get("num")
            if chunks[i]["law"] == "약관의 규제에 관한 법률" and n is not None:
                retrieved_nums.append(int(n))
            else:
                # also match if id contains
                m = re.search(r"제(\d+)조", chunks[i]["article"])
                if m and chunks[i]["law"] == "약관의 규제에 관한 법률":
                    retrieved_nums.append(int(m.group(1)))
        for k in (1, 3, 5):
            if gold & set(retrieved_nums[:k]):
                hits[k] += 1
    results["BM25"] = {f"hit@{k}": hits[k] / len(e2) for k in (1, 3, 5)} | {"n": len(e2)}

    # dense models
    for name, path in (("KURE-v1", KURE), ("bge-m3", BGE)):
        if not path.exists():
            results[name] = {"error": f"missing {path}"}
            continue
        print("embed corpus", name)
        doc_emb = embed_texts(path, texts, batch=8)
        print("embed queries", name)
        q_embs = embed_texts(path, [ex["clause"] for ex in e2], batch=8)
        hits = {1: 0, 3: 0, 5: 0}
        pred_top5 = []
        for qi, ex in enumerate(e2):
            top = dense_topk(q_embs[qi], doc_emb, 5)
            gold = set(ex["gold_articles"])
            retrieved_nums = []
            for i, _ in top:
                if chunks[i]["law"] == "약관의 규제에 관한 법률" and chunks[i].get("num") is not None:
                    retrieved_nums.append(int(chunks[i]["num"]))
            for k in (1, 3, 5):
                if gold & set(retrieved_nums[:k]):
                    hits[k] += 1
            pred_top5.append(
                {
                    "id": ex["id"],
                    "gold": ex["gold_articles"],
                    "retrieved": [
                        {"chunk_id": chunks[i]["id"], "num": chunks[i].get("num"), "score": s}
                        for i, s in top
                    ],
                }
            )
        results[name] = {f"hit@{k}": hits[k] / len(e2) for k in (1, 3, 5)} | {"n": len(e2)}
        np.save(RET / f"r1_docemb_{name}.npy", doc_emb)
        (RET / f"r1_preds_{name}.json").write_text(
            json.dumps(pred_top5, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # store for C3: pick best later
        results[name]["_doc_emb_path"] = str(RET / f"r1_docemb_{name}.npy")

    # choose best by hit@5 then hit@1
    rankable = {k: v for k, v in results.items() if "hit@5" in v}
    best = max(rankable.items(), key=lambda kv: (kv[1]["hit@5"], kv[1]["hit@3"], kv[1]["hit@1"]))[0]
    results["best"] = best
    (RET / "r1_eval.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # precompute C3 packs for e1 and e2 with best retriever
    return results, chunks


def build_c3_packs(chunks, best_name, results):
    e1 = [json.loads(l) for l in (DATA / "e1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    e2 = [json.loads(l) for l in (DATA / "e2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    texts = [c["text"] for c in chunks]

    def fmt_top(indices_scores):
        blocks = []
        for rank, (i, s) in enumerate(indices_scores, 1):
            c = chunks[i]
            blocks.append(f"[{rank}] {c['law']} {c['article']}\n{c['text'][:1200]}")
        return "\n\n".join(blocks)

    packs = {"e1": {}, "e2": {}}
    if best_name == "BM25":
        bm = BM25([bigrams(t) for t in texts])
        for ex in e1:
            top = bm.topk(bigrams(ex["clause"]), 5)
            packs["e1"][ex["id"]] = fmt_top(top)
        for ex in e2:
            top = bm.topk(bigrams(ex["clause"]), 5)
            packs["e2"][ex["id"]] = fmt_top(top)
    else:
        doc_emb = np.load(RET / f"r1_docemb_{best_name}.npy")
        model_path = KURE if best_name == "KURE-v1" else BGE
        for split, items in (("e1", e1), ("e2", e2)):
            qe = embed_texts(model_path, [x["clause"] for x in items], batch=8)
            for qi, ex in enumerate(items):
                top = dense_topk(qe[qi], doc_emb, 5)
                packs[split][ex["id"]] = fmt_top(top)
    (RET / "c3_packs_r1.json").write_text(json.dumps(packs, ensure_ascii=False), encoding="utf-8")
    return packs


def eval_r2():
    train = [
        json.loads(l)
        for l in (DATA / "e3_train_sections.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    test = [json.loads(l) for l in (DATA / "e3.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    labels = json.loads((DATA / "e3_labels.json").read_text(encoding="utf-8"))["labels"]
    results = {}
    packs = {}

    for name, path in (("KURE-v1", KURE), ("bge-m3", BGE)):
        if not path.exists():
            results[name] = {"error": "missing"}
            continue
        print("R2 embed", name)
        doc_emb = embed_texts(path, [t["clause"] for t in train], batch=8)
        q_emb = embed_texts(path, [t["clause"] for t in test], batch=8)
        top1_hit = 0
        maj_hit = 0
        local_packs = {}
        for qi, ex in enumerate(test):
            # exclude same doc
            mask = np.array([t["doc_id"] == ex["doc_id"] for t in train], dtype=bool)
            top = dense_topk(q_emb[qi], doc_emb, 5, exclude_mask=mask)
            neigh = [train[i] for i, _ in top]
            gold = set(ex["gold_labels"])
            top1_lab = neigh[0]["gold_labels"][0] if neigh and neigh[0]["gold_labels"] else None
            if top1_lab in gold:
                top1_hit += 1
            # majority of primary labels
            primaries = [n["gold_labels"][0] for n in neigh if n["gold_labels"]]
            if primaries:
                maj = Counter(primaries).most_common(1)[0][0]
                if maj in gold:
                    maj_hit += 1
            # pack text
            blocks = []
            for rank, (i, s) in enumerate(top, 1):
                t = train[i]
                blocks.append(
                    f"[{rank}] labels={t['gold_labels']} (score={s:.3f})\n{t['clause'][:800]}"
                )
            local_packs[ex["id"]] = "\n\n".join(blocks)
        results[name] = {
            "n": len(test),
            "top1_neighbor_label_in_gold": top1_hit / len(test),
            "top5_majority_label_in_gold": maj_hit / len(test),
        }
        packs[name] = local_packs
        np.save(RET / f"r2_trainemb_{name}.npy", doc_emb)

    best = max(
        ((k, v) for k, v in results.items() if "top1_neighbor_label_in_gold" in v),
        key=lambda kv: (kv[1]["top5_majority_label_in_gold"], kv[1]["top1_neighbor_label_in_gold"]),
    )[0]
    results["best"] = best
    (RET / "r2_eval.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (RET / "c3_packs_r2.json").write_text(
        json.dumps(packs[best], ensure_ascii=False), encoding="utf-8"
    )
    return results


def main():
    RET.mkdir(parents=True, exist_ok=True)
    print("build R1 corpus")
    chunks = build_r1_corpus()
    print("chunks", len(chunks))
    print("eval R1")
    r1, chunks = eval_r1(chunks)
    print(r1)
    print("C3 packs R1 with", r1["best"])
    build_c3_packs(chunks, r1["best"], r1)
    print("eval R2")
    r2 = eval_r2()
    print(r2)
    print("done")


if __name__ == "__main__":
    main()
