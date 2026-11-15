# -*- coding: utf-8 -*-
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
CORPUS = APP / "corpus" / "records.json"
PROMPTS = APP / "prompts"
OUT = APP / "out"
LAW_NODES = WORK / "exp_v2" / "law_node_texts.jsonl"
AX_URL = "http://127.0.0.1:8082/v1/chat/completions"
AX_HEALTH = "http://127.0.0.1:8082/health"
AX_GGUF = WORK / "data_local" / "models" / "A.X-4.0-Light-Q8_0.gguf"
LLAMA = WORK / "data_local" / "llama.cpp" / "b11755"
SERVER = LLAMA / "llama-server.exe"
