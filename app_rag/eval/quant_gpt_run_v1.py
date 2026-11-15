# -*- coding: utf-8 -*-
"""WEEK_FINAL-A: OpenAI GPT를 QUANT와 같은 조건으로 평가. 상한 $15."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import is_blocking_fact, select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import build_judge_prompt, parse_json_output  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.pii import mask_pii  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import NEEDS_FACT_STATS, reset_needs_fact_stats, verify_finding  # noqa: E402
from quant_run import _hit_slim, load_domain_docs  # noqa: E402
from metrics import score_pair  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta  # noqa: E402
from relax_check import classify_review_source  # noqa: E402

COST_CAP_USD = 15.0
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODELS_URL = "https://api.openai.com/v1/models"

# 공식 가격(USD / 1M tokens) — platform.openai.com/docs/pricing 기준
PRICING = {
    "gpt-4o-mini": {"in": 0.15, "out": 0.60, "label": "G1"},
    "gpt-4.1": {"in": 2.00, "out": 8.00, "label": "G2"},
}
G1_ID = "gpt-4o-mini"
G2_ID = "gpt-4.1"

QGPT = OUT / "quant_gpt"
CACHE_DIR = QGPT / "cache"
COST_LOCK = Lock()
COST_STATE = {"usd": 0.0, "in_tok": 0, "out_tok": 0, "calls": 0, "cache_hits": 0}


def _api_key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY missing")
    return key


def list_models() -> list[str]:
    req = urllib.request.Request(
        MODELS_URL,
        headers={"Authorization": f"Bearer {_api_key()}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return sorted(m.get("id") or "" for m in (data.get("data") or []) if m.get("id"))


def safe_model_tag(model_id: str) -> str:
    return model_id.replace("/", "_").replace(":", "_")


def cache_path(model_id: str, prompt_hash: str) -> Path:
    d = CACHE_DIR / safe_model_tag(model_id)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{prompt_hash}.json"


def prompt_hash(model_id: str, user: str) -> str:
    blob = f"{model_id}\n{user}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def add_cost(usage: dict, model_id: str) -> float:
    pin = PRICING.get(model_id, {}).get("in", 0.0)
    pout = PRICING.get(model_id, {}).get("out", 0.0)
    tin = int(usage.get("prompt_tokens") or 0)
    tout = int(usage.get("completion_tokens") or 0)
    usd = tin / 1_000_000 * pin + tout / 1_000_000 * pout
    with COST_LOCK:
        COST_STATE["usd"] += usd
        COST_STATE["in_tok"] += tin
        COST_STATE["out_tok"] += tout
        COST_STATE["calls"] += 1
        total = COST_STATE["usd"]
    return total


def chat_openai(model_id: str, user: str, *, max_tokens: int = 512) -> dict:
    """temperature 0, JSON 강제. 캐시·재시도·비용 누적."""
    ph = prompt_hash(model_id, user)
    cp = cache_path(model_id, ph)
    if cp.exists():
        cached = json.loads(cp.read_text(encoding="utf-8"))
        with COST_LOCK:
            COST_STATE["cache_hits"] += 1
        return cached

    with COST_LOCK:
        if COST_STATE["usd"] >= COST_CAP_USD:
            raise SystemExit(f"COST_CAP reached ${COST_STATE['usd']:.4f}")

    body = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "당신은 계약서 조항 판정기입니다. 반드시 JSON 객체만 출력하세요.",
            },
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(5):
        req = urllib.request.Request(
            OPENAI_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
            js = json.loads(raw)
            msg = (js.get("choices") or [{}])[0].get("message") or {}
            content = msg.get("content") or ""
            usage = js.get("usage") or {}
            total = add_cost(usage, model_id)
            if total >= COST_CAP_USD:
                # 이번 호출은 저장하되 이후 중단 신호
                pass
            out = {
                "content": content,
                "error": None,
                "usage": usage,
                "model": model_id,
                "prompt_hash": ph,
                "cached": False,
            }
            cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            return out
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            last_err = f"HTTP {exc.code}: {detail}"
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** attempt))
                continue
            break
        except Exception as exc:
            last_err = str(exc)
            time.sleep(min(30, 2 ** attempt))
    return {"content": "", "error": last_err, "usage": {}, "model": model_id, "prompt_hash": ph, "cached": False}


def finding_from_openai(clause_masked: str, facts: dict, hits: list[dict], *, model_id: str) -> dict:
    user, cards, hits2 = build_judge_prompt(clause_masked, facts, hits, use_criteria=True)
    # 프롬프트 전체도 한 번 더 마스킹(근거 텍스트 안전)
    user_m, _ = mask_pii(user)
    resp = chat_openai(model_id, user_m, max_tokens=512)
    parsed, ok = parse_json_output(resp.get("content") or "")
    row = {
        "verdict": "확인 필요",
        "contract_quote": "",
        "gap": "애매",
        "why": "",
        "evidence": [],
        "suggestion": "",
        "needs_fact": None,
        "parse_ok": False,
        "raw": resp.get("content") or "",
        "error": resp.get("error"),
        "selected_cards": [c.get("id") for c in cards],
        "hits_for_verify": hits2,
        "prompt_chars": len(user_m),
        "prompt_hash": resp.get("prompt_hash"),
        "usage": resp.get("usage") or {},
        "cached": bool(resp.get("cached")),
    }
    if not ok or not isinstance(parsed, dict):
        row["why"] = "모델 출력을 JSON으로 읽지 못했다."
        return row
    verdict = str(parsed.get("verdict") or "확인 필요").strip()
    if verdict not in ("위반", "위험", "확인 필요", "문제 없음"):
        verdict = "확인 필요"
    evidence = []
    for item in parsed.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if eid:
            evidence.append({"id": eid, "quote": quote})
    needs = parsed.get("needs_fact")
    if needs in ("", "null", "None"):
        needs = None
    elif needs is not None:
        needs = str(needs).strip() or None
    row.update(
        {
            "verdict": verdict,
            "contract_quote": str(parsed.get("contract_quote") or "").strip(),
            "gap": str(parsed.get("gap") or "").strip(),
            "why": str(parsed.get("why") or "").strip(),
            "evidence": evidence,
            "suggestion": str(parsed.get("suggestion") or "").strip(),
            "needs_fact": needs,
            "parse_ok": True,
            "error": None,
        }
    )
    return row


def estimate_cost(n_clauses: int, avg_in_tok: int, avg_out_tok: int = 200) -> dict:
    out = {}
    for mid, pr in PRICING.items():
        usd = n_clauses * (avg_in_tok / 1e6 * pr["in"] + avg_out_tok / 1e6 * pr["out"])
        out[mid] = {"usd": round(usd, 4), "in_tok": n_clauses * avg_in_tok, "out_tok": n_clauses * avg_out_tok}
    out["total"] = round(sum(v["usd"] for v in out.values() if isinstance(v, dict) and "usd" in v), 4)
    return out


def run_domain(model_id: str, domain: str, *, workers: int = 4, domains_filter: set[str] | None = None) -> dict:
    if domains_filter and domain not in domains_filter:
        return {"skipped": True}
    tag = safe_model_tag(model_id)
    out_jsonl = QGPT / f"{tag}_{domain}_rows.jsonl"
    docs = load_domain_docs(domain)
    index, _ = get_index()
    reset_needs_fact_stats()
    label = PRICING.get(model_id, {}).get("label", model_id)

    # 작업 목록 준비 (검색은 로컬, LLM만 병렬)
    jobs = []
    mask_counts_total = {"rrn": 0, "phone": 0, "account": 0, "email": 0, "address": 0, "name": 0}
    mask_piece_changes = 0
    for doc in docs:
        did = doc["doc_id"]
        labs = {s.get("label") for s in doc["segs"]}
        is_clean = ("toxic" not in labs) and ("check" not in labs)
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = domain
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            masked, mc = mask_pii(text)
            for k, v in mc.items():
                mask_counts_total[k] = mask_counts_total.get(k, 0) + v
            mask_piece_changes += sum(mc.values())
            law = doc["law_map"].get(seg.get("segment_id") or "", {})
            hits_raw = (index.search(strip_placeholders(text), domain=domain, title="") or {}).get("hits") or []
            jobs.append(
                {
                    "domain": domain,
                    "doc_id": did,
                    "seg": seg,
                    "law": law,
                    "facts": facts,
                    "text": text,
                    "masked": masked,
                    "hits_raw": hits_raw,
                    "is_clean": is_clean,
                    "is_clean_twin": "-C" in did,
                }
            )

    rows: list[dict | None] = [None] * len(jobs)
    t0 = time.perf_counter()

    def _one(i: int, job: dict) -> tuple[int, dict]:
        with COST_LOCK:
            if COST_STATE["usd"] >= COST_CAP_USD:
                raise RuntimeError("COST_CAP")
        t1 = time.perf_counter()
        finding = finding_from_openai(job["masked"], job["facts"], job["hits_raw"], model_id=model_id)
        hits_for_v = finding.get("hits_for_verify") or job["hits_raw"]
        hits_slim = [_hit_slim(h, i + 1) for i, h in enumerate(hits_for_v)]
        cards = select_cards(job["text"], limit=2, domain=domain)
        verified = verify_finding(
            job["text"],
            hits_for_v,
            finding,
            job["facts"],
            needs_fact_mode="cards",
            selected_cards=cards,
            ax_review_to_ok=False,
        )
        ms = (time.perf_counter() - t1) * 1000
        verdict = verified.get("verdict") or "확인 필요"
        label_seg = job["seg"].get("label") or ""
        nf = verified.get("needs_fact")
        blocking = bool(nf) and is_blocking_fact(nf, cards) if cards else False
        notes = verified.get("notes") or []
        rs = verified.get("review_sources") or []
        row = {
            "domain": domain,
            "model": label,
            "model_id": model_id,
            "doc_id": job["doc_id"],
            "segment_id": job["seg"].get("segment_id"),
            "std_item": job["seg"].get("std_item") or job["law"].get("std_item"),
            "label": label_seg,
            "gold_codes": gold_codes(job["seg"], job["law"]),
            "gold_provisions": gold_provisions(job["seg"], job["law"]),
            "is_clean_doc": job["is_clean"],
            "is_clean_twin": job["is_clean_twin"],
            "text": job["text"],
            "text_masked": job["masked"],
            "finding": {
                "verdict": finding.get("verdict"),
                "contract_quote": finding.get("contract_quote"),
                "evidence": finding.get("evidence") or [],
                "needs_fact": finding.get("needs_fact"),
                "why": finding.get("why"),
                "suggestion": finding.get("suggestion"),
                "gap": finding.get("gap"),
                "parse_ok": finding.get("parse_ok"),
                "raw": finding.get("raw"),
                "error": finding.get("error"),
                "selected_cards": finding.get("selected_cards") or [],
                "usage": finding.get("usage") or {},
                "prompt_hash": finding.get("prompt_hash"),
            },
            "hits": hits_slim,
            "selected_cards": [c.get("id") for c in cards if c.get("id")],
            "selected_cards_full": [
                {
                    "id": c.get("id"),
                    "blocking_if": c.get("blocking_if"),
                    "violation": c.get("violation") or [],
                    "safe": c.get("safe") or [],
                }
                for c in cards
            ],
            "facts": job["facts"],
            "verdict": verdict,
            "ax_verdict": verified.get("ax_verdict"),
            "review_source": classify_review_source(verified, verdict),
            "review_sources": rs,
            "notes": notes,
            "needs_fact": nf,
            "needs_fact_action": verified.get("needs_fact_action"),
            "needs_fact_is_blocking_if": blocking if nf else None,
            "dropped_ids": verified.get("dropped_ids") or [],
            "quote_mismatch": "quote_mismatch" in rs or any("quote_mismatch" in str(n) for n in notes),
            "parse_ok": bool(verified.get("parse_ok")),
            "evidence_final": verified.get("evidence") or [],
            "rule": verified.get("rule") or {},
            "doc_question": verified.get("doc_question"),
            "latency_ms": round(ms, 1),
            "bucket": score_pair(label_seg, verdict),
            "ax_review_to_ok_run": False,
        }
        return i, row

    print(f"START {label}/{model_id} {domain} jobs={len(jobs)} workers={workers}", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_one, i, job) for i, job in enumerate(jobs)]
            done = 0
            for fut in as_completed(futs):
                i, row = fut.result()
                rows[i] = row
                done += 1
                if done % 25 == 0 or done == len(jobs):
                    with COST_LOCK:
                        usd = COST_STATE["usd"]
                    print(f"  progress {domain} {done}/{len(jobs)} cost=${usd:.4f}", flush=True)
                    if usd >= COST_CAP_USD:
                        raise SystemExit(f"COST_CAP during {domain}")
    except RuntimeError as exc:
        if "COST_CAP" in str(exc):
            raise SystemExit(f"COST_CAP during {domain}") from exc
        raise

    wall = time.perf_counter() - t0
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            if r is not None:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with COST_LOCK:
        cost_snap = dict(COST_STATE)
    meta = {
        "model": label,
        "model_id": model_id,
        "model_label": model_id,
        "domain": domain,
        "ax_review_to_ok": False,
        "n_rows": sum(1 for r in rows if r is not None),
        "wall_sec": round(wall, 2),
        "mean_latency_ms": round(wall * 1000 / max(1, sum(1 for r in rows if r is not None)), 1),
        "needs_fact_stats": dict(NEEDS_FACT_STATS),
        "jsonl": str(out_jsonl),
        "mask_counts": mask_counts_total,
        "mask_piece_changes": mask_piece_changes,
        "cost_usd_cumulative": round(cost_snap["usd"], 6),
        "tokens_in_cumulative": cost_snap["in_tok"],
        "tokens_out_cumulative": cost_snap["out_tok"],
        "cache_hits_cumulative": cost_snap["cache_hits"],
        "pricing_per_1m": PRICING.get(model_id),
    }
    out_jsonl.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", out_jsonl, "rows=", meta["n_rows"], "wall=", meta["wall_sec"], flush=True)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["estimate", "run", "list"], default="run")
    parser.add_argument("--models", default=f"{G1_ID},{G2_ID}")
    parser.add_argument("--domains", default="LAB,LEASE,LOAN")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    QGPT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if args.phase == "list":
        ids = list_models()
        pick = [x for x in ids if any(k in x for k in ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4", "mini"))]
        print("\n".join(pick or ids[:50]))
        return

    # 재현 메타
    import hashlib

    card_hashes = {}
    for name in ("LAB_cards.yaml", "LEASE_cards.yaml", "LOAN_cards.yaml"):
        p = APP / "criteria" / name
        if p.exists():
            card_hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    judge_p = APP / "prompts" / "judge.txt"
    judge_hash = hashlib.sha256(judge_p.read_bytes()).hexdigest()[:16] if judge_p.exists() else None

    # 조항 수·토큰 추정
    from rag.generate import build_judge_prompt as bjp

    index, _ = get_index()
    n = 0
    total_chars = 0
    for d in ["LAB", "LEASE", "LOAN"]:
        for doc in load_domain_docs(d):
            full = "\n".join(s.get("text") or "" for s in doc["segs"])
            facts = extract_facts(full)
            facts["domain"] = d
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                text = seg.get("text") or ""
                hits = (index.search(strip_placeholders(text), domain=d, title="") or {}).get("hits") or []
                user, _, _ = bjp(text, facts, hits, use_criteria=True)
                total_chars += len(user)
                n += 1
    avg_chars = total_chars / max(1, n)
    # 한국어 보수 추정: chars/2
    avg_in_tok = int(avg_chars / 2)
    est = estimate_cost(n, avg_in_tok, 200)
    plan = {
        "g1": G1_ID,
        "g2": G2_ID,
        "pricing": PRICING,
        "n_clauses": n,
        "avg_prompt_chars": round(avg_chars, 1),
        "avg_in_tok_est": avg_in_tok,
        "cost_estimate_usd": est,
        "cost_cap_usd": COST_CAP_USD,
        "card_hashes": card_hashes,
        "judge_hash": judge_hash,
        "aihub_in_eval_data": False,
        "aihub_note": "gold·corpus 텍스트에 AI Hub 문자열 0건",
        "settings": {"temperature": 0, "max_tokens": 512, "response_format": "json_object", "workers": args.workers},
    }
    (QGPT / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PLAN", json.dumps(plan["cost_estimate_usd"], ensure_ascii=False), flush=True)
    if est["total"] > COST_CAP_USD:
        # G2를 LAB만으로 축소
        print("EST over cap → shrink G2 to LAB only", flush=True)
        plan["g2_domains"] = ["LAB"]
        plan["g2_shrink_reason"] = "estimate over $15"
    else:
        plan["g2_domains"] = ["LAB", "LEASE", "LOAN"]
    (QGPT / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.phase == "estimate":
        print("estimate_only", flush=True)
        return

    # 모델 존재 확인
    try:
        available = set(list_models())
    except Exception as exc:
        print("WARN models list fail", exc, flush=True)
        available = {G1_ID, G2_ID}
    for mid in (G1_ID, G2_ID):
        if mid not in available:
            # dated variants
            alts = [x for x in available if x.startswith(mid)]
            if not alts:
                raise SystemExit(f"model not available: {mid}")
            print(f"WARN {mid} exact missing, using as-is (API may resolve)", flush=True)

    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    metas = {}
    for mid in models:
        doms = domains
        if mid == G2_ID:
            doms = plan.get("g2_domains") or domains
        for d in doms:
            if COST_STATE["usd"] >= COST_CAP_USD:
                raise SystemExit(f"STOP cost cap ${COST_STATE['usd']:.4f}")
            metas[f"{mid}_{d}"] = run_domain(mid, d, workers=min(4, max(1, args.workers)))
    with COST_LOCK:
        final_cost = dict(COST_STATE)
    summary = {"metas": metas, "cost": final_cost, "plan": plan}
    (QGPT / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE cost=$%.4f calls=%d cache=%d" % (final_cost["usd"], final_cost["calls"], final_cost["cache_hits"]), flush=True)


if __name__ == "__main__":
    main()
