# -*- coding: utf-8 -*-
"""QUANT_FULL 1장: 모델×도메인 1회 실행, 조항별 원본 저장 (LLM 호출)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import is_blocking_fact, select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, generate_finding, set_llm_endpoint  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import NEEDS_FACT_STATS, reset_needs_fact_stats, verify_finding  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from metrics import score_pair  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta  # noqa: E402
from relax_check import classify_review_source  # noqa: E402

ENDPOINTS = {
    "AX": {
        "url": "http://127.0.0.1:8082/v1/chat/completions",
        "health": "http://127.0.0.1:8082/health",
        "label": "A.X-4.0-Light",
        "port": 8082,
        "start": "start_ax.py",
    },
    "EXAONE": {
        "url": "http://127.0.0.1:8083/v1/chat/completions",
        "health": "http://127.0.0.1:8083/health",
        "label": "EXAONE-4.0-32B-Q4_K_M",
        "port": 8083,
        "start": "start_exaone.py",
    },
}
DOMAIN_KEY = {"LAB": "LAB", "LEASE": "LEASE", "LOAN": "LOAN", "근로": "LAB", "임대": "LEASE", "차용": "LOAN"}
MODEL_FILE = {"AX": "AX", "EXAONE": "EXAONE"}


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def stop_port(port: int) -> None:
    cmd = (
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        f"Select-Object -First 1; if($c -and $c.OwningProcess -gt 0)"
        f"{{ Stop-Process -Id $c.OwningProcess -Force }}"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)


def ensure_model(model: str, *, alone: bool = True) -> float:
    """모델을 올리고, alone이면 다른 쪽을 내린다. 교체 시간(초) 반환."""
    t0 = time.perf_counter()
    other = "AX" if model == "EXAONE" else "EXAONE"
    if alone and health(ENDPOINTS[other]["health"]):
        stop_port(ENDPOINTS[other]["port"])
        time.sleep(3)
    if health(ENDPOINTS[model]["health"]):
        return time.perf_counter() - t0
    log = (OUT / f"start_{model.lower()}_quant.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(APP / ENDPOINTS[model]["start"])],
        cwd=str(APP),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(300):
        if health(ENDPOINTS[model]["health"]):
            print(f"{model}_UP", flush=True)
            return time.perf_counter() - t0
        if proc.poll() is not None:
            raise SystemExit(f"{model} start fail")
        time.sleep(2)
    raise SystemExit(f"{model} timeout")


def load_domain_docs(domain: str) -> list[dict]:
    ids = load_split_ids("dev", domain, SPLIT_FILE_V2)
    rows = load_jsonl(GOLD[domain]["contract"])
    twin_p = clean_twin_path(domain)
    if twin_p.exists():
        rows = rows + load_jsonl(twin_p)
    law_path = GOLD[domain]["law"]
    law_map = {r["segment_id"]: r for r in load_jsonl(law_path)} if law_path.exists() else {}
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.get("doc_id") in ids:
            by[r["doc_id"]].append(r)
    docs = []
    for did in sorted(by):
        segs = sorted(
            by[did],
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        docs.append({"domain": domain, "doc_id": did, "segs": segs, "law_map": law_map})
    return docs


def _hit_slim(h: dict, rank: int) -> dict:
    return {
        "id": h.get("id"),
        "rank": rank,
        "score": h.get("score"),
        "rrf": h.get("rrf"),
        "title": h.get("title"),
        "doc_type": h.get("doc_type"),
        # replay 재현을 위해 전문 유지
        "text": h.get("text") or "",
    }


def run_one(*, model: str, domain: str, out_jsonl: Path) -> dict:
    ep = ENDPOINTS[model]
    set_llm_endpoint(ep["url"], ep["health"])
    if not ax_up():
        raise SystemExit(f"STOP {model} down")
    docs = load_domain_docs(domain)
    index, _ = get_index()
    reset_needs_fact_stats()
    use_criteria = True
    nf_mode = "cards"

    rows = []
    t0 = time.perf_counter()
    for doc in docs:
        did = doc["doc_id"]
        tox = any(s.get("label") == "toxic" for s in doc["segs"])
        # clean_v2: toxic 0 and check 0
        labs = {s.get("label") for s in doc["segs"]}
        is_clean = ("toxic" not in labs) and ("check" not in labs)
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = domain
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            law = doc["law_map"].get(seg.get("segment_id") or "", {})
            t1 = time.perf_counter()
            hits_raw = (index.search(strip_placeholders(text), domain=domain, title="") or {}).get("hits") or []
            finding = generate_finding(text, facts, hits_raw, use_criteria=use_criteria)
            hits_for_v = finding.get("hits_for_verify") or hits_raw
            hits_slim = [_hit_slim(h, i + 1) for i, h in enumerate(hits_for_v)]
            cards = select_cards(text, limit=2, domain=domain) if use_criteria else []
            # 원본 저장용: verify는 ax_review_to_ok=False 로 실행
            verified = verify_finding(
                text,
                hits_for_v,
                finding,
                facts,
                needs_fact_mode=nf_mode,
                selected_cards=cards,
                ax_review_to_ok=False,
            )
            ms = (time.perf_counter() - t1) * 1000
            verdict = verified.get("verdict") or "확인 필요"
            label = seg.get("label") or ""
            nf = verified.get("needs_fact")
            blocking = bool(nf) and is_blocking_fact(nf, cards) if cards else False
            notes = verified.get("notes") or []
            rs = verified.get("review_sources") or []
            row = {
                "domain": domain,
                "model": model,
                "doc_id": did,
                "segment_id": seg.get("segment_id"),
                "std_item": seg.get("std_item") or law.get("std_item"),
                "label": label,
                "gold_codes": gold_codes(seg, law),
                "gold_provisions": gold_provisions(seg, law),
                "is_clean_doc": is_clean,
                "is_clean_twin": "-C" in did,
                "text": text,
                "finding": {
                    "verdict": finding.get("verdict"),
                    "contract_quote": finding.get("contract_quote"),
                    "evidence": finding.get("evidence") or [],
                    "needs_fact": finding.get("needs_fact"),
                    "why": finding.get("why"),
                    "suggestion": finding.get("suggestion"),
                    "gap": finding.get("gap"),
                    "parse_ok": finding.get("parse_ok"),
                    "raw": finding.get("raw"),
                    "error": finding.get("error"),
                    "selected_cards": finding.get("selected_cards") or [],
                },
                "hits": hits_slim,
                "selected_cards": [c.get("id") for c in cards if c.get("id")],
                "selected_cards_full": [
                    {
                        "id": c.get("id"),
                        "blocking_if": c.get("blocking_if"),
                        "violation": c.get("violation") or [],
                        "safe": c.get("safe") or [],
                    }
                    for c in cards
                ],
                "facts": facts,
                "verdict": verdict,
                "ax_verdict": verified.get("ax_verdict"),
                "review_source": classify_review_source(verified, verdict),
                "review_sources": rs,
                "notes": notes,
                "needs_fact": nf,
                "needs_fact_action": verified.get("needs_fact_action"),
                "needs_fact_is_blocking_if": blocking if nf else None,
                "dropped_ids": verified.get("dropped_ids") or [],
                "quote_mismatch": "quote_mismatch" in rs or any("quote_mismatch" in str(n) for n in notes),
                "parse_ok": bool(verified.get("parse_ok")),
                "evidence_final": verified.get("evidence") or [],
                "rule": verified.get("rule") or {},
                "doc_question": verified.get("doc_question"),
                "latency_ms": round(ms, 1),
                "bucket": score_pair(label, verdict),
                "ax_review_to_ok_run": False,
            }
            rows.append(row)
        print(f"  DOC {domain} {did} clean={is_clean} n={sum(1 for r in rows if r['doc_id']==did)}", flush=True)

    wall = time.perf_counter() - t0
    set_llm_endpoint(None, None)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = {
        "model": model,
        "model_label": ep["label"],
        "domain": domain,
        "ax_review_to_ok": False,
        "n_rows": len(rows),
        "wall_sec": round(wall, 2),
        "mean_latency_ms": round(wall * 1000 / max(1, len(rows)), 1),
        "needs_fact_stats": dict(NEEDS_FACT_STATS),
        "jsonl": str(out_jsonl),
    }
    meta_path = out_jsonl.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", out_jsonl, "rows=", len(rows), "wall=", meta["wall_sec"], flush=True)
    return meta


def out_path(model: str, domain: str) -> Path:
    return OUT / "quant" / f"{model}_{domain}_rows.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["AX", "EXAONE"])
    parser.add_argument("--domain", required=True, choices=["LAB", "LEASE", "LOAN"])
    parser.add_argument("--ensure", action="store_true", help="모델 기동/교체")
    parser.add_argument("--alone", action="store_true", default=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "quant").mkdir(parents=True, exist_ok=True)
    switch_sec = 0.0
    if args.ensure:
        switch_sec = ensure_model(args.model, alone=True)
        print(f"SWITCH_SEC {switch_sec:.1f}", flush=True)
    meta = run_one(model=args.model, domain=args.domain, out_jsonl=out_path(args.model, args.domain))
    meta["switch_sec"] = round(switch_sec, 2)
    meta_path = out_path(args.model, args.domain).with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
