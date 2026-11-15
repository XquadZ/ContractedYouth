# -*- coding: utf-8 -*-
"""GAP-1 스모크/본실행. 순서: 8B 전체 → 32B 전체. append jsonl, 기존 id 스킵."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from llm_server import chat, start_server, stop_server

EXP = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1")
DATA = EXP / "data"
RET = EXP / "retrieval"
PROMPTS = EXP / "prompts"
OUT = EXP / "out"

SYSTEM_NORAG = (PROMPTS / "system_norag.txt").read_text(encoding="utf-8")
SYSTEM_RAG = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
USER_E1 = (PROMPTS / "user_e1.txt").read_text(encoding="utf-8")
USER_E2 = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")
USER_E3 = (PROMPTS / "user_e3.txt").read_text(encoding="utf-8")


def load_jsonl(p: Path):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(p: Path, row: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_ids(p: Path) -> set:
    return {r["id"] for r in load_jsonl(p) if "id" in r}


def parse_json_output(text: str):
    if text is None:
        return None, False
    t = text.strip()
    # strip think tags / markdown fences
    t = re.sub(r"<think>[\s\S]*?</think>", "", t).strip()
    t = re.sub(r"/no_think", "", t).strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    # extract first {...}
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None, False
    blob = m.group(0)
    try:
        return json.loads(blob), True
    except Exception:
        # trailing commas etc
        try:
            blob2 = re.sub(r",\s*}", "}", blob)
            blob2 = re.sub(r",\s*]", "]", blob2)
            return json.loads(blob2), True
        except Exception:
            return None, False


def build_messages(task: str, cond: str, item: dict, ctx: dict):
    if cond == "C1":
        system = SYSTEM_NORAG
        material = None
    else:
        system = SYSTEM_RAG
        if task in ("E1", "E2"):
            if cond == "C2":
                material = ctx["c2_e12"]
            else:
                material = ctx["c3_r1"][task.lower()].get(item["id"], "")
        else:
            if cond == "C2":
                material = ctx["c2_e3"]
            else:
                material = ctx["c3_r2"].get(item["id"], "")

    if task == "E1":
        user_body = USER_E1.replace("{clause}", item["clause"])
    elif task == "E2":
        user_body = USER_E2.replace("{clause}", item["clause"]).replace("{choices}", ctx["e2_choices"])
    else:
        user_body = USER_E3.replace("{clause}", item["clause"]).replace("{label_list}", ctx["e3_label_list"])

    # /no_think hint in user for models that honor it
    user_body = user_body + "\n/no_think"

    messages = [{"role": "system", "content": system}]
    if material:
        # C2/C3: material right after system as start of user (prefix cache)
        user = f"<자료>\n{material}\n</자료>\n\n{user_body}"
    else:
        user = user_body
    messages.append({"role": "user", "content": user})
    return messages


def load_ctx():
    choices = json.loads((DATA / "e2_choices.json").read_text(encoding="utf-8"))["choices_line"]
    return {
        "c2_e12": (RET / "c2_e1e2_material.txt").read_text(encoding="utf-8"),
        "c2_e3": (RET / "c2_e3_material.txt").read_text(encoding="utf-8"),
        "c3_r1": json.loads((RET / "c3_packs_r1.json").read_text(encoding="utf-8")),
        "c3_r2": json.loads((RET / "c3_packs_r2.json").read_text(encoding="utf-8")),
        "e2_choices": choices,
        "e3_label_list": (RET / "e3_label_list.txt").read_text(encoding="utf-8"),
        "e3_labels": json.loads((DATA / "e3_labels.json").read_text(encoding="utf-8"))["labels"],
    }


def run_subset(model: str, items_by_task: dict, conds, n_per: int | None, smoke: bool):
    ctx = load_ctx()
    latencies = []
    parse_stats = []
    ood_e3 = []
    for task, items in items_by_task.items():
        subset = items[:n_per] if n_per else items
        for cond in conds:
            outp = OUT / f"{model}_{task}_{cond}.jsonl"
            done = existing_ids(outp)
            for item in subset:
                if item["id"] in done:
                    continue
                messages = build_messages(task, cond, item, ctx)
                try:
                    resp = chat(messages, temperature=0.0, max_tokens=256)
                    raw = resp["content"]
                except Exception as e:
                    raw = ""
                    resp = {
                        "latency_total_ms": None,
                        "latency_prompt_ms": None,
                        "latency_gen_ms": None,
                        "error": str(e),
                    }
                parsed, ok = parse_json_output(raw)
                # E3 OOD
                ood = False
                if task == "E3" and ok and isinstance(parsed, dict):
                    labs = parsed.get("labels") or []
                    if any(lb not in ctx["e3_labels"] for lb in labs):
                        ood = True
                        ood_e3.append({"id": item["id"], "labels": labs})
                row = {
                    "id": item["id"],
                    "raw_output": raw,
                    "parsed": parsed,
                    "parse_ok": ok,
                    "ood_label": ood,
                    "latency_prompt_ms": resp.get("latency_prompt_ms"),
                    "latency_gen_ms": resp.get("latency_gen_ms"),
                    "latency_total_ms": resp.get("latency_total_ms"),
                    "error": resp.get("error"),
                }
                append_jsonl(outp, row)
                latencies.append(resp.get("latency_total_ms"))
                parse_stats.append(ok)
                if smoke and len(parse_stats) <= 3:
                    print(model, task, cond, item["id"], "ok", ok, (raw or "")[:80])
    return {
        "n_calls": len(parse_stats),
        "parse_rate": (sum(parse_stats) / len(parse_stats)) if parse_stats else 0,
        "empty": sum(1 for x in load_all_raw(model) if not (x.get("raw_output") or "").strip()),
        "mean_latency_ms": (sum(x for x in latencies if x) / max(1, sum(1 for x in latencies if x))),
        "ood_e3_n": len(ood_e3),
        "ood_e3_samples": ood_e3[:5],
    }


def load_all_raw(model):
    rows = []
    for p in OUT.glob(f"{model}_*.jsonl"):
        rows.extend(load_jsonl(p))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["smoke", "full"], required=True)
    ap.add_argument("--model", choices=["8B", "32B", "both"], default="both")
    ap.add_argument("--n", type=int, default=None, help="override per-task n")
    args = ap.parse_args()

    e1 = load_jsonl(DATA / "e1.jsonl")
    e2 = load_jsonl(DATA / "e2.jsonl")
    e3 = load_jsonl(DATA / "e3.jsonl")
    items = {"E1": e1, "E2": e2, "E3": e3}
    conds = ["C1", "C2", "C3"]

    if args.mode == "smoke":
        n_per = 5
    else:
        n_per = args.n  # None = all

    models = ["8B", "32B"] if args.model == "both" else [args.model]
    report = {"mode": args.mode, "models": {}}

    for model in models:
        print("=== start server", model)
        start_server(model)
        try:
            stats = run_subset(model, items, conds, n_per, smoke=(args.mode == "smoke"))
            # per model-cond parse rates for smoke gate
            gate = {}
            for task in items:
                for cond in conds:
                    p = OUT / f"{model}_{task}_{cond}.jsonl"
                    rows = load_jsonl(p)
                    if args.mode == "smoke":
                        rows = rows[:5]
                    if not rows:
                        gate[f"{task}_{cond}"] = {"n": 0, "parse_rate": 0}
                        continue
                    # last n_per for this run — approx by id prefix count
                    gate[f"{task}_{cond}"] = {
                        "n": len(rows),
                        "parse_rate": sum(1 for r in rows if r.get("parse_ok")) / len(rows),
                        "empty": sum(1 for r in rows if not (r.get("raw_output") or "").strip()),
                    }
            report["models"][model] = {"stats": stats, "gate": gate}
        finally:
            stop_server()
            time.sleep(2)

    out = OUT / f"{args.mode}_run_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.mode == "smoke":
        # gate: each model-cond parse >= 0.95, empty 0
        fails = []
        for model, blk in report["models"].items():
            for k, g in blk["gate"].items():
                if g["n"] == 0 or g["parse_rate"] < 0.95 or g["empty"] > 0:
                    fails.append({"model": model, "cell": k, **g})
        report["smoke_pass"] = len(fails) == 0
        report["smoke_fails"] = fails
        # estimate time
        means = [blk["stats"]["mean_latency_ms"] for blk in report["models"].values() if blk["stats"]["mean_latency_ms"]]
        mean_ms = sum(means) / len(means) if means else 0
        # full: 2 models * 3 tasks * 3 conds * 200
        full_calls = 2 * 3 * 3 * 200
        est_h = (mean_ms / 1000 * full_calls) / 3600
        report["est_full_hours"] = est_h
        report["recommend_n"] = 150 if est_h > 14 else 200
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("SMOKE_PASS", report["smoke_pass"], "est_h", est_h, "fails", fails)
        if not report["smoke_pass"]:
            raise SystemExit(2)
    else:
        # 본실행 종료 후 채점
        import subprocess

        score_py = EXP / "score.py"
        print("scoring", score_py)
        subprocess.check_call([sys.executable, str(score_py)])
    print("wrote", out)


if __name__ == "__main__":
    main()
