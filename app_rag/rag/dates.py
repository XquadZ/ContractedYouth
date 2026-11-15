# -*- coding: utf-8 -*-
"""계약서 날짜와 연도별 최저임금. 추측하지 않는다."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from rag.paths import MIN_WAGE_YAML
from rag.yamlutil import load as load_yaml

DATE_RES = [
    re.compile(r"(?P<y>\d{4})\s*년\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일"),
    re.compile(r"(?P<y>\d{4})\.(?P<m>\d{1,2})\.(?P<d>\d{1,2})"),
    re.compile(r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"),
    re.compile(r"(?P<y>\d{4})/(?P<m>\d{1,2})/(?P<d>\d{1,2})"),
]
START_KEYS = ("근로개시일", "계약기간", "임대차기간", "차용일")
FALLBACK_KEYS = ("계약일", "작성일")
DATE_MISSING_NOTE = "계약서에 날짜가 없어 오늘 기준으로 봤어요."
DATE_INVALID_TMPL = "계약서 날짜 '{raw}'은 없는 날짜예요."


def load_min_wage(path: Path | None = None) -> dict[int, int]:
    spec = load_yaml(path or MIN_WAGE_YAML) or {}
    out: dict[int, int] = {}
    for key, val in spec.items():
        try:
            out[int(key)] = int(val)
        except (TypeError, ValueError):
            continue
    return out


def wage_for_year(year: int, table: dict[int, int] | None = None):
    table = table if table is not None else load_min_wage()
    return table.get(int(year))


def _to_iso(match: re.Match) -> str | None:
    try:
        y, m, d = int(match.group("y")), int(match.group("m")), int(match.group("d"))
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def iter_date_matches(text: str) -> list[tuple[int, int, str | None, str]]:
    """(start, end, iso_or_None, raw). iso가 None이면 달력에 없는 날짜."""
    found: list[tuple[int, int, str | None, str]] = []
    occupied: list[tuple[int, int]] = []
    for pat in DATE_RES:
        for match in pat.finditer(text or ""):
            span = (match.start(), match.end())
            if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                continue
            occupied.append(span)
            found.append((span[0], span[1], _to_iso(match), match.group(0)))
    found.sort(key=lambda x: x[0])
    return found


def iter_dates(text: str) -> list[tuple[int, int, str]]:
    return [(a, b, iso) for a, b, iso, _raw in iter_date_matches(text) if iso]


def invalid_date_raws(text: str) -> list[str]:
    seen = []
    for _a, _b, iso, raw in iter_date_matches(text or ""):
        if iso is None and raw not in seen:
            seen.append(raw)
    return seen


def _sentences(text: str) -> list[str]:
    chunks = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=다)\s+|(?<=요)\s+", line)
        chunks.extend([p.strip() for p in parts if p.strip()])
    return chunks or ([text.strip()] if (text or "").strip() else [])


def _date_before(sent: str, keyword: str) -> str | None:
    idx = sent.find(keyword)
    if idx < 0:
        return None
    before = [iso for start, end, iso in iter_dates(sent) if end <= idx]
    return before[-1] if before else None


def _date_immediately_before(sent: str, keyword: str) -> str | None:
    idx = sent.find(keyword)
    if idx < 0:
        return None
    hits = [(end, iso) for start, end, iso in iter_dates(sent) if end <= idx and not sent[end:idx].strip()]
    return hits[-1][1] if hits else None


def _sents_with_keys(text: str, keys: tuple[str, ...]) -> list[str]:
    out = []
    for sent in _sentences(text):
        if any(k in sent for k in keys) and iter_dates(sent):
            out.append(sent)
    return out


def _end_from_sentence(sent: str) -> str | None:
    end = _date_before(sent, "까지")
    if re.search(r"기간의\s*정함이\s*없", sent):
        return None
    return end


def extract_dates(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    blob = text or ""
    invalid = invalid_date_raws(blob)
    start = None
    end = None
    source = None

    for sent in _sents_with_keys(blob, START_KEYS):
        cand = _date_immediately_before(sent, "부터") or _date_before(sent, "부터")
        if cand:
            start, source = cand, sent
            end = _end_from_sentence(sent)
            break

    if start is None:
        for sent in _sentences(blob):
            cand = _date_immediately_before(sent, "부터")
            if cand:
                start, source = cand, sent
                end = _end_from_sentence(sent)
                break

    if start is None:
        for sent in _sents_with_keys(blob, FALLBACK_KEYS):
            dates = iter_dates(sent)
            if dates:
                start, source = dates[0][2], sent
                end = _end_from_sentence(sent)
                break

    if start is None:
        return {
            "start_date": today.isoformat(),
            "end_date": None,
            "date_source": None,
            "date_missing": True,
            "date_invalid": invalid,
        }
    return {
        "start_date": start,
        "end_date": end,
        "date_source": (source or "")[:240],
        "date_missing": False,
        "date_invalid": invalid,
    }


def _parse_iso(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        y, m, d = [int(x) for x in str(raw).split("-")[:3]]
        return date(y, m, d)
    except ValueError:
        return None


def min_wage_verdict(facts: dict, today: date | None = None) -> dict | None:
    """근로 시급만. hourly_wage가 없으면 None."""
    hourly = facts.get("hourly_wage")
    if hourly is None or not isinstance(hourly, (int, float)):
        return None
    today = today or date.today()
    table = load_min_wage()
    start = _parse_iso(facts.get("start_date")) or today
    end = _parse_iso(facts.get("end_date"))
    date_missing = bool(facts.get("date_missing"))
    start_year = start.year
    floor = wage_for_year(start_year, table)
    notes = []
    if date_missing:
        notes.append(DATE_MISSING_NOTE)
    if floor is None:
        return {
            "fired": [],
            "verdict": None,
            "why": " ".join(notes + [f"{start_year}년 최저임금은 표에 없다."]).strip(),
            "year": start_year,
            "floor": None,
        }
    if hourly < floor:
        why = f"시급 {int(hourly)}원은 {start_year}년 최저임금 {floor}원 미만이다."
        if notes:
            why = notes[0] + " " + why
        return {"fired": ["min_wage"], "verdict": "위반", "why": why, "year": start_year, "floor": floor}

    later_years: list[int] = []
    if end is None:
        nxt = sorted(y for y in table if y > start_year)
        if nxt:
            later_years = [nxt[0]]
    else:
        later_years = [y for y in sorted(table) if start_year < y <= end.year]

    for year in later_years:
        need = table[year]
        if hourly < need:
            why = f"{year}년 1월부터는 시급 {need}원 이상으로 올려야 해요."
            if notes:
                why = notes[0] + " " + why
            return {
                "fired": ["min_wage_future"],
                "verdict": "확인 필요",
                "why": why,
                "year": year,
                "floor": need,
            }
    why = ""
    if notes:
        why = notes[0]
    return {"fired": [], "verdict": "문제 없음", "why": why, "year": start_year, "floor": floor}
