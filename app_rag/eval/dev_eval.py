# -*- coding: utf-8 -*-
"""dev 전용 A방식 평가. 정답 조각 text+순서만 시스템에 넘긴다. test 금지."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, generate_finding  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import verify_finding  # noqa: E402
from recall_dev import (  # noqa: E402
    canon_from_id,
    gold_in_corpus,
    hit_matches_gold,
    keys_from_gold,
    load_jsonl,
)
from splitutil import load_split_ids  # noqa: E402
from metrics import RISKY, rate, score_pair, summarize_rows  # noqa: E402

LEAK_FIELDS = ("label", "toxic_code", "evidence_hint", "facts", "std_item")


def is_meta(seg: dict) -> bool:
    return (seg.get("segment_type") or "") == "meta" or (seg.get("label") or "") == "meta"


def gold_codes(seg: dict, law: dict) -> list[str]:
    raw = law.get("toxic_code") if law.get("toxic_code") else seg.get("toxic_code")
    if isinstance(raw, str):
        return [raw] if raw else []
    return [str(x) for x in (raw or []) if x]


def gold_provisions(seg: dict, law: dict) -> list[str]:
    return list(law.get("legal_provisions") or seg.get("evidence_hint") or [])


def load_docs(domain: str | None) -> list[dict]:
    names = [domain] if domain else ["LEASE", "LOAN", "LAB"]
    docs = []
    for name in names:
        keep = load_split_ids("dev", name)
        contracts = load_jsonl(GOLD[name]["contract"])
        law_map = {r["segment_id"]: r for r in load_jsonl(GOLD[name]["law"])}
        by_doc = defaultdict(list)
        for row in contracts:
            if row.get("doc_id") in keep:
                by_doc[row["doc_id"]].append(row)
        for did in sorted(by_doc):
            segs = sorted(
                by_doc[did],
                key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
            )
            docs.append({"domain": name, "doc_id": did, "segs": segs, "law_map": law_map})
    return docs


def count_judge(docs: list[dict]) -> dict:
    out = {d: {"docs": 0, "judge": 0, "meta": 0, "toxic": 0, "safe": 0, "check": 0} for d in ("LEASE", "LOAN", "LAB")}
    out["ALL"] = {"docs": 0, "judge": 0, "meta": 0, "toxic": 0, "safe": 0, "check": 0}
    for doc in docs:
        d = doc["domain"]
        out[d]["docs"] += 1
        out["ALL"]["docs"] += 1
        for seg in doc["segs"]:
            if is_meta(seg):
                out[d]["meta"] += 1
                out["ALL"]["meta"] += 1
                continue
            out[d]["judge"] += 1
            out["ALL"]["judge"] += 1
            lab = seg.get("label") or ""
            if lab in ("toxic", "safe", "check"):
                out[d][lab] += 1
                out["ALL"][lab] += 1
    return out


def eval_doc(doc: dict, index, corpus_keys, corpus_ids, llm_ok: bool) -> dict:
    segs = doc["segs"]
    domain = doc["domain"]
    full = "\n".join(s.get("text") or "" for s in segs)
    facts = extract_facts(full)
    rows = []
    for seg in segs:
        if is_meta(seg):
            continue
        text = seg.get("text") or ""
        law = doc["law_map"].get(seg.get("segment_id") or "") or {}
        t0 = time.perf_counter()
        retrieved = index.search(strip_placeholders(text), domain=domain, title="")
        hits = retrieved.get("hits") or []
        if llm_ok:
            finding = generate_finding(text, facts, hits)
        else:
            finding = {
                "verdict": "확인 필요",
                "contract_quote": "",
                "gap": "",
                "why": "A.X 없음",
                "evidence": [],
                "suggestion": "",
                "needs_fact": None,
                "parse_ok": False,
                "error": "ax_down",
            }
        verified = verify_finding(text, hits, finding, facts)
        ms = (time.perf_counter() - t0) * 1000
        used_ids = [e.get("id") for e in (verified.get("evidence") or []) if e.get("id")]
        hit_ids = [h["id"] for h in hits]
        gold_raw = gold_provisions(seg, law)
        gold_keys = {k for raw in gold_raw for k in keys_from_gold(raw)}
        in_corpus = [raw for raw in gold_raw if gold_in_corpus(raw, corpus_keys, corpus_ids)]
        missing = [raw for raw in gold_raw if raw not in in_corpus]
        all_missing = bool(gold_raw) and not in_corpus
        ev_ok = any(hit_matches_gold(eid, gold_keys, gold_raw) for eid in used_ids) if (gold_keys or gold_raw) else False
        rec_ok = any(hit_matches_gold(hid, gold_keys, gold_raw) for hid in hit_ids) if (gold_keys or gold_raw) else False
        verdict = verified.get("verdict") or "확인 필요"
        label = seg.get("label") or ""
        bucket = score_pair(label, verdict)
        notes = verified.get("notes") or []
        ax_v = verified.get("ax_verdict")
        rule_flip = "rule_override" in notes and ax_v != verdict
        sys_codes = list(verified.get("toxic_code") or finding.get("toxic_code") or [])
        gold_c = gold_codes(seg, law)
        code_ok = bool(set(sys_codes) & set(gold_c)) if sys_codes and gold_c else False
        rows.append(
            {
                "domain": domain,
                "doc_id": doc["doc_id"],
                "segment_id": seg.get("segment_id"),
                "order": seg.get("order"),
                "segment_type": seg.get("segment_type"),
                "label": label,
                "gold_codes": gold_c,
                "gold_provisions": gold_raw,
                "verdict": verdict,
                "ax_verdict": ax_v,
                "bucket": bucket,
                "why": (verified.get("why") or "")[:240],
                "used_ids": used_ids,
                "hit_ids": hit_ids,
                "sys_codes": sys_codes,
                "code_ok": code_ok,
                "ev_ok": ev_ok,
                "recall_ok": rec_ok,
                "gold_missing_from_corpus": all_missing,
                "gold_not_in_corpus": missing,
                "parse_ok": bool(verified.get("parse_ok")),
                "quote_mismatch": any(str(n).startswith("quote_mismatch") for n in notes),
                "dropped_n": len(verified.get("dropped_ids") or []),
                "rule_flip": rule_flip,
                "latency_ms": round(ms, 1),
                "text60": (text.replace("\n", " ")[:60]),
            }
        )
    return {"domain": domain, "doc_id": doc["doc_id"], "rows": rows}


def summarize(rows: list[dict], corpus_has_sys_code: bool) -> dict:
    by = {d: [r for r in rows if r["domain"] == d] for d in ("LEASE", "LOAN", "LAB")}
    by["ALL"] = rows
    tables = {}
    for name, rs in by.items():
        tox = [r for r in rs if r["label"] == "toxic"]
        saf = [r for r in rs if r["label"] == "safe"]
        chk = [r for r in rs if r["label"] == "check"]
        det = [r for r in tox if r["bucket"] == "detect"]
        par = [r for r in tox if r["bucket"] == "partial"]
        mis = [r for r in tox if r["bucket"] == "miss"]
        fp = [r for r in saf if r["bucket"] == "fp"]
        ow = [r for r in saf if r["bucket"] == "overwarn"]
        cok = [r for r in chk if r["bucket"] == "check_ok"]
        ctox = [r for r in chk if r["bucket"] == "check_as_toxic"]
        csafe = [r for r in chk if r["bucket"] == "check_as_safe"]
        code_n = sum(1 for r in det if r["code_ok"])
        ev_all = tox + chk
        ev_ok_all = sum(1 for r in ev_all if r["ev_ok"])
        ev_inc = [r for r in ev_all if not r["gold_missing_from_corpus"]]
        ev_ok_inc = sum(1 for r in ev_inc if r["ev_ok"])
        rec_t = [r for r in tox]
        rec_c = [r for r in chk]
        lat = [r["latency_ms"] for r in rs]
        tables[name] = {
            "n": len(rs),
            "toxic": len(tox),
            "detect": len(det),
            "partial": len(par),
            "miss": len(mis),
            "safe": len(saf),
            "fp": len(fp),
            "overwarn": len(ow),
            "check": len(chk),
            "check_ok": len(cok),
            "check_as_toxic": len(ctox),
            "check_as_safe": len(csafe),
            "code_ok": code_n,
            "code_den": len(det),
            "sys_code_present": corpus_has_sys_code,
            "ev_ok": ev_ok_all,
            "ev_den": len(ev_all),
            "ev_ok_inc": ev_ok_inc,
            "ev_den_inc": len(ev_inc),
            "gold_missing_n": sum(1 for r in ev_all if r["gold_missing_from_corpus"]),
            "recall_toxic": sum(1 for r in rec_t if r["recall_ok"]),
            "recall_toxic_den": len(rec_t),
            "recall_check": sum(1 for r in rec_c if r["recall_ok"]),
            "recall_check_den": len(rec_c),
            "quote_mismatch": sum(1 for r in rs if r["quote_mismatch"]),
            "dropped_ids": sum(r["dropped_n"] for r in rs),
            "parse_fail": sum(1 for r in rs if not r["parse_ok"]),
            "rule_flip": sum(1 for r in rs if r["rule_flip"]),
            "lat_avg": (sum(lat) / len(lat)) if lat else 0.0,
            "lat_max": max(lat) if lat else 0.0,
            "detect_rate": rate(len(det), len(tox)),
            "partial_rate": rate(len(par), len(tox)),
            "miss_rate": rate(len(mis), len(tox)),
            "fp_rate": rate(len(fp), len(saf)),
            "overwarn_rate": rate(len(ow), len(saf)),
            "check_rate": rate(len(cok), len(chk)),
            "code_rate": rate(code_n, len(det)) if corpus_has_sys_code else "미확인 (시스템 toxic_code 없음)",
            "ev_rate": rate(ev_ok_all, len(ev_all)),
            "ev_rate_inc": rate(ev_ok_inc, len(ev_inc)),
            "recall_t_rate": rate(sum(1 for r in rec_t if r["recall_ok"]), len(rec_t)),
            "recall_c_rate": rate(sum(1 for r in rec_c if r["recall_ok"]), len(rec_c)),
        }
        # FIX_ROUND1-B 보강 지표
        extra = summarize_rows(rs)
        for k in (
            "warn_capture_rate",
            "clean_doc_pass_rate",
            "toxic_doc_warn_rate",
            "ax_review_to_ok",
            "ax_review_to_ok_toxic",
            "ax_review_to_ok_safe",
            "doc_headlines",
        ):
            tables[name][k] = extra.get(k)
    codes = defaultdict(lambda: {"n": 0, "detect": 0, "partial": 0, "miss": 0, "domain": ""})
    for r in rows:
        if r["label"] != "toxic":
            continue
        for c in r["gold_codes"] or ["(없음)"]:
            cell = codes[(r["domain"], c)]
            cell["n"] += 1
            cell["domain"] = r["domain"]
            if r["bucket"] == "detect":
                cell["detect"] += 1
            elif r["bucket"] == "partial":
                cell["partial"] += 1
            else:
                cell["miss"] += 1
    missed = [r for r in rows if r["label"] == "toxic" and r["bucket"] == "miss"]
    fps = [r for r in rows if r["label"] == "safe" and r["bucket"] == "fp"]
    return {"tables": tables, "codes": {f"{k[0]}|{k[1]}": v for k, v in codes.items()}, "missed": missed[:10], "fps": fps[:10]}


def print_count(cnt: dict) -> None:
    print("COUNT_CMD python app_rag/eval/dev_eval.py --count")
    print("SPLIT datasets/splits/dev_test_split.json dev only")
    for name in ("LEASE", "LOAN", "LAB", "ALL"):
        c = cnt[name]
        print(
            f"COUNT {name} docs={c['docs']} judge={c['judge']} meta_skip={c['meta']} "
            f"toxic={c['toxic']} safe={c['safe']} check={c['check']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--domain", choices=["LEASE", "LOAN", "LAB"], default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    docs = load_docs(args.domain)
    cnt = count_judge(docs)
    print_count(cnt)
    if args.count:
        dest = args.out or (OUT / "dev_eval_count.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(cnt, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", dest)
        return

    llm_ok = ax_up()
    print("AX_UP", llm_ok)
    if not llm_ok:
        print("STOP A.X 8082 응답 없음")
        sys.exit(2)

    index, skipped = get_index()
    corpus_ids = [r["id"] for r in index.records]
    corpus_keys = set()
    for rec in index.records:
        key = canon_from_id(rec["id"])
        if key:
            corpus_keys.add(key)
    print("INDEX_N", len(index.records), "skipped", json.dumps(skipped, ensure_ascii=False))
    print("LEAK_CHECK generate_finding(text, extract_facts(full), hits) only. fields_not_passed", list(LEAK_FIELDS))
    print("LEAK_LINES pipeline.py:82-100 generate.py:77-85 facts.py:119-157 split.py:262-263")

    if args.pilot:
        chosen = []
        seen = set()
        for doc in docs:
            if doc["domain"] in seen:
                continue
            seen.add(doc["domain"])
            chosen.append(doc)
        target_docs = chosen
        tag = "pilot"
    else:
        target_docs = docs
        tag = "full"

    t_all = time.perf_counter()
    all_rows = []
    per_doc = []
    for doc in target_docs:
        t0 = time.perf_counter()
        pack = eval_doc(doc, index, corpus_keys, corpus_ids, llm_ok)
        elapsed = time.perf_counter() - t0
        n = len(pack["rows"])
        avg = (elapsed / n) if n else 0.0
        per_doc.append(
            {
                "domain": doc["domain"],
                "doc_id": doc["doc_id"],
                "n": n,
                "sec": round(elapsed, 2),
                "avg_sec": round(avg, 3),
            }
        )
        print(
            f"DOC {doc['domain']} {doc['doc_id']} n={n} sec={elapsed:.2f} avg_sec/seg={avg:.3f} "
            f"cmd=python app_rag/eval/dev_eval.py --pilot"
        )
        all_rows.extend(pack["rows"])

    wall = time.perf_counter() - t_all
    sys_code_present = any(r.get("sys_codes") for r in all_rows)
    summary = summarize(all_rows, sys_code_present)
    judge_all = cnt["ALL"]["judge"]
    done_n = len(all_rows)
    avg_sec = (wall / done_n) if done_n else 0.0
    est_full_sec = avg_sec * judge_all
    print("WALL_SEC", round(wall, 2), "DONE_SEGS", done_n, "AVG_SEC", round(avg_sec, 3))
    print("EST_FULL_SEC", round(est_full_sec, 1), "EST_FULL_MIN", round(est_full_sec / 60, 1))
    print("OVER_60MIN", est_full_sec > 3600)

    payload = {
        "tag": tag,
        "split": "dev",
        "ax": True,
        "count": cnt,
        "per_doc": per_doc,
        "wall_sec": round(wall, 2),
        "avg_sec": round(avg_sec, 3),
        "est_full_sec": round(est_full_sec, 1),
        "est_full_min": round(est_full_sec / 60, 1),
        "over_60min": est_full_sec > 3600,
        "summary": summary["tables"],
        "codes": summary["codes"],
        "missed": summary["missed"],
        "fps": summary["fps"],
        "rows": all_rows,
        "leak": {
            "not_passed": list(LEAK_FIELDS),
            "lines": {
                "pipeline.search_and_generate": "app_rag/rag/pipeline.py:82-100",
                "generate_finding": "app_rag/rag/generate.py:77-85",
                "facts_for_prompt": "app_rag/rag/facts.py:119-157",
                "judge_segments_skip_meta": "app_rag/rag/split.py:262-263",
                "judge_prompt_keys": "app_rag/prompts/judge.txt:20",
            },
        },
    }
    dest = args.out or (OUT / ("dev_eval_pilot.json" if args.pilot else "dev_eval.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)
    if args.pilot and est_full_sec > 3600:
        print("STOP_ASK 예상 시간이 60분을 넘는다. 설정을 줄이지 않고 멈춘다.")


if __name__ == "__main__":
    main()
