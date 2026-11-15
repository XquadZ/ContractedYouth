# -*- coding: utf-8 -*-
"""검색 손보기 확인: 임베딩 저장, 최저임금 6건, 정답 계약서 날짜."""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.corpus import load_corpus, write_records  # noqa: E402
from rag.dates import extract_dates, min_wage_verdict  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.paths import CORPUS, EMBED_IDS, EMBED_NPY, GOLD, OUT, SAMPLES  # noqa: E402
from rag.retrieve import HybridIndex  # noqa: E402
from rag.split import split_contract  # noqa: E402


def join_docs(path: Path) -> dict[str, str]:
    docs = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        docs[row["doc_id"]].append(row.get("text") or "")
    return {did: "\n".join(texts) for did, texts in docs.items()}


def date_stats(path: Path) -> dict:
    docs = join_docs(path)
    missing = []
    start_ok = end_ok = end_null = 0
    examples = []
    for did, text in docs.items():
        got = extract_dates(text)
        if got["date_missing"] or not got["start_date"]:
            missing.append(did)
        if got["start_date"] and not got["date_missing"]:
            start_ok += 1
        if got["end_date"]:
            end_ok += 1
        elif not got["date_missing"]:
            end_null += 1
        if len(examples) < 3:
            examples.append({"doc_id": did, **got})
    return {
        "path": str(path),
        "n_docs": len(docs),
        "missing_start_or_date_missing": len(missing),
        "missing_ids": missing,
        "start_found": start_ok,
        "end_found": end_ok,
        "end_null_but_start_found": end_null,
        "examples": examples,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    recs, skipped = load_corpus()
    write_records(recs)
    recs2, skipped2 = load_corpus()
    print("CORPUS_N", len(recs2), "skipped", json.dumps(skipped2, ensure_ascii=False))
    print("LONG_AFTER", sum(1 for r in recs2 if len(r.get("text") or "") > 600))
    hang_ids = [r["id"] for r in recs2 if r["id"].rsplit(":", 1)[-1].isdigit()]
    print("HANG_IDS", len(hang_ids), hang_ids[:12])

    t0 = time.perf_counter()
    index = HybridIndex(recs2)
    print("INDEX_MS", round((time.perf_counter() - t0) * 1000, 1))
    print("EMBED_OK", index.embed.ok, index.embed.error)
    print("EMBED_BUILD_MS", index.embed.build_ms, "LOAD_MS", index.embed.load_ms)
    print("NPY", EMBED_NPY, "exists", EMBED_NPY.exists(), "bytes", EMBED_NPY.stat().st_size if EMBED_NPY.exists() else 0)
    print("IDS", EMBED_IDS)

    t1 = time.perf_counter()
    index2 = HybridIndex(recs2)
    print("RELOAD_MS", round((time.perf_counter() - t1) * 1000, 1), "LOAD_MS", index2.embed.load_ms)

    after = {}
    for p in sorted(SAMPLES.glob("*.txt")):
        segs = split_contract(p.read_text(encoding="utf-8"))
        after[p.name] = {
            "n": len(segs),
            "by_type": {},
            "examples": [
                {"segment_id": s["segment_id"], "segment_type": s["segment_type"], "article_title": s.get("article_title"), "text": s["text"][:180]}
                for s in segs[:3]
            ],
        }
        for s in segs:
            after[p.name]["by_type"][s["segment_type"]] = after[p.name]["by_type"].get(s["segment_type"], 0) + 1
    print("SPLIT_AFTER", json.dumps({k: {"n": v["n"], "by_type": v["by_type"]} for k, v in after.items()}, ensure_ascii=False))

    cases = [
        {"name": "c1", "start_date": "2026-03-02", "end_date": "2026-08-31", "hourly_wage": 10320, "date_missing": False, "expect": "문제 없음"},
        {"name": "c2", "start_date": "2026-03-02", "end_date": "2027-03-01", "hourly_wage": 10320, "date_missing": False, "expect": "확인 필요"},
        {"name": "c3", "start_date": "2026-03-02", "end_date": None, "hourly_wage": 10500, "date_missing": False, "expect": "확인 필요"},
        {"name": "c4", "start_date": "2026-03-02", "end_date": "2027-03-01", "hourly_wage": 10820, "date_missing": False, "expect": "문제 없음"},
        {"name": "c5", "start_date": "2027-01-04", "end_date": "2027-12-31", "hourly_wage": 10320, "date_missing": False, "expect": "위반"},
        {"name": "c6", "start_date": None, "end_date": None, "hourly_wage": 10000, "date_missing": True, "expect": "위반"},
    ]
    wage_rows = []
    for case in cases:
        facts = {
            "hourly_wage": case["hourly_wage"],
            "start_date": case["start_date"],
            "end_date": case["end_date"],
            "date_missing": case["date_missing"],
        }
        if case["date_missing"]:
            facts.update(extract_dates(""))
            facts["hourly_wage"] = 10000
        got = min_wage_verdict(facts)
        row = {
            "name": case["name"],
            "expect": case["expect"],
            "got": (got or {}).get("verdict"),
            "why": (got or {}).get("why"),
            "facts": {k: facts.get(k) for k in ("start_date", "end_date", "hourly_wage", "date_missing")},
            "match": (got or {}).get("verdict") == case["expect"],
        }
        wage_rows.append(row)
        print("WAGE", json.dumps(row, ensure_ascii=False))

    alba = (SAMPLES / "alba_cafe.txt").read_text(encoding="utf-8")
    print("FACTS_ALBA", json.dumps(extract_facts(alba), ensure_ascii=False))

    domain_dates = {}
    for domain, spec in GOLD.items():
        domain_dates[domain] = date_stats(spec["contract"])
        print("DATES", domain, json.dumps({k: domain_dates[domain][k] for k in ("n_docs", "missing_start_or_date_missing", "start_found", "end_found", "end_null_but_start_found")}, ensure_ascii=False))

    payload = {
        "corpus_n": len(recs2),
        "skipped": skipped2,
        "hang_ids_n": len(hang_ids),
        "embed": {"ok": index.embed.ok, "error": index.embed.error, "build_ms": index.embed.build_ms, "load_ms": index2.embed.load_ms, "npy": str(EMBED_NPY), "ids": str(EMBED_IDS)},
        "split_after": after,
        "wage": wage_rows,
        "dates": domain_dates,
        "wrote_corpus": str(CORPUS),
    }
    dest = OUT / "rag_light_run.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
