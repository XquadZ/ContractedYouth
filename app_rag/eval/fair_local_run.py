# -*- coding: utf-8 -*-
"""FAIR_RERUN 로컬 실행. 한 번에 모델 하나만. GPT를 부르지 않는다."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache  # noqa: E402
from fair_common import DOMAINS, QFAIR, QNEU, code_hashes, label_set, load_hash, neutral_prompt_hashes_equal  # noqa: E402
from quant_run import ensure_model, run_one  # noqa: E402
from dev_eval import is_meta  # noqa: E402
from rag.pii import mask_pii  # noqa: E402


def _changed_segments() -> int:
    from quant_run import load_domain_docs

    n = 0
    for domain in DOMAINS:
        for doc in load_domain_docs(domain):
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                raw = seg.get("text") or ""
                if mask_pii(raw)[0] != raw:
                    n += 1
    return n


def reuse_ok() -> dict:
    equal, same = neutral_prompt_hashes_equal()
    changed = _changed_segments()
    after = load_hash("after")
    info = {
        "neutral_hash_equal_799": equal,
        "neutral_hash_same": same,
        "mask_changed_segments": changed,
        "law_star": after.get("law_evidence_star_count"),
        "law_mismatch_empty_basis_id": after.get("law_mismatch"),
        "law_note": "law_mismatch는 카드 basis id가 corpus에 없어 본문이 빈 경우. 본문이 있는 조문은 corpus와 같고 별표 0.",
        "reuse": bool(equal and changed == 0),
    }
    return info


def _keys_of_rows(path: Path) -> set[tuple]:
    keys = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            keys.add((row.get("domain"), row.get("doc_id"), row.get("segment_id"), row.get("label") or ""))
    return keys


def reuse_neutral(model: str) -> None:
    gate = reuse_ok()
    (QFAIR / "reuse_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    if not gate["reuse"]:
        raise SystemExit(f"REUSE_BLOCKED {gate}")
    expected = label_set(load_hash("before"))
    hashes = code_hashes()
    for domain in DOMAINS:
        src = QNEU / f"{model}_{domain}_rows.jsonl"
        src_meta = src.with_suffix(".meta.json")
        dst = QFAIR / f"{model}_neutral_{domain}_rows.jsonl"
        if not src.exists():
            raise SystemExit(f"missing {src}")
        got = _keys_of_rows(src)
        if got != {k for k in expected if k[0] == domain}:
            diff_missing = sorted({k for k in expected if k[0] == domain} - got)[:20]
            diff_extra = sorted(got - {k for k in expected if k[0] == domain})[:20]
            note = {
                "model": model,
                "domain": domain,
                "missing": diff_missing,
                "extra": diff_extra,
            }
            (QFAIR / f"key_mismatch_{model}_neutral_{domain}.json").write_text(
                json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("KEY_MISMATCH", model, domain, "missing", len(diff_missing), "extra", len(diff_extra), flush=True)
            continue
        shutil.copy2(src, dst)
        meta = {}
        if src_meta.exists():
            meta = json.loads(src_meta.read_text(encoding="utf-8"))
        meta.update(
            {
                "reused": True,
                "reused_from": str(src),
                "cards_version": "neutral",
                "fair": True,
                "code_hashes": hashes,
                "ax_review_to_ok": False,
            }
        )
        dst.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("REUSED", dst, "rows_keys", len(got), flush=True)


def run_version(model: str, version: str) -> None:
    os.environ["CARDS_VERSION"] = version
    clear_cards_cache()
    QFAIR.mkdir(parents=True, exist_ok=True)
    hashes = code_hashes()
    ensure_model(model, alone=True)
    for domain in DOMAINS:
        out = QFAIR / f"{model}_{version}_{domain}_rows.jsonl"
        last_err = None
        meta = None
        for attempt in range(2):
            try:
                print(f"RUN {model} {version} {domain} attempt={attempt + 1}", flush=True)
                meta = run_one(model=model, domain=domain, out_jsonl=out)
                last_err = None
                break
            except SystemExit as exc:
                last_err = str(exc)
                print("FAIL", model, version, domain, last_err, flush=True)
                traceback.print_exc()
        if meta is None:
            (QFAIR / f"skip_{model}_{version}_{domain}.json").write_text(
                json.dumps({"error": last_err, "attempts": 2}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("SKIP", model, version, domain, flush=True)
            continue
        meta.update(
            {
                "reused": False,
                "cards_version": version,
                "fair": True,
                "code_hashes": hashes,
                "ax_review_to_ok": False,
            }
        )
        out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("META", out.with_suffix(".meta.json"), flush=True)


def leave_exaone() -> None:
    sw = ensure_model("EXAONE", alone=True)
    print("EXAONE_LEFT_UP", round(sw, 2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["gate", "reuse", "run", "leave"], required=True)
    parser.add_argument("--model", choices=["EXAONE", "AX"])
    parser.add_argument("--version", choices=["neutral", "tuned"])
    args = parser.parse_args()
    if args.step == "gate":
        info = reuse_ok()
        QFAIR.mkdir(parents=True, exist_ok=True)
        (QFAIR / "reuse_gate.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(info, ensure_ascii=False), flush=True)
        return
    if args.step == "reuse":
        if not args.model:
            raise SystemExit("--model required")
        reuse_neutral(args.model)
        return
    if args.step == "run":
        if not args.model or not args.version:
            raise SystemExit("--model and --version required")
        run_version(args.model, args.version)
        return
    leave_exaone()


if __name__ == "__main__":
    main()
