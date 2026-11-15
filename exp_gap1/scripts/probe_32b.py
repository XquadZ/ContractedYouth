# -*- coding: utf-8 -*-
import json
import time
import urllib.request
import sys

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from llm_server import start_server, stop_server, chat

stop_server()
start_server("32B")
t0 = time.time()
r = chat(
    [
        {"role": "system", "content": "JSON only."},
        {"role": "user", "content": 'Reply exactly {"ok": true}\n/no_think'},
    ],
    max_tokens=32,
)
print("sec", time.time() - t0)
print("content", r["content"])
print("lat", r["latency_total_ms"])
stop_server()
