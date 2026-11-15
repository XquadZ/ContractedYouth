# -*- coding: utf-8 -*-
"""FAIR_RERUN 표. 채점은 neutral_analyze와 같은 함수."""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.paths import OUT  # noqa: E402
from rag.score import score_from_findings  # noqa: E402
from replay import load_rows, mcnemar_compare, transform_row  # noqa: E402
from fix_round3_run import analyze_rows  # noqa: E402
from metrics import rate  # noqa: E402
from neutral_analyze import sweep_best, score_docs  # noqa: E402
from fair_common import DOMAINS, QFAIR, label_set, load_hash  # noqa: E402

MODELS = ("luna", "EXAONE", "AX")
VERSIONS = ("neutral", "tuned")
PAIRS = (("EXAONE", "luna"), ("EXAONE", "AX"), ("luna", "AX"))
BASE_TF = dict(axok=False, num2way=True, ne_risky_only=True, num_year_doc=True)


def path_for(model: str, version: str, domain: str) -> Path:
    return QFAIR / f"{model}_{version}_{domain}_rows.jsonl"


def _keys(rows: list[dict]) -> set[tuple]:
    return {(r.get("domain"), r.get("doc_id"), r.get("segment_id"), r.get("label") or "") for r in rows}


def _parse_fail(rows: list[dict]) -> int:
    return sum(1 for r in rows if not r.get("parse_ok"))


def _truncated(rows: list[dict]) -> int | None:
    seen = False
    n = 0
    for r in rows:
        fr = r.get("finish_reason")
        if fr is None:
            fr = (r.get("finding") or {}).get("finish_reason")
        if fr is None:
            continue
        seen = True
        if fr in ("length", "max_tokens"):
            n += 1
    return n if seen else None


def _fmt_best(cell: dict | None) -> str:
    if not cell:
        return "—"
    return (
        f"axok={cell.get('axok')} num2way={cell.get('num2way')} "
        f"ne_risky_only={cell.get('ne_risky_only')} num_year_doc={cell.get('num_year_doc')} "
        f"clean_v2={cell.get('clean_v2')} R={cell.get('R')} K={cell.get('K')}"
    )


def _p(text) -> float | None:
    try:
        return float(str(text).split()[0])
    except Exception:
        return None


def main() -> None:
    expected = label_set(load_hash("before"))
    loaded = {}
    excluded = []
    for model in MODELS:
        for version in VERSIONS:
            for domain in DOMAINS:
                path = path_for(model, version, domain)
                key = (model, version, domain)
                if not path.exists():
                    loaded[key] = None
                    excluded.append({"model": model, "version": version, "domain": domain, "reason": "파일 없음", "path": str(path)})
                    continue
                rows = load_rows(path)
                got = _keys(rows)
                want = {k for k in expected if k[0] == domain}
                if got != want:
                    missing = sorted(want - got)[:30]
                    extra = sorted(got - want)[:30]
                    excluded.append(
                        {
                            "model": model,
                            "version": version,
                            "domain": domain,
                            "reason": "조각 집합·라벨이 다름",
                            "n_got": len(got),
                            "n_want": len(want),
                            "missing": missing,
                            "extra": extra,
                            "path": str(path),
                        }
                    )
                    loaded[key] = None
                    continue
                loaded[key] = rows

    fixed = {}
    best = {}
    scores = {}
    scores79 = {}
    extra = {}
    for key, rows in loaded.items():
        if rows is None:
            continue
        fixed[key] = analyze_rows(rows)
        best[key] = sweep_best(rows)
        tr = [transform_row(r, **BASE_TF) for r in rows]
        scores[key] = score_docs(tr, check_cap79=False)
        scores79[key] = score_docs(tr, check_cap79=True)
        extra[key] = {
            "parse_fail": _parse_fail(rows),
            "n": len(rows),
            "truncated": _truncated(rows),
            "time_sec_per_doc": fixed[key].get("time_sec_per_doc"),
        }

    mcn = {}
    for version in VERSIONS:
        mcn[version] = {}
        for domain in DOMAINS:
            mcn[version][domain] = {}
            for a, b in PAIRS:
                ra = loaded.get((a, version, domain))
                rb = loaded.get((b, version, domain))
                if ra is None or rb is None:
                    continue
                ta = [transform_row(r, **BASE_TF) for r in ra]
                tb = [transform_row(r, **BASE_TF) for r in rb]
                mcn[version][domain][f"{a}_vs_{b}"] = {
                    "warn_capture": mcnemar_compare(ta, tb, kind="warn_capture"),
                    "fp": mcnemar_compare(ta, tb, kind="fp"),
                }

    def cell_line(model: str, version: str, domain: str, kind: str) -> dict:
        key = (model, version, domain)
        if kind == "fixed":
            block = fixed.get(key)
            if not block:
                return {}
            return {
                "warn": block["clause"]["warn_capture_rate"],
                "fp": block["clause"]["fp_rate"],
                "ow": block["clause"]["overwarn_rate"],
                "clean": block["doc"]["clean_pass_rate"],
                "miss": f"{block['doc']['toxic_miss_n']}/{block['doc'].get('clean_n', '—')}",
                "miss_n": block["doc"]["toxic_miss_n"],
                "toxic_n": block["doc"].get("clean_n"),
                "parse_fail": extra[key]["parse_fail"],
                "time": block.get("time_sec_per_doc"),
                "setting": "axok=False num2way=True ne_risky_only=True num_year_doc=True clean_v2=True R=R0 K=2",
            }
        cell = best.get(key)
        if not cell:
            return {}
        return {
            "warn": cell.get("warn_capture_rate"),
            "fp": cell.get("fp_rate"),
            "ow": cell.get("overwarn_rate"),
            "clean": cell.get("clean_pass_rate"),
            "miss": cell.get("toxic_miss_n"),
            "parse_fail": extra.get(key, {}).get("parse_fail"),
            "time": extra.get(key, {}).get("time_sec_per_doc"),
            "setting": _fmt_best(cell),
        }

    # toxic miss denominator: analyze_rows doc doesn't include toxic_n. Recompute label from rows.
    for key, rows in loaded.items():
        if not rows or key not in fixed:
            continue
        docs = {}
        for r in rows:
            docs.setdefault(r["doc_id"], set()).add(r.get("label"))
        toxic_docs = sum(1 for labs in docs.values() if "toxic" in labs)
        fixed[key]["doc"]["toxic_doc_n"] = toxic_docs

    tables = {"neutral": [], "tuned": []}
    for version in VERSIONS:
        for model in MODELS:
            for kind in ("fixed", "best"):
                row = {"model": model, "kind": kind}
                for domain in DOMAINS:
                    info = cell_line(model, version, domain, kind)
                    if kind == "fixed" and (model, version, domain) in fixed:
                        miss_n = fixed[(model, version, domain)]["doc"]["toxic_miss_n"]
                        tox_n = fixed[(model, version, domain)]["doc"].get("toxic_doc_n")
                        info["miss"] = f"{miss_n}/{tox_n}"
                    row[domain] = info
                tables[version].append(row)

    deltas = []
    for model in MODELS:
        item = {"model": model}
        gains = []
        for domain in DOMAINS:
            a = cell_line(model, "neutral", domain, "fixed")
            b = cell_line(model, "tuned", domain, "fixed")
            for metric in ("warn", "fp", "clean"):
                pa, pb = _p(a.get(metric)), _p(b.get(metric))
                item[f"{domain}_{metric}"] = None if pa is None or pb is None else round(pb - pa, 3)
            if item.get(f"{domain}_clean") is not None:
                gains.append(item[f"{domain}_clean"])
            if item.get(f"{domain}_warn") is not None:
                gains.append(item[f"{domain}_warn"])
        item["mean_warn_clean_delta"] = round(sum(gains) / len(gains), 3) if gains else None
        deltas.append(item)
    by_model = {d["model"]: d.get("mean_warn_clean_delta") for d in deltas}
    ex = by_model.get("EXAONE")
    others = [by_model.get(m) for m in ("luna", "AX") if by_model.get(m) is not None]
    interpret = ""
    if ex is not None and others and ex > max(others) + 0.05 and ex > 0.05:
        interpret = "카드가 EXAONE에 맞춰졌다"

    pilot = {}
    pp = QFAIR / "gpt_pilot.json"
    if pp.exists():
        pilot = json.loads(pp.read_text(encoding="utf-8"))
    style = {}
    sp = QFAIR / "gpt_style.json"
    if sp.exists():
        style = json.loads(sp.read_text(encoding="utf-8"))
    skipped = {}
    sk = QFAIR / "gpt_skipped.json"
    if sk.exists():
        skipped = json.loads(sk.read_text(encoding="utf-8"))

    payload = {
        "tables": tables,
        "deltas": deltas,
        "interpret": interpret,
        "mcnemar": mcn,
        "scores": {f"{a}|{b}|{c}": scores[(a, b, c)] for (a, b, c) in scores},
        "scores79": {f"{a}|{b}|{c}": scores79[(a, b, c)] for (a, b, c) in scores79},
        "extra": {f"{a}|{b}|{c}": extra[(a, b, c)] for (a, b, c) in extra},
        "excluded": excluded,
        "pilot": {k: pilot.get(k) for k in ("n_pilot", "avg_in", "avg_out", "avg_reasoning", "spent_usd", "est_total_if_batch_usd", "over_cap", "avg_latency_ms") if pilot},
        "style": style.get("extra"),
        "skipped": skipped,
    }
    (QFAIR / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", QFAIR / "summary.json", "interpret", interpret or "(none)", flush=True)
    print("EXCLUDED", len(excluded), flush=True)


if __name__ == "__main__":
    main()
