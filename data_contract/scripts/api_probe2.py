# -*- coding: utf-8 -*-
import json
import os
import re
import time
import urllib.parse
import urllib.request
import winreg
from pathlib import Path


def oc():
    v = os.environ.get("LAW_OC", "").strip()
    if v:
        return v
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
        v, _ = winreg.QueryValueEx(k, "LAW_OC")
        return str(v).strip()


def get(base, params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            t = raw.decode(enc)
            break
        except Exception:
            t = raw.decode("utf-8", "replace")
    time.sleep(0.55)
    return t


def classify(t):
    if "<html" in t[:300].lower() or "<!DOCTYPE" in t[:80]:
        text = re.sub(r"<[^>]+>", " ", t)
        text = re.sub(r"\s+", " ", text).strip()
        return "html", text[:400]
    try:
        j = json.loads(t)
        return "json", {"keys": list(j.keys())[:10], "head": json.dumps(j, ensure_ascii=False)[:250]}
    except Exception:
        return "other", t[:200]


OC = oc()
S = "http://www.law.go.kr/DRF/lawSearch.do"
V = "http://www.law.go.kr/DRF/lawService.do"
tests = [
    ("eflaw list", S, {"OC": OC, "target": "eflaw", "type": "JSON", "query": "근로기준법", "display": 5}),
    ("lsHistory HTML", S, {"OC": OC, "target": "lsHistory", "type": "HTML", "query": "근로기준법", "display": 20}),
    ("lsHistory JSON", S, {"OC": OC, "target": "lsHistory", "type": "JSON", "query": "근로기준법", "display": 5}),
    ("ftc JSON body probe list", S, {"OC": OC, "target": "ftc", "type": "JSON", "query": "임대차 약관", "search": 2, "display": 10}),
    ("ftc XML", S, {"OC": OC, "target": "ftc", "type": "XML", "query": "임대차", "display": 5}),
]
# common ministry codes from open law
for tgt in [
    "moelExpc", "molitExpc", "mojExpc", "molegExpc", "els", "drfExpc",
    "expcMoel", "expcMolit", "expcMoj", "expcMoleg",
    "moel", "molit", "moj", "moleg",
    "elo", "eloMoel", "govExpc",
]:
    tests.append((tgt, S, {"OC": OC, "target": tgt, "type": "JSON", "query": "근로", "display": 3}))

out = []
for name, base, params in tests:
    try:
        t = get(base, params)
        kind, info = classify(t)
    except Exception as e:
        kind, info = "err", repr(e)
    print(name, kind, str(info)[:220])
    out.append({"name": name, "kind": kind, "info": info})

Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\api_probe2.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
