# -*- coding: utf-8 -*-
import json
import os
import re
import urllib.parse
import urllib.request

OC = os.environ["LAW_OC"]
q = urllib.parse.urlencode(
    {"OC": OC, "target": "moelCgmExpc", "type": "JSON", "query": "근로계약", "display": 1, "search": 2}
)
req = urllib.request.Request(
    "http://www.law.go.kr/DRF/lawSearch.do?" + q, headers={"User-Agent": "Mozilla/5.0"}
)
with urllib.request.urlopen(req, timeout=60) as r:
    t = r.read().decode("utf-8", "replace")
t = re.sub(r"OC=[^&\s\"]+", "OC=REDACTED", t)
j = json.loads(t)
raw_items = j["CgmExpc"]["cgmExpc"]
if isinstance(raw_items, dict):
    items = [raw_items]
else:
    items = list(raw_items)
item = items[0]
print("n", len(items), "keys", sorted(item.keys()))
print("link", item.get("법령해석상세링크"))
m = re.search(r"ID=(\d+)", item.get("법령해석상세링크", "") or "")
print("id_from_link", m.group(1) if m else None)
eid = m.group(1)
for typ in ("JSON", "HTML", "XML"):
    q2 = urllib.parse.urlencode({"OC": OC, "target": "moelCgmExpc", "type": typ, "ID": eid})
    req2 = urllib.request.Request(
        "http://www.law.go.kr/DRF/lawService.do?" + q2, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req2, timeout=60) as r:
        t2 = r.read().decode("utf-8", "replace")
    t2r = re.sub(r"OC=[^&\s\"]+", "OC=REDACTED", t2)
    print("--- body", typ, "len", len(t2), "head", t2r[:180].replace("\n", " "))
