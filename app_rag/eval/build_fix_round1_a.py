# -*- coding: utf-8 -*-
"""FIX_ROUND1-A: dev_test_split_v2 + clean twins. datasets 원본은 읽기만."""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
sys.path.insert(0, str(APP))

from rag.facts import extract_facts  # noqa: E402
from rag.verify import numeric_rules  # noqa: E402

SEED = 42
SPLIT_V1 = WORK / "datasets" / "splits" / "dev_test_split.json"
SPLIT_V2 = WORK / "datasets" / "splits" / "dev_test_split_v2.json"
OUT_DIR = APP / "out"

GOLD = {
    "LEASE": WORK / "datasets" / "property" / "v2_fixed" / "01_계약서.jsonl",
    "LOAN": WORK / "datasets" / "money" / "v3_fixed" / "01_위반계약서_60건.jsonl",
    "LAB": WORK / "datasets" / "work" / "v3_1" / "01_계약서.jsonl",
}
CLEAN_DIR = {
    "LEASE": WORK / "datasets" / "property" / "clean_twins",
    "LOAN": WORK / "datasets" / "money" / "clean_twins",
    "LAB": WORK / "datasets" / "work" / "clean_twins",
}
PREFIX = {"LEASE": "LEASE-C", "LOAN": "LOAN-C", "LAB": "WORK-C"}
TARGET_DEV = {"LEASE": 15, "LOAN": 18, "LAB": 12}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def by_doc(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["doc_id"]].append(r)
    for did in out:
        out[did] = sorted(
            out[did],
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
    return dict(out)


def toxic_n(segs: list[dict]) -> int:
    return sum(1 for s in segs if s.get("label") == "toxic")


def bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n <= 2:
        return "1-2"
    if n <= 5:
        return "3-5"
    return "6+"


def ideal_bucket_counts(n_docs: int, global_bc: Counter) -> dict[str, int]:
    """전역 비율에 맞춰 n_docs개 버킷 목표(반올림, 합=n_docs)."""
    keys = ["0", "1-2", "3-5", "6+"]
    total = sum(global_bc[k] for k in keys) or 1
    raw = {k: global_bc[k] / total * n_docs for k in keys}
    floors = {k: int(raw[k]) for k in keys}
    rem = n_docs - sum(floors.values())
    frac = sorted(((raw[k] - floors[k], k) for k in keys), reverse=True)
    for i in range(rem):
        floors[frac[i % len(keys)][1]] += 1
    # 6+가 전역에 1개뿐이면 목표는 최대 1
    if global_bc["6+"] == 0:
        floors["6+"] = 0
    elif floors["6+"] > global_bc["6+"]:
        floors["6+"] = global_bc["6+"]
    # 합 보정
    while sum(floors.values()) > n_docs:
        for k in ("0", "1-2", "3-5", "6+"):
            if floors[k] > 0 and sum(floors.values()) > n_docs:
                floors[k] -= 1
    while sum(floors.values()) < n_docs:
        for k in ("1-2", "3-5", "0", "6+"):
            if sum(floors.values()) < n_docs:
                floors[k] += 1
    return floors


def expand_dev(domain: str, docs: dict[str, list[dict]], split: dict) -> tuple[list[str], list[str], list[str]]:
    """현재 dev 유지, test에서 목표 수만큼 버킷 맞춰 이동. returns (dev, test, moved)."""
    rng = random.Random(SEED + hash(domain) % 10007)
    cur_dev = list(split[domain]["dev"])
    cur_test = list(split[domain]["test"])
    target = TARGET_DEV[domain]
    need = target - len(cur_dev)
    assert need >= 0

    global_bc = Counter(bucket(toxic_n(docs[d])) for d in docs)
    ideal = ideal_bucket_counts(target, global_bc)
    cur_bc = Counter(bucket(toxic_n(docs[d])) for d in cur_dev)
    deficit = {k: max(0, ideal.get(k, 0) - cur_bc.get(k, 0)) for k in ("0", "1-2", "3-5", "6+")}
    # deficit 합이 need와 다르면 need에 맞게 조정
    while sum(deficit.values()) > need:
        for k in ("0", "6+", "1-2", "3-5"):
            if deficit[k] > 0 and sum(deficit.values()) > need:
                deficit[k] -= 1
    while sum(deficit.values()) < need:
        for k in ("1-2", "3-5", "0", "6+"):
            if sum(deficit.values()) < need:
                deficit[k] += 1

    test_by_b: dict[str, list[str]] = defaultdict(list)
    for d in cur_test:
        test_by_b[bucket(toxic_n(docs[d]))].append(d)
    for k in test_by_b:
        rng.shuffle(test_by_b[k])

    moved = []
    for k, n in deficit.items():
        take = test_by_b[k][:n]
        if len(take) < n:
            # 모자라면 다른 버킷에서 보충
            short = n - len(take)
            pool = []
            for ok in ("1-2", "3-5", "0", "6+"):
                if ok == k:
                    continue
                pool.extend(test_by_b[ok][deficit.get(ok, 0) :])  # already reserved front
            # simpler: remaining test not yet moved
            rem = [d for d in cur_test if d not in moved and d not in take]
            rng.shuffle(rem)
            take = take + rem[:short]
        moved.extend(take[:n])

    # 정확히 need개
    moved = moved[:need]
    # 부족하면 남은 test에서
    if len(moved) < need:
        rem = [d for d in cur_test if d not in moved]
        rng.shuffle(rem)
        moved.extend(rem[: need - len(moved)])

    new_dev = sorted(set(cur_dev) | set(moved))
    new_test = sorted(set(cur_test) - set(moved))
    assert len(new_dev) == target, (domain, len(new_dev), target, moved)
    assert len(new_dev) + len(new_test) == len(cur_dev) + len(cur_test)
    return new_dev, new_test, sorted(moved)


def safe_pool(docs: dict[str, list[dict]], split_ids: set[str], exclude_doc: str) -> dict[str, list[dict]]:
    """std_item -> safe segments from other docs in same split."""
    pool: dict[str, list[dict]] = defaultdict(list)
    for did in split_ids:
        if did == exclude_doc:
            continue
        for s in docs[did]:
            if s.get("label") == "safe" and s.get("std_item"):
                pool[s["std_item"]].append(s)
    return pool


def lab_rules_fire(segs: list[dict]) -> list[str]:
    full = "\n".join(s.get("text") or "" for s in segs)
    facts = extract_facts(full)
    facts["domain"] = "LAB"
    reasons = []
    for s in segs:
        if s.get("label") == "meta":
            continue
        rule = numeric_rules(s.get("text") or "", facts)
        if rule.get("fired"):
            reasons.append(f"{s.get('segment_id')}:{','.join(rule['fired'])}:{rule.get('why')}")
    # 시급 vs 최저임금도 facts 수준에서
    wage = facts.get("hourly_wage")
    year = facts.get("apply_year")
    if wage is not None:
        from rag.dates import min_wage_verdict

        mv = min_wage_verdict(facts)
        if mv and mv.get("verdict") == "위반":
            reasons.append(f"doc_min_wage:{mv.get('why')}")
    return reasons


def make_twin(
    src_id: str,
    docs: dict[str, list[dict]],
    split_ids: set[str],
    new_id: str,
    split_name: str,
    domain: str,
) -> tuple[list[dict] | None, dict]:
    segs = deepcopy(docs[src_id])
    pool = safe_pool(docs, split_ids, src_id)
    skipped = 0
    replaced = 0
    out = []
    for i, s in enumerate(segs):
        lab = s.get("label") or ""
        if lab in ("toxic", "check"):
            std = s.get("std_item") or ""
            cands = pool.get(std) or []
            if not cands:
                skipped += 1
                continue  # drop segment
            donor = cands[(hash(src_id + std + str(i)) & 0xFFFF) % len(cands)]
            news = deepcopy(donor)
            news["doc_id"] = new_id
            news["segment_id"] = f"{new_id}-S{len(out):02d}"
            news["order"] = len(out)
            news["label"] = "safe"
            news["toxic_code"] = []
            news["twin_of"] = src_id
            news["split"] = split_name
            news["replaced_from"] = donor.get("segment_id")
            news["orig_std_item"] = std
            out.append(news)
            replaced += 1
        else:
            news = deepcopy(s)
            news["doc_id"] = new_id
            news["segment_id"] = f"{new_id}-S{len(out):02d}"
            news["order"] = len(out)
            if lab != "meta":
                news["label"] = "safe"
                news["toxic_code"] = []
            news["twin_of"] = src_id
            news["split"] = split_name
            out.append(news)

    meta = {
        "src": src_id,
        "new_id": new_id,
        "split": split_name,
        "replaced": replaced,
        "skipped_no_safe": skipped,
        "n_segs": len(out),
    }
    if domain == "LAB":
        reasons = lab_rules_fire(out)
        if reasons:
            meta["rejected"] = reasons
            return None, meta
    # 최종 라벨 확인
    for s in out:
        if s.get("label") not in ("safe", "meta"):
            s["label"] = "safe"
            s["toxic_code"] = []
    return out, meta


def build_clean_twins(domain: str, docs: dict[str, list[dict]], split_v2: dict) -> tuple[list[dict], dict]:
    rng = random.Random(SEED + 17 + hash(domain) % 10007)
    all_rows: list[dict] = []
    report = {"dev": [], "test": [], "rejected": []}
    for part, start_idx in (("dev", 1), ("test", 6)):
        ids = list(split_v2[domain][part])
        toxic_srcs = [d for d in ids if toxic_n(docs[d]) > 0]
        rng.shuffle(toxic_srcs)
        made = 0
        attempts = 0
        used_src = set()
        while made < 5 and attempts < 80:
            attempts += 1
            if not toxic_srcs:
                break
            src = toxic_srcs[attempts % len(toxic_srcs)]
            if src in used_src and attempts < len(toxic_srcs):
                continue
            used_src.add(src)
            new_id = f"{PREFIX[domain]}{made + start_idx:03d}"
            twin, meta = make_twin(src, docs, set(ids), new_id, part, domain)
            if twin is None:
                report["rejected"].append(meta)
                continue
            all_rows.extend(twin)
            report[part].append(meta)
            made += 1
        if made < 5:
            report["shortfall"] = report.get("shortfall", {})
            report["shortfall"][part] = 5 - made
    return all_rows, report


def summarize(domain: str, docs: dict[str, list[dict]], split: dict, clean_ids: dict) -> dict:
    out = {}
    for part in ("dev", "test"):
        ids = list(split[domain][part]) + list(clean_ids.get(part) or [])
        tox_docs = sum(1 for d in ids if d in docs and toxic_n(docs[d]) > 0)
        # clean twins always clean
        clean_docs = 0
        labels = Counter()
        for d in ids:
            if d.startswith(PREFIX[domain].rstrip("0123456789")[:]) or d in (clean_ids.get(part) or []):
                # will count from clean file separately
                pass
            if d not in docs:
                clean_docs += 1  # twin placeholder
                continue
            nt = toxic_n(docs[d])
            if nt == 0:
                clean_docs += 1
            for s in docs[d]:
                labels[s.get("label") or ""] += 1
        out[part] = {
            "n_docs": len(ids),
            "toxic_docs": tox_docs,
            "clean_docs": clean_docs,
            "labels": dict(labels),
        }
    return out


def main() -> None:
    split_v1 = json.loads(SPLIT_V1.read_text(encoding="utf-8"))
    docs_all = {dom: by_doc(load_jsonl(p)) for dom, p in GOLD.items()}

    split_v2 = {
        "seed": SEED,
        "parent": "dev_test_split.json",
        "rule": "v1 dev 전부 유지 + test→dev 이동으로 약 30%(LEASE15/LOAN18/LAB12). clean twin 포함.",
        "files": dict(split_v1.get("files") or {}),
        "moved_from_test": {},
        "LEASE": {},
        "LOAN": {},
        "LAB": {},
        "clean_twins": {"LEASE": {"dev": [], "test": []}, "LOAN": {"dev": [], "test": []}, "LAB": {"dev": [], "test": []}},
    }

    moved_report = {}
    for dom in ("LEASE", "LOAN", "LAB"):
        new_dev, new_test, moved = expand_dev(dom, docs_all[dom], split_v1)
        split_v2[dom] = {"dev": new_dev, "test": new_test}
        split_v2["moved_from_test"][dom] = moved
        moved_report[dom] = moved
        print(dom, "dev", len(new_dev), "test", len(new_test), "moved", moved)

    twin_meta = {}
    for dom in ("LEASE", "LOAN", "LAB"):
        rows, rep = build_clean_twins(dom, docs_all[dom], split_v2)
        twin_meta[dom] = rep
        dest = CLEAN_DIR[dom] / "01_계약서.jsonl"
        write_jsonl(dest, rows)
        print(dom, "twins", dest, "rows", len(rows), "rej", len(rep.get("rejected") or []))
        for part in ("dev", "test"):
            ids = [m["new_id"] for m in rep.get(part) or []]
            split_v2["clean_twins"][dom][part] = ids
            # also append to domain split lists for loaders that union clean
            split_v2[dom][part] = list(split_v2[dom][part]) + ids

    SPLIT_V2.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_V2.write_text(json.dumps(split_v2, ensure_ascii=False, indent=2), encoding="utf-8")

    # A-3 tables — reload twins into docs maps for counting
    tables = {}
    for dom in ("LEASE", "LOAN", "LAB"):
        base = docs_all[dom]
        twin_rows = load_jsonl(CLEAN_DIR[dom] / "01_계약서.jsonl")
        twin_docs = by_doc(twin_rows)
        merged = {**base, **twin_docs}
        part_stats = {}
        for part in ("dev", "test"):
            ids = split_v2[dom][part]
            tox_d = sum(1 for d in ids if toxic_n(merged[d]) > 0)
            clean_d = sum(1 for d in ids if toxic_n(merged[d]) == 0)
            labels = Counter()
            for d in ids:
                for s in merged[d]:
                    labels[s.get("label") or ""] += 1
            part_stats[part] = {
                "n_docs": len(ids),
                "toxic_docs": tox_d,
                "clean_docs": clean_d,
                "toxic_segs": labels.get("toxic", 0),
                "check_segs": labels.get("check", 0),
                "safe_segs": labels.get("safe", 0),
                "meta_segs": labels.get("meta", 0),
            }
        tables[dom] = {
            "parts": part_stats,
            "moved": moved_report[dom],
            "twins": twin_meta[dom],
            "lab_rejected": twin_meta[dom].get("rejected") if dom == "LAB" else twin_meta[dom].get("rejected"),
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "split_v2": str(SPLIT_V2),
        "moved_from_test": moved_report,
        "tables": tables,
        "target_dev": TARGET_DEV,
    }
    (OUT_DIR / "fix_round1_a.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", SPLIT_V2)
    print("WROTE", OUT_DIR / "fix_round1_a.json")


if __name__ == "__main__":
    main()
