from collections import Counter
import json
from pathlib import Path
RUN3=Path(r"C:\Users\DMLAB\pilot_root\run3")
def load(p):
  if not p.exists(): return []
  return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
items=load(RUN3/"items.jsonl") or load(RUN3/"smoke"/"items.jsonl")
teacher=load(RUN3/"teacher_outputs.jsonl") or load(RUN3/"smoke"/"teacher_outputs.jsonl")
build=RUN3/"build_sft_report.json"
rep={"items_n":len(items),"items_dom":dict(Counter(r["domain"] for r in items)),"teacher_n":len(teacher),"sft_B":len(load(RUN3/"sft_B.jsonl")),"build":json.loads(build.read_text(encoding="utf-8")) if build.exists() else None}
(RUN3/"_report_bits.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
print("ok", rep["items_n"], rep["teacher_n"])
