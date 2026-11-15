# -*- coding: utf-8 -*-
"""3-3. 교사 출력 검증 + SFT B/C 구축."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import FOOTER, RUN3, SEED, SYSTEM_SFT, load_jsonl, log, write_jsonl

HEADER_MARKERS = ["1. 🔍", "2. 📜", "3. 💡", "4. 📝"]
ARTICLE_RE = re.compile(r"제\d+조(?:의\d+)?")
CASE_RE = re.compile(r"\d{2,4}[다도누두마카]\d+")
PHONE_RE = re.compile(r"\d{2,4}-\d{3,4}(?:-\d{4})?")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{4,}")


def headers_in_order(text: str) -> bool:
    pos = -1
    for h in HEADER_MARKERS:
        i = text.find(h)
        if i < 0 or i < pos:
            return False
        pos = i
    return True


def footer_ok(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    if lines[-1] != FOOTER:
        return False
    return text.count(FOOTER) == 1


def find_novel(pattern: re.Pattern, out: str, ans: str) -> list[str]:
    a_set = set(pattern.findall(ans))
    return sorted({m for m in pattern.findall(out) if m not in a_set})


def novel_phones(out: str, ans: str) -> list[str]:
    a_set = set(PHONE_RE.findall(ans)) | {"132"}
    bad = []
    for m in PHONE_RE.findall(out):
        if m == "132" or m in a_set:
            continue
        bad.append(m)
    # also bare 132 is ok in footer; PHONE_RE may not match bare 132
    return sorted(set(bad))


def novel_cjk_runs(out: str, q: str, a: str) -> list[str]:
    allowed = set(CJK_RUN_RE.findall(q + a))
    return sorted({m for m in CJK_RUN_RE.findall(out) if m not in allowed})


def normalize_numbered_headers(text: str) -> tuple[str, bool]:
    """교사가 '1. ' 번호를 빼고 이모지 헤더만 쓴 경우, 번호만 보정(본문 미변경)."""
    if headers_in_order(text):
        return text, False
    pairs = [
        (r"(?m)^🔍\s*핵심 쟁점:", "1. 🔍 핵심 쟁점:"),
        (r"(?m)^📜\s*관련 법 원칙:", "2. 📜 관련 법 원칙:"),
        (r"(?m)^💡\s*이유:", "3. 💡 이유:"),
        (r"(?m)^📝\s*이렇게 하세요:", "4. 📝 이렇게 하세요:"),
    ]
    new = text
    for pat, repl in pairs:
        new2, n = re.subn(pat, repl, new, count=1)
        if n != 1:
            return text, False
        new = new2
    if headers_in_order(new):
        return new, True
    return text, False


def validate(row: dict) -> list[str]:
    reasons: list[str] = []
    out = row.get("output") or ""
    ans = row.get("answer") or ""
    q = row.get("question") or ""

    if out.strip() == "[SKIP]" or out.strip().startswith("[SKIP]"):
        reasons.append("skip")
    if not headers_in_order(out):
        reasons.append("headers")
    if not footer_ok(out):
        reasons.append("footer")
    arts = find_novel(ARTICLE_RE, out, ans)
    if arts:
        reasons.append("article:" + ",".join(arts))
    cases = find_novel(CASE_RE, out, ans)
    if cases:
        reasons.append("case:" + ",".join(cases))
    phones = novel_phones(out, ans)
    if phones:
        reasons.append("phone:" + ",".join(phones))
    cjk = novel_cjk_runs(out, q, ans)
    if cjk:
        reasons.append("cjk:" + ",".join(cjk[:5]))
    if "<think>" in out or "</think>" in out:
        reasons.append("think_tag")
    n = len(out)
    if n < 300:
        reasons.append("too_short")
    if n > 1200:
        reasons.append("too_long")
    return reasons


def count_tokens(tokenizer, system: str, question: str, assistant: str) -> int:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
        {"role": "assistant", "content": assistant},
    ]
    try:
        ids = tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=False
        )
        return len(ids)
    except Exception:
        text = system + "\n" + question + "\n" + assistant
        return len(tokenizer.encode(text))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", type=Path, default=RUN3 / "teacher_outputs.jsonl")
    ap.add_argument("--outdir", type=Path, default=RUN3)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--skip-tokenizer", action="store_true")
    args = ap.parse_args()

    random.seed(args.seed)
    rows = load_jsonl(args.teacher)
    log(f"teacher rows: {len(rows)}")

    reason_counts: Counter[str] = Counter()
    fail_examples: dict[str, list[dict]] = defaultdict(list)
    passed: list[dict] = []
    header_normalized = 0

    for r in rows:
        out0 = r.get("output") or ""
        out1, did_norm = normalize_numbered_headers(out0)
        if did_norm:
            r = dict(r)
            r["output"] = out1
            r["header_normalized"] = True
            header_normalized += 1
        reasons = validate(r)
        if reasons:
            for reason in reasons:
                key = reason.split(":")[0]
                reason_counts[key] += 1
                if len(fail_examples[key]) < 2:
                    fail_examples[key].append({
                        "id": r.get("id"),
                        "reason": reason,
                        "output": (r.get("output") or "")[:500],
                        "answer": (r.get("answer") or "")[:300],
                    })
        else:
            passed.append(r)
    log(f"header_normalized: {header_normalized}")

    log(f"passed_pre_token: {len(passed)}")
    log(f"reason_counts: {dict(reason_counts)}")

    tokenizer = None
    if not args.skip_tokenizer:
        try:
            from transformers import AutoTokenizer
            from common import resolve_student_model
            tok_name = resolve_student_model()
            tokenizer = AutoTokenizer.from_pretrained(
                tok_name, trust_remote_code=True
            )
            log(f"tokenizer loaded: {tok_name}")
        except Exception as e:
            log(f"tokenizer load failed: {type(e).__name__}: {e}")
            log("continuing without token-length filter (will mark 미확인)")

    final_rows = []
    dropped_len = 0
    for r in passed:
        if tokenizer is not None:
            tb = count_tokens(tokenizer, SYSTEM_SFT, r["question"], r["answer"])
            tc = count_tokens(tokenizer, SYSTEM_SFT, r["question"], r["output"])
            if tb > args.max_len or tc > args.max_len:
                dropped_len += 1
                reason_counts["token_over_2048"] += 1
                continue
        final_rows.append(r)
    log(f"dropped token>2048 (both B&C): {dropped_len}")
    log(f"final ids: {len(final_rows)}")

    ids = [r["id"] for r in final_rows]
    (args.outdir / "final_ids.txt").write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")

    # 5% val split same ids
    n_val = max(1, int(round(len(final_rows) * 0.05))) if final_rows else 0
    shuffled = list(final_rows)
    random.shuffle(shuffled)
    val_ids = {r["id"] for r in shuffled[:n_val]}
    train_rows = [r for r in final_rows if r["id"] not in val_ids]
    val_rows = [r for r in final_rows if r["id"] in val_ids]
    log(f"split train={len(train_rows)} val={len(val_rows)}")

    def to_sft(src: list[dict], assistant_key: str) -> list[dict]:
        out = []
        for r in src:
            out.append({
                "id": r["id"],
                "domain": r["domain"],
                "split": "val" if r["id"] in val_ids else "train",
                "messages": [
                    {"role": "system", "content": SYSTEM_SFT},
                    {"role": "user", "content": r["question"]},
                    {"role": "assistant", "content": r[assistant_key]},
                ],
            })
        return out

    sft_b = to_sft(final_rows, "answer")
    sft_c = to_sft(final_rows, "output")
    write_jsonl(args.outdir / "sft_B.jsonl", sft_b)
    write_jsonl(args.outdir / "sft_C.jsonl", sft_c)

    dom = Counter(r["domain"] for r in final_rows)
    report = {
        "teacher_n": len(rows),
        "passed": len(final_rows),
        "header_normalized": header_normalized,
        "reason_counts": dict(reason_counts),
        "domain_counts": dict(dom),
        "train_n": len(train_rows),
        "val_n": len(val_rows),
        "fail_examples": {k: v for k, v in fail_examples.items()},
        "tokenizer_ok": tokenizer is not None,
    }
    (args.outdir / "build_sft_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
