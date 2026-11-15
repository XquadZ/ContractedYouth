# -*- coding: utf-8 -*-
import json
import os
import re
import time
import urllib.parse
import urllib.request

OC = os.environ["LAW_OC"]
SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
targets = [
    "moelCgmExpc",
    "molitCgmExpc",
    "mojCgmExpc",
    "molegCgmExpc",
    "cgmExpc",
    "expc",
    "ftc",
    "lstrm",
    "lstrmRlt",
    "admrul",
]
for tgt in targets:
    params = {"OC": OC, "target": tgt, "type": "JSON", "query": "근로", "display": 2, "search": 2}
    if tgt == "admrul":
        params = {"OC": OC, "target": tgt, "type": "JSON", "query": "적용 최저임금 고시", "display": 3, "nw": 2}
    if tgt == "lstrmRlt":
        params = {"OC": OC, "target": tgt, "type": "JSON", "query": "근로계약"}
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(SEARCH + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        t = raw.decode("utf-8", "replace")
    except Exception as e:
        print(tgt, "ERR", e)
        continue
    html = t.lstrip().lower().startswith("<!doctype") or t.lstrip().lower().startswith("<html")
    if html:
        msg = re.sub(r"<[^>]+>", " ", t)
        msg = re.sub(r"\s+", " ", msg).strip()[:160]
        print(tgt, "HTML", msg)
    else:
        try:
            j = json.loads(t)
            print(tgt, "JSON", list(j.keys())[:6], t[:100].replace("\n", " "))
        except Exception:
            print(tgt, "NOTJSON", t[:100])
    time.sleep(0.5)
