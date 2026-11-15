# -*- coding: utf-8 -*-
"""2단계: 교사 모델 비교 (20문항 × 2모델)."""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from tqdm import tqdm


class _NewlineTqdmStream:
    """Redirected logs: turn tqdm \\r updates into newlines so Get-Content -Wait / tail -f works."""

    def write(self, s: str) -> int:
        if not s:
            return 0
        sys.__stdout__.write(s.replace("\r", "\n"))
        sys.__stdout__.flush()
        return len(s)

    def flush(self) -> None:
        sys.__stdout__.flush()


ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
# llama-server on Windows fails to open UTF-8 Korean paths; use ASCII junction.
RUNTIME_ROOT = Path(r"C:\Users\DMLAB\pilot_root")
PILOT = ROOT / "pilot"
SEED = 42
PORT = 8080
BASE_URL = f"http://127.0.0.1:{PORT}"

SYSTEM_PROMPT = (
    "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다. "
    "확실하지 않은 내용은 단정하지 않는다."
)

USER_TEMPLATE = """아래는 실제 법률 상담 질문과, 변호사가 작성한 답변입니다.
변호사 답변을 근거로, 법률을 모르는 대학생이 이해할 수 있는 해설을 작성하세요.

[질문]
{question}

[변호사 답변]
{answer}

[작성 규칙]
- 결론은 반드시 변호사 답변의 결론과 같아야 합니다.
- 법조문 번호와 판례 번호는 변호사 답변에 나온 것만 쓰세요. 그 외에는 번호 없이 원칙만 설명하세요.
- 질문이나 답변에 없는 사실(금액·날짜·행위)을 지어내지 마세요.
- "변호사 답변에 따르면", "위 답변에서" 같은 표현을 쓰지 말고, 질문자에게 직접 설명하듯 쓰세요.
- 변호사 답변이 질문에 실제로 답하지 않거나, 내용이 부족해 해설을 쓸 수 없으면 다른 내용 없이 [SKIP] 만 출력하세요.

[출력 형식]
1. 🔍 핵심 쟁점: 무엇이 문제인지 1~2문장
2. 📜 관련 법 원칙: 적용되는 법리를 쉬운 말로
3. 💡 이유: 결론에 이르는 논리를 단계별로
4. 📝 이렇게 하세요: 질문자가 할 수 있는 구체적 행동
마지막 줄: 구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."""

LLAMA_SERVER = RUNTIME_ROOT / "tools" / "llama.cpp" / "llama-server.exe"
EXAONE_GGUF = RUNTIME_ROOT / "models" / "EXAONE-4.0-32B-GGUF" / "EXAONE-4.0-32B-Q6_K.gguf"
EXAONE_TMPL = RUNTIME_ROOT / "models" / "EXAONE-4.0-32B-GGUF" / "chat_template.jinja"
QWEN_GGUF = RUNTIME_ROOT / "models" / "Qwen3-32B-GGUF" / "Qwen3-32B-Q6_K.gguf"

MODELS = {
    "EXAONE-4.0-32B-Q6_K": {
        "gguf": EXAONE_GGUF,
        "repo": "LGAI-EXAONE/EXAONE-4.0-32B-GGUF",
        "quant": "Q6_K",
        # Official non-reasoning via chat_template_kwargs enable_thinking=false
        # Jinja file via ASCII junction (Korean absolute path fails on Win llama-server).
        "extra_args": ["--jinja", "--chat-template-file", str(EXAONE_TMPL)],
        "chat_template_kwargs": {"enable_thinking": False},
        "append_user_suffix": None,
    },
    "Qwen3-32B-Q6_K": {
        "gguf": QWEN_GGUF,
        "repo": "Qwen/Qwen3-32B-GGUF",
        "quant": "Q6_K",
        "extra_args": ["--jinja"],
        "chat_template_kwargs": {"enable_thinking": False},
        "append_user_suffix": "/no_think",
    },
}

DOMAIN_ORDER = ["고용", "계약", "채권채무"]
DOMAIN_QUOTA = {"고용": 7, "계약": 7, "채권채무": 6}


def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sample_items(pilot_set: list[dict]) -> list[dict]:
    by_d: dict[str, list[dict]] = defaultdict(list)
    for r in pilot_set:
        by_d[r["domain"]].append(r)

    items: list[dict] = []
    notes: list[str] = []
    item_id = 1
    for d in DOMAIN_ORDER:
        pool = list(by_d.get(d, []))
        need = DOMAIN_QUOTA[d]
        if len(pool) < need:
            chosen = pool
            notes.append(f"{d}: pool={len(pool)} < {need} → took {len(chosen)}")
        else:
            chosen = random.sample(pool, need)
            notes.append(f"{d}: sampled {need}/{len(pool)}")
        for r in chosen:
            items.append({
                "item_id": f"T{item_id:02d}",
                "domain": d,
                "row_idx": r["row_idx"],
                "question": r["question"],
                "answer": r["answer"],
            })
            item_id += 1
    for n in notes:
        log(f"[sample] {n}")
    return items


def wait_ready(proc: subprocess.Popen, timeout: int = 900) -> None:
    url = f"{BASE_URL}/health"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited early with code {proc.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"llama-server not ready after {timeout}s")


def start_server(model_name: str, cfg: dict) -> subprocess.Popen:
    cmd = [
        str(LLAMA_SERVER),
        "-m", str(cfg["gguf"]),
        "-ngl", "99",
        "--tensor-split", "1,1",
        "-c", "8192",
        "--port", str(PORT),
        "--host", "127.0.0.1",
    ] + cfg["extra_args"]
    log("START: " + " ".join(cmd))
    log_path = PILOT / f"llama_server_{model_name}.log"
    logf = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        stdout=logf,
        stderr=subprocess.STDOUT,
        cwd=str(LLAMA_SERVER.parent),
    )
    proc._logf = logf  # type: ignore[attr-defined]
    wait_ready(proc)
    log(f"server ready for {model_name}, pid={proc.pid}")
    return proc


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
    finally:
        logf = getattr(proc, "_logf", None)
        if logf:
            logf.close()


def chat_completion(messages: list[dict], cfg: dict) -> tuple[str, int, float]:
    body = {
        "messages": messages,
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 1200,
        "chat_template_kwargs": cfg["chat_template_kwargs"],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    content = payload["choices"][0]["message"]["content"] or ""
    usage = payload.get("usage") or {}
    out_tokens = usage.get("completion_tokens")
    if out_tokens is None:
        out_tokens = -1
    return content, int(out_tokens), elapsed


ARTICLE_RE = re.compile(r"제\s*\d+\s*조")
FOOTER = "대한법률구조공단"


def extract_articles(text: str) -> set[str]:
    found = set()
    for m in ARTICLE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        found.add(f"제{digits}조")
    return found


def has_four_sections(text: str) -> bool:
    # look for numbered section headers 1. 2. 3. 4.
    return all(re.search(rf"(?m)^\s*{i}\.", text) for i in range(1, 5))


def build_compare_md(items: list[dict], outputs: list[dict]) -> str:
    by_key: dict[tuple[str, str], dict] = {}
    for o in outputs:
        by_key[(o["item_id"], o["model"])] = o

    model_names = list(MODELS.keys())
    lines = ["# TEACHER_COMPARE", ""]
    for item in items:
        lines.append(f"## {item['item_id']} | {item['domain']}")
        lines.append("")
        lines.append("### [질문]")
        lines.append(item["question"])
        lines.append("")
        lines.append("### [변호사 답변]")
        lines.append(item["answer"])
        lines.append("")
        for mn in model_names:
            o = by_key.get((item["item_id"], mn))
            lines.append(f"### [{mn}]")
            if o is None:
                lines.append("(미생성)")
            else:
                lines.append(o["output"])
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def aggregate(outputs: list[dict], items: list[dict]) -> dict:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for o in outputs:
        by_model[o["model"]].append(o)

    item_ans = {i["item_id"]: i["answer"] for i in items}
    stats = {}
    for model, rows in by_model.items():
        n = len(rows)
        skip_n = sum(1 for r in rows if "[SKIP]" in (r["output"] or "").strip()[:20] or (r["output"] or "").strip() == "[SKIP]")
        # stricter SKIP: whole output is essentially just [SKIP]
        skip_n = sum(1 for r in rows if (r["output"] or "").strip() == "[SKIP]" or (r["output"] or "").strip().startswith("[SKIP]"))
        sec4 = sum(1 for r in rows if has_four_sections(r["output"] or ""))
        footer = sum(1 for r in rows if FOOTER in (r["output"] or ""))
        halluc_articles: list[str] = []
        for r in rows:
            out_arts = extract_articles(r["output"] or "")
            ans_arts = extract_articles(item_ans[r["item_id"]])
            for a in sorted(out_arts - ans_arts):
                halluc_articles.append(f"{r['item_id']}:{a}")
        think_n = sum(1 for r in rows if "<think>" in (r["output"] or "").lower() or "<think>" in (r["output"] or ""))
        # also check common think tags
        think_n = sum(
            1 for r in rows
            if "<think>" in (r["output"] or "") or "</think>" in (r["output"] or "")
        )
        stats[model] = {
            "n": n,
            "skip": skip_n,
            "four_section_ratio": sec4 / n if n else 0.0,
            "footer_ratio": footer / n if n else 0.0,
            "hallucinated_articles": halluc_articles,
            "think_tag_count": think_n,
            "avg_gen_sec": sum(r["gen_sec"] for r in rows) / n if n else 0.0,
            "avg_out_tokens": sum(r["out_tokens"] for r in rows if r["out_tokens"] >= 0) / max(1, sum(1 for r in rows if r["out_tokens"] >= 0)),
            "avg_tok_per_sec": (
                sum(r["out_tokens"] / r["gen_sec"] for r in rows if r["out_tokens"] >= 0 and r["gen_sec"] > 0)
                / max(1, sum(1 for r in rows if r["out_tokens"] >= 0 and r["gen_sec"] > 0))
            ),
        }
    return stats


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    PILOT.mkdir(parents=True, exist_ok=True)

    if not LLAMA_SERVER.exists():
        raise FileNotFoundError(f"llama-server missing: {LLAMA_SERVER}")

    for name, cfg in MODELS.items():
        if not cfg["gguf"].exists():
            raise FileNotFoundError(f"GGUF missing for {name}: {cfg['gguf']}")
        size_gb = cfg["gguf"].stat().st_size / (1024 ** 3)
        log(f"model {name}: repo={cfg['repo']} file={cfg['gguf'].name} quant={cfg['quant']} size_gb={size_gb:.2f}")

    # version
    ver = subprocess.run([str(LLAMA_SERVER), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    log("llama-server --version stdout:\n" + (ver.stdout or ""))
    log("llama-server --version stderr:\n" + (ver.stderr or ""))

    pilot_set = load_jsonl(PILOT / "pilot_set.jsonl")
    items = sample_items(pilot_set)
    write_jsonl(PILOT / "teacher_items.jsonl", items)
    log(f"teacher_items: {len(items)}")

    all_outputs: list[dict] = []
    model_names = list(MODELS.keys())
    # 전체 진행: 모델 로드 포함 문항 단위 (로그 리다이렉트 시에도 줄 단위로 보이도록)
    pbar = tqdm(
        total=len(model_names) * len(items),
        desc="teacher_compare",
        unit="item",
        file=_NewlineTqdmStream(),
        dynamic_ncols=False,
        mininterval=1.0,
        ascii=True,
    )
    for model_name, cfg in MODELS.items():
        proc = None
        try:
            log(f"loading server: {model_name}")
            proc = start_server(model_name, cfg)
            for item in items:
                pbar.set_postfix_str(f"{model_name} {item['item_id']}", refresh=True)
                user_content = USER_TEMPLATE.format(
                    question=item["question"],
                    answer=item["answer"],
                )
                if cfg["append_user_suffix"]:
                    user_content = user_content + "\n\n" + cfg["append_user_suffix"]
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ]
                log(f"generate {model_name} {item['item_id']} ...")
                try:
                    content, out_tokens, elapsed = chat_completion(messages, cfg)
                except Exception as e:
                    content = f"[ERROR] {type(e).__name__}: {e}"
                    out_tokens = -1
                    elapsed = -1.0
                    log(content)
                tps = (out_tokens / elapsed) if out_tokens >= 0 and elapsed > 0 else None
                log(f"  gen_sec={elapsed:.2f} out_tokens={out_tokens} tok/s={tps}")
                all_outputs.append({
                    "item_id": item["item_id"],
                    "domain": item["domain"],
                    "question": item["question"],
                    "answer": item["answer"],
                    "model": model_name,
                    "output": content,
                    "gen_sec": round(elapsed, 3) if elapsed >= 0 else elapsed,
                    "out_tokens": out_tokens,
                })
                pbar.update(1)
        finally:
            stop_server(proc)
            time.sleep(3)
    pbar.close()

    write_jsonl(PILOT / "teacher_outputs.jsonl", all_outputs)
    md = build_compare_md(items, all_outputs)
    (PILOT / "TEACHER_COMPARE.md").write_text(md, encoding="utf-8")

    stats = aggregate(all_outputs, items)
    with (PILOT / "teacher_compare_stats.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    log("STATS:")
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    log("done")


if __name__ == "__main__":
    main()
