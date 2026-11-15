# -*- coding: utf-8 -*-
"""서버에 있는 정답 조문·최저임금 고시를 corpus에 넣는다. LAW_OC 값은 출력하지 않는다."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.corpus import (  # noqa: E402
    FETCH_ARTICLES,
    FETCH_LAWS,
    LOCAL_EXTRA_ARTICLES,
    extract_article,
    load_corpus,
    min_wage_notice_record,
    mst_path,
    write_records,
)
from rag.paths import CORPUS, LAW_API_CURRENT  # noqa: E402

SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"


def oc_value() -> str:
    raw = os.environ.get("LAW_OC", "").strip()
    if raw:
        return raw
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        val, _typ = winreg.QueryValueEx(key, "LAW_OC")
        return str(val or "").strip()
    except Exception:
        return ""


def _redact(text: str) -> str:
    import re

    text = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", text or "")
    text = re.sub(r'("OC"\s*:\s*")[^"]+(")', r"\1REDACTED\2", text)
    return text


def _http(params: dict, base: str) -> tuple[bool, str, str]:
    q = urllib.parse.urlencode(params, doseq=True, encoding="utf-8")
    url = f"{base}?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
        text = raw.decode("utf-8", "replace")
        time.sleep(0.55)
        return True, text, ""
    except Exception as exc:
        time.sleep(0.55)
        return False, "", type(exc).__name__


def _parse(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def _pick_law(data, name: str):
    if data is None:
        return None
    node = data.get("LawSearch", data) if isinstance(data, dict) else {}
    cands = []
    law = node.get("law") if isinstance(node, dict) else None
    if isinstance(law, list):
        cands.extend([x for x in law if isinstance(x, dict)])
    elif isinstance(law, dict):
        cands.append(law)
    exact = [c for c in cands if c.get("법령명한글") == name]
    pool = exact or cands
    for item in pool:
        code = str(item.get("현행연혁코드", ""))
        if code == "현행" or "현행" in code:
            return item
    return pool[0] if pool else None


def fetch_bodies(key: str) -> dict:
    LAW_API_CURRENT.mkdir(parents=True, exist_ok=True)
    out = {"ok": [], "fail": []}
    for name in FETCH_LAWS:
        dest = mst_path(name)
        if dest.exists():
            out["ok"].append({"name": name, "status": "already_on_disk", "path": str(dest)})
            print("FETCH_SKIP_EXISTS", name)
            continue
        ok, text, err = _http({"OC": key, "target": "law", "type": "JSON", "query": name, "display": 20}, SEARCH)
        if not ok:
            out["fail"].append({"name": name, "step": "search", "error": err})
            print("FETCH_FAIL", name, "search", err)
            continue
        data = _parse(_redact(text))
        item = _pick_law(data, name)
        mst = (item or {}).get("법령일련번호")
        if not mst:
            out["fail"].append({"name": name, "step": "parse", "error": "no_mst"})
            print("FETCH_FAIL", name, "parse")
            continue
        ok2, body, err2 = _http({"OC": key, "target": "law", "type": "JSON", "MST": mst}, SERVICE)
        if not ok2 or not body or "없습니다" in body[:120]:
            out["fail"].append({"name": name, "step": "body", "error": err2 or "empty"})
            print("FETCH_FAIL", name, "body")
            continue
        dest.write_text(_redact(body), encoding="utf-8")
        out["ok"].append({"name": name, "status": "fetched", "path": str(dest)})
        print("FETCH_OK", name)
    return out


def add_one(existing_ids: set[str], law_name: str, art: str) -> dict:
    path = mst_path(law_name)
    rec_id = f"law:{law_name}:{art}"
    if rec_id in existing_ids or any(x.startswith(rec_id + ":") for x in existing_ids):
        print("SKIP_EXISTS", rec_id)
        return {"id": rec_id, "status": "exists"}
    if not path.exists():
        print("MISS_FILE", law_name, art)
        return {"id": rec_id, "status": "no_body_file"}
    rec = extract_article(path, art)
    if not rec:
        print("MISS_ARTICLE", law_name, art)
        return {"id": rec_id, "status": "article_not_in_file"}
    print("ADD", rec["id"], "chars", len(rec.get("text") or ""), "domain", rec.get("domain"))
    return {"id": rec["id"], "status": "added", "record": rec}


def main() -> None:
    key = oc_value()
    print("LAW_OC_SET", bool(key))
    fetch_result = None
    if key:
        fetch_result = fetch_bodies(key)
    else:
        print("미확인(LAW_OC 없음)")

    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = raw.get("records") if isinstance(raw, dict) else raw
    existing_ids = {r["id"] for r in rows if isinstance(r, dict)}
    added = []
    log = []
    for law_name, art in LOCAL_EXTRA_ARTICLES:
        item = add_one(existing_ids, law_name, art)
        log.append({k: v for k, v in item.items() if k != "record"})
        rec = item.get("record")
        if rec:
            rows.append(rec)
            existing_ids.add(rec["id"])
            added.append(rec["id"])

    notice = min_wage_notice_record()
    if notice["id"] in existing_ids:
        print("SKIP_EXISTS", notice["id"])
        log.append({"id": notice["id"], "status": "exists"})
    else:
        rows.append(notice)
        existing_ids.add(notice["id"])
        added.append(notice["id"])
        print("ADD", notice["id"], "chars", len(notice.get("text") or ""))
        log.append({"id": notice["id"], "status": "added"})

    fetched_added = []
    fetched_missing = []
    for law_name, art in FETCH_ARTICLES:
        item = add_one(existing_ids, law_name, art)
        log.append({k: v for k, v in item.items() if k != "record"})
        rec = item.get("record")
        if rec:
            rows.append(rec)
            existing_ids.add(rec["id"])
            added.append(rec["id"])
            fetched_added.append(rec["id"])
        elif item.get("status") != "exists":
            fetched_missing.append(f"{law_name} 제{art}조")

    write_records(rows)
    recs, skipped = load_corpus()
    write_records(recs)
    print("ADDED_IDS", json.dumps(added, ensure_ascii=False))
    print("ADDED_N", len(added))
    print("CORPUS_AFTER_EXPAND", len(recs), "skipped", json.dumps(skipped, ensure_ascii=False))
    print("FETCHED_ADDED", json.dumps(fetched_added, ensure_ascii=False))
    print("NOT_FETCHED", json.dumps(fetched_missing, ensure_ascii=False))
    payload = {
        "law_oc_set": bool(key),
        "fetch": fetch_result,
        "log": log,
        "added_ids": added,
        "corpus_n": len(recs),
        "not_fetched": fetched_missing,
    }
    dest = APP / "out" / "corpus_add.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
