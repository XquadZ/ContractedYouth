# -*- coding: utf-8 -*-
"""WEEK_FINAL-A: GPT rows → replay 지표·McNemar·점수·보고서."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.paths import OUT  # noqa: E402
from rag.score import score_from_findings  # noqa: E402
from replay import (  # noqa: E402
    clause_metrics,
    doc_metrics,
    load_rows,
    mcnemar_compare,
    pick_best,
    transform_row,
    write_csv,
    K_GRID,
    R_OPTS,
)
from metrics import rate  # noqa: E402
from quant_gpt_run import G1_ID, G2_ID, PRICING, QGPT, safe_model_tag  # noqa: E402
from fix_round3_run import analyze_rows, q3_path  # noqa: E402

DOMAINS = ("LAB", "LEASE", "LOAN")
# FIX_ROUND3와 맞춘 기본 변형
BASE_TF = dict(axok=False, num2way=True, ne_risky_only=True, num_year_doc=True)


def gpt_path(model_id: str, domain: str) -> Path:
    return QGPT / f"{safe_model_tag(model_id)}_{domain}_rows.jsonl"


def sweep_best(rows: list[dict]) -> dict | None:
    cells = []
    for axok in (False, True):
        for num2way in (False, True):
            for ne in (False, True):
                for yd in (False, True):
                    if not num2way and yd:
                        continue
                    tr = [
                        transform_row(r, axok=axok, num2way=num2way, ne_risky_only=ne, num_year_doc=yd)
                        for r in rows
                    ]
                    for clean_v2 in (False, True):
                        for method in R_OPTS:
                            for k in K_GRID:
                                cm = clause_metrics(tr)
                                dm = doc_metrics(tr, method, k, clean_v2=clean_v2)
                                cells.append(
                                    {
                                        "axok": axok,
                                        "num2way": num2way,
                                        "ne_risky_only": ne,
                                        "num_year_doc": yd,
                                        "clean_v2": clean_v2,
                                        "R": method,
                                        "K": k,
                                        "warn_capture_rate": cm["warn_capture_rate"],
                                        "warn_capture_p": cm["warn_capture_p"],
                                        "fp_rate": cm["fp_rate"],
                                        "fp_p": cm["fp_p"],
                                        "overwarn_rate": cm["overwarn_rate"],
                                        "clean_pass_rate": dm["clean_pass_rate"],
                                        "clean_pass_p": dm["clean_pass_p"],
                                        "toxic_miss_n": dm["toxic_miss_n"],
                                    }
                                )
    return pick_best(cells)


def score_docs(rows: list[dict]) -> dict:
    """문서별 점수·등급. missing/mismatch 미반영."""
    by = defaultdict(list)
    for r in rows:
        by[r["doc_id"]].append(r)
    clean_safe = clean_n = 0
    toxic_not_safe = toxic_n = 0
    details = []
    for did, rs in by.items():
        labs = {x.get("label") for x in rs}
        is_clean = "toxic" not in labs and "check" not in labs
        is_toxic = "toxic" in labs
        sc = score_from_findings(rs, missing_reflected=False, mismatch_reflected=False)
        details.append({"doc_id": did, "is_clean": is_clean, "is_toxic": is_toxic, **sc})
        if is_clean:
            clean_n += 1
            if sc["grade"] == "안전":
                clean_safe += 1
        if is_toxic:
            toxic_n += 1
            if sc["grade"] != "안전":
                toxic_not_safe += 1
    return {
        "clean_safe_rate": rate(clean_safe, clean_n),
        "clean_safe_p": (clean_safe / clean_n) if clean_n else None,
        "clean_n": clean_n,
        "toxic_not_safe_rate": rate(toxic_not_safe, toxic_n),
        "toxic_not_safe_p": (toxic_not_safe / toxic_n) if toxic_n else None,
        "toxic_n": toxic_n,
        "missing_mismatch": "미반영",
        "docs": details,
    }


def load_model_domain(model_key: str, domain: str) -> list[dict]:
    if model_key == "AX":
        p = q3_path("AX", domain)
    elif model_key == "EXAONE":
        p = q3_path("EXAONE", domain)
    elif model_key == "G1":
        p = gpt_path(G1_ID, domain)
    elif model_key == "G2":
        p = gpt_path(G2_ID, domain)
    else:
        return []
    if not p.exists():
        return []
    return load_rows(p)


def main() -> None:
    QGPT.mkdir(parents=True, exist_ok=True)
    plan = {}
    plan_p = QGPT / "plan.json"
    if plan_p.exists():
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
    run_sum = {}
    rs_p = QGPT / "run_summary.json"
    if rs_p.exists():
        run_sum = json.loads(rs_p.read_text(encoding="utf-8"))

    results = {}
    best = {}
    scores = {}
    for key, mid in (("G1", G1_ID), ("G2", G2_ID)):
        results[key] = {}
        best[key] = {}
        scores[key] = {}
        for d in DOMAINS:
            rows = load_model_domain(key, d)
            if not rows:
                results[key][d] = None
                continue
            tr = [transform_row(r, **BASE_TF) for r in rows]
            results[key][d] = analyze_rows(rows)
            results[key][d]["base_transform"] = BASE_TF
            best[key][d] = sweep_best(rows)
            scores[key][d] = score_docs(tr)

    # 로컬 모델 점수·지표 (quant3)
    local = {}
    local_scores = {}
    for key in ("AX", "EXAONE"):
        local[key] = {}
        local_scores[key] = {}
        for d in DOMAINS:
            rows = load_model_domain(key, d)
            if not rows:
                continue
            local[key][d] = analyze_rows(rows)
            tr = [transform_row(r, **BASE_TF) for r in rows]
            local_scores[key][d] = score_docs(tr)

    # McNemar: G1/G2 vs EXAONE, G1/G2 vs AX
    mcn = {}
    for d in DOMAINS:
        mcn[d] = {}
        pairs = [
            ("G1", "EXAONE"),
            ("G2", "EXAONE"),
            ("G1", "AX"),
            ("G2", "AX"),
            ("G1", "G2"),
        ]
        for a, b in pairs:
            ra = load_model_domain(a, d)
            rb = load_model_domain(b, d)
            if not ra or not rb:
                continue
            ta = [transform_row(r, **BASE_TF) for r in ra]
            tb = [transform_row(r, **BASE_TF) for r in rb]
            mcn[d][f"{a}_vs_{b}"] = {
                "warn_capture": mcnemar_compare(ta, tb, kind="warn_capture"),
                "fp": mcnemar_compare(ta, tb, kind="fp"),
            }

    # 한 장 표 행
    def cell(block, path, default="—"):
        if not block:
            return default
        cur = block
        for p in path.split("."):
            if cur is None:
                return default
            cur = cur.get(p) if isinstance(cur, dict) else None
        return cur if cur is not None else default

    table_rows = []
    for key in ("AX", "EXAONE", "G1", "G2"):
        src = local if key in ("AX", "EXAONE") else results
        sc = local_scores if key in ("AX", "EXAONE") else scores
        mid = {"AX": "A.X", "EXAONE": "EXAONE", "G1": G1_ID, "G2": G2_ID}[key]
        row = {"model": key, "model_id": mid}
        for d in DOMAINS:
            b = (src.get(key) or {}).get(d)
            s = (sc.get(key) or {}).get(d) or {}
            row[f"{d}_warn"] = cell(b, "clause.warn_capture_rate")
            row[f"{d}_fp"] = cell(b, "clause.fp_rate")
            row[f"{d}_ow"] = cell(b, "clause.overwarn_rate")
            row[f"{d}_clean"] = cell(b, "doc.clean_pass_rate")
            row[f"{d}_safe_clean"] = s.get("clean_safe_rate", "—")
            row[f"{d}_toxic_ns"] = s.get("toxic_not_safe_rate", "—")
            row[f"{d}_time"] = f"{cell(b, 'time_sec_per_doc')}s" if b else "—"
        # cost: GPT only
        if key in ("G1", "G2"):
            cost = 0.0
            for meta in (run_sum.get("metas") or {}).values():
                if meta.get("model_id") == (G1_ID if key == "G1" else G2_ID):
                    # approximate: use cumulative at end of that domain — better from usage in rows
                    pass
            # sum usage from rows
            tin = tout = 0
            for d in DOMAINS:
                for r in load_model_domain(key, d):
                    u = ((r.get("finding") or {}).get("usage")) or {}
                    tin += int(u.get("prompt_tokens") or 0)
                    tout += int(u.get("completion_tokens") or 0)
            pr = PRICING[G1_ID if key == "G1" else G2_ID]
            usd = tin / 1e6 * pr["in"] + tout / 1e6 * pr["out"]
            row["dev_cost_usd"] = round(usd, 4)
            row["tokens_in"] = tin
            row["tokens_out"] = tout
        else:
            row["dev_cost_usd"] = 0.0
            row["tokens_in"] = 0
            row["tokens_out"] = 0
        table_rows.append(row)

    payload = {
        "plan": plan,
        "run_cost": run_sum.get("cost"),
        "results": results,
        "local": local,
        "best": best,
        "scores": {k: {d: {kk: vv for kk, vv in (s or {}).items() if kk != "docs"} for d, s in v.items()} for k, v in scores.items()},
        "local_scores": {
            k: {d: {kk: vv for kk, vv in (s or {}).items() if kk != "docs"} for d, s in v.items()}
            for k, v in local_scores.items()
        },
        "mcnemar": mcn,
        "table": table_rows,
        "base_transform": BASE_TF,
    }
    (QGPT / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(QGPT / "tables" / "one_page.csv", table_rows)

    # markdown report
    lines = []
    lines.append("# GPT_EVAL_REPORT")
    lines.append("")
    lines.append("## 모델")
    lines.append(f"- **G1:** `{G1_ID}` — in ${PRICING[G1_ID]['in']}/1M, out ${PRICING[G1_ID]['out']}/1M")
    lines.append(f"- **G2:** `{G2_ID}` — in ${PRICING[G2_ID]['in']}/1M, out ${PRICING[G2_ID]['out']}/1M")
    lines.append(f"- 카드 해시: `{plan.get('card_hashes')}`")
    lines.append(f"- judge.txt 해시: `{plan.get('judge_hash')}`")
    lines.append(f"- AI Hub 원문: {plan.get('aihub_note', '확인')}")
    lines.append(f"- 설정: temperature=0, max_tokens=512, response_format=json_object")
    est = (plan.get("cost_estimate_usd") or {})
    lines.append(f"- 실행 전 추정 비용: ${est.get('total')} (상한 $15)")
    cost = run_sum.get("cost") or {}
    lines.append(f"- 실제 누적 비용: ${cost.get('usd', '—')} (in={cost.get('in_tok')} out={cost.get('out_tok')} cache={cost.get('cache_hits')})")
    lines.append("")
    lines.append("## 한 장 표 (모델×도메인)")
    lines.append("")
    lines.append("| 모델 | 근로 경고포착 | 근로 오탐 | 근로 과잉 | 근로 깨끗 | 근로 안전(점수) | 근로 독소非안전 | 근로 시간 | 임대 경고 | 임대 오탐 | 임대 깨끗 | 차용 경고 | 차용 오탐 | 차용 깨끗 | dev비용 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in table_rows:
        lines.append(
            "| {model} | {LAB_warn} | {LAB_fp} | {LAB_ow} | {LAB_clean} | {LAB_safe_clean} | {LAB_toxic_ns} | {LAB_time} | {LEASE_warn} | {LEASE_fp} | {LEASE_clean} | {LOAN_warn} | {LOAN_fp} | {LOAN_clean} | ${dev_cost_usd} |".format(
                **{k: r.get(k, "—") for k in (
                    "model", "LAB_warn", "LAB_fp", "LAB_ow", "LAB_clean", "LAB_safe_clean", "LAB_toxic_ns", "LAB_time",
                    "LEASE_warn", "LEASE_fp", "LEASE_clean", "LOAN_warn", "LOAN_fp", "LOAN_clean", "dev_cost_usd",
                )}
            )
        )
    lines.append("")
    lines.append("## 최적 조합 (GPT)")
    for key in ("G1", "G2"):
        for d, cfg in (best.get(key) or {}).items():
            if not cfg:
                continue
            lines.append(
                f"- **{key}/{d}**: AXOK={cfg.get('axok')} NUM2WAY={cfg.get('num2way')} ne={cfg.get('ne_risky_only')} "
                f"year={cfg.get('num_year_doc')} R={cfg.get('R')} K={cfg.get('K')} clean_v2={cfg.get('clean_v2')} "
                f"| warn={cfg.get('warn_capture_rate')} clean={cfg.get('clean_pass_rate')} miss={cfg.get('toxic_miss_n')}"
            )
    lines.append("")
    lines.append("## McNemar")
    for d, pairs in mcn.items():
        lines.append(f"### {d}")
        for name, m in pairs.items():
            w, f = m.get("warn_capture") or {}, m.get("fp") or {}
            lines.append(
                f"- {name}: warn b={w.get('b')} c={w.get('c')} p={w.get('p')} | fp b={f.get('b')} c={f.get('c')} p={f.get('p')}"
            )
    lines.append("")
    lines.append("## 점수 공식 평가")
    lines.append("누락·불일치=미반영(0). 깨끗 문서 중 안전(≥80) 비율 / 독소 문서 중 안전이 아닌 비율.")
    for key in ("AX", "EXAONE", "G1", "G2"):
        sc = local_scores.get(key) if key in ("AX", "EXAONE") else scores.get(key)
        if not sc:
            continue
        lines.append(f"### {key}")
        for d, s in (sc or {}).items():
            lines.append(
                f"- {d}: clean_safe={s.get('clean_safe_rate')} toxic_not_safe={s.get('toxic_not_safe_rate')} ({s.get('missing_mismatch')})"
            )
    lines.append("")
    lines.append("산출: `out/quant_gpt/summary.json`, `out/GPT_EVAL_REPORT.md`")
    report = OUT / "GPT_EVAL_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", report, flush=True)
    # 채팅용 짧은 표
    print("TABLE_JSON", json.dumps(table_rows, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
