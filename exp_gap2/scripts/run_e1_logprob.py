# -*- coding: utf-8 -*-
"""E1 logprob 점수 비교. GAP-1 프롬프트 재현 + /completion n_probs."""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
G1 = ROOT / "exp_gap1"
G2 = ROOT / "exp_gap2"
OUT = G2 / "out"

sys.path.insert(0, str(G1 / "scripts"))
from llm_server import HOST, PORT, start_server, stop_server  # noqa: E402
from run_gap1 import SYSTEM_NORAG, SYSTEM_RAG, USER_E1, load_jsonl  # noqa: E402


def http_json(path, body, timeout=180):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def apply_template(messages):
    """llama-server /apply-template → prompt 문자열."""
    last_err = None
    for path in ("/apply-template", "/v1/apply-template"):
        try:
            js = http_json(path, {"messages": messages})
            if isinstance(js, str):
                return js, path, "str"
            if isinstance(js, dict):
                for k in ("prompt", "formatted", "content", "text", "result"):
                    if isinstance(js.get(k), str) and js[k]:
                        return js[k], path, k
                # sometimes nested
                if "data" in js and isinstance(js["data"], str):
                    return js["data"], path, "data"
            last_err = f"unexpected shape keys={list(js)[:20] if isinstance(js, dict) else type(js)}"
        except Exception as e:
            last_err = str(e)
    # Qwen2/3 ChatML fallback
    parts = []
    for m in messages:
        parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts), "fallback_chatml", last_err


def normalize_assistant_prefix(prompt: str, gap1_sample_raw: str | None):
    """thinking 끔이면 빈 <think> 블록이 있을 수 있음. GAP-1 raw 시작부와 맞춤."""
    notes = []
    p = prompt
    # If server returns prompt without assistant header, add it
    if "<|im_start|>assistant" not in p[-120:]:
        if not p.endswith("\n"):
            p += "\n"
        p += "<|im_start|>assistant\n"
        notes.append("appended_im_start_assistant")

    # Check whether empty think block needed
    # GAP-1 with --reasoning off often still emits empty think in chat path
    empty_think = "<think>\n\n</think>\n\n"
    # Inspect a GAP-1 raw output start if available
    needs_think = False
    if gap1_sample_raw:
        raw = gap1_sample_raw.lstrip()
        if raw.startswith("<think>") or raw.startswith("<think>\n"):
            needs_think = True
            notes.append("gap1_raw_starts_with_think")
    # Also probe: many Qwen3+llama.cpp with reasoning off still prefix empty think
    # Prefer adding empty think if not already present near end
    tail = p[-300:]
    if empty_think.strip() not in tail and "<think>" not in tail:
        if needs_think or True:
            # default: add empty think to match reasoning-off chat completions
            p = p + empty_think
            notes.append("appended_empty_think")
    return p, notes


def build_messages(item, cond, c2_material):
    if cond == "C1":
        system = SYSTEM_NORAG
        user = USER_E1.replace("{clause}", item["clause"]) + "\n/no_think"
    else:
        system = SYSTEM_RAG
        user = f"<자료>\n{c2_material}\n</자료>\n\n" + USER_E1.replace("{clause}", item["clause"]) + "\n/no_think"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _tok_prob_pairs(completion_js):
    """Yield (token_str, prob) for first predicted position top-n.

    llama.cpp current format:
      completion_probabilities: [{token, logprob, top_logprobs:[{token, logprob}, ...]}]
    """
    cp = completion_js.get("completion_probabilities")
    if isinstance(cp, list) and cp:
        first = cp[0]
        if isinstance(first, dict):
            tops = first.get("top_logprobs") or first.get("probs")
            if isinstance(tops, list) and tops:
                for pt in tops:
                    tok = pt.get("tok") or pt.get("token") or pt.get("t") or ""
                    if "prob" in pt:
                        yield str(tok), float(pt["prob"])
                    elif "logprob" in pt:
                        yield str(tok), float(math.exp(pt["logprob"]))
                return
            # single sampled token only
            if "token" in first and "logprob" in first:
                yield str(first["token"]), float(math.exp(first["logprob"]))
                return
    try:
        ch = completion_js["choices"][0]
        lp = ch.get("logprobs") or {}
        content = lp.get("content") or []
        if isinstance(content, list) and content:
            first = content[0]
            tops = first.get("top_logprobs") if isinstance(first, dict) else None
            if tops:
                for pt in tops:
                    tok = pt.get("token") or pt.get("tok") or ""
                    if "prob" in pt:
                        yield str(tok), float(pt["prob"])
                    else:
                        yield str(tok), float(math.exp(pt.get("logprob", -99)))
                return
    except Exception:
        pass


def _is_true_tok(tok: str) -> bool:
    t = tok.replace("▁", " ").replace("Ġ", " ").replace("\t", " ").strip().lower()
    return t == "true"


def _is_false_tok(tok: str) -> bool:
    t = tok.replace("▁", " ").replace("Ġ", " ").replace("\t", " ").strip().lower()
    return t == "false"


def extract_tf_probs(completion_js):
    p_true = 0.0
    p_false = 0.0
    tokens_seen = []
    for tok, p in _tok_prob_pairs(completion_js):
        tokens_seen.append((tok, p))
        if _is_true_tok(tok):
            p_true += p
        elif _is_false_tok(tok):
            p_false += p
    missing = (p_true + p_false) <= 0
    return p_true, p_false, missing, tokens_seen[:20]


def run_model(model: str, conds=("C1", "C2")):
    e1 = load_jsonl(G1 / "data" / "e1.jsonl")
    c2 = (G1 / "retrieval" / "c2_e1e2_material.txt").read_text(encoding="utf-8")
    gap1 = {}
    for cond in conds:
        for r in load_jsonl(G1 / "out" / f"{model}_E1_{cond}.jsonl"):
            gap1[(cond, r["id"])] = r

    start_server(model)
    results = {}
    try:
        # template probe
        sample_msgs = build_messages(e1[0], "C1", c2)
        prompt0, src, note = apply_template(sample_msgs)
        g1_raw = (gap1.get(("C1", e1[0]["id"])) or {}).get("raw_output") or ""
        prompt0b, notes = normalize_assistant_prefix(prompt0, g1_raw)
        (OUT / f"e1_logprob_template_{model}.txt").write_text(
            f"# source={src} note={note} normalize={notes}\n" + prompt0b, encoding="utf-8"
        )
        # also dump one completion raw for debug
        probe_body = {
            "prompt": prompt0b + '{"risky": ',
            "n_predict": 1,
            "temperature": 0,
            "n_probs": 20,
            "cache_prompt": True,
        }
        try:
            probe_js = http_json("/completion", probe_body, timeout=180)
            (OUT / f"e1_logprob_probe_{model}.json").write_text(
                json.dumps(probe_js, ensure_ascii=False, indent=2)[:50000], encoding="utf-8"
            )
        except Exception as e:
            (OUT / f"e1_logprob_probe_{model}.json").write_text(json.dumps({"error": str(e)}), encoding="utf-8")

        for cond in conds:
            outp = OUT / f"e1_logprob_{model}_{cond}.jsonl"
            existing = {r["id"] for r in load_jsonl(outp)}
            for item in e1:
                if item["id"] in existing:
                    continue
                messages = build_messages(item, cond, c2)
                prompt, _, _ = apply_template(messages)
                g1 = gap1.get((cond, item["id"]), {})
                prompt, _ = normalize_assistant_prefix(prompt, g1.get("raw_output"))
                prompt_full = prompt + '{"risky": '
                body = {
                    "prompt": prompt_full,
                    "n_predict": 1,
                    "temperature": 0,
                    "n_probs": 20,
                    "cache_prompt": True,
                }
                try:
                    js = http_json("/completion", body, timeout=180)
                    p_true, p_false, missing, toks = extract_tf_probs(js)
                    content = js.get("content") or ""
                except Exception as e:
                    p_true, p_false, missing, toks = 0.0, 0.0, True, []
                    content = ""
                    js = {"error": str(e)}
                denom = p_true + p_false
                score = (p_true / denom) if denom > 0 else None
                g1_pred = None
                if g1.get("parse_ok") and isinstance(g1.get("parsed"), dict) and "risky" in g1["parsed"]:
                    g1_pred = bool(g1["parsed"]["risky"])
                row = {
                    "id": item["id"],
                    "p_true": p_true,
                    "p_false": p_false,
                    "score": score,
                    "missing": missing or score is None,
                    "gap1_pred": g1_pred,
                    "top_tokens": toks,
                    "completion_content": content,
                }
                with outp.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            all_rows = load_jsonl(outp)
            agree = []
            for r in all_rows:
                if r.get("score") is None or r.get("gap1_pred") is None:
                    continue
                agree.append(1.0 if (r["score"] > 0.5) == r["gap1_pred"] else 0.0)
            rate = sum(agree) / len(agree) if agree else 0.0
            disagrees = [
                {"id": r["id"], "score": r["score"], "gap1_pred": r["gap1_pred"], "top_tokens": r.get("top_tokens")}
                for r in all_rows
                if r.get("score") is not None
                and r.get("gap1_pred") is not None
                and (r["score"] > 0.5) != r["gap1_pred"]
            ][:5]
            results[cond] = {
                "n": len(all_rows),
                "n_scored": len(agree),
                "agree_rate": rate,
                "missing_n": sum(1 for r in all_rows if r.get("missing")),
                "gate_pass": rate >= 0.90 and len(agree) >= 0.8 * max(1, len(all_rows)),
                "disagree_samples": disagrees,
            }
            print(model, cond, "agree", f"{rate:.3f}", "gate", results[cond]["gate_pass"], "missing", results[cond]["missing_n"])
            if not results[cond]["gate_pass"]:
                print("GATE FAIL — stop this stage for", model, cond, "(other stages continue)")
    finally:
        stop_server()
    (OUT / f"e1_logprob_gate_{model}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_res = {}
    for model in ("8B", "32B"):
        all_res[model] = run_model(model)
    (OUT / "e1_logprob_gate.json").write_text(json.dumps(all_res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(all_res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
