# -*- coding: utf-8 -*-
"""FAIR_RERUN GPT. luna 하나만. gpt-4.1·gpt-4o-mini 호출 금지. 상한 $1.0.

--phase discover  모델 목록과 가격 페이지 저장. 완성 호출 없음.
--phase pilot     중립 20조각 일반 요청, 비용 추정.
--phase batch     나머지를 Batch로. 2시간이면 취소 후 일반 요청.
--phase materialize  캐시로 행 파일을 만든다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache, is_blocking_fact  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import build_judge_prompt, parse_json_output  # noqa: E402
from rag.pii import mask_pii  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import reset_needs_fact_stats, verify_finding  # noqa: E402
from quant_run import _hit_slim, load_domain_docs  # noqa: E402
from metrics import score_pair  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta  # noqa: E402
from relax_check import classify_review_source  # noqa: E402
from fair_common import COST_CAP_USD, DOMAINS, QFAIR, code_hashes, load_hash  # noqa: E402

CHAT_URL = "https://api.openai.com/v1/chat/completions"
MODELS_URL = "https://api.openai.com/v1/models"
FILES_URL = "https://api.openai.com/v1/files"
BATCH_URL = "https://api.openai.com/v1/batches"
PRICING_URL = "https://openai.com/api/pricing"
CACHE = QFAIR / "cache"
FORBIDDEN = ("gpt-4.1", "gpt-4o", "gpt-4o-mini")


def _key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY missing")
    return key


def _req(url: str, data: bytes | None = None, headers: dict | None = None, method: str | None = None) -> dict:
    hdr = {"Authorization": f"Bearer {_key()}"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _assert_luna(model_id: str) -> None:
    low = model_id.lower()
    if "luna" not in low or "pro" in low:
        raise SystemExit(f"not a non-pro luna model: {model_id}")
    for bad in FORBIDDEN:
        if bad in low:
            raise SystemExit(f"forbidden model {model_id}")


def list_models() -> list[str]:
    data = _req(MODELS_URL, method="GET")
    return sorted(m.get("id") or "" for m in (data.get("data") or []) if m.get("id"))


def discover() -> None:
    QFAIR.mkdir(parents=True, exist_ok=True)
    ids = list_models()
    luna = [i for i in ids if "luna" in i.lower() and "pro" not in i.lower()]
    (QFAIR / "openai_model_ids.json").write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
    page = ""
    try:
        req = urllib.request.Request(PRICING_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        page = f"FETCH_FAIL {exc}"
    (QFAIR / "pricing_page.html").write_text(page, encoding="utf-8")
    payload = {"luna_candidates": luna, "n_models": len(ids), "pricing_chars": len(page), "pricing_url": PRICING_URL}
    (QFAIR / "gpt_discover.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DISCOVER luna", luna, "models", len(ids), "pricing_chars", len(page), flush=True)


def _price() -> dict:
    path = QFAIR / "luna_price.json"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    price = json.loads(path.read_text(encoding="utf-8"))
    _assert_luna(price["model_id"])
    for k in ("in", "out", "batch_in", "batch_out"):
        price[k] = float(price[k])
    return price


def _style() -> dict:
    return json.loads((QFAIR / "gpt_style.json").read_text(encoding="utf-8"))


def _body(model_id: str, user: str, extra: dict) -> dict:
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }
    body.update(extra)
    return body


def _variants(model_id: str, user: str) -> list[dict]:
    efforts = ("none", "minimal", "low")
    out = []
    for effort in efforts:
        out.append(_body(model_id, user, {"temperature": 0, "max_tokens": 512, "reasoning_effort": effort}))
    for effort in efforts:
        out.append(_body(model_id, user, {"max_completion_tokens": 512, "reasoning_effort": effort}))
    out.append(_body(model_id, user, {"max_completion_tokens": 512}))
    return out


def _req_hash(body: dict) -> str:
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _cache_file(digest: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"{digest}.json"


def _usage_tokens(usage: dict) -> tuple[int, int, int]:
    tin = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    tout = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    reason = int(details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
    return tin, tout, reason


def _usd(usage: dict, price: dict, *, batch: bool) -> float:
    tin, tout, _reason = _usage_tokens(usage)
    pin = price["batch_in"] if batch else price["in"]
    pout = price["batch_out"] if batch else price["out"]
    return tin / 1_000_000 * pin + tout / 1_000_000 * pout


def spent() -> float:
    total = 0.0
    if not CACHE.exists():
        return 0.0
    for path in CACHE.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        total += float(rec.get("usd") or 0.0)
    return total


def _post_chat(body: dict) -> tuple[dict | None, str | None, int]:
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(3):
        req = urllib.request.Request(
            CHAT_URL,
            data=data,
            headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8")), None, resp.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            last = f"HTTP {exc.code}: {detail}"
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(min(20, 2 ** attempt))
                continue
            return None, last, exc.code
        except Exception as exc:
            last = str(exc)
            if attempt < 2:
                time.sleep(min(20, 2 ** attempt))
                continue
            return None, last, 0
    return None, last, 0


def _record(body: dict, js: dict, price: dict, *, batch: bool, latency_ms: float | None) -> dict:
    digest = _req_hash(body)
    choice = (js.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = js.get("usage") or {}
    rec = {
        "content": msg.get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "usage": usage,
        "usd": _usd(usage, price, batch=batch),
        "batch": batch,
        "model": body.get("model"),
        "latency_ms": latency_ms,
        "error": None,
        "request_hash": digest,
    }
    _cache_file(digest).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def _load_cached(body: dict) -> dict | None:
    path = _cache_file(_req_hash(body))
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_jobs() -> list[dict]:
    index, _skipped = get_index()
    jobs = []
    n = 0
    for domain in DOMAINS:
        for doc in load_domain_docs(domain):
            full = "\n".join(s.get("text") or "" for s in doc["segs"])
            full_m, _ = mask_pii(full)
            facts = extract_facts(full_m)
            facts["domain"] = domain
            labs = {s.get("label") for s in doc["segs"]}
            is_clean = ("toxic" not in labs) and ("check" not in labs)
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                raw = seg.get("text") or ""
                text_m, _mc = mask_pii(raw)
                hits_raw = (index.search(strip_placeholders(text_m), domain=domain, title="") or {}).get("hits") or []
                law = doc["law_map"].get(seg.get("segment_id") or "", {})
                base = {
                    "domain": domain,
                    "doc_id": doc["doc_id"],
                    "segment_id": seg.get("segment_id"),
                    "label": seg.get("label") or "",
                    "std_item": seg.get("std_item") or law.get("std_item"),
                    "gold_codes": gold_codes(seg, law),
                    "gold_provisions": gold_provisions(seg, law),
                    "is_clean": is_clean,
                    "is_clean_twin": "-C" in doc["doc_id"],
                    "text": text_m,
                    "facts": facts,
                    "hits_raw": hits_raw,
                }
                for ver in ("neutral", "tuned"):
                    os.environ["CARDS_VERSION"] = ver
                    clear_cards_cache()
                    user, cards, hits2 = build_judge_prompt(text_m, facts, hits_raw, use_criteria=True)
                    jobs.append(
                        {
                            **base,
                            "version": ver,
                            "user": user,
                            "user_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                            "cards": cards,
                            "hits2": hits2,
                        }
                    )
                n += 1
                if n % 100 == 0:
                    print("JOBS", n, flush=True)
    path = QFAIR / "jobs.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    print("WROTE", path, "jobs", len(jobs), flush=True)
    return jobs


def _load_jobs() -> list[dict]:
    path = QFAIR / "jobs.jsonl"
    jobs = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                jobs.append(json.loads(line))
    return jobs


def _check_hashes(jobs: list[dict]) -> None:
    after = load_hash("after")
    amap = {
        (r["doc_id"], r["segment_id"], ver): r[f"{ver}_sha256"]
        for r in after["items"]
        for ver in ("neutral", "tuned")
    }
    bad = 0
    for job in jobs:
        key = (job["doc_id"], job["segment_id"], job["version"])
        if amap.get(key) != job["user_sha256"]:
            bad += 1
    if bad:
        raise SystemExit(f"PROMPT_HASH_MISMATCH {bad}")
    if "JSON" not in jobs[0]["user"]:
        raise SystemExit("prompt has no JSON word")
    print("PROMPT_HASH_OK", len(jobs), flush=True)


def _pilot_sample(jobs: list[dict]) -> list[dict]:
    buckets = {d: [j for j in jobs if j["version"] == "neutral" and j["domain"] == d] for d in DOMAINS}
    want = {"LAB": 7, "LEASE": 7, "LOAN": 6}
    picked = []
    for domain, k in want.items():
        rows = buckets[domain]
        step = len(rows) / k
        picked.extend(rows[int(i * step)] for i in range(k))
    return picked


def _extra_from_body(body: dict) -> dict:
    skip = {"model", "messages", "response_format"}
    return {k: v for k, v in body.items() if k not in skip}


def pilot() -> None:
    price = _price()
    model_id = price["model_id"]
    jobs = build_jobs()
    _check_hashes(jobs)
    sample = _pilot_sample(jobs)
    print("PILOT", len(sample), "spent", round(spent(), 6), flush=True)
    style = None
    rows_stat = []
    for idx, job in enumerate(sample):
        if spent() >= COST_CAP_USD:
            print("STOP_CAP before pilot", idx, flush=True)
            break
        if style is None:
            locked = None
            errors = []
            for body in _variants(model_id, job["user"]):
                _assert_luna(body["model"])
                t1 = time.perf_counter()
                js, err, code = _post_chat(body)
                ms = (time.perf_counter() - t1) * 1000
                if js is None:
                    errors.append({"code": code, "error": err, "keys": sorted(_extra_from_body(body))})
                    continue
                _record(body, js, price, batch=False, latency_ms=ms)
                locked = _extra_from_body(body)
                (QFAIR / "gpt_style.json").write_text(
                    json.dumps({"extra": locked, "probe_errors": errors}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                style = locked
                print("STYLE", locked, "ms", round(ms, 1), "spent", round(spent(), 6), flush=True)
                break
            if style is None:
                (QFAIR / "gpt_style.json").write_text(
                    json.dumps({"extra": None, "probe_errors": errors}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                raise SystemExit("STYLE_LOCK_FAILED")
            rec = _load_cached(_body(model_id, job["user"], style))
        else:
            body = _body(model_id, job["user"], style)
            rec = _load_cached(body)
            if rec is None:
                t1 = time.perf_counter()
                js, err, code = _post_chat(body)
                ms = (time.perf_counter() - t1) * 1000
                if js is None:
                    print("PILOT_FAIL", idx, code, err, flush=True)
                    continue
                rec = _record(body, js, price, batch=False, latency_ms=ms)
        usage = rec.get("usage") or {}
        tin, tout, reason = _usage_tokens(usage)
        rows_stat.append(
            {
                "domain": job["domain"],
                "doc_id": job["doc_id"],
                "segment_id": job["segment_id"],
                "in": tin,
                "out": tout,
                "reasoning": reason,
                "usd": rec.get("usd"),
                "latency_ms": rec.get("latency_ms"),
                "finish_reason": rec.get("finish_reason"),
            }
        )
        print(
            f"PILOT {idx + 1}/{len(sample)} {job['domain']} in={tin} out={tout} reason={reason} ${spent():.4f}",
            flush=True,
        )
    n_all = len(jobs)
    n_done = len(rows_stat)
    if not rows_stat:
        raise SystemExit("PILOT_EMPTY")
    avg_in = sum(r["in"] for r in rows_stat) / n_done
    avg_out = sum(r["out"] for r in rows_stat) / n_done
    avg_reason = sum(r["reasoning"] for r in rows_stat) / n_done
    avg_ms = sum(float(r["latency_ms"] or 0) for r in rows_stat) / n_done
    remain = n_all - n_done
    # 캐시에 있는 시범분은 본 실행에서 다시 보내지 않는다.
    est_batch = remain * (avg_in / 1e6 * price["batch_in"] + avg_out / 1e6 * price["batch_out"])
    est_regular = remain * (avg_in / 1e6 * price["in"] + avg_out / 1e6 * price["out"])
    est_total_batch = spent() + est_batch
    summary = {
        "n_pilot": n_done,
        "n_all": n_all,
        "avg_in": avg_in,
        "avg_out": avg_out,
        "avg_reasoning": avg_reason,
        "avg_latency_ms": avg_ms,
        "spent_usd": spent(),
        "est_remain_batch_usd": est_batch,
        "est_remain_regular_usd": est_regular,
        "est_total_if_batch_usd": est_total_batch,
        "over_cap": est_total_batch > COST_CAP_USD,
        "cap": COST_CAP_USD,
        "rows": rows_stat,
        "price": price,
    }
    (QFAIR / "gpt_pilot.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "ESTIMATE",
        json.dumps({k: summary[k] for k in ("n_pilot", "avg_in", "avg_out", "avg_reasoning", "spent_usd", "est_total_if_batch_usd", "over_cap")}, ensure_ascii=False),
        flush=True,
    )


def _pilot_mean_ms() -> float:
    summary = json.loads((QFAIR / "gpt_pilot.json").read_text(encoding="utf-8"))
    return float(summary.get("avg_latency_ms") or 0.0)


def _upload_batch(jsonl_path: Path) -> str:
    boundary = "----fair" + uuid.uuid4().hex
    file_bytes = jsonl_path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
        f"batch\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="fair_batch.jsonl"\r\n'
        f"Content-Type: application/jsonl\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    data = head + file_bytes + tail
    req = urllib.request.Request(
        FILES_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        js = json.loads(resp.read().decode("utf-8"))
    return js["id"]


def _batch_create(file_id: str) -> dict:
    body = {"input_file_id": file_id, "endpoint": "/v1/chat/completions", "completion_window": "24h"}
    return _req(BATCH_URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")


def _batch_get(batch_id: str) -> dict:
    return _req(f"{BATCH_URL}/{batch_id}", method="GET")


def _batch_cancel(batch_id: str) -> dict:
    return _req(f"{BATCH_URL}/{batch_id}/cancel", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")


def _download_file(file_id: str, dest: Path) -> None:
    req = urllib.request.Request(
        f"https://api.openai.com/v1/files/{file_id}/content",
        headers={"Authorization": f"Bearer {_key()}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def batch_submit() -> None:
    price = _price()
    summary = json.loads((QFAIR / "gpt_pilot.json").read_text(encoding="utf-8"))
    if summary.get("over_cap"):
        (QFAIR / "gpt_skipped.json").write_text(
            json.dumps({"reason": "estimate_over_cap", "estimate": summary["est_total_if_batch_usd"]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("SKIP_BATCH estimate", summary["est_total_if_batch_usd"], flush=True)
        return
    style = _style()["extra"]
    if not style and style != {}:
        raise SystemExit("no style")
    jobs = _load_jobs()
    lines = []
    id_map = {}
    for job in jobs:
        body = _body(price["model_id"], job["user"], style)
        _assert_luna(body["model"])
        if _load_cached(body):
            continue
        digest = _req_hash(body)
        cid = digest[:48]
        id_map[cid] = {"request_hash": digest, "doc_id": job["doc_id"], "segment_id": job["segment_id"], "version": job["version"], "domain": job["domain"]}
        lines.append({"custom_id": cid, "method": "POST", "url": "/v1/chat/completions", "body": body})
    jsonl = QFAIR / "fair_batch_input.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    (QFAIR / "fair_batch_map.json").write_text(json.dumps(id_map, ensure_ascii=False), encoding="utf-8")
    print("BATCH_LINES", len(lines), "cached_skip", len(jobs) - len(lines), flush=True)
    if not lines:
        print("BATCH_NOTHING_TO_SEND", flush=True)
        return
    last_err = None
    created = None
    for attempt in range(2):
        try:
            file_id = _upload_batch(jsonl)
            created = _batch_create(file_id)
            last_err = None
            break
        except Exception as exc:
            last_err = str(exc)[:800]
            print("BATCH_SUBMIT_FAIL", attempt + 1, last_err, flush=True)
            time.sleep(3)
    if created is None:
        (QFAIR / "gpt_batch_error.json").write_text(
            json.dumps({"error": last_err, "attempts": 2}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("BATCH_SKIP", last_err, flush=True)
        return
    (QFAIR / "gpt_batch.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BATCH_ID", created.get("id"), "status", created.get("status"), flush=True)


def _ingest_output(path: Path, price: dict) -> int:
    style = _style()["extra"]
    jobs = _load_jobs()
    by_hash = {}
    for job in jobs:
        body = _body(price["model_id"], job["user"], style)
        by_hash[_req_hash(body)] = body
    id_map = json.loads((QFAIR / "fair_batch_map.json").read_text(encoding="utf-8"))
    n = 0
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            cid = rec.get("custom_id")
            info = id_map.get(cid) or {}
            body = by_hash.get(info.get("request_hash"))
            resp = rec.get("response") or {}
            js = resp.get("body") or {}
            if resp.get("status_code") != 200 or not js:
                continue
            if body is None:
                continue
            _record(body, js, price, batch=True, latency_ms=None)
            n += 1
    return n


def batch_wait() -> None:
    path = QFAIR / "gpt_batch.json"
    if not path.exists():
        print("NO_BATCH", flush=True)
        return
    created = json.loads(path.read_text(encoding="utf-8"))
    batch_id = created.get("id")
    if not batch_id:
        print("NO_BATCH_ID", flush=True)
        return
    price = _price()
    deadline = time.time() + 7200
    status = created
    timed_out = False
    while time.time() < deadline:
        status = _batch_get(batch_id)
        st = status.get("status")
        print("BATCH_STATUS", st, "counts", status.get("request_counts"), flush=True)
        if st in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(30)
    else:
        timed_out = True
        print("BATCH_TIMEOUT cancel", flush=True)
        try:
            status = _batch_cancel(batch_id)
        except Exception as exc:
            print("CANCEL_FAIL", exc, flush=True)
        time.sleep(10)
        status = _batch_get(batch_id)
    (QFAIR / "gpt_batch_final.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    out_id = status.get("output_file_id")
    err_id = status.get("error_file_id")
    if out_id:
        dest = QFAIR / "fair_batch_output.jsonl"
        _download_file(out_id, dest)
        n = _ingest_output(dest, price)
        print("BATCH_INGEST", n, "spent", round(spent(), 6), flush=True)
    if err_id:
        _download_file(err_id, QFAIR / "fair_batch_errors.jsonl")
    if timed_out or status.get("status") != "completed":
        _regular_remaining(price, reason="batch_incomplete")


def _regular_remaining(price: dict, *, reason: str) -> None:
    style = _style()["extra"]
    jobs = _load_jobs()
    sent = 0
    for job in jobs:
        if spent() >= COST_CAP_USD:
            print("STOP_CAP regular", "spent", round(spent(), 6), flush=True)
            break
        body = _body(price["model_id"], job["user"], style)
        if _load_cached(body):
            continue
        t1 = time.perf_counter()
        js, err, code = _post_chat(body)
        ms = (time.perf_counter() - t1) * 1000
        if js is None:
            print("REGULAR_FAIL", code, (err or "")[:200], flush=True)
            continue
        _record(body, js, price, batch=False, latency_ms=ms)
        sent += 1
        if sent % 25 == 0:
            print("REGULAR", sent, "spent", round(spent(), 6), flush=True)
    note = {"reason": reason, "regular_sent": sent, "spent": spent()}
    (QFAIR / "gpt_regular_fallback.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REGULAR_DONE", note, flush=True)


def _finding(content: str, error: str | None, cards: list, hits2: list) -> dict:
    parsed, ok = parse_json_output(content or "")
    row = {
        "verdict": "확인 필요",
        "contract_quote": "",
        "gap": "애매",
        "why": "",
        "evidence": [],
        "suggestion": "",
        "needs_fact": None,
        "parse_ok": False,
        "raw": content or "",
        "error": error,
        "selected_cards": [c.get("id") for c in cards],
        "hits_for_verify": hits2,
    }
    if not ok or not isinstance(parsed, dict):
        row["why"] = "모델 출력을 JSON으로 읽지 못했다."
        return row
    verdict = str(parsed.get("verdict") or "확인 필요").strip()
    if verdict not in ("위반", "위험", "확인 필요", "문제 없음"):
        verdict = "확인 필요"
    evidence = []
    for item in parsed.get("evidence") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            evidence.append({"id": str(item.get("id") or "").strip(), "quote": str(item.get("quote") or "").strip()})
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


def materialize() -> None:
    price = _price()
    style = _style().get("extra") or {}
    jobs = _load_jobs()
    mean_ms = _pilot_mean_ms()
    hashes = code_hashes()
    grouped: dict[tuple[str, str], list] = {}
    expected: dict[tuple[str, str], int] = {}
    for job in jobs:
        key = (job["version"], job["domain"])
        expected[key] = expected.get(key, 0) + 1
        body = _body(price["model_id"], job["user"], style)
        rec = _load_cached(body)
        if rec is None:
            continue
        os.environ["CARDS_VERSION"] = job["version"]
        clear_cards_cache()
        reset_needs_fact_stats()
        finding = _finding(rec.get("content") or "", rec.get("error"), job["cards"], job["hits2"])
        finding["finish_reason"] = rec.get("finish_reason")
        finding["usage"] = rec.get("usage") or {}
        finding["prompt_sha256"] = job["user_sha256"]
        hits_for_v = finding.get("hits_for_verify") or job["hits_raw"]
        verified = verify_finding(
            job["text"],
            hits_for_v,
            finding,
            job["facts"],
            needs_fact_mode="cards",
            selected_cards=job["cards"],
            ax_review_to_ok=False,
        )
        verdict = verified.get("verdict") or "확인 필요"
        latency = rec.get("latency_ms")
        if latency is None:
            latency = mean_ms
        row = {
            "domain": job["domain"],
            "model": "luna",
            "model_id": price["model_id"],
            "cards_version": job["version"],
            "doc_id": job["doc_id"],
            "segment_id": job["segment_id"],
            "std_item": job.get("std_item"),
            "label": job["label"],
            "gold_codes": job["gold_codes"],
            "gold_provisions": job["gold_provisions"],
            "is_clean_doc": job["is_clean"],
            "is_clean_twin": job["is_clean_twin"],
            "text": job["text"],
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
                "finish_reason": finding.get("finish_reason"),
                "usage": finding.get("usage") or {},
                "prompt_sha256": job["user_sha256"],
            },
            "hits": [_hit_slim(h, i + 1) for i, h in enumerate(hits_for_v)],
            "selected_cards": [c.get("id") for c in job["cards"] if c.get("id")],
            "selected_cards_full": [
                {
                    "id": c.get("id"),
                    "blocking_if": c.get("blocking_if"),
                    "violation": c.get("violation") or [],
                    "safe": c.get("safe") or [],
                }
                for c in job["cards"]
            ],
            "facts": job["facts"],
            "verdict": verdict,
            "ax_verdict": verified.get("ax_verdict"),
            "review_source": classify_review_source(verified, verdict),
            "review_sources": verified.get("review_sources") or [],
            "notes": verified.get("notes") or [],
            "needs_fact": verified.get("needs_fact"),
            "needs_fact_action": verified.get("needs_fact_action"),
            "needs_fact_is_blocking_if": bool(verified.get("needs_fact")) and is_blocking_fact(verified.get("needs_fact"), job["cards"]) if job["cards"] else False,
            "dropped_ids": verified.get("dropped_ids") or [],
            "quote_mismatch": "quote_mismatch" in (verified.get("review_sources") or [])
            or any("quote_mismatch" in str(n) for n in (verified.get("notes") or [])),
            "parse_ok": bool(verified.get("parse_ok")),
            "evidence_final": verified.get("evidence") or [],
            "rule": verified.get("rule") or {},
            "doc_question": verified.get("doc_question"),
            "latency_ms": round(float(latency or 0), 1),
            "latency_from_pilot_mean": rec.get("latency_ms") is None,
            "bucket": score_pair(job["label"], verdict),
            "ax_review_to_ok_run": False,
            "finish_reason": rec.get("finish_reason"),
        }
        grouped.setdefault(key, []).append(row)
    for (version, domain), rows in grouped.items():
        complete = len(rows) == expected[(version, domain)]
        name = f"luna_{version}_{domain}_rows.jsonl" if complete else f"luna_{version}_{domain}_partial.jsonl"
        out = QFAIR / name
        with out.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        meta = {
            "model": "luna",
            "model_id": price["model_id"],
            "cards_version": version,
            "domain": domain,
            "n_rows": len(rows),
            "n_expected": expected[(version, domain)],
            "partial": not complete,
            "ax_review_to_ok": False,
            "reused": False,
            "fair": True,
            "code_hashes": hashes,
            "spent_usd_cache": round(spent(), 6),
            "time_note": "배치 행의 latency_ms는 시범 평균이다",
            "jsonl": str(out),
        }
        out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", out, "rows", len(rows), "partial", not complete, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["discover", "pilot", "batch", "wait", "materialize"], required=True)
    args = parser.parse_args()
    QFAIR.mkdir(parents=True, exist_ok=True)
    if args.phase == "discover":
        discover()
    elif args.phase == "pilot":
        pilot()
    elif args.phase == "batch":
        batch_submit()
    elif args.phase == "wait":
        batch_wait()
    else:
        materialize()


if __name__ == "__main__":
    main()
