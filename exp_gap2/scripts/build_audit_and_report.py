# -*- coding: utf-8 -*-
"""audit CSV + GAP2_REPORT.md 생성."""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"
DATA = G2 / "data"
AUDIT = G2 / "audit"

sys.path.insert(0, str(G2))
from score2 import (  # noqa: E402
    auroc_bootstrap,
    balanced_acc_cv,
    balanced_acc_fixed,
    fmt_ci,
    gap_label,
    load_jsonl,
    paired_diff_ci,
    score_e1,
    score_e2,
)

SEED = 42


def pct(d):
    return fmt_ci(d, pct=True)


def write_audit():
    AUDIT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    test = load_jsonl(DATA / "e2_test1000.jsonl")
    by_id = {r["id"]: r for r in test}
    p8 = {r["id"]: r for r in load_jsonl(OUT / "8B_E2_C2.jsonl")}
    p32 = {r["id"]: r for r in load_jsonl(OUT / "32B_E2_C2.jsonl")}

    # (a) 32B top1 not in gold
    a_pool = []
    for g in test:
        r = p32.get(g["id"])
        if not r or not r.get("parse_ok") or not isinstance(r.get("parsed"), dict):
            continue
        arts = r["parsed"].get("articles") or []
        if not arts or arts[0] not in set(g["gold_articles"]):
            a_pool.append(g["id"])
    a_ids = rng.sample(a_pool, min(60, len(a_pool)))
    b_ids = rng.sample([g["id"] for g in test], min(40, len(test)))
    # dedupe prefer a
    seen = set(a_ids)
    b_ids = [i for i in b_ids if i not in seen][:40]

    e2_rows = []
    for sid, ids in (("a", a_ids), ("b", b_ids)):
        for iid in ids:
            g = by_id[iid]
            r8, r32 = p8.get(iid, {}), p32.get(iid, {})
            e2_rows.append(
                {
                    "id": iid,
                    "표본구분": sid,
                    "조항전문": g["clause"],
                    "gold조항": json.dumps(g["gold_articles"], ensure_ascii=False),
                    "relateLaword원문": g.get("relate") or "",
                    "해설원문": g.get("illdcssBasiss") or "",
                    "8B_articles": json.dumps((r8.get("parsed") or {}).get("articles"), ensure_ascii=False) if r8.get("parsed") else "",
                    "8B_reason": (r8.get("parsed") or {}).get("reason", "") if r8.get("parsed") else "",
                    "32B_articles": json.dumps((r32.get("parsed") or {}).get("articles"), ensure_ascii=False) if r32.get("parsed") else "",
                    "32B_reason": (r32.get("parsed") or {}).get("reason", "") if r32.get("parsed") else "",
                }
            )
    e2p = AUDIT / "audit_e2.csv"
    with e2p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(e2_rows[0].keys()) if e2_rows else ["id"])
        w.writeheader()
        w.writerows(e2_rows)

    # E1: both models wrong on C1 and C2
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    e1_rows = []
    for g in e1:
        truth = bool(g["label_risky"])
        wrong_all = True
        outs = {}
        for model in ("8B", "32B"):
            for cond in ("C1", "C2"):
                rows = {r["id"]: r for r in load_jsonl(G1 / "out" / f"{model}_E1_{cond}.jsonl")}
                r = rows.get(g["id"], {})
                parsed = r.get("parsed") if isinstance(r.get("parsed"), dict) else None
                pred = bool(parsed.get("risky")) if parsed and "risky" in parsed else None
                outs[f"{model}_{cond}"] = {
                    "risky": pred,
                    "reason": (parsed or {}).get("reason", ""),
                    "raw": (r.get("raw_output") or "")[:500],
                }
                if pred is None or pred == truth:
                    wrong_all = False
        if wrong_all:
            e1_rows.append(
                {
                    "id": g["id"],
                    "분야": g.get("field", ""),
                    "조항전문": g["clause"],
                    "gold": truth,
                    "해설원문": g.get("illdcssBasiss") or "",
                    "8B_C1": json.dumps(outs["8B_C1"], ensure_ascii=False),
                    "8B_C2": json.dumps(outs["8B_C2"], ensure_ascii=False),
                    "32B_C1": json.dumps(outs["32B_C1"], ensure_ascii=False),
                    "32B_C2": json.dumps(outs["32B_C2"], ensure_ascii=False),
                }
            )
            if len(e1_rows) >= 50:
                break
    e1p = AUDIT / "audit_e1.csv"
    with e1p.open("w", encoding="utf-8-sig", newline="") as f:
        fields = list(e1_rows[0].keys()) if e1_rows else ["id"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(e1_rows)
    return {"audit_e2": str(e2p), "audit_e2_n": len(e2_rows), "audit_e1": str(e1p), "audit_e1_n": len(e1_rows)}


def score_baseline_e2(name, gold, excl_ids=None):
    rows = load_jsonl(OUT / f"baseline_e2_{name}.jsonl")
    # convert to parsed form
    pred = [{"id": r["id"], "parsed": {"articles": r["articles"]}, "parse_ok": True} for r in rows]
    mask = {i: True for i in (excl_ids or [])}
    return score_e2(gold, pred, exclude_mask=mask if excl_ids else None)


def logprob_table():
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    gold = {r["id"]: r for r in e1}
    gate = {}
    gp = OUT / "e1_logprob_gate.json"
    if gp.exists():
        gate = json.loads(gp.read_text(encoding="utf-8"))
    lines = []
    auroc_diffs = {}
    rows_out = []
    for model in ("8B", "32B"):
        for cond in ("C1", "C2"):
            lp = load_jsonl(OUT / f"e1_logprob_{model}_{cond}.jsonl")
            y_true, y_score = [], []
            for r in lp:
                g = gold.get(r["id"])
                if not g or r.get("score") is None:
                    continue
                y_true.append(1 if g["label_risky"] else 0)
                y_score.append(float(r["score"]))
            au = auroc_bootstrap(y_true, y_score) if y_true else {"mean": None}
            ba05 = balanced_acc_fixed(y_true, y_score, 0.5) if y_true else None
            bacv = balanced_acc_cv(y_true, y_score) if y_true else None
            # also discrete metrics from score>0.5
            pred_rows = [
                {"id": r["id"], "risky": (r["score"] > 0.5) if r.get("score") is not None else None, "parse_ok": r.get("score") is not None, "score": r.get("score")}
                for r in lp
            ]
            sc = score_e1(e1, pred_rows)
            rows_out.append(
                {
                    "model": model,
                    "cond": cond,
                    "accuracy": sc["accuracy"],
                    "recall": sc["recall"],
                    "false_alarm": sc["false_alarm"],
                    "auroc": au,
                    "ba_05": ba05,
                    "ba_cv": bacv,
                    "y_true": y_true,
                    "y_score": y_score,
                }
            )
    for cond in ("C1", "C2"):
        a32 = next(r for r in rows_out if r["model"] == "32B" and r["cond"] == cond)
        a8 = next(r for r in rows_out if r["model"] == "8B" and r["cond"] == cond)
        # paired AUROC diff via bootstrap of score vectors aligned by id order of e1
        # rebuild aligned
        lp8 = {r["id"]: r for r in load_jsonl(OUT / f"e1_logprob_8B_{cond}.jsonl")}
        lp32 = {r["id"]: r for r in load_jsonl(OUT / f"e1_logprob_32B_{cond}.jsonl")}
        from sklearn.metrics import roc_auc_score

        rng = random.Random(SEED)
        diffs = []
        ids = [g["id"] for g in e1 if g["id"] in lp8 and g["id"] in lp32 and lp8[g["id"]].get("score") is not None and lp32[g["id"]].get("score") is not None]
        if ids:
            yt = [1 if gold[i]["label_risky"] else 0 for i in ids]
            for _ in range(1000):
                idx = [rng.randrange(len(ids)) for _ in range(len(ids))]
                ytb = [yt[j] for j in idx]
                if len(set(ytb)) < 2:
                    continue
                s8 = [float(lp8[ids[j]]["score"]) for j in idx]
                s32 = [float(lp32[ids[j]]["score"]) for j in idx]
                diffs.append(roc_auc_score(ytb, s32) - roc_auc_score(ytb, s8))
            diffs.sort()
            auroc_diffs[cond] = {
                "mean": sum(diffs) / len(diffs) if diffs else None,
                "lo": diffs[int(0.025 * len(diffs))] if diffs else None,
                "hi": diffs[int(0.975 * len(diffs)) - 1] if diffs else None,
                "n": len(ids),
            }
        else:
            auroc_diffs[cond] = {"mean": None, "lo": None, "hi": None, "n": 0}
    return rows_out, auroc_diffs, gate


def error_samples(cond, n=5):
    test = load_jsonl(DATA / "e2_test1000.jsonl")
    if cond == "R":
        test = load_jsonl(G1 / "data" / "e2.jsonl")
    by = {r["id"]: r for r in test}
    p8 = {r["id"]: r for r in load_jsonl(OUT / f"8B_E2_{cond}.jsonl")}
    p32 = {r["id"]: r for r in load_jsonl(OUT / f"32B_E2_{cond}.jsonl")}
    samples = []
    for g in test:
        r32 = p32.get(g["id"])
        if not r32 or not isinstance(r32.get("parsed"), dict):
            continue
        arts = r32["parsed"].get("articles") or []
        if arts and arts[0] in set(g["gold_articles"]):
            continue
        r8 = p8.get(g["id"], {})
        samples.append(
            {
                "id": g["id"],
                "clause200": g["clause"][:200],
                "gold": g["gold_articles"],
                "8B": (r8.get("parsed") or {}).get("articles") if r8 else None,
                "32B": arts,
            }
        )
        if len(samples) >= n:
            break
    return samples


def build_report(audit_meta):
    lines = []
    lines.append("# GAP-2 실험 보고서\n")
    lines.append("실험 폴더: `exp_gap2/`. GAP-1은 읽기 전용.\n")

    # --- Table A ---
    lines.append("## 표 A. E1\n")
    lines.append("| 모델 | 조건 | accuracy | 재현율 | 거짓경보 | AUROC(CI) | 균형정확도(CV 문턱) |")
    lines.append("|---|---|---|---|---|---|---|")
    try:
        lp_rows, auroc_diffs, gate = logprob_table()
    except Exception as e:
        lp_rows, auroc_diffs, gate = [], {}, {"error": str(e)}
        lines.append(f"\n(logprob 표 생성 오류: {e})\n")

    for r in lp_rows:
        au = r["auroc"]
        au_s = f"{au['mean']:.3f} [{au['lo']:.3f}, {au['hi']:.3f}]" if au.get("mean") is not None else "미확인"
        bacv = f"{100*r['ba_cv']:.1f}%" if r.get("ba_cv") is not None else "미확인"
        lines.append(
            f"| {r['model']} | {r['cond']}(logprob) | {pct(r['accuracy'])} | {pct(r['recall'])} | {pct(r['false_alarm'])} | {au_s} | {bacv} |"
        )

    # kNN baselines
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    for name in ("K1", "K5"):
        rows = load_jsonl(OUT / f"baseline_e1_{name}.jsonl")
        if not rows:
            continue
        pred = [{"id": r["id"], "risky": r["risky"], "parse_ok": True, "score": r.get("score", 1.0 if r["risky"] else 0.0)} for r in rows]
        sc = score_e1(e1, pred)
        au = auroc_bootstrap(sc["y_true"], sc["y_score"])
        au_s = f"{au['mean']:.3f} [{au['lo']:.3f}, {au['hi']:.3f}]" if au.get("mean") is not None else "미확인"
        lines.append(
            f"| kNN | {name} | {pct(sc['accuracy'])} | {pct(sc['recall'])} | {pct(sc['false_alarm'])} | {au_s} | — |"
        )
        # excl neardup
        mask_path = DATA / "e1_neardup095_mask.npy"
        if mask_path.exists():
            import numpy as np

            mask_arr = np.load(mask_path)
            excl = {e1[i]["id"]: True for i in range(len(e1)) if mask_arr[i]}
            sc2 = score_e1(e1, pred, exclude_mask=excl)
            au2 = auroc_bootstrap(sc2["y_true"], sc2["y_score"])
            au2_s = f"{au2['mean']:.3f} [{au2['lo']:.3f}, {au2['hi']:.3f}]" if au2.get("mean") is not None else "미확인"
            lines.append(
                f"| kNN | {name} excl≥0.95 | {pct(sc2['accuracy'])} | {pct(sc2['recall'])} | {pct(sc2['false_alarm'])} | {au2_s} | — |"
            )

    for cond, d in auroc_diffs.items():
        if d.get("mean") is None:
            verdict = "미확인"
        elif d["lo"] is not None and d["lo"] <= 0 <= (d["hi"] or 0):
            verdict = "E1 갭은 문턱 차이로 설명됨"
        else:
            verdict = "판별력 차이 있음"
        lines.append(
            f"\n**32B−8B AUROC 차이 ({cond})**: "
            f"{d['mean']:+.3f} [{d['lo']:.3f}, {d['hi']:.3f}] (n={d['n']}) → **{verdict}**\n"
            if d.get("mean") is not None
            else f"\n**32B−8B AUROC 차이 ({cond})**: 미확인\n"
        )

    # --- Table B ---
    lines.append("\n## 표 B. E2 (test1000)\n")
    lines.append("| 모델/기준선 | 조건 | top1(CI) | any_hit | exact | macroF1 | top1_excl6 | n_pred_mean | ood |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    gold = load_jsonl(DATA / "e2_test1000.jsonl")
    excl_ids = []
    meta_nd = OUT / "baseline_e2_meta.json"
    if meta_nd.exists():
        excl_ids = json.loads(meta_nd.read_text(encoding="utf-8")).get("neardup_ids", [])

    def row_e2(label, cond, sc):
        lines.append(
            f"| {label} | {cond} | {pct(sc['top1'])} | {pct(sc['any_hit'])} | {pct(sc['exact'])} | "
            f"{sc['macroF1_point']:.3f} | {pct(sc['top1_excl6'])} | {sc['n_pred_mean']['mean']:.2f} | {pct(sc['ood'])} |"
        )

    for name in ("B0", "B1", "B2", "B3"):
        if not (OUT / f"baseline_e2_{name}.jsonl").exists():
            continue
        sc = score_baseline_e2(name, gold)
        row_e2(name, "기준선", sc)
        if excl_ids:
            sc2 = score_baseline_e2(name, gold, excl_ids=excl_ids)
            row_e2(f"{name} excl≥0.95", "기준선", sc2)

    e2_scores = {}
    for model in ("8B", "32B"):
        for cond in ("C2", "C5", "C4", "R"):
            p = OUT / f"{model}_E2_{cond}.jsonl"
            if not p.exists():
                continue
            g = gold if cond != "R" else load_jsonl(G1 / "data" / "e2.jsonl")
            if cond == "C4":
                g = gold[:500]
            if cond == "C5":
                # may be reduced
                preds = load_jsonl(p)
                ids = {r["id"] for r in preds}
                g = [x for x in gold if x["id"] in ids]
            sc = score_e2(g, load_jsonl(p))
            e2_scores[(model, cond)] = sc
            row_e2(model, cond, sc)

    for cond in ("C2", "C5", "C4", "R"):
        if ("32B", cond) in e2_scores and ("8B", cond) in e2_scores:
            a = e2_scores[("32B", cond)]["top1_vals"]
            b = e2_scores[("8B", cond)]["top1_vals"]
            n = min(len(a), len(b))
            diff = paired_diff_ci(a[:n], b[:n])
            lines.append(f"\n**32B−8B top1 ({cond})**: {pct(diff)} → {gap_label(diff)}\n")

    # --- Table C ---
    lines.append("\n## 표 C. 적용 추론·thinking\n")
    lines.append("| 모델 | C4 top1(CI) | 무작위 33.3% | thinking 끔 C2 | thinking 켬 C2 | 차이 |")
    lines.append("|---|---|---|---|---|---|")
    g1_e2 = load_jsonl(G1 / "data" / "e2.jsonl")
    for model in ("8B", "32B"):
        c4 = e2_scores.get((model, "C4"))
        c4s = pct(c4["top1"]) if c4 else "미확인"
        # thinking off = GAP-1 C2 on e2 200
        off = score_e2(g1_e2, load_jsonl(G1 / "out" / f"{model}_E2_C2.jsonl")) if (G1 / "out" / f"{model}_E2_C2.jsonl").exists() else None
        on_p = OUT / f"{model}_E2_C2_thinking.jsonl"
        on = score_e2(g1_e2, load_jsonl(on_p)) if on_p.exists() and load_jsonl(on_p) else None
        off_s = pct(off["top1"]) if off else "미확인"
        on_s = pct(on["top1"]) if on else "미확인"
        if off and on:
            n = min(len(off["top1_vals"]), len(on["top1_vals"]))
            # align by intersecting ids would be better
            d = paired_diff_ci(on["top1_vals"][:n], off["top1_vals"][:n])
            diff_s = pct(d)
        else:
            diff_s = "미확인"
        lines.append(f"| {model} | {c4s} | 33.3% | {off_s} | {on_s} | {diff_s} |")

    # detailed sections
    lines.append("\n---\n")
    lines.append("## 1. 데이터 준비\n")
    for fn in ("e2_prep_meta.json", "e1_prep_meta.json"):
        p = DATA / fn
        if p.exists():
            lines.append(f"### {fn}\n```json\n{p.read_text(encoding='utf-8')}\n```\n")

    lines.append("## 2. 근접 중복 점검\n")
    for name in ("e1", "e2"):
        p = DATA / f"neardup_{name}.json"
        if not p.exists():
            lines.append(f"{name}: 미확인\n")
            continue
        nd = json.loads(p.read_text(encoding="utf-8"))
        lines.append(
            f"### {name}\n- sim≥0.95 비율: {nd['rate_sim_ge_0_95']:.3f} ({nd['n_sim_ge_0_95']}/{nd['n_query']})\n"
            f"- 그중 라벨/조항 집합 상이: {nd['rate_opposite_among_ge095']:.3f} ({nd['n_opposite_among_ge095']})\n"
            f"- 코드: `{nd['code']}`\n"
        )
        lines.append("#### 쌍 샘플 (최대 10)\n")
        for i, pair in enumerate(nd.get("pairs_sample", [])[:10], 1):
            lines.append(
                f"**쌍 {i}** sim={pair['sim']:.4f} opp={pair['opposite']} "
                f"q={pair.get('q_id')} c={pair.get('c_id')} labels={pair.get('q_label')}/{pair.get('c_label')}\n\n"
                f"- Q: {pair['q_clause']}\n\n- C: {pair['c_clause']}\n"
            )

    lines.append("## 3. E1 logprob 일치 게이트\n")
    gp = OUT / "e1_logprob_gate.json"
    if gp.exists():
        lines.append(f"```json\n{gp.read_text(encoding='utf-8')}\n```\n")
    else:
        lines.append("미확인\n")

    lines.append("## 4. R 재현성\n")
    for model in ("8B", "32B"):
        p = OUT / f"repro_R_{model}.json"
        if p.exists():
            lines.append(f"### {model}\n```json\n{p.read_text(encoding='utf-8')}\n```\n")

    lines.append("## 5. 스모크·속도·n 축소\n")
    for model in ("8B", "32B"):
        p = OUT / f"smoke_timing_{model}.json"
        if p.exists():
            lines.append(f"### {model}\n```json\n{p.read_text(encoding='utf-8')}\n```\n")
    if (OUT / "thinking_n_reduced.json").exists():
        lines.append(f"thinking n 축소: `{OUT / 'thinking_n_reduced.json'}`\n")

    lines.append("## 6. 조건별 오답 샘플\n")
    for cond in ("C2", "C5", "C4", "R"):
        samples = error_samples(cond, 5)
        lines.append(f"### {cond}\n")
        if not samples:
            lines.append("미확인 또는 오답 없음\n")
            continue
        for s in samples:
            lines.append(
                f"- `{s['id']}` gold={s['gold']} 8B={s['8B']} 32B={s['32B']}\n  조항: {s['clause200']}\n"
            )

    lines.append("## 7. thinking 샘플 3건\n")
    for model in ("8B", "32B"):
        rows = load_jsonl(OUT / f"{model}_E2_C2_thinking.jsonl")[:3]
        lines.append(f"### {model}\n")
        if not rows:
            lines.append("미확인\n")
            continue
        for r in rows:
            think = (r.get("thinking") or "")[:800]
            lines.append(f"**{r['id']}**\n\nthinking:\n```\n{think}\n```\n\n최종: `{r.get('parsed')}`\n")

    lines.append("## 8. audit 파일\n")
    lines.append(
        f"- `{audit_meta.get('audit_e2')}` n={audit_meta.get('audit_e2_n')}\n"
        f"- `{audit_meta.get('audit_e1')}` n={audit_meta.get('audit_e1_n')}\n"
        "판정은 하지 않음.\n"
    )

    lines.append("## 9. 기록 사항\n")
    lines.append(
        "- 프롬프트: GAP-1 `prompts/` 복사 + `user_e2_c4.txt` 신규(명세 문구).\n"
        "- GAP-1 원본 수정 없음.\n"
        f"- 실행 산출: `exp_gap2/out/`\n"
    )
    # failures
    fails = list(OUT.glob("smoke_FAIL_*.json")) + list(OUT.glob("thinking_FAIL_*.json"))
    if fails:
        lines.append("- 실패 플래그: " + ", ".join(p.name for p in fails) + "\n")
    else:
        lines.append("- 실패 플래그: 없음(또는 미생성)\n")

    report = G2 / "GAP2_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", report)
    return str(report)


def main():
    audit_meta = write_audit()
    build_report(audit_meta)
    print(audit_meta)


if __name__ == "__main__":
    main()
