# -*- coding: utf-8 -*-
"""NEUTRAL_CARDS: GPT 실행 전 비용 추정. 상한 $8."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

os.environ["CARDS_VERSION"] = "neutral"

from rag.criteria import clear_cards_cache, load_domain_cards  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import CRITERIA_EXTRA_RULES_NEUTRAL, CRITERIA_EXTRA_RULES_TUNED, build_judge_prompt  # noqa: E402
from rag.paths import OUT  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.settings import get_cards_version  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402

COST_CAP = 8.0
PRICING = {
    "gpt-4o-mini": {"in": 0.15, "out": 0.60, "label": "N-G1"},
    "gpt-4.1": {"in": 2.00, "out": 8.00, "label": "N-G2"},
}


def file_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> None:
    clear_cards_cache()
    assert get_cards_version() == "neutral"
    out = OUT / "quant_neutral"
    out.mkdir(parents=True, exist_ok=True)

    # provenance
    v3 = APP / "criteria" / "LAB_cards_v3.yaml"
    lab_n = APP / "criteria" / "neutral" / "LAB_cards.yaml"
    note = {
        "lab_neutral_source": "LAB_cards_v3.yaml",
        "lab_v3_ok": lab_n.read_bytes() == v3.read_bytes(),
        "lab_v3_reason": (
            "LAB_CARDS_FIX_LOG·PROGRESS상 v3는 라벨 정렬·uses_facts/blocking_if 분리까지. "
            "v4는 check_if를 줄인 A.X 실험 수정. 현재 LAB_cards.yaml은 safe 보강+LAB-GENERAL. "
            "따라서 모델 결과 튜닝 전 기준으로 v3를 중립으로 채택."
        ),
        "extra_rules_tuned_lines": CRITERIA_EXTRA_RULES_TUNED.strip().splitlines(),
        "extra_rules_neutral_lines": CRITERIA_EXTRA_RULES_NEUTRAL.strip().splitlines(),
        "extra_rules_history": [
            {
                "line": '- 조항이 criteria의 safe에 해당하고 violation·check_if에 해당하지 않으면 "문제 없음"으로 답한다.',
                "when": "카드 연결 최초 설계",
                "why": "safe 매칭 시 문제 없음 강제",
            },
            {
                "line": '- check_if에 해당할 때만 "확인 필요"로 답하고, needs_fact에 그 사실을 적는다.',
                "when": "카드 연결 최초 설계",
                "why": "확인 필요 남용 방지",
            },
            {
                "line": '- criteria의 violation 목록이 비어 있으면 "위반"·"위험"으로 답하지 않는다.',
                "when": "LAB 카드 연결/A.X 과잉경고 실험",
                "why": "PLACE·DUTY처럼 violation 빈 카드에서 위반 오탐 억제",
            },
            {
                "line": '- 근거 id가 부족해도 safe에 해당하면 "문제 없음"으로 답한다.',
                "when": "A.X 과잉경고 실험",
                "why": "검색 근거 부족으로 확인필요로 떨어지는 경우 완화",
            },
        ],
        "card_table": [],
    }
    pairs = [
        ("LAB", "tuned", APP / "criteria" / "LAB_cards.yaml"),
        ("LAB", "neutral", lab_n),
        ("LEASE", "tuned", APP / "criteria" / "LEASE_cards.yaml"),
        ("LEASE", "neutral", APP / "criteria" / "neutral" / "LEASE_cards.yaml"),
        ("LOAN", "tuned", APP / "criteria" / "LOAN_cards.yaml"),
        ("LOAN", "neutral", APP / "criteria" / "neutral" / "LOAN_cards.yaml"),
    ]
    for dom, ver, p in pairs:
        rows = load_domain_cards(dom) if ver == "neutral" else None
        # force load each file
        from rag.yamlutil import load as load_yaml

        data = [r for r in (load_yaml(p) or []) if isinstance(r, dict) and r.get("id")]
        note["card_table"].append(
            {
                "domain": dom,
                "version": ver,
                "path": str(p.relative_to(APP)),
                "n_cards": len(data),
                "sha256_16": file_hash(p),
                "ids": [r["id"] for r in data],
            }
        )

    index, _ = get_index()
    n = 0
    total_chars = 0
    for d in ("LAB", "LEASE", "LOAN"):
        for doc in load_domain_docs(d):
            full = "\n".join(s.get("text") or "" for s in doc["segs"])
            facts = extract_facts(full)
            facts["domain"] = d
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                text = seg.get("text") or ""
                hits = (index.search(strip_placeholders(text), domain=d, title="") or {}).get("hits") or []
                user, _, _ = build_judge_prompt(text, facts, hits, use_criteria=True)
                total_chars += len(user)
                n += 1
    avg_chars = total_chars / max(1, n)
    avg_in = int(avg_chars / 2)
    avg_out = 200
    costs = {}
    for mid, pr in PRICING.items():
        usd = n * (avg_in / 1e6 * pr["in"] + avg_out / 1e6 * pr["out"])
        costs[mid] = {"usd": round(usd, 4), "in_tok": n * avg_in, "out_tok": n * avg_out}
    total = round(sum(v["usd"] for v in costs.values()), 4)
    plan = {
        "cards_version": "neutral",
        "n_clauses": n,
        "avg_prompt_chars": round(avg_chars, 1),
        "avg_in_tok_est": avg_in,
        "avg_out_tok_est": avg_out,
        "pricing": PRICING,
        "cost_estimate_usd": {**costs, "total": total},
        "cost_cap_usd": COST_CAP,
        "over_cap": total > COST_CAP,
        "provenance": note,
        "judge_neutral_hash": file_hash(APP / "prompts" / "judge_neutral.txt"),
        "judge_tuned_hash": file_hash(APP / "prompts" / "judge.txt"),
    }
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== NEUTRAL GPT COST ESTIMATE ===")
    print(f"clauses={n} avg_in_tok~{avg_in} avg_out_tok~{avg_out}")
    for mid, c in costs.items():
        print(f"  {PRICING[mid]['label']} {mid}: ${c['usd']}")
    print(f"TOTAL ${total}  CAP ${COST_CAP}  over={total > COST_CAP}")
    print("WROTE", out / "plan.json")
    if total > COST_CAP:
        print("STOP: over cost cap — ask user")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
