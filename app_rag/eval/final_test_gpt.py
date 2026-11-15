# -*- coding: utf-8 -*-
"""FINAL_TEST GPT. gpt-6-luna만. 상한 $1.5. Batch custom_id는 프롬프트 해시 1회."""
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
from rag.settings import use_criteria_cards  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import reset_needs_fact_stats, verify_finding  # noqa: E402
from quant_run import _hit_slim, load_domain_docs  # noqa: E402
from metrics import score_pair  # noqa: E402
from dev_eval import gold_codes, gold_provisions, is_meta  # noqa: E402
from relax_check import classify_review_source  # noqa: E402
from final_test_common import (  # noqa: E402
    COST_CAP_USD,
    DOMAINS,
    LUNA_EXTRA,
    LUNA_PRICE,
    QDEV,
    QTEST,
    VERSIONS,
    code_hashes,
    dump_json,
)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
FILES_URL = "https://api.openai.com/v1/files"
BATCH_URL = "https://api.openai.com/v1/batches"
CACHE = QTEST / "cache"
COST_STATE_PATH = QTEST / "gpt_cost_state.json"


def _key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY missing")
    return key


def _assert_luna(model_id: str) -> None:
    low = model_id.lower()
    if low != "gpt-6-luna":
        raise SystemExit(f"forbidden model {model_id}")


def _body(user: str) -> dict:
    _assert_luna(LUNA_PRICE["model_id"])
    body = {
        "model": LUNA_PRICE["model_id"],
        "messages": [{"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }
    body.update(LUNA_EXTRA)
    return body


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


def _usd(usage: dict, *, batch: bool) -> float:
    tin, tout, _ = _usage_tokens(usage)
    pin = LUNA_PRICE["batch_in"] if batch else LUNA_PRICE["in"]
    pout = LUNA_PRICE["batch_out"] if batch else LUNA_PRICE["out"]
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


def _load_cached(body: dict) -> dict | None:
    path = _cache_file(_req_hash(body))
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _record(body: dict, js: dict, *, batch: bool, latency_ms: float | None) -> dict:
    digest = _req_hash(body)
    choice = (js.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = js.get("usage") or {}
    rec = {
        "content": msg.get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "usage": usage,
        "usd": _usd(usage, batch=batch),
        "batch": batch,
        "model": body.get("model"),
        "latency_ms": latency_ms,
        "error": None,
        "request_hash": digest,
    }
    _cache_file(digest).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    dump_json(COST_STATE_PATH, {"spent_usd": round(spent(), 6), "n_cache": len(list(CACHE.glob("*.json")))})
    return rec


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


def _jobs_path(split: str, versions: list[str]) -> Path:
    tag = "-".join(versions)
    root = QDEV if split == "dev" else QTEST
    return root / f"jobs_{split}_{tag}.jsonl"


def build_jobs(split: str, versions: list[str]) -> list[dict]:
    index, _ = get_index()
    jobs = []
    n = 0
    for domain in DOMAINS:
        for doc in load_domain_docs(domain, split=split):
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
                text_m, _ = mask_pii(raw)
                hits_raw = (index.search(strip_placeholders(text_m), domain=domain, title="") or {}).get("hits") or []
                law = doc["law_map"].get(seg.get("segment_id") or "", {})
                base = {
                    "split": split,
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
                for ver in versions:
                    os.environ["CARDS_VERSION"] = ver
                    clear_cards_cache()
                    use_c = use_criteria_cards()
                    user, cards, hits2 = build_judge_prompt(text_m, facts, hits_raw, use_criteria=use_c)
                    body = _body(user)
                    jobs.append(
                        {
                            **base,
                            "version": ver,
                            "user": user,
                            "user_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                            "request_hash": _req_hash(body),
                            "cards": cards,
                            "hits2": hits2,
                            "use_criteria": use_c,
                        }
                    )
                n += 1
                if n % 100 == 0:
                    print("JOBS", split, n, flush=True)
    path = _jobs_path(split, versions)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for job in jobs:
            slim = {k: v for k, v in job.items() if k not in ("cards", "hits2", "hits_raw", "facts")}
            # cards/hits는 재구성 가능하지만 materialize에 필요 → 별도 저장은 무거움. 전체 저장.
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    print("WROTE", path, "jobs", len(jobs), "spent", round(spent(), 6), flush=True)
    return jobs


def _load_jobs(split: str, versions: list[str]) -> list[dict]:
    path = _jobs_path(split, versions)
    jobs = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                jobs.append(json.loads(line))
    return jobs


def estimate(split: str, versions: list[str], sample_n: int = 12) -> dict:
    jobs = build_jobs(split, versions)
    # 버전·도메인 섞어 샘플
    picked = []
    for ver in versions:
        for domain in DOMAINS:
            pool = [j for j in jobs if j["version"] == ver and j["domain"] == domain]
            if not pool:
                continue
            step = max(1, len(pool) // max(1, sample_n // (len(versions) * 3) or 1))
            picked.extend(pool[::step][: max(1, sample_n // (len(versions) * 3))])
    picked = picked[:sample_n]
    rows = []
    for i, job in enumerate(picked):
        if spent() >= COST_CAP_USD:
            break
        body = _body(job["user"])
        rec = _load_cached(body)
        if rec is None:
            t1 = time.perf_counter()
            js, err, code = _post_chat(body)
            ms = (time.perf_counter() - t1) * 1000
            if js is None:
                print("EST_FAIL", code, (err or "")[:200], flush=True)
                continue
            rec = _record(body, js, batch=False, latency_ms=ms)
        tin, tout, reason = _usage_tokens(rec.get("usage") or {})
        rows.append({"in": tin, "out": tout, "reasoning": reason, "usd": rec.get("usd"), "latency_ms": rec.get("latency_ms")})
        print(f"EST {i+1}/{len(picked)} in={tin} out={tout} reason={reason} ${spent():.4f}", flush=True)
    if not rows:
        raise SystemExit("ESTIMATE_EMPTY")
    avg_in = sum(r["in"] for r in rows) / len(rows)
    avg_out = sum(r["out"] for r in rows) / len(rows)
    avg_reason = sum(r["reasoning"] for r in rows) / len(rows)
    # 남은 unique 요청 수
    unique = {}
    for job in jobs:
        unique[job["request_hash"]] = job
    uncached = [h for h, j in unique.items() if not _cache_file(h).exists()]
    est_batch = len(uncached) * (avg_in / 1e6 * LUNA_PRICE["batch_in"] + avg_out / 1e6 * LUNA_PRICE["batch_out"])
    est_reg = len(uncached) * (avg_in / 1e6 * LUNA_PRICE["in"] + avg_out / 1e6 * LUNA_PRICE["out"])
    summary = {
        "split": split,
        "versions": versions,
        "n_jobs": len(jobs),
        "n_unique": len(unique),
        "n_uncached": len(uncached),
        "n_sample": len(rows),
        "avg_in": avg_in,
        "avg_out": avg_out,
        "avg_reasoning": avg_reason,
        "spent_usd": spent(),
        "est_remain_batch_usd": est_batch,
        "est_remain_regular_usd": est_reg,
        "est_total_if_batch_usd": spent() + est_batch,
        "est_total_if_regular_usd": spent() + est_reg,
        "over_cap_batch": spent() + est_batch > COST_CAP_USD,
        "over_cap_regular": spent() + est_reg > COST_CAP_USD,
        "cap": COST_CAP_USD,
    }
    out = (QDEV if split == "dev" else QTEST) / f"gpt_estimate_{split}_{'-'.join(versions)}.json"
    dump_json(out, summary)
    print("ESTIMATE", json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def _req(url: str, data: bytes | None = None, headers: dict | None = None, method: str | None = None) -> dict:
    hdr = {"Authorization": f"Bearer {_key()}"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _upload_batch(jsonl_path: Path) -> str:
    boundary = "----ft" + uuid.uuid4().hex
    file_bytes = jsonl_path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
        f"batch\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="final_batch.jsonl"\r\n'
        f"Content-Type: application/jsonl\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    data = head + file_bytes + tail
    req = urllib.request.Request(
        FILES_URL,
        data=data,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        js = json.loads(resp.read().decode("utf-8"))
    return js["id"]


def batch_submit(split: str, versions: list[str]) -> None:
    jobs = _load_jobs(split, versions) if _jobs_path(split, versions).exists() else build_jobs(split, versions)
    # 같은 프롬프트 해시는 한 번만
    unique: dict[str, dict] = {}
    for job in jobs:
        h = job["request_hash"]
        if h not in unique and not _cache_file(h).exists():
            unique[h] = job
    root = QDEV if split == "dev" else QTEST
    lines = []
    id_map = {}
    for digest, job in unique.items():
        body = _body(job["user"])
        # custom_id = 프롬프트 해시 (유일). 중복 요청은 unique로 제거됨.
        cid = digest
        id_map[cid] = {
            "request_hash": digest,
            "doc_id": job["doc_id"],
            "segment_id": job["segment_id"],
            "version": job["version"],
            "domain": job["domain"],
        }
        lines.append({"custom_id": cid, "method": "POST", "url": "/v1/chat/completions", "body": body})
    jsonl = root / f"batch_input_{split}_{'-'.join(versions)}.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    dump_json(root / f"batch_map_{split}_{'-'.join(versions)}.json", id_map)
    print("BATCH_LINES", len(lines), "jobs", len(jobs), "cached_skip", len(jobs) - len(lines), flush=True)
    if not lines:
        print("BATCH_NOTHING", flush=True)
        return
    last_err = None
    created = None
    for attempt in range(2):
        try:
            file_id = _upload_batch(jsonl)
            created = _req(
                BATCH_URL,
                data=json.dumps({"input_file_id": file_id, "endpoint": "/v1/chat/completions", "completion_window": "24h"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            last_err = None
            break
        except Exception as exc:
            last_err = str(exc)[:800]
            print("BATCH_SUBMIT_FAIL", attempt + 1, last_err, flush=True)
            time.sleep(3)
    if created is None:
        dump_json(root / f"batch_error_{split}.json", {"error": last_err})
        print("BATCH_SKIP", last_err, flush=True)
        return
    dump_json(root / f"batch_{split}_{'-'.join(versions)}.json", created)
    print("BATCH_ID", created.get("id"), "status", created.get("status"), flush=True)


def _download_file(file_id: str, dest: Path) -> None:
    req = urllib.request.Request(
        f"https://api.openai.com/v1/files/{file_id}/content",
        headers={"Authorization": f"Bearer {_key()}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def _ingest_output(path: Path) -> int:
    n = 0
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            cid = rec.get("custom_id")
            resp = rec.get("response") or {}
            js = resp.get("body") or {}
            if resp.get("status_code") != 200 or not js:
                continue
            # body 재구성: cache key = custom_id(=request_hash)
            # 원본 body는 출력에 없을 수 있어 usage만으로 기록하려면 body 필요
            # batch input에서 다시 읽는다
            body = None
            # custom_id가 request_hash
            # content 저장을 위해 가짜 body로 해시 맞추기: 입력 파일에서 찾기
            # 간단히: choices만 저장할 때도 request_hash로 저장
            digest = cid
            choice = (js.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            usage = js.get("usage") or {}
            out = {
                "content": msg.get("content") or "",
                "finish_reason": choice.get("finish_reason"),
                "usage": usage,
                "usd": _usd(usage, batch=True),
                "batch": True,
                "model": LUNA_PRICE["model_id"],
                "latency_ms": None,
                "error": None,
                "request_hash": digest,
            }
            _cache_file(digest).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            n += 1
    dump_json(COST_STATE_PATH, {"spent_usd": round(spent(), 6), "n_cache": len(list(CACHE.glob("*.json")))})
    return n


def batch_wait(split: str, versions: list[str]) -> None:
    root = QDEV if split == "dev" else QTEST
    path = root / f"batch_{split}_{'-'.join(versions)}.json"
    if not path.exists():
        print("NO_BATCH → regular", flush=True)
        _regular_remaining(split, versions, reason="no_batch")
        return
    created = json.loads(path.read_text(encoding="utf-8"))
    batch_id = created.get("id")
    if not batch_id:
        _regular_remaining(split, versions, reason="no_batch_id")
        return
    deadline = time.time() + 7200
    status = created
    timed_out = False
    while time.time() < deadline:
        status = _req(f"{BATCH_URL}/{batch_id}", method="GET")
        st = status.get("status")
        print("BATCH_STATUS", st, "counts", status.get("request_counts"), flush=True)
        if st in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(30)
    else:
        timed_out = True
        try:
            status = _req(f"{BATCH_URL}/{batch_id}/cancel", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        except Exception as exc:
            print("CANCEL_FAIL", exc, flush=True)
        time.sleep(10)
        status = _req(f"{BATCH_URL}/{batch_id}", method="GET")
    dump_json(root / f"batch_final_{split}_{'-'.join(versions)}.json", status)
    out_id = status.get("output_file_id")
    err_id = status.get("error_file_id")
    if out_id:
        dest = root / f"batch_output_{split}_{'-'.join(versions)}.jsonl"
        _download_file(out_id, dest)
        n = _ingest_output(dest)
        print("BATCH_INGEST", n, "spent", round(spent(), 6), flush=True)
    if err_id:
        _download_file(err_id, root / f"batch_errors_{split}_{'-'.join(versions)}.jsonl")
    errs = ((status.get("errors") or {}).get("data") or [])
    if errs:
        dump_json(
            root / f"batch_fail_reason_{split}.json",
            {"status": status.get("status"), "n_errors": len(errs), "code": errs[0].get("code"), "message": errs[0].get("message")},
        )
    if timed_out or status.get("status") != "completed":
        _regular_remaining(split, versions, reason="batch_incomplete")


def _regular_remaining(split: str, versions: list[str], *, reason: str) -> None:
    jobs = _load_jobs(split, versions)
    unique = {}
    for job in jobs:
        unique[job["request_hash"]] = job
    sent = 0
    for digest, job in unique.items():
        if spent() >= COST_CAP_USD:
            print("STOP_CAP regular", round(spent(), 6), flush=True)
            break
        if _cache_file(digest).exists():
            continue
        body = _body(job["user"])
        t1 = time.perf_counter()
        js, err, code = _post_chat(body)
        ms = (time.perf_counter() - t1) * 1000
        if js is None:
            print("REGULAR_FAIL", code, (err or "")[:200], flush=True)
            continue
        _record(body, js, batch=False, latency_ms=ms)
        sent += 1
        if sent % 25 == 0:
            print("REGULAR", sent, "spent", round(spent(), 6), flush=True)
    note = {"reason": reason, "regular_sent": sent, "spent": spent()}
    root = QDEV if split == "dev" else QTEST
    dump_json(root / f"gpt_regular_{split}_{'-'.join(versions)}.json", note)
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


def materialize(split: str, versions: list[str]) -> None:
    jobs = _load_jobs(split, versions)
    hashes = code_hashes()
    # latency mean from cached with latency
    lats = []
    for path in CACHE.glob("*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("latency_ms") is not None:
            lats.append(float(rec["latency_ms"]))
    mean_ms = sum(lats) / len(lats) if lats else 0.0
    grouped: dict[tuple[str, str], list] = {}
    expected: dict[tuple[str, str], int] = {}
    for job in jobs:
        key = (job["version"], job["domain"])
        expected[key] = expected.get(key, 0) + 1
        rec = None
        cp = _cache_file(job["request_hash"])
        if cp.exists():
            rec = json.loads(cp.read_text(encoding="utf-8"))
        if rec is None:
            continue
        os.environ["CARDS_VERSION"] = job["version"]
        clear_cards_cache()
        reset_needs_fact_stats()
        # cards/hits2 may need rebuild if jobs loaded without them - they are in jobs
        cards = job.get("cards") or []
        hits2 = job.get("hits2") or job.get("hits_raw") or []
        finding = _finding(rec.get("content") or "", rec.get("error"), cards, hits2)
        finding["finish_reason"] = rec.get("finish_reason")
        finding["usage"] = rec.get("usage") or {}
        finding["prompt_sha256"] = job["user_sha256"]
        hits_for_v = finding.get("hits_for_verify") or hits2
        nf_mode = "cards" if job.get("use_criteria", True) else "legacy"
        verified = verify_finding(
            job["text"],
            hits_for_v,
            finding,
            job["facts"],
            needs_fact_mode=nf_mode,
            selected_cards=cards,
            ax_review_to_ok=False,
        )
        verdict = verified.get("verdict") or "확인 필요"
        latency = rec.get("latency_ms")
        if latency is None:
            latency = mean_ms
        row = {
            "domain": job["domain"],
            "model": "luna",
            "model_id": LUNA_PRICE["model_id"],
            "cards_version": job["version"],
            "split": split,
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
            "review_sources": verified.get("review_sources") or [],
            "notes": verified.get("notes") or [],
            "needs_fact": verified.get("needs_fact"),
            "needs_fact_action": verified.get("needs_fact_action"),
            "needs_fact_is_blocking_if": bool(verified.get("needs_fact"))
            and is_blocking_fact(verified.get("needs_fact"), cards)
            if cards
            else False,
            "dropped_ids": verified.get("dropped_ids") or [],
            "quote_mismatch": "quote_mismatch" in (verified.get("review_sources") or [])
            or any("quote_mismatch" in str(n) for n in (verified.get("notes") or [])),
            "parse_ok": bool(verified.get("parse_ok")),
            "evidence_final": verified.get("evidence") or [],
            "rule": verified.get("rule") or {},
            "doc_question": verified.get("doc_question"),
            "latency_ms": round(float(latency or 0), 1),
            "latency_from_mean": rec.get("latency_ms") is None,
            "bucket": score_pair(job["label"], verdict),
            "ax_review_to_ok_run": False,
            "finish_reason": rec.get("finish_reason"),
        }
        grouped.setdefault(key, []).append(row)
    root = QDEV if split == "dev" else QTEST
    for (version, domain), rows in grouped.items():
        complete = len(rows) == expected[(version, domain)]
        name = f"luna_{version}_{domain}_rows.jsonl" if complete else f"luna_{version}_{domain}_partial.jsonl"
        out = root / name
        with out.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        meta = {
            "model": "luna",
            "model_id": LUNA_PRICE["model_id"],
            "cards_version": version,
            "domain": domain,
            "split": split,
            "n_rows": len(rows),
            "n_expected": expected[(version, domain)],
            "partial": not complete,
            "ax_review_to_ok": False,
            "final_test": True,
            "code_hashes": hashes,
            "spent_usd_cache": round(spent(), 6),
            "jsonl": str(out),
        }
        out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WROTE", out, "rows", len(rows), "partial", not complete, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["estimate", "batch", "wait", "regular", "materialize"], required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--versions", default="none", help="comma list: none,neutral,tuned")
    args = parser.parse_args()
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    for v in versions:
        if v not in VERSIONS:
            raise SystemExit(f"bad version {v}")
    QTEST.mkdir(parents=True, exist_ok=True)
    QDEV.mkdir(parents=True, exist_ok=True)
    if args.phase == "estimate":
        estimate(args.split, versions)
    elif args.phase == "batch":
        batch_submit(args.split, versions)
    elif args.phase == "wait":
        batch_wait(args.split, versions)
    elif args.phase == "regular":
        _regular_remaining(args.split, versions, reason="forced_regular")
    else:
        materialize(args.split, versions)


if __name__ == "__main__":
    main()
