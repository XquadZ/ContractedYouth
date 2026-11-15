# -*- coding: utf-8 -*-
"""계약서 텍스트 → v2 RAG 리포트. 로컬 A.X만 호출한다. 계약서 원문은 디스크에 쓰지 않는다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from rag.corpus import convert_law_nodes, load_corpus, propose_tags, write_records, write_tag_proposal  # noqa: E402
from rag.paths import CORPUS, OUT, STD_ITEM_RULES, TAG_PROPOSAL  # noqa: E402
from rag.pipeline import run, write_outputs  # noqa: E402
from rag.split import split_contract  # noqa: E402


def _ensure_corpus() -> None:
    records, skipped = load_corpus()
    if records:
        print("CORPUS", len(records), "skipped", len(skipped))
        return
    converted, conv_skip = convert_law_nodes()
    write_records(converted)
    rows = propose_tags(converted, STD_ITEM_RULES)
    write_tag_proposal(rows)
    print("CONVERTED", len(converted), "skipped", len(conv_skip), "proposal", TAG_PROPOSAL)
    (OUT / "corpus_skipped.json").write_text(json.dumps(conv_skip, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="계약서 텍스트 파일")
    parser.add_argument("--text", type=str, default="", help="계약서 문자열")
    parser.add_argument("--no-llm", action="store_true", help="검색만. A.X 호출 없음")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--convert-corpus", action="store_true")
    parser.add_argument("--dump-split", action="store_true", help="분할만 표준출력")
    args = parser.parse_args()
    _ensure_corpus()
    if args.convert_corpus:
        return
    if args.file:
        text = args.file.read_text(encoding="utf-8")
    else:
        text = args.text
    if not text.strip():
        raise SystemExit("계약서 텍스트가 없다. --file 또는 --text")
    if args.dump_split:
        segs = split_contract(text)
        print(json.dumps(segs, ensure_ascii=False, indent=2))
        return
    report = run(text, no_llm=args.no_llm)
    dest = args.out or (OUT / "report.json")
    json_path, md_path = write_outputs(report, dest)
    print("WROTE", json_path)
    print("WROTE", md_path)
    s = report["summary"]
    print(
        "clauses",
        s["n_segments"],
        "viol",
        s["n_violation"],
        "risk",
        s["n_risk"],
        "review",
        s["n_review"],
        "ok",
        s["n_ok"],
        "kb",
        report.get("n_records"),
        "llm",
        report.get("llm"),
    )
    st = report.get("stats") or {}
    print("parse", st.get("parse_ok"), "/", st.get("parse_total"), "embed", st.get("embed_ok"), st.get("embed_error"))
    if report.get("llm_error"):
        print("LLM", report["llm_error"])


if __name__ == "__main__":
    main()
