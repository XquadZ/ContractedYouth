# -*- coding: utf-8 -*-
"""참고 JSON 로드. 레코드 1건 = 검색 1단위."""
from __future__ import annotations

import json
from pathlib import Path

from rag.paths_v1 import CORPUS, LAW_NODES


def _norm(raw: dict, fallback_id: str) -> dict | None:
    rec_id = str(raw.get("id") or fallback_id).strip()
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        text = raw.get("본문")
    if not isinstance(text, str) or not text.strip():
        return None
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        law = (raw.get("법령명") or "").strip()
        art = (raw.get("조문 번호") or "").strip()
        head = (raw.get("조문 제목") or "").strip()
        title = " ".join(p for p in (law, art, head) if p).strip()
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        source = (raw.get("법령명") or raw.get("출처 파일") or "").strip()
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    return {
        "id": rec_id,
        "title": title or rec_id,
        "text": text.strip(),
        "source": source or "",
        "tags": [str(t) for t in tags],
    }


def _from_records_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        rows = obj.get("records") or obj.get("items") or []
    elif isinstance(obj, list):
        rows = obj
    else:
        return []
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        rec = _norm(row, f"rec-{i+1:04d}")
        if rec:
            out.append(rec)
    return out


def _from_law_nodes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        rec = _norm(row, f"law-{i+1:04d}")
        if rec:
            out.append(rec)
    return out


def load_corpus(kb: str = "auto") -> tuple[list[dict], str]:
    """kb: auto | corpus | law. auto는 records.json에 본문이 있으면 그것, 없으면 실험용 조문 59개."""
    if kb not in ("auto", "corpus", "law"):
        raise ValueError(f"unknown kb: {kb}")
    file_rows = _from_records_file(CORPUS)
    if kb == "corpus":
        return file_rows, str(CORPUS)
    if kb == "law":
        return _from_law_nodes(LAW_NODES), str(LAW_NODES)
    if file_rows:
        return file_rows, str(CORPUS)
    return _from_law_nodes(LAW_NODES), str(LAW_NODES)
