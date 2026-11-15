# -*- coding: utf-8 -*-
"""평가 재생. 새 추론은 하지 않는다.

왼쪽 = Q8B T3 A4-BM25.
오른쪽 = numeric 은 규칙, 규칙을 못 하면 AX7 T3 A1, text 는 AX7 T3 A1.
수치는 exp_v2/score_v2.py 의 t3_pack, metric_ci, paired_cluster_diff.
"""
from __future__ import annotations

import sys
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
sys.path.insert(0, str(WORK / "exp_v2"))

from baselines.rules import TARGET_CHECKS, judge_item  # noqa: E402
from score_v2 import as_bool, fmt, metric_ci, paired_cluster_diff, t3_pack  # noqa: E402

from pipelines.common import SEVERITY_KO, load_jsonl, world  # noqa: E402

RUNS = WORK / "exp_v2" / "runs"
CODE = "exp_v2/score_v2.py (metric_ci, paired_cluster_diff, t3_pack); app_compare/pipelines/replay.py"


def _pack_stat(rows: list[dict], key: str):
    stat = metric_ci(rows, key, by_pair=True)
    return stat


def build() -> dict:
    w = world()
    golds = w.t3
    left_runs = {r["id"]: r for r in load_jsonl(RUNS / "Q8B_T3_A4-BM25.jsonl")}
    ax_runs = {r["id"]: r for r in load_jsonl(RUNS / "AX7_T3_A1.jsonl")}
    left_rows = []
    right_rows = []
    view = []
    for item_id, gold in golds.items():
        left = left_runs.get(item_id) or {}
        ax = ax_runs.get(item_id) or {}
        lpred = as_bool((left.get("parsed") or {}).get("risky")) if left.get("parse_ok") else None
        apred = as_bool((ax.get("parsed") or {}).get("risky")) if ax.get("parse_ok") else None
        lreason = str((left.get("parsed") or {}).get("reason") or "")
        areason = str((ax.get("parsed") or {}).get("reason") or "")
        actor = "모델"
        rpred = apred
        rreason = areason
        if gold.get("kind") == "numeric" and gold.get("check_id") in TARGET_CHECKS:
            ruled = judge_item(gold)
            if ruled is None:
                actor = "규칙 N/A→모델"
                rpred = apred
                rreason = areason
            else:
                actor = "규칙"
                rpred = ruled
                check = w.check_by_id.get(gold["check_id"]) or {}
                rreason = "규칙 판정. " + (check.get("title") or gold["check_id"])
        base = {
            "id": item_id,
            "pair_id": gold.get("pair_id"),
            "surface": gold.get("surface"),
            "kind": gold.get("kind"),
            "check_id": gold.get("check_id"),
            "domain": gold.get("domain"),
            "gold": bool(gold.get("risky")),
            "clause": gold.get("clause") or "",
        }
        left_rows.append({**base, "pred": lpred, "parse_fail": lpred is None})
        right_rows.append({**base, "pred": rpred, "parse_fail": rpred is None})
        check = w.check_by_id.get(gold.get("check_id")) or {}
        view.append(
            {
                **base,
                "left_risky": lpred,
                "right_risky": rpred,
                "left_reason": lreason[:240],
                "right_reason": rreason[:240],
                "actor": actor,
                "severity": SEVERITY_KO.get(check.get("severity") or "", ""),
                "left_ok": lpred is not None and lpred == bool(gold.get("risky")),
                "right_ok": rpred is not None and rpred == bool(gold.get("risky")),
            }
        )

    def side(rows: list[dict]) -> dict:
        num = [r for r in rows if r["kind"] == "numeric"]
        text = [r for r in rows if r["kind"] == "text"]
        return {
            "bacc": _pack_stat(rows, "bacc"),
            "pair": _pack_stat(rows, "pair"),
            "acc": _pack_stat(rows, "acc"),
            "numeric_acc": _pack_stat(num, "acc"),
            "text_acc": _pack_stat(text, "acc"),
            "numeric_bacc": _pack_stat(num, "bacc"),
            "text_bacc": _pack_stat(text, "bacc"),
            "n": len(rows),
            "point": {
                "bacc": t3_pack(rows)["bacc"],
                "pair": t3_pack(rows)["pair"],
                "numeric_acc": t3_pack(num)["acc"],
                "text_acc": t3_pack(text)["acc"],
            },
        }

    diff_bacc = paired_cluster_diff(left_rows, right_rows, "bacc")
    diff_pair = paired_cluster_diff(left_rows, right_rows, "pair")
    return {
        "code": CODE,
        "summary": {
            "left": side(left_rows),
            "right": side(right_rows),
            "diff_bacc": diff_bacc,
            "diff_pair": diff_pair,
            "fmt": {
                "left_bacc": fmt(_pack_stat(left_rows, "bacc")),
                "left_pair": fmt(_pack_stat(left_rows, "pair")),
                "right_bacc": fmt(_pack_stat(right_rows, "bacc")),
                "right_pair": fmt(_pack_stat(right_rows, "pair")),
                "diff_bacc": _fmt_diff(diff_bacc),
                "diff_pair": _fmt_diff(diff_pair),
                "left_num": fmt(_pack_stat([r for r in left_rows if r["kind"] == "numeric"], "acc")),
                "left_text": fmt(_pack_stat([r for r in left_rows if r["kind"] == "text"], "acc")),
                "right_num": fmt(_pack_stat([r for r in right_rows if r["kind"] == "numeric"], "acc")),
                "right_text": fmt(_pack_stat([r for r in right_rows if r["kind"] == "text"], "acc")),
            },
        },
        "rows": view,
    }


def _fmt_diff(stat) -> str:
    if not stat or stat.get("point") is None:
        return "-"
    return f"{stat['point']:+.3f} [{stat['lo']:.3f}, {stat['hi']:.3f}] (n={stat['n']})"


_CACHE = None


def replay() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = build()
    return _CACHE
