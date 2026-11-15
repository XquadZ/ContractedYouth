# -*- coding: utf-8 -*-
"""설계 v2 모델 실행. 입력 jsonl 은 읽기만 한다. 결과는 runs 에 append+fsync, id 로 재개."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
RUNS = EXP / "runs"
SMOKE = RUNS / "smoke"
LLAMA_DIR = WORK / "data_local" / "llama.cpp" / "b11755"
SERVER = LLAMA_DIR / "llama-server.exe"
HOST = "127.0.0.1"
PORT = 8080
MODELS = {
    "Q8B": WORK / "data_local" / "models" / "Qwen3-8B-Q8_0.gguf",
    "Q8B-T": WORK / "data_local" / "models" / "Qwen3-8B-Q8_0.gguf",
    "AX7": WORK / "data_local" / "models" / "A.X-4.0-Light-Q8_0.gguf",
}
SYSTEM_NORAG = (WORK / "exp_gap1" / "prompts" / "system_norag.txt").read_text(encoding="utf-8")
SYSTEM_RAG = (WORK / "exp_gap1" / "prompts" / "system_rag.txt").read_text(encoding="utf-8")
USER = {
    "T1": (EXP / "prompts" / "user_t1.txt").read_text(encoding="utf-8"),
    "T2": (EXP / "prompts" / "user_t2.txt").read_text(encoding="utf-8"),
    "T3": (EXP / "prompts" / "user_t3.txt").read_text(encoding="utf-8"),
    "T4": (EXP / "prompts" / "user_t4.txt").read_text(encoding="utf-8"),
    "CF": (EXP / "prompts" / "user_t3.txt").read_text(encoding="utf-8"),
}

# 본 실행 건수. 스모크 속도에 곱한다.
FULL_COUNTS = {
    "Q8B": {"T1": 17 * 2, "T2": 330 * 2, "T3": 402 * 6, "T4": 67 * 6, "CF": 268 * 2},
    "AX7": {"T1": 17 * 2, "T2": 330 * 2, "T3": 402 * 6, "T4": 67 * 6, "CF": 268 * 2},
    "Q8B-T": {"T1": 17 * 2, "T3": 134 * 6, "T4": 67 * 6},
}


def log(msg: str) -> None:
    # 콘솔은 ASCII 만.
    sys.stdout.buffer.write((msg.encode("ascii", "replace") + b"\n"))
    sys.stdout.flush()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def done_ids(path: Path) -> set[str]:
    # 연결이 끊긴 행은 재개 때 다시 호출한다.
    ids = set()
    for row in load_jsonl(path):
        if row.get("id") and row.get("parse_ok") and not row.get("error"):
            ids.add(row["id"])
    return ids


def write_crash(reason: str, extra: dict | None = None) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": reason, "extra": extra or {}}
    append_jsonl(RUNS / "CRASH.jsonl", row)
    log("CRASH " + reason.encode("ascii", "replace").decode("ascii"))


def parse_json_output(text: str):
    if not text:
        return None, False
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None, False
    blob = match.group(0)
    try:
        return json.loads(blob), True
    except json.JSONDecodeError:
        try:
            blob2 = re.sub(r",\s*}", "}", blob)
            blob2 = re.sub(r",\s*]", "]", blob2)
            return json.loads(blob2), True
        except json.JSONDecodeError:
            return None, False


def choice_line(node: dict) -> str:
    title = (node.get("조문 제목") or "").strip()
    base = f"{node.get('법령명')} {node.get('조문 번호')}"
    return f"{base}({title})" if title else base


def render_nodes(ids: list[str], law: dict) -> str:
    blocks = []
    for node_id in ids:
        node = law.get(node_id)
        if node is None:
            blocks.append(f"[{node_id}]\n")
            continue
        title = node.get("조문 제목") or ""
        head = f"[{node['id']}] {node.get('법령명')} {node.get('조문 번호')}"
        if title:
            head += " " + title
        blocks.append(head + "\n" + (node.get("본문") or ""))
    return "\n\n".join(blocks)


def node_missing(node_id: str, law: dict) -> bool:
    node = law.get(node_id)
    if node is None:
        return True
    if node.get("text_source") == "missing":
        return True
    return not (node.get("본문") or "").strip()


class GpuLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("ts,util_gpu,mem_used_mib,temp_c,power_w\n", encoding="utf-8")
        self.thread.start()

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=utilization.gpu,memory.used,temperature.gpu,power.draw",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                ).strip()
            except Exception as exc:
                out = "ERR " + str(exc)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')},{out}\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.stop.wait(2)

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


def server_cmd(model: str) -> list[str]:
    reasoning = "on" if model == "Q8B-T" else "off"
    cmd = [
        str(SERVER),
        "-m",
        str(MODELS[model]),
        "--host",
        HOST,
        "--port",
        str(PORT),
        "-c",
        "8192",
        "-ngl",
        "99",
        "-np",
        "1",
        "--cache-prompt",
        "--reasoning",
        reasoning,
    ]
    if model != "Q8B-T":
        cmd.extend(["--reasoning-budget", "0"])
    else:
        cmd.extend(["--reasoning-format", "deepseek"])
    return cmd


def health() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def start_server(model: str) -> subprocess.Popen:
    if not SERVER.exists():
        raise FileNotFoundError(str(SERVER))
    if not MODELS[model].exists():
        raise FileNotFoundError(str(MODELS[model]))
    cmd = server_cmd(model)
    record = {
        "model": model,
        "cmd": cmd,
        "gguf": str(MODELS[model]),
        "llama_cpp": "b11755 commit 704366d76 version 0.7.0-dev",
        "request": request_body(model, []),
    }
    append_jsonl(RUNS / "server_cmd.jsonl", record)
    log_path = RUNS / f"server_{model}.log"
    logf = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "0"
    proc = subprocess.Popen(cmd, cwd=str(LLAMA_DIR), stdout=logf, stderr=subprocess.STDOUT, env=env)
    for _ in range(180):
        if health():
            log(f"server {model} up")
            return proc
        if proc.poll() is not None:
            write_crash("server_exited_early", {"model": model, "code": proc.returncode, "log": str(log_path)})
            raise SystemExit(2)
        time.sleep(2)
    write_crash("server_not_healthy", {"model": model, "log": str(log_path)})
    proc.kill()
    raise SystemExit(2)


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def request_body(model: str, messages: list[dict]) -> dict:
    if model == "Q8B-T":
        body = {
            "messages": messages,
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "seed": 42,
            "max_tokens": 4096,
            "chat_template_kwargs": {"enable_thinking": True},
            "enable_thinking": True,
        }
    elif model == "Q8B":
        body = {
            "messages": messages,
            "temperature": 0,
            "max_tokens": 256,
            "repeat_penalty": 1.05,
            "chat_template_kwargs": {"enable_thinking": False},
            "enable_thinking": False,
        }
    else:
        body = {
            "messages": messages,
            "temperature": 0,
            "max_tokens": 256,
        }
    return body


def chat(model: str, messages: list[dict]) -> dict:
    body = request_body(model, messages)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = 900 if model == "Q8B-T" else 300
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {"content": "", "reasoning": "", "latency_ms": (time.perf_counter() - t0) * 1000, "error": detail[:2000]}
    except Exception as exc:
        return {"content": "", "reasoning": "", "latency_ms": (time.perf_counter() - t0) * 1000, "error": str(exc)}
    js = json.loads(raw)
    msg = js["choices"][0]["message"]
    return {
        "content": msg.get("content") or "",
        "reasoning": msg.get("reasoning_content") or "",
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "error": None,
        "usage": js.get("usage"),
    }


def index_by_id(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in load_jsonl(path)}


def load_world() -> dict:
    law = {r["id"]: r for r in load_jsonl(EXP / "law_node_texts.jsonl")}
    cat = json.loads((WORK / "data_contract" / "catalog" / "catalog_v0.2.json").read_text(encoding="utf-8"))
    slot_name = {s["id"]: s["name"] for s in cat["slots"]}
    slot_name["기타"] = "기타"
    labels = [s["name"] for s in cat["slots"] if s["domain"] in ("LAB", "LEASE")]
    labels.append("기타")
    label_list = "\n".join(labels)
    ctx = {}
    for name in ("t3_A1", "t3_A2", "t3_A3", "t3_A4", "t4_A1", "t4_A2", "t4_A3", "t4_A4"):
        ctx[name] = index_by_id(EXP / "contexts" / f"{name}.jsonl")
    t3 = load_jsonl(EXP / "data" / "t3_clauses.jsonl")
    t3_by = {r["id"]: r for r in t3}
    from t2_neighbors import build as build_neighbors

    neighbors = build_neighbors(force=not (RUNS / "t2_neighbors.jsonl").exists())
    return {
        "law": law,
        "slot_name": slot_name,
        "label_list": label_list,
        "ctx": ctx,
        "t3_by": t3_by,
        "neighbors": neighbors,
        "t1": load_jsonl(EXP / "data" / "t1_items.jsonl"),
        "t2": load_jsonl(EXP / "data" / "t2_clauses.jsonl"),
        "t3": t3,
        "t4": load_jsonl(EXP / "data" / "t4_items.jsonl"),
        "cf": [r for r in load_jsonl(EXP / "data" / "counterfactual.jsonl") if r.get("variant") == "irrelevant"],
    }


def incomplete_ids(ids: list[str], law: dict) -> bool:
    return any(node_missing(node_id, law) for node_id in ids)


def material_for(task: str, cond: str, item: dict, world: dict) -> tuple[str | None, list[str]]:
    law = world["law"]
    if cond == "A0":
        return None, []
    if task == "T1" and cond == "A1":
        ids = list(item.get("law_nodes") or [])
        return render_nodes(ids, law), ids
    if task == "T2" and cond == "K":
        neighbors = world["neighbors"].get(item["id"]) or []
        blocks = []
        for i, neigh in enumerate(neighbors, start=1):
            blocks.append(f"[유사 조항 {i}]\n라벨: {neigh['slot_name']}\n조항: {neigh['clause']}")
        return "\n\n".join(blocks), []
    if task == "CF" and cond == "A1":
        src = world["t3_by"].get(item["source_id"]) or {}
        ids = list(src.get("gold_law_nodes") or [])
        packed = world["ctx"]["t3_A1"].get(item["source_id"])
        return (packed or {}).get("text") or render_nodes(ids, law), ids
    prefix = "t3" if task in ("T3",) else "t4"
    if task == "T3":
        prefix = "t3"
    elif task == "T4":
        prefix = "t4"
    if cond in ("A1", "A2", "A3"):
        packed = world["ctx"][f"{prefix}_{cond}"].get(item["id"]) or {}
        return packed.get("text") or "", list(packed.get("node_ids") or [])
    if cond in ("A4-BM25", "A4-bge"):
        packed = world["ctx"][f"{prefix}_A4"].get(item["id"]) or {}
        key = "bm25" if cond == "A4-BM25" else "bge"
        part = packed.get(key) or {}
        return part.get("text") or "", list(part.get("node_ids") or [])
    return None, []


def user_text(task: str, item: dict, world: dict) -> str:
    if task == "T1":
        return USER["T1"].replace("{q}", item["q"])
    if task == "T2":
        return USER["T2"].replace("{label_list}", world["label_list"]).replace("{clause}", item["clause"])
    if task == "T4":
        law = world["law"]
        lines = [choice_line(law[node_id]) for node_id in sorted(item["choices"]) if node_id in law]
        return USER["T4"].replace("{choices}", "\n".join(lines)).replace("{clause}", item["clause"])
    return USER["T3"].replace("{clause}", item["clause"])


def gold_ids(task: str, item: dict, world: dict) -> list[str]:
    if task == "T1":
        return list(item.get("law_nodes") or [])
    if task == "T3":
        return list(item.get("gold_law_nodes") or [])
    if task == "T4":
        return list(item.get("gold") or [])
    if task == "CF":
        src = world["t3_by"].get(item["source_id"]) or {}
        return list(src.get("gold_law_nodes") or [])
    return []


def messages_for(task: str, cond: str, item: dict, world: dict) -> tuple[list[dict], bool]:
    material, ctx_ids = material_for(task, cond, item, world)
    system = SYSTEM_NORAG if cond == "A0" else SYSTEM_RAG
    user = user_text(task, item, world)
    if material:
        user = f"<자료>\n{material}\n</자료>\n\n{user}"
    flags = gold_ids(task, item, world) + ctx_ids
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], incomplete_ids(flags, world["law"])


def iter_items(model: str, world: dict):
    plan = [
        ("T1", ["A0", "A1"], world["t1"]),
        ("T4", ["A0", "A1", "A2", "A3", "A4-BM25", "A4-bge"], world["t4"]),
        ("T3", ["A0", "A1", "A2", "A3", "A4-BM25", "A4-bge"], world["t3"]),
        ("CF", ["A0", "A1"], world["cf"]),
        ("T2", ["A0", "K"], world["t2"]),
    ]
    if model == "Q8B-T":
        plan = [
            ("T1", ["A0", "A1"], world["t1"]),
            ("T4", ["A0", "A1", "A2", "A3", "A4-BM25", "A4-bge"], world["t4"]),
            (
                "T3",
                ["A0", "A1", "A2", "A3", "A4-BM25", "A4-bge"],
                [r for r in world["t3"] if r.get("surface") == "0"],
            ),
        ]
    for task, conds, items in plan:
        for cond in conds:
            yield task, cond, items


def run_model(model: str, world: dict, limit: int | None, out_dir: Path) -> dict:
    proc = start_server(model)
    summary = {}
    try:
        for task, cond, items in iter_items(model, world):
            subset = items[:limit] if limit else items
            outp = out_dir / f"{model}_{task}_{cond}.jsonl"
            done = done_ids(outp)
            lats = []
            oks = []
            for item in subset:
                if proc.poll() is not None:
                    write_crash("server_died", {"model": model, "task": task, "cond": cond, "id": item["id"]})
                    raise SystemExit(2)
                if item["id"] in done:
                    continue
                messages, incomplete = messages_for(task, cond, item, world)
                resp = chat(model, messages)
                if resp.get("error") and proc.poll() is None:
                    resp = chat(model, messages)
                if proc.poll() is not None:
                    write_crash("server_died", {"model": model, "task": task, "cond": cond, "id": item["id"]})
                    raise SystemExit(2)
                parsed, ok = parse_json_output(resp["content"])
                reasoning = resp.get("reasoning") or ""
                row = {
                    "id": item["id"],
                    "task": task,
                    "cond": cond,
                    "model": model,
                    "pair_id": item.get("pair_id") or item.get("source_id"),
                    "check_id": item.get("check_id"),
                    "domain": item.get("domain"),
                    "surface": item.get("surface"),
                    "kind": item.get("kind"),
                    "ctx_incomplete": incomplete,
                    "raw_output": resp["content"],
                    "reasoning": reasoning,
                    "reasoning_chars": len(reasoning),
                    "parsed": parsed,
                    "parse_ok": ok,
                    "latency_ms": resp.get("latency_ms"),
                    "error": resp.get("error"),
                }
                append_jsonl(outp, row)
                (RUNS / "heartbeat.txt").write_text(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {model} {task} {cond} {item['id']}\n",
                    encoding="utf-8",
                )
                lats.append(resp.get("latency_ms") or 0)
                oks.append(ok)
                log(f"{model} {task} {cond} {item['id']} ok={int(ok)} ms={int(resp.get('latency_ms') or 0)}")
            summary[f"{task}_{cond}"] = {
                "n": len(oks),
                "parse_ok": sum(oks),
                "mean_ms": (sum(lats) / len(lats)) if lats else 0,
            }
    finally:
        stop_server(proc)
    return summary


def estimate(model: str, summary: dict) -> float:
    means = []
    weights = []
    for key, stat in summary.items():
        if stat["n"] <= 0:
            continue
        task = key.split("_", 1)[0]
        means.append(stat["mean_ms"])
        weights.append(stat["n"])
    if not means:
        return 0.0
    # 조건별 평균을 그 과제의 본실행 건수에 태스크 단위로 다시 평균한다.
    by_task: dict[str, list[float]] = {}
    for key, stat in summary.items():
        if stat["n"] <= 0:
            continue
        task = key.split("_", 1)[0]
        by_task.setdefault(task, []).append(stat["mean_ms"])
    total_ms = 0.0
    for task, samples in by_task.items():
        total_ms += (sum(samples) / len(samples)) * FULL_COUNTS[model].get(task, 0)
    return total_ms / 1000.0 / 3600.0


def smoke_passed(summary: dict) -> bool:
    if not summary:
        return False
    for stat in summary.values():
        if stat["n"] < 3:
            return False
        if stat["parse_ok"] / stat["n"] < 0.95:
            return False
    return True


def acquire_lock() -> None:
    lock = RUNS / "runner.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = -1
        alive = False
        if pid > 0:
            listed = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], text=True, errors="replace")
            alive = str(pid) in listed
        if alive:
            log(f"another runner is alive pid={pid}")
            raise SystemExit(5)
    lock.write_text(str(os.getpid()), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["neighbors", "smoke", "run"])
    parser.add_argument("--model", default="Q8B")
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    if args.stage != "neighbors":
        acquire_lock()
    if args.stage == "neighbors":
        from t2_neighbors import build

        build(force=True)
        return
    gpu = GpuLog(RUNS / "gpu.csv")
    gpu.start()
    try:
        world = load_world()
        art = world["law"]["근기법:제54조"]["본문"]
        has = "4시간인 경우에는 30분 이상" in art
        (RUNS / "art54_check.txt").write_text(
            "include=" + str(has) + "\n" + art + "\n",
            encoding="utf-8",
        )
        log("art54_include=" + str(has))
        if args.stage == "smoke":
            summary = run_model(args.model, world, limit=3, out_dir=SMOKE)
            hours = estimate(args.model, summary)
            append_jsonl(
                RUNS / "smoke_summary.jsonl",
                {"model": args.model, "summary": summary, "est_hours": hours, "passed": smoke_passed(summary)},
            )
            log(f"SMOKE {args.model} pass={int(smoke_passed(summary))} est_hours={hours:.2f}")
            if not smoke_passed(summary):
                write_crash("smoke_failed", {"model": args.model, "summary": summary})
                raise SystemExit(3)
            if args.model == "Q8B-T" and hours > 8:
                (RUNS / "Q8BT_OVER_8H.txt").write_text(
                    f"est_hours={hours:.2f}\nAsk the user before the full Q8B-T run.\n",
                    encoding="utf-8",
                )
                log(f"Q8B-T est {hours:.2f}h > 8. full run held")
        else:
            if args.model == "Q8B-T" and (RUNS / "Q8BT_OVER_8H.txt").exists():
                log("Q8B-T full run blocked by 8h estimate")
                raise SystemExit(4)
            run_model(args.model, world, limit=None, out_dir=RUNS)
            log(f"DONE {args.model}")
    finally:
        gpu.close()
        lock = RUNS / "runner.lock"
        if lock.exists() and lock.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock.unlink()


if __name__ == "__main__":
    main()
