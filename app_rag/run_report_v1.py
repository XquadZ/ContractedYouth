# -*- coding: utf-8 -*-
"""계약서 텍스트 → RAG 리포트. 로컬 A.X만 호출한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from rag.paths_v1 import OUT  # noqa: E402
from rag.pipeline_v1 import run, to_markdown  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="계약서 텍스트 파일")
    parser.add_argument("--text", type=str, default="", help="계약서 문자열")
    parser.add_argument("--split", choices=("clause", "whole"), default="clause")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--kb", choices=("auto", "corpus", "law"), default="auto")
    parser.add_argument("--no-llm", action="store_true", help="검색만. A.X 호출 없음")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.file:
        text = args.file.read_text(encoding="utf-8")
    else:
        text = args.text
    if not text.strip():
        raise SystemExit("계약서 텍스트가 없다. --file 또는 --text")
    report = run(text, split=args.split, k=args.k, kb=args.kb, no_llm=args.no_llm)
    dest = args.out or (OUT / "report.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = dest.with_suffix(".md")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    print("WROTE", dest)
    print("WROTE", md_path)
    print("clauses", report["summary"]["n_clauses"], "kb", report["n_records"], "llm", report["llm"])
    if report.get("llm_error"):
        print("LLM", report["llm_error"])


if __name__ == "__main__":
    main()
