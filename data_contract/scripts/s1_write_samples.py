# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\s1_results.json")
d = json.loads(p.read_text(encoding="utf-8"))
out = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\s1_samples.md")
lines = []
lines.append("# S1 samples")
lines.append(f"buckets={d['bucket_counts_label_json']}")
lines.append(f"employment_non_labor_total={d['employment_non_labor_total']}")
lines.append("## employment detail")
for k, v in d["employment_detail_category_counts"].items():
    lines.append(f"- {k}: {v}")
lines.append("## taxonomy top 40")
for row in d["taxonomy_counts"][:40]:
    lines.append(f"- {row}")
for bucket, samples in d["sample_sections"].items():
    lines.append(f"## sample {bucket}")
    for s in samples:
        lines.append(f"### {s['path']}")
        lines.append(f"meta={s['meta']}")
        lines.append(f"n_sections={s['n_sections']}")
        for sec in s["sections_preview"][:8]:
            lines.append(
                f"- format={sec['format_type']} labels={sec['content_labels']} filled={sec['filled_status']}"
            )
            lines.append(f"  text: {sec['text_head_200']}")
lines.append("## content vocab top20")
for b, items in d["content_vocab_top20"].items():
    lines.append(f"### {b}")
    for lab, cnt in items:
        lines.append(f"- {lab}: {cnt}")

pkg = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발") / "계약 법률 문서 서식 데이터"
size = 0
n = 0
if pkg.exists():
    for f in pkg.rglob("*"):
        if f.is_file():
            size += f.stat().st_size
            n += 1
lines.append(f"## full_package path={pkg} files={n} GB={round(size/1024**3, 2)}")
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "GB", round(size / 1024**3, 2))
