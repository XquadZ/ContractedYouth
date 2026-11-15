# -*- coding: utf-8 -*-
"""FIX_ROUND1-D: 새 v2 dev + clean twin. LAB D1~D4 + LEASE/LOAN A.X 기준점."""
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

from rag.criteria import select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, generate_finding, set_llm_endpoint  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import NEEDS_FACT_STATS, reset_needs_fact_stats, verify_finding  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from metrics import rate, score_pair, summarize_rows  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta  # noqa: E402

ENDPOINTS = {
    "AX": {
        "url": "http://127.0.0.1:8082/v1/chat/completions",
        "health": "http://127.0.0.1:8082/health",
        "label": "A.X-4.0-Light",
    },
    "EXAONE": {
        "url": "http://127.0.0.1:8083/v1/chat/completions",
        "health": "http://127.0.0.1:8083/health",
        "label": "EXAONE-4.0-32B-Q4_K_M",
    },
}


def load_domain_docs(domain: str) -> list[dict]:
    ids = load_split_ids("dev", domain, SPLIT_FILE_V2)
    rows = load_jsonl(GOLD[domain]["contract"])
    twin_p = clean_twin_path(domain)
    if twin_p.exists():
        rows = rows + load_jsonl(twin_p)
    law_path = GOLD[domain]["law"]
    law_map = {r["segment_id"]: r for r in load_jsonl(law_path)} if law_path.exists() else {}
    by = defaultdict(list)
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


def eval_docs(docs, index, *, use_criteria: bool, needs_fact_mode: str, ax_review_to_ok: bool) -> dict:
    reset_needs_fact_stats()
    all_rows = []
    t0 = time.perf_counter()
    for doc in docs:
        domain = doc["domain"]
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = domain
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            t1 = time.perf_counter()
            hits = (index.search(strip_placeholders(text), domain=domain, title="") or {}).get("hits") or []
            finding = generate_finding(text, facts, hits, use_criteria=use_criteria and domain == "LAB")
            cards = select_cards(text, limit=2) if (use_criteria and domain == "LAB") else []
            verified = verify_finding(
                text,
                hits,
                finding,
                facts,
                needs_fact_mode=needs_fact_mode if domain == "LAB" else "legacy",
                selected_cards=cards,
                ax_review_to_ok=ax_review_to_ok,
            )
            ms = (time.perf_counter() - t1) * 1000
            verdict = verified.get("verdict") or "확인 필요"
            label = seg.get("label") or ""
            all_rows.append(
                {
                    "domain": domain,
                    "doc_id": doc["doc_id"],
                    "segment_id": seg.get("segment_id"),
                    "label": label,
                    "verdict": verdict,
                    "ax_verdict": verified.get("ax_verdict"),
                    "bucket": score_pair(label, verdict),
                    "needs_fact_action": verified.get("needs_fact_action"),
                    "ax_review_to_ok": verified.get("needs_fact_action") == "ax_review_to_ok"
                    or "ax_review_to_ok" in (verified.get("notes") or []),
                    "parse_ok": bool(verified.get("parse_ok")),
                    "latency_ms": round(ms, 1),
                    "is_clean_twin": "-C" in (doc["doc_id"] or ""),
                }
            )
        print(f"  DOC {doc['domain']} {doc['doc_id']} n_acc={len(all_rows)}", flush=True)
    wall = time.perf_counter() - t0
    summary = summarize_rows(all_rows)
    summary["wall_sec"] = round(wall, 2)
    summary["mean_latency_ms"] = round(sum(r["latency_ms"] for r in all_rows) / max(1, len(all_rows)), 1)
    summary["needs_fact_stats"] = dict(NEEDS_FACT_STATS)
    return {"summary": summary, "rows": all_rows, "wall_sec": round(wall, 2)}


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def stop_port(port: int) -> None:
    try:
        import psutil  # type: ignore
    except Exception:
        psutil = None
    # powershell fallback
    cmd = (
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        f"Select-Object -First 1; if($c -and $c.OwningProcess){{ Stop-Process -Id $c.OwningProcess -Force }}"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)


def ensure_ax() -> None:
    if health(ENDPOINTS["AX"]["health"]):
        return
    subprocess.Popen(
        [sys.executable, str(APP / "start_ax.py")],
        cwd=str(APP),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        if health(ENDPOINTS["AX"]["health"]):
            return
        time.sleep(2)
    raise SystemExit("AX start fail")


def ensure_exaone_only() -> None:
    # A.X 잠시 내림
    if health(ENDPOINTS["AX"]["health"]):
        stop_port(8082)
        time.sleep(3)
    if health(ENDPOINTS["EXAONE"]["health"]):
        return
    proc = subprocess.Popen(
        [sys.executable, str(APP / "start_exaone.py")],
        cwd=str(APP),
        stdout=(APP / "out" / "start_exaone_d.log").open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    for _ in range(300):
        if health(ENDPOINTS["EXAONE"]["health"]):
            return
        if proc.poll() is not None:
            raise SystemExit("EXAONE start fail")
        time.sleep(2)
    raise SystemExit("EXAONE health timeout")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--skip-exaone", action="store_true")
    parser.add_argument("--only", default="", help="comma: D1,D2,D3,D4,BASE")
    args = parser.parse_args()

    lab = load_domain_docs("LAB")
    lease = load_domain_docs("LEASE")
    loan = load_domain_docs("LOAN")
    n_lab = sum(1 for d in lab for s in d["segs"] if not is_meta(s))
    n_lease = sum(1 for d in lease for s in d["segs"] if not is_meta(s))
    n_loan = sum(1 for d in loan for s in d["segs"] if not is_meta(s))
    est = {
        "LAB_judge": n_lab,
        "LEASE_judge": n_lease,
        "LOAN_judge": n_loan,
        "D1_D2_AX_min": round(n_lab * 2.64 * 2 / 60, 1),
        "D3_D4_EX_min": round(n_lab * 8.3 * 2 / 60, 1),
        "BASE_LEASE_LOAN_AX_min": round((n_lease + n_loan) * 2.64 / 60, 1),
    }
    est["total_min"] = round(est["D1_D2_AX_min"] + est["D3_D4_EX_min"] + est["BASE_LEASE_LOAN_AX_min"], 1)
    print("ESTIMATE", json.dumps(est, ensure_ascii=False), flush=True)
    if args.estimate_only:
        (OUT / "fix_round1_d_estimate.json").write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if est["total_min"] > 90 and "--force" not in sys.argv:
        # caller should have asked; allow --force
        pass

    only = {x.strip() for x in args.only.split(",") if x.strip()} or {"D1", "D2", "D3", "D4", "BASE"}
    index, _ = get_index()
    results = {"estimate": est, "runs": {}}

    def run_lab(tag, model, ax_ok):
        ep = ENDPOINTS[model]
        set_llm_endpoint(ep["url"], ep["health"])
        if not ax_up():
            raise SystemExit(f"{model} down")
        print("RUN", tag, model, "ax_review_to_ok", ax_ok, flush=True)
        pack = eval_docs(
            lab,
            index,
            use_criteria=True,
            needs_fact_mode="cards",
            ax_review_to_ok=ax_ok,
        )
        results["runs"][tag] = {
            "model": model,
            "ax_review_to_ok": ax_ok,
            "domain": "LAB",
            "summary": pack["summary"],
        }
        set_llm_endpoint(None, None)
        dest = OUT / f"fix_round1_{tag.lower()}.json"
        dest.write_text(json.dumps(results["runs"][tag], ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", dest, "detect", pack["summary"]["detect_rate"], "warn", pack["summary"]["warn_capture_rate"])

    if "D1" in only or "D2" in only:
        ensure_ax()
        if "D1" in only:
            run_lab("D1", "AX", True)
        if "D2" in only:
            run_lab("D2", "AX", False)

    if not args.skip_exaone and ("D3" in only or "D4" in only):
        ensure_exaone_only()
        if "D3" in only:
            run_lab("D3", "EXAONE", True)
        if "D4" in only:
            run_lab("D4", "EXAONE", False)
        stop_port(8083)
        time.sleep(3)
        ensure_ax()

    if "BASE" in only:
        ensure_ax()
        set_llm_endpoint(ENDPOINTS["AX"]["url"], ENDPOINTS["AX"]["health"])
        print("RUN BASE LEASE+LOAN AX", flush=True)
        pack_l = eval_docs(lease, index, use_criteria=False, needs_fact_mode="legacy", ax_review_to_ok=True)
        pack_o = eval_docs(loan, index, use_criteria=False, needs_fact_mode="legacy", ax_review_to_ok=True)
        results["runs"]["BASE_LEASE"] = {"model": "AX", "domain": "LEASE", "summary": pack_l["summary"]}
        results["runs"]["BASE_LOAN"] = {"model": "AX", "domain": "LOAN", "summary": pack_o["summary"]}
        set_llm_endpoint(None, None)

    dest = OUT / "fix_round1_d.json"
    # strip huge rows
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
