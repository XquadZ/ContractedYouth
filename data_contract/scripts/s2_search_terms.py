# -*- coding: utf-8 -*-
"""2단계: 판결서·약관 텍스트 분석 데이터 탐색."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
OUT = ROOT / "data_contract" / "s2_results.json"

needles = [
    "판결서", "약관", "텍스트 분석", "법률규정", "법률_규정",
    "법률규정(판결서", "약관등", "dataSetSn=580", "TL_약관", "TS_약관",
]
bases = [
    ROOT,
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path(r"D:\\"),
    Path(r"E:\\"),
]
hits = []
for base in bases:
    if not base.exists():
        continue
    try:
        for p in base.rglob("*"):
            name = p.name
            if any(n in name for n in needles):
                try:
                    sz = p.stat().st_size if p.is_file() else -1
                except Exception:
                    sz = -1
                hits.append({"path": str(p), "is_dir": p.is_dir(), "bytes": sz})
                if len(hits) >= 100:
                    break
    except Exception as e:
        hits.append({"path": str(base), "error": repr(e)})
    if len(hits) >= 100:
        break

result = {
    "status": "미발견" if not hits else "후보있음",
    "search_roots": [str(b) for b in bases if b.exists()],
    "needles": needles,
    "hits": hits,
    "aihub_page": "https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&dataSetSn=580&topMenu=100",
    "note": "ROOT/Downloads/Desktop 및 D/E 드라이브에서 판결서·약관 데이터셋 폴더/zip 미발견. 사용자가 받은 위치 확인 후 data_contract/aihub_terms 로 해제 필요.",
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
(ROOT / "data_contract" / "aihub_terms" / "NOT_FOUND.txt").write_text(result["note"] + "\n", encoding="utf-8")
print(result["status"], "hits", len(hits))
