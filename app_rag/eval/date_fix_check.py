# -*- coding: utf-8 -*-
"""날짜 추출 수정 확인: 4건 + 최저임금 6건 + 도메인별 못 찾음 + 계약일 이상치 + --split."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.dates import DATE_INVALID_TMPL, extract_dates, min_wage_verdict  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.paths import GOLD, OUT, SAMPLES  # noqa: E402
from rag.report import find_mismatches  # noqa: E402
from rag.split import split_contract  # noqa: E402
from splitutil import load_split_ids  # noqa: E402

CONTRACT_DATE_RE = re.compile(
    r"(?:계약일|작성일)\s*[:：]?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
)


def join_docs(path: Path) -> dict[str, str]:
    docs = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        docs[row["doc_id"]].append(row.get("text") or "")
    return {did: "\n".join(texts) for did, texts in docs.items()}


def contract_date_iso(text: str) -> str | None:
    match = CONTRACT_DATE_RE.search(text or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def date_stats(path: Path) -> dict:
    docs = join_docs(path)
    missing = []
    start_ok = end_ok = end_null = 0
    outliers = []
    examples = []
    for did, text in docs.items():
        got = extract_dates(text)
        if got["date_missing"] or not got["start_date"]:
            missing.append({"doc_id": did, "got": got})
        if got["start_date"] and not got["date_missing"]:
            start_ok += 1
        if got["end_date"]:
            end_ok += 1
        elif not got["date_missing"]:
            end_null += 1
        signed = contract_date_iso(text)
        start = got.get("start_date")
        if signed and start and not got.get("date_missing"):
            sy, sm, sd = [int(x) for x in start.split("-")[:3]]
            cy, cm, cd = [int(x) for x in signed.split("-")[:3]]
            sdt, cdt = date(sy, sm, sd), date(cy, cm, cd)
            if sdt < cdt or sdt > cdt + timedelta(days=366):
                outliers.append(
                    {
                        "doc_id": did,
                        "start_date": start,
                        "contract_date": signed,
                        "days": (sdt - cdt).days,
                        "date_source": got.get("date_source"),
                    }
                )
        if len(examples) < 3:
            examples.append({"doc_id": did, **got})
    return {
        "path": str(path),
        "n_docs": len(docs),
        "missing_start_or_date_missing": len(missing),
        "missing_ids": [m["doc_id"] for m in missing],
        "missing_detail": missing,
        "start_found": start_ok,
        "end_found": end_ok,
        "end_null_but_start_found": end_null,
        "start_vs_contract_outliers": outliers,
        "examples": examples,
    }


def wage_cases() -> list[dict]:
    cases = [
        {"name": "c1", "start_date": "2026-03-02", "end_date": "2026-08-31", "hourly_wage": 10320, "date_missing": False, "expect": "문제 없음"},
        {"name": "c2", "start_date": "2026-03-02", "end_date": "2027-03-01", "hourly_wage": 10320, "date_missing": False, "expect": "확인 필요"},
        {"name": "c3", "start_date": "2026-03-02", "end_date": None, "hourly_wage": 10500, "date_missing": False, "expect": "확인 필요"},
        {"name": "c4", "start_date": "2026-03-02", "end_date": "2027-03-01", "hourly_wage": 10820, "date_missing": False, "expect": "문제 없음"},
        {"name": "c5", "start_date": "2027-01-04", "end_date": "2027-12-31", "hourly_wage": 10320, "date_missing": False, "expect": "위반"},
        {"name": "c6", "start_date": None, "end_date": None, "hourly_wage": 10000, "date_missing": True, "expect": "위반"},
    ]
    rows = []
    for case in cases:
        facts = {
            "hourly_wage": case["hourly_wage"],
            "start_date": case["start_date"],
            "end_date": case["end_date"],
            "date_missing": case["date_missing"],
        }
        if case["date_missing"]:
            facts.update(extract_dates(""))
            facts["hourly_wage"] = 10000
        got = min_wage_verdict(facts)
        row = {
            "name": case["name"],
            "expect": case["expect"],
            "got": (got or {}).get("verdict"),
            "why": (got or {}).get("why"),
            "facts": {k: facts.get(k) for k in ("start_date", "end_date", "hourly_wage", "date_missing")},
            "match": (got or {}).get("verdict") == case["expect"],
        }
        rows.append(row)
        print("WAGE", json.dumps(row, ensure_ascii=False))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    work_docs = join_docs(GOLD["LAB"]["contract"])
    expect = {
        "WORK-0001": {"start_date": "2026-03-02", "flag": None},
        "WORK-0010": {"start_date": "2026-05-04", "flag": None},
        "WORK-0032": {"start_date": "2026-10-05", "flag": None},
        "WORK-0026": {"start_date": "2026-08-21", "flag": "date_invalid"},
    }
    four = []
    for did, spec in expect.items():
        text = work_docs.get(did, "")
        got = extract_dates(text)
        facts = extract_facts(text)
        mismatches = find_mismatches(split_contract(text), facts)
        notes = [m.get("note") for m in mismatches if m.get("type") == "date_invalid"]
        invalid = got.get("date_invalid") or []
        flag_ok = True
        if spec["flag"] == "date_invalid":
            flag_ok = bool(invalid) and any("date_invalid" == m.get("type") for m in mismatches)
        else:
            flag_ok = not invalid
        row = {
            "doc_id": did,
            "expect_start": spec["start_date"],
            "got_start": got.get("start_date"),
            "date_missing": got.get("date_missing"),
            "date_source": got.get("date_source"),
            "date_invalid": invalid,
            "mismatch_notes": notes,
            "start_ok": got.get("start_date") == spec["start_date"] and not got.get("date_missing"),
            "flag_ok": flag_ok,
        }
        four.append(row)
        print("FOUR", json.dumps(row, ensure_ascii=False))
        for note in notes:
            print("INVALID_NOTE", did, note)

    wage_rows = wage_cases()

    alba = (SAMPLES / "alba_cafe.txt").read_text(encoding="utf-8")
    print("FACTS_ALBA", json.dumps(extract_facts(alba), ensure_ascii=False))

    domain_dates = {}
    for domain, spec in GOLD.items():
        domain_dates[domain] = date_stats(spec["contract"])
        slim = {k: domain_dates[domain][k] for k in ("n_docs", "missing_start_or_date_missing", "start_found", "end_found", "end_null_but_start_found", "missing_ids")}
        print("DATES", domain, json.dumps(slim, ensure_ascii=False))
        print("OUTLIERS", domain, json.dumps(domain_dates[domain]["start_vs_contract_outliers"], ensure_ascii=False))

    split_counts = {}
    for split_name in ("dev", "test"):
        split_counts[split_name] = {}
        for domain in ("LEASE", "LOAN", "LAB"):
            ids = load_split_ids(split_name, domain)
            split_counts[split_name][domain] = len(ids)
            print("SPLIT", split_name, domain, len(ids))

    payload = {
        "four": four,
        "wage": wage_rows,
        "dates": domain_dates,
        "split_counts": split_counts,
        "date_invalid_tmpl": DATE_INVALID_TMPL,
    }
    dest = OUT / "date_fix_run.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
