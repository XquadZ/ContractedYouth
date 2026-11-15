# -*- coding: utf-8 -*-
import json
import os
import re
import urllib.parse
import urllib.request

OC = os.environ["LAW_OC"]
q = urllib.parse.urlencode(
    {"OC": OC, "target": "ftc", "type": "JSON", "query": "임대차 약관", "search": 2, "display": 2}
)
req = urllib.request.Request(
    "http://www.law.go.kr/DRF/lawSearch.do?" + q, headers={"User-Agent": "Mozilla/5.0"}
)
with urllib.request.urlopen(req, timeout=60) as r:
    t = r.read().decode("utf-8", "replace")
t = re.sub(r"OC=[^&\s\"]+", "OC=REDACTED", t)
j = json.loads(t)
ftc = j["Ftc"]["ftc"]
items = ftc if isinstance(ftc, list) else [ftc]
print("keys", sorted(items[0].keys()))
for k, v in items[0].items():
    print(k, ":", str(v)[:120])
# try body
for keyname in ("결정문일련번호", "일련번호", "판례일련번호"):
    pass
link = items[0].get("결정문상세링크") or items[0].get("상세링크") or ""
print("link fields", [k for k in items[0] if "링크" in k or "일련" in k])
m = re.search(r"ID=(\d+)", str(items[0]))
print("any ID in item", m.group(1) if m else None)
eid = items[0].get("결정문일련번호") or (m.group(1) if m else None)
if eid:
    q2 = urllib.parse.urlencode({"OC": OC, "target": "ftc", "type": "JSON", "ID": eid})
    req2 = urllib.request.Request(
        "http://www.law.go.kr/DRF/lawService.do?" + q2, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req2, timeout=60) as r:
        t2 = r.read().decode("utf-8", "replace")
    t2 = re.sub(r"OC=[^&\s\"]+", "OC=REDACTED", t2)
    print("body head", t2[:250].replace("\n", " "))
