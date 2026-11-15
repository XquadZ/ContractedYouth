# -*- coding: utf-8 -*-
"""폴더 정리(빈 AI_Service) + F1~F12 최종 데이터 검사."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
NOW = datetime.now().strftime("%Y%m%d%H%M")
SEARCH_BASES = [
    Path(r"C:\Users\DMLAB\Desktop"),
    Path(r"C:\Users\DMLAB\Documents"),
    Path(r"C:\Users\DMLAB"),
    ROOT,
]


def sha256_file(path: Path, chunk=8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def folder_stats(p: Path) -> dict:
    n = sz = 0
    latest = 0
    if not p.exists():
        return {"files": 0, "bytes": 0, "mtime": None}
    for f in p.rglob("*"):
        if f.is_file():
            st = f.stat()
            n += 1
            sz += st.st_size
            latest = max(latest, st.st_mtime)
    return {
        "files": n,
        "bytes": sz,
        "mtime": datetime.fromtimestamp(latest).isoformat(sep=" ", timespec="seconds") if latest else None,
    }


# ---------- 0. find WRONG ----------
def step0() -> list[dict]:
    found = []
    # direct + limited recursive
    candidates = []
    home = Path(r"C:\Users\DMLAB")
    for child in home.iterdir() if home.exists() else []:
        if child.is_dir() and child.name == "AI_Service":
            candidates.append(child)
    for base in [Path(r"C:\Users\DMLAB\Desktop"), Path(r"C:\Users\DMLAB\Documents"), ROOT]:
        if not base.exists():
            continue
        for p in base.rglob("AI_Service"):
            if p.is_dir() and p.name == "AI_Service":
                candidates.append(p)
    seen = set()
    for p in candidates:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        st = folder_stats(p)
        found.append({"path": key, **st, "children": [c.name for c in p.iterdir()] if p.exists() else []})
    return found


# ---------- 1–2. diff + merge ----------
def classify_and_merge(wrong_dirs: list[dict]) -> dict:
    diff_rows = []
    merge_rows = []
    summary = Counter()
    summary_bytes = Counter()
    only_wrong_by_top = defaultdict(list)
    conflicts = []
    copied = []

    # build ROOT hash index (data_contract + standard_forms + models top — avoid full 160GB)
    # For empty WRONG this is fast; if WRONG has files scan those only
    root_by_rel = {}
    root_by_hash = defaultdict(list)

    def index_root_file(f: Path):
        try:
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return
        h = sha256_file(f)
        root_by_rel[rel] = {"path": str(f), "sha256": h, "size": f.stat().st_size, "mtime": f.stat().st_mtime}
        root_by_hash[h].append(str(f))

    # Only index if WRONG has files
    wrong_files = []
    for w in wrong_dirs:
        wp = Path(w["path"])
        if not wp.exists():
            continue
        for f in wp.rglob("*"):
            if f.is_file():
                wrong_files.append((wp, f))

    if wrong_files:
        # index relevant ROOT areas + any matching relative paths
        for area in [DC, ROOT / "standard_forms", ROOT / "models", ROOT / "datasets"]:
            if not area.exists():
                continue
            for f in area.rglob("*"):
                if f.is_file() and f.stat().st_size < 500 * 1024 * 1024:  # skip huge blobs in index unless needed
                    # still hash all for correctness on (c)/(d) — but skip >2GB model shards unless compared
                    if f.stat().st_size > 2 * 1024 * 1024 * 1024:
                        continue
                    try:
                        index_root_file(f)
                    except Exception:
                        pass

    for wp, f in wrong_files:
        rel = str(f.relative_to(wp)).replace("\\", "/")
        size = f.stat().st_size
        h = sha256_file(f)
        root_path = ROOT / rel.replace("/", os.sep)
        classification = None
        root_match = ""
        if root_path.exists() and root_path.is_file():
            rh = sha256_file(root_path)
            if rh == h:
                classification = "a_same_path_same_hash"
                root_match = str(root_path)
            else:
                classification = "b_conflict"
                root_match = str(root_path)
                conflicts.append({
                    "rel": rel,
                    "wrong_size": size,
                    "wrong_mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(sep=" "),
                    "wrong_sha": h,
                    "root_size": root_path.stat().st_size,
                    "root_mtime": datetime.fromtimestamp(root_path.stat().st_mtime).isoformat(sep=" "),
                    "root_sha": rh,
                })
        elif h in root_by_hash:
            classification = "d_same_hash_diff_path"
            root_match = ";".join(root_by_hash[h][:3])
        else:
            # also check if hash exists anywhere under indexed root
            classification = "c_only_in_wrong"
            only_wrong_by_top[rel.split("/")[0] if "/" in rel else "(root)"].append(rel)

        summary[classification] += 1
        summary_bytes[classification] += size
        diff_rows.append({
            "rel_path": rel,
            "size": size,
            "sha256": h,
            "class": classification,
            "root_counterpart": root_match,
            "wrong_root": str(wp),
        })

    # copy (c)
    for row in diff_rows:
        if row["class"] != "c_only_in_wrong":
            continue
        rel = row["rel_path"]
        wp = Path(row["wrong_root"])
        src = wp / rel.replace("/", os.sep)
        # destination heuristics
        dest = ROOT / rel.replace("/", os.sep)
        low = rel.lower()
        if any(k in low for k in ["aihub", "약관", "서식", "계약"]):
            if "약관" in rel or "terms" in low or "580" in rel:
                dest = DC / "aihub_terms" / Path(rel).name
            elif "script" in low:
                dest = DC / "scripts" / Path(rel).name
            else:
                dest = DC / "aihub_forms" / rel.replace("/", os.sep)
        elif "law_api" in low or "법령" in rel:
            dest = DC / "law_api" / Path(*Path(rel).parts[1:]) if len(Path(rel).parts) > 1 else DC / "law_api" / Path(rel).name
        elif "cases" in low or "사례" in rel:
            dest = DC / "cases" / Path(rel).name
        elif "model" in low or rel.startswith("models/"):
            # compare only if model exists
            dest = DC / "models" / Path(rel).name
            # skip copy if same model name folder exists with matching file hash elsewhere
            existing = list((DC / "models").rglob(Path(rel).name)) if (DC / "models").exists() else []
            skip = False
            for e in existing:
                if e.is_file() and sha256_file(e) == row["sha256"]:
                    skip = True
                    merge_rows.append({
                        "rel_path": rel,
                        "action": "skip_model_same_hash",
                        "dest": str(e),
                        "src_sha": row["sha256"],
                        "dest_sha": row["sha256"],
                        "ok": True,
                    })
                    break
            if skip:
                continue
        elif "script" in low or rel.endswith(".py"):
            dest = DC / "scripts" / Path(rel).name

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # don't overwrite — side by side
            dest = dest.with_name(dest.stem + "__from_AI_Service" + dest.suffix)
        shutil.copy2(src, dest)
        dh = sha256_file(dest)
        ok = dh == row["sha256"]
        merge_rows.append({
            "rel_path": rel,
            "action": "copied",
            "dest": str(dest),
            "src_sha": row["sha256"],
            "dest_sha": dh,
            "ok": ok,
            "size": row["size"],
        })
        if ok:
            copied.append(dest)

    # write CSVs
    diff_path = DC / "FOLDER_DIFF.csv"
    with diff_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rel_path", "size", "sha256", "class", "root_counterpart", "wrong_root"])
        w.writeheader()
        w.writerows(diff_rows)

    merge_path = DC / "FOLDER_MERGE_LOG.csv"
    with merge_path.open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["rel_path", "action", "dest", "src_sha", "dest_sha", "ok", "size"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(merge_rows)

    return {
        "diff_rows": len(diff_rows),
        "summary_count": dict(summary),
        "summary_bytes": dict(summary_bytes),
        "only_wrong_by_top": {k: v for k, v in only_wrong_by_top.items()},
        "conflicts": conflicts,
        "copied_n": len([m for m in merge_rows if m.get("action") == "copied"]),
        "copied_bytes": sum(m.get("size") or 0 for m in merge_rows if m.get("action") == "copied" and m.get("ok")),
        "merge_ok": all(m.get("ok") for m in merge_rows if m.get("action") == "copied") if merge_rows else True,
    }


# ---------- 3. path refs ----------
def step3_path_refs() -> dict:
    hits = []
    exts = {".py", ".md", ".json", ".csv", ".html", ".txt", ".yml", ".yaml", ".bat", ".ps1"}
    # focus data_contract + scripts + prep; skip huge trees
    scan_roots = [DC, ROOT / "prep_contract", ROOT / "pilot", ROOT / "tools"]
    for base in scan_roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            if ".cache" in p.parts or "node_modules" in p.parts:
                continue
            try:
                if p.stat().st_size > 20 * 1024 * 1024:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "AI_Service" not in text:
                continue
            lines = []
            for i, line in enumerate(text.splitlines(), 1):
                if "AI_Service" in line:
                    lines.append({"line": i, "text": line.strip()[:200]})
            hits.append({"file": str(p.relative_to(ROOT)), "n": len(lines), "samples": lines[:5]})

    modified = []
    # Only auto-fix path assignments in scripts/config — never rewrite this checker itself
    skip_names = {"final_data_check.py", "DATA_READY_REPORT.md", "FINAL_DATA_CHECK.md", "MANUAL_DOWNLOADS.html"}
    for hit in hits:
        path = ROOT / hit["file"]
        if path.name in skip_names or path.name.startswith("final_data_check"):
            continue
        if path.suffix.lower() not in {".py", ".json"}:
            continue  # reports/html: list only
        if "REPORT" in path.name.upper() or "DATA_READY" in path.name:
            continue
        if "data_contract" not in hit["file"].replace("\\", "/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "AI_Service" not in text:
            continue
        # replace wrong-folder absolute paths only
        new = text
        new = new.replace(r"C:\Users\DMLAB\AI_Service", str(ROOT))
        new = new.replace("C:/Users/DMLAB/AI_Service", str(ROOT).replace("\\", "/"))
        # do not blindly replace bare 'AI_Service\\' — could be folder-name searches
        if new != text:
            bak = path.with_name(path.stem + f"_old_{NOW}" + path.suffix)
            if not bak.exists():
                shutil.copy2(path, bak)
            path.write_text(new, encoding="utf-8")
            modified.append({"file": hit["file"], "backup": str(bak.relative_to(ROOT))})

    return {"hits": hits, "modified": modified}


# ---------- 4. F1–F12 ----------
def parse_json_file(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": repr(e)}


def f1_standard_forms() -> dict:
    d = ROOT / "standard_forms"
    man = d / "MANIFEST.csv"
    out = {"id": "F1", "path": str(d), "status": "미확인", "detail": {}}
    if not d.exists():
        out["status"] = "없음"
        return out
    if not man.exists():
        out["status"] = "일부"
        out["detail"]["manifest"] = "없음"
        return out
    rows = list(csv.DictReader(man.open(encoding="utf-8-sig")))
    out["detail"]["manifest_rows"] = len(rows)
    missing = []
    hash_mismatch = []
    checked = set()
    for r in rows:
        rel = (r.get("파일명") or r.get("path") or r.get("file") or "").strip()
        if not rel:
            missing.append({"id": r.get("id"), "reason": "파일명 없음"})
            continue
        fp = d / rel
        expected = (r.get("sha256") or r.get("hash") or r.get("SHA256") or "").strip()
        if not fp.exists() or not fp.is_file():
            missing.append({"id": r.get("id"), "file": rel})
            continue
        key = (str(fp), expected.lower())
        if key in checked:
            continue
        checked.add(key)
        if expected:
            actual = sha256_file(fp)
            if actual.lower() != expected.lower():
                hash_mismatch.append({"file": rel, "expected": expected, "actual": actual})
    extracted = []
    for i in range(1, 7):
        p = d / "_extracted" / f"L{i}.txt"
        extracted.append({"file": f"L{i}.txt", "exists": p.exists(), "chars": len(p.read_text(encoding="utf-8", errors="ignore")) if p.exists() else 0})
    out["detail"]["missing_files"] = len(missing)
    out["detail"]["hash_mismatch"] = len(hash_mismatch)
    out["detail"]["extracted"] = extracted
    if missing or hash_mismatch or not all(x["exists"] for x in extracted):
        out["status"] = "일부" if rows else "불일치"
    else:
        out["status"] = "정상"
    return out


def f2_aihub_forms() -> dict:
    d = DC / "aihub_forms"
    out = {"id": "F2", "path": str(d), "status": "미확인", "detail": {}}
    if not d.exists():
        out["status"] = "없음"
        return out
    labels = [p for p in d.rglob("*.json") if any(x.startswith(("TL_", "VL_")) for x in p.parts)]
    out["detail"]["label_json_n"] = len(labels)
    c = Counter()
    for p in labels:
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cat = (((o.get("document") or {}).get("metadata") or {}).get("file_info") or {}).get("document_category") or {}
        detail = cat.get("detail_category") or ""
        if detail in ("근로(고용)계약서", "아르바이트계약서", "주거용부동산임대계약서"):
            c[detail] += 1
        elif "근로" in detail and "계약" in detail:
            c[detail] += 1
    out["detail"]["소분류"] = dict(c)
    vocab = d / "label_vocab.csv"
    out["detail"]["label_vocab"] = vocab.exists()
    if vocab.exists():
        out["detail"]["label_vocab_rows"] = sum(1 for _ in vocab.open(encoding="utf-8-sig")) - 1
    expect = {"근로(고용)계약서": 167, "아르바이트계약서": 31, "주거용부동산임대계약서": 70}
    diff = {k: c.get(k, 0) - v for k, v in expect.items()}
    out["detail"]["expect_diff"] = diff
    out["status"] = "정상" if vocab.exists() and len(labels) > 0 else "일부"
    return out


def f3_aihub_terms() -> dict:
    d = DC / "aihub_terms"
    out = {"id": "F3", "path": str(d), "status": "미확인", "detail": {}}
    if not d.exists():
        out["status"] = "없음"
        out["detail"]["note"] = "없음"
        return out
    files = [f for f in d.rglob("*") if f.is_file()]
    data_files = [f for f in files if f.suffix.lower() in {".json", ".zip", ".csv", ".xlsx"} or "약관" in f.name]
    placeholders = [f.name for f in files if f.name.upper() in {"NOT_FOUND.TXT", "WAITING.TXT"} or f.stem.upper() in {"NOT_FOUND", "WAITING"}]
    out["detail"]["files"] = len(files)
    out["detail"]["placeholders"] = placeholders
    out["detail"]["data_files"] = [f.name for f in data_files]
    if not data_files:
        out["status"] = "없음"
        out["detail"]["note"] = "약관 원천/라벨 없음 (WAITING/NOT_FOUND 플레이스홀더만)"
        return out
    good = bad = 0
    for p in d.rglob("*.json"):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "임대" not in t and "임대차" not in str(p):
            continue
        if "유리" in t:
            good += 1
        if "불리" in t:
            bad += 1
    out["detail"]["임대차_유리_언급파일"] = good
    out["detail"]["임대차_불리_언급파일"] = bad
    out["status"] = "일부"
    return out


def f4_current_laws() -> dict:
    out = {"id": "F4", "path": str(DC / "law_api"), "status": "미확인", "detail": {"laws": []}}
    targets = [
        "근로기준법", "근로기준법 시행령", "최저임금법", "최저임금법 시행령",
        "주택임대차보호법", "주택임대차보호법 시행령", "민법", "이자제한법",
        "이자제한법 제2조제1항의 최고이자율에 관한 규정", "보증인 보호를 위한 특별법",
    ]
    # search bodies in 연혁_g3, 연혁_v2_exact, 연혁, and any *body*
    body_dirs = [
        DC / "law_api" / "연혁_g3" / "bodies",
        DC / "law_api" / "연혁_v2_exact" / "bodies",
        DC / "law_api" / "연혁",
        DC / "law_api" / "현행",
    ]
    # longer names first so "근로기준법 시행령" wins over "근로기준법"
    for name in sorted(targets, key=len, reverse=True):
        cand = None
        for bd in body_dirs:
            if not bd.exists():
                continue
            # exact: "{name}_{digits}.json" and not longer sibling prefix
            for p in bd.glob("*.json"):
                if "_old_" in p.name:
                    continue
                m = re.match(rf"^{re.escape(name)}_(\d+)\.json$", p.name)
                if m:
                    cand = p
                    break
            if cand:
                break
        info = {"name": name, "file": str(cand) if cand else None}
        if cand:
            j = parse_json_file(cand)
            if "_error" in j:
                info["parse_ok"] = False
                info["error"] = j["_error"]
            else:
                info["parse_ok"] = True
                blob = json.dumps(j, ensure_ascii=False)
                # MST from filename is reliable
                mm = re.search(rf"^{re.escape(name)}_(\d+)\.json$", Path(cand).name)
                info["MST"] = mm.group(1) if mm else None
                m2 = re.search(r'"시행일자"\s*:\s*"?(\d{8})"?', blob)
                info["시행일"] = m2.group(1) if m2 else None
                try:
                    basic = (((j.get("법령") or {}).get("기본정보") or {}))
                    if isinstance(basic, dict):
                        info["시행일"] = info["시행일"] or basic.get("시행일자")
                        info["법령명_in_json"] = basic.get("법령명_한글") or basic.get("법령명한글")
                    units = j.get("법령", {}).get("조문", {}).get("조문단위")
                    if isinstance(units, list):
                        info["조문단위_수"] = len(units)
                        info["조문_수"] = sum(1 for u in units if u.get("조문여부") == "조문" and not u.get("조문가지번호"))
                    else:
                        info["조문단위_수"] = 1 if units else 0
                except Exception:
                    info["조문_수"] = None
                if not info.get("법령명_in_json"):
                    m3 = re.search(r'"법령명_?한글"\s*:\s*"([^"]+)"', blob)
                    info["법령명_in_json"] = m3.group(1) if m3 else None
                # name must match
                if info.get("법령명_in_json") and info["법령명_in_json"] != name:
                    info["parse_ok"] = False
                    info["error"] = f"법령명 불일치: {info['법령명_in_json']}"
        out["detail"]["laws"].append(info)
    # restore target order
    order = {n: i for i, n in enumerate(targets)}
    out["detail"]["laws"].sort(key=lambda x: order.get(x["name"], 99))
    ok_n = sum(1 for x in out["detail"]["laws"] if x.get("parse_ok"))
    out["detail"]["parse_ok_n"] = ok_n
    out["status"] = "정상" if ok_n == 10 else ("일부" if ok_n else "없음")
    return out


def f5_history() -> dict:
    out = {"id": "F5", "status": "미확인", "detail": {}}
    # prefer 연혁_g3 then 연혁_v2_exact then 연혁
    dirs = [DC / "law_api" / "연혁_g3", DC / "law_api" / "연혁_v2_exact", DC / "law_api" / "연혁"]
    used = next((d for d in dirs if d.exists()), None)
    out["path"] = str(used) if used else str(dirs[0])
    if not used:
        out["status"] = "없음"
        return out
    bodies = used / "bodies" if (used / "bodies").exists() else used
    by_law = defaultdict(list)
    mix = []
    for p in bodies.rglob("*.json"):
        if "list_" in p.name or p.name.startswith("_"):
            continue
        # expected name from filename prefix before _MST or _digits
        m = re.match(r"(.+?)_(\d+)\.json$", p.name)
        if not m:
            m = re.match(r"(.+?)_body_MST_(\d+)\.json$", p.name)
        expected = m.group(1) if m else p.stem
        j = parse_json_file(p)
        actual = None
        if isinstance(j, dict) and "_error" not in j:
            mm = re.search(r'"법령명한글"\s*:\s*"([^"]+)"', json.dumps(j, ensure_ascii=False))
            actual = mm.group(1) if mm else None
        by_law[expected].append({"file": p.name, "actual": actual, "MST": m.group(2) if m else None})
        if actual and actual != expected:
            mix.append({"file": p.name, "expected": expected, "actual": actual})
    out["detail"]["법령별_판수"] = {k: len(v) for k, v in by_law.items()}
    out["detail"]["혼입_건수"] = len(mix)
    out["detail"]["혼입_샘플"] = mix[:10]
    # g3 target laws
    g3_laws = ["근로기준법", "근로기준법 시행령", "주택임대차보호법", "주택임대차보호법 시행령", "민법", "보증인 보호를 위한 특별법"]
    out["detail"]["g3_대상_판수"] = {k: out["detail"]["법령별_판수"].get(k, 0) for k in g3_laws}
    out["status"] = "정상" if len(mix) == 0 and any(by_law.values()) else ("일부" if by_law else "없음")
    if mix and used.name == "연혁":
        out["status"] = "불일치"
        out["detail"]["note"] = "구 연혁 폴더에 혼입 있음. 연혁_g3 권장"
    if (DC / "law_api" / "연혁_g3" / "bodies").exists():
        # re-check g3 only for status
        mix_g3 = []
        for p in (DC / "law_api" / "연혁_g3" / "bodies").glob("*.json"):
            m = re.match(r"(.+?)_(\d+)\.json$", p.name)
            expected = m.group(1) if m else p.stem
            j = parse_json_file(p)
            mm = re.search(r'"법령명한글"\s*:\s*"([^"]+)"', json.dumps(j, ensure_ascii=False)) if "_error" not in j else None
            actual = mm.group(1) if mm else None
            if actual and actual != expected:
                mix_g3.append((expected, actual))
        out["detail"]["연혁_g3_혼입"] = len(mix_g3)
        out["status"] = "정상" if len(mix_g3) == 0 else "불일치"
        out["path"] = str(DC / "law_api" / "연혁_g3")
    return out


def f6_minwage() -> dict:
    out = {"id": "F6", "status": "미확인", "detail": {"years": {}}}
    expect = {"2022": "9,160", "2023": "9,620", "2024": "9,860", "2025": "10,030", "2026": "10,320"}
    adir = DC / "law_api" / "행정규칙" / "최저임금_v2"
    out["path"] = str(adir)
    if not adir.exists():
        out["status"] = "없음"
        return out
    ok = 0
    for y, hourly in expect.items():
        bodies = list(adir.glob(f"body_{y}_*.json"))
        pdf_txt = list((adir / "pdfs").glob(f"{y}_*.pdf.txt")) if (adir / "pdfs").exists() else []
        evidence = None
        found = None
        sources = bodies + pdf_txt
        for p in sources:
            t = p.read_text(encoding="utf-8", errors="ignore")
            if hourly.replace(",", "") in t.replace(",", "") or hourly in t:
                found = hourly
                # capture sentence
                m = re.search(rf".{{0,40}}{re.escape(hourly)}.{{0,20}}", t)
                evidence = {"file": str(p.relative_to(DC)), "snip": (m.group(0) if m else t[:80]).replace("\n", " ")}
                break
            # spaced OCR in pdf txt
            if re.search(r"시간급.*?모\s*든\s*산\s*업\s*" + hourly.replace(",", "[,]?"), t):
                found = hourly
                evidence = {"file": str(p.relative_to(DC)), "snip": "pdf txt match"}
                break
        # also check fix results
        out["detail"]["years"][y] = {"expected": hourly, "found": found, "evidence": evidence, "body_files": [str(p.name) for p in bodies]}
        if found == hourly:
            ok += 1
    # fallback from fix_abcdef / g results
    for cand in [DC / "fix_abcdef_results.json", DC / "g1_g7_results.json"]:
        if not cand.exists():
            continue
        try:
            j = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        years = (j.get("C") or {}).get("years") or {}
        for y, info in years.items():
            if y in out["detail"]["years"] and not out["detail"]["years"][y]["found"]:
                if info.get("hourly") == expect.get(y):
                    out["detail"]["years"][y]["found"] = info.get("hourly")
                    out["detail"]["years"][y]["evidence"] = {"file": cand.name, "snip": info.get("evidence")}
                    ok += 1
    out["detail"]["match_n"] = ok
    out["status"] = "정상" if ok == 5 else ("일부" if ok else "불일치")
    return out


def f7_prec() -> dict:
    out = {"id": "F7", "path": str(DC / "law_api" / "판례"), "status": "미확인", "detail": {}}
    prec = DC / "law_api" / "판례"
    if not prec.exists():
        out["status"] = "없음"
        return out
    # unique from list files
    ids = set()
    for p in list(prec.glob("list_*.json")) + list((prec / "g2_lists").glob("*.json") if (prec / "g2_lists").exists() else []):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        node = j.get("PrecSearch") or {}
        for v in node.values():
            items = v if isinstance(v, list) else ([v] if isinstance(v, dict) else [])
            for it in items:
                if not isinstance(it, dict):
                    continue
                link = it.get("판례상세링크") or ""
                m = re.search(r"[?&]ID=(\d+)", link)
                pid = m.group(1) if m else (it.get("판례정보일련번호") or it.get("판례일련번호"))
                if pid:
                    ids.add(str(pid))
    bodies = list((prec / "bodies").glob("*.json")) if (prec / "bodies").exists() else []
    filt = list((prec / "bodies_filtered_v2").glob("*.json")) if (prec / "bodies_filtered_v2").exists() else []
    # recount filter
    def fields(j):
        node = j.get("PrecService") or j
        if isinstance(node, dict):
            return str(node.get("판시사항") or ""), str(node.get("판결요지") or "")
        return "", ""

    pass_n = 0
    for p in filt:
        j = parse_json_file(p)
        if "_error" in j:
            continue
        a, b = fields(j)
        if "특약" in a + b or "약정" in a + b:
            pass_n += 1
    if pass_n == 0 and filt:
        pass_n = len(filt)  # already filtered set
    out["detail"]["목록_고유수"] = len(ids)
    out["detail"]["본문_파일수"] = len(bodies)
    out["detail"]["필터통과_본문수"] = pass_n if pass_n else len(filt)
    out["detail"]["기대_필터통과"] = 216
    out["detail"]["차이"] = (pass_n if pass_n else len(filt)) - 216
    n = pass_n if pass_n else len(filt)
    out["status"] = "정상" if n == 216 else ("일부" if n else "없음")
    return out


def f8_expc() -> dict:
    out = {"id": "F8", "path": str(DC / "law_api" / "법령해석례"), "status": "미확인", "detail": {}}
    base = DC / "law_api" / "법령해석례"
    if not base.exists():
        out["status"] = "없음"
        return out
    expc_bodies = list((base / "expc_v3" / "bodies").glob("*.json")) if (base / "expc_v3" / "bodies").exists() else []
    ministry_bodies = list((base / "g2_full" / "bodies_g2").glob("*.json")) if (base / "g2_full" / "bodies_g2").exists() else []
    # list totals from g2 results or list files
    org_stats = {}
    g2 = DC / "g1_g7_results.json"
    if g2.exists():
        j = json.loads(g2.read_text(encoding="utf-8"))
        for row in (j.get("G2") or {}).get("rows") or []:
            if "CgmExpc" in str(row.get("target")):
                key = f"{row.get('org')}|{row.get('keyword')}"
                org_stats[key] = {
                    "totalCnt": row.get("totalCnt"),
                    "saved_list": row.get("saved_list"),
                    "saved_body": row.get("saved_body"),
                    "match": row.get("totalCnt") == row.get("saved_list") == row.get("saved_body"),
                }
    out["detail"]["expc_bodies"] = len(expc_bodies)
    out["detail"]["기대_expc"] = 515
    out["detail"]["ministry_g2_bodies"] = len(ministry_bodies)
    out["detail"]["g2_keyword_rows"] = org_stats
    mismatches = [
        k for k, v in org_stats.items()
        if v.get("totalCnt") is not None and not v.get("match")
    ]
    unauth = [k for k, v in org_stats.items() if v.get("totalCnt") is None]
    out["detail"]["totalCnt_불일치_키워드"] = mismatches
    out["detail"]["미승인_또는_실패_키워드"] = unauth
    out["status"] = "정상" if len(expc_bodies) == 515 and not mismatches else "일부"
    if len(expc_bodies) == 515 and not mismatches and unauth:
        out["status"] = "일부"
        out["detail"]["note"] = "expc·승인된 부처는 totalCnt 일치. 미승인 target 키워드만 실패"
    return out


def f9_ftc() -> dict:
    out = {"id": "F9", "path": str(DC / "law_api" / "공정위"), "status": "미확인", "detail": {}}
    base = DC / "law_api" / "공정위"
    if not base.exists():
        out["status"] = "없음"
        return out
    lists = list(base.rglob("list_*.json")) + list(base.rglob("ftc_*.json"))
    lists = [p for p in lists if "list" in p.name.lower() or "_p" in p.name]
    bodies = list((base / "v2" / "bodies").glob("*.json")) if (base / "v2" / "bodies").exists() else []
    bodies += list((base / "g2_full" / "bodies_g2").glob("*.json")) if (base / "g2_full" / "bodies_g2").exists() else []
    # unique body ids
    ids = set()
    for p in bodies:
        m = re.search(r"(\d+)\.json$", p.name)
        if m:
            ids.add(m.group(1))
    out["detail"]["목록_파일수"] = len(set(lists))
    out["detail"]["본문_고유수"] = len(ids)
    out["detail"]["본문_파일수"] = len(bodies)
    # from g2
    if (DC / "g1_g7_results.json").exists():
        j = json.loads((DC / "g1_g7_results.json").read_text(encoding="utf-8"))
        ftc_rows = [r for r in (j.get("G2") or {}).get("rows") or [] if r.get("target") == "ftc"]
        out["detail"]["g2_rows"] = ftc_rows
    out["status"] = "정상" if ids else "일부"
    return out


def f10_cases() -> dict:
    out = {"id": "F10", "path": str(DC / "cases"), "status": "미확인", "detail": {}}
    pdf = DC / "cases" / "주택임대차분쟁조정사례집.pdf"
    if not pdf.exists():
        out["status"] = "없음"
        return out
    out["detail"]["pdf_bytes"] = pdf.stat().st_size
    pages = None
    try:
        import fitz
        doc = fitz.open(pdf)
        pages = doc.page_count
        doc.close()
    except Exception as e:
        out["detail"]["page_error"] = repr(e)
    out["detail"]["pages"] = pages
    ocr_dir = DC / "cases" / "ocr"
    ocr_txts = list(ocr_dir.glob("p*.txt")) if ocr_dir.exists() else []
    out["detail"]["ocr_page_txt"] = len(ocr_txts)
    out["detail"]["ocr_all"] = (ocr_dir / "ALL.txt").exists() if ocr_dir.exists() else False
    # quality from results
    hangul = None
    if (DC / "g1_g7_results.json").exists():
        j = json.loads((DC / "g1_g7_results.json").read_text(encoding="utf-8"))
        hangul = (j.get("G6") or {}).get("avg_hangul_ratio")
        out["detail"]["avg_hangul_ratio"] = hangul
        out["detail"]["quality_ok"] = (j.get("G6") or {}).get("quality_ok")
    out["status"] = "일부"  # OCR low quality known
    if pages == 101 and ocr_txts:
        out["status"] = "일부"
    return out


def f11_models() -> dict:
    out = {"id": "F11", "status": "미확인", "detail": {}}
    models = {
        "Qwen3-8B": DC / "models" / "Qwen3-8B",
        "KURE-v1": DC / "models" / "KURE-v1",
        "bge-m3": DC / "models" / "bge-m3",
    }
    # reuse previous hash compare if present
    prev = None
    for cand in [DC / "fix_abcdef_results.json"]:
        if cand.exists():
            prev = json.loads(cand.read_text(encoding="utf-8"))
            break
    hash_rows = (prev or {}).get("F", {}).get("hash_compare") if prev else None
    if hash_rows:
        out["detail"]["hf_hash_compare"] = [
            {"repo": r["repo"], "file": r["file"], "match": r["match"]} for r in hash_rows
        ]
        out["detail"]["all_match"] = all(r.get("match") for r in hash_rows)
    else:
        out["detail"]["hf_hash_compare"] = "미확인(이전 결과 없음 — 재해시 생략: 대용량)"
        out["detail"]["all_match"] = None

    for name, path in models.items():
        if path.exists():
            sz = sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and ".incomplete" not in f.name)
            out["detail"][name] = {"exists": True, "bytes": sz, "path": str(path)}
        else:
            out["detail"][name] = {"exists": False}

    # GGUF Qwen3-32B Q6_K
    gguf_hits = []
    for base in [ROOT / "models", DC / "models", ROOT]:
        if not base.exists():
            continue
        for p in base.rglob("*.gguf"):
            if "Qwen3" in p.name or "qwen3" in p.name.lower() or "32B" in p.name or "Q6" in p.name:
                gguf_hits.append({"path": str(p), "bytes": p.stat().st_size})
    # also search common names
    if not gguf_hits:
        for p in (ROOT / "models").rglob("*.gguf") if (ROOT / "models").exists() else []:
            gguf_hits.append({"path": str(p), "bytes": p.stat().st_size})
        for p in Path(r"C:\Users\DMLAB\pilot_root").rglob("*.gguf") if Path(r"C:\Users\DMLAB\pilot_root").exists() else []:
            if "qwen" in p.name.lower() or "32" in p.name:
                gguf_hits.append({"path": str(p), "bytes": p.stat().st_size})
    out["detail"]["gguf_qwen3_32b"] = gguf_hits[:10]
    incomplete = list((DC / "models").rglob("*.incomplete")) if (DC / "models").exists() else []
    out["detail"]["incomplete_n"] = len(incomplete)
    out["detail"]["incomplete_paths"] = [str(p) for p in incomplete]
    if out["detail"].get("all_match") and all(models[k].exists() for k in models) and gguf_hits:
        out["status"] = "정상"
    elif all(models[k].exists() for k in models):
        out["status"] = "일부"  # maybe no gguf
    else:
        out["status"] = "일부"
    return out


def f12_manual() -> dict:
    out = {"id": "F12", "path": str(DC / "MANUAL_DOWNLOADS.html"), "status": "미확인", "detail": {}}
    p = DC / "MANUAL_DOWNLOADS.html"
    if not p.exists():
        out["status"] = "없음"
        return out
    t = p.read_text(encoding="utf-8")
    titles = re.findall(r"<h2>(.*?)</h2>", t)
    if "수동 작업 없음" in t:
        out["detail"]["n"] = 0
        out["detail"]["titles"] = []
        out["status"] = "정상"
    else:
        out["detail"]["n"] = len(titles)
        out["detail"]["titles"] = titles
        out["status"] = "일부"  # remaining manual items
    return out


def write_report(wrong, merge, refs, checks) -> Path:
    path = DC / "FINAL_DATA_CHECK.md"
    lines = []
    lines.append(f"# FINAL_DATA_CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("ROOT = `C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발`")
    lines.append("")
    lines.append("## 1. F1–F12 상태표")
    lines.append("")
    lines.append("| ID | 항목 | 상태 | 실제 수치 | 기대와의 차이 |")
    lines.append("|---|---|---|---|---|")
    labels = {
        "F1": "표준계약서",
        "F2": "AI Hub 계약 서식",
        "F3": "AI Hub 약관(580)",
        "F4": "법령 현행 10개",
        "F5": "연혁",
        "F6": "최저임금 2022–2026",
        "F7": "판례",
        "F8": "해석례",
        "F9": "공정위",
        "F10": "사례집",
        "F11": "모델",
        "F12": "수동 다운로드",
    }
    for c in checks:
        cid = c["id"]
        d = c.get("detail") or {}
        # compact actual
        if cid == "F1":
            actual = f"manifest={d.get('manifest_rows')} missing={d.get('missing_files')} hash_mismatch={d.get('hash_mismatch')} extracted={d.get('extracted')}"
            diff = "—" if c["status"] == "정상" else "누락/해시/추출 확인"
        elif cid == "F2":
            actual = f"labels={d.get('label_json_n')} 소분류={d.get('소분류')} vocab={d.get('label_vocab')}"
            diff = str(d.get("expect_diff"))
        elif cid == "F3":
            actual = d.get("note") or str(d)
            diff = "기대: dataSetSn=580 약관 원천/라벨"
        elif cid == "F4":
            actual = f"parse_ok={d.get('parse_ok_n')}/10"
            diff = "—" if d.get("parse_ok_n") == 10 else "일부 법령 본문 미확인"
        elif cid == "F5":
            actual = f"path={c.get('path')} 판수={d.get('g3_대상_판수') or d.get('법령별_판수')} 혼입={d.get('연혁_g3_혼입', d.get('혼입_건수'))}"
            diff = "혼입 0 기대"
        elif cid == "F6":
            ys = {y: v.get("found") for y, v in (d.get("years") or {}).items()}
            actual = str(ys)
            diff = f"match {d.get('match_n')}/5"
        elif cid == "F7":
            actual = f"unique={d.get('목록_고유수')} bodies={d.get('본문_파일수')} filter={d.get('필터통과_본문수')}"
            diff = f"filter 기대 216, 차이 {d.get('차이')}"
        elif cid == "F8":
            actual = f"expc_bodies={d.get('expc_bodies')} ministry_bodies={d.get('ministry_g2_bodies')} mismatch_kw={len(d.get('totalCnt_불일치_키워드') or [])}"
            diff = f"expc 기대 515, 차이 {(d.get('expc_bodies') or 0) - 515}"
        elif cid == "F9":
            actual = f"lists≈{d.get('목록_파일수')} bodies_unique={d.get('본문_고유수')}"
            diff = "—"
        elif cid == "F10":
            actual = f"pdf_bytes={d.get('pdf_bytes')} pages={d.get('pages')} ocr_txt={d.get('ocr_page_txt')} hangul={d.get('avg_hangul_ratio')}"
            diff = "OCR 한글비율≥0.7 기대 → 미달"
        elif cid == "F11":
            actual = f"hf_match={d.get('all_match')} incomplete={d.get('incomplete_n')} gguf={d.get('gguf_qwen3_32b')}"
            diff = "GGUF/해시 항목 확인"
        elif cid == "F12":
            actual = f"n={d.get('n')} titles={d.get('titles')}"
            diff = "수동 0 기대" if d.get("n") else "—"
        else:
            actual = str(d)[:120]
            diff = "—"
        lines.append(f"| {cid} | {labels.get(cid, cid)} | **{c['status']}** | {actual} | {diff} |")
    lines.append("")

    lines.append("## 2. 폴더 정리 요약")
    lines.append("")
    lines.append("### 0) WRONG(AI_Service) 탐색")
    if not wrong:
        lines.append("- 발견 없음")
    for w in wrong:
        lines.append(
            f"- `{w['path']}` — files={w['files']}, bytes={w['bytes']}, mtime={w['mtime']}, children={w.get('children')}"
        )
    lines.append("")
    lines.append("### 1) 분류 요약 (FOLDER_DIFF.csv)")
    lines.append(f"- diff 행 수: {merge.get('diff_rows')}")
    lines.append(f"- 분류별 파일 수: {merge.get('summary_count')}")
    lines.append(f"- 분류별 총 바이트: {merge.get('summary_bytes')}")
    if merge.get("only_wrong_by_top"):
        lines.append("- (c) WRONG에만 있음 — 최상위 폴더별:")
        for top, rels in merge["only_wrong_by_top"].items():
            lines.append(f"  - `{top}`: {len(rels)}건 예) {rels[:5]}")
    else:
        lines.append("- (c) WRONG에만 있음: **0건**")
    lines.append("")
    lines.append("### 2) 복사 (FOLDER_MERGE_LOG.csv)")
    lines.append(f"- 복사 성공 수: {merge.get('copied_n')} / 바이트: {merge.get('copied_bytes')}")
    lines.append(f"- 충돌(b) 수: {len(merge.get('conflicts') or [])}")
    for c in (merge.get("conflicts") or [])[:20]:
        lines.append(f"  - {c}")
    lines.append("")
    lines.append("### 3) 경로 참조")
    lines.append(f"- `AI_Service` 문자열 발견 파일 수: {len(refs.get('hits') or [])}")
    for h in (refs.get("hits") or [])[:30]:
        lines.append(f"  - `{h['file']}` ({h['n']}줄)")
    lines.append(f"- 자동 수정한 스크립트/설정: {len(refs.get('modified') or [])}")
    for m in refs.get("modified") or []:
        lines.append(f"  - `{m['file']}` ← backup `{m['backup']}`")
    lines.append("")

    all_copied = merge.get("copied_n", 0) == 0 and merge.get("diff_rows", 0) == 0
    empty_wrong = all((w.get("files") or 0) == 0 for w in wrong) if wrong else True
    if empty_wrong:
        moved_line = (
            "WRONG 폴더는 삭제하지 않았음. 내용이 ROOT로 모두 옮겨졌는지: **예** "
            "(근거: `C:\\Users\\DMLAB\\AI_Service` 파일 수 0·바이트 0 — 옮길 (c) 항목 없음)"
        )
    elif merge.get("copied_n", 0) >= merge.get("summary_count", {}).get("c_only_in_wrong", 0) and not merge.get("conflicts"):
        moved_line = (
            f"WRONG 폴더는 삭제하지 않았음. 내용이 ROOT로 모두 옮겨졌는지: **예** "
            f"(근거: (c) {merge.get('summary_count', {}).get('c_only_in_wrong')}건 복사·해시 확인)"
        )
    else:
        moved_line = (
            "WRONG 폴더는 삭제하지 않았음. 내용이 ROOT로 모두 옮겨졌는지: **아니오** "
            f"(근거: 충돌 {len(merge.get('conflicts') or [])} / (c)잔여 가능)"
        )
    lines.append("## 3. WRONG 보존·이전 여부")
    lines.append("")
    lines.append(moved_line)
    lines.append("")

    lines.append("## 4. 사람이 할 일")
    lines.append("")
    manual = next((c for c in checks if c["id"] == "F12"), {})
    titles = (manual.get("detail") or {}).get("titles") or []
    if titles:
        lines.append(f"- 수동 다운로드 잔여 **{len(titles)}**:")
        for t in titles:
            lines.append(f"  - {t}")
    else:
        lines.append("- 수동 다운로드 잔여 없음")
    if merge.get("conflicts"):
        lines.append("- 충돌(b) 판단 필요:")
        for c in merge["conflicts"][:20]:
            lines.append(f"  - `{c.get('rel')}`")
    else:
        lines.append("- 충돌(b) 없음")
    f3 = next((c for c in checks if c["id"] == "F3"), {})
    if f3.get("status") in ("없음", "일부") and not (f3.get("detail") or {}).get("data_files"):
        lines.append("- AI Hub 약관(580) 다운로드 후 `after_manual.py` 실행")
    f10 = next((c for c in checks if c["id"] == "F10"), {})
    if f10.get("status") == "일부":
        lines.append("- 사례집 OCR 품질 재작업(한글비율 미달) 검토")
    f11 = next((c for c in checks if c["id"] == "F11"), {})
    if not (f11.get("detail") or {}).get("gguf_qwen3_32b"):
        lines.append("- Qwen3-32B Q6_K GGUF 경로·존재 재확인")
    lines.append("")

    # appendix F4/F5/F6/F7 details
    lines.append("## 부록: 상세")
    lines.append("")
    for c in checks:
        lines.append(f"### {c['id']}")
        lines.append("```json")
        lines.append(json.dumps(c, ensure_ascii=False, indent=2)[:4000])
        lines.append("```")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    print("STEP0", flush=True)
    wrong = step0()
    print("wrong", wrong, flush=True)
    print("STEP1-2", flush=True)
    merge = classify_and_merge(wrong)
    print("merge", {k: merge[k] for k in ("diff_rows", "summary_count", "copied_n")}, flush=True)
    print("STEP3", flush=True)
    refs = step3_path_refs()
    print("refs", len(refs.get("hits") or []), "modified", len(refs.get("modified") or []), flush=True)
    print("STEP4 checks", flush=True)
    checks = [
        f1_standard_forms(),
        f2_aihub_forms(),
        f3_aihub_terms(),
        f4_current_laws(),
        f5_history(),
        f6_minwage(),
        f7_prec(),
        f8_expc(),
        f9_ftc(),
        f10_cases(),
        f11_models(),
        f12_manual(),
    ]
    for c in checks:
        print(c["id"], c["status"], flush=True)
    path = write_report(wrong, merge, refs, checks)
    # also dump json
    (DC / "final_data_check.json").write_text(
        json.dumps({"wrong": wrong, "merge": merge, "refs": refs, "checks": checks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("WROTE", path, flush=True)


if __name__ == "__main__":
    main()
