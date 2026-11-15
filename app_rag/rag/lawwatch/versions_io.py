# -*- coding: utf-8 -*-
"""카드 버전 YAML 읽기/쓰기."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from rag.lawwatch.paths import CRITERIA_VERSIONS
from rag.yamlutil import load as load_yaml

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def versions_path(card_id: str) -> Path:
    return CRITERIA_VERSIONS / f"{card_id}.yaml"


def load_card_versions(card_id: str) -> dict | None:
    path = versions_path(card_id)
    if not path.exists():
        return None
    data = load_yaml(path)
    if not isinstance(data, dict):
        return None
    return data


def dump_yaml(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        return
    # minimal fallback
    import json

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_card_versions(data: dict) -> Path:
    card_id = data["card_id"]
    path = versions_path(card_id)
    dump_yaml(data, path)
    return path


def card_fields(card: dict) -> dict:
    keys = ("safe", "violation", "check_if", "basis", "match_keywords", "uses_facts", "blocking_if", "title", "missing_basis")
    out = {}
    for k in keys:
        if k in card:
            out[k] = copy.deepcopy(card[k])
    return out


def current_cards_map(domain: str) -> dict[str, dict]:
    from rag.criteria import load_domain_cards

    return {c["id"]: c for c in load_domain_cards(domain) if c.get("id")}


def get_version_entry(card_id: str, version: int) -> dict | None:
    data = load_card_versions(card_id)
    if not data:
        return None
    for v in data.get("versions") or []:
        if int(v.get("version") or -1) == int(version):
            return v
    return None


def sorted_versions(card_id: str) -> list[dict]:
    data = load_card_versions(card_id)
    if not data:
        return []
    vers = list(data.get("versions") or [])
    vers.sort(key=lambda v: (v.get("effective_from") or "", int(v.get("version") or 0)))
    return vers


def has_any_version_files() -> bool:
    if not CRITERIA_VERSIONS.exists():
        return False
    return any(CRITERIA_VERSIONS.glob("*.yaml"))
