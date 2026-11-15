# -*- coding: utf-8 -*-
"""조항 분할, 카탈로그, BM25. BM25는 exp_v2/build_evalset.py 와 같은 식이다."""
from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
CAT_PATH = WORK / "data_contract" / "catalog" / "catalog_v0.2.json"
LAW_PATH = EXP / "law_node_texts.jsonl"
APP = Path(__file__).resolve().parents[1]

SEVERITY_KO = {
    "invalid": "무효",
    "violation": "법 위반",
    "unfavorable": "불리",
    "caution": "주의",
    "info": "주의",
}
DOMAIN_KO = {"LAB": "근로·알바", "LEASE": "주택임대", "LOAN": "차용"}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_catalog() -> dict:
    return json.loads(CAT_PATH.read_text(encoding="utf-8"))


def basis_ids(check: dict) -> list[str]:
    out = []
    for basis in check.get("legal_basis") or []:
        node_id = f"{basis.get('law')}:{basis.get('article')}"
        if node_id not in out:
            out.append(node_id)
    return out


def choice_line(node: dict) -> str:
    title = (node.get("조문 제목") or "").strip()
    base = f"{node.get('법령명')} {node.get('조문 번호')}"
    return f"{base}({title})" if title else base


def render_nodes(ids: list[str], law: dict) -> str:
    blocks = []
    for node_id in ids:
        node = law.get(node_id)
        if node is None:
            blocks.append(f"[{node_id}]\n")
            continue
        title = node.get("조문 제목") or ""
        head = f"[{node['id']}] {node.get('법령명')} {node.get('조문 번호')}"
        if title:
            head += " " + title
        blocks.append(head + "\n" + (node.get("본문") or ""))
    return "\n\n".join(blocks)


def bigrams(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    return [compact[i : i + 2] for i in range(len(compact) - 1)]


class BM25:
    def __init__(self, docs: list[str]) -> None:
        self.tfs = []
        self.lens = []
        df = Counter()
        for doc in docs:
            tf = Counter(bigrams(doc))
            self.tfs.append(tf)
            length = sum(tf.values())
            self.lens.append(length)
            df.update(tf.keys())
        self.df = df
        self.n = len(docs)
        self.avg = (sum(self.lens) / self.n) if self.n else 0.0

    def rank(self, query: str, k: int = 5) -> list[int]:
        qtf = Counter(bigrams(query))
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
        return order[:k]


def split_clauses(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    pattern = re.compile(
        rf"(?=^제\s*\d+\s*조)|(?=^[{CIRCLED}])|(?=^\d{{1,2}}\.\s)",
        re.M,
    )
    idxs = [m.start() for m in pattern.finditer(raw)]
    if not idxs:
        return [raw]
    if idxs[0] != 0:
        idxs = [0] + idxs
    parts = []
    for i, start in enumerate(idxs):
        end = idxs[i + 1] if i + 1 < len(idxs) else len(raw)
        piece = raw[start:end].strip()
        if len(piece) >= 2:
            parts.append(piece)
    return parts or [raw]


def guess_domain(text: str) -> str:
    scores = {
        "LAB": len(re.findall(r"근로|임금|사업주|아르바이트|급여", text or "")),
        "LEASE": len(re.findall(r"임대인|임차인|보증금|월세|임대차", text or "")),
        "LOAN": len(re.findall(r"차용|이자|채무자|채권자", text or "")),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "LAB"
    return best


class World:
    def __init__(self) -> None:
        self.cat = load_catalog()
        self.law = {r["id"]: r for r in load_jsonl(LAW_PATH)}
        self.checks = list(self.cat["checks"])
        self.slots = list(self.cat["slots"])
        self.slot_by_id = {s["id"]: s for s in self.slots}
        self.slot_by_name = {s["name"]: s["id"] for s in self.slots}
        self.check_by_id = {c["id"]: c for c in self.checks}
        self.params = self.cat["params"]
        labels = [s["name"] for s in self.slots if s["domain"] in ("LAB", "LEASE")]
        labels.append("기타")
        self.label_list = "\n".join(labels)
        self.node_ids = [n["id"] for n in self.cat["law_nodes"]]
        self.bm25 = BM25([self.law.get(nid, {}).get("본문") or "" for nid in self.node_ids])
        self.t3 = {r["id"]: r for r in load_jsonl(EXP / "data" / "t3_clauses.jsonl")}
        self.t3_by_clause = {}
        for row in self.t3.values():
            self.t3_by_clause.setdefault(row["clause"], row)
        self.a1 = {r["id"]: r for r in load_jsonl(EXP / "contexts" / "t3_A1.jsonl")}
        self.a4 = {r["id"]: r for r in load_jsonl(EXP / "contexts" / "t3_A4.jsonl")}
        sys_rag = (WORK / "exp_gap1" / "prompts" / "system_rag.txt").read_text(encoding="utf-8")
        sys_norag = (WORK / "exp_gap1" / "prompts" / "system_norag.txt").read_text(encoding="utf-8")
        self.system_rag = sys_rag
        self.system_norag = sys_norag
        self.user_t2 = (EXP / "prompts" / "user_t2.txt").read_text(encoding="utf-8")
        self.user_t3 = (EXP / "prompts" / "user_t3.txt").read_text(encoding="utf-8")
        self.user_t4 = (EXP / "prompts" / "user_t4.txt").read_text(encoding="utf-8")

    def checks_for_slot(self, slot_id: str) -> list[dict]:
        return [c for c in self.checks if c.get("slot") == slot_id]

    def bm25_ids(self, clause: str, k: int = 5) -> list[str]:
        return [self.node_ids[i] for i in self.bm25.rank(clause, k)]

    def articles_of(self, node_ids: list[str]) -> list[dict]:
        out = []
        for node_id in node_ids:
            node = self.law.get(node_id) or {}
            out.append(
                {
                    "id": node_id,
                    "line": choice_line(node) if node else node_id,
                    "body": node.get("본문") or "",
                }
            )
        return out


_WORLD: World | None = None
_WORLD_LOCK = threading.Lock()


def world() -> World:
    global _WORLD
    if _WORLD is None:
        with _WORLD_LOCK:
            if _WORLD is None:
                _WORLD = World()
    return _WORLD
