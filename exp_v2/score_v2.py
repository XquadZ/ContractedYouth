# -*- coding: utf-8 -*-
"""설계 v2 채점. 부트스트랩 1,000회, seed 42. T3 는 pair_id 단위로 다시 뽑는다.

파싱 실패는 정확도에서 오답이다. 위험 재현율 분모에 들어가고 맞춘 것으로 세지 않는다.
거짓 경보는 안전 조항을 위험이라고 출력한 경우만 센다. 파싱 실패는 거짓 경보가 아니다.
ctx_incomplete 항목은 넣은 결과와 뺀 결과를 둘 다 낸다.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
RUNS = EXP / "runs"
DATA = EXP / "data"
BASE = EXP / "baselines" / "out"
N_BOOT = 1000
SEED = 42
T3_CONDS = ["A0", "A1", "A2", "A3", "A4-BM25", "A4-bge"]
MODELS = ["Q8B", "AX7", "Q8B-T"]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def number_ok(answer: str, value: float) -> bool:
    if not answer:
        return False
    cands = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*시간", answer):
        cands.append(float(match.group(1)) * 60.0)
        cands.append(float(match.group(1)))
    for match in re.finditer(r"(\d+)\s*분의\s*(\d+)", answer):
        den = int(match.group(1))
        if den:
            cands.append(100.0 * int(match.group(2)) / den)
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", answer):
        cands.append(float(match.group(1)))
    for match in re.finditer(r"(\d+(?:,\d{3})*(?:\.\d+)?)", answer):
        cands.append(float(match.group(1).replace(",", "")))
    return any(abs(cand - float(value)) <= 1e-6 for cand in cands)


def yesno_ok(answer: str, value: bool) -> bool:
    negative = bool(re.search(r"않|없|아니|금지|불가", answer or ""))
    return negative if value is False else not negative


def text_ok(item_id: str, answer: str) -> bool:
    text = answer or ""
    if item_id == "R05":
        return "10" in text and "3개월" in text
    if item_id == "R15":
        return ("전입" in text) or ("주민등록" in text)
    if item_id == "R17":
        return ("무효" in text) or ("효력이 없" in text)
    return False


def t3_pack(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "acc": None, "recall": None, "fpr": None, "bacc": None, "pair": None, "parse_fail": 0}
    correct = tp = fp = tn = parse_fail = 0
    n_pos = n_neg = 0
    for row in rows:
        gold = bool(row["gold"])
        pred = row["pred"]
        if row.get("parse_fail"):
            parse_fail += 1
        if gold:
            n_pos += 1
            if pred is True:
                tp += 1
                correct += 1
        else:
            n_neg += 1
            if pred is True:
                fp += 1
            elif pred is False:
                tn += 1
                correct += 1
    recall = tp / n_pos if n_pos else None
    spec = tn / n_neg if n_neg else None
    fpr = fp / n_neg if n_neg else None
    groups = defaultdict(list)
    for row in rows:
        groups[(row.get("pair_id"), row.get("surface"))].append(row)
    pair_hit = pair_n = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        pair_n += 1
        if all((not r.get("parse_fail")) and r["pred"] == bool(r["gold"]) for r in group):
            pair_hit += 1
    return {
        "n": len(rows),
        "acc": correct / len(rows),
        "recall": recall,
        "fpr": fpr,
        "bacc": None if recall is None or spec is None else (recall + spec) / 2,
        "pair": (pair_hit / pair_n) if pair_n else None,
        "pair_n": pair_n,
        "parse_fail": parse_fail,
    }


def bootstrap(rows: list[dict], fn, by_pair: bool = True):
    if not rows:
        return None
    groups = defaultdict(list)
    for row in rows:
        key = row.get("pair_id") if by_pair else row["id"]
        groups[key].append(row)
    keys = list(groups)
    point = fn([row for key in keys for row in groups[key]])
    if point is None:
        return None
    rng = np.random.default_rng(SEED)
    stats = []
    for _ in range(N_BOOT):
        take = rng.integers(0, len(keys), len(keys))
        sample = [row for i in take for row in groups[keys[i]]]
        value = fn(sample)
        if value is not None:
            stats.append(value)
    if not stats:
        return None
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"point": float(point), "lo": float(lo), "hi": float(hi), "n": len(rows), "n_groups": len(keys)}


def metric_ci(rows: list[dict], key: str, by_pair: bool = True):
    return bootstrap(rows, lambda sample: t3_pack(sample)[key], by_pair=by_pair)


def fmt(stat, digits: int = 3) -> str:
    if not stat or stat.get("point") is None:
        return "-"
    return f"{stat['point']:.{digits}f} [{stat['lo']:.{digits}f}, {stat['hi']:.{digits}f}] (n={stat['n']})"


def fmt_diff(stat, digits: int = 3) -> str:
    if not stat or stat.get("point") is None:
        return "-"
    return f"{stat['point']:+.{digits}f} [{stat['lo']:.{digits}f}, {stat['hi']:.{digits}f}] (n={stat['n']})"


def paired_cluster_diff(rows_a: list[dict], rows_b: list[dict], key: str = "bacc", by_pair: bool = True):
    """metric(rows_b) - metric(rows_a). 같은 id만 쓰고, pair_id(또는 id)를 함께 다시 뽑는다."""
    map_a = {r["id"]: r for r in rows_a}
    map_b = {r["id"]: r for r in rows_b}
    ids = [i for i in map_a if i in map_b]
    if not ids:
        return None
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        group = map_a[i].get("pair_id") if by_pair else i
        groups[str(group)].append(i)
    keys = list(groups)

    def diff_of(draw: list[str]):
        take: list[str] = []
        for group in draw:
            take.extend(groups[group])
        left = t3_pack([map_a[i] for i in take])[key]
        right = t3_pack([map_b[i] for i in take])[key]
        if left is None or right is None:
            return None
        return right - left

    point = diff_of(keys)
    if point is None:
        return None
    rng = np.random.default_rng(SEED)
    stats = []
    n_keys = len(keys)
    for _ in range(N_BOOT):
        draw = [keys[i] for i in rng.integers(0, n_keys, n_keys)]
        value = diff_of(draw)
        if value is not None:
            stats.append(value)
    if not stats:
        return None
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"point": float(point), "lo": float(lo), "hi": float(hi), "n": len(ids), "n_groups": n_keys}


def paired_acc_diff(flags_a: dict[str, bool], flags_b: dict[str, bool]):
    """정확도(b) - 정확도(a). 같은 id를 항목 단위로 다시 뽑는다."""
    ids = [i for i in flags_a if i in flags_b]
    if not ids:
        return None
    left = np.array([1.0 if flags_a[i] else 0.0 for i in ids])
    right = np.array([1.0 if flags_b[i] else 0.0 for i in ids])
    point = float(right.mean() - left.mean())
    rng = np.random.default_rng(SEED)
    ix = rng.integers(0, len(ids), size=(N_BOOT, len(ids)))
    stats = right[ix].mean(axis=1) - left[ix].mean(axis=1)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"point": point, "lo": float(lo), "hi": float(hi), "n": len(ids), "n_groups": len(ids)}


COND_DIFFS = [
    ("A1−A0", "A0", "A1"),
    ("A2−A1", "A1", "A2"),
    ("A3−A1", "A1", "A3"),
    ("A4-BM25−A0", "A0", "A4-BM25"),
    ("A4-bge−A0", "A0", "A4-bge"),
]
LEAK = "무효(유출)"


def uses_t4_leak(left: str, right: str) -> bool:
    return left == "A1" or right == "A1"


def row_correct(row: dict) -> bool:
    return (not row.get("parse_fail")) and row["pred"] == bool(row["gold"])


def surface0(rows: list[dict]) -> list[dict]:
    return [r for r in rows if str(r.get("surface")) == "0"]


def append_contrasts(lines: list[str], cached: dict, t4_flags: dict) -> None:
    lines.append("## 짝지은 차이 (부트스트랩 1,000회, seed 42)")
    lines.append("")
    lines.append("차이는 뒤 조건(또는 뒤 모델) − 앞쪽이다. 같은 id만 남기고, T3는 pair_id를 한 덩어리로 다시 뽑는다. T4는 항목 단위다. 칸의 n은 항목 수다.")
    lines.append("T4에서 A1이 들어간 대비는 무효(유출)이다.")
    lines.append("")
    lines.append("### T3 균형 정확도, 전체 (Q8B·AX7)")
    lines.append("")
    lines.append("| 대비 | Q8B | AX7 |")
    lines.append("|---|---|---|")
    for label, left, right in COND_DIFFS:
        cells = []
        for model in ("Q8B", "AX7"):
            stat = paired_cluster_diff(cached[(model, left)], cached[(model, right)], "bacc")
            cells.append(fmt_diff(stat))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| 조건 | AX7−Q8B |")
    lines.append("|---|---|")
    for cond in T3_CONDS:
        stat = paired_cluster_diff(cached[("Q8B", cond)], cached[("AX7", cond)], "bacc")
        lines.append(f"| {cond} | {fmt_diff(stat)} |")
    lines.append("")
    lines.append("### T3 균형 정확도, surface 0 (134건)")
    lines.append("")
    lines.append("Q8B-T는 surface 0만 돌렸다. 아래 Q8B·AX7도 같은 134건만 다시 계산했다.")
    lines.append("")
    lines.append("| 모델 | A0 | A1 | A2 | A3 | A4-BM25 | A4-bge |")
    lines.append("|---|---|---|---|---|---|---|")
    s0 = {}
    for model in MODELS:
        cells = []
        for cond in T3_CONDS:
            rows = surface0(cached[(model, cond)])
            s0[(model, cond)] = rows
            cells.append(fmt(metric_ci(rows, "bacc")) if rows else "-")
        lines.append("| " + model + " | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| 대비 | Q8B | AX7 | Q8B-T |")
    lines.append("|---|---|---|---|")
    for label, left, right in COND_DIFFS:
        cells = []
        for model in MODELS:
            stat = paired_cluster_diff(s0[(model, left)], s0[(model, right)], "bacc")
            cells.append(fmt_diff(stat))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| 조건 | AX7−Q8B | Q8B-T−Q8B |")
    lines.append("|---|---|---|")
    for cond in T3_CONDS:
        ax = paired_cluster_diff(s0[("Q8B", cond)], s0[("AX7", cond)], "bacc")
        qt = paired_cluster_diff(s0[("Q8B", cond)], s0[("Q8B-T", cond)], "bacc")
        lines.append(f"| {cond} | {fmt_diff(ax)} | {fmt_diff(qt)} |")
    lines.append("")
    lines.append("### T4 top1")
    lines.append("")
    lines.append("| 대비 | Q8B | AX7 | Q8B-T |")
    lines.append("|---|---|---|---|")
    for label, left, right in COND_DIFFS:
        cells = []
        for model in MODELS:
            if uses_t4_leak(left, right):
                cells.append(LEAK)
            else:
                stat = paired_acc_diff(t4_flags[(model, left)], t4_flags[(model, right)])
                cells.append(fmt_diff(stat))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| 조건 | AX7−Q8B | Q8B-T−Q8B |")
    lines.append("|---|---|---|")
    for cond in T3_CONDS:
        if cond == "A1":
            lines.append(f"| {cond} | {LEAK} | {LEAK} |")
            continue
        ax = paired_acc_diff(t4_flags[("Q8B", cond)], t4_flags[("AX7", cond)])
        qt = paired_acc_diff(t4_flags[("Q8B", cond)], t4_flags[("Q8B-T", cond)])
        lines.append(f"| {cond} | {fmt_diff(ax)} | {fmt_diff(qt)} |")
    lines.append("")


def append_ax7_check_gain(lines: list[str], cached: dict) -> None:
    lines.append("## AX7 T3 A0→A1 check별 차이")
    lines.append("")
    lines.append("균형 정확도 A1−A0. pair_id 단위 부트스트랩. 상위 5개와, 그 check에서 A0 오답이 A1 정답으로 바뀐 항목 3건(조항 150자).")
    lines.append("")
    a0 = cached[("AX7", "A0")]
    a1 = cached[("AX7", "A1")]
    checks = sorted({r["check_id"] for r in a0})
    ranked = []
    for check in checks:
        left = [r for r in a0 if r["check_id"] == check]
        right = [r for r in a1 if r["check_id"] == check]
        stat = paired_cluster_diff(left, right, "bacc")
        ranked.append((stat["point"] if stat else -999, check, stat, left, right))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    lines.append("| check | A1−A0 | n |")
    lines.append("|---|---|---:|")
    for _point, check, stat, _left, _right in ranked[:5]:
        lines.append(f"| {check} | {fmt_diff(stat)} | {stat['n'] if stat else 0} |")
    lines.append("")
    for _point, check, stat, left, right in ranked[:5]:
        by_id = {r["id"]: r for r in left}
        flips = []
        for row in right:
            prev = by_id.get(row["id"])
            if prev is None:
                continue
            if (not row_correct(prev)) and row_correct(row):
                flips.append((prev, row))
        flips.sort(key=lambda item: item[1]["id"])
        lines.append(f"### {check} 전환 {len(flips)}건")
        lines.append("")
        for prev, row in flips[:3]:
            snippet = row["clause"].replace("\n", " ").replace("|", "/")[:150]
            lines.append(
                f"- `{row['id']}` gold={row['gold']} A0={prev['pred']} → A1={row['pred']} / {snippet}"
            )
        lines.append("")


def choice_line(node: dict) -> str:
    title = (node.get("조문 제목") or "").strip()
    base = f"{node.get('법령명')} {node.get('조문 번호')}"
    return f"{base}({title})" if title else base


def runs(model: str, task: str, cond: str) -> list[dict]:
    return load_jsonl(RUNS / f"{model}_{task}_{cond}.jsonl")


def build_t3(model: str, cond: str, golds: dict, drop_incomplete: bool = False) -> list[dict]:
    out = []
    for run in runs(model, "T3", cond):
        if drop_incomplete and run.get("ctx_incomplete"):
            continue
        gold = golds.get(run["id"])
        if gold is None:
            continue
        pred = as_bool((run.get("parsed") or {}).get("risky")) if run.get("parse_ok") else None
        out.append(
            {
                "id": run["id"],
                "pair_id": gold["pair_id"],
                "surface": gold.get("surface"),
                "kind": gold.get("kind"),
                "check_id": gold.get("check_id"),
                "domain": gold.get("domain"),
                "gold": bool(gold["risky"]),
                "pred": pred,
                "parse_fail": pred is None,
                "ctx_incomplete": bool(run.get("ctx_incomplete")),
                "raw": (run.get("raw_output") or "")[:180],
                "clause": gold["clause"],
            }
        )
    return out


def pred_rows_from_file(path: Path, golds: dict, pred_key="pred") -> list[dict]:
    out = []
    for run in load_jsonl(path):
        gold = golds.get(run["id"])
        if gold is None:
            continue
        pred = run.get(pred_key)
        if pred is None:
            parsed_pred = None
        else:
            parsed_pred = bool(pred) if not isinstance(pred, str) else None
        out.append(
            {
                "id": run["id"],
                "pair_id": gold["pair_id"],
                "surface": gold.get("surface"),
                "kind": gold.get("kind"),
                "check_id": gold.get("check_id"),
                "domain": gold.get("domain"),
                "gold": bool(gold["risky"]),
                "pred": parsed_pred,
                "parse_fail": parsed_pred is None,
                "na": bool(run.get("na")),
                "clause": gold["clause"],
            }
        )
    return out


def cell(rows: list[dict]) -> str:
    if not rows:
        return "-"
    return f"{fmt(metric_ci(rows, 'bacc'))} / {fmt(metric_ci(rows, 'pair'))}"


def acc_ci(flags: list[bool]):
    rows = [{"id": str(i), "pair_id": str(i), "gold": True, "pred": bool(v), "parse_fail": False} for i, v in enumerate(flags)]
    # 위에서 gold True, pred True 면 맞음. 단순 정확도는 직접 부트스트랩한다.
    if not flags:
        return None
    arr = np.array(flags, dtype=float)
    point = float(arr.mean())
    rng = np.random.default_rng(SEED)
    stats = [float(arr[rng.integers(0, len(arr), len(arr))].mean()) for _ in range(N_BOOT)]
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return {"point": point, "lo": float(lo), "hi": float(hi), "n": len(flags), "n_groups": len(flags)}


def macro_f1(pairs: list[tuple[set, set]]) -> float | None:
    labels = sorted({lab for gold, _ in pairs for lab in gold})
    if not labels:
        return None
    f1s = []
    for lab in labels:
        tp = fp = fn = 0
        for gold, pred in pairs:
            in_g, in_p = lab in gold, lab in pred
            if in_g and in_p:
                tp += 1
            elif in_p:
                fp += 1
            elif in_g:
                fn += 1
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec))
    return float(sum(f1s) / len(f1s))


def main() -> None:
    law = {r["id"]: r for r in load_jsonl(EXP / "law_node_texts.jsonl")}
    cat = json.loads((WORK / "data_contract" / "catalog" / "catalog_v0.2.json").read_text(encoding="utf-8"))
    slot_name = {s["id"]: s["name"] for s in cat["slots"]}
    slot_name["기타"] = "기타"
    t3_gold = {r["id"]: r for r in load_jsonl(DATA / "t3_clauses.jsonl")}
    t1_gold = {r["id"]: r for r in load_jsonl(DATA / "t1_items.jsonl")}
    t2_gold = {r["id"]: r for r in load_jsonl(DATA / "t2_clauses.jsonl")}
    t4_gold = {r["id"]: r for r in load_jsonl(DATA / "t4_items.jsonl")}
    clauses = {}
    for task, name in (("T1", "t1_items.jsonl"), ("T3", "t3_clauses.jsonl"), ("T4", "t4_items.jsonl"), ("CF", "counterfactual.jsonl")):
        key = "q" if task == "T1" else "clause"
        for row in load_jsonl(DATA / name):
            clauses[(task, row["id"])] = row.get(key) or ""

    lines = ["# 설계 v2 실행", ""]
    art = (RUNS / "art54_check.txt").read_text(encoding="utf-8") if (RUNS / "art54_check.txt").exists() else ""
    lines += ["## 제54조 문자열 검사", "", "```", art.strip(), "```", ""]
    lines.append("채점 코드: `exp_v2/score_v2.py`. 부트스트랩 1,000회, seed 42. T3는 pair_id로 묶는다.")
    lines.append("균형 정확도 = (위험 재현율 + 안전 특이도) / 2. 쌍 정답률은 같은 pair·같은 surface의 위험·안전을 둘 다 맞힌 비율이다.")
    lines.append("")
    lines.append("## 표 1. T3 위험 판정 (균형 정확도 / 쌍 정답률)")
    lines.append("")
    lines.append("| 모델 | A0 | A1 | A2 | A3 | A4-BM25 | A4-bge |")
    lines.append("|---|---|---|---|---|---|---|")
    cached = {}
    for model in MODELS:
        cells = []
        for cond in T3_CONDS:
            rows = build_t3(model, cond, t3_gold)
            cached[(model, cond)] = rows
            cells.append(cell(rows))
        lines.append("| " + model + " | " + " | ".join(cells) + " |")
    rule_all = pred_rows_from_file(BASE / "rule_t3.jsonl", t3_gold)
    rule_rows = [r for r in rule_all if not r["na"]]
    rule_targets = {"L-T01", "L-T02", "L-T05", "L-T06", "H-T01", "H-T03", "H-T04", "D-T01"}
    rule_na = sum(1 for r in rule_all if r["na"] and r["check_id"] in rule_targets and r["kind"] == "numeric")
    tfidf_rows = pred_rows_from_file(BASE / "tfidf_t3.jsonl", t3_gold)
    lines.append("| 규칙(R) numeric | " + cell(rule_rows) + f" (N/A {rule_na}) | - | - | - | - | - |")
    lines.append("| 약관 TF-IDF(a) | " + cell(tfidf_rows) + " | - | - | - | - | - |")
    roberta_cells = []
    for seed in (42, 43, 44):
        path = BASE / f"roberta_t3_seed{seed}.jsonl"
        roberta_cells.append(cell(pred_rows_from_file(path, t3_gold)) if path.exists() else "학습 전")
    lines.append("| 약관 RoBERTa(b) seed 42/43/44 | " + " ; ".join(roberta_cells) + " | - | - | - | - | - |")
    lines.append("")
    lines.append("## 표 2. T4 근거 연결 top1")
    lines.append("")
    lines.append("T4 A1 자료는 정답 조문 본문이다. A1 칸은 채점하지 않고 무효(유출)로 둔다.")
    lines.append("")
    lines.append("| 모델 | A0 | A1 | A2 | A3 | A4-BM25 | A4-bge |")
    lines.append("|---|---|---|---|---|---|---|")
    t4_cache = {}
    t4_flags = {}
    for model in MODELS:
        cells = []
        for cond in T3_CONDS:
            flags = []
            flag_map = {}
            detail = []
            for run in runs(model, "T4", cond):
                gold = t4_gold.get(run["id"])
                if gold is None:
                    continue
                gold_lines = {choice_line(law[i]) for i in gold["gold"] if i in law}
                choice_lines = {choice_line(law[i]) for i in gold["choices"] if i in law}
                preds = []
                if run.get("parse_ok"):
                    raw_preds = (run.get("parsed") or {}).get("articles") or []
                    preds = [str(x).strip() for x in raw_preds]
                hit = bool(preds) and preds[0] in gold_lines
                flags.append(hit)
                flag_map[run["id"]] = hit
                outside = [p for p in preds if p not in choice_lines]
                detail.append({"id": run["id"], "hit": hit, "any": any(p in gold_lines for p in preds), "npred": len(preds), "out": len(outside), "npred_all": len(preds)})
            t4_cache[(model, cond)] = detail
            t4_flags[(model, cond)] = flag_map
            cells.append(LEAK if cond == "A1" else (fmt(acc_ci(flags)) if flags else "-"))
        lines.append("| " + model + " | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 표 3. 규칙형(T1 정확도) vs 적용형(T3 균형 정확도, T4 top1)")
    lines.append("")
    lines.append("| 모델 | T1 A0 | T1 A1 | T3 A0 | T3 A1 | T4 A0 | T4 A1 |")
    lines.append("|---|---|---|---|---|---|---|")
    t1_detail = []
    for model in MODELS:
        t1_stats = {}
        for cond in ("A0", "A1"):
            flags = []
            for run in runs(model, "T1", cond):
                gold = t1_gold[run["id"]]
                answer = str((run.get("parsed") or {}).get("answer") or "") if run.get("parse_ok") else ""
                kind = gold["answer_type"]
                if not run.get("parse_ok"):
                    ok = False
                elif kind == "number":
                    ok = number_ok(answer, gold["value"])
                elif kind == "yesno":
                    ok = yesno_ok(answer, bool(gold["value"]))
                else:
                    ok = text_ok(gold["id"], answer)
                flags.append(ok)
                if model == "Q8B" or True:
                    t1_detail.append((model, cond, gold["id"], ok, answer, gold.get("answer")))
            t1_stats[cond] = acc_ci(flags) if flags else None
        b0 = metric_ci(cached[(model, "A0")], "bacc") if cached[(model, "A0")] else None
        b1 = metric_ci(cached[(model, "A1")], "bacc") if cached[(model, "A1")] else None
        f0 = acc_ci([d["hit"] for d in t4_cache.get((model, "A0"), [])]) if t4_cache.get((model, "A0")) else None
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    fmt(t1_stats["A0"]),
                    fmt(t1_stats["A1"]),
                    fmt(b0),
                    fmt(b1),
                    fmt(f0),
                    LEAK,
                ]
            )
            + " |"
        )
    lines.append("")
    append_contrasts(lines, cached, t4_flags)
    append_ax7_check_gain(lines, cached)
    lines.append("")
    lines.append("## T1 문항")
    lines.append("")
    lines.append("| 문항 | 정답 | " + " | ".join(f"{m} {c}" for m in MODELS for c in ("A0", "A1")) + " |")
    lines.append("|---|---|" + "|".join(["---"] * (len(MODELS) * 2)) + "|")
    by_item = defaultdict(dict)
    for model, cond, item_id, ok, answer, _gold_answer in t1_detail:
        by_item[item_id][(model, cond)] = (ok, answer)
    for item_id, gold in t1_gold.items():
        cells = []
        for model in MODELS:
            for cond in ("A0", "A1"):
                ok, answer = by_item[item_id].get((model, cond), (None, ""))
                mark = "-" if ok is None else ("O" if ok else "X")
                cells.append(f"{mark} {answer[:40].replace('|', '/')}")
        lines.append(f"| {item_id} | {str(gold.get('answer')).replace('|', '/')} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## T2")
    lines.append("")
    lines.append("| 모델 | 조건 | top1 | macroF1 | n |")
    lines.append("|---|---|---|---|---:|")
    neigh = {r["id"]: r["neighbors"] for r in load_jsonl(RUNS / "t2_neighbors.jsonl")}

    def t2_eval(pred_of):
        pairs = []
        top = []
        for item_id, gold in t2_gold.items():
            gset = {slot_name.get(s, s) for s in gold["slots"]}
            pred = pred_of(item_id)
            if pred is None:
                continue
            pred_list = pred if isinstance(pred, list) else [pred]
            top.append(bool(pred_list) and pred_list[0] in gset)
            pairs.append((gset, set(pred_list[:2])))
        return acc_ci(top), macro_f1(pairs), len(top)

    for model in ("Q8B", "AX7"):
        for cond in ("A0", "K"):
            got = {}
            for run in runs(model, "T2", cond):
                labs = (run.get("parsed") or {}).get("labels") if run.get("parse_ok") else None
                got[run["id"]] = [str(x) for x in labs] if labs else []
            stat, f1, n = t2_eval(lambda i, got=got: got.get(i))
            lines.append(f"| {model} | {cond} | {fmt(stat)} | {f1 if f1 is not None else '-'} | {n} |")
    if neigh:
        stat, f1, n = t2_eval(lambda i: [neigh[i][0]["slot_name"]] if neigh.get(i) else None)
        lines.append(f"| bge-m3 kNN top1 | K | {fmt(stat)} | {f1} | {n} |")
        def vote5(i):
            if not neigh.get(i):
                return None
            return [Counter(n["slot_name"] for n in neigh[i][:5]).most_common(1)[0][0]]
        stat, f1, n = t2_eval(vote5)
        lines.append(f"| bge-m3 kNN top5 다수결 | K | {fmt(stat)} | {f1} | {n} |")
    for seed in (42, 43, 44):
        path = BASE / f"roberta_t2_seed{seed}.jsonl"
        if not path.exists():
            lines.append(f"| RoBERTa T2 seed {seed} | train | 학습 전 | - | 0 |")
            continue
        got = {r["id"]: [r["label"]] for r in load_jsonl(path)}
        stat, f1, n = t2_eval(lambda i, got=got: got.get(i))
        lines.append(f"| RoBERTa T2 seed {seed} | train | {fmt(stat)} | {f1} | {n} |")
    lines.append("")
    lines.append("## CF 일관성 (무관 변경, 원문 surface 0과 같은 판정)")
    lines.append("")
    lines.append("| 모델 | A0 | A1 |")
    lines.append("|---|---|---|")
    for model in ("Q8B", "AX7"):
        cells = []
        for cond in ("A0", "A1"):
            base = {r["id"]: as_bool((r.get("parsed") or {}).get("risky")) for r in runs(model, "T3", cond) if r.get("parse_ok")}
            flags = []
            for run in runs(model, "CF", cond):
                src = run.get("pair_id")
                pred = as_bool((run.get("parsed") or {}).get("risky")) if run.get("parse_ok") else None
                if pred is None or src not in base or base[src] is None:
                    continue
                flags.append(pred == base[src])
            cells.append(fmt(acc_ci(flags)) if flags else "-")
        lines.append(f"| {model} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## numeric / text")
    lines.append("")
    lines.append("| 모델 | 조건 | kind | 균형 정확도 | n |")
    lines.append("|---|---|---|---|---:|")
    for model in ("Q8B", "AX7"):
        for cond in ("A0", "A1"):
            for kind in ("numeric", "text"):
                rows = [r for r in cached[(model, cond)] if r["kind"] == kind]
                lines.append(f"| {model} | {cond} | {kind} | {fmt(metric_ci(rows, 'bacc'))} | {len(rows)} |")
    lines.append("")
    lines.append("## surface (0/A/B)")
    lines.append("")
    lines.append("균형 정확도. Q8B-T는 surface 0만 있다.")
    lines.append("")
    lines.append("| 모델 | 조건 | 0 | A | B |")
    lines.append("|---|---|---|---|---|")
    for model in MODELS:
        for cond in T3_CONDS:
            cells = []
            for surface in ("0", "A", "B"):
                rows = [r for r in cached[(model, cond)] if str(r.get("surface")) == surface]
                cells.append(fmt(metric_ci(rows, "bacc")) if rows else "-")
            lines.append(f"| {model} | {cond} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## check별 (A0, 균형 정확도)")
    lines.append("")
    lines.append("| check | Q8B | AX7 | n |")
    lines.append("|---|---|---|---:|")
    checks = sorted({r["check_id"] for r in cached.get(("Q8B", "A0"), [])})
    for check in checks:
        a = [r for r in cached.get(("Q8B", "A0"), []) if r["check_id"] == check]
        b = [r for r in cached.get(("AX7", "A0"), []) if r["check_id"] == check]
        lines.append(f"| {check} | {fmt(metric_ci(a, 'bacc'))} | {fmt(metric_ci(b, 'bacc'))} | {len(a)} |")
    lines.append("")
    lines.append("## ctx_incomplete 를 뺀 T3 A0/A1 균형 정확도")
    lines.append("")
    for model in ("Q8B", "AX7"):
        for cond in ("A0", "A1"):
            kept = build_t3(model, cond, t3_gold, drop_incomplete=True)
            dropped = len(cached[(model, cond)]) - len(kept)
            lines.append(f"- {model} {cond}: 제외 {dropped}, {fmt(metric_ci(kept, 'bacc'))}")
    lines.append("")
    lines.append("## 오답 샘플")
    lines.append("")
    for model in ("Q8B", "AX7"):
        for cond in T3_CONDS:
            wrong = [r for r in cached[(model, cond)] if r["pred"] != r["gold"]]
            lines.append(f"### {model} T3 {cond}")
            lines.append("")
            for row in wrong[:5]:
                snippet = row["clause"].replace("\n", " ")[:150]
                lines.append(f"- `{row['id']}` gold={row['gold']} pred={row['pred']} / {snippet}")
            lines.append("")
    lines.append("## Q8B-T thinking 길이")
    lines.append("")
    think = []
    for path in RUNS.glob("Q8B-T_*.jsonl"):
        for row in load_jsonl(path):
            think.append(int(row.get("reasoning_chars") or 0))
    if think:
        arr = np.array(think)
        lines.append(
            f"n={len(arr)}, mean={arr.mean():.1f}, p50={np.percentile(arr,50):.0f}, p90={np.percentile(arr,90):.0f}, max={arr.max()}"
        )
    else:
        lines.append("Q8B-T 본실행 결과가 없다.")
    lines.append("")
    lines.append("## 실행 시간과 설정")
    lines.append("")
    if (RUNS / "server_cmd.jsonl").exists():
        lines.append("서버 명령은 `exp_v2/runs/server_cmd.jsonl`에 원문으로 있다.")
    lines.append("Qwen3-8B GGUF Q8_0와 A.X-4.0 Light GGUF Q8_0는 llama.cpp b11755 (commit 704366d76, 0.7.0-dev)로 변환했다.")
    lines.append("AX7도 llama-server를 썼다. transformers bf16 경로는 쓰지 않았다.")
    lines.append("OPEN_LAW_KEY 길이 0. 법령 보충은 하지 않았다. 본문이 없는 노드는 ctx_incomplete로 표시했다.")
    lines.append("휴게 규칙은 `exp_v2/baselines/rules.py`에서 4시간 이상 30분, 8시간 이상 1시간으로 적용했다. work_hours_gt는 쓰지 않았다.")
    meta = BASE / "tfidf_meta.json"
    if meta.exists():
        lines.append("TF-IDF 메타: `" + meta.read_text(encoding="utf-8").replace("\n", " ") + "`")
    lines.append("GPU 로그: `exp_v2/runs/gpu.csv`.")
    lines.append("요청 지연의 합(파싱 성공·실패 포함, 중복 제거 후 파일 기준):")
    for model in MODELS:
        total = 0.0
        count = 0
        for path in RUNS.glob(f"{model}_*.jsonl"):
            for row in load_jsonl(path):
                total += float(row.get("latency_ms") or 0)
                count += 1
        if count:
            lines.append(f"- {model}: {count}건, 합계 {total/1000/3600:.2f}시간")
    for seed in (42, 43, 44):
        meta_path = BASE / f"roberta_meta_seed{seed}.json"
        if meta_path.exists():
            lines.append(f"- RoBERTa seed {seed}: {meta_path.read_text(encoding='utf-8')}")
    lines.append("Q8B-T 스모크 예상은 7.61시간이었고 8시간 미만이라 본실행을 했다. 실제 요청 합계는 위 줄이다.")
    lines.append("실행 도중 Q8B-T 프로세스가 두 개 떠서 같은 항목이 중복 기록되었다. 중복을 id 기준으로 한 줄만 남기고 한 프로세스로 재개했다.")
    text = "\n".join(lines) + "\n"
    (EXP / "RUN_REPORT.md").write_text(text, encoding="utf-8")
    print("wrote report", len(lines))


if __name__ == "__main__":
    main()
