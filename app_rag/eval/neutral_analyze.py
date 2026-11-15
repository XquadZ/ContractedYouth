# -*- coding: utf-8 -*-
"""NEUTRAL_CARDS 표·McNemar·점수·보고서."""
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
from replay import load_rows, mcnemar_compare, pick_best, transform_row, clause_metrics, doc_metrics, K_GRID, R_OPTS  # noqa: E402
from fix_round3_run import analyze_rows  # noqa: E402
from metrics import rate  # noqa: E402

QN = OUT / "quant_neutral"
DOMAINS = ("LAB", "LEASE", "LOAN")
BASE_TF = dict(axok=False, num2way=True, ne_risky_only=True, num_year_doc=True)
G1, G2 = "gpt-4o-mini", "gpt-4.1"


def path_for(model: str, domain: str) -> Path:
    if model in ("AX", "EXAONE"):
        return QN / f"{model}_{domain}_rows.jsonl"
    tag = model.replace("/", "_")
    return QN / f"{tag}_{domain}_rows.jsonl"


def sweep_best(rows: list[dict]) -> dict | None:
    cells = []
    for axok in (False, True):
        for num2way in (False, True):
            for ne in (False, True):
                for yd in (False, True):
                    if not num2way and yd:
                        continue
                    tr = [transform_row(r, axok=axok, num2way=num2way, ne_risky_only=ne, num_year_doc=yd) for r in rows]
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


def score_docs(rows: list[dict], *, check_cap79: bool = False) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["doc_id"]].append(r)
    clean_safe = clean_n = toxic_ns = toxic_n = 0
    for did, rs in by.items():
        labs = {x.get("label") for x in rs}
        is_clean = "toxic" not in labs and "check" not in labs
        is_toxic = "toxic" in labs
        sc = score_from_findings(rs, missing_reflected=False, mismatch_reflected=False, check_cap79=check_cap79)
        if is_clean:
            clean_n += 1
            if sc["grade"] == "안전":
                clean_safe += 1
        if is_toxic:
            toxic_n += 1
            if sc["grade"] != "안전":
                toxic_ns += 1
    return {
        "clean_safe_rate": rate(clean_safe, clean_n),
        "toxic_not_safe_rate": rate(toxic_ns, toxic_n),
        "clean_n": clean_n,
        "toxic_n": toxic_n,
        "check_cap79": check_cap79,
    }


def load_tuned_table() -> dict:
    """GPT_EVAL_REPORT summary table for delta."""
    p = OUT / "quant_gpt" / "summary.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def cell(block, path, default="—"):
    if not block:
        return default
    cur = block
    for p in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def main() -> None:
    models = {
        "AX": "AX",
        "EXAONE": "EXAONE",
        "G1": G1,
        "G2": G2,
    }
    results = {}
    best = {}
    scores = {}
    scores79 = {}
    for key, mid in models.items():
        results[key] = {}
        best[key] = {}
        scores[key] = {}
        scores79[key] = {}
        for d in DOMAINS:
            p = path_for(mid, d)
            if not p.exists():
                results[key][d] = None
                continue
            rows = load_rows(p)
            results[key][d] = analyze_rows(rows)
            best[key][d] = sweep_best(rows)
            tr = [transform_row(r, **BASE_TF) for r in rows]
            scores[key][d] = score_docs(tr, check_cap79=False)
            scores79[key][d] = score_docs(tr, check_cap79=True)

    mcn = {}
    for d in DOMAINS:
        mcn[d] = {}
        for a, b in (("EXAONE", "G1"), ("EXAONE", "G2"), ("G1", "G2")):
            pa, pb = path_for(models[a], d), path_for(models[b], d)
            if not (pa.exists() and pb.exists()):
                continue
            ta = [transform_row(r, **BASE_TF) for r in load_rows(pa)]
            tb = [transform_row(r, **BASE_TF) for r in load_rows(pb)]
            mcn[d][f"{a}_vs_{b}"] = {
                "warn_capture": mcnemar_compare(ta, tb, kind="warn_capture"),
                "fp": mcnemar_compare(ta, tb, kind="fp"),
            }

    # table 1
    table1 = []
    for key in ("AX", "EXAONE", "G1", "G2"):
        row = {"model": key}
        for d in DOMAINS:
            b = results[key].get(d)
            row[f"{d}_warn"] = cell(b, "clause.warn_capture_rate")
            row[f"{d}_fp"] = cell(b, "clause.fp_rate")
            row[f"{d}_ow"] = cell(b, "clause.overwarn_rate")
            row[f"{d}_clean"] = cell(b, "doc.clean_pass_rate")
            row[f"{d}_miss"] = cell(b, "doc.toxic_miss_n")
            row[f"{d}_time"] = f"{cell(b, 'time_sec_per_doc')}s" if b else "—"
        table1.append(row)

    # table 2: tuned from quant_gpt summary
    tuned = load_tuned_table()
    tuned_map = {r["model"]: r for r in (tuned.get("table") or [])}
    table2 = []
    for key in ("AX", "EXAONE", "G1", "G2"):
        trow = tuned_map.get(key) or {}
        nrow = next(r for r in table1 if r["model"] == key)
        delta = {"model": key}
        for d in DOMAINS:
            for metric, tk in (("warn", f"{d}_warn"), ("fp", f"{d}_fp"), ("clean", f"{d}_clean")):
                nval = nrow.get(tk, "—")
                tval = trow.get(tk, "—")
                delta[f"{d}_{metric}_neutral"] = nval
                delta[f"{d}_{metric}_tuned"] = tval
                # extract first float for delta if possible
                def _p(s):
                    try:
                        return float(str(s).split()[0])
                    except Exception:
                        return None

                pn, pt = _p(nval), _p(tval)
                delta[f"{d}_{metric}_delta"] = round(pt - pn, 3) if pn is not None and pt is not None else "—"
        table2.append(delta)

    # interpret EXAONE vs GPT improvement on clean/warn
    ex_imp = []
    g_imp = []
    for d in DOMAINS:
        for metric in ("warn", "fp", "clean"):
            for row in table2:
                if row["model"] == "EXAONE":
                    v = row.get(f"{d}_{metric}_delta")
                    if isinstance(v, (int, float)):
                        # for fp, improvement is negative delta (tuned lower)
                        ex_imp.append((d, metric, v))
                if row["model"] in ("G1", "G2"):
                    v = row.get(f"{d}_{metric}_delta")
                    if isinstance(v, (int, float)):
                        g_imp.append((d, metric, row["model"], v))
    # clean: higher better; warn: higher better; fp: lower better → use clean primarily
    ex_clean = [v for d, m, v in ex_imp if m == "clean"]
    g_clean = [v for d, m, model, v in g_imp if m == "clean"]
    interpret = ""
    if ex_clean and g_clean:
        if sum(ex_clean) / len(ex_clean) > sum(g_clean) / len(g_clean) + 0.05:
            interpret = "EXAONE의 튜닝 개선폭(특히 깨끗 통과)이 GPT보다 커서, 카드가 EXAONE에 맞춰졌을 가능성이 있다."
        else:
            interpret = "중립→튜닝 개선폭이 EXAONE에만 두드러지지는 않는다(또는 GPT도 비슷한 방향)."

    plan = {}
    if (QN / "plan.json").exists():
        plan = json.loads((QN / "plan.json").read_text(encoding="utf-8"))
    run_sum = {}
    if (QN / "run_summary.json").exists():
        run_sum = json.loads((QN / "run_summary.json").read_text(encoding="utf-8"))

    payload = {
        "plan": plan,
        "cost": run_sum.get("cost"),
        "results": results,
        "best": best,
        "scores": scores,
        "scores_check_cap79": scores79,
        "mcnemar": mcn,
        "table1": table1,
        "table2": table2,
        "interpret": interpret,
    }
    (QN / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# NEUTRAL_CARDS_REPORT", ""]
    lines.append("## 0. 중립 버전")
    prov = (plan.get("provenance") or {})
    lines.append(f"- LAB: `{prov.get('lab_neutral_source')}` — {prov.get('lab_v3_reason')}")
    lines.append(f"- v3 바이트 일치: {prov.get('lab_v3_ok')}")
    lines.append("")
    lines.append("### 카드 수·해시")
    lines.append("| 도메인 | 버전 | n | sha256_16 |")
    lines.append("|---|---|---:|---|")
    for r in prov.get("card_table") or []:
        lines.append(f"| {r['domain']} | {r['version']} | {r['n_cards']} | `{r['sha256_16']}` |")
    lines.append("")
    lines.append("### criteria_extra_rules (tuned 전체)")
    for h in prov.get("extra_rules_history") or []:
        lines.append(f"- {h['line']} — {h['when']}: {h['why']}")
    lines.append("")
    lines.append("### 비용")
    est = (plan.get("cost_estimate_usd") or {}).get("total")
    lines.append(f"- 추정 ${est} / 상한 $8 / 실제 ${(run_sum.get('cost') or {}).get('usd', '—')}")
    lines.append("")
    lines.append("## 표 1. 중립 버전 (같은 카드)")
    lines.append("")
    lines.append("| 모델 | 근로 경고 | 근로 오탐 | 근로 과잉 | 근로 깨끗 | 근로 놓침 | 근로 시간 | 임대 경고 | 임대 오탐 | 임대 깨끗 | 차용 경고 | 차용 오탐 | 차용 깨끗 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in table1:
        lines.append(
            "| {model} | {LAB_warn} | {LAB_fp} | {LAB_ow} | {LAB_clean} | {LAB_miss} | {LAB_time} | {LEASE_warn} | {LEASE_fp} | {LEASE_clean} | {LOAN_warn} | {LOAN_fp} | {LOAN_clean} |".format(
                **{k: r.get(k, "—") for k in (
                    "model", "LAB_warn", "LAB_fp", "LAB_ow", "LAB_clean", "LAB_miss", "LAB_time",
                    "LEASE_warn", "LEASE_fp", "LEASE_clean", "LOAN_warn", "LOAN_fp", "LOAN_clean",
                )}
            )
        )
    lines.append("")
    lines.append("## 표 2. 튜닝 효과 (중립→튜닝 Δ)")
    lines.append("")
    lines.append("| 모델 | 근로 warnΔ | 근로 fpΔ | 근로 cleanΔ | 임대 warnΔ | 임대 fpΔ | 임대 cleanΔ | 차용 warnΔ | 차용 fpΔ | 차용 cleanΔ |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in table2:
        lines.append(
            "| {model} | {LAB_warn_delta} | {LAB_fp_delta} | {LAB_clean_delta} | {LEASE_warn_delta} | {LEASE_fp_delta} | {LEASE_clean_delta} | {LOAN_warn_delta} | {LOAN_fp_delta} | {LOAN_clean_delta} |".format(
                **{k: r.get(k, "—") for k in (
                    "model", "LAB_warn_delta", "LAB_fp_delta", "LAB_clean_delta",
                    "LEASE_warn_delta", "LEASE_fp_delta", "LEASE_clean_delta",
                    "LOAN_warn_delta", "LOAN_fp_delta", "LOAN_clean_delta",
                )}
            )
        )
    lines.append("")
    lines.append(f"**해석:** {interpret}")
    lines.append("")
    lines.append("## McNemar (중립)")
    for d, pairs in mcn.items():
        lines.append(f"### {d}")
        for name, m in pairs.items():
            w, f = m.get("warn_capture") or {}, m.get("fp") or {}
            lines.append(
                f"- {name}: warn b={w.get('b')} c={w.get('c')} p={w.get('p')} | fp b={f.get('b')} c={f.get('c')} p={f.get('p')}"
            )
    lines.append("")
    lines.append("## 점수 공식 (현행 / 확인필요≥3 → max79)")
    for key in ("AX", "EXAONE", "G1", "G2"):
        lines.append(f"### {key}")
        for d in DOMAINS:
            a = scores.get(key, {}).get(d) or {}
            b = scores79.get(key, {}).get(d) or {}
            if not a:
                continue
            lines.append(
                f"- {d}: 현행 clean_safe={a.get('clean_safe_rate')} toxic_ns={a.get('toxic_not_safe_rate')} "
                f"| 수정안 clean_safe={b.get('clean_safe_rate')} toxic_ns={b.get('toxic_not_safe_rate')}"
            )
    lines.append("")
    lines.append("수정안 채택 여부는 사용자가 정한다.")
    lines.append("")
    lines.append("## 미확인")
    missing = []
    for key, mid in models.items():
        for d in DOMAINS:
            if not path_for(mid, d).exists():
                missing.append(f"{key}/{d} rows 없음")
    if not missing:
        lines.append("- (실행 산출 기준 없음)")
    for m in missing:
        lines.append(f"- {m}")
    report = OUT / "NEUTRAL_CARDS_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", report, flush=True)
    print("TABLE1", json.dumps(table1, ensure_ascii=False), flush=True)
    print("INTERPRET", interpret, flush=True)


if __name__ == "__main__":
    main()
