# -*- coding: utf-8 -*-
"""GAP-2 데이터 준비 + 근접 중복 점검. GAP-1/원본 수정 금지."""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
DATA = G2 / "data"
TERMS = ROOT / "data_contract" / "aihub_terms"
BGE = ROOT / "data_contract" / "models" / "bge-m3"
SEED = 42

sys.path.insert(0, str(G1 / "scripts"))
from prepare_data import (  # noqa: E402
    ARTICLE_RE,
    clause_text,
    domain_of,
    extract_articles,
    load_terms_rows,
)

# reuse gap1 embed if available
sys.path.insert(0, str(G1 / "scripts"))
from build_corpus_and_retrieve import embed_texts  # noqa: E402


def norm_text(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", (t or ""), flags=re.UNICODE)


def load_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def prepare_e2_pools():
    rng = random.Random(SEED)
    rows = load_terms_rows()
    g1_e2 = load_jsonl(G1 / "data" / "e2.jsonl")
    g1_norms = {norm_text(x["clause"]) for x in g1_e2}
    g1_ids_src = {x.get("source") for x in g1_e2}

    pool = []
    for r in rows:
        if r["adv"] != "2":
            continue
        cl = (r["clause"] or "").strip()
        if len(cl) < 20 or len(cl) > 1500:
            continue
        arts = [a for a in extract_articles(r["relate"]) if 6 <= a <= 14]
        if not arts:
            continue
        pool.append(
            {
                "field": r["field"],
                "clause": cl,
                "gold_articles": arts,
                "source": r["path"],
                "relate": r["relate"],
                "illdcssBasiss": r["obj"].get("illdcssBasiss"),
            }
        )
    before = len(pool)
    # exact dedupe by normalized text
    seen = set()
    deduped = []
    for r in pool:
        nt = norm_text(r["clause"])
        if not nt or nt in seen:
            continue
        seen.add(nt)
        deduped.append(r)
    # exclude gap1 e2 (by norm or source)
    remain = [
        r
        for r in deduped
        if norm_text(r["clause"]) not in g1_norms and r["source"] not in g1_ids_src
    ]
    rng.shuffle(remain)
    test = remain[:1000]
    train = remain[1000:]
    for i, r in enumerate(test):
        r["id"] = f"E2T-{i:04d}"
    for i, r in enumerate(train):
        r["id"] = f"E2TR-{i:05d}"
    write_jsonl(DATA / "e2_test1000.jsonl", test)
    write_jsonl(DATA / "e2_pool_train.jsonl", train)
    dist = Counter()
    for r in test:
        for a in r["gold_articles"]:
            dist[a] += 1
    has6 = sum(1 for r in test if 6 in r["gold_articles"])
    meta = {
        "pool_before_dedupe": before,
        "after_dedupe": len(deduped),
        "removed_dupes": before - len(deduped),
        "excluded_gap1_e2": len(deduped) - len(remain),
        "n_test": len(test),
        "n_train": len(train),
        "test_article_freq": dict(sorted(dist.items())),
        "test_gold_contains_6_rate": has6 / len(test) if test else 0,
        "test_gold_contains_6_n": has6,
        "code": "exp_gap2/scripts/prepare_data2.py::prepare_e2_pools",
    }
    (DATA / "e2_prep_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return test, train, meta


def prepare_e1_pool():
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    e1m = json.loads((G1 / "data" / "e1_meta.json").read_text(encoding="utf-8"))
    ok = set(e1m["ok_fields"])
    g1_norms = {norm_text(x["clause"]) for x in e1}
    rows = load_terms_rows()
    pool = []
    for r in rows:
        if r["field"] not in ok:
            continue
        if r["adv"] not in ("1", "2"):
            continue
        cl = (r["clause"] or "").strip()
        if len(cl) < 20 or len(cl) > 1500:
            continue
        if norm_text(cl) in g1_norms:
            continue
        pool.append(
            {
                "id": f"E1TR-{len(pool):05d}",
                "field": r["field"],
                "clause": cl,
                "label_risky": r["adv"] == "2",
                "source": r["path"],
                "illdcssBasiss": r["obj"].get("illdcssBasiss"),
            }
        )
    write_jsonl(DATA / "e1_pool_train.jsonl", pool)
    meta = {"n_train": len(pool), "ok_fields": sorted(ok), "excluded_gap1_e1": len(e1)}
    (DATA / "e1_prep_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return pool, meta


def near_dup_check(queries, corpus, q_key="clause", c_key="clause", label_fn_q=None, label_fn_c=None, name="e1"):
    """Return stats + sample pairs for cosine >= 0.95."""
    print(f"embed {name} queries", len(queries))
    qe = embed_texts(BGE, [q[q_key] for q in queries], batch=8)
    print(f"embed {name} corpus", len(corpus))
    ce = embed_texts(BGE, [c[c_key] for c in corpus], batch=8)
    hits = 0
    opposite = 0
    pairs = []
    sims_all_top1 = []
    for i, q in enumerate(queries):
        sims = ce @ qe[i]
        j = int(np.argmax(sims))
        s = float(sims[j])
        sims_all_top1.append(s)
        if s < 0.95:
            continue
        hits += 1
        cq, cc = q, corpus[j]
        lq = label_fn_q(cq) if label_fn_q else None
        lc = label_fn_c(cc) if label_fn_c else None
        opp = False
        if lq is not None and lc is not None:
            if isinstance(lq, (set, list)) and isinstance(lc, (set, list)):
                opp = set(lq) != set(lc)
            else:
                opp = lq != lc
        if opp:
            opposite += 1
        if len(pairs) < 10:
            pairs.append(
                {
                    "sim": s,
                    "q_id": cq.get("id"),
                    "c_id": cc.get("id"),
                    "q_label": list(lq) if isinstance(lq, set) else lq,
                    "c_label": list(lc) if isinstance(lc, set) else lc,
                    "opposite": opp,
                    "q_clause": cq[q_key],
                    "c_clause": cc[c_key],
                }
            )
    n = len(queries)
    out = {
        "n_query": n,
        "n_corpus": len(corpus),
        "rate_sim_ge_0_95": hits / n if n else 0,
        "n_sim_ge_0_95": hits,
        "rate_opposite_among_ge095": (opposite / hits) if hits else 0,
        "n_opposite_among_ge095": opposite,
        "top1_sim_mean": float(np.mean(sims_all_top1)) if sims_all_top1 else None,
        "pairs_sample": pairs,
        "code": "exp_gap2/scripts/prepare_data2.py::near_dup_check",
    }
    (DATA / f"neardup_{name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # also save embeddings for baselines
    np.save(DATA / f"emb_{name}_query.npy", qe)
    np.save(DATA / f"emb_{name}_corpus.npy", ce)
    return out


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    print("E2 pools")
    e2_test, e2_train, m2 = prepare_e2_pools()
    print(m2)
    print("E1 pool")
    e1_train, m1 = prepare_e1_pool()
    print(m1)
    e1_test = load_jsonl(G1 / "data" / "e1.jsonl")
    print("near-dup E1")
    nd1 = near_dup_check(
        e1_test,
        e1_train,
        label_fn_q=lambda x: bool(x["label_risky"]),
        label_fn_c=lambda x: bool(x["label_risky"]),
        name="e1",
    )
    print("E1 neardup", nd1["rate_sim_ge_0_95"], "opp", nd1["rate_opposite_among_ge095"])
    print("near-dup E2")
    nd2 = near_dup_check(
        e2_test,
        e2_train,
        label_fn_q=lambda x: set(x["gold_articles"]),
        label_fn_c=lambda x: set(x["gold_articles"]),
        name="e2",
    )
    print("E2 neardup", nd2["rate_sim_ge_0_95"], "diff_gold", nd2["rate_opposite_among_ge095"])
    print("done")


if __name__ == "__main__":
    main()
