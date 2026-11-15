# -*- coding: utf-8 -*-
"""FIX_ROUND1-C: 임대 탐지 급등 원인 — 옛 judge vs 지금 judge (옛 dev 10장)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

import rag.generate as gen  # noqa: E402
from rag.criteria import select_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import ax_up, build_judge_prompt, generate_finding  # noqa: E402
from rag.paths import GOLD, OUT, PROMPTS  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from rag.verify import verify_finding  # noqa: E402
from recall_dev import canon_from_id, load_jsonl  # noqa: E402
from splitutil import SPLIT_FILE, load_split_ids  # noqa: E402
from metrics import rate, score_pair, summarize_rows  # noqa: E402
from dev_eval import is_meta  # noqa: E402

OLD_DEV = [
    "LEASE-0003",
    "LEASE-0014",
    "LEASE-0017",
    "LEASE-0026",
    "LEASE-0028",
    "LEASE-0035",
    "LEASE-0039",
    "LEASE-0040",
    "LEASE-0043",
    "LEASE-0050",
]


def load_lease_docs(ids: list[str]) -> list[dict]:
    contracts = load_jsonl(GOLD["LEASE"]["contract"])
    law_map = {r["segment_id"]: r for r in load_jsonl(GOLD["LEASE"]["law"])}
    by = {}
    for row in contracts:
        by.setdefault(row["doc_id"], []).append(row)
    docs = []
    for did in ids:
        segs = sorted(
            by[did],
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        docs.append({"domain": "LEASE", "doc_id": did, "segs": segs, "law_map": law_map})
    return docs


def run_once(name: str, judge_path: Path, docs, index) -> dict:
    gen.JUDGE_TMPL = judge_path.read_text(encoding="utf-8")
    # rebuild CRITERIA placeholder behavior uses current generate.py
    all_rows = []
    t0 = time.perf_counter()
    for doc in docs:
        full = "\n".join(s.get("text") or "" for s in doc["segs"])
        facts = extract_facts(full)
        facts["domain"] = "LEASE"
        for seg in doc["segs"]:
            if is_meta(seg):
                continue
            text = seg.get("text") or ""
            hits = (index.search(strip_placeholders(text), domain="LEASE", title="") or {}).get("hits") or []
            finding = generate_finding(text, facts, hits, use_criteria=False)
            verified = verify_finding(
                text, hits, finding, facts, needs_fact_mode="legacy", selected_cards=[]
            )
            verdict = verified.get("verdict") or "확인 필요"
            label = seg.get("label") or ""
            all_rows.append(
                {
                    "doc_id": doc["doc_id"],
                    "segment_id": seg.get("segment_id"),
                    "label": label,
                    "verdict": verdict,
                    "ax_verdict": verified.get("ax_verdict"),
                    "bucket": score_pair(label, verdict),
                    "ax_review_to_ok": False,
                    "parse_ok": bool(verified.get("parse_ok")),
                    "latency_ms": 0,
                }
            )
        print(f"  [{name}] {doc['doc_id']} done", flush=True)
    wall = time.perf_counter() - t0
    summary = summarize_rows(all_rows)
    summary["wall_sec"] = round(wall, 2)
    summary["judge"] = str(judge_path.name)
    return {"name": name, "summary": summary, "n": len(all_rows)}


def sample_prompt(index) -> dict:
    docs = load_lease_docs(OLD_DEV[:1])
    doc = docs[0]
    full = "\n".join(s.get("text") or "" for s in doc["segs"])
    facts = extract_facts(full)
    facts["domain"] = "LEASE"
    seg = next(s for s in doc["segs"] if not is_meta(s))
    text = seg.get("text") or ""
    hits = (index.search(strip_placeholders(text), domain="LEASE", title="") or {}).get("hits") or []
    # restore current judge
    gen.JUDGE_TMPL = (PROMPTS / "judge.txt").read_text(encoding="utf-8")
    user, cards = build_judge_prompt(text, facts, hits, use_criteria=False)
    # redact contract body
    red = user
    if "<contract>" in red and "</contract>" in red:
        a = red.index("<contract>") + len("<contract>")
        b = red.index("</contract>")
        red = red[:a] + "\n…\n" + red[b:]
    return {
        "doc_id": doc["doc_id"],
        "segment_id": seg.get("segment_id"),
        "cards": [c.get("id") for c in cards],
        "criteria_block_excerpt": "…\n".join(
            [ln for ln in user.splitlines() if "criteria" in ln.lower() or ln.strip() == "(없음)"][:8]
        ),
        "has_violation_empty_rule": 'violation 목록이 비어 있으면' in user,
        "prompt_redacted": red,
    }


def change_table() -> list[dict]:
    return [
        {
            "file": "prompts/judge.txt",
            "change": "criteria 블록 + 카드 규칙 추가(v1→현재). FIX_C: 카드 전용 규칙은 {criteria_extra_rules}로 분리",
            "applies_to_LEASE": "criteria=(없음). 카드 규칙 줄은 수정 후 LEASE에 안 들어감",
        },
        {
            "file": "rag/generate.py",
            "change": "use_criteria+LAB만 select_cards. 카드 없으면 criteria=(없음). FIX_C: extra rules 조건부",
            "applies_to_LEASE": "use_criteria=False → 카드 없음",
        },
        {
            "file": "rag/verify.py",
            "change": "needs_fact cards/legacy, ax_review_to_ok, empty_violation_downgrade, min_wage 범위",
            "applies_to_LEASE": "legacy needs_fact·카드 없음. empty_violation_downgrade는 selected_cards 비면 미적용",
        },
        {
            "file": "rag/retrieve.py / corpus",
            "change": "검색 하한·RRF 고정. corpus 보강(회수 개선 이력)",
            "applies_to_LEASE": "예 — 임대 검색 품질에 영향 가능",
        },
        {
            "file": "rag/pipeline.py",
            "change": "LAB 기본 카드, select_cards 전달",
            "applies_to_LEASE": "도메인 LEASE면 카드 경로 비활성",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-only", action="store_true")
    args = parser.parse_args()

    if not ax_up():
        print("STOP A.X down")
        sys.exit(2)

    index, _ = get_index()
    prompt = sample_prompt(index)
    (OUT / "fix_round1_c_lease_prompt.txt").write_text(prompt["prompt_redacted"], encoding="utf-8")

    if args.prompt_only:
        print(json.dumps({k: v for k, v in prompt.items() if k != "prompt_redacted"}, ensure_ascii=False, indent=2))
        return

    docs = load_lease_docs(OLD_DEV)
    judge_n = sum(1 for d in docs for s in d["segs"] if not is_meta(s))
    print("LEASE_OLD_DEV", len(docs), "JUDGE", judge_n, "EST_MIN", round(judge_n * 2.64 / 60, 1), flush=True)

    runs = []
    # 1) 옛 judge + 지금 나머지
    runs.append(run_once("judge_v1", PROMPTS / "judge_v1.txt", docs, index))
    # 2) 고치기 전 카드규칙 포함 judge (judge_v3 = 백업본, 카드규칙 항상 포함)
    runs.append(run_once("judge_v3_pre_fix", PROMPTS / "judge_v3.txt", docs, index))
    # 3) 지금 judge (카드 규칙 조건부)
    runs.append(run_once("judge_fixed", PROMPTS / "judge.txt", docs, index))

    # restore
    gen.JUDGE_TMPL = (PROMPTS / "judge.txt").read_text(encoding="utf-8")

    payload = {
        "change_table": change_table(),
        "prompt_sample": {k: v for k, v in prompt.items() if k != "prompt_redacted"},
        "prompt_file": str(OUT / "fix_round1_c_lease_prompt.txt"),
        "runs": [
            {
                "name": r["name"],
                "judge": r["summary"]["judge"],
                "detect_rate": r["summary"]["detect_rate"],
                "warn_capture_rate": r["summary"]["warn_capture_rate"],
                "fp_rate": r["summary"]["fp_rate"],
                "overwarn_rate": r["summary"]["overwarn_rate"],
                "wall_sec": r["summary"]["wall_sec"],
                "n": r["n"],
            }
            for r in runs
        ],
    }
    dest = OUT / "fix_round1_c.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)
    for r in payload["runs"]:
        print(r["name"], "detect", r["detect_rate"], "warn", r["warn_capture_rate"], "fp", r["fp_rate"])


if __name__ == "__main__":
    main()
