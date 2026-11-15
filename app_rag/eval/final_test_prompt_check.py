# -*- coding: utf-8 -*-
"""FINAL_TEST 1: none 프롬프트에 카드가 없고 법 조문은 neutral·tuned와 같은지."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.criteria import clear_cards_cache  # noqa: E402
from rag.facts import extract_facts  # noqa: E402
from rag.generate import build_judge_prompt  # noqa: E402
from rag.pii import mask_pii  # noqa: E402
from rag.pipeline import get_index  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from quant_run import load_domain_docs  # noqa: E402
from dev_eval import is_meta  # noqa: E402
from final_test_common import QTEST  # noqa: E402


def _evidence_block(user: str) -> str:
    start = user.find("근거(이 id 중에서만 고른다):\n")
    end = user.find("\n\n지시:")
    if start < 0 or end < 0 or end <= start:
        return ""
    return user[start:end]


def main() -> None:
    index, _ = get_index()
    samples = []
    for domain in ("LAB", "LEASE", "LOAN"):
        for doc in load_domain_docs(domain, split="dev"):
            for seg in doc["segs"]:
                if is_meta(seg):
                    continue
                samples.append((domain, doc["doc_id"], seg))
                break
            if len(samples) >= 3:
                break
        if len(samples) >= 3:
            break

    lines = ["# none_prompt_check", "", "명령: `python -u -X utf8 eval/final_test_prompt_check.py`", ""]
    ok = True
    for domain, did, seg in samples:
        text, _ = mask_pii(seg.get("text") or "")
        facts = extract_facts(text)
        facts["domain"] = domain
        hits_raw = (index.search(strip_placeholders(text), domain=domain, title="") or {}).get("hits") or []
        prompts = {}
        for ver in ("none", "neutral", "tuned"):
            os.environ["CARDS_VERSION"] = ver
            clear_cards_cache()
            use_c = ver != "none"
            user, cards, hits2 = build_judge_prompt(text, facts, hits_raw, use_criteria=use_c)
            prompts[ver] = {"user": user, "cards": [c.get("id") for c in cards], "hits": [h.get("id") for h in hits2]}
        none_u = prompts["none"]["user"]
        has_card_words = any(x in none_u for x in ("LAB-", "LEASE-", "LOAN-", "violation", "safe:"))
        # criteria 블록이 (없음) 인지
        criteria_ok = "<criteria>\n(없음)\n</criteria>" in none_u or "기준 카드:\n<criteria>\n(없음)\n</criteria>" in none_u
        # none의 검색 hit 본문(카드 basis 제외)이 다른 버전의 검색 hit와 같은지:
        # 카드 basis 병합 전 검색 상위 3의 id
        base_ids = [h.get("id") for h in hits_raw[:3]]
        neu_ev = _evidence_block(prompts["neutral"]["user"])
        tun_ev = _evidence_block(prompts["tuned"]["user"])
        none_ev = _evidence_block(none_u)
        # none에는 basis 추가가 없으므로, 검색 상위 조문 텍스트가 none 근거에 들어가 있는지
        law_ok = True
        missing = []
        for h in hits_raw[:3]:
            t = h.get("text") or ""
            if t and t not in none_u:
                law_ok = False
                missing.append(h.get("id"))
        # none에 카드 id가 없는지
        card_ids_present = [cid for cid in (prompts["neutral"]["cards"] + prompts["tuned"]["cards"]) if cid and cid in none_u]
        row_ok = (not has_card_words) and criteria_ok and law_ok and not card_ids_present and not prompts["none"]["cards"]
        ok = ok and row_ok
        lines.append(f"## {domain} {did} {seg.get('segment_id')}")
        lines.append(f"- none cards: {prompts['none']['cards']}")
        lines.append(f"- neutral cards: {prompts['neutral']['cards']}")
        lines.append(f"- tuned cards: {prompts['tuned']['cards']}")
        lines.append(f"- search top3 ids: {base_ids}")
        lines.append(f"- none criteria=(없음): {criteria_ok}")
        lines.append(f"- none에 카드 id 없음: {not card_ids_present} ({card_ids_present})")
        lines.append(f"- 검색 법 조문 본문이 none에 있음: {law_ok} missing={missing}")
        lines.append(f"- none 근거 길이={len(none_ev)} neutral={len(neu_ev)} tuned={len(tun_ev)}")
        lines.append(f"- 판정: {'OK' if row_ok else 'FAIL'}")
        lines.append("")
        lines.append("### none user (앞 800자)")
        lines.append("```")
        lines.append(none_u[:800])
        lines.append("```")
        lines.append("")
    lines.append(f"## 종합: {'OK' if ok else 'FAIL'}")
    out = QTEST / "none_prompt_check.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", out, "ok=", ok, flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
