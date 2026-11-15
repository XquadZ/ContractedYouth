# -*- coding: utf-8 -*-
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from pipelines.common import split_clauses, world
from pipelines.evidence import load
from pipelines.replay import replay


def test_split_numbered_and_articles():
    text = Path(APP / "samples" / "alba_cafe.txt").read_text(encoding="utf-8")
    parts = split_clauses(text)
    assert len(parts) >= 10
    lease = Path(APP / "samples" / "oneroom_lease.txt").read_text(encoding="utf-8")
    lease_parts = split_clauses(lease)
    assert any(p.startswith("제14조") for p in lease_parts)
    assert any("휴게시간은 없다" in p for p in parts)


def test_bm25_matches_stored_context():
    w = world()
    miss = 0
    n = 0
    for row in w.t3.values():
        stored = (w.a4.get(row["id"]) or {}).get("bm25") or {}
        got = w.bm25_ids(row["clause"], 5)
        n += 1
        if got != list(stored.get("node_ids") or []):
            miss += 1
    assert n == 402
    assert miss == 0, miss


def test_replay_metrics():
    data = replay()
    assert data["summary"]["left"]["n"] == 402
    assert data["summary"]["right"]["n"] == 402
    bacc = data["summary"]["right"]["bacc"]["point"]
    assert 0.0 <= bacc <= 1.0
    assert data["summary"]["diff_bacc"]["n"] == 402
    ev = load()
    assert ev["t2_roberta42"].startswith("0.861")
    assert ev["t3_rule"].startswith("1.000")


def test_evidence_cells():
    ev = load()
    assert ev["t3_q8b_a4bm25"].startswith("0.724")
    assert ev["t3_ax7_a1"].startswith("0.838")
    assert ev["t4_q8b_a4bm25"].startswith("0.448")
    assert ev["t4_q8bt_a3"].startswith("0.806")
