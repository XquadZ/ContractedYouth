# -*- coding: utf-8 -*-
"""BM25 검색. 색인은 CPU. 임베딩은 아직 붙이지 않는다."""
from __future__ import annotations

import math
import re
from collections import Counter


def _bigrams(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    return [compact[i : i + 2] for i in range(len(compact) - 1)]


class Bm25Index:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.tfs: list[Counter] = []
        self.lens: list[int] = []
        df: Counter = Counter()
        for rec in records:
            blob = " ".join(
                [
                    rec.get("title") or "",
                    rec.get("text") or "",
                    " ".join(rec.get("tags") or []),
                ]
            )
            tf = Counter(_bigrams(blob))
            self.tfs.append(tf)
            length = sum(tf.values())
            self.lens.append(length)
            df.update(tf.keys())
        self.df = df
        self.n = len(records)
        self.avg = (sum(self.lens) / self.n) if self.n else 0.0

    def search(self, query: str, k: int = 3) -> list[dict]:
        if not self.records or not (query or "").strip():
            return []
        qtf = Counter(_bigrams(query))
        scores = []
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
            scores.append(score)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        hits = []
        for i in order[:k]:
            if scores[i] <= 0:
                continue
            rec = self.records[i]
            hits.append(
                {
                    "id": rec["id"],
                    "title": rec["title"],
                    "source": rec.get("source") or "",
                    "text": rec["text"],
                    "score": round(float(scores[i]), 4),
                }
            )
        return hits


def render_hits(hits: list[dict], max_chars: int = 1200) -> str:
    blocks = []
    for hit in hits:
        body = hit["text"]
        if len(body) > max_chars:
            body = body[:max_chars] + "…"
        head = f"[{hit['id']}] {hit['title']}".strip()
        blocks.append(head + "\n" + body)
    return "\n\n".join(blocks)
