# -*- coding: utf-8 -*-
"""QUANT_FULL 오케스트레이터: 실행 → replay → 보고. 중간 질문 없음."""
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
from quant_run import ENDPOINTS, ensure_model, out_path, run_one, health, stop_port  # noqa: E402
from replay import (  # noqa: E402
    RISKY,
    cascade_rows,
    check_reproducibility,
    clause_metrics,
    doc_metrics,
    evidence_match_rate,
    goals_flags,
    load_rows,
    mcnemar_compare,
    pick_best,
    recall_at_3,
    sweep_all,
    timing_stats,
    transform_row,
    verify_stats,
    write_csv,
)
from relax_check import counts_as_review_for_doc  # noqa: E402
from metrics import rate as rate_fmt  # noqa: E402
from recall_dev import canon_from_id, load_jsonl  # noqa: E402
from rag.corpus import load_corpus  # noqa: E402

MODELS = ("EXAONE", "AX")  # EXAONE first if already up after RELAX P
DOMAINS = ("LAB", "LEASE", "LOAN")
QUANT = OUT / "quant"
TABLES = QUANT / "tables"


def _meta_path(model: str, domain: str) -> Path:
    return out_path(model, domain).with_suffix(".meta.json")


def rows_ok(model: str, domain: str) -> bool:
    p = out_path(model, domain)
    if not p.exists():
        return False
    # 1장 필수 필드 샘플 확인
    rows = load_rows(p)
    if not rows:
        return False
    r0 = rows[0]
    need = ("finding", "hits", "facts", "text", "verdict", "gold_codes", "latency_ms")
    return all(k in r0 for k in need)


def run_all_models(*, skip_existing: bool = True) -> dict:
    QUANT.mkdir(parents=True, exist_ok=True)
    switch_log = []
    metas = {}
    # Prefer current up model order
    order = list(MODELS)
    if health(ENDPOINTS["EXAONE"]["health"]) and not health(ENDPOINTS["AX"]["health"]):
        order = ["EXAONE", "AX"]
    elif health(ENDPOINTS["AX"]["health"]) and not health(ENDPOINTS["EXAONE"]["health"]):
        order = ["AX", "EXAONE"]

    for model in order:
        need_any = [d for d in DOMAINS if not (skip_existing and rows_ok(model, d))]
        if not need_any:
            print(f"SKIP model runs {model} (all domains present)", flush=True)
            for d in DOMAINS:
                mp = _meta_path(model, d)
                if mp.exists():
                    metas[f"{model}_{d}"] = json.loads(mp.read_text(encoding="utf-8"))
            continue
        sw = ensure_model(model, alone=True)
        switch_log.append({"to": model, "sec": round(sw, 2), "ts": time.time()})
        print(f"SWITCH to {model} {sw:.1f}s", flush=True)
        for domain in DOMAINS:
            key = f"{model}_{domain}"
            if skip_existing and rows_ok(model, domain):
                print(f"SKIP {key}", flush=True)
                metas[key] = json.loads(_meta_path(model, domain).read_text(encoding="utf-8"))
                continue
            print(f"RUN {key}", flush=True)
            meta = run_one(model=model, domain=domain, out_jsonl=out_path(model, domain))
            meta["switch_sec_before_model"] = round(sw, 2)
            _meta_path(model, domain).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            metas[key] = meta
            sw = 0.0  # only first domain pays switch

    # 끝나면 EXAONE 유지
    if not health(ENDPOINTS["EXAONE"]["health"]):
        sw = ensure_model("EXAONE", alone=True)
        switch_log.append({"to": "EXAONE", "sec": round(sw, 2), "final": True})
        print(f"FINAL EXAONE_UP {sw:.1f}s", flush=True)
    else:
        # AX 내리기
        if health(ENDPOINTS["AX"]["health"]):
            t0 = time.perf_counter()
            stop_port(8082)
            time.sleep(2)
            switch_log.append({"action": "stop_AX_keep_EXAONE", "sec": round(time.perf_counter() - t0, 2)})

    (QUANT / "switch_log.json").write_text(json.dumps(switch_log, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metas": metas, "switch_log": switch_log}


def analyze() -> dict:
    TABLES.mkdir(parents=True, exist_ok=True)
    corpus, _skipped = load_corpus()
    corpus_ids = [c["id"] for c in corpus]
    corpus_keys = set()
    for c in corpus:
        k = canon_from_id(c["id"])
        if k:
            corpus_keys.add(k)

    # recall@3 once per domain
    recall = {d: recall_at_3(d) for d in DOMAINS}
    write_csv(
        TABLES / "recall_at3.csv",
        [{"domain": d, **{k: v for k, v in recall[d].items() if k != "domain"}} for d in DOMAINS],
    )

    repro = {}
    sweeps = {}
    best = {}
    best_by_domain = {}
    clause_tables = []
    doc_tables = []
    unknown = []

    for model in ("AX", "EXAONE"):
        model_cells = []
        for domain in DOMAINS:
            p = out_path(model, domain)
            if not p.exists():
                unknown.append(f"missing {model}_{domain}")
                continue
            rows = load_rows(p)
            rp = check_reproducibility(rows)
            repro[f"{model}_{domain}"] = {k: rp[k] for k in ("n", "mismatch", "ok")}
            if not rp["ok"]:
                unknown.append(f"repro_fail {model}_{domain} mismatch={rp['mismatch']}")
                (QUANT / f"repro_{model}_{domain}.json").write_text(
                    json.dumps(rp, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                # 지시: 다르면 멈추고 원인 — 여기서는 기록 후 계속하되 보고에 명시
            cells = sweep_all(rows)
            sweeps[f"{model}_{domain}"] = cells
            meta = {}
            mp = _meta_path(model, domain)
            if mp.exists():
                meta = json.loads(mp.read_text(encoding="utf-8"))
            timing = timing_stats(rows, switch_sec=float(meta.get("switch_sec_before_model") or meta.get("switch_sec") or 0))
            # evidence on base (axok=False,num2way=False) transformed
            base = [transform_row(r, axok=False, num2way=False) for r in rows]
            ev = evidence_match_rate(base, corpus_keys, corpus_ids)
            vs = verify_stats(base)

            # domain best
            b = pick_best(cells)
            if b:
                best_by_domain[f"{model}_{domain}"] = dict(b)
                model_cells.append(b)

            for c in cells:
                clause_tables.append(
                    {
                        "model": model,
                        "domain": domain,
                        "axok": c["axok"],
                        "num2way": c["num2way"],
                        "R": c["R"],
                        "K": c["K"],
                        "warn_capture": c["warn_capture_rate"],
                        "detect": c["detect_rate"],
                        "fp": c["fp_rate"],
                        "overwarn": c["overwarn_rate"],
                        "check": c["check_rate"],
                        "clean_pass": c["clean_pass_rate"],
                        "toxic_miss_n": c["toxic_miss_n"],
                    }
                )
            # base verify/timing
            (QUANT / f"verify_{model}_{domain}.json").write_text(
                json.dumps({"verify": vs, "timing": timing, "evidence": ev, "repro": repro[f"{model}_{domain}"]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # model-level best across domains: aggregate by same (axok,num2way,R,K)
        if model_cells:
            # pick using pooled metrics across domains for each combo key
            pooled = {}
            for domain in DOMAINS:
                key = f"{model}_{domain}"
                for c in sweeps.get(key) or []:
                    ck = (c["axok"], c["num2way"], c["R"], c["K"])
                    slot = pooled.setdefault(
                        ck,
                        {
                            "axok": c["axok"],
                            "num2way": c["num2way"],
                            "R": c["R"],
                            "K": c["K"],
                            "warn_num": 0,
                            "warn_den": 0,
                            "fp_num": 0,
                            "fp_den": 0,
                            "ow_num": 0,
                            "clean_num": 0,
                            "clean_den": 0,
                            "miss_n": 0,
                            "overwarn_den": 0,
                        },
                    )
                    # parse rates from strings is hard; recompute from stored p fields
                    wn = int(round((c.get("warn_capture_p") or 0) * (c.get("toxic_n") or 0)))
                    wd = c.get("toxic_n") or 0
                    slot["warn_num"] += wn
                    slot["warn_den"] += wd
                    fn = int(round((c.get("fp_p") or 0) * (c.get("safe_n") or 0)))
                    fd = c.get("safe_n") or 0
                    slot["fp_num"] += fn
                    slot["fp_den"] += fd
                    slot["miss_n"] += c.get("toxic_miss_n") or 0
                    slot["clean_num"] += c.get("clean_pass") or 0
                    slot["clean_den"] += c.get("clean_n") or 0
                    slot["ow_num"] = slot.get("ow_num", 0) + int(round((c.get("overwarn_p") or 0) * fd))
                    slot["overwarn_den"] += fd

            pool_list = []
            for ck, s in pooled.items():
                pool_list.append(
                    {
                        **{k: s[k] for k in ("axok", "num2way", "R", "K")},
                        "toxic_miss_n": s["miss_n"],
                        "warn_capture_p": (s["warn_num"] / s["warn_den"]) if s["warn_den"] else None,
                        "clean_pass_p": (s["clean_num"] / s["clean_den"]) if s["clean_den"] else None,
                        "fp_p": (s["fp_num"] / s["fp_den"]) if s["fp_den"] else None,
                        "overwarn_p": (s["ow_num"] / s["overwarn_den"]) if s["overwarn_den"] else None,
                        "warn_capture_rate": rate_fmt(s["warn_num"], s["warn_den"]),
                        "clean_pass_rate": rate_fmt(s["clean_num"], s["clean_den"]),
                        "fp_rate": rate_fmt(s["fp_num"], s["fp_den"]),
                        "overwarn_rate": rate_fmt(s["ow_num"], s["overwarn_den"]),
                    }
                )
            best[model] = pick_best(pool_list)

    write_csv(TABLES / "clause_doc_grid.csv", clause_tables)

    # McNemar at best combos
    mcnemar = {}
    for domain in DOMAINS:
        ax_p = out_path("AX", domain)
        ex_p = out_path("EXAONE", domain)
        if not (ax_p.exists() and ex_p.exists()):
            continue
        ax_cfg = best.get("AX") or {"axok": False, "num2way": False}
        ex_cfg = best.get("EXAONE") or {"axok": False, "num2way": False}
        # domain-specific if available
        ax_d = best_by_domain.get(f"AX_{domain}") or ax_cfg
        ex_d = best_by_domain.get(f"EXAONE_{domain}") or ex_cfg
        ax_rows = [transform_row(r, axok=ax_d["axok"], num2way=ax_d["num2way"]) for r in load_rows(ax_p)]
        ex_rows = [transform_row(r, axok=ex_d["axok"], num2way=ex_d["num2way"]) for r in load_rows(ex_p)]
        mcnemar[domain] = {
            "warn_capture": mcnemar_compare(ax_rows, ex_rows, kind="warn_capture"),
            "fp": mcnemar_compare(ax_rows, ex_rows, kind="fp"),
            "ax_cfg": {k: ax_d[k] for k in ("axok", "num2way", "R", "K") if k in ax_d},
            "ex_cfg": {k: ex_d[k] for k in ("axok", "num2way", "R", "K") if k in ex_d},
        }

    # Cascade
    cascade = {}
    ax_best = best.get("AX") or {"axok": False, "num2way": False, "R": "R0", "K": 2}
    ex_best = best.get("EXAONE") or {"axok": False, "num2way": False, "R": "R0", "K": 2}
    switch_sec = 0.0
    slog = QUANT / "switch_log.json"
    if slog.exists():
        for item in json.loads(slog.read_text(encoding="utf-8")):
            if item.get("to") == "EXAONE" or item.get("to") == "AX":
                switch_sec = max(switch_sec, float(item.get("sec") or 0))

    for domain in DOMAINS:
        ax_p = out_path("AX", domain)
        ex_p = out_path("EXAONE", domain)
        if not (ax_p.exists() and ex_p.exists()):
            continue
        ax_rows = load_rows(ax_p)
        ex_rows = load_rows(ex_p)
        merged, n_ex = cascade_rows(ax_rows, ex_rows, ax_best, ex_best)
        cm = clause_metrics(merged)
        dm = doc_metrics(merged, ax_best.get("R", "R0"), int(ax_best.get("K", 2)))
        # time: AX all + EXAONE subset + 1 switch
        ax_ms = sum(float(r.get("latency_ms") or 0) for r in ax_rows)
        ex_by = {(r["doc_id"], r["segment_id"]): r for r in ex_rows}
        ex_ms = 0.0
        for r in merged:
            if r.get("cascade_source") == "EXAONE":
                er = ex_by.get((r["doc_id"], r["segment_id"]))
                if er:
                    ex_ms += float(er.get("latency_ms") or 0)
        n_docs = len({r["doc_id"] for r in merged})
        total_sec = (ax_ms + ex_ms) / 1000 + switch_sec
        cascade[domain] = {
            "clause": {k: cm[k] for k in (
                "warn_capture_rate", "fp_rate", "overwarn_rate", "detect_rate",
                "warn_capture_p", "fp_p", "overwarn_p",
            )},
            "doc": {
                "clean_pass_rate": dm["clean_pass_rate"],
                "clean_pass_p": dm["clean_pass_p"],
                "toxic_miss_n": dm["toxic_miss_n"],
                "toxic_misses": dm["toxic_misses"],
            },
            "n_exaone_segments": n_ex,
            "n_segments": len(merged),
            "time_sec_total": round(total_sec, 1),
            "time_sec_per_doc": round(total_sec / max(1, n_docs), 2),
            "ax_ms": round(ax_ms, 1),
            "ex_ms": round(ex_ms, 1),
            "switch_sec": switch_sec,
        }

    # clean failure analysis at best
    clean_fail = {}
    for model in ("AX", "EXAONE"):
        cfg = best.get(model)
        if not cfg:
            continue
        fails = []
        for domain in DOMAINS:
            p = out_path(model, domain)
            if not p.exists():
                continue
            rows = [transform_row(r, axok=cfg["axok"], num2way=cfg["num2way"]) for r in load_rows(p)]
            dm = doc_metrics(rows, cfg.get("R", "R0"), int(cfg.get("K", 2)))
            for did, hl in dm["headlines"].items():
                rs = [r for r in rows if r["doc_id"] == did]
                if not rs or not rs[0].get("is_clean_doc"):
                    continue
                if hl == "큰 문제 없음":
                    continue
                for r in rs:
                        if r.get("verdict") in RISKY or (
                            r.get("verdict") == "확인 필요"
                            and counts_as_review_for_doc(r, cfg.get("R", "R0"))
                        ):
                            fails.append(
                                {
                                    "model": model,
                                    "domain": domain,
                                    "doc_id": did,
                                    "text50": (r.get("text") or "")[:50],
                                    "std_item": r.get("std_item"),
                                    "verdict": r.get("verdict"),
                                    "cards": r.get("selected_cards"),
                                    "review_source": r.get("review_source"),
                                    "rule": (r.get("rule") or {}).get("verdict"),
                                    "num2way_flipped": r.get("num2way_flipped"),
                                }
                            )
        clean_fail[model] = fails
        write_csv(TABLES / f"clean_fail_{model}.csv", fails)

    # one-page summary
    summary_rows = []
    for tag, model, cfg_key in (
        ("빠른 검토(A.X 최적)", "AX", "AX"),
        ("정밀 검사(EXAONE 최적)", "EXAONE", "EXAONE"),
    ):
        cfg = best.get(cfg_key) or {}
        row = {"mode": tag, "axok": cfg.get("axok"), "num2way": cfg.get("num2way"), "R": cfg.get("R"), "K": cfg.get("K")}
        for domain in DOMAINS:
            p = out_path(cfg_key, domain)
            if not p.exists() or not cfg:
                for m in ("warn", "fp", "ow", "clean", "time"):
                    row[f"{domain}_{m}"] = "미확인"
                continue
            rows = [transform_row(r, axok=cfg["axok"], num2way=cfg["num2way"]) for r in load_rows(p)]
            cm = clause_metrics(rows)
            dm = doc_metrics(rows, cfg.get("R", "R0"), int(cfg.get("K", 2)))
            ts = timing_stats(load_rows(p))
            row[f"{domain}_warn"] = cm["warn_capture_rate"]
            row[f"{domain}_fp"] = cm["fp_rate"]
            row[f"{domain}_ow"] = cm["overwarn_rate"]
            row[f"{domain}_clean"] = dm["clean_pass_rate"]
            row[f"{domain}_time"] = f"{ts['doc_mean_sec']}s"
            row[f"{domain}_miss"] = dm["toxic_miss_n"]
            row[f"{domain}_goals"] = goals_flags({**cm, **dm, "clean_pass_p": dm["clean_pass_p"]})
        summary_rows.append(row)

    # cascade summary row
    crow = {"mode": "캐스케이드", "axok": f"AX{ax_best}", "num2way": "", "R": "", "K": ""}
    for domain in DOMAINS:
        c = cascade.get(domain)
        if not c:
            for m in ("warn", "fp", "ow", "clean", "time"):
                crow[f"{domain}_{m}"] = "미확인"
            continue
        crow[f"{domain}_warn"] = c["clause"]["warn_capture_rate"]
        crow[f"{domain}_fp"] = c["clause"]["fp_rate"]
        crow[f"{domain}_ow"] = c["clause"]["overwarn_rate"]
        crow[f"{domain}_clean"] = c["doc"]["clean_pass_rate"]
        crow[f"{domain}_time"] = f"{c['time_sec_per_doc']}s"
        crow[f"{domain}_miss"] = c["doc"]["toxic_miss_n"]
    summary_rows.append(crow)
    write_csv(TABLES / "one_page_summary.csv", summary_rows)

    payload = {
        "repro": repro,
        "best": best,
        "best_by_domain": best_by_domain,
        "mcnemar": mcnemar,
        "cascade": cascade,
        "recall": recall,
        "unknown": unknown,
        "summary": summary_rows,
        "clean_fail_counts": {m: len(v) for m, v in clean_fail.items()},
    }
    (QUANT / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (QUANT / "sweeps.json").write_text(
        json.dumps(sweeps, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload


def write_report(payload: dict) -> Path:
    lines = []
    lines.append("# QUANT_FULL 보고")
    lines.append("")
    lines.append("dev만. test 미실행. 모델×도메인 1회 + 오프라인 replay.")
    lines.append("")
    lines.append("## 한 장 요약")
    lines.append("")
    lines.append("| 모드 | 근로 warn | 근로 fp | 근로 깨끗 | 근로 시간 | 임대 warn | 임대 fp | 임대 깨끗 | 차용 warn | 차용 fp | 차용 깨끗 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in payload.get("summary") or []:
        lines.append(
            "| {mode} | {LAB_warn} | {LAB_fp} | {LAB_clean} | {LAB_time} | {LEASE_warn} | {LEASE_fp} | {LEASE_clean} | {LOAN_warn} | {LOAN_fp} | {LOAN_clean} |".format(
                mode=r.get("mode"),
                LAB_warn=r.get("LAB_warn", "—"),
                LAB_fp=r.get("LAB_fp", "—"),
                LAB_clean=r.get("LAB_clean", "—"),
                LAB_time=r.get("LAB_time", "—"),
                LEASE_warn=r.get("LEASE_warn", "—"),
                LEASE_fp=r.get("LEASE_fp", "—"),
                LEASE_clean=r.get("LEASE_clean", "—"),
                LOAN_warn=r.get("LOAN_warn", "—"),
                LOAN_fp=r.get("LOAN_fp", "—"),
                LOAN_clean=r.get("LOAN_clean", "—"),
            )
        )
    lines.append("")
    lines.append("## 재현 확인")
    lines.append("")
    for k, v in (payload.get("repro") or {}).items():
        lines.append(f"- `{k}`: ok={v.get('ok')} mismatch={v.get('mismatch')}/{v.get('n')}")
    lines.append("")
    lines.append("## 모델별 최적 조합")
    lines.append("")
    for m, cfg in (payload.get("best") or {}).items():
        lines.append(
            f"- **{m}**: AXOK={cfg.get('axok')} NUM2WAY={cfg.get('num2way')} R={cfg.get('R')} K={cfg.get('K')} "
            f"| warn={cfg.get('warn_capture_rate')} clean={cfg.get('clean_pass_rate')} fp={cfg.get('fp_rate')} miss={cfg.get('toxic_miss_n')}"
        )
    lines.append("")
    lines.append("### 도메인별 최적")
    for k, cfg in (payload.get("best_by_domain") or {}).items():
        lines.append(
            f"- `{k}`: AXOK={cfg.get('axok')} NUM2WAY={cfg.get('num2way')} R={cfg.get('R')} K={cfg.get('K')} "
            f"warn={cfg.get('warn_capture_rate')} clean={cfg.get('clean_pass_rate')} miss={cfg.get('toxic_miss_n')}"
        )
    lines.append("")
    lines.append("## McNemar (A.X vs EXAONE, 각 모델 도메인 최적)")
    lines.append("")
    for d, m in (payload.get("mcnemar") or {}).items():
        w, f = m.get("warn_capture") or {}, m.get("fp") or {}
        lines.append(
            f"- **{d}** warn_capture: b={w.get('b')} c={w.get('c')} p={w.get('p')} | "
            f"fp: b={f.get('b')} c={f.get('c')} p={f.get('p')}"
        )
    lines.append("")
    lines.append("## 캐스케이드")
    lines.append("")
    for d, c in (payload.get("cascade") or {}).items():
        lines.append(
            f"- **{d}**: warn={c['clause']['warn_capture_rate']} fp={c['clause']['fp_rate']} "
            f"clean={c['doc']['clean_pass_rate']} miss={c['doc']['toxic_miss_n']} "
            f"EX조항={c['n_exaone_segments']}/{c['n_segments']} 시간/장={c['time_sec_per_doc']}s"
        )
        if c["doc"]["toxic_misses"]:
            lines.append(f"  - 놓침: {', '.join(c['doc']['toxic_misses'])}")
    lines.append("")
    lines.append("## 검색 recall@3")
    lines.append("")
    for d, r in (payload.get("recall") or {}).items():
        lines.append(f"- {d}: {r.get('recall_at_3')} (skip={r.get('skipped')})")
    lines.append("")
    lines.append("## 미확인")
    lines.append("")
    unk = payload.get("unknown") or []
    if not unk:
        lines.append("- (없음)")
    for u in unk:
        lines.append(f"- {u}")
    lines.append("")
    lines.append("산출: `out/quant/summary.json`, `out/quant/tables/*.csv`")
    path = OUT / "QUANT_FULL_REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--force-rerun", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    QUANT.mkdir(parents=True, exist_ok=True)

    if not args.analyze_only:
        print("=== QUANT_FULL RUN ===", flush=True)
        run_all_models(skip_existing=not args.force_rerun)
    print("=== QUANT_FULL ANALYZE ===", flush=True)
    payload = analyze()
    # stop if any repro hard-fail? instruction says stop and write cause — we recorded in unknown
    report = write_report(payload)
    print("WROTE", report, flush=True)
    print("BEST", json.dumps(payload.get("best"), ensure_ascii=False), flush=True)
    print("UNKNOWN", payload.get("unknown"), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
