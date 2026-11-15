# -*- coding: utf-8 -*-
"""dev toxic·check 조각 recall@3. A.X 없이 검색만. sparse 없음."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from rag.corpus import load_corpus  # noqa: E402
from rag.paths import GOLD, OUT, RETRIEVE_FLOOR, RETRIEVE_K  # noqa: E402
from rag.retrieve import HybridIndex  # noqa: E402
from rag.split import strip_placeholders  # noqa: E402
from splitutil import load_split_ids  # noqa: E402

ART_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _art(num: str, of: str | None) -> str:
    return f"{num}의{of}" if of else num


def keys_from_gold(raw: str) -> list[tuple[str, str]]:
    text = raw or ""
    matches = list(ART_RE.finditer(text))
    if not matches:
        return []
    name = compact(text[: matches[0].start()])
    if not name:
        return []
    return [(name, _art(m.group(1), m.group(2))) for m in matches]


def canon_from_id(cid: str) -> tuple[str, str] | None:
    raw = cid or ""
    if raw.startswith("law:"):
        rest, kind = raw[4:], "law"
    elif raw.startswith("decree:"):
        rest, kind = raw[7:], "decree"
    else:
        return None
    parts = rest.split(":")
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and parts[-1].isdigit():
        art = parts[-2]
        name = ":".join(parts[:-2])
    else:
        art = parts[-1]
        name = ":".join(parts[:-1])
    if kind == "decree" and "시행령" not in name:
        name = f"{name} 시행령"
    return compact(name), art


def id_display(cid: str) -> str:
    parsed = canon_from_id(cid)
    if not parsed:
        return cid
    name, art = parsed
    if "의" in art:
        base, of = art.split("의", 1)
        shown = f"제{base}조의{of}"
    else:
        shown = f"제{art}조"
    return f"{name} {shown}"


def gold_in_corpus(gold_raw: str, corpus_keys: set[tuple[str, str]], corpus_ids: list[str]) -> bool:
    keys = keys_from_gold(gold_raw)
    if keys:
        return any(k in corpus_keys for k in keys)
    blob = compact(gold_raw)
    if not blob:
        return False
    return any(blob in compact(cid) or compact(cid) in blob for cid in corpus_ids)


def hit_matches_gold(hit_id: str, gold_keys: set[tuple[str, str]], gold_raws: list[str]) -> bool:
    key = canon_from_id(hit_id)
    if key and key in gold_keys:
        return True
    hid = compact(hit_id)
    return any(compact(raw) and compact(raw) in hid for raw in gold_raws)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    recs, skipped = load_corpus()
    print("CORPUS_N", len(recs), "skipped", json.dumps(skipped, ensure_ascii=False))
    corpus_keys = set()
    corpus_ids = [r["id"] for r in recs]
    for rec in recs:
        key = canon_from_id(rec["id"])
        if key:
            corpus_keys.add(key)
    print("CORPUS_KEYS", len(corpus_keys))

    t0 = time.perf_counter()
    index = HybridIndex(recs)
    print("INDEX_MS", round((time.perf_counter() - t0) * 1000, 1))
    print("EMBED_OK", index.embed.ok, index.embed.error)
    print("FLOOR", RETRIEVE_FLOOR, "K", RETRIEVE_K)

    by_domain = {}
    all_wrong = []
    missing_gold_list = []
    for domain, spec in GOLD.items():
        keep = load_split_ids("dev", domain)
        contracts = load_jsonl(spec["contract"])
        law_rows = {r["segment_id"]: r for r in load_jsonl(spec["law"])}
        segs = [
            r
            for r in contracts
            if r.get("doc_id") in keep and r.get("label") in ("toxic", "check")
        ]
        hits_n = 0
        floor_zero = 0
        gold_missing_segs = 0
        rows = []
        for seg in segs:
            sid = seg["segment_id"]
            law = law_rows.get(sid) or {}
            gold_raw = list(law.get("legal_provisions") or seg.get("evidence_hint") or [])
            gold_keys = {k for raw in gold_raw for k in keys_from_gold(raw)}
            in_corpus = [raw for raw in gold_raw if gold_in_corpus(raw, corpus_keys, corpus_ids)]
            missing = [raw for raw in gold_raw if raw not in in_corpus]
            all_gold_missing = bool(gold_raw) and not in_corpus
            if all_gold_missing:
                gold_missing_segs += 1
                missing_gold_list.append({"domain": domain, "segment_id": sid, "gold": gold_raw})
            query = strip_placeholders(seg.get("text") or "")
            retrieved = index.search(query, domain=domain, title="")
            hit_ids = [h["id"] for h in retrieved.get("hits") or []]
            if not hit_ids:
                floor_zero += 1
            ok = any(hit_matches_gold(hid, gold_keys, gold_raw) for hid in hit_ids) if (gold_keys or gold_raw) else False
            if ok:
                hits_n += 1
            row = {
                "domain": domain,
                "doc_id": seg.get("doc_id"),
                "segment_id": sid,
                "label": seg.get("label"),
                "gold": gold_raw,
                "gold_keys": [f"{a} 제{b}조" for a, b in sorted(gold_keys)],
                "hit_ids": hit_ids,
                "hit_display": [id_display(i) for i in hit_ids],
                "ok": ok,
                "floor_zero": not hit_ids,
                "gold_missing_from_corpus": all_gold_missing,
                "gold_not_in_corpus": missing,
                "filter_mode": retrieved.get("filter_mode"),
                "text": query[:180],
            }
            rows.append(row)
            if not ok:
                all_wrong.append(row)
            print(
                "SEG",
                json.dumps(
                    {
                        "domain": domain,
                        "segment_id": sid,
                        "ok": ok,
                        "gold": gold_raw,
                        "hits": hit_ids,
                        "floor_zero": not hit_ids,
                        "gold_missing": all_gold_missing,
                    },
                    ensure_ascii=False,
                ),
            )
        n = len(segs)
        by_domain[domain] = {
            "n_dev_docs": len(keep),
            "n_toxic_check": n,
            "hit": hits_n,
            "recall_at_3": (hits_n / n) if n else None,
            "floor_zero": floor_zero,
            "gold_missing_from_corpus_segs": gold_missing_segs,
            "rows": rows,
        }
        print(
            "DOMAIN",
            json.dumps(
                {
                    "domain": domain,
                    "n": n,
                    "hit": hits_n,
                    "recall_at_3": by_domain[domain]["recall_at_3"],
                    "floor_zero": floor_zero,
                    "gold_missing_from_corpus_segs": gold_missing_segs,
                },
                ensure_ascii=False,
            ),
        )

    unique_missing = []
    seen = set()
    for spec in by_domain.values():
        for row in spec["rows"]:
            for raw in row.get("gold_not_in_corpus") or []:
                if raw not in seen:
                    seen.add(raw)
                    unique_missing.append(raw)

    wrong_examples = all_wrong[:10]
    payload = {
        "k": RETRIEVE_K,
        "floor": RETRIEVE_FLOOR,
        "corpus_n": len(recs),
        "embed_ok": index.embed.ok,
        "by_domain": {d: {k: v for k, v in spec.items() if k != "rows"} | {"n_rows": len(spec["rows"])} for d, spec in by_domain.items()},
        "unique_gold_not_in_corpus": unique_missing,
        "gold_missing_seg_examples": missing_gold_list[:20],
        "wrong_examples": [
            {
                "domain": r["domain"],
                "segment_id": r["segment_id"],
                "gold": r["gold"],
                "hit_ids": r["hit_ids"],
                "hit_display": r["hit_display"],
                "gold_not_in_corpus": r["gold_not_in_corpus"],
                "text": r["text"],
            }
            for r in wrong_examples
        ],
        "detail": by_domain,
    }
    dest = OUT / "recall_dev.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", dest)
    print("UNIQUE_MISSING", json.dumps(unique_missing, ensure_ascii=False))
    print("WRONG_N", len(all_wrong), "SHOW", len(wrong_examples))


if __name__ == "__main__":
    main()
