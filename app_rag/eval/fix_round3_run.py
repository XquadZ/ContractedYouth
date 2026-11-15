# -*- coding: utf-8 -*-
"""FIX_ROUND3 C/D: EXAONE·A.X 실행 + 지표 + McNemar. out/quant3/."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.paths import OUT  # noqa: E402
from quant_run import ENDPOINTS, ensure_model, health, load_domain_docs, run_one, stop_port  # noqa: E402
from replay import (  # noqa: E402
    clause_metrics,
    doc_metrics,
    load_rows,
    mcnemar_compare,
    transform_row,
    write_csv,
)
from metrics import rate  # noqa: E402

QUANT3 = OUT / "quant3"
TABLES = QUANT3 / "tables"
DOMAINS = ("LAB", "LEASE", "LOAN")


def q3_path(model: str, domain: str) -> Path:
    return QUANT3 / f"{model}_{domain}_rows.jsonl"


def run_model(model: str, domains: list[str]) -> dict:
    QUANT3.mkdir(parents=True, exist_ok=True)
    sw = ensure_model(model, alone=True)
    metas = {}
    for i, domain in enumerate(domains):
        out = q3_path(model, domain)
        print(f"RUN {model}_{domain} -> {out}", flush=True)
        meta = run_one(model=model, domain=domain, out_jsonl=out)
        meta["switch_sec"] = round(sw if i == 0 else 0.0, 2)
        out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        metas[domain] = meta
    return metas


def analyze_rows(rows: list[dict], *, k: int = 2) -> dict:
    # NUM2WAY on, axok off (stored already axok=False; apply num2way in transform)
    tr = [transform_row(r, axok=False, num2way=True, ne_risky_only=True, num_year_doc=True) for r in rows]
    cm = clause_metrics(tr)
    dm = doc_metrics(tr, "R0", k, clean_v2=True)
    # 위반 오표시 없는 깨끗: clean docs with 0 risky
    by = {}
    for r in tr:
        by.setdefault(r["doc_id"], []).append(r)
    clean_no_fp = clean_n = 0
    for did, rs in by.items():
        labs = {x.get("label") for x in rs}
        if "toxic" in labs or "check" in labs:
            continue
        clean_n += 1
        if sum(1 for x in rs if x.get("verdict") in ("위반", "위험")) == 0:
            clean_no_fp += 1
    # timing
    ms = [float(r.get("latency_ms") or 0) for r in rows]
    by_doc = {}
    for r in rows:
        by_doc[r["doc_id"]] = by_doc.get(r["doc_id"], 0) + float(r.get("latency_ms") or 0)
    doc_mean = (sum(by_doc.values()) / max(1, len(by_doc))) / 1000
    # GENERAL toxic
    gen_tox = [
        {"doc_id": r["doc_id"], "segment_id": r["segment_id"], "cards": r.get("selected_cards")}
        for r in tr
        if r.get("label") == "toxic"
        and r.get("selected_cards")
        and all(str(c).endswith("GENERAL") for c in (r.get("selected_cards") or []))
    ]
    # K curve
    kcurve = {str(k0): doc_metrics(tr, "R0", k0, clean_v2=True) for k0 in (0, 1, 2, 3, 4, 5, 6, 8, 10)}
    return {
        "clause": {k: cm[k] for k in (
            "warn_capture_rate", "fp_rate", "overwarn_rate", "detect_rate", "check_rate",
            "warn_capture_p", "fp_p", "overwarn_p",
        )},
        "doc": {
            "clean_pass_rate": dm["clean_pass_rate"],
            "clean_pass_p": dm["clean_pass_p"],
            "check_doc_rate": dm["check_doc_rate"],
            "toxic_miss_n": dm["toxic_miss_n"],
            "toxic_misses": dm["toxic_misses"],
            "clean_no_risky_rate": rate(clean_no_fp, clean_n),
            "clean_no_risky": clean_no_fp,
            "clean_n": clean_n,
        },
        "time_sec_per_doc": round(doc_mean, 2),
        "mean_ms": round(sum(ms) / max(1, len(ms)), 1),
        "general_toxic_n": len(gen_tox),
        "general_toxic": gen_tox[:20],
        "k_curve": {
            k: {"clean": v["clean_pass_rate"], "miss": v["toxic_miss_n"], "check_doc": v["check_doc_rate"]}
            for k, v in kcurve.items()
        },
    }


def compare_quant_full(domain: str) -> dict:
    old_p = OUT / "quant" / f"EXAONE_{domain}_rows.jsonl"
    new_p = q3_path("EXAONE", domain)
    if not (old_p.exists() and new_p.exists()):
        return {"ok": False}
    old = analyze_rows(load_rows(old_p))
    new = analyze_rows(load_rows(new_p))
    return {"ok": True, "before": old, "after": new}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["C", "D", "analyze"], required=True)
    parser.add_argument("--domains", default="LAB,LEASE,LOAN")
    args = parser.parse_args()
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    TABLES.mkdir(parents=True, exist_ok=True)

    if args.phase == "C":
        print("=== FIX_ROUND3-C EXAONE ===", flush=True)
        metas = run_model("EXAONE", domains)
        # leave EXAONE up
        summary = {}
        for d in domains:
            rows = load_rows(q3_path("EXAONE", d))
            summary[d] = analyze_rows(rows)
            summary[d]["compare"] = compare_quant_full(d)
            summary[d]["meta"] = metas.get(d)
        (QUANT3 / "C_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", QUANT3 / "C_summary.json", flush=True)
        print("EXAONE left UP", flush=True)
        return

    if args.phase == "D":
        print("=== FIX_ROUND3-D A.X ===", flush=True)
        metas = run_model("AX", domains)
        # switch back to EXAONE
        sw = ensure_model("EXAONE", alone=True)
        print(f"FINAL EXAONE_UP {sw:.1f}s", flush=True)
        summary = {}
        mcn = {}
        for d in domains:
            ax_rows = load_rows(q3_path("AX", d))
            ex_rows = load_rows(q3_path("EXAONE", d)) if q3_path("EXAONE", d).exists() else []
            summary[d] = {"AX": analyze_rows(ax_rows), "meta": metas.get(d)}
            if ex_rows:
                summary[d]["EXAONE"] = analyze_rows(ex_rows)
                ax_t = [transform_row(r, axok=False, num2way=True, ne_risky_only=True, num_year_doc=True) for r in ax_rows]
                ex_t = [transform_row(r, axok=False, num2way=True, ne_risky_only=True, num_year_doc=True) for r in ex_rows]
                mcn[d] = {
                    "warn_capture": mcnemar_compare(ax_t, ex_t, kind="warn_capture"),
                    "fp": mcnemar_compare(ax_t, ex_t, kind="fp"),
                }
        (QUANT3 / "D_summary.json").write_text(
            json.dumps({"summary": summary, "mcnemar": mcn}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("WROTE", QUANT3 / "D_summary.json", flush=True)
        return

    # analyze only
    out = {}
    for model in ("EXAONE", "AX"):
        out[model] = {}
        for d in DOMAINS:
            p = q3_path(model, d)
            if p.exists():
                out[model][d] = analyze_rows(load_rows(p))
    (QUANT3 / "analyze.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE analyze", flush=True)


if __name__ == "__main__":
    main()
