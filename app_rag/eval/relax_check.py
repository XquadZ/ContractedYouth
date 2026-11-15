# -*- coding: utf-8 -*-
"""RELAX_CHECK: 문서 판정 완화 R0/R1/R2. 조항별 jsonl 저장 후 재계산."""
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

from rag.criteria import is_blocking_fact, select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, generate_finding, set_llm_endpoint  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import NEEDS_FACT_STATS, reset_needs_fact_stats, verify_finding  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from metrics import rate, score_pair, summarize_rows, wilson_ci  # noqa: E402
from dev_eval import is_meta  # noqa: E402

RISKY = ("위반", "위험")
K_GRID = [0, 1, 2, 3, 4, 5, 6, 8, 10]

ENDPOINTS = {
    "AX": {
        "url": "http://127.0.0.1:8082/v1/chat/completions",
        "health": "http://127.0.0.1:8082/health",
    },
    "EXAONE": {
        "url": "http://127.0.0.1:8083/v1/chat/completions",
        "health": "http://127.0.0.1:8083/health",
    },
}


def load_lab_docs() -> list[dict]:
    ids = load_split_ids("dev", "LAB", SPLIT_FILE_V2)
    rows = load_jsonl(GOLD["LAB"]["contract"])
    twin_p = clean_twin_path("LAB")
    if twin_p.exists():
        rows = rows + load_jsonl(twin_p)
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
        docs.append({"domain": "LAB", "doc_id": did, "segs": segs})
    return docs


def classify_review_source(verified: dict, verdict: str) -> str | None:
    """확인 필요일 때 1차 출처. 아니면 None 또는 참고용."""
    rs = verified.get("review_sources") or []
    notes = " ".join(str(n) for n in (verified.get("notes") or []))
    if not verified.get("parse_ok", True):
        return "parse_fail"
    if "no_evidence" in rs:
        return "no_evidence"
    if "needs_fact" in rs or "blocking_if" in notes:
        return "needs_fact"
    if "quote_mismatch" in rs or "quote_mismatch" in notes:
        return "quote_mismatch"
    if verdict == "확인 필요":
        if verified.get("ax_verdict") == "확인 필요" or "ax_verdict" in rs:
            return "ax_verdict"
        return "other"
    return None


def run_eval(*, model: str, ax_review_to_ok: bool, out_jsonl: Path) -> dict:
    ep = ENDPOINTS[model]
    set_llm_endpoint(ep["url"], ep["health"])
    if not ax_up():
        raise SystemExit(f"STOP {model} down")
    docs = load_lab_docs()
    index, _ = get_index()
    reset_needs_fact_stats()
    # is_clean_doc: 문서에 toxic 없음 or twin
    tox_by_doc = {}
    for doc in docs:
        tox_by_doc[doc["doc_id"]] = any(s.get("label") == "toxic" for s in doc["segs"])

    rows = []
    t0 = time.perf_counter()
    for doc in docs:
        did = doc["doc_id"]
        is_clean = (not tox_by_doc[did]) or ("-C" in did)
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = "LAB"
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            hits = (index.search(strip_placeholders(text), domain="LAB", title="") or {}).get("hits") or []
            finding = generate_finding(text, facts, hits, use_criteria=True)
            cards = select_cards(text, limit=2)
            verified = verify_finding(
                text,
                hits,
                finding,
                facts,
                needs_fact_mode="cards",
                selected_cards=cards,
                ax_review_to_ok=ax_review_to_ok,
            )
            verdict = verified.get("verdict") or "확인 필요"
            label = seg.get("label") or ""
            nf = verified.get("needs_fact")
            blocking = bool(nf) and is_blocking_fact(nf, cards)
            row = {
                "doc_id": did,
                "segment_id": seg.get("segment_id"),
                "label": label,
                "is_clean_doc": is_clean,
                "verdict": verdict,
                "ax_verdict": verified.get("ax_verdict"),
                "needs_fact": nf,
                "needs_fact_is_blocking_if": blocking if nf else None,
                "review_source": classify_review_source(verified, verdict),
                "review_sources": verified.get("review_sources") or [],
                "notes": verified.get("notes") or [],
                "selected_cards": [c.get("id") for c in cards if c.get("id")],
                "bucket": score_pair(label, verdict),
                "text40": (text.replace("\n", " ")[:40]),
                "ax_review_to_ok": "ax_review_to_ok" in (verified.get("notes") or []),
            }
            rows.append(row)
        print(f"  DOC {did} clean={is_clean} n={sum(1 for r in rows if r['doc_id']==did)}", flush=True)

    wall = time.perf_counter() - t0
    set_llm_endpoint(None, None)
    OUT.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    clause = summarize_rows(rows)
    clause["wall_sec"] = round(wall, 2)
    clause["mean_latency_ms"] = round(wall * 1000 / max(1, len(rows)), 1)
    meta = {
        "model": model,
        "ax_review_to_ok": ax_review_to_ok,
        "n_rows": len(rows),
        "wall_sec": round(wall, 2),
        "clause_summary": clause,
        "needs_fact_stats": dict(NEEDS_FACT_STATS),
        "jsonl": str(out_jsonl),
    }
    return {"meta": meta, "rows": rows}


def load_jsonl_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def counts_as_review_for_doc(row: dict, method: str) -> bool:
    """문서 판정용 '확인 필요' 카운트에 넣을지."""
    if row.get("verdict") != "확인 필요":
        return False
    if method == "R0":
        return True
    # R1: 아래는 빼고 직접 확인할 것으로만
    nf = row.get("needs_fact")
    if nf and row.get("needs_fact_is_blocking_if") is False:
        return False
    src = row.get("review_source")
    if src in ("no_evidence", "quote_mismatch"):
        return False
    # notes에도 quote_mismatch
    notes = " ".join(str(n) for n in (row.get("notes") or []))
    if "quote_mismatch" in notes and src != "needs_fact":
        # if classified as quote_mismatch already handled; if mixed keep conservative
        if src == "quote_mismatch":
            return False
    return True


def doc_headline_from_counts(n_risky: int, n_review: int, k: int) -> str:
    if n_risky >= 1:
        return "고칠 조항 있음"
    if n_review <= k:
        return "큰 문제 없음"
    return "확인할 부분 있음"


def evaluate_docs(rows: list[dict], method: str, k: int) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["doc_id"]].append(r)

    clean_pass = 0
    clean_n = 0
    tox_warn = 0
    tox_n = 0
    misses = []  # toxic docs with 큰 문제 없음
    headlines = {}

    for did, rs in by.items():
        is_clean = bool(rs[0].get("is_clean_doc"))
        n_risky = sum(1 for r in rs if r.get("verdict") in RISKY)
        n_review = sum(1 for r in rs if counts_as_review_for_doc(r, method))
        hl = doc_headline_from_counts(n_risky, n_review, k)
        headlines[did] = {"headline": hl, "n_risky": n_risky, "n_review": n_review, "is_clean": is_clean}
        if is_clean:
            clean_n += 1
            if hl == "큰 문제 없음":
                clean_pass += 1
        else:
            tox_n += 1
            if hl != "큰 문제 없음":
                tox_warn += 1
            else:
                tox_segs = [
                    {
                        "segment_id": r["segment_id"],
                        "verdict": r["verdict"],
                        "ax_verdict": r.get("ax_verdict"),
                        "text40": r.get("text40"),
                    }
                    for r in rs
                    if r.get("label") == "toxic"
                ]
                misses.append({"doc_id": did, "toxic_verdicts": tox_segs})

    return {
        "method": method,
        "K": k,
        "clean_pass": clean_pass,
        "clean_n": clean_n,
        "clean_pass_rate": rate(clean_pass, clean_n),
        "toxic_warn": tox_warn,
        "toxic_n": tox_n,
        "toxic_warn_rate": rate(tox_warn, tox_n),
        "misses": misses,
        "headlines": headlines,
    }


def sweep(rows: list[dict]) -> dict:
    out = {"R0": {}, "R1": {}}
    for method in ("R0", "R1"):
        for k in K_GRID:
            out[method][str(k)] = evaluate_docs(rows, method, k)
    return out


def pick_recommend(sweep_res: dict) -> dict | None:
    """독소 경고율 100% 중 깨끗 통과율 최고 (method, K)."""
    best = None
    best_rate = -1.0
    for method in ("R0", "R1"):
        for k in K_GRID:
            cell = sweep_res[method][str(k)]
            if cell["toxic_n"] == 0:
                continue
            if cell["toxic_warn"] < cell["toxic_n"]:
                continue  # not 100%
            cr = cell["clean_pass"] / cell["clean_n"] if cell["clean_n"] else 0.0
            if cr > best_rate or (
                cr == best_rate and best and (method, k) < (best["method"], best["K"])
            ):
                best_rate = cr
                best = {
                    "method": method,
                    "K": k,
                    "clean_pass_rate": cell["clean_pass_rate"],
                    "toxic_warn_rate": cell["toxic_warn_rate"],
                }
    return best


def clean_remaining_reviews(rows: list[dict]) -> list[dict]:
    """R1 적용 후 깨끗한 문서에 남은 확인 필요."""
    out = []
    for r in rows:
        if not r.get("is_clean_doc"):
            continue
        if not counts_as_review_for_doc(r, "R1"):
            continue
        out.append(
            {
                "doc_id": r["doc_id"],
                "segment_id": r["segment_id"],
                "text40": r.get("text40"),
                "cards": r.get("selected_cards"),
                "review_source": r.get("review_source"),
                "needs_fact": r.get("needs_fact"),
            }
        )
    return out


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def stop_port(port: int) -> None:
    cmd = (
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        f"Select-Object -First 1; if($c -and $c.OwningProcess -gt 0){{ Stop-Process -Id $c.OwningProcess -Force }}"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)


def ensure_exaone_alone() -> None:
    if health(ENDPOINTS["AX"]["health"]):
        stop_port(8082)
        time.sleep(3)
    if health(ENDPOINTS["EXAONE"]["health"]):
        return
    log = (OUT / "start_exaone_relax.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(APP / "start_exaone.py")],
        cwd=str(APP),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(300):
        if health(ENDPOINTS["EXAONE"]["health"]):
            print("EXAONE_UP", flush=True)
            return
        if proc.poll() is not None:
            raise SystemExit("EXAONE start fail")
        time.sleep(2)
    raise SystemExit("EXAONE timeout")


def write_partial_report(tag: str, meta: dict, rows: list[dict], sweep_res: dict, rec: dict | None) -> Path:
    lines = []
    lines.append(f"# RELAX_CHECK — {tag}")
    lines.append("")
    lines.append(f"- model: {meta.get('model')}, ax_review_to_ok={meta.get('ax_review_to_ok')}")
    lines.append(f"- rows: {meta.get('n_rows')}, wall_sec: {meta.get('wall_sec')}")
    lines.append(f"- jsonl: `{meta.get('jsonl')}`")
    lines.append("")
    cs = meta.get("clause_summary") or {}
    lines.append("## 조항 단위 (FIX_ROUND1 대조)")
    lines.append("")
    lines.append("| 지표 | 값 |")
    lines.append("|---|---|")
    for k in ("detect_rate", "warn_capture_rate", "fp_rate", "overwarn_rate"):
        lines.append(f"| {k} | {cs.get(k)} |")
    lines.append("")
    lines.append("## 문서 판정")
    lines.append("")
    lines.append("| 방법 | K | 깨끗 통과 | 독소 경고 | 놓침 doc |")
    lines.append("|---|---|---|---|---|")
    for method in ("R0", "R1"):
        for k in (2,):  # highlight K=2 first; full grid below
            cell = sweep_res[method][str(k)]
            miss = ",".join(m["doc_id"] for m in cell["misses"]) or "—"
            lines.append(
                f"| {method} | {k} | {cell['clean_pass_rate']} | {cell['toxic_warn_rate']} | {miss} |"
            )
    lines.append("")
    lines.append("### K 스윕 (R0 / R1)")
    lines.append("")
    lines.append("| 방법 | K | 깨끗 통과 | 독소 경고 | 놓침 |")
    lines.append("|---|---|---|---|---|")
    for method in ("R0", "R1"):
        for k in K_GRID:
            cell = sweep_res[method][str(k)]
            nmiss = len(cell["misses"])
            lines.append(
                f"| {method} | {k} | {cell['clean_pass_rate']} | {cell['toxic_warn_rate']} | {nmiss} |"
            )
    lines.append("")
    lines.append(f"### 추천 기준: {rec}")
    lines.append("")
    rem = clean_remaining_reviews(rows)
    lines.append(f"## 깨끗 문서 R1 후 남은 확인 필요 ({len(rem)}건)")
    lines.append("")
    for r in rem[:40]:
        lines.append(
            f"- {r['doc_id']} {r['segment_id']} src={r['review_source']} cards={r['cards']} | {r['text40']}"
        )
    if len(rem) > 40:
        lines.append(f"- … +{len(rem)-40}")
    lines.append("")
    # misses detail for R0/R1 K=2
    for method in ("R0", "R1"):
        cell = sweep_res[method]["2"]
        lines.append(f"## 독소 놓침 {method} K=2")
        if not cell["misses"]:
            lines.append("- (없음)")
        for m in cell["misses"]:
            lines.append(f"- **{m['doc_id']}**")
            for t in m["toxic_verdicts"]:
                lines.append(f"  - {t['segment_id']}: {t['verdict']} (ax={t['ax_verdict']}) {t['text40']}")
        lines.append("")
    path = OUT / f"RELAX_CHECK_{tag}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=["Q", "P", "compute"], required=True)
    parser.add_argument("--jsonl", type=Path, default=None)
    args = parser.parse_args()

    if args.run == "Q":
        out = OUT / "relax_Q_rows.jsonl"
        print("RUN Q A.X ax_review_to_ok=True", flush=True)
        pack = run_eval(model="AX", ax_review_to_ok=True, out_jsonl=out)
        rows = pack["rows"]
        sw = sweep(rows)
        rec = pick_recommend(sw)
        meta = pack["meta"]
        # fix mean latency roughly from wall
        if rows:
            meta["clause_summary"]["mean_latency_ms"] = round(meta["wall_sec"] * 1000 / len(rows), 1)
        report = write_partial_report("Q", meta, rows, sw, rec)
        payload = {"meta": meta, "recommend": rec, "R0_K2": sw["R0"]["2"], "R1_K2": sw["R1"]["2"], "sweep": {
            m: {k: {kk: vv for kk, vv in cell.items() if kk != "headlines"} for k, cell in sw[m].items()}
            for m in sw
        }}
        # strip huge headlines from sweep file - already done
        (OUT / "relax_Q_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", out)
        print("WROTE", report)
        print("REC", rec)
        print("R0K2", payload["R0_K2"]["clean_pass_rate"], payload["R0_K2"]["toxic_warn_rate"])
        print("R1K2", payload["R1_K2"]["clean_pass_rate"], payload["R1_K2"]["toxic_warn_rate"])
        return

    if args.run == "P":
        ensure_exaone_alone()
        out = OUT / "relax_P_rows.jsonl"
        print("RUN P EXAONE ax_review_to_ok=False", flush=True)
        pack = run_eval(model="EXAONE", ax_review_to_ok=False, out_jsonl=out)
        rows = pack["rows"]
        sw = sweep(rows)
        rec = pick_recommend(sw)
        meta = pack["meta"]
        if rows:
            meta["clause_summary"]["mean_latency_ms"] = round(meta["wall_sec"] * 1000 / len(rows), 1)
        report = write_partial_report("P", meta, rows, sw, rec)
        payload = {"meta": meta, "recommend": rec, "R0_K2": sw["R0"]["2"], "R1_K2": sw["R1"]["2"], "sweep": {
            m: {k: {kk: vv for kk, vv in cell.items() if kk != "headlines"} for k, cell in sw[m].items()}
            for m in sw
        }}
        (OUT / "relax_P_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", out)
        print("WROTE", report)
        print("EXAONE left UP on 8083", flush=True)
        return

    # compute only
    path = args.jsonl
    rows = load_jsonl_rows(path)
    sw = sweep(rows)
    print(json.dumps({"rec": pick_recommend(sw), "R0K2": sw["R0"]["2"], "R1K2": sw["R1"]["2"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
