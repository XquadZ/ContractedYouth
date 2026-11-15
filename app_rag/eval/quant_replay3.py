# -*- coding: utf-8 -*-
"""QUANT_FULL replay 변형 3개 추가 재계산 (LLM 없음).
① ne_risky_only ② clean_v2 ③ num_year_doc
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.paths import OUT  # noqa: E402
from quant_run import out_path  # noqa: E402
from metrics import rate as rate_fmt  # noqa: E402
from replay import (  # noqa: E402
    K_GRID,
    R_OPTS,
    clause_metrics,
    doc_metrics,
    load_rows,
    pick_best,
    transform_row,
    write_csv,
)

QUANT = OUT / "quant"
TABLES = QUANT / "tables"
MODELS = ("AX", "EXAONE")
DOMAINS = ("LAB", "LEASE", "LOAN")

# 변형 기본(끔) + 각각 켠 값. 최적 탐색은 전부 포함.
BASE = {"ne_risky_only": False, "clean_v2": False, "num_year_doc": False}


def cfg_key(c: dict) -> tuple:
    return (
        c.get("axok"),
        c.get("num2way"),
        c.get("ne_risky_only"),
        c.get("clean_v2"),
        c.get("num_year_doc"),
        c.get("R"),
        c.get("K"),
    )


def transform_cache(rows: list[dict], *, axok, num2way, ne_risky_only, num_year_doc):
    return [
        transform_row(
            r,
            axok=axok,
            num2way=num2way,
            ne_risky_only=ne_risky_only,
            num_year_doc=num_year_doc,
        )
        for r in rows
    ]


def sweep_domain(rows: list[dict]) -> list[dict]:
    cells = []
    # cache transforms
    tcache = {}
    for axok in (False, True):
        for num2way in (False, True):
            for ne in (False, True):
                for yd in (False, True):
                    if not num2way and yd:
                        continue  # year flag only meaningful with num2way
                    tcache[(axok, num2way, ne, yd)] = transform_cache(
                        rows, axok=axok, num2way=num2way, ne_risky_only=ne, num_year_doc=yd
                    )

    for (axok, num2way, ne, yd), transformed in tcache.items():
        cm = clause_metrics(transformed)
        flips = [t for t in transformed if t.get("num2way_flipped")]
        toxic_flips = [
            {
                "doc_id": t["doc_id"],
                "segment_id": t["segment_id"],
                "domain": t.get("domain"),
                "prev": t.get("ax_verdict"),
                "rule_year_source": [
                    d.get("year_source")
                    for d in ((t.get("num2way_info") or {}).get("details") or [])
                    if d.get("rule") == "min_wage"
                ],
                "text40": (t.get("text") or "").replace("\n", " ")[:40],
                "notes": [n for n in (t.get("notes") or []) if "num2way" in str(n)],
            }
            for t in flips
            if t.get("label") == "toxic"
        ]
        for clean_v2 in (False, True):
            for method in R_OPTS:
                for k in K_GRID:
                    dm = doc_metrics(transformed, method, k, clean_v2=clean_v2)
                    cells.append(
                        {
                            "axok": axok,
                            "num2way": num2way,
                            "ne_risky_only": ne,
                            "clean_v2": clean_v2,
                            "num_year_doc": yd if num2way else False,
                            "R": method,
                            "K": k,
                            "detect_rate": cm["detect_rate"],
                            "warn_capture_rate": cm["warn_capture_rate"],
                            "fp_rate": cm["fp_rate"],
                            "overwarn_rate": cm["overwarn_rate"],
                            "check_rate": cm["check_rate"],
                            "detect_p": cm["detect_p"],
                            "warn_capture_p": cm["warn_capture_p"],
                            "fp_p": cm["fp_p"],
                            "overwarn_p": cm["overwarn_p"],
                            "toxic_n": cm["toxic_n"],
                            "safe_n": cm["safe_n"],
                            "clean_pass_rate": dm["clean_pass_rate"],
                            "clean_pass_p": dm["clean_pass_p"],
                            "clean_pass": dm["clean_pass"],
                            "clean_n": dm["clean_n"],
                            "check_doc_rate": dm["check_doc_rate"],
                            "check_doc_p": dm["check_doc_p"],
                            "check_doc_ok": dm["check_doc_ok"],
                            "check_doc_n": dm["check_doc_n"],
                            "toxic_warn_rate": dm["toxic_warn_rate"],
                            "toxic_miss_n": dm["toxic_miss_n"],
                            "toxic_misses": dm["toxic_misses"],
                            "num2way_toxic_flips": toxic_flips if (num2way and method == "R0" and k == 0 and not clean_v2) else [],
                            "n_num2way_flips": len(flips),
                            "n_num2way_toxic_flips": len(toxic_flips),
                        }
                    )
    return cells


def pool_model(cells_by_domain: dict[str, list[dict]]) -> list[dict]:
    pooled: dict[tuple, dict] = {}
    for domain, cells in cells_by_domain.items():
        for c in cells:
            ck = cfg_key(c)
            s = pooled.setdefault(
                ck,
                {
                    "axok": c["axok"],
                    "num2way": c["num2way"],
                    "ne_risky_only": c["ne_risky_only"],
                    "clean_v2": c["clean_v2"],
                    "num_year_doc": c["num_year_doc"],
                    "R": c["R"],
                    "K": c["K"],
                    "warn_num": 0,
                    "warn_den": 0,
                    "fp_num": 0,
                    "fp_den": 0,
                    "ow_num": 0,
                    "ow_den": 0,
                    "clean_num": 0,
                    "clean_den": 0,
                    "check_ok": 0,
                    "check_den": 0,
                    "miss_n": 0,
                },
            )
            wd = c.get("toxic_n") or 0
            wn = int(round((c.get("warn_capture_p") or 0) * wd))
            s["warn_num"] += wn
            s["warn_den"] += wd
            fd = c.get("safe_n") or 0
            s["fp_num"] += int(round((c.get("fp_p") or 0) * fd))
            s["fp_den"] += fd
            s["ow_num"] += int(round((c.get("overwarn_p") or 0) * fd))
            s["ow_den"] += fd
            s["clean_num"] += c.get("clean_pass") or 0
            s["clean_den"] += c.get("clean_n") or 0
            s["check_ok"] += c.get("check_doc_ok") or 0
            s["check_den"] += c.get("check_doc_n") or 0
            s["miss_n"] += c.get("toxic_miss_n") or 0
    out = []
    for s in pooled.values():
        out.append(
            {
                **{k: s[k] for k in ("axok", "num2way", "ne_risky_only", "clean_v2", "num_year_doc", "R", "K")},
                "toxic_miss_n": s["miss_n"],
                "warn_capture_p": (s["warn_num"] / s["warn_den"]) if s["warn_den"] else None,
                "clean_pass_p": (s["clean_num"] / s["clean_den"]) if s["clean_den"] else None,
                "fp_p": (s["fp_num"] / s["fp_den"]) if s["fp_den"] else None,
                "overwarn_p": (s["ow_num"] / s["ow_den"]) if s["ow_den"] else None,
                "check_doc_p": (s["check_ok"] / s["check_den"]) if s["check_den"] else None,
                "warn_capture_rate": rate_fmt(s["warn_num"], s["warn_den"]),
                "clean_pass_rate": rate_fmt(s["clean_num"], s["clean_den"]),
                "fp_rate": rate_fmt(s["fp_num"], s["fp_den"]),
                "overwarn_rate": rate_fmt(s["ow_num"], s["ow_den"]),
                "check_doc_rate": rate_fmt(s["check_ok"], s["check_den"]),
            }
        )
    return out


def metrics_at(rows: list[dict], cfg: dict) -> dict:
    tr = transform_cache(
        rows,
        axok=cfg["axok"],
        num2way=cfg["num2way"],
        ne_risky_only=cfg["ne_risky_only"],
        num_year_doc=cfg.get("num_year_doc", False) if cfg.get("num2way") else False,
    )
    cm = clause_metrics(tr)
    dm = doc_metrics(tr, cfg["R"], int(cfg["K"]), clean_v2=cfg.get("clean_v2", False))
    flips = [t for t in tr if t.get("num2way_flipped") and t.get("label") == "toxic"]
    return {"clause": cm, "doc": dm, "toxic_flips": flips, "rows": tr}


def ablation_pair(rows_by_domain: dict, model: str, flag: str) -> dict:
    """flag 하나만 켠/끈. 나머지 False, axok=False,num2way=True(연도 비교 시), R0 K=3."""
    base = {
        "axok": False,
        "num2way": True if flag == "num_year_doc" else False,
        "ne_risky_only": False,
        "clean_v2": False,
        "num_year_doc": False,
        "R": "R0",
        "K": 3,
    }
    off = dict(base)
    on = dict(base)
    on[flag] = True
    if flag == "num_year_doc":
        off["num2way"] = True
        on["num2way"] = True

    def agg(cfg):
        warn_n = warn_d = fp_n = fp_d = cl_n = cl_d = miss = chk_ok = chk_d = 0
        tox_flips = []
        per = {}
        for d, rows in rows_by_domain.items():
            m = metrics_at(rows, cfg)
            cm, dm = m["clause"], m["doc"]
            warn_n += cm["warn_capture"]
            warn_d += cm["toxic_n"]
            fp_n += cm["fp"]
            fp_d += cm["safe_n"]
            cl_n += dm["clean_pass"]
            cl_d += dm["clean_n"]
            miss += dm["toxic_miss_n"]
            chk_ok += dm["check_doc_ok"]
            chk_d += dm["check_doc_n"]
            for t in m["toxic_flips"]:
                tox_flips.append(
                    {
                        "model": model,
                        "domain": d,
                        "doc_id": t["doc_id"],
                        "segment_id": t["segment_id"],
                        "ax_verdict": t.get("ax_verdict"),
                        "text40": (t.get("text") or "").replace("\n", " ")[:40],
                        "year_from_doc": "num2way_year_from_doc" in (t.get("notes") or []),
                    }
                )
            per[d] = {
                "warn": cm["warn_capture_rate"],
                "fp": cm["fp_rate"],
                "clean": dm["clean_pass_rate"],
                "check_doc": dm["check_doc_rate"],
                "miss": dm["toxic_miss_n"],
            }
        return {
            "cfg": cfg,
            "warn": rate_fmt(warn_n, warn_d),
            "fp": rate_fmt(fp_n, fp_d),
            "clean": rate_fmt(cl_n, cl_d),
            "check_doc": rate_fmt(chk_ok, chk_d),
            "miss": miss,
            "per_domain": per,
            "toxic_flips": tox_flips,
        }

    return {"off": agg(off), "on": agg(on)}


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    all_cells = {}
    rows_store = {}
    grid_csv = []
    toxic_flip_csv = []

    for model in MODELS:
        by_dom_cells = {}
        by_dom_rows = {}
        for domain in DOMAINS:
            p = out_path(model, domain)
            rows = load_rows(p)
            by_dom_rows[domain] = rows
            print(f"SWEEP {model} {domain} n={len(rows)}", flush=True)
            cells = sweep_domain(rows)
            by_dom_cells[domain] = cells
            all_cells[f"{model}_{domain}"] = cells
            for c in cells:
                grid_csv.append({"model": model, "domain": domain, **{k: v for k, v in c.items() if k != "num2way_toxic_flips" and k != "toxic_misses"}})
                for t in c.get("num2way_toxic_flips") or []:
                    toxic_flip_csv.append({"model": model, **t, "axok": c["axok"], "ne": c["ne_risky_only"], "year_doc": c["num_year_doc"]})
        rows_store[model] = by_dom_rows

        best_dom = {f"{model}_{d}": pick_best(by_dom_cells[d]) for d in DOMAINS}
        best_all = pick_best(pool_model(by_dom_cells))
        all_cells[f"{model}_best_domain"] = best_dom
        all_cells[f"{model}_best"] = best_all

    # ablations
    ablations = {}
    for model in MODELS:
        ablations[model] = {}
        for flag in ("ne_risky_only", "clean_v2", "num_year_doc"):
            print(f"ABLATION {model} {flag}", flush=True)
            ablations[model][flag] = ablation_pair(rows_store[model], model, flag)

    # one-page at model best
    summary = []
    for tag, model in (("빠른 검토(A.X 최적)", "AX"), ("정밀 검사(EXAONE 최적)", "EXAONE")):
        cfg = all_cells[f"{model}_best"]
        row = {
            "mode": tag,
            "axok": cfg.get("axok"),
            "num2way": cfg.get("num2way"),
            "ne_risky_only": cfg.get("ne_risky_only"),
            "clean_v2": cfg.get("clean_v2"),
            "num_year_doc": cfg.get("num_year_doc"),
            "R": cfg.get("R"),
            "K": cfg.get("K"),
        }
        for domain in DOMAINS:
            m = metrics_at(rows_store[model][domain], cfg)
            cm, dm = m["clause"], m["doc"]
            row[f"{domain}_warn"] = cm["warn_capture_rate"]
            row[f"{domain}_fp"] = cm["fp_rate"]
            row[f"{domain}_clean"] = dm["clean_pass_rate"]
            row[f"{domain}_check_doc"] = dm["check_doc_rate"]
            row[f"{domain}_miss"] = dm["toxic_miss_n"]
        summary.append(row)

    # toxic flips at best configs
    best_toxic_flips = []
    for model in MODELS:
        cfg = all_cells[f"{model}_best"]
        for domain in DOMAINS:
            m = metrics_at(rows_store[model][domain], cfg)
            for t in m["toxic_flips"]:
                best_toxic_flips.append(
                    {
                        "model": model,
                        "domain": domain,
                        "doc_id": t["doc_id"],
                        "segment_id": t["segment_id"],
                        "ax_verdict": t.get("ax_verdict"),
                        "text40": (t.get("text") or "").replace("\n", " ")[:40],
                        "year_from_doc": "num2way_year_from_doc" in (t.get("notes") or []),
                    }
                )

    write_csv(TABLES / "replay3_grid.csv", grid_csv)
    write_csv(TABLES / "replay3_toxic_flips.csv", toxic_flip_csv)
    write_csv(TABLES / "replay3_best_toxic_flips.csv", best_toxic_flips)
    write_csv(TABLES / "replay3_one_page.csv", summary)

    payload = {
        "best": {m: all_cells[f"{m}_best"] for m in MODELS},
        "best_by_domain": {
            f"{m}_{d}": all_cells[f"{m}_best_domain"][f"{m}_{d}"] for m in MODELS for d in DOMAINS
        },
        "ablations": {
            m: {
                f: {
                    "off": {k: v for k, v in ablations[m][f]["off"].items() if k != "toxic_flips"},
                    "on": {k: v for k, v in ablations[m][f]["on"].items() if k != "toxic_flips"},
                    "toxic_flips_on": ablations[m][f]["on"]["toxic_flips"],
                    "toxic_flips_off": ablations[m][f]["off"]["toxic_flips"],
                }
                for f in ablations[m]
            }
            for m in MODELS
        },
        "summary": summary,
        "best_toxic_flips": best_toxic_flips,
    }
    # strip huge
    for m in MODELS:
        for d in DOMAINS:
            b = payload["best_by_domain"][f"{m}_{d}"]
            if b:
                b.pop("num2way_toxic_flips", None)
                b.pop("toxic_misses", None)

    (QUANT / "summary_replay3.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown report
    lines = []
    lines.append("# QUANT_FULL replay 변형 3 재계산")
    lines.append("")
    lines.append("모델 재실행 없음. 저장 rows + 오프라인 replay.")
    lines.append("")
    lines.append("변형:")
    lines.append("1. **ne_risky_only**: no_evidence를 위반·위험일 때만 적용(문제 없음 유지)")
    lines.append("2. **clean_v2**: 깨끗=toxic0 & check0 / check만 있는 문서는「확인할 부분 있음」정답으로 따로 집계")
    lines.append("3. **num_year_doc**: NUM2WAY 최저임금 연도에 문서 사실표 start_date 허용")
    lines.append("")
    lines.append("## 한 장 요약 (모델 합산 최적)")
    lines.append("")
    lines.append("| 모드 | 설정 | 근로 warn/fp/깨끗/check문서 | 임대 | 차용 |")
    lines.append("|---|---|---|---|---|")
    for r in summary:
        sett = f"AXOK={r['axok']} NUM2={r['num2way']} NE={r['ne_risky_only']} C2={r['clean_v2']} YD={r['num_year_doc']} {r['R']}K={r['K']}"
        lab = f"{r['LAB_warn']} / {r['LAB_fp']} / {r['LAB_clean']} / {r['LAB_check_doc']}"
        lease = f"{r['LEASE_warn']} / {r['LEASE_fp']} / {r['LEASE_clean']} / {r['LEASE_check_doc']}"
        loan = f"{r['LOAN_warn']} / {r['LOAN_fp']} / {r['LOAN_clean']} / {r['LOAN_check_doc']}"
        lines.append(f"| {r['mode']} | {sett} | {lab} | {lease} | {loan} |")
    lines.append("")
    lines.append("## 모델별 최적 조합")
    lines.append("")
    for m in MODELS:
        b = payload["best"][m]
        lines.append(
            f"- **{m}**: AXOK={b['axok']} NUM2WAY={b['num2way']} NE={b['ne_risky_only']} "
            f"clean_v2={b['clean_v2']} year_doc={b['num_year_doc']} R={b['R']} K={b['K']} | "
            f"warn={b['warn_capture_rate']} clean={b['clean_pass_rate']} fp={b['fp_rate']} "
            f"check문서={b.get('check_doc_rate')} miss={b['toxic_miss_n']}"
        )
    lines.append("")
    lines.append("### 도메인별 최적")
    for k, b in payload["best_by_domain"].items():
        if not b:
            continue
        lines.append(
            f"- `{k}`: AXOK={b['axok']} NUM2={b['num2way']} NE={b['ne_risky_only']} C2={b['clean_v2']} "
            f"YD={b['num_year_doc']} {b['R']}K={b['K']} warn={b['warn_capture_rate']} "
            f"clean={b['clean_pass_rate']} check문서={b.get('check_doc_rate')} miss={b['toxic_miss_n']}"
        )
    lines.append("")
    lines.append("## 변형별 켬/끔 (ablation)")
    lines.append("")
    for m in MODELS:
        lines.append(f"### {m}")
        for flag in ("ne_risky_only", "clean_v2", "num_year_doc"):
            ab = ablations[m][flag]
            lines.append(f"**{flag}**")
            lines.append("")
            lines.append("| | warn | fp | 깨끗 | check문서 | 독소놓침 |")
            lines.append("|---|---|---|---|---|---|")
            for lab in ("off", "on"):
                x = ab[lab]
                lines.append(f"| {lab} | {x['warn']} | {x['fp']} | {x['clean']} | {x['check_doc']} | {x['miss']} |")
            lines.append("")
            # domain detail
            lines.append("| 도메인 | off warn/clean/check | on warn/clean/check |")
            lines.append("|---|---|---|")
            for d in DOMAINS:
                o, n = ab["off"]["per_domain"][d], ab["on"]["per_domain"][d]
                lines.append(
                    f"| {d} | {o['warn']} / {o['clean']} / {o['check_doc']} | {n['warn']} / {n['clean']} / {n['check_doc']} |"
                )
            lines.append("")
    lines.append("## 정답 toxic이 NUM2WAY로 바뀐 건 (모델 최적 조합)")
    lines.append("")
    if not best_toxic_flips:
        lines.append("- (없음)")
    for t in best_toxic_flips:
        lines.append(
            f"- **{t['model']} {t['domain']}** {t['doc_id']} {t['segment_id']} "
            f"ax={t['ax_verdict']} year_doc={t['year_from_doc']} | {t['text40']}"
        )
    lines.append("")
    lines.append("Ablation에서 NUM2WAY toxic 플립 목록은 `out/quant/summary_replay3.json` / `tables/replay3_toxic_flips.csv`.")
    path = OUT / "QUANT_FULL_REPLAY3_REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", path, flush=True)
    print("BEST", json.dumps(payload["best"], ensure_ascii=False), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
