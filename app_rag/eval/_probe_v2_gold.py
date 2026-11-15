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
for dom, block in sel["domains"].items():
    rows = load_jsonl(GOLD[dom]["contract"])
    twin = clean_twin_path(dom)
    if twin.exists():
        rows = rows + load_jsonl(twin)
    print("====", dom)
    for it in block:
        did = it["doc_id"]
        segs = [r for r in rows if r.get("doc_id") == did]
        segs = sorted(
            segs,
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        print(did, it["kind"], "n=", len(segs))
        for s in segs:
            lab = s.get("label")
            st = s.get("std_item")
            sid = s.get("segment_id")
            txt = (s.get("text") or "")[:80].replace("\n", " ")
            m = "META" if is_meta(s) else ""
            print(f"  {sid} o={s.get('order')} lab={lab} std={st} type={s.get('segment_type')} {m}")
            print(f"    {txt}")
