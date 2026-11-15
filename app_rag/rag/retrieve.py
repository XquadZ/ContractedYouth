# -*- coding: utf-8 -*-
"""BM25(문자 bigram) + bge-m3 코사인을 RRF로 합친다. 상위 3, 하한 미만 버림."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np

from rag.paths import BGE_SNAP, CORPUS, EMBED_IDS, EMBED_NPY, OUT, RETRIEVE_FLOOR, RETRIEVE_K, RRF_K, STD_ITEM_RULES
from rag.yamlutil import load as load_yaml

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _bigrams(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    return [compact[i : i + 2] for i in range(max(0, len(compact) - 1))]


class Bm25Index:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.tfs: list[Counter] = []
        self.lens: list[int] = []
        df: Counter = Counter()
        for rec in records:
            blob = " ".join([rec.get("title") or "", rec.get("text") or "", " ".join(rec.get("std_item") or [])])
            tf = Counter(_bigrams(blob))
            self.tfs.append(tf)
            length = sum(tf.values())
            self.lens.append(length)
            df.update(tf.keys())
        self.df = df
        self.n = len(records)
        self.avg = (sum(self.lens) / self.n) if self.n else 0.0

    def scores(self, query: str) -> list[float]:
        if not self.records or not (query or "").strip():
            return [0.0] * len(self.records)
        qtf = Counter(_bigrams(query))
        out = []
        k1, b = 1.5, 0.75
        for i, tf in enumerate(self.tfs):
            score = 0.0
            dl = self.lens[i] or 1
            for term, qf in qtf.items():
                freq = tf.get(term)
                if not freq:
                    continue
                n = self.df[term]
                idf = math.log(1 + (self.n - n + 0.5) / (n + 0.5))
                score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / self.avg)) * qf
            out.append(float(score))
        return out

    def search(self, query: str, k: int = 3) -> list[dict]:
        scores = self.scores(query)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        hits = []
        for i in order[:k]:
            if scores[i] <= 0:
                continue
            rec = self.records[i]
            hits.append({**_hit_view(rec), "score": round(float(scores[i]), 4)})
        return hits


def _hit_view(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "title": rec.get("title") or "",
        "source": rec.get("source") or "",
        "text": rec.get("text") or "",
        "doc_type": rec.get("doc_type") or "",
        "domain": list(rec.get("domain") or []),
        "std_item": list(rec.get("std_item") or []),
    }


def load_std_item_rules(path: Path | None = None) -> list[dict]:
    target = path or STD_ITEM_RULES
    try:
        spec = load_yaml(target)
        rules = list((spec or {}).get("rules") or [])
        if rules and isinstance(rules[0], dict) and rules[0].get("id"):
            return rules
    except Exception:
        pass
    return _parse_rules_text(target.read_text(encoding="utf-8"))


def _parse_rules_text(text: str) -> list[dict]:
    rules = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- id:"):
            if current:
                rules.append(current)
            current = {"id": line.split(":", 1)[1].strip(), "domain": "", "keywords": []}
        elif current is not None and line.startswith("domain:"):
            current["domain"] = line.split(":", 1)[1].strip()
        elif current is not None and line.startswith("keywords:"):
            inner = line.split(":", 1)[1].strip().strip("[]")
            current["keywords"] = [p.strip() for p in inner.split(",") if p.strip()]
    if current:
        rules.append(current)
    return rules


def assign_std_items(title: str, text: str, domain: str, rules: list[dict] | None = None) -> list[str]:
    rules = rules if rules is not None else load_std_item_rules()
    blob = f"{title or ''}\n{text or ''}"
    hits = []
    for rule in rules:
        if domain and rule.get("domain") and rule.get("domain") != domain:
            continue
        kws = rule.get("keywords") or []
        if any(k and k in blob for k in kws):
            rid = rule.get("id")
            if rid and rid not in hits:
                hits.append(rid)
    return hits


def filter_records(records: list[dict], domain: str, std_items: list[str]) -> tuple[list[dict], str]:
    if domain:
        by_domain = [r for r in records if domain in (r.get("domain") or [])]
        if not by_domain:
            by_domain = list(records)
            mode = "no_domain_match"
        else:
            mode = "domain"
    else:
        by_domain = list(records)
        mode = "no_domain"
    tagged = []
    if std_items:
        for rec in by_domain:
            rec_tags = set(rec.get("std_item") or [])
            if rec_tags and rec_tags.intersection(std_items):
                tagged.append(rec)
    if tagged:
        return tagged, mode + "+std_item"
    return by_domain, mode + "_only"


def corpus_sha1(path: Path | None = None) -> str:
    target = path or CORPUS
    if not target.exists():
        return ""
    return hashlib.sha1(target.read_bytes()).hexdigest()


class EmbedIndex:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.ok = False
        self.error = None
        self.vectors = None
        self._model = None
        self.build_ms = None
        self.load_ms = None
        self.n_records = len(records)
        if not records:
            self.error = "empty_records"
            return
        try:
            self.vectors = self._load_or_build()
            self.ok = self.vectors is not None
        except Exception as exc:
            self.error = str(exc)[:300]
            self.ok = False

    def _record_ids(self) -> list[str]:
        return [r["id"] for r in self.records]

    def _load_or_build(self):
        sha = corpus_sha1()
        ids = self._record_ids()
        if EMBED_IDS.exists() and EMBED_NPY.exists():
            t0 = time.perf_counter()
            meta = json.loads(EMBED_IDS.read_text(encoding="utf-8"))
            saved_ids = meta.get("ids") if isinstance(meta, dict) else meta
            saved_sha = meta.get("corpus_sha1") if isinstance(meta, dict) else None
            if saved_sha == sha and saved_ids == ids:
                vec = np.load(EMBED_NPY)
                if len(vec) == len(self.records):
                    self.load_ms = round((time.perf_counter() - t0) * 1000, 1)
                    self._write_timing("load")
                    return np.asarray(vec, dtype=np.float32)
        t0 = time.perf_counter()
        model = self._get_model()
        texts = [(r.get("title") or "") + "\n" + (r.get("text") or "") for r in self.records]
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
        arr = np.asarray(vectors, dtype=np.float32)
        EMBED_NPY.parent.mkdir(parents=True, exist_ok=True)
        np.save(EMBED_NPY, arr)
        EMBED_IDS.write_text(
            json.dumps({"corpus_sha1": sha, "ids": ids, "n": len(ids)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.build_ms = round((time.perf_counter() - t0) * 1000, 1)
        self._write_timing("build")
        return arr

    def _write_timing(self, mode: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": mode,
            "n_records": self.n_records,
            "build_ms": self.build_ms,
            "load_ms": self.load_ms,
            "npy": str(EMBED_NPY),
            "ids": str(EMBED_IDS),
        }
        (OUT / "embed_timing.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(str(BGE_SNAP), device="cpu")
        return self._model

    def scores(self, query: str) -> list[float]:
        if not self.ok or self.vectors is None:
            return [0.0] * len(self.records)
        q = self._get_model().encode([query], normalize_embeddings=True, show_progress_bar=False)
        qv = np.asarray(q, dtype=np.float32)[0]
        sims = self.vectors @ qv
        return [float(x) for x in sims]


def rrf_combine(bm25: list[float], dense: list[float], k: int = RRF_K) -> list[float]:
    n = len(bm25)
    bm_rank = _ranks(bm25)
    de_rank = _ranks(dense) if any(dense) else None
    out = []
    for i in range(n):
        score = 1.0 / (k + bm_rank[i])
        if de_rank is not None:
            score += 1.0 / (k + de_rank[i])
        out.append(score)
    return out


def _ranks(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    rank = [0] * len(scores)
    for r, i in enumerate(order, start=1):
        rank[i] = r
    return rank


class HybridIndex:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.bm25 = Bm25Index(records)
        self.embed = EmbedIndex(records)
        self.rules = load_std_item_rules()

    def search(
        self,
        query: str,
        *,
        domain: str = "",
        title: str = "",
        k: int = RETRIEVE_K,
        floor: float = RETRIEVE_FLOOR,
        unique_article: bool = True,
    ) -> dict:
        std_items = assign_std_items(title, query, domain, self.rules)
        subset, filter_mode = filter_records(self.records, domain, std_items)
        if not subset:
            return {
                "hits": [],
                "std_items": std_items,
                "filter_mode": filter_mode,
                "embed_ok": self.embed.ok,
                "embed_error": self.embed.error,
                "candidates": [],
            }
        id_set = {r["id"] for r in subset}
        mask = [i for i, r in enumerate(self.records) if r["id"] in id_set]
        bm = self.bm25.scores(query)
        de = self.embed.scores(query) if self.embed.ok else [0.0] * len(self.records)
        rrf = rrf_combine([bm[i] for i in mask], [de[i] for i in mask])
        scored = []
        for local, gi in enumerate(mask):
            rec = self.records[gi]
            scored.append(
                {
                    **_hit_view(rec),
                    "bm25": round(bm[gi], 4),
                    "cosine": round(de[gi], 4) if self.embed.ok else None,
                    "rrf": round(rrf[local], 6),
                    "score": round(rrf[local], 6),
                }
            )
        scored.sort(key=lambda h: (-h["rrf"], h["id"]))
        if unique_article:
            kept = _keep_unique_articles(scored, k=k, floor=floor)
        else:
            kept = [h for h in scored if h["rrf"] >= floor][:k]
        return {
            "hits": kept,
            "std_items": std_items,
            "filter_mode": filter_mode,
            "embed_ok": self.embed.ok,
            "embed_error": self.embed.error,
            "candidates": [
                {"id": h["id"], "bm25": h["bm25"], "cosine": h["cosine"], "rrf": h["rrf"]} for h in scored[:8]
            ],
        }


def article_stem(cid: str) -> str:
    """같은 조: law/decree는 법령명+조까지. 항 번호는 버린다."""
    raw = cid or ""
    if raw.startswith("law:") or raw.startswith("decree:"):
        parts = raw.split(":")
        if len(parts) >= 4 and parts[-1].isdigit():
            return ":".join(parts[:-1])
        return raw
    return raw


def _keep_unique_articles(scored: list[dict], k: int, floor: float) -> list[dict]:
    kept = []
    seen = set()
    for hit in scored:
        if hit["rrf"] < floor:
            continue
        stem = article_stem(hit["id"])
        if stem in seen:
            continue
        seen.add(stem)
        kept.append(hit)
        if len(kept) >= k:
            break
    return kept


def render_hits(hits: list[dict], max_chars: int = 1200) -> str:
    blocks = []
    for hit in hits:
        body = hit["text"]
        if len(body) > max_chars:
            body = body[:max_chars] + "…"
        head = f"[{hit['id']}] {hit['title']}".strip()
        blocks.append(head + "\n" + body)
    return "\n\n".join(blocks)
