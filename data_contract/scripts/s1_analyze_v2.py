# -*- coding: utf-8 -*-
"""S1 재분석: document.sections / content_labels / description 구조."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
OUT = ROOT / "data_contract" / "aihub_forms"
SRC = ROOT / "05.계약 법률 문서 서식 데이터"
REPORT = ROOT / "data_contract" / "s1_results.json"


def classify_bucket(path: Path) -> str:
    s = str(path)
    if "금전" in s or "채권_채무" in s:
        return "금전대차"
    if "부동산" in s or "임대" in s:
        return "부동산임대"
    if "고용" in s or "인사" in s or "노무" in s:
        return "고용"
    return "기타"


def kind_of(path: Path) -> str:
    for part in path.parts:
        if part.startswith(("TS_", "VS_")):
            return "원천"
        if part.startswith(("TL_", "VL_")):
            return "라벨"
    return "기타"


def load_obj(p: Path):
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return json.loads(p.read_text(encoding=enc))
        except Exception:
            continue
    return {"_load_error": "read_fail"}


def doc_meta(obj: dict) -> dict:
    doc = obj.get("document") if isinstance(obj.get("document"), dict) else obj
    meta = ((doc.get("metadata") or {}).get("file_info") or {}) if isinstance(doc, dict) else {}
    cat = meta.get("document_category") or {}
    return {
        "document_name": meta.get("document_name"),
        "document_format": meta.get("document_format"),
        "document_page_count": meta.get("document_page_count"),
        "type": doc.get("type") if isinstance(doc, dict) else None,
        "main_category": cat.get("main_category"),
        "sub_category": cat.get("sub_category"),
        "detail_category": cat.get("detail_category"),
        "related_law": ((meta.get("additional_info") or {}) or {}).get("related_law"),
    }


def sections_of(obj: dict):
    doc = obj.get("document") if isinstance(obj.get("document"), dict) else obj
    if isinstance(doc, dict) and isinstance(doc.get("sections"), list):
        return doc["sections"]
    return []


def filled_status(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "빈칸"
    markers = ["OOO", "OO", "○○", "○○○", "___", "□", "(@", "마스킹", "***", "×××", "성명", "금 원"]
    hit = [m for m in markers if m in t]
    has_amount = bool(re.search(r"\d{1,3}(,\d{3})+|\d+\s*원|금\s*\d+", t))
    has_date = bool(re.search(r"\d{4}\s*[.\-/년]\s*\d{1,2}", t))
    # placeholder patterns like (@회사명1)
    has_placeholder = bool(re.search(r"\(@[^)]+\)|【[^】]+】|_{2,}", t))
    if has_placeholder or (hit and not has_amount):
        return f"플레이스홀더/서식칸 의심" + (f"({','.join(hit[:3])})" if hit else "")
    if has_amount or has_date:
        return "금액·날짜 등 값 채움 흔적"
    return "텍스트 있음(서식성 여부 불명확)"


def main():
    files = [p for p in OUT.rglob("*") if p.is_file()]
    by_kind = {"원천": [], "라벨": [], "기타": []}
    for p in files:
        by_kind[kind_of(p)].append(p)

    zip_rows = []
    for z in sorted(SRC.rglob("*.zip")):
        zip_rows.append({
            "zip": str(z.relative_to(SRC)),
            "zip_bytes": z.stat().st_size,
            "zip_MB": round(z.stat().st_size / 1024 / 1024, 3),
        })

    label_jsons = [(p, load_obj(p)) for p in by_kind["라벨"] if p.suffix.lower() == ".json"]
    source_jsons = [(p, load_obj(p)) for p in by_kind["원천"] if p.suffix.lower() == ".json"]

    tax = Counter()
    emp_detail = Counter()
    bucket_counts = Counter()
    content_vocab = defaultdict(Counter)
    format_vocab = defaultdict(Counter)
    detail_by_bucket = defaultdict(Counter)

    for p, obj in label_jsons:
        if not isinstance(obj, dict) or "_load_error" in obj:
            continue
        bucket = classify_bucket(p)
        bucket_counts[bucket] += 1
        m = doc_meta(obj)
        tax[(m["main_category"], m["sub_category"], m["detail_category"], bucket)] += 1
        detail_by_bucket[bucket][m["detail_category"] or "?"] += 1
        if bucket == "고용":
            emp_detail[m["detail_category"] or "?"] += 1
        for sec in sections_of(obj):
            if not isinstance(sec, dict):
                continue
            content = sec.get("content") or {}
            labels = content.get("content_labels") or []
            if isinstance(labels, list):
                for lab in labels:
                    content_vocab[bucket][str(lab)] += 1
            fmt = (sec.get("format") or {}).get("format_type")
            if fmt:
                format_vocab[bucket][str(fmt)] += 1

    # samples: 3 per bucket
    sample_sections = {}
    for bucket in ("고용", "부동산임대", "금전대차"):
        picked = []
        for p, obj in label_jsons:
            if classify_bucket(p) != bucket or not isinstance(obj, dict):
                continue
            secs = sections_of(obj)
            if not secs:
                continue
            m = doc_meta(obj)
            sec_rows = []
            for sec in secs[:15]:
                if not isinstance(sec, dict):
                    continue
                content = sec.get("content") or {}
                txt = content.get("description") or ""
                labs = content.get("content_labels") or []
                fmt = (sec.get("format") or {})
                sec_rows.append({
                    "format_type": fmt.get("format_type"),
                    "section_type": fmt.get("section_type"),
                    "content_labels": labs,
                    "text_head_200": (txt or "")[:200],
                    "filled_status": filled_status(txt or ""),
                })
            picked.append({
                "path": str(p.relative_to(OUT)),
                "meta": m,
                "n_sections": len(secs),
                "sections_preview": sec_rows,
            })
            if len(picked) >= 3:
                break
        sample_sections[bucket] = picked

    # employment non-labor-contract count
    laborish = []
    non_labor = []
    for name, cnt in emp_detail.most_common():
        if any(k in (name or "") for k in ("근로", "고용계약", "연봉", "임금", "채용")):
            laborish.append((name, cnt))
        else:
            non_labor.append((name, cnt))

    vocab_path = OUT / "label_vocab.csv"
    with vocab_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "rank", "content_label", "count"])
        for bucket in ("고용", "부동산임대", "금전대차"):
            for i, (lab, cnt) in enumerate(content_vocab[bucket].most_common(50), 1):
                w.writerow([bucket, i, lab, cnt])

    # source vs label format note
    src_sample = None
    if source_jsons:
        p0, o0 = source_jsons[0]
        src_sample = {
            "path": str(p0.relative_to(OUT)),
            "top_keys": list(o0.keys()) if isinstance(o0, dict) else [],
            "meta": doc_meta(o0) if isinstance(o0, dict) else {},
            "n_sections": len(sections_of(o0)) if isinstance(o0, dict) else 0,
            "head": json.dumps(o0, ensure_ascii=False)[:800] if isinstance(o0, dict) else str(o0)[:400],
        }

    expected = {
        "근로(고용) 계약서": 182,
        "주거용 부동산 임대": 81,
        "사용대차/임대차": 182,
        "금전대차": 320,
    }

    # compare: actual detail categories under 부동산 that look residential lease
    residential = sum(
        c for name, c in detail_by_bucket["부동산임대"].items()
        if any(k in (name or "") for k in ("주택", "주거", "원룸", "오피스텔", "아파트", "임대차"))
    )

    result = {
        "src": str(SRC),
        "out": str(OUT),
        "zips": zip_rows,
        "n_files_total": len(files),
        "ext_all": dict(Counter(p.suffix.lower() for p in files)),
        "n_source_files": len(by_kind["원천"]),
        "n_label_files": len(by_kind["라벨"]),
        "source_ext": dict(Counter(p.suffix.lower() for p in by_kind["원천"])),
        "label_ext": dict(Counter(p.suffix.lower() for p in by_kind["라벨"])),
        "label_json_count": len(label_jsons),
        "bucket_counts_label_json": dict(bucket_counts),
        "detail_category_by_bucket": {k: dict(v.most_common()) for k, v in detail_by_bucket.items()},
        "taxonomy_counts": [
            {"대분류": a, "중분류": b, "소분류": c, "bucket": d, "count": n}
            for (a, b, c, d), n in tax.most_common()
        ],
        "employment_detail_category_counts": dict(emp_detail.most_common()),
        "employment_laborish": laborish,
        "employment_non_labor_contract_like": non_labor,
        "employment_non_labor_total": sum(c for _, c in non_labor),
        "expected_aihub_page": expected,
        "actual_vs_expected_note": {
            "고용_label_json": bucket_counts.get("고용"),
            "부동산임대_label_json": bucket_counts.get("부동산임대"),
            "금전대차_label_json": bucket_counts.get("금전대차"),
            "부동산_detail_주거임대_추정합": residential,
            "note": "AI Hub 페이지 기대값(Train+Val)과 zip 파일명 버킷 합이 다름. 이번 다운로드는 3개 대분류 zip만 포함.",
        },
        "sample_sections": sample_sections,
        "label_vocab_csv": str(vocab_path),
        "content_vocab_top20": {k: v.most_common(20) for k, v in content_vocab.items()},
        "format_vocab_top10": {k: v.most_common(10) for k, v in format_vocab.items()},
        "source_sample": src_sample,
        "structure_note": "라벨/원천 모두 .json. 조항 텍스트는 sections[].content.description. content_labels는 배열. 원천도 JSON(PDF 바이너리 아님).",
    }
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("buckets", dict(bucket_counts))
    print("emp_non_labor_total", result["employment_non_labor_total"])
    print("samples", {k: len(v) for k, v in sample_sections.items()})
    if sample_sections.get("고용"):
        print("고용 sample0", sample_sections["고용"][0]["meta"], sample_sections["고용"][0]["sections_preview"][:2])
    print("WROTE", REPORT)


if __name__ == "__main__":
    main()
