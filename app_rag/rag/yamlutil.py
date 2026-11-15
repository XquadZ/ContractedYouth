# -*- coding: utf-8 -*-
"""아주 얕은 YAML 읽기. 외부 패키지 없이 이 프로젝트 설정 파일만 다룬다."""
from __future__ import annotations

from pathlib import Path


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        return _parse(text)


def _parse(text: str):
    lines = [ln.rstrip() for ln in text.splitlines() if not ln.strip().startswith("#")]
    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        while stack and indent <= stack[-1][0]:
            if indent == stack[-1][0] and not isinstance(stack[-1][1], list):
                break
            if indent < stack[-1][0]:
                stack.pop()
                continue
            break
        parent = stack[-1][1]
        if stripped.startswith("- "):
            item_raw = stripped[2:]
            if isinstance(parent, list):
                target = parent
            else:
                raise ValueError(f"list item without list parent: {raw}")
            if ":" in item_raw and not item_raw.startswith("[") and not item_raw.startswith("'") and not item_raw.startswith('"'):
                key, _, val = item_raw.partition(":")
                key = key.strip()
                val = val.strip()
                node: dict = {}
                if val:
                    node[key] = _scalar(val)
                else:
                    node[key] = {}
                    stack.append((indent, node[key] if isinstance(node[key], dict) else node))
                target.append(node)
                if not val:
                    stack.append((indent, node))
            else:
                target.append(_scalar(item_raw))
            i += 1
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not isinstance(parent, dict):
                raise ValueError(f"key into non-dict: {raw}")
            if val == "" or val == "|" or val == ">":
                peek = lines[i + 1] if i + 1 < len(lines) else ""
                peek_indent = len(peek) - len(peek.lstrip(" ")) if peek.strip() else indent
                if peek.strip().startswith("- "):
                    parent[key] = []
                    stack.append((indent, parent[key]))
                else:
                    parent[key] = {}
                    stack.append((indent, parent[key]))
            else:
                parent[key] = _scalar(val)
            i += 1
            continue
        i += 1
    return root


def _scalar(val: str):
    if "#" in val:
        val = val.split("#", 1)[0].strip()
    if val in ("null", "~", ""):
        return None
    if val in ("true", "True"):
        return True
    if val in ("false", "False"):
        return False
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip().strip("'\"") for p in inner.split(",")]
        return parts
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val
