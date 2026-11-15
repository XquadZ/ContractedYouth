# -*- coding: utf-8 -*-
"""GAP-2 E2 실행: smoke → R → C2 → C5 → C4. 8B 전체 → 32B 전체."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
DATA = G2 / "data"
OUT = G2 / "out"
PROMPTS = G2 / "prompts"
RET = G2 / "retrieval"

sys.path.insert(0, str(G1 / "scripts"))
from llm_server import chat, start_server, stop_server  # noqa: E402
from run_gap1 import parse_json_output  # noqa: E402

SYSTEM_NORAG = (PROMPTS / "system_norag.txt").read_text(encoding="utf-8")
SYSTEM_RAG = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
USER_E2 = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")
USER_E2_C4 = (PROMPTS / "user_e2_c4.txt").read_text(encoding="utf-8")

ARTICLE_TITLES = {
    6: "일반원칙",
    7: "면책조항의 금지",
    8: "손해배상액의 예정",
    9: "계약의 해제·해지",
    10: "채무의 이행",
    11: "고객의 권익 보호",
    12: "의사표시의 의제",
    13: "대리인의 책임",
    14: "소송제기 관련 조항",
}
ALL_ARTS = list(range(6, 15))


def load_jsonl(p: Path):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(p: Path, row: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_ids(p: Path) -> set:
    return {r["id"] for r in load_jsonl(p) if "id" in r}


def e2_choices_line(arts=None):
    arts = arts or ALL_ARTS
    return ", ".join(f"제{a}조({ARTICLE_TITLES.get(a, '')})" for a in arts)


def load_c2_material():
    p = G1 / "retrieval" / "c2_e1e2_material.txt"
    return p.read_text(encoding="utf-8")


def split_articles_text(material: str) -> dict:
    """약관법 전문을 조항별로 대략 분할. C4용."""
    # try numbered sections
    parts = {}
    # patterns like "제6조" headings
    matches = list(re.finditer(r"(제\s*([6-9]|1[0-4])\s*조[^\n]*)", material))
    if not matches:
        return {a: material for a in ALL_ARTS}
    for i, m in enumerate(matches):
        a = int(re.search(r"(\d+)", m.group(1)).group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(material)
        parts[a] = material[start:end].strip()
    return parts


def ensure_c4_candidates(test500, article_parts, seed=42):
    outp = DATA / "e2_c4_candidates.jsonl"
    if outp.exists() and len(load_jsonl(outp)) >= len(test500):
        return {r["id"]: r for r in load_jsonl(outp)}
    rng = random.Random(seed)
    rows = []
    for ex in test500:
        gold = list(ex["gold_articles"])
        g = rng.choice(gold)
        non = [a for a in ALL_ARTS if a not in gold]
        wrong = rng.sample(non, 2) if len(non) >= 2 else non
        cands = [g] + wrong
        rng.shuffle(cands)
        materials = "\n\n".join(article_parts.get(a, f"제{a}조") for a in cands)
        choices = e2_choices_line(cands)
        row = {
            "id": ex["id"],
            "candidates": cands,
            "gold_pick": g,
            "choices_line": choices,
            "material": materials,
        }
        rows.append(row)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {r["id"]: r for r in rows}


def build_messages_e2(cond, item, ctx):
    if cond == "C4":
        c4 = ctx["c4"][item["id"]]
        system = SYSTEM_RAG
        user_body = USER_E2_C4.replace("{choices}", c4["choices_line"]).replace("{clause}", item["clause"])
        material = c4["material"]
        user = f"<자료>\n{material}\n</자료>\n\n{user_body}\n/no_think"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    choices = ctx["choices"]
    user_body = USER_E2.replace("{clause}", item["clause"]).replace("{choices}", choices)
    system = SYSTEM_RAG
    if cond == "C2" or cond == "R":
        material = ctx["c2"]
    elif cond == "C5":
        pack = ctx["c5_packs"].get(item["id"], "")
        material = (
            f"[약관법 조문]\n{ctx['c2']}\n\n"
            f"[유사 판정 사례] 아래는 비슷한 조항이 과거에 어느 조항 문제로 판정되었는지 보여 주는 참고 사례다. "
            f"사례가 지금 조항과 다를 수 있으니 그대로 따르지 말고 조항 문구를 직접 판단하라.\n{pack}"
        )
    else:
        material = ctx["c2"]
    user = f"<자료>\n{material}\n</자료>\n\n{user_body}\n/no_think"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_items(model, cond, items, ctx, out_name=None):
    outp = OUT / (out_name or f"{model}_E2_{cond}.jsonl")
    done = existing_ids(outp)
    latencies = []
    parse_oks = []
    t0 = time.perf_counter()
    for item in items:
        if item["id"] in done:
            continue
        messages = build_messages_e2(cond, item, ctx)
        try:
            resp = chat(messages, temperature=0.0, max_tokens=256)
            raw = resp["content"]
        except Exception as e:
            raw = ""
            resp = {"latency_total_ms": None, "error": str(e)}
        parsed, ok = parse_json_output(raw)
        row = {
            "id": item["id"],
            "cond": cond,
            "raw_output": raw,
            "parsed": parsed,
            "parse_ok": ok,
            "latency_total_ms": resp.get("latency_total_ms"),
            "error": resp.get("error"),
        }
        append_jsonl(outp, row)
        if resp.get("latency_total_ms"):
            latencies.append(resp["latency_total_ms"])
        parse_oks.append(ok)
    elapsed = time.perf_counter() - t0
    n_new = len(parse_oks)
    return {
        "n_new": n_new,
        "n_total": len(load_jsonl(outp)),
        "parse_rate": (sum(parse_oks) / n_new) if n_new else None,
        "mean_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "elapsed_s": elapsed,
        "out": str(outp),
    }


def load_ctx(n_c5=None):
    c2 = load_c2_material()
    parts = split_articles_text(c2)
    test = load_jsonl(DATA / "e2_test1000.jsonl")
    test500 = test[:500]
    c4 = ensure_c4_candidates(test500, parts)
    packs = {}
    for packs_path in (RET / "c5_neighbor_packs.json", DATA / "e2_c5_neighbors.json"):
        if packs_path.exists():
            packs = json.loads(packs_path.read_text(encoding="utf-8"))
            break
    choices = json.loads((G1 / "data" / "e2_choices.json").read_text(encoding="utf-8"))["choices_line"]
    g1_e2 = load_jsonl(G1 / "data" / "e2.jsonl")
    return {
        "c2": c2,
        "article_parts": parts,
        "c4": c4,
        "c5_packs": packs,
        "choices": choices,
        "test": test,
        "test500": test500,
        "g1_e2": g1_e2,
        "n_c5": n_c5,
    }


def smoke(model, ctx):
    """C5·C4 × 5건. 파싱률 ≥95%."""
    stats = {}
    for cond, items in (("C5", ctx["test"][:5]), ("C4", ctx["test500"][:5])):
        # use separate smoke files
        out_name = f"smoke_{model}_E2_{cond}.jsonl"
        # clear old smoke for fresh measure? keep append; delete content if exists for clean smoke
        p = OUT / out_name
        if p.exists():
            p.unlink()
        st = run_items(model, cond, items, ctx, out_name=out_name)
        stats[cond] = st
        print("SMOKE", model, cond, st)
    return stats


def estimate_hours(smoke_stats, n_c2=1000, n_c5=1000, n_c4=500, n_r=200):
    """Estimate from smoke mean latency."""
    # prefer C5 latency as heavier
    lat = None
    for cond in ("C5", "C4"):
        if smoke_stats.get(cond, {}).get("mean_latency_ms"):
            lat = smoke_stats[cond]["mean_latency_ms"]
            break
    if not lat:
        return {"hours_one_model": None, "reduce_c5": False}
    # R and C2 similar to C2; C5 longer material → use smoke C5; C4 shorter
    lat_c2 = smoke_stats.get("C4", {}).get("mean_latency_ms") or lat
    lat_c5 = smoke_stats.get("C5", {}).get("mean_latency_ms") or lat
    lat_c4 = smoke_stats.get("C4", {}).get("mean_latency_ms") or lat
    total_ms = n_r * lat_c2 + n_c2 * lat_c2 + n_c5 * lat_c5 + n_c4 * lat_c4
    hours = total_ms / 1000 / 3600
    reduce = hours > 12
    return {
        "lat_c2_ms": lat_c2,
        "lat_c5_ms": lat_c5,
        "lat_c4_ms": lat_c4,
        "hours_one_model": hours,
        "hours_both": hours * 2,
        "reduce_c5": reduce,
        "n_c5_planned": 500 if reduce else n_c5,
    }


def run_repro_r(model, ctx):
    """GAP-1 E2 200건 C2 재실행. 일치율 비교."""
    st = run_items(model, "R", ctx["g1_e2"], ctx, out_name=f"{model}_E2_R.jsonl")
    # compare with gap1
    g1 = {r["id"]: r for r in load_jsonl(G1 / "out" / f"{model}_E2_C2.jsonl")}
    g2 = load_jsonl(OUT / f"{model}_E2_R.jsonl")
    agree = []
    for r in g2:
        a = g1.get(r["id"])
        if not a:
            continue
        pa = a.get("parsed") if isinstance(a.get("parsed"), dict) else None
        pb = r.get("parsed") if isinstance(r.get("parsed"), dict) else None
        if pa and pb:
            aa = tuple(sorted(int(x) for x in (pa.get("articles") or [])))
            bb = tuple(sorted(int(x) for x in (pb.get("articles") or [])))
            agree.append(1.0 if aa == bb else 0.0)
        else:
            agree.append(1.0 if (a.get("raw_output") or "") == (r.get("raw_output") or "") else 0.0)
    rate = sum(agree) / len(agree) if agree else 0.0
    meta = {"run": st, "agree_rate": rate, "n_compared": len(agree), "ok_ge_95": rate >= 0.95}
    (OUT / f"repro_R_{model}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPRO R", model, meta)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["smoke", "full", "continue"], default="full")
    ap.add_argument("--model", choices=["8B", "32B", "both"], default="both")
    ap.add_argument("--skip-smoke", action="store_true")
    ap.add_argument("--n-c5", type=int, default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    RET.mkdir(parents=True, exist_ok=True)
    ctx = load_ctx()
    models = ["8B", "32B"] if args.model == "both" else [args.model]
    timing = {}

    for model in models:
        print("=== start model", model)
        start_server(model)
        try:
            if not args.skip_smoke and args.mode in ("smoke", "full"):
                sm = smoke(model, ctx)
                est = estimate_hours(sm)
                timing[model] = {"smoke": sm, "estimate": est}
                (OUT / f"smoke_timing_{model}.json").write_text(
                    json.dumps(timing[model], ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print("ESTIMATE", model, est)
                for cond, st in sm.items():
                    if st.get("parse_rate") is not None and st["parse_rate"] < 0.95:
                        print("SMOKE FAIL", model, cond, st["parse_rate"])
                        (OUT / f"smoke_FAIL_{model}_{cond}.json").write_text(
                            json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        # stop only that condition later
                if args.mode == "smoke":
                    continue
                n_c5 = args.n_c5 or est["n_c5_planned"]
            else:
                n_c5 = args.n_c5 or 1000
                # load prior estimate if any
                tp = OUT / f"smoke_timing_{model}.json"
                if tp.exists():
                    timing[model] = json.loads(tp.read_text(encoding="utf-8"))
                    n_c5 = args.n_c5 or timing[model].get("estimate", {}).get("n_c5_planned", 1000)

            # check smoke fail flags
            fail_c5 = (OUT / f"smoke_FAIL_{model}_C5.json").exists()
            fail_c4 = (OUT / f"smoke_FAIL_{model}_C4.json").exists()

            # 1 R
            run_repro_r(model, ctx)
            # 2 C2
            run_items(model, "C2", ctx["test"], ctx)
            # 3 C5
            if not fail_c5:
                run_items(model, "C5", ctx["test"][:n_c5], ctx)
            else:
                print("SKIP C5 due to smoke fail")
            # 4 C4
            if not fail_c4:
                run_items(model, "C4", ctx["test500"], ctx)
            else:
                print("SKIP C4 due to smoke fail")
        finally:
            stop_server()
        print("=== done model", model)

    (OUT / "run_timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ALL DONE")


if __name__ == "__main__":
    main()
