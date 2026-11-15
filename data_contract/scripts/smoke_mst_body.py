# -*- coding: utf-8 -*-
import json
import re
import urllib.parse
import urllib.request
import winreg
from pathlib import Path

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
    oc, _ = winreg.QueryValueEx(k, "LAW_OC")

p = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\law_api\현행\근로기준법_search.json")
d = json.loads(p.read_text(encoding="utf-8"))
law = d["LawSearch"]["law"]
item = law[0] if isinstance(law, list) else law
mst = item["법령일련번호"]
q = urllib.parse.urlencode({"OC": oc, "target": "law", "type": "JSON", "MST": mst})
req = urllib.request.Request(
    "http://www.law.go.kr/DRF/lawService.do?" + q,
    headers={"User-Agent": "Mozilla/5.0"},
)
raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
raw2 = re.sub(r"OC=[^&\s\"]+", "OC=REDACTED", raw)
print("mst", mst, "len", len(raw))
print("head", raw2[:300])
print("ok_body", "없습니다" not in raw[:80] and len(raw) > 200)
