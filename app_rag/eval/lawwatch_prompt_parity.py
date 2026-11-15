# -*- coding: utf-8 -*-
"""버전 파일 없을 때 판정 프롬프트 해시 799/799 같음 검사. LLM 호출 없음. test 평가 안 함."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import build_judge_prompt  # noqa: E402
from rag.lawwatch.paths import CRITERIA_VERSIONS, LAWWATCH_OUT  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402

DOMAINS = ("LAB", "LEASE", "LOAN")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_all(*, cards_version: str = "tuned") -> dict:
    os.environ["CARDS_VERSION"] = cards_version
    clear_cards_cache()
    index, _skipped = get_index()
    items = []
    n = 0
    for domain in DOMAINS:
        docs = load_domain_docs(domain)
        for doc in docs:
            full = "\n".join(s.get("text") or "" for s in doc["segs"])
            facts = extract_facts(full)
            facts["domain"] = domain
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                text = seg.get("text") or ""
                hits_raw = (index.search(strip_placeholders(text), domain=domain, title="") or {}).get("hits") or []
                user, cards, _hits2 = build_judge_prompt(text, facts, hits_raw, use_criteria=True)
                items.append(
                    {
                        "domain": domain,
                        "doc_id": doc["doc_id"],
                        "segment_id": seg.get("segment_id"),
                        "label": seg.get("label") or "",
                        "sha256": _sha(user),
                        "card_ids": [c.get("id") for c in cards],
                    }
                )
                n += 1
                if n % 100 == 0:
                    print(f"HASH {n}", flush=True)
    return {
        "n": n,
        "cards_version": cards_version,
        "domains": {d: sum(1 for r in items if r["domain"] == d) for d in DOMAINS},
        "items": items,
    }


def compare(before: dict, after: dict) -> dict:
    bmap = {(r["domain"], r["doc_id"], r["segment_id"]): r["sha256"] for r in before["items"]}
    amap = {(r["domain"], r["doc_id"], r["segment_id"]): r["sha256"] for r in after["items"]}
    keys = sorted(set(bmap) | set(amap))
    same = 0
    diff = []
    for k in keys:
        if bmap.get(k) == amap.get(k) and k in bmap and k in amap:
            same += 1
        else:
            diff.append({"key": list(k), "before": bmap.get(k), "after": amap.get(k)})
    return {"n": len(keys), "same": same, "diff_n": len(diff), "diff_sample": diff[:20]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["before", "after", "compare", "after_no_versions"], required=True)
    args = ap.parse_args()
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    aside = APP / "criteria" / "versions.__aside__"

    if args.phase == "before":
        payload = hash_all()
        out = LAWWATCH_OUT / "prompt_hash_before.json"
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"phase": "before", "n": payload["n"], "out": str(out)}, ensure_ascii=False))
        return

    if args.phase == "after_no_versions":
        # 버전 디렉터리 잠시 치움 (해시 중 mkdir로 빈 폴더가 생겨도 복구)
        moved = False
        if CRITERIA_VERSIONS.exists() and not aside.exists():
            CRITERIA_VERSIONS.rename(aside)
            moved = True
        elif CRITERIA_VERSIONS.exists() and aside.exists():
            # 이전 실패 잔여물
            for f in CRITERIA_VERSIONS.glob("*.yaml"):
                f.unlink()
            moved = True
        try:
            payload = hash_all()
            out = LAWWATCH_OUT / "prompt_hash_after_no_versions.json"
            out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"phase": "after_no_versions", "n": payload["n"], "out": str(out), "moved": moved}, ensure_ascii=False))
        finally:
            if aside.exists():
                CRITERIA_VERSIONS.mkdir(parents=True, exist_ok=True)
                for f in aside.glob("*"):
                    dest = CRITERIA_VERSIONS / f.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(f), str(dest))
                try:
                    aside.rmdir()
                except OSError:
                    pass
        return

    if args.phase == "after":
        payload = hash_all()
        out = LAWWATCH_OUT / "prompt_hash_after.json"
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"phase": "after", "n": payload["n"], "out": str(out)}, ensure_ascii=False))
        return

    if args.phase == "compare":
        before = json.loads((LAWWATCH_OUT / "prompt_hash_before.json").read_text(encoding="utf-8"))
        after = json.loads((LAWWATCH_OUT / "prompt_hash_after_no_versions.json").read_text(encoding="utf-8"))
        cmp = compare(before, after)
        out = LAWWATCH_OUT / "prompt_parity.json"
        out.write_text(json.dumps(cmp, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = cmp["same"] == cmp["n"] and cmp["n"] > 0
        print(json.dumps({"ok": ok, "same": cmp["same"], "n": cmp["n"], "out": str(out)}, ensure_ascii=False))
        if not ok:
            sys.exit(2)


if __name__ == "__main__":
    main()
