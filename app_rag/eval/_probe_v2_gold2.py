# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[2]
APP = WORK / "app_rag"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))
from recall_dev import load_jsonl
from rag.paths import GOLD
from splitutil import clean_twin_path
from dev_eval import is_meta

sel = json.loads((WORK / "datasets/test_hwp_pdfs/selection.json").read_text(encoding="utf-8"))
out = {}
for dom, block in sel["domains"].items():
    rows = load_jsonl(GOLD[dom]["contract"])
    twin = clean_twin_path(dom)
    if twin.exists():
        rows = rows + load_jsonl(twin)
    out[dom] = {}
    for it in block:
        did = it["doc_id"]
        segs = [r for r in rows if r.get("doc_id") == did]
        segs = sorted(
            segs,
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        out[dom][did] = [
            {
                "segment_id": s.get("segment_id"),
                "order": s.get("order"),
                "label": s.get("label"),
                "std_item": s.get("std_item"),
                "segment_type": s.get("segment_type"),
                "is_meta": bool(is_meta(s)),
                "text": s.get("text") or "",
                "source_hwpx": s.get("source_hwpx"),
            }
            for s in segs
        ]
path = WORK / "datasets" / "test_hwp_pdfs_v2" / "__gold_sel.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("WROTE", path)
