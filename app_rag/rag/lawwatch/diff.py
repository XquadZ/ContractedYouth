# -*- coding: utf-8 -*-
"""조문 비교 · 영향 카드 · 부칙 추출."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rag.lawwatch.byeol import extract_rule_sentences, resolve_apply_rule
from rag.lawwatch.parse import normalize_space
from rag.paths import APP, CORPUS
from rag.lawwatch.paths import LAWWATCH_OUT
from rag.lawwatch.store import load_version
from rag.yamlutil import load as load_yaml


def _classify_change(before: str, after: str) -> str:
    if before == after:
        return "동일"
    if normalize_space(before) == normalize_space(after):
        return "형식 변경"
    return "변경"


def diff_articles(before_arts: list[dict], after_arts: list[dict]) -> list[dict]:
    bmap = {a["id"]: a for a in before_arts}
    amap = {a["id"]: a for a in after_arts}
    ids = sorted(set(bmap) | set(amap))
    out = []
    for aid in ids:
        b = bmap.get(aid)
        a = amap.get(aid)
        if b and not a:
            out.append({"id": aid, "kind": "삭제", "before": b.get("text") or "", "after": ""})
        elif a and not b:
            out.append({"id": aid, "kind": "추가", "before": "", "after": a.get("text") or ""})
        else:
            kind = _classify_change(b.get("text") or "", a.get("text") or "")
            if kind == "동일":
                continue
            out.append(
                {
                    "id": aid,
                    "kind": kind,
                    "before": b.get("text") or "",
                    "after": a.get("text") or "",
                    "title": (a or b).get("title") or "",
                }
            )
    return out


def _load_all_cards() -> list[dict]:
    cards = []
    for domain in ("LAB", "LEASE", "LOAN"):
        path = APP / "criteria" / f"{domain}_cards.yaml"
        if not path.exists():
            continue
        for row in load_yaml(path) or []:
            if isinstance(row, dict) and row.get("id"):
                c = dict(row)
                c["_domain"] = domain
                cards.append(c)
    return cards


def find_impacted_cards(changed_ids: list[str], cards: list[dict] | None = None) -> list[dict]:
    cards = cards if cards is not None else _load_all_cards()
    changed = set(changed_ids)
    hit = []
    for card in cards:
        basis = [str(x) for x in (card.get("basis") or [])]
        overlap = [b for b in basis if b in changed or any(b.startswith(cid) or cid.startswith(b) for cid in changed)]
        # prefix match: law:이자제한법:2 vs law:이자제한법:2:1
        if not overlap:
            for b in basis:
                for cid in changed:
                    if b == cid or b.startswith(cid + ":") or cid.startswith(b + ":"):
                        overlap.append(b)
                        break
        if overlap:
            hit.append({"card_id": card["id"], "domain": card.get("_domain"), "basis_hit": sorted(set(overlap)), "title": card.get("title")})
    return hit


def find_impacted_records(changed_ids: list[str]) -> list[str]:
    if not CORPUS.exists():
        return []
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    changed = set(changed_ids)
    out = []
    for rec in data.get("records") or []:
        rid = rec.get("id") or ""
        if rid in changed or any(rid.startswith(cid + ":") or cid.startswith(rid + ":") for cid in changed):
            out.append(rid)
    return out


_NUMERIC_HINTS = re.compile(r"(최저임금|최고이자|이자율|증액|100분의\s*\d+|연\s*\d+\s*퍼센트|\d{4,5}\s*원)")

# 숫자 기준 법령명 → 영향 카드 (basis ID가 규정 본문과 다를 때)
NUMERIC_LAW_CARDS = {
    "이자제한법 제2조제1항의 최고이자율에 관한 규정": ["LOAN-INTEREST"],
    "최저임금법": ["LAB-MINWAGE"],
    "최저임금법 시행령": ["LAB-MINWAGE", "LAB-PROBATION"],
    "주택임대차보호법": ["LEASE-RENEW", "LEASE-RENT"],
    "주택임대차보호법 시행령": ["LEASE-RENT"],
}


def flag_numeric_changes(changes: list[dict]) -> list[dict]:
    out = []
    for ch in changes:
        blob = (ch.get("before") or "") + "\n" + (ch.get("after") or "")
        if _NUMERIC_HINTS.search(blob):
            out.append({**ch, "numeric": True})
    return out


def numeric_impact_cards(law_name: str, cards: list[dict] | None = None) -> list[dict]:
    cards = cards if cards is not None else _load_all_cards()
    want = set(NUMERIC_LAW_CARDS.get(law_name) or [])
    if not want:
        return []
    return [
        {"card_id": c["id"], "domain": c.get("_domain"), "basis_hit": ["(numeric)"], "title": c.get("title")}
        for c in cards
        if c.get("id") in want
    ]


def diff_versions(law_name: str, before_id: str, after_id: str) -> dict:
    before = load_version(law_name, before_id)
    after = load_version(law_name, after_id)
    changes = diff_articles(before.get("articles") or [], after.get("articles") or [])
    changed_ids = [c["id"] for c in changes if c["kind"] in ("추가", "삭제", "변경", "형식 변경")]
    content_ids = [c["id"] for c in changes if c["kind"] in ("추가", "삭제", "변경")]
    cards = find_impacted_cards(content_ids)
    numeric = flag_numeric_changes([c for c in changes if c["kind"] == "변경"])
    if numeric or any("퍼센트" in ((c.get("before") or "") + (c.get("after") or "")) for c in changes):
        extra = numeric_impact_cards(law_name)
        seen = {c["card_id"] for c in cards}
        for c in extra:
            if c["card_id"] not in seen:
                cards.append(c)
                seen.add(c["card_id"])
    records = find_impacted_records(content_ids)
    after_meta = after.get("meta") or {}
    byeol_info = resolve_apply_rule(
        after.get("byeol") or [],
        announced=after_meta.get("announced"),
        effective=after_meta.get("effective"),
    )
    # 개정문에 있는 적용 문장도 후보로
    raw = after.get("raw") or {}
    rev = raw.get("개정문") or {}
    rev_text = ""
    if isinstance(rev, dict):
        from rag.lawwatch.parse import flatten_text

        rev_text = flatten_text(rev.get("개정문내용"))
    if rev_text:
        extra_lines = [ln.strip() for ln in rev_text.splitlines() if ln.strip()]
        byeol_info = resolve_apply_rule(
            after.get("byeol") or [],
            announced=after_meta.get("announced"),
            effective=after_meta.get("effective"),
            extra_quotes=extra_lines,
        )
    return {
        "law": law_name,
        "before_id": before_id,
        "after_id": after_id,
        "before_meta": before.get("meta"),
        "after_meta": after_meta,
        "changes": changes,
        "n_changes": len(changes),
        "impacted_cards": cards,
        "reindex_records": records,
        "numeric_changes": numeric,
        "byeol": byeol_info,
    }


def write_changes_report(diff_payload: dict, day: str | None = None) -> dict:
    LAWWATCH_OUT.mkdir(parents=True, exist_ok=True)
    day = day or datetime.now().strftime("%Y%m%d")
    out_json = LAWWATCH_OUT / f"{day}_changes.json"
    out_md = LAWWATCH_OUT / f"{day}_changes.md"
    # merge if exists
    existing = {}
    if out_json.exists():
        existing = json.loads(out_json.read_text(encoding="utf-8"))
    items = existing.get("items") or []
    items = [it for it in items if not (it.get("law") == diff_payload.get("law") and it.get("before_id") == diff_payload.get("before_id") and it.get("after_id") == diff_payload.get("after_id"))]
    items.append(diff_payload)
    payload = {"day": day, "items": items, "updated_at": datetime.now().isoformat(timespec="seconds")}
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 법령 변경 {day}", ""]
    for it in items:
        lines.append(f"## {it.get('law')} ({it.get('before_id')} → {it.get('after_id')})")
        lines.append(f"- 변경 수: {it.get('n_changes')}")
        byeol = it.get("byeol") or {}
        lines.append(f"- 적용 기준: {byeol.get('apply_rule')} ({byeol.get('status')})")
        if byeol.get("rule_quote"):
            lines.append(f"- 부칙: {byeol.get('rule_quote')}")
        lines.append("- 영향 카드: " + ", ".join(c["card_id"] for c in it.get("impacted_cards") or []) or "(없음)")
        for ch in it.get("changes") or []:
            lines.append(f"### {ch.get('kind')} `{ch.get('id')}`")
            if ch.get("before"):
                lines.append("**전**")
                lines.append("```")
                lines.append(ch["before"][:800])
                lines.append("```")
            if ch.get("after"):
                lines.append("**후**")
                lines.append("```")
                lines.append(ch["after"][:800])
                lines.append("```")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(out_json), "md": str(out_md), "payload": payload}
