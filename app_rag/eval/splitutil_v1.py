# -*- coding: utf-8 -*-
"""datasets/splits/dev_test_split.json 읽기. 설정 비교는 dev만."""
from __future__ import annotations

import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
SPLIT_FILE = WORK / "datasets" / "splits" / "dev_test_split.json"
DOMAINS = ("LEASE", "LOAN", "LAB")


def load_split_file(path: Path | None = None) -> dict:
    target = path or SPLIT_FILE
    return json.loads(target.read_text(encoding="utf-8"))


def load_split_ids(split: str, domain: str | None = None, path: Path | None = None) -> set[str]:
    if split not in ("dev", "test"):
        raise ValueError("split must be dev or test")
    data = load_split_file(path)
    domains = [domain] if domain else list(DOMAINS)
    ids: set[str] = set()
    for name in domains:
        block = data.get(name) or {}
        ids.update(block.get(split) or [])
    return ids
