# -*- coding: utf-8 -*-
"""FAIR_RERUN 2-1/2-4: 로컬 user 프롬프트 해시. LLM 호출 없음.

--when before: 지금 quant_run 경로(가리기 없음).
--when after: 고친 경로(조각·facts만 mask_pii, 법 조문·카드는 그대로).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import build_judge_prompt  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402

QFAIR = OUT / "quant_fair"
DOMAINS = ("LAB", "LEASE", "LOAN")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--when", choices=["before", "after"], required=True)
    args = parser.parse_args()
    use_mask = args.when == "after"
    if use_mask:
        from rag.pii import mask_pii
    else:
        mask_pii = None  # type: ignore

    index, _skipped = get_index()
    corpus = {rec.get("id"): rec.get("text") or "" for rec in index.records}
    items = []
    law_star = 0
    law_mismatch = 0
    law_checked = 0
    n = 0
    for domain in DOMAINS:
        docs = load_domain_docs(domain)
        for doc in docs:
            full = "\n".join(s.get("text") or "" for s in doc["segs"])
            if use_mask:
                full_for_facts, _ = mask_pii(full)
            else:
                full_for_facts = full
            facts = extract_facts(full_for_facts)
            facts["domain"] = domain
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                text = seg.get("text") or ""
                if use_mask:
                    text_for_model, _ = mask_pii(text)
                else:
                    text_for_model = text
                hits_raw = (index.search(strip_placeholders(text_for_model), domain=domain, title="") or {}).get("hits") or []
                row = {
                    "domain": domain,
                    "doc_id": doc["doc_id"],
                    "segment_id": seg.get("segment_id"),
                    "label": seg.get("label") or "",
                }
                for ver in ("neutral", "tuned"):
                    os.environ["CARDS_VERSION"] = ver
                    clear_cards_cache()
                    user, _cards, hits2 = build_judge_prompt(text_for_model, facts, hits_raw, use_criteria=True)
                    row[f"{ver}_sha256"] = _sha(user)
                    row[f"{ver}_bytes"] = len(user.encode("utf-8"))
                    if use_mask:
                        for hit in hits2:
                            hid = hit.get("id")
                            htext = hit.get("text") or ""
                            law_checked += 1
                            src = corpus.get(hid)
                            if src is None or htext != src or (htext and htext not in user):
                                law_mismatch += 1
                            law_star += htext.count("*")
                items.append(row)
                n += 1
                if n % 100 == 0:
                    print(f"HASH {args.when} {n}", flush=True)
    keys = [(r["doc_id"], r["segment_id"], r["label"]) for r in items]
    payload = {
        "when": args.when,
        "masked_clause_and_facts": use_mask,
        "n": n,
        "domains": {d: sum(1 for r in items if r["domain"] == d) for d in DOMAINS},
        "label_counts": {},
        "items": items,
    }
    labels: dict[str, int] = {}
    for _d, _s, lab in keys:
        labels[lab] = labels.get(lab, 0) + 1
    payload["label_counts"] = labels
    if use_mask:
        payload["law_evidence_star_count"] = law_star
        payload["law_hit_checks"] = law_checked
        payload["law_mismatch"] = law_mismatch
    QFAIR.mkdir(parents=True, exist_ok=True)
    out = QFAIR / f"prompt_hash_{args.when}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("WROTE", out, "n=", n, flush=True)
    if use_mask:
        print("LAW stars", law_star, "mismatch", law_mismatch, "checks", law_checked, flush=True)


if __name__ == "__main__":
    main()
