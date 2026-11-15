# -*- coding: utf-8 -*-
"""계약서 점검 비교. 127.0.0.1 만 연다. 계약서 원문은 디스크에 쓰지 않는다."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipelines.common import DOMAIN_KO, guess_domain, split_clauses, world
from pipelines.evidence import load as load_evidence
from pipelines.left import run_left
from pipelines.llm import healthy
from pipelines.replay import replay
from pipelines.right import ready as roberta_ready
from pipelines.right import run_right

LOG = APP / "logs" / "analyze.jsonl"
POOL = ThreadPoolExecutor(max_workers=2)
app = FastAPI(title="계약서 점검 비교")


class AnalyzeIn(BaseModel):
    text: str
    domain: str | None = None
    oracle_slot: bool = False
    include_articles: bool = True


def _log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@app.get("/api/health")
def health():
    return {
        "qwen": healthy(8081),
        "ax": healthy(8082),
        "roberta": roberta_ready(),
        "wage_2026": world().params["min_wage_hourly"].get("2026"),
    }


@app.get("/api/evidence")
def evidence():
    return load_evidence()


@app.get("/api/replay")
def replay_api():
    return replay()


@app.get("/api/samples")
def samples():
    folder = APP / "samples"
    titles = {
        "alba_cafe": "카페 알바 계약서",
        "oneroom_lease": "원룸 월세 계약서",
        "clean_alba": "표준 근로계약서",
    }
    items = []
    for path in sorted(folder.glob("*.txt")):
        items.append({"id": path.stem, "name": path.stem, "title": titles.get(path.stem, path.stem)})
    answers = {}
    ans = folder / "answers.json"
    if ans.exists():
        answers = json.loads(ans.read_text(encoding="utf-8"))
    return {"samples": items, "answers": answers, "domains": DOMAIN_KO}


@app.get("/api/samples/{name}")
def sample_text(name: str):
    path = (APP / "samples" / f"{name}.txt").resolve()
    if path.parent != (APP / "samples").resolve() or not path.exists():
        return {"text": ""}
    return {"text": path.read_text(encoding="utf-8")}


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    text = body.text or ""
    domain = body.domain or guess_domain(text)
    clauses = split_clauses(text)

    def events():
        t0 = time.perf_counter()
        yield _sse("meta", {"n": len(clauses), "domain": domain, "domain_ko": DOMAIN_KO.get(domain, domain)})
        left_ms = right_ms = 0.0
        left_calls = right_calls = 0
        verdicts = []
        for i, clause in enumerate(clauses):
            fut_l = POOL.submit(run_left, clause, body.include_articles)
            fut_r = POOL.submit(run_right, clause, body.oracle_slot, body.include_articles)
            left = fut_l.result()
            right = fut_r.result()
            left_ms += left["latency_ms"]
            right_ms += right["latency_ms"]
            left_calls += left["calls"]
            right_calls += right["calls"]
            verdicts.append({"i": i, "left": left["verdict"], "right": right["verdict"], "actor": right["actor"]})
            yield _sse(
                "clause",
                {"i": i, "left": left, "right": right, "differ": left["verdict"] != right["verdict"]},
            )
        wall = (time.perf_counter() - t0) * 1000
        summary = {
            "n": len(clauses),
            "domain": domain,
            "wall_ms": round(wall, 1),
            "left_ms": round(left_ms, 1),
            "right_ms": round(right_ms, 1),
            "left_calls": left_calls,
            "right_calls": right_calls,
            "verdicts": verdicts,
        }
        _log(summary)
        yield _sse("done", summary)

    return StreamingResponse(events(), media_type="text/event-stream")


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
def index():
    return FileResponse(APP / "static" / "index.html")


app.mount("/static", StaticFiles(directory=APP / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="info")
