import json,statistics
from pathlib import Path
from collections import defaultdict
run3=Path(r"C:\Users\DMLAB\pilot_root\run3")
d=defaultdict(list)
for tag in "A","B","C":
  p=run3/f"eval_outputs_{tag}.jsonl"
  if not p.exists(): continue
  for l in p.read_text(encoding="utf-8").splitlines():
    if not l.strip(): continue
    r=json.loads(l); d[tag].append(float(r.get("gen_sec") or 0))
for m,v in d.items():
  print(m,"done",len(v),"/88 mean_sec",round(sum(v)/len(v),2) if v else None)
