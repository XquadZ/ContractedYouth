# -*- coding: utf-8 -*-
"""FINAL_TEST 통계. test에서 sweep_best를 쓰지 않는다. freeze 설정만 사용."""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.paths import GOLD, OUT  # noqa: E402
from rag.score import score_from_findings  # noqa: E402
from replay import (  # noqa: E402
    clause_metrics,
    doc_metrics,
    load_rows,
    mcnemar_compare,
    transform_row,
)
from metrics import RISKY, WARN, rate, rate_plain, wilson_ci  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from final_test_common import DOMAINS, MODELS, QDEV, QFAIR, QTEST, VERSIONS, dump_json, load_json  # noqa: E402
from neutral_analyze import score_docs  # noqa: E402

SEED = 42
N_BOOT = 2000


def path_for(split: str, model: str, version: str, domain: str) -> Path:
    root = QDEV if split == "dev" else QTEST
    # fair results for neutral/tuned on dev
    if split == "dev" and version in ("neutral", "tuned"):
        p = QFAIR / f"{model}_{version}_{domain}_rows.jsonl"
        if p.exists():
            return p
    full = root / f"{model}_{version}_{domain}_rows.jsonl"
    if full.exists():
        return full
    partial = root / f"{model}_{version}_{domain}_partial.jsonl"
    return partial if partial.exists() else full


def apply_settings(rows: list[dict], settings: dict) -> list[dict]:
    return [
        transform_row(
            r,
            axok=bool(settings.get("axok")),
            num2way=bool(settings.get("num2way")),
            ne_risky_only=bool(settings.get("ne_risky_only")),
            num_year_doc=bool(settings.get("num_year_doc")),
        )
        for r in rows
    ]


def analyze_with_settings(rows: list[dict], settings: dict) -> dict:
    tr = apply_settings(rows, settings)
    cm = clause_metrics(tr)
    dm = doc_metrics(tr, settings.get("R") or "R0", int(settings.get("K") or 2), clean_v2=bool(settings.get("clean_v2")))
    by = defaultdict(list)
    for r in tr:
        by[r["doc_id"]].append(r)
    ms = [float(r.get("latency_ms") or 0) for r in rows]
    by_doc = defaultdict(float)
    for r in rows:
        by_doc[r["doc_id"]] += float(r.get("latency_ms") or 0)
    parse_fail = sum(1 for r in rows if not r.get("parse_ok"))
    scores = score_docs(tr, check_cap79=False)
    scores79 = score_docs(tr, check_cap79=True)
    toxic_docs = sum(1 for labs in ({x.get("label") for x in rs} for rs in by.values()) if "toxic" in labs)
    return {
        "clause": {
            "warn_capture_rate": cm["warn_capture_rate"],
            "warn_capture_p": cm["warn_capture_p"],
            "detect_rate": cm["detect_rate"],
            "detect_p": cm["detect_p"],
            "fp_rate": cm["fp_rate"],
            "fp_p": cm["fp_p"],
            "overwarn_rate": cm["overwarn_rate"],
            "overwarn_p": cm["overwarn_p"],
            "warn_n": cm["warn_capture"],
            "warn_d": cm["toxic_n"],
            "detect_n": cm["detect"],
            "detect_d": cm["toxic_n"],
            "fp_n": cm["fp"],
            "fp_d": cm["safe_n"],
            "ow_n": cm["overwarn"],
            "ow_d": cm["safe_n"],
        },
        "doc": {
            "clean_pass_rate": dm["clean_pass_rate"],
            "clean_pass_p": dm["clean_pass_p"],
            "clean_pass": dm["clean_pass"],
            "clean_n": dm["clean_n"],
            "toxic_miss_n": dm["toxic_miss_n"],
            "toxic_doc_n": toxic_docs,
        },
        "score": scores,
        "score79": scores79,
        "parse_fail": parse_fail,
        "n": len(rows),
        "time_sec_per_doc": round((sum(by_doc.values()) / max(1, len(by_doc))) / 1000, 2),
        "settings": settings,
    }


def bootstrap_doc_ci(rows: list[dict], settings: dict, metric: str, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """metric: warn_capture|detect|fp|overwarn|clean_pass — 계약서 단위 재표집."""
    tr = apply_settings(rows, settings)
    by = defaultdict(list)
    for r in tr:
        by[r["doc_id"]].append(r)
    docs = list(by.keys())
    rng = random.Random(seed)

    def compute(doc_ids: list[str]) -> float | None:
        rs = [r for d in doc_ids for r in by[d]]
        if metric == "warn_capture":
            tox = [r for r in rs if r.get("label") == "toxic"]
            if not tox:
                return None
            return sum(1 for r in tox if r.get("verdict") in WARN) / len(tox)
        if metric == "detect":
            tox = [r for r in rs if r.get("label") == "toxic"]
            if not tox:
                return None
            return sum(1 for r in tox if r.get("verdict") in RISKY) / len(tox)
        if metric == "fp":
            saf = [r for r in rs if r.get("label") == "safe"]
            if not saf:
                return None
            return sum(1 for r in saf if r.get("verdict") in RISKY) / len(saf)
        if metric == "overwarn":
            saf = [r for r in rs if r.get("label") == "safe"]
            if not saf:
                return None
            return sum(1 for r in saf if r.get("verdict") == "확인 필요") / len(saf)
        if metric == "clean_pass":
            dm = doc_metrics(rs, settings.get("R") or "R0", int(settings.get("K") or 2), clean_v2=bool(settings.get("clean_v2")))
            return dm["clean_pass_p"]
        return None

    point = compute(docs)
    vals = []
    for _ in range(n_boot):
        sample = [docs[rng.randrange(len(docs))] for _ in range(len(docs))]
        v = compute(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return {"point": point, "lo": None, "hi": None, "n_boot": 0}
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))]
    hi = vals[int(0.975 * (len(vals) - 1))]
    return {"point": point, "lo": lo, "hi": hi, "n_boot": len(vals)}


def holm(pvals: list[tuple[str, float]]) -> dict[str, float]:
    """Return name -> holm-adjusted p."""
    m = len(pvals)
    ordered = sorted(pvals, key=lambda x: x[1])
    out = {}
    max_adj = 0.0
    for i, (name, p) in enumerate(ordered):
        adj = min(1.0, (m - i) * p)
        max_adj = max(max_adj, adj)
        out[name] = max_adj
    # ensure monotone by rank order already with running max
    return out


def novel_toxic_codes() -> dict:
    """근로 test 독소 중 dev에 없는 toxic_code."""
    from quant_run import load_domain_docs
    from dev_eval import is_meta, gold_codes

    def codes_for(split: str) -> Counter:
        c = Counter()
        for doc in load_domain_docs("LAB", split=split):
            for seg in doc["segs"]:
                if is_meta(seg) or seg.get("label") != "toxic":
                    continue
                law = doc["law_map"].get(seg.get("segment_id") or "", {})
                for code in gold_codes(seg, law) or ["(none)"]:
                    c[code] += 1
        return c

    # also count from gold files for TVD later
    dev_c = codes_for("dev")
    test_c = codes_for("test")
    novel = sorted(set(test_c) - set(dev_c))
    # lease/loan claim
    lease_dev = set()
    lease_test = set()
    loan_dev = set()
    loan_test = set()
    for domain, dset, tset in (("LEASE", lease_dev, lease_test), ("LOAN", loan_dev, loan_test)):
        for split, store in (("dev", dset), ("test", tset)):
            for doc in load_domain_docs(domain, split=split):
                for seg in doc["segs"]:
                    if is_meta(seg) or seg.get("label") != "toxic":
                        continue
                    law = doc["law_map"].get(seg.get("segment_id") or "", {})
                    for code in gold_codes(seg, law) or ["(none)"]:
                        store.add(code)
    return {
        "LAB_dev": dict(dev_c),
        "LAB_test": dict(test_c),
        "LAB_novel": novel,
        "LAB_novel_n": len(novel),
        "LAB_test_toxic_n": sum(test_c.values()),
        "LAB_novel_share": (sum(test_c[c] for c in novel) / max(1, sum(test_c.values()))),
        "LEASE_test_only": sorted(lease_test - lease_dev),
        "LOAN_test_only": sorted(loan_test - loan_dev),
        "LEASE_all_in_dev": len(lease_test - lease_dev) == 0,
        "LOAN_all_in_dev": len(loan_test - loan_dev) == 0,
    }


def data_diff() -> dict:
    from quant_run import load_domain_docs
    from dev_eval import is_meta, gold_codes

    out = {}
    for domain in DOMAINS:
        for split in ("dev", "test"):
            docs = load_domain_docs(domain, split=split)
            n_doc = len(docs)
            labels = Counter()
            lens = []
            texts = {"toxic": set(), "safe": set()}
            codes = Counter()
            n_seg = 0
            for doc in docs:
                for seg in doc["segs"]:
                    if is_meta(seg):
                        continue
                    n_seg += 1
                    lab = seg.get("label") or ""
                    labels[lab] += 1
                    t = seg.get("text") or ""
                    lens.append(len(t))
                    if lab in texts:
                        texts[lab].add(t)
                    if lab == "toxic":
                        law = doc["law_map"].get(seg.get("segment_id") or "", {})
                        for code in gold_codes(seg, law) or ["(none)"]:
                            codes[code] += 1
            out[f"{domain}_{split}"] = {
                "n_docs": n_doc,
                "n_segs": n_seg,
                "labels": dict(labels),
                "mean_len": round(sum(lens) / max(1, len(lens)), 1),
                "codes": dict(codes),
                "texts_toxic": texts["toxic"],
                "texts_safe": texts["safe"],
            }
        # overlap
        d = out[f"{domain}_dev"]
        t = out[f"{domain}_test"]
        tox_overlap = len(t["texts_toxic"] & d["texts_toxic"]) / max(1, len(t["texts_toxic"]))
        saf_overlap = len(t["texts_safe"] & d["texts_safe"]) / max(1, len(t["texts_safe"]))
        # TVD of toxic_code
        all_codes = set(d["codes"]) | set(t["codes"])
        sd = sum(d["codes"].values()) or 1
        st = sum(t["codes"].values()) or 1
        tvd = 0.5 * sum(abs(d["codes"].get(c, 0) / sd - t["codes"].get(c, 0) / st) for c in all_codes)
        out[f"{domain}_compare"] = {
            "toxic_text_overlap": tox_overlap,
            "safe_text_overlap": saf_overlap,
            "toxic_code_tvd": tvd,
            "test_only_codes": sorted(set(t["codes"]) - set(d["codes"])),
            "test_only_code_share": sum(t["codes"].get(c, 0) for c in set(t["codes"]) - set(d["codes"])) / st,
        }
        # drop text sets for JSON
        for split in ("dev", "test"):
            block = out[f"{domain}_{split}"]
            block.pop("texts_toxic", None)
            block.pop("texts_safe", None)
    return out


def pair_delta_boot(rows_a: list[dict], rows_b: list[dict], settings: dict, metric: str) -> dict:
    """짝지은 조각 기준 차이 bootstrap(계약서 단위). a-b."""
    ta = {(r["doc_id"], r["segment_id"]): r for r in apply_settings(rows_a, settings)}
    tb = {(r["doc_id"], r["segment_id"]): r for r in apply_settings(rows_b, settings)}
    keys = sorted(set(ta) & set(tb))
    by_doc = defaultdict(list)
    for k in keys:
        by_doc[k[0]].append(k)
    docs = list(by_doc.keys())
    rng = random.Random(SEED)

    def score(pairs: list[tuple]) -> float | None:
        if metric == "warn_capture":
            items = [(ta[k], tb[k]) for k in pairs if ta[k].get("label") == "toxic"]
            if not items:
                return None
            pa = sum(1 for a, _ in items if a.get("verdict") in WARN) / len(items)
            pb = sum(1 for _, b in items if b.get("verdict") in WARN) / len(items)
            return pa - pb
        if metric == "detect":
            items = [(ta[k], tb[k]) for k in pairs if ta[k].get("label") == "toxic"]
            if not items:
                return None
            pa = sum(1 for a, _ in items if a.get("verdict") in RISKY) / len(items)
            pb = sum(1 for _, b in items if b.get("verdict") in RISKY) / len(items)
            return pa - pb
        if metric == "fp":
            items = [(ta[k], tb[k]) for k in pairs if ta[k].get("label") == "safe"]
            if not items:
                return None
            pa = sum(1 for a, _ in items if a.get("verdict") in RISKY) / len(items)
            pb = sum(1 for _, b in items if b.get("verdict") in RISKY) / len(items)
            return pa - pb
        return None

    all_pairs = keys
    point = score(all_pairs)
    vals = []
    for _ in range(N_BOOT):
        sample_docs = [docs[rng.randrange(len(docs))] for _ in range(len(docs))]
        pairs = [k for d in sample_docs for k in by_doc[d]]
        v = score(pairs)
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))] if vals else None
    hi = vals[int(0.975 * (len(vals) - 1))] if vals else None
    return {"point": point, "lo": lo, "hi": hi, "covers_zero": (lo is not None and hi is not None and lo <= 0 <= hi)}


def main() -> None:
    freeze = load_json(QTEST / "freeze.json")
    fixed = freeze["fixed"]
    best = freeze["best"]
    loaded = {}
    excluded = []
    for split in ("dev", "test"):
        for model in MODELS:
            for version in VERSIONS:
                for domain in DOMAINS:
                    key = (split, model, version, domain)
                    p = path_for(split, model, version, domain)
                    if not p.exists():
                        loaded[key] = None
                        excluded.append({"key": key, "reason": "파일 없음", "path": str(p)})
                        continue
                    rows = load_rows(p)
                    loaded[key] = rows

    # basic tables test
    tables = {}
    boots = {}
    for model in MODELS:
        for version in VERSIONS:
            for kind, settings_src in (("fixed", None), ("best", None)):
                for domain in list(DOMAINS) + ["ALL"]:
                    settings = dict(fixed) if kind == "fixed" else (best.get(version, {}).get(model, {}).get(domain if domain != "ALL" else "LAB") or dict(fixed))
                    if domain == "ALL":
                        # domain-specific best: apply per-domain then concat metrics carefully
                        rows = []
                        missing = False
                        for d in DOMAINS:
                            r = loaded.get(("test", model, version, d))
                            if r is None:
                                missing = True
                                break
                            rows.extend(r)
                        if missing:
                            continue
                        # For ALL with best, transform each domain with its own best
                        if kind == "best":
                            tr = []
                            for d in DOMAINS:
                                st = best.get(version, {}).get(model, {}).get(d) or dict(fixed)
                                tr.extend(apply_settings(loaded[("test", model, version, d)], st))
                            cm = clause_metrics(tr)
                            dm = doc_metrics(tr, fixed["R"], fixed["K"], clean_v2=True)
                            # approximate using fixed R/K for ALL best doc metrics is imperfect;
                            # recompute domain-wise weighted later. Use per-domain settings already in tr for clause;
                            # for doc_metrics use R/K from LAB best or fixed.
                            st0 = best.get(version, {}).get(model, {}).get("LAB") or dict(fixed)
                            dm = doc_metrics(tr, st0.get("R") or "R0", int(st0.get("K") or 2), clean_v2=bool(st0.get("clean_v2")))
                            block = {
                                "clause": {
                                    "warn_capture_rate": cm["warn_capture_rate"],
                                    "detect_rate": cm["detect_rate"],
                                    "fp_rate": cm["fp_rate"],
                                    "overwarn_rate": cm["overwarn_rate"],
                                    "warn_capture_p": cm["warn_capture_p"],
                                    "detect_p": cm["detect_p"],
                                    "fp_p": cm["fp_p"],
                                    "overwarn_p": cm["overwarn_p"],
                                    "warn_n": cm["warn_capture"],
                                    "warn_d": cm["toxic_n"],
                                    "detect_n": cm["detect"],
                                    "detect_d": cm["toxic_n"],
                                    "fp_n": cm["fp"],
                                    "fp_d": cm["safe_n"],
                                    "ow_n": cm["overwarn"],
                                    "ow_d": cm["safe_n"],
                                },
                                "doc": {
                                    "clean_pass_rate": dm["clean_pass_rate"],
                                    "clean_pass_p": dm["clean_pass_p"],
                                    "clean_pass": dm["clean_pass"],
                                    "clean_n": dm["clean_n"],
                                    "toxic_miss_n": dm["toxic_miss_n"],
                                    "toxic_doc_n": dm["toxic_n"],
                                },
                                "score": score_docs(tr, check_cap79=False),
                                "score79": score_docs(tr, check_cap79=True),
                                "parse_fail": sum(1 for r in rows if not r.get("parse_ok")),
                                "n": len(rows),
                                "time_sec_per_doc": None,
                                "settings": {"note": "per-domain best; doc R/K from LAB best"},
                            }
                        else:
                            block = analyze_with_settings(rows, settings)
                        tables[(model, version, kind, domain)] = block
                        continue
                    rows = loaded.get(("test", model, version, domain))
                    if rows is None:
                        continue
                    if kind == "best":
                        settings = best.get(version, {}).get(model, {}).get(domain) or dict(fixed)
                    block = analyze_with_settings(rows, settings)
                    tables[(model, version, kind, domain)] = block
                    boots[(model, version, kind, domain)] = {
                        m: bootstrap_doc_ci(rows, settings, m) for m in ("warn_capture", "detect", "fp", "overwarn", "clean_pass")
                    }

    # card effects
    card_fx = {}
    for model in MODELS:
        card_fx[model] = {}
        for a, b, name in (("neutral", "none", "neutral_minus_none"), ("tuned", "none", "tuned_minus_none"), ("tuned", "neutral", "tuned_minus_neutral")):
            card_fx[model][name] = {}
            for domain in DOMAINS:
                ra = loaded.get(("test", model, a, domain))
                rb = loaded.get(("test", model, b, domain))
                if ra is None or rb is None:
                    continue
                # use fixed settings for fair paired compare
                settings = dict(fixed)
                ta = apply_settings(ra, settings)
                tb = apply_settings(rb, settings)
                card_fx[model][name][domain] = {
                    "warn_capture": {
                        "mcnemar": mcnemar_compare(ta, tb, kind="warn_capture"),
                        "delta_boot": pair_delta_boot(ra, rb, settings, "warn_capture"),
                    },
                    "detect": {
                        "mcnemar": mcnemar_compare(ta, tb, kind="warn_capture"),  # placeholder wrong
                        "delta_boot": pair_delta_boot(ra, rb, settings, "detect"),
                    },
                    "fp": {
                        "mcnemar": mcnemar_compare(ta, tb, kind="fp"),
                        "delta_boot": pair_delta_boot(ra, rb, settings, "fp"),
                    },
                }
                # fix detect mcnemar manually
                ka = {(r["doc_id"], r["segment_id"]): r for r in ta}
                kb = {(r["doc_id"], r["segment_id"]): r for r in tb}
                b_ct = c_ct = n = 0
                for k in sorted(set(ka) & set(kb)):
                    if ka[k].get("label") != "toxic":
                        continue
                    ya = ka[k].get("verdict") in RISKY
                    yb = kb[k].get("verdict") in RISKY
                    n += 1
                    if ya and not yb:
                        b_ct += 1
                    elif (not ya) and yb:
                        c_ct += 1
                from replay import mcnemar_exact

                card_fx[model][name][domain]["detect"]["mcnemar"] = {
                    "n": n,
                    "b": b_ct,
                    "c": c_ct,
                    "p": round(mcnemar_exact(b_ct, c_ct), 6),
                }

    # model compare + Holm
    model_cmp = {}
    p_collect = []
    for version in VERSIONS:
        model_cmp[version] = {}
        for domain in DOMAINS:
            model_cmp[version][domain] = {}
            for a, b in (("luna", "EXAONE"), ("luna", "AX"), ("EXAONE", "AX")):
                ra = loaded.get(("test", a, version, domain))
                rb = loaded.get(("test", b, version, domain))
                if ra is None or rb is None:
                    continue
                ta = apply_settings(ra, fixed)
                tb = apply_settings(rb, fixed)
                cell = {
                    "warn_capture": mcnemar_compare(ta, tb, kind="warn_capture"),
                    "fp": mcnemar_compare(ta, tb, kind="fp"),
                }
                # detect
                ka = {(r["doc_id"], r["segment_id"]): r for r in ta}
                kb = {(r["doc_id"], r["segment_id"]): r for r in tb}
                b_ct = c_ct = n = 0
                for k in sorted(set(ka) & set(kb)):
                    if ka[k].get("label") != "toxic":
                        continue
                    ya = ka[k].get("verdict") in RISKY
                    yb = kb[k].get("verdict") in RISKY
                    n += 1
                    if ya and not yb:
                        b_ct += 1
                    elif (not ya) and yb:
                        c_ct += 1
                from replay import mcnemar_exact

                cell["detect"] = {"n": n, "b": b_ct, "c": c_ct, "p": round(mcnemar_exact(b_ct, c_ct), 6)}
                model_cmp[version][domain][f"{a}_vs_{b}"] = cell
                for metric in ("warn_capture", "detect", "fp"):
                    p_collect.append((f"{version}|{domain}|{a}_vs_{b}|{metric}", cell[metric]["p"]))
    holm_map = holm(p_collect)
    for version in model_cmp:
        for domain in model_cmp[version]:
            for pair, cell in model_cmp[version][domain].items():
                for metric in ("warn_capture", "detect", "fp"):
                    cell[metric]["p_holm"] = holm_map.get(f"{version}|{domain}|{pair}|{metric}")

    # dev vs test
    dev_test = {}
    for model in MODELS:
        for version in VERSIONS:
            for domain in DOMAINS:
                rd = loaded.get(("dev", model, version, domain))
                rt = loaded.get(("test", model, version, domain))
                if rd is None or rt is None:
                    continue
                settings = dict(fixed)
                ad = analyze_with_settings(rd, settings)
                at = analyze_with_settings(rt, settings)
                boot = bootstrap_doc_ci(rt, settings, "warn_capture")
                boot_fp = bootstrap_doc_ci(rt, settings, "fp")
                boot_clean = bootstrap_doc_ci(rt, settings, "clean_pass")
                def outside(dev_p, boot):
                    if boot.get("lo") is None or boot.get("hi") is None or dev_p is None:
                        return None
                    return dev_p < boot["lo"] or dev_p > boot["hi"]

                dev_test[(model, version, domain)] = {
                    "dev": ad,
                    "test": at,
                    "warn_boot": boot,
                    "fp_boot": boot_fp,
                    "clean_boot": boot_clean,
                    "dev_warn_outside_test_boot": outside(ad["clause"]["warn_capture_p"], boot),
                    "dev_fp_outside_test_boot": outside(ad["clause"]["fp_p"], boot_fp),
                    "dev_clean_outside_test_boot": outside(ad["doc"]["clean_pass_p"], boot_clean),
                }

    # novel toxic on LAB test
    novel = novel_toxic_codes()
    novel_metrics = {}
    novel_set = set(novel.get("LAB_novel") or [])
    for model in MODELS:
        for version in VERSIONS:
            rows = loaded.get(("test", model, version, "LAB"))
            if rows is None:
                continue
            tr = apply_settings(rows, fixed)
            subset = []
            for r in tr:
                if r.get("label") != "toxic":
                    continue
                codes = r.get("gold_codes") or []
                if any(c in novel_set for c in codes):
                    subset.append(r)
            if not subset:
                novel_metrics[(model, version)] = {"n": 0}
                continue
            warn = sum(1 for r in subset if r.get("verdict") in WARN)
            det = sum(1 for r in subset if r.get("verdict") in RISKY)
            novel_metrics[(model, version)] = {
                "n": len(subset),
                "warn_capture": rate(warn, len(subset)),
                "detect": rate(det, len(subset)),
                "warn_p": warn / len(subset),
                "detect_p": det / len(subset),
            }

    data = data_diff()

    # cost
    cost = {}
    cp = QTEST / "gpt_cost_state.json"
    if cp.exists():
        cost = load_json(cp)
    detail = QTEST / "gpt_cost_detail.json"
    if detail.exists():
        cost["detail"] = load_json(detail)

    def ser_key(k):
        return "|".join(str(x) for x in k)

    payload = {
        "freeze": freeze,
        "excluded": excluded,
        "tables": {ser_key(k): v for k, v in tables.items()},
        "boots": {ser_key(k): v for k, v in boots.items()},
        "card_fx": card_fx,
        "model_cmp": model_cmp,
        "dev_test": {ser_key(k): v for k, v in dev_test.items()},
        "novel": novel,
        "novel_metrics": {ser_key(k): v for k, v in novel_metrics.items()},
        "data_diff": data,
        "cost": cost,
    }
    dump_json(QTEST / "summary.json", payload)
    print("WROTE", QTEST / "summary.json", "excluded", len(excluded), flush=True)


if __name__ == "__main__":
    main()
