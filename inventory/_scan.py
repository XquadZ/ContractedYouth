# -*- coding: utf-8 -*-
"""Read-only inventory scanner. Writes only under WORK/inventory/."""
from __future__ import annotations

import csv
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
USB = Path(r"D:\ai")
OUT = WORK / "inventory"
KST = timezone(timedelta(hours=9))
OUT.mkdir(parents=True, exist_ok=True)


def log(m):
    print(f"[{datetime.now(KST).isoformat(timespec='seconds')}] {m}", flush=True)


def write_json(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clip(s, n=150):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:n]


def nonempty(x):
    if x is None:
        return False
    if isinstance(x, str):
        return bool(x.strip())
    if isinstance(x, (list, tuple, dict)):
        if not x:
            return False
        if isinstance(x, dict):
            return any(nonempty(v) for v in x.values())
        return any(nonempty(v) for v in x)
    return True


def file_kind_bytes(raw: bytes):
    head = raw[:400].lower()
    if not raw:
        return "empty"
    if b"<html" in head or "권한" in raw[:800].decode("utf-8", "ignore") or b"<!doctype html" in head:
        return "html"
    try:
        json.loads(raw)
        return "json"
    except Exception:
        return "other"


# ---------- A 약관 / 판결문 from zip (no extract) ----------
def scan_019():
    root = WORK / "019.법률, 규정 (판결서, 약관 등) 텍스트 분석 데이터"
    zips = sorted(root.rglob("*.zip"))
    zip_info = []
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            json_n = sum(1 for n in names if n.lower().endswith(".json"))
            xml_n = sum(1 for n in names if n.lower().endswith(".xml"))
            zip_info.append(
                {
                    "zip": str(zp.relative_to(WORK)),
                    "bytes": zp.stat().st_size,
                    "members": len(names),
                    "json": json_n,
                    "xml": xml_n,
                }
            )
    # 약관 labeled JSON TL+VL
    dv = Counter()
    field = Counter()
    field_adv = Counter()
    field_unf = Counter()
    n_docs = 0
    n_clause_arts = 0
    n_unf = 0
    n_unf_law = 0
    n_unf_ill = 0
    broken = 0
    law_names = Counter()
    n_unf_non_yakgwan = 0
    ill_samples = []
    samples_adv = []
    samples_unf = []
    yakgwan_re = re.compile(r"약관")
    law_token_re = re.compile(r"([가-힣A-Za-z0-9]+법(?:\s*시행령)?(?:\s*시행규칙)?)")

    def consume_terms(zp):
        nonlocal n_docs, n_clause_arts, n_unf, n_unf_law, n_unf_ill, broken, n_unf_non_yakgwan
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    obj = json.loads(z.read(name))
                except Exception:
                    broken += 1
                    continue
                n_docs += 1
                d = str(obj.get("dvAntageous", ""))
                dv[d] += 1
                cf = str(obj.get("clauseField", ""))
                field[cf] += 1
                arts = obj.get("clauseArticle") or []
                n_clause_arts += len(arts) if isinstance(arts, list) else 1
                if d == "1":
                    field_adv[cf] += 1
                    if len(samples_adv) < 2:
                        samples_adv.append(
                            {
                                "file": Path(name).name,
                                "fields": sorted(obj.keys()),
                                "dvAntageous": d,
                                "clauseField": cf,
                                "clauseArticle": clip((arts[0] if arts else ""), 150),
                            }
                        )
                elif d == "2":
                    n_unf += 1
                    field_unf[cf] += 1
                    if nonempty(obj.get("relateLaword")):
                        n_unf_law += 1
                    if nonempty(obj.get("illdcssBasiss")):
                        n_unf_ill += 1
                    laws = obj.get("relateLaword") or []
                    texts = laws if isinstance(laws, list) else [laws]
                    joined = " ".join(str(t) for t in texts)
                    if joined.strip() and not yakgwan_re.search(joined):
                        n_unf_non_yakgwan += 1
                    elif joined.strip() and yakgwan_re.search(joined):
                        # still count other statutes if mixed
                        pass
                    found = law_token_re.findall(joined)
                    if not found and joined.strip():
                        found = [clip(joined, 40)]
                    for t in found:
                        law_names[t.strip()] += 1
                    if joined.strip() and not any("약관" in t for t in found):
                        n_unf_non_yakgwan += 0  # counted via found names below
                    ill = obj.get("illdcssBasiss") or []
                    if len(ill_samples) < 2 and nonempty(ill):
                        ill_samples.append(clip(" / ".join(str(x) for x in (ill if isinstance(ill, list) else [ill])), 150))
                    if len(samples_unf) < 2:
                        samples_unf.append(
                            {
                                "file": Path(name).name,
                                "fields": sorted(obj.keys()),
                                "dvAntageous": d,
                                "clauseField": cf,
                                "relateLaword": clip(joined, 150),
                            }
                        )

    for zp in zips:
        if "약관" in zp.name and zp.name.startswith("TL") or (zp.name.startswith("VL") and "약관" in zp.name):
            if "약관" in zp.name and zp.name[0] in "TV":
                log(f"  consume {zp.name}")
                consume_terms(zp)

    # 판결문: count by folder from namelist + peek labels
    case_kind = Counter()
    trail = Counter()
    case_field = Counter()
    n_jud = 0
    jud_broken = 0
    jud_keys = None
    jud_samples = []
    year_bins = Counter()
    for zp in zips:
        if "판결문" not in zp.name:
            continue
        if not (zp.name.startswith("TL") or zp.name.startswith("VL")):
            continue
        log(f"  consume {zp.name}")
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                n_jud += 1
                if "/01.민사/" in name.replace("\\", "/") or "01.민사" in name:
                    case_kind["민사"] += 1
                elif "/02.형사/" in name.replace("\\", "/") or "02.형사" in name:
                    case_kind["형사"] += 1
                elif "/03.행정/" in name.replace("\\", "/") or "03.행정" in name:
                    case_kind["행정"] += 1
                else:
                    case_kind["기타경로"] += 1
                if n_jud <= 50 or n_jud % 200 == 0:
                    try:
                        obj = json.loads(z.read(name))
                    except Exception:
                        jud_broken += 1
                        continue
                    if jud_keys is None:
                        jud_keys = {
                            "top": list(obj.keys()),
                            "info": list((obj.get("info") or {}).keys()),
                        }
                    info = obj.get("info") or {}
                    trail[str(info.get("trailField", ""))] += 1
                    case_field[str(info.get("caseField", ""))] += 1
                    if len(jud_samples) < 2:
                        jud_samples.append(
                            {
                                "file": Path(name).name,
                                "caseNm": clip(info.get("caseNm"), 80),
                                "courtNm": info.get("courtNm"),
                                "trailField": info.get("trailField"),
                                "caseField": info.get("caseField"),
                                "detailField": info.get("detailField"),
                            }
                        )
                m = re.search(r"(19|20)\d{2}", name)
                if m:
                    y = int(m.group(0))
                    year_bins[f"{(y//10)*10}s"] += 1

    # non-약관법 share among unfavorable that have relateLaword
    n_unf_has_non_yakgwan = 0
    # recompute from law_names is wrong; do second pass only for rate among filled
    # We'll approximate: count docs whose relateLaword mentions a 법 other than 약관규제법/약관법
    n_unf_law_other = 0
    n_unf_law_only_yakgwan = 0
    for zp in zips:
        if "약관" not in zp.name or zp.name[0] not in "TV":
            continue
        if not (zp.name.startswith("TL") or zp.name.startswith("VL")):
            continue
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    obj = json.loads(z.read(name))
                except Exception:
                    continue
                if str(obj.get("dvAntageous")) != "2":
                    continue
                laws = obj.get("relateLaword") or []
                texts = " ".join(str(t) for t in (laws if isinstance(laws, list) else [laws]))
                if not texts.strip():
                    continue
                toks = law_token_re.findall(texts)
                other = [t for t in toks if "약관" not in t]
                if other:
                    n_unf_law_other += 1
                else:
                    n_unf_law_only_yakgwan += 1

    return {
        "zip_info": zip_info,
        "terms": {
            "n_docs_labeled_json": n_docs,
            "n_clauseArticle_items": n_clause_arts,
            "broken_json": broken,
            "dvAntageous": dict(dv),
            "clauseField": dict(field.most_common()),
            "clauseField_adv": dict(field_adv.most_common()),
            "clauseField_unf": dict(field_unf.most_common()),
            "n_unfavorable": n_unf,
            "n_unf_relateLaword_filled": n_unf_law,
            "n_unf_illdcssBasiss_filled": n_unf_ill,
            "pct_unf_law": (100.0 * n_unf_law / n_unf) if n_unf else None,
            "pct_unf_ill": (100.0 * n_unf_ill / n_unf) if n_unf else None,
            "n_unf_law_other_statute": n_unf_law_other,
            "n_unf_law_only_yakgwanish": n_unf_law_only_yakgwan,
            "pct_unf_law_other_among_filled": (
                100.0 * n_unf_law_other / n_unf_law if n_unf_law else None
            ),
            "top10_laws": law_names.most_common(10),
            "ill_samples": ill_samples,
            "samples_adv": samples_adv,
            "samples_unf": samples_unf,
        },
        "judgments": {
            "n_labeled_json_tl_vl": n_jud,
            "broken_in_sampled_reads": jud_broken,
            "case_kind_from_path": dict(case_kind),
            "trailField_sampled": dict(trail),
            "caseField_sampled": dict(case_field),
            "note_trail_caseField": "trailField/caseField는 일부만 열어 센 값(전수는 경로 민사/형사/행정). 전수 필드는 확인 필요가 아님: 경로는 전수.",
            "keys": jud_keys,
            "samples": jud_samples,
        },
        "models_in_dataset_folder": "zip 8개만 존재, 모델/학습코드/README 없음",
    }


def scan_forms():
    root = WORK / "data_contract" / "aihub_forms"
    files = [p for p in root.rglob("*") if p.is_file()]
    jsons = [p for p in files if p.suffix.lower() == ".json"]
    exts = Counter(p.suffix.lower() or "(none)" for p in files)
    # document-level: each json is one document?
    types = Counter()
    splits = Counter()
    n_ok = 0
    broken = 0
    empty = 0
    html = 0
    label_ctr = Counter()
    n_label_types = 0
    section_keys = Counter()
    n_docs = 0
    clause_by_type = Counter()
    samples = {}
    placeholder_stats = {}
    target_types = ["아르바이트계약서", "근로(고용)계약서", "주거용부동산임대계약서"]
    target_docs = defaultdict(list)
    dataset_name = None
    keys_top = None

    ph_re = re.compile(r"\(@[^)]+\)|○+|XXXX+|____+")
    money_re = re.compile(r"\d{1,3}(?:,\d{3})+\s*원|\d+\s*원")
    wage_re = re.compile(r"시급|월급|임금")
    date_re = re.compile(r"\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}")

    for p in jsons:
        raw = p.read_bytes()
        if not raw:
            empty += 1
            continue
        k = file_kind_bytes(raw)
        if k == "html":
            html += 1
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            broken += 1
            continue
        n_ok += 1
        n_docs += 1
        if keys_top is None and isinstance(obj, dict):
            keys_top = list(obj.keys())
        data = obj.get("data") if isinstance(obj, dict) and "data" in obj else obj
        # typical AI hub contract form schema
        meta = {}
        if isinstance(obj, dict):
            dataset_name = dataset_name or obj.get("dataset") or obj.get("dataSetInfo") or obj.get("info")
            for cand in ("문서종류", "소분류", "doc_type", "type", "계약서종류"):
                if cand in obj:
                    meta["type"] = obj[cand]
        # nested
        info = obj.get("info") if isinstance(obj, dict) else None
        if isinstance(info, dict):
            dataset_name = dataset_name or info.get("dataSetName") or info.get("datasetName")
        # walk common fields
        doc_type = None
        for path_part in p.parts:
            pass
        # from filename parent folder already has 대분류
        # look inside
        def find_type(o, depth=0):
            if depth > 3 or not isinstance(o, dict):
                return None
            for k, v in o.items():
                if k in ("소분류", "문서종류", "docNm", "formName", "계약서명", "title") and isinstance(v, str) and v.strip():
                    if k in ("소분류", "문서종류", "formName"):
                        return v
                if isinstance(v, dict):
                    t = find_type(v, depth + 1)
                    if t:
                        return t
            return None

        doc_type = find_type(obj) or "미상"
        types[doc_type] += 1
        parent = p.parent.name
        if parent.startswith(("TL_", "TS_", "VL_", "VS_")):
            splits[parent[:2]] += 1
        # labels
        labels = []

        def harvest_labels(o, depth=0):
            if depth > 5:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    section_keys[k] += 1
                    if k in ("content_labels", "contentLabels", "label", "labels"):
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, str):
                                    labels.append(item)
                                elif isinstance(item, dict):
                                    for kk in ("label", "name", "tag", "type"):
                                        if kk in item and isinstance(item[kk], str):
                                            labels.append(item[kk])
                    harvest_labels(v, depth + 1)
            elif isinstance(o, list):
                for it in o[:500]:
                    harvest_labels(it, depth + 1)

        harvest_labels(obj)
        for lb in labels:
            label_ctr[lb] += 1
        # clauses
        n_cl = 0

        def count_clauses(o, depth=0):
            nonlocal n_cl
            if depth > 6:
                return
            if isinstance(o, dict):
                if any(k in o for k in ("clause", "article", "조항", "content")) and (
                    "text" in o or "content" in o or "clause" in o
                ):
                    n_cl += 1
                for v in o.values():
                    count_clauses(v, depth + 1)
            elif isinstance(o, list):
                for it in o:
                    count_clauses(it, depth + 1)

        count_clauses(obj)
        clause_by_type[doc_type] += max(n_cl, 1) if False else n_cl
        if doc_type in target_types and len(target_docs[doc_type]) < 25:
            # flatten text
            texts = []

            def grab_text(o, depth=0):
                if depth > 6:
                    return
                if isinstance(o, str) and len(o) > 2:
                    texts.append(o)
                elif isinstance(o, dict):
                    for v in o.values():
                        grab_text(v, depth + 1)
                elif isinstance(o, list):
                    for it in o:
                        grab_text(it, depth + 1)

            grab_text(obj)
            blob = " ".join(texts)
            target_docs[doc_type].append(
                {
                    "file": str(p.relative_to(root)),
                    "n_chars": len(blob),
                    "n_ph": len(ph_re.findall(blob)),
                    "n_money": len(money_re.findall(blob)),
                    "has_wage_word": bool(wage_re.search(blob)),
                    "n_date": len(date_re.findall(blob)),
                    "n_clauses_est": n_cl,
                    "sample": clip(blob, 150),
                }
            )
        if doc_type not in samples and len(samples) < 6:
            samples[doc_type] = {
                "file": str(p.relative_to(root)),
                "top_keys": list(obj.keys()) if isinstance(obj, dict) else type(obj).__name__,
                "n_labels": len(labels),
                "sample": clip(json.dumps(obj, ensure_ascii=False)[:400], 150),
            }

    for t, docs in target_docs.items():
        take = docs[:20]
        placeholder_stats[t] = {
            "n_docs_sampled": len(take),
            "sum_ph": sum(d["n_ph"] for d in take),
            "docs_with_ph": sum(1 for d in take if d["n_ph"] > 0),
            "docs_with_money": sum(1 for d in take if d["n_money"] > 0),
            "docs_with_date": sum(1 for d in take if d["n_date"] > 0),
            "docs_with_wage_word": sum(1 for d in take if d["has_wage_word"]),
            "mean_ph": (sum(d["n_ph"] for d in take) / len(take)) if take else None,
            "clause_sum_sampled": sum(d["n_clauses_est"] for d in take),
        }

    # clause counts for ALL docs of 3 types
    clause_all = Counter()
    n_type_all = Counter()
    for p in jsons:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        def find_type(o, depth=0):
            if depth > 3 or not isinstance(o, dict):
                return None
            for k, v in o.items():
                if k in ("소분류", "문서종류", "formName") and isinstance(v, str) and v.strip():
                    return v
                if isinstance(v, dict):
                    t = find_type(v, depth + 1)
                    if t:
                        return t
            return None

        dt = find_type(obj)
        if dt not in target_types:
            continue
        n_type_all[dt] += 1
        n_cl = 0

        def count_clauses(o, depth=0):
            nonlocal n_cl
            if depth > 6:
                return
            if isinstance(o, dict):
                ks = set(o.keys())
                if ks & {"text", "content", "clause", "article"} and len(ks) <= 12:
                    if any(isinstance(o.get(k), str) and len(o.get(k) or "") > 5 for k in ("text", "content", "clause")):
                        n_cl += 1
                for v in o.values():
                    count_clauses(v, depth + 1)
            elif isinstance(o, list):
                for it in o:
                    count_clauses(it, depth + 1)

        count_clauses(obj)
        clause_all[dt] += n_cl

    return {
        "n_files": len(files),
        "exts": dict(exts),
        "n_json": len(jsons),
        "n_ok": n_ok,
        "broken": broken,
        "empty": empty,
        "html": html,
        "bytes": sum(p.stat().st_size for p in files),
        "top_keys_example": keys_top,
        "dataset_name_guess": dataset_name,
        "doc_type_counts": dict(types.most_common()),
        "splits": dict(splits),
        "n_label_occurrences": sum(label_ctr.values()),
        "n_distinct_labels": len(label_ctr),
        "top30_labels": label_ctr.most_common(30),
        "section_keys_top": section_keys.most_common(40),
        "target_placeholder": placeholder_stats,
        "clause_all_three_types": dict(clause_all),
        "n_type_all_three": dict(n_type_all),
        "samples": samples,
        "target_doc_samples": {k: v[:2] for k, v in target_docs.items()},
    }


def scan_law_api():
    root = WORK / "data_contract" / "law_api"
    out = {"folders": {}}
    wanted = [
        "근로기준법",
        "근로기준법 시행령",
        "최저임금법",
        "기간제 및 단시간근로자 보호 등에 관한 법률",
        "주택임대차보호법",
        "주택임대차보호법 시행령",
        "민법",
        "약관의 규제에 관한 법률",
        "보증인 보호를 위한 특별법",
        "이자제한법",
        "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
        "고용보험법",
        "산업재해보상보험법",
    ]
    for sub in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda x: x.name):
        files = [f for f in sub.rglob("*") if f.is_file()]
        kinds = Counter()
        empty = html = js = other = 0
        json_ok = 0
        broken = 0
        samples = []
        names = []
        for f in files:
            raw = f.read_bytes()
            if not raw:
                empty += 1
                kinds["empty"] += 1
                continue
            k = file_kind_bytes(raw)
            kinds[k] += 1
            if k == "empty":
                empty += 1
            elif k == "html":
                html += 1
            elif k == "json":
                json_ok += 1
                try:
                    obj = json.loads(raw)
                except Exception:
                    broken += 1
                    json_ok -= 1
                    continue
                if len(samples) < 2:
                    samples.append({"file": f.name, "top": list(obj.keys())[:20] if isinstance(obj, dict) else type(obj).__name__})
            else:
                other += 1
        folder = {
            "n_files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "kinds": dict(kinds),
            "json_ok": json_ok,
            "html": html,
            "empty": empty,
            "other": other,
            "broken_json": broken,
            "samples": samples,
        }
        out["folders"][sub.name] = folder

    # 현행: law names
    cur = root / "현행"
    current_laws = []
    article_split = Counter()
    for f in sorted(cur.glob("*")):
        if not f.is_file():
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            current_laws.append({"file": f.name, "status": "parse_fail"})
            continue
        # try common keys
        name = None
        date = None

        def find(o, keys, depth=0):
            if depth > 5:
                return None
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in keys and isinstance(v, str) and v.strip():
                        return v.strip()
                for v in o.values():
                    r = find(v, keys, depth + 1)
                    if r:
                        return r
            elif isinstance(o, list):
                for it in o[:20]:
                    r = find(it, keys, depth + 1)
                    if r:
                        return r
            return None

        name = find(obj, {"법령명_한글", "법령명한글", "법령명", "lawName", "법종명"})
        date = find(obj, {"시행일자", "시행일", "efYd", "시행일자문자열"})
        # articles
        n_art = 0

        def count_art(o, depth=0):
            nonlocal n_art
            if depth > 8:
                return
            if isinstance(o, dict):
                if any(k in o for k in ("조문번호", "조번호", "조문내용", "article")):
                    n_art += 1
                for v in o.values():
                    count_art(v, depth + 1)
            elif isinstance(o, list):
                for it in o:
                    count_art(it, depth + 1)

        count_art(obj)
        current_laws.append({"file": f.name, "name": name, "efYd": date, "n_article_nodes": n_art, "top_keys": list(obj.keys())[:15] if isinstance(obj, dict) else None})
        article_split[bool(n_art)] += 1
    wanted_hit = []
    names_only = [x.get("name") or "" for x in current_laws]
    blob = " ".join(names_only)
    for w in wanted:
        hit = any(w.replace(" ", "") in (n or "").replace(" ", "") for n in names_only)
        wanted_hit.append({"want": w, "present": hit})
    out["current_laws"] = current_laws
    out["wanted"] = wanted_hit
    out["article_split_flag_counts"] = {"has_article_nodes": article_split[True], "no_article_nodes": article_split[False]}

    # 판례
    prec_dir = root / "판례"
    prec_files = [f for f in prec_dir.rglob("*") if f.is_file()]
    prec_n = 0
    case_names = Counter()
    fill = Counter()
    fields_seen = Counter()
    html_p = empty_p = broken_p = 0
    query_notes = []
    for f in prec_files:
        if f.suffix.lower() in {".md", ".txt", ".csv"}:
            try:
                t = f.read_text(encoding="utf-8", errors="ignore")[:2000]
            except Exception:
                t = ""
            if any(k in f.name.lower() for k in ("query", "log", "report", "filter", "수집")):
                query_notes.append({"file": str(f.relative_to(root)), "clip": clip(t, 150)})
            continue
        raw = f.read_bytes()
        if not raw:
            empty_p += 1
            continue
        k = file_kind_bytes(raw)
        if k == "html":
            html_p += 1
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            broken_p += 1
            continue
        items = None
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict):
            for kk in ("PrecSearch", "prec", "list", "items", "판례", "body"):
                if kk in obj and isinstance(obj[kk], (list, dict)):
                    items = obj[kk]
                    break
            if items is None:
                items = [obj]
        if isinstance(items, dict):
            # nested list
            for v in items.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
        if not isinstance(items, list):
            items = [items]
        for it in items:
            if not isinstance(it, dict):
                continue
            prec_n += 1
            for k in it.keys():
                fields_seen[k] += 1
            nm = it.get("사건명") or it.get("caseNm") or it.get("사건명목록")
            if nm:
                case_names[str(nm)] += 1
            for fld, aliases in {
                "판시사항": ["판시사항", "판시사항내용"],
                "판결요지": ["판결요지", "판결요지내용"],
                "전문": ["판례내용", "전문", "판결문", "precContents"],
            }.items():
                ok = any(nonempty(it.get(a)) for a in aliases)
                fill[fld + ("_filled" if ok else "_empty")] += 1
    out["prec"] = {
        "n_files": len(prec_files),
        "n_records_parsed": prec_n,
        "html": html_p,
        "empty": empty_p,
        "broken": broken_p,
        "top20_caseNm": case_names.most_common(20),
        "fill": dict(fill),
        "fields_seen": fields_seen.most_common(30),
        "query_notes": query_notes,
        "near_400_cut": "확인 필요" if 350 <= prec_n <= 450 else ("건수가 400 근처가 아님" if prec_n else "0"),
    }

    # 해석례
    exp_dir = root / "법령해석례"
    exp_files = [f for f in exp_dir.rglob("*") if f.is_file()]
    exp_n = 0
    exp_fill = Counter()
    exp_html = exp_empty = 0
    for f in exp_files:
        raw = f.read_bytes()
        if not raw:
            exp_empty += 1
            continue
        if file_kind_bytes(raw) == "html":
            exp_html += 1
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        items = obj if isinstance(obj, list) else [obj]
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
                if isinstance(v, dict):
                    for vv in v.values():
                        if isinstance(vv, list) and vv and isinstance(vv[0], dict):
                            items = vv
                            break
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            exp_n += 1
            for fld, aliases in {
                "질의요지": ["질의요지", "질의요지내용", "question"],
                "회답": ["회답", "회답내용", "answer"],
                "이유": ["이유", "이유내용", "reason"],
            }.items():
                ok = any(nonempty(it.get(a)) for a in aliases)
                exp_fill[fld + ("_filled" if ok else "_empty")] += 1
    out["expc"] = {"n_files": len(exp_files), "n_records": exp_n, "html": exp_html, "empty": exp_empty, "fill": dict(exp_fill)}

    # 공정위
    ftc = root / "공정위"
    ftc_files = [f for f in ftc.rglob("*") if f.is_file()]
    ftc_n = 0
    ftc_kind = Counter()
    yakgwan_n = 0
    reason_field = None
    reason_samples = []
    ftc_html = 0
    for f in ftc_files:
        raw = f.read_bytes()
        if not raw:
            continue
        if file_kind_bytes(raw) == "html":
            ftc_html += 1
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        items = []
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict):
            items = [obj]
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
        for it in items:
            if not isinstance(it, dict):
                continue
            ftc_n += 1
            blob = json.dumps(it, ensure_ascii=False)
            if "약관" in blob:
                yakgwan_n += 1
            for k, v in it.items():
                if any(x in k for x in ("이유", "판단", "위반", "불공정")) and nonempty(v) and reason_field is None:
                    reason_field = k
            if reason_field and nonempty(it.get(reason_field)) and len(reason_samples) < 2:
                reason_samples.append({"field": reason_field, "text": clip(it.get(reason_field), 150)})
            title = str(it.get("제목") or it.get("title") or it.get("문서명") or "")
            if "심결" in blob:
                ftc_kind["심결키워드"] += 1
            if "의결" in blob:
                ftc_kind["의결키워드"] += 1
            if "약관" in blob:
                ftc_kind["약관키워드"] += 1
    out["ftc"] = {
        "n_files": len(ftc_files),
        "n_records": ftc_n,
        "html": ftc_html,
        "yakgwan_records": yakgwan_n,
        "kind_keyword_counts": dict(ftc_kind),
        "reason_field": reason_field,
        "reason_samples": reason_samples,
        "file_list": [str(f.relative_to(ftc)) for f in ftc_files],
    }

    # 용어
    term_dir = root / "법령용어"
    term_files = [f for f in term_dir.rglob("*") if f.is_file()]
    term_n = 0
    for f in term_files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(obj, list):
            term_n += len(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    term_n += len(v)
                    break
            else:
                term_n += 1
    out["terms"] = {"n_files": len(term_files), "n_records_est": term_n}
    return out


def main():
    log("A 019")
    a = scan_019()
    write_json(OUT / "A_019.json", a)
    log("B forms")
    b = scan_forms()
    write_json(OUT / "B_forms.json", b)
    log("D law_api")
    d = scan_law_api()
    write_json(OUT / "D_law_api.json", d)
    log("done core A/B/D")


if __name__ == "__main__":
    main()
