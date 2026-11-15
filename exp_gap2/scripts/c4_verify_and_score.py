# -*- coding: utf-8 -*-
"""C4 integrity check + score for GAP2 table C. ASCII-only console."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
DATA = G2 / "data"
G1 = ROOT / "exp_gap1"
RUN_LOG = G2 / "run_log.md"

sys.path.insert(0, str(G2))
from score2 import fmt_ci, gap_label, load_jsonl, paired_diff_ci, score_e2  # noqa: E402

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def append_run_log(text: str):
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        f.flush()
        os.fsync(f.fileno())


def analyze(path: Path, expected_ids: list[str]):
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    rows = []
    broken = 0
    for i, ln in enumerate(raw_lines, 1):
        if not ln.strip():
            continue
        try:
            o = json.loads(ln)
            if isinstance(o, dict) and "id" in o:
                rows.append(o)
            else:
                broken += 1
        except Exception:
            broken += 1
    ids = [r["id"] for r in rows]
    cnt = Counter(ids)
    dup = sorted([i for i, c in cnt.items() if c > 1])
    unique = list(dict.fromkeys(ids))  # first occurrence order
    first_by_id = {}
    for r in rows:
        if r["id"] not in first_by_id:
            first_by_id[r["id"]] = r
    missing = [i for i in expected_ids if i not in first_by_id]
    extra = [i for i in unique if i not in set(expected_ids)]
    parse_fail = sum(
        1
        for r in first_by_id.values()
        if not (
            r.get("parse_ok")
            and isinstance(r.get("parsed"), dict)
            and r["parsed"].get("articles") is not None
        )
    )
    return {
        "lines": len(raw_lines),
        "valid_json": len(rows),
        "unique_ids": len(unique),
        "dup_ids": dup,
        "n_dup_ids": len(dup),
        "missing": missing,
        "extra": extra,
        "parse_fail_first": parse_fail,
        "first_by_id": first_by_id,
        "broken_lines": broken,
    }


def main():
    test500 = load_jsonl(DATA / "e2_test1000.jsonl")[:500]
    expected = [r["id"] for r in test500]
    c4p = OUT / "32B_E2_C4.jsonl"
    info = analyze(c4p, expected)
    # drop heavy field for log
    log_info = {k: v for k, v in info.items() if k != "first_by_id"}
    append_run_log(
        f"\n## C4 integrity @ {datetime.now().isoformat(timespec='seconds')}\n"
        f"```json\n{json.dumps(log_info, ensure_ascii=False, indent=2)}\n```\n"
        f"Scoring rule: if duplicate id, use FIRST record only.\n"
    )
    print("C4 integrity", json.dumps(log_info, ensure_ascii=True), flush=True)

    if info["missing"]:
        print("MISSING ids", len(info["missing"]), info["missing"][:10], flush=True)
        (OUT / "c4_missing_ids.json").write_text(
            json.dumps(info["missing"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        print("no missing ids", flush=True)

    # score: first-only preds
    preds32 = []
    for iid in expected:
        r = info["first_by_id"].get(iid)
        if not r:
            continue
        preds32.append(r)
    gold = test500
    sc32 = score_e2(gold, preds32)
    # 8B
    p8 = {r["id"]: r for r in load_jsonl(OUT / "8B_E2_C4.jsonl")}
    # first only for 8B too
    seen = set()
    preds8 = []
    for r in load_jsonl(OUT / "8B_E2_C4.jsonl"):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        preds8.append(r)
    sc8 = score_e2(gold, preds8)

    # align top1 vals by gold order
    def top1_by_id(sc, gold_rows, pred_rows):
        # re-score already has vals in gold order excluding mask; rebuild
        from score2 import index_preds

        preds = index_preds(pred_rows)
        vals = []
        for g in gold_rows:
            p = preds.get(g["id"])
            ok = bool(p and p["parse_ok"] and p["articles"] is not None)
            arts = (p["articles"] or []) if ok else []
            vals.append(1.0 if arts and arts[0] in set(g["gold_articles"]) else 0.0)
        return vals

    v32 = top1_by_id(sc32, gold, preds32)
    v8 = top1_by_id(sc8, gold, preds8)
    n = min(len(v32), len(v8))
    diff = paired_diff_ci(v32[:n], v8[:n])

    result = {
        "n_gold": len(gold),
        "8B_top1": sc8["top1"],
        "32B_top1": sc32["top1"],
        "8B_any_hit": sc8["any_hit"],
        "32B_any_hit": sc32["any_hit"],
        "diff_32_8_top1": diff,
        "gap_label": gap_label(diff),
        "random_baseline": 0.333,
        "setting": "A",
        "dup_rule": "first_record_only",
        "code": "exp_gap2/scripts/c4_verify_and_score.py",
    }
    (OUT / "c4_score.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    append_run_log(
        f"\n## C4 score (table C)\n"
        f"- 8B top1: {fmt_ci(sc8['top1'])}\n"
        f"- 32B top1: {fmt_ci(sc32['top1'])}\n"
        f"- 32B-8B: {fmt_ci(diff)} -> {gap_label(diff)}\n"
        f"- random baseline: 33.3%\n"
        f"- setting: A; n={len(gold)}; first_record_only for dups\n"
        f"```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n"
    )
    print("8B", fmt_ci(sc8["top1"]), flush=True)
    print("32B", fmt_ci(sc32["top1"]), flush=True)
    print("diff", fmt_ci(diff), gap_label(diff), flush=True)
    return info


if __name__ == "__main__":
    main()
