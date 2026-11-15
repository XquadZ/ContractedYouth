# -*- coding: utf-8 -*-
"""1단계: AI Hub 계약 법률 문서 서식 zip 해제·검증 (GPU 미사용)."""
from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
SRC = ROOT / "05.계약 법률 문서 서식 데이터"
OUT = ROOT / "data_contract" / "aihub_forms"
REPORT = ROOT / "data_contract" / "s1_results.json"


def unzip_all() -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for z in sorted(SRC.rglob("*.zip")):
        dest = OUT / z.stem
        dest.mkdir(parents=True, exist_ok=True)
        info = {
            "zip": str(z.relative_to(SRC)),
            "zip_bytes": z.stat().st_size,
            "dest": str(dest),
            "ok": False,
            "n_extracted": 0,
            "error": None,
        }
        try:
            with zipfile.ZipFile(z, "r") as zf:
                names = zf.namelist()
                # extract only if empty-ish
                existing = list(dest.rglob("*"))
                if len([p for p in existing if p.is_file()]) == 0:
                    zf.extractall(dest)
                info["n_extracted"] = len([p for p in dest.rglob("*") if p.is_file()])
                info["ok"] = True
                info["zip_entries"] = len(names)
        except Exception as e:
            info["error"] = repr(e)
        rows.append(info)
        print("ZIP", info["zip"], "bytes", info["zip_bytes"], "files", info["n_extracted"], info.get("error"))
    return rows


def load_jsons(base: Path) -> list[tuple[Path, dict]]:
    out = []
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".json":
            try:
                out.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                try:
                    out.append((p, json.loads(p.read_text(encoding="utf-8-sig"))))
                except Exception as e:
                    out.append((p, {"_load_error": repr(e)}))
    return out


def classify_bucket(path: Path) -> str:
    s = str(path)
    if "금전" in s or "채권_채무" in s:
        return "금전대차"
    if "부동산" in s or "임대" in s:
        return "부동산임대"
    if "고용" in s or "인사" in s or "노무" in s:
        return "고용"
    return "기타"


def extract_meta(obj: dict) -> dict:
    """Best-effort metadata from AIHub label JSON."""
    meta = {}
    # common patterns
    for k in ("dataInfo", "meta", "Meta", "info", "datasetInfo", "data_info"):
        if isinstance(obj.get(k), dict):
            meta.update(obj[k])
    for k in (
        "doc_type", "documentType", "대분류", "중분류", "소분류",
        "category", "subcategory", "cls", "class", "type",
        "docNm", "docName", "문서명", "formName", "title",
    ):
        if k in obj and not isinstance(obj[k], (dict, list)):
            meta[k] = obj[k]
        if k in meta:
            continue
        for nest in ("dataInfo", "meta", "Meta", "info"):
            if isinstance(obj.get(nest), dict) and k in obj[nest]:
                meta[k] = obj[nest][k]
    return meta


def get_sections(obj: dict):
    for k in ("sections", "section", "Sections", "조항", "clauses"):
        if isinstance(obj.get(k), list):
            return obj[k]
    # nested
    for nest in ("data", "label", "annotation", "labeledData"):
        v = obj.get(nest)
        if isinstance(v, dict):
            for k in ("sections", "section", "Sections"):
                if isinstance(v.get(k), list):
                    return v[k]
    return []


def text_of_section(sec: dict) -> str:
    for k in ("content", "text", "clause", "value", "본문", "내용"):
        v = sec.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            for kk in ("text", "content", "value", "label"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return v[kk]
    # sometimes content is nested list
    return ""


def section_labels(sec: dict) -> dict:
    out = {}
    for k in ("format", "content", "type", "label", "tag", "name", "sectionType"):
        v = sec.get(k)
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = v.get("label") or v.get("type") or str(v)[:80]
    # nested content label
    c = sec.get("content")
    if isinstance(c, dict):
        out["content_label"] = c.get("label") or c.get("type") or c.get("tag")
        out["content_text"] = c.get("text") or c.get("value") or c.get("content") or ""
    else:
        out["content_label"] = out.get("content")
        out["content_text"] = text_of_section(sec)
    f = sec.get("format")
    if isinstance(f, dict):
        out["format_label"] = f.get("label") or f.get("type")
    else:
        out["format_label"] = out.get("format")
    return out


def filled_status(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "빈칸"
    markers = ["OOO", "OO", "○○", "○○○", "___", "___", "□", "【", "홍길동", "김○○", "마스킹", "***", "×××"]
    hit = [m for m in markers if m in t]
    # digit/amount presence
    import re
    has_amount = bool(re.search(r"\d{1,3}(,\d{3})+|\d+\s*원|금\s*\d+", t))
    has_date = bool(re.search(r"\d{4}\s*[.\-/년]\s*\d{1,2}", t))
    if hit and not has_amount and not has_date:
        return f"플레이스홀더/마스킹 의심({','.join(hit[:3])})"
    if has_amount or has_date:
        return "금액·날짜 등 값 채움 흔적"
    return "텍스트 있음(서식성 여부 불명확)"


def analyze() -> dict:
    zip_rows = unzip_all()
    files = [p for p in OUT.rglob("*") if p.is_file()]
    ext_counter = Counter(p.suffix.lower() or "(noext)" for p in files)

    # split source vs label by path
    source_files = [p for p in files if "원천" in str(p) or p.parts and any("TS_" in x or "VS_" in x or "원천" in x for x in p.parts)]
    # better: parent zip stem
    by_kind = {"원천": [], "라벨": [], "기타": []}
    for p in files:
        s = str(p)
        if any(x in s for x in ("TS_", "VS_", "원천")) and "라벨" not in s:
            # zip stem starts with TS/VS
            parent_zipish = p.parts
            if any(part.startswith(("TS_", "VS_")) for part in parent_zipish):
                by_kind["원천"].append(p)
            elif any(part.startswith(("TL_", "VL_")) for part in parent_zipish):
                by_kind["라벨"].append(p)
            else:
                by_kind["기타"].append(p)
        elif any(part.startswith(("TL_", "VL_")) for part in p.parts):
            by_kind["라벨"].append(p)
        else:
            by_kind["기타"].append(p)

    # recount properly by top extracted folder name
    by_kind = {"원천": [], "라벨": [], "기타": []}
    for p in files:
        top = None
        for part in p.parts:
            if part.startswith(("TS_", "VS_", "TL_", "VL_")):
                top = part
                break
        if top is None:
            by_kind["기타"].append(p)
        elif top.startswith(("TS_", "VS_")):
            by_kind["원천"].append(p)
        else:
            by_kind["라벨"].append(p)

    label_jsons = []
    for p in by_kind["라벨"]:
        if p.suffix.lower() == ".json":
            try:
                label_jsons.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                try:
                    label_jsons.append((p, json.loads(p.read_text(encoding="utf-8-sig"))))
                except Exception as e:
                    label_jsons.append((p, {"_load_error": repr(e)}))

    # taxonomy counts
    tax = Counter()
    tax_detail = []
    bucket_counts = Counter()
    employment_sub = Counter()
    samples_raw = []

    content_vocab = defaultdict(Counter)  # bucket -> content_label -> count

    for p, obj in label_jsons:
        bucket = classify_bucket(p)
        bucket_counts[bucket] += 1
        meta = extract_meta(obj) if isinstance(obj, dict) else {}
        # try deep keys for classification
        big = mid = small = docnm = None
        def walk(o, depth=0):
            nonlocal big, mid, small, docnm
            if depth > 4 or not isinstance(o, dict):
                return
            for k, v in o.items():
                kl = str(k)
                if kl in ("대분류", "lclas", "Lclas", "largeCategory", "superCategory") and isinstance(v, str):
                    big = big or v
                if kl in ("중분류", "mlsfc", "Mlsfc", "middleCategory") and isinstance(v, str):
                    mid = mid or v
                if kl in ("소분류", "sclas", "Sclas", "smallCategory", "subCategory") and isinstance(v, str):
                    small = small or v
                if kl in ("문서명", "docNm", "docName", "formName", "title", "fileName") and isinstance(v, str):
                    docnm = docnm or v
                if isinstance(v, dict):
                    walk(v, depth + 1)
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    walk(v[0], depth + 1)
        if isinstance(obj, dict):
            walk(obj)
        key = (big or "?", mid or "?", small or "?", bucket)
        tax[key] += 1
        tax_detail.append({
            "path": str(p.relative_to(OUT)),
            "bucket": bucket,
            "대분류": big,
            "중분류": mid,
            "소분류": small,
            "문서명": docnm,
            "top_keys": list(obj.keys())[:20] if isinstance(obj, dict) else [],
        })
        if bucket == "고용":
            employment_sub[small or docnm or mid or "?"] += 1

        secs = get_sections(obj) if isinstance(obj, dict) else []
        for sec in secs:
            if not isinstance(sec, dict):
                continue
            labs = section_labels(sec)
            cl = labs.get("content_label") or labs.get("content") or "(none)"
            content_vocab[bucket][str(cl)] += 1

    # pick 3 samples per target bucket with sections
    sample_sections = {}
    for bucket in ("고용", "부동산임대", "금전대차"):
        picked = []
        for p, obj in label_jsons:
            if classify_bucket(p) != bucket:
                continue
            secs = get_sections(obj) if isinstance(obj, dict) else []
            if not secs:
                continue
            sec_rows = []
            for sec in secs[:12]:
                if not isinstance(sec, dict):
                    continue
                labs = section_labels(sec)
                txt = labs.get("content_text") or text_of_section(sec)
                sec_rows.append({
                    "format": labs.get("format_label"),
                    "content_label": labs.get("content_label"),
                    "text_head_200": (txt or "")[:200],
                    "filled_status": filled_status(txt or ""),
                })
            picked.append({
                "path": str(p.relative_to(OUT)),
                "n_sections": len(secs),
                "sections_preview": sec_rows,
                "top_keys": list(obj.keys())[:30] if isinstance(obj, dict) else [],
            })
            if len(picked) >= 3:
                break
        sample_sections[bucket] = picked

    # write label_vocab.csv
    vocab_path = OUT.parent / "aihub_forms" / "label_vocab.csv"
    # actually put at data_contract/aihub_forms/label_vocab.csv
    vocab_path = OUT / "label_vocab.csv"
    with vocab_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "rank", "content_label", "count"])
        for bucket in ("고용", "부동산임대", "금전대차"):
            for i, (lab, cnt) in enumerate(content_vocab[bucket].most_common(50), 1):
                w.writerow([bucket, i, lab, cnt])

    # expected comparison
    expected = {
        "근로(고용) 계약서": 182,
        "주거용 부동산 임대": 81,
        "사용대차/임대차": 182,
        "금전대차": 320,
    }

    # source file formats
    src_ext = Counter(p.suffix.lower() or "(noext)" for p in by_kind["원천"])
    lab_ext = Counter(p.suffix.lower() or "(noext)" for p in by_kind["라벨"])

    result = {
        "src": str(SRC),
        "out": str(OUT),
        "zips": zip_rows,
        "n_files_total": len(files),
        "ext_all": dict(ext_counter),
        "n_source_files": len(by_kind["원천"]),
        "n_label_files": len(by_kind["라벨"]),
        "source_ext": dict(src_ext),
        "label_ext": dict(lab_ext),
        "label_json_count": len(label_jsons),
        "bucket_counts_label_json": dict(bucket_counts),
        "taxonomy_counts": [
            {"대분류": a, "중분류": b, "소분류": c, "bucket": d, "count": n}
            for (a, b, c, d), n in tax.most_common()
        ],
        "employment_subcategory_counts": dict(employment_sub.most_common()),
        "expected_aihub_page": expected,
        "sample_sections": sample_sections,
        "label_vocab_csv": str(vocab_path),
        "content_vocab_top10": {k: v.most_common(10) for k, v in content_vocab.items()},
        "taxonomy_sample_paths": tax_detail[:5],
        "note_first_label_keys": (list(label_jsons[0][1].keys()) if label_jsons and isinstance(label_jsons[0][1], dict) else None),
    }
    # dump one full sample structure keys recursively shallow
    if label_jsons:
        p0, o0 = label_jsons[0]
        result["first_label_path"] = str(p0.relative_to(OUT))
        result["first_label_dump_head"] = json.dumps(o0, ensure_ascii=False)[:2000] if isinstance(o0, dict) else str(o0)[:500]

    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", REPORT)
    return result


if __name__ == "__main__":
    analyze()
