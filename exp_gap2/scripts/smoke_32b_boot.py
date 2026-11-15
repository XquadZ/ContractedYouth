# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1\scripts")))
from llm_server import chat, health, start_server, stop_server

print("starting 32B...", flush=True)
start_server("32B")
print("health", health(), flush=True)
r = chat(
    [{"role": "user", "content": 'Reply JSON only: {"ok": true}\n/no_think'}],
    temperature=0.0,
    max_tokens=32,
)
print(
    "chat_ok",
    bool(r.get("content")),
    "lat_ms",
    r.get("latency_total_ms"),
    "preview",
    repr((r.get("content") or "")[:80]),
    flush=True,
)
stop_server()
print("SMOKE_PASS", flush=True)
