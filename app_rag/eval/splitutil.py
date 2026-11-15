# -*- coding: utf-8 -*-
"""datasets/splits/dev_test_split.json 읽기. 설정 비교는 dev만.
FIX_ROUND1: v2 경로·clean twin 지원.
"""
from __future__ import annotations

import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
SPLIT_FILE = WORK / "datasets" / "splits" / "dev_test_split.json"
SPLIT_FILE_V2 = WORK / "datasets" / "splits" / "dev_test_split_v2.json"
DOMAINS = ("LEASE", "LOAN", "LAB")
CLEAN_JSONL = {
    "LEASE": WORK / "datasets" / "property" / "clean_twins" / "01_계약서.jsonl",
    "LOAN": WORK / "datasets" / "money" / "clean_twins" / "01_계약서.jsonl",
    "LAB": WORK / "datasets" / "work" / "clean_twins" / "01_계약서.jsonl",
}


def load_split_file(path: Path | None = None) -> dict:
    target = path or SPLIT_FILE
    return json.loads(target.read_text(encoding="utf-8"))


def load_split_ids(
    split: str,
    domain: str | None = None,
    path: Path | None = None,
    *,
    include_clean_twins: bool | None = None,
) -> set[str]:
    if split not in ("dev", "test"):
        raise ValueError("split must be dev or test")
    data = load_split_file(path)
    domains = [domain] if domain else list(DOMAINS)
    ids: set[str] = set()
    # v2는 domain.dev에 twin id가 이미 포함됨. include_clean_twins=False면 제외.
    use_clean = include_clean_twins
    if use_clean is None:
        use_clean = path is not None and Path(path).name.endswith("_v2.json")
    for name in domains:
        block = data.get(name) or {}
        part_ids = list(block.get(split) or [])
        if use_clean is False:
            twins = set((data.get("clean_twins") or {}).get(name, {}).get(split) or [])
            part_ids = [i for i in part_ids if i not in twins]
        ids.update(part_ids)
    return ids


def clean_twin_path(domain: str) -> Path:
    return CLEAN_JSONL[domain]
