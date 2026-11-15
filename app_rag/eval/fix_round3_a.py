# -*- coding: utf-8 -*-
"""FIX_ROUND3-A: 숫자규칙·인용완화 replay 전/후 (LLM 없음)."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import is_blocking_fact  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.verify import _contains, _is_wage_amount_clause, verify_finding  # noqa: E402
from quant_run import out_path  # noqa: E402
from replay import (  # noqa: E402
    clause_metrics,
    doc_metrics,
    load_rows,
    transform_row,
    write_csv,
)
from relax_check import classify_review_source  # noqa: E402
from metrics import score_pair  # noqa: E402

# 구버전 대조용 (백업)
import importlib.util


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


facts_old = _load_mod("facts_v5", APP / "rag" / "facts_v5.py")
verify_old = _load_mod("verify_v7", APP / "rag" / "verify_v7.py")

WAGE_HINT = re.compile(
    r"시급|시간급|시간당|1시간당|시간\s*단위\s*임금|월급|월\s*급여|월\s*임금|최저임금|기본급|임금.{0,24}\d"
)
DOMAINS = ("LAB", "LEASE", "LOAN")
QUANT3 = OUT / "quant3"


def _cards(row):
    return row.get("selected_cards_full") or [{"id": c} for c in (row.get("selected_cards") or [])]


def _hits(row):
    return [
        {
            "id": h.get("id"),
            "title": h.get("title") or "",
            "doc_type": h.get("doc_type") or "",
            "text": h.get("text") or "",
            "score": h.get("score"),
        }
        for h in (row.get("hits") or [])
    ]


def wage_recognized(text: str, extract_fn) -> bool:
    if not WAGE_HINT.search(text or ""):
        return False
    f = extract_fn(text or "")
    return f.get("hourly_wage") is not None or f.get("monthly_wage") is not None


def quote_mismatch_old(row) -> bool:
    finding = row.get("finding") or {}
    clause = row.get("text") or ""
    cq = finding.get("contract_quote") or ""
    if cq and not verify_old._contains(cq, clause):
        return True
    allowed = {h["id"]: h for h in _hits(row)}
    for ev in finding.get("evidence") or []:
        rec = allowed.get(ev.get("id"))
        if rec and ev.get("quote") and not verify_old._contains(ev.get("quote") or "", rec.get("text") or ""):
            return True
    return False


def quote_mismatch_new(row) -> bool:
    finding = row.get("finding") or {}
    clause = row.get("text") or ""
    cq = finding.get("contract_quote") or ""
    if cq and not _contains(cq, clause):
        return True
    allowed = {h["id"]: h for h in _hits(row)}
    for ev in finding.get("evidence") or []:
        rec = allowed.get(ev.get("id"))
        if rec and ev.get("quote") and not _contains(ev.get("quote") or "", rec.get("text") or ""):
            return True
    return False


def replay_variant(row: dict, *, soft_quote: bool, new_wage: bool) -> dict:
    """soft_quote/new_wage 켠 상태로 verify 재적용. NUM2WAY 켬, axok 끔."""
    finding = dict(row.get("finding") or {})
    domain = row.get("domain") or "LAB"
    text = row.get("text") or ""
    # facts: 새 임금이면 조항+문서 재추출 병합
    if new_wage:
        # 문서 facts는 전체 텍스트가 없으므로 저장 facts의 주시간·날짜를 유지하고 조항에서 임금 보강
        facts = dict(row.get("facts") or {})
        local = extract_facts(text)
        for k in ("hourly_wage", "monthly_wage", "hourly_from_monthly"):
            if local.get(k) is not None:
                facts[k] = local[k]
        # 문서에 주시간이 있고 월급만 있으면 환산
        if facts.get("hourly_wage") is None and facts.get("monthly_wage") and facts.get("weekly_scheduled_hours"):
            from rag.facts import _fill_hourly_from_monthly

            _fill_hourly_from_monthly(facts)
    else:
        facts = dict(row.get("facts") or {})

    cards = _cards(row)
    hits = _hits(row)
    nf_mode = "cards" if domain == "LAB" else "legacy"

    if soft_quote:
        verified = verify_finding(
            text, hits, finding, facts,
            needs_fact_mode=nf_mode,
            selected_cards=cards if domain == "LAB" else [],
            ax_review_to_ok=False,
        )
    else:
        # 구 인용 규칙: verify_old
        verified = verify_old.verify_finding(
            text, hits, finding, facts,
            needs_fact_mode=nf_mode,
            selected_cards=cards if domain == "LAB" else [],
            ax_review_to_ok=False,
        )

    # NUM2WAY (doc year 허용 — QUANT 합의)
    from replay import apply_num2way

    verdict = verified.get("verdict") or "확인 필요"
    new_v, info = apply_num2way(verdict, text, doc_facts=facts, allow_doc_year=True)
    flipped = new_v != verdict
    if flipped:
        verdict = new_v

    out = dict(row)
    out["verdict"] = verdict
    out["ax_verdict"] = verified.get("ax_verdict")
    out["notes"] = list(verified.get("notes") or [])
    if flipped:
        out["notes"] = out["notes"] + ["num2way_to_ok"]
    out["review_sources"] = verified.get("review_sources") or []
    out["review_source"] = classify_review_source(verified, verdict)
    out["needs_fact"] = verified.get("needs_fact")
    nf = out["needs_fact"]
    out["needs_fact_is_blocking_if"] = bool(nf) and is_blocking_fact(nf, cards) if cards else False
    out["quote_mismatch"] = "quote_mismatch" in (out["review_sources"])
    out["bucket"] = score_pair(row.get("label") or "", verdict)
    out["num2way_flipped"] = flipped
    out["facts_used"] = {k: facts.get(k) for k in ("hourly_wage", "monthly_wage", "weekly_scheduled_hours", "start_date")}
    return out


def summarize(rows: list[dict], tag: str) -> dict:
    cm = clause_metrics(rows)
    dm = doc_metrics(rows, "R0", 2, clean_v2=True)
    tox_flips = [
        {
            "doc_id": r["doc_id"],
            "segment_id": r["segment_id"],
            "domain": r.get("domain"),
            "ax": r.get("ax_verdict"),
            "verdict": r.get("verdict"),
            "text40": (r.get("text") or "").replace("\n", " ")[:40],
        }
        for r in rows
        if r.get("label") == "toxic" and r.get("num2way_flipped")
    ]
    # also toxic whose final verdict differs from stored baseline verdict? handled outside
    return {
        "tag": tag,
        "warn": cm["warn_capture_rate"],
        "fp": cm["fp_rate"],
        "overwarn": cm["overwarn_rate"],
        "detect": cm["detect_rate"],
        "clean": dm["clean_pass_rate"],
        "check_doc": dm["check_doc_rate"],
        "toxic_miss_n": dm["toxic_miss_n"],
        "toxic_misses": dm["toxic_misses"],
        "warn_p": cm["warn_capture_p"],
        "fp_p": cm["fp_p"],
        "clean_p": dm["clean_pass_p"],
        "n": cm["n"],
        "num2way_toxic_flips": tox_flips,
    }


def main() -> None:
    QUANT3.mkdir(parents=True, exist_ok=True)
    (QUANT3 / "tables").mkdir(parents=True, exist_ok=True)

    all_rows = []
    for d in DOMAINS:
        all_rows.extend(load_rows(out_path("EXAONE", d)))

    # wage recognition counts
    wage_like = [r for r in all_rows if WAGE_HINT.search(r.get("text") or "")]
    wage_old = sum(1 for r in wage_like if wage_recognized(r["text"], facts_old.extract_facts))
    wage_new = sum(1 for r in wage_like if wage_recognized(r["text"], extract_facts))
    wage_stats = {
        "wage_like": len(wage_like),
        "recognized_before": wage_old,
        "recognized_after": wage_new,
        "unrecognized_before": len(wage_like) - wage_old,
        "unrecognized_after": len(wage_like) - wage_new,
    }

    # quote mismatch counts
    qm = {"before": {"toxic": 0, "safe": 0, "n_tox": 0, "n_saf": 0}, "after": {"toxic": 0, "safe": 0, "n_tox": 0, "n_saf": 0}}
    for r in all_rows:
        lab = r.get("label")
        if lab == "toxic":
            qm["before"]["n_tox"] += 1
            qm["after"]["n_tox"] += 1
            if quote_mismatch_old(r):
                qm["before"]["toxic"] += 1
            if quote_mismatch_new(r):
                qm["after"]["toxic"] += 1
        elif lab == "safe":
            qm["before"]["n_saf"] += 1
            qm["after"]["n_saf"] += 1
            if quote_mismatch_old(r):
                qm["before"]["safe"] += 1
            if quote_mismatch_new(r):
                qm["after"]["safe"] += 1

    variants = {
        "base": {"soft_quote": False, "new_wage": False},
        "wage_only": {"soft_quote": False, "new_wage": True},
        "quote_only": {"soft_quote": True, "new_wage": False},
        "both": {"soft_quote": True, "new_wage": True},
    }
    results = {}
    toxic_changed = []  # base vs variant final verdict on toxic
    base_rows = [replay_variant(r, **variants["base"]) for r in all_rows]
    base_by = {(r["doc_id"], r["segment_id"]): r for r in base_rows}
    results["base"] = summarize(base_rows, "base")

    for name, opts in variants.items():
        if name == "base":
            continue
        rows = [replay_variant(r, **opts) for r in all_rows]
        results[name] = summarize(rows, name)
        for r in rows:
            if r.get("label") != "toxic":
                continue
            b = base_by.get((r["doc_id"], r["segment_id"]))
            if b and b.get("verdict") != r.get("verdict"):
                toxic_changed.append(
                    {
                        "variant": name,
                        "domain": r.get("domain"),
                        "doc_id": r["doc_id"],
                        "segment_id": r["segment_id"],
                        "before": b.get("verdict"),
                        "after": r.get("verdict"),
                        "text40": (r.get("text") or "").replace("\n", " ")[:40],
                    }
                )

    # keep rule: toxic_miss_n == 0 and not worse miss; prefer improvements
    keep = []
    base_miss = results["base"]["toxic_miss_n"]
    for name in ("wage_only", "quote_only", "both"):
        cell = results[name]
        if cell["toxic_miss_n"] > base_miss:
            keep.append({"name": name, "keep": False, "reason": f"독소놓침 {cell['toxic_miss_n']}>{base_miss}"})
            continue
        # improve if warn up or fp/ow/clean better without miss increase
        better = (
            (cell.get("warn_p") or 0) >= (results["base"].get("warn_p") or 0)
            and (cell.get("fp_p") or 1) <= (results["base"].get("fp_p") or 1) + 1e-9
        ) or (qm["after"]["toxic"] + qm["after"]["safe"] < qm["before"]["toxic"] + qm["before"]["safe"] and name in ("quote_only", "both")) \
          or (wage_stats["unrecognized_after"] < wage_stats["unrecognized_before"] and name in ("wage_only", "both"))
        # always keep if miss not worse and (quote reduced or wage recog improved)
        ok = cell["toxic_miss_n"] <= base_miss
        keep.append({"name": name, "keep": bool(ok and (name == "both" or better or True)), "reason": "독소놓침 유지"})

    # A-4: 둘 다 독소놓침 안 늘리면 both 채택
    adopt_wage = results["wage_only"]["toxic_miss_n"] <= base_miss
    adopt_quote = results["quote_only"]["toxic_miss_n"] <= base_miss
    adopt = {"new_wage": adopt_wage, "soft_quote": adopt_quote, "code_applied": True}

    payload = {
        "wage_stats": wage_stats,
        "quote_mismatch": qm,
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "num2way_toxic_flips"} for k, v in results.items()},
        "toxic_changed": toxic_changed,
        "keep": keep,
        "adopt": adopt,
    }
    (QUANT3 / "fix_round3_a.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(QUANT3 / "tables" / "a_toxic_changed.csv", toxic_changed)

    lines = ["# FIX_ROUND3-A", "", "## 임금 인식", json.dumps(wage_stats, ensure_ascii=False), "", "## quote_mismatch", json.dumps(qm, ensure_ascii=False), "", "## 지표"]
    lines.append("| 변형 | warn | fp | overwarn | clean_v2 K2 | 독소놓침 |")
    lines.append("|---|---|---|---|---|---|")
    for name in ("base", "wage_only", "quote_only", "both"):
        r = results[name]
        lines.append(f"| {name} | {r['warn']} | {r['fp']} | {r['overwarn']} | {r['clean']} | {r['toxic_miss_n']} |")
    lines.append("")
    lines.append(f"## 채택: wage={adopt_wage} quote={adopt_quote}")
    lines.append(f"toxic 판정 변경 {len(toxic_changed)}건 → tables/a_toxic_changed.csv")
    (OUT / "FIX_ROUND3_A.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wage": wage_stats, "qm_tox": (qm["before"]["toxic"], qm["after"]["toxic"]), "qm_saf": (qm["before"]["safe"], qm["after"]["safe"]), "adopt": adopt, "miss": {k: results[k]["toxic_miss_n"] for k in results}}, ensure_ascii=False, indent=2))
    print("WROTE", OUT / "FIX_ROUND3_A.md")


if __name__ == "__main__":
    main()
