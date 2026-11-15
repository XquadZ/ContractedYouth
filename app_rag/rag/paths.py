# -*- coding: utf-8 -*-
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
CORPUS = APP / "corpus" / "records.json"
CORPUS_DIR = APP / "corpus"
PROMPTS = APP / "prompts"
OUT = APP / "out"
SAMPLES = APP / "samples"
EVAL = APP / "eval"
LAW_NODES = WORK / "exp_v2" / "law_node_texts.jsonl"
AX_URL = "http://127.0.0.1:8082/v1/chat/completions"
AX_HEALTH = "http://127.0.0.1:8082/health"
AX_GGUF = WORK / "data_local" / "models" / "A.X-4.0-Light-Q8_0.gguf"
LLAMA = WORK / "data_local" / "llama.cpp" / "b11755"
SERVER = LLAMA / "llama-server.exe"
BGE_SNAP = Path(
    r"C:\Users\DMLAB_Server1\.cache\huggingface\hub\models--BAAI--bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181"
)
STD_ITEM_RULES = CORPUS_DIR / "std_item_rules.yaml"
REQUIRED_ITEMS = CORPUS_DIR / "required_items.yaml"
TAG_PROPOSAL = CORPUS_DIR / "tag_proposal.csv"
EMBED_CACHE = CORPUS_DIR / "bge_m3.npz"
EMBED_NPY = CORPUS_DIR / "emb_bge_m3.npy"
EMBED_IDS = CORPUS_DIR / "emb_ids.json"
MIN_WAGE_YAML = APP / "config" / "min_wage.yaml"
SPLIT_FILE = WORK / "datasets" / "splits" / "dev_test_split.json"
LAW_API_CURRENT = WORK / "data_contract" / "law_api" / "현행"
GOLD = {
    "LEASE": {
        "contract": WORK / "datasets" / "property" / "v2_fixed" / "01_계약서.jsonl",
        "law": WORK / "datasets" / "property" / "v2_fixed" / "02_법률근거.jsonl",
    },
    "LOAN": {
        "contract": WORK / "datasets" / "money" / "v3_fixed" / "01_위반계약서_60건.jsonl",
        "law": WORK / "datasets" / "money" / "v3_fixed" / "02_법률근거_조항별_메모.jsonl",
    },
    "LAB": {
        "contract": WORK / "datasets" / "work" / "v3_1" / "01_계약서.jsonl",
        "law": WORK / "datasets" / "work" / "v3_1" / "02_법률근거.jsonl",
    },
}
ANALYZE_LOG = OUT / "analyze.jsonl"
JUDGE_PROMPT = PROMPTS / "judge.txt"
# 검색 하한. 카페 알바 1장에서 정했다. 바꾸려면 먼저 묻는다.
RRF_K = 60
RETRIEVE_K = 3
RETRIEVE_FLOOR = 0.016
# A.X 호출 값. 바꾸려면 먼저 묻는다.
AX_TEMPERATURE = 0
AX_MAX_TOKENS = 512
AX_TIMEOUT = 300
LEASE_INCREASE_CAP = 0.05
MAX_INTEREST = 0.20
