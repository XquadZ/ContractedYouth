# -*- coding: utf-8 -*-
"""법령 MST JSON → 조문·부칙 정규화."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


def load_mst(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("법령") or data


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def flatten_text(node: Any) -> str:
    parts: list[str] = []

    def walk(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            s = x.strip()
            if s:
                parts.append(s)
            return
        if isinstance(x, list):
            for i in x:
                walk(i)
            return
        if isinstance(x, dict):
            for key in ("조문내용", "항내용", "호내용", "목내용", "부칙내용", "content", "텍스트"):
                if key in x:
                    walk(x[key])
            for k, v in x.items():
                if k in ("조문내용", "항내용", "호내용", "목내용", "부칙내용", "content", "텍스트"):
                    continue
                if isinstance(v, (str, list, dict)):
                    walk(v)

    walk(node)
    return "\n".join(parts)


def _art_no(unit: dict) -> str:
    no = str(unit.get("조문번호") or "").strip()
    branch = str(unit.get("조문가지번호") or "").strip()
    if branch and branch not in ("0", "None"):
        # 가지번호가 "2"이면 6의2 형태
        if branch.isdigit():
            return f"{no}의{branch}" if no else branch
        return f"{no}{branch}" if no else branch
    return no


def article_id(law_name: str, unit: dict, *, prefix: str = "law") -> str | None:
    if (unit.get("조문여부") or "") == "전문":
        # 본문만 있는 규정(조번호 0) → 조 0
        no = _art_no(unit) or "0"
        return f"{prefix}:{law_name}:{no}"
    no = _art_no(unit)
    if not no:
        return None
    return f"{prefix}:{law_name}:{no}"


def prefix_for_law(law_name: str) -> str:
    if "시행령" in law_name or "시행규칙" in law_name:
        return "decree"
    if "고시" in law_name or "규정" in law_name and "최고이자율" in law_name:
        # 최고이자율 규정은 corpus에서 law: 로 안 쓰이고 notice/별도 — 본문은 law 취급 가능
        if "최고이자율" in law_name:
            return "law"
        return "notice"
    return "law"


def extract_articles(law: dict, law_name: str | None = None) -> list[dict]:
    basic = law.get("기본정보") or {}
    name = law_name or basic.get("법령명_한글") or basic.get("법령명한글") or ""
    prefix = prefix_for_law(name)
    units = _as_list((law.get("조문") or {}).get("조문단위"))
    out = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        aid = article_id(name, unit, prefix=prefix)
        if not aid:
            continue
        text = flatten_text(unit)
        out.append(
            {
                "id": aid,
                "article_no": _art_no(unit),
                "title": (unit.get("조문제목") or "").strip(),
                "text": text,
                "raw": unit,
            }
        )
    return out


def extract_byeol(law: dict) -> list[dict]:
    units = _as_list((law.get("부칙") or {}).get("부칙단위"))
    out = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        lines = []
        content = unit.get("부칙내용")
        if isinstance(content, str):
            lines = [content]
        else:
            flat = flatten_text(content).splitlines()
            lines = [ln.strip() for ln in flat if ln.strip()]
        out.append(
            {
                "key": unit.get("부칙키"),
                "announced": _ymd(unit.get("부칙공포일자")),
                "number": str(unit.get("부칙공포번호") or ""),
                "lines": lines,
                "text": "\n".join(lines),
            }
        )
    return out


def basic_meta(law: dict) -> dict:
    basic = law.get("기본정보") or {}
    mst = str(basic.get("법령일련번호") or "")
    law_key = str(law.get("법령키") or "")
    if not mst and law_key:
        # 법령키 앞부분이 ID인 경우가 많음. MST는 search에서 보완.
        mst = ""
    return {
        "name": basic.get("법령명_한글") or basic.get("법령명한글") or "",
        "law_id": str(basic.get("법령ID") or ""),
        "mst": mst,
        "announce_no": str(basic.get("공포번호") or ""),
        "announced": _ymd(basic.get("공포일자")),
        "effective": _ymd(basic.get("시행일자") or basic.get("시행일")),
        "revision_type": basic.get("제개정구분") or "",
        "law_key": law_key,
    }


def _ymd(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def normalize_space(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "", flags=re.UNICODE)


def clone_with_article_text(law: dict, new_text: str) -> dict:
    """단일 조문 규정의 본문만 바꾼 복사본(과거 이자율 재구성용)."""
    out = deepcopy(law)
    jo = out.get("조문") or {}
    unit = jo.get("조문단위")
    if isinstance(unit, dict):
        unit["조문내용"] = new_text
    elif isinstance(unit, list) and unit:
        unit[0]["조문내용"] = new_text
    return out
