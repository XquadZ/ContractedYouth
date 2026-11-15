# -*- coding: utf-8 -*-
"""2단계: AIHub 판결서·약관 zip 안정화 대기 후 약관만 해제·검증."""
from __future__ import annotations

import json
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
OUT = DC / "aihub_terms"
REPORT = DC / "s2_results.json"

NEEDLES = ["약관", "판결", "텍스트", "법률규정", "판결서", "Terms", "prec", "580"]


def find_candidate_zips() -> list[Path]:
    bases = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        ROOT,
        ROOT / "data_contract",
        Path.home() / "Documents",
        Path(os_localappdata()) / "Temp" if os_localappdata() else None,
    ]
    hits = []
    for base in bases:
        if not base or not Path(base).exists():
            continue
        try:
            for p in Path(base).rglob("*.zip"):
                name = p.name
                # growing downloads often have partial names; include large recent zips with keywords
                try:
                    st = p.stat()
                except Exception:
                    continue
                age_h = (time.time() - st.st_mtime) / 3600
                if age_h > 72 and st.st_size < 50_000_000:
                    continue
                if any(n.lower() in name.lower() for n in NEEDLES) or (
                    age_h < 6 and st.st_size > 20_000_000 and "cuda" not in name.lower() and "llama" not in name.lower()
                ):
                    hits.append(p)
        except Exception:
            continue
    # dedupe
    uniq = {}
    for p in hits:
        uniq[str(p.resolve())] = p
    return list(uniq.values())


def os_localappdata():
    import os
    return os.environ.get("LOCALAPPDATA", "")


def sizes(paths: list[Path]) -> dict:
    out = {}
    for p in paths:
        try:
            out[str(p)] = p.stat().st_size
        except Exception:
            out[str(p)] = -1
    return out


def wait_stable(paths: list[Path], rounds=4, interval=20) -> tuple[list[Path], dict]:
    """Return paths that stayed same size for `rounds` checks."""
    if not paths:
        return [], {}
    hist = []
    for i in range(rounds):
        hist.append(sizes(paths))
        time.sleep(interval)
    stable = []
    last = hist[-1]
    for p in paths:
        key = str(p)
        series = [h.get(key, -1) for h in hist]
        if len(set(series)) == 1 and series[0] > 0:
            stable.append(p)
    return stable, {"size_history": hist, "stable": [str(p) for p in stable]}


def looks_like_terms(name: str, namelist: list[str]) -> bool:
    blob = name + " " + " ".join(namelist[:50])
    return any(k in blob for k in ("약관", "terms", "clause", "dvAntageous", "clauseField"))


def looks_like_judgment(name: str, namelist: list[str]) -> bool:
    blob = name + " " + " ".join(namelist[:50])
    return any(k in blob for k in ("판결", "판결서", "precedent", "판결문"))


def analyze_terms(extract_root: Path) -> dict:
    jsons = list(extract_root.rglob("*.json"))
    fields_present = Counter()
    clause_field = Counter()
    lease_adv = {"유리": 0, "불리": 0, "other": 0}
    samples_bad = []
    samples_good = []
    field_names_wanted = [
        "clauseField", "dvAntageous", "ftcCnclsns", "unfavorableProvision",
        "illdcssBasiss", "relateLaword", "clauseArticle",
    ]
    for p in jsons:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            try:
                obj = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
        # flatten keys
        def walk(o, prefix=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    fields_present[k] += 1
                    if k == "clauseField":
                        clause_field[str(v)] += 1
                    if k == "dvAntageous":
                        pass
                    walk(v, prefix + k + ".")
            elif isinstance(o, list):
                for it in o[:5]:
                    walk(it, prefix)

        walk(obj)
        # get values
        def find(o, key):
            if isinstance(o, dict):
                if key in o:
                    return o[key]
                for v in o.values():
                    r = find(v, key)
                    if r is not None:
                        return r
            elif isinstance(o, list):
                for it in o:
                    r = find(it, key)
                    if r is not None:
                        return r
            return None

        cf = str(find(obj, "clauseField") or "")
        adv = str(find(obj, "dvAntageous") or "")
        if any(k in cf for k in ("임대차", "입주")):
            if adv in ("1", "유리"):
                lease_adv["유리"] += 1
                if len(samples_good) < 5:
                    samples_good.append(extract_sample(obj, p))
            elif adv in ("2", "불리"):
                lease_adv["불리"] += 1
                if len(samples_bad) < 5:
                    samples_bad.append(extract_sample(obj, p))
            else:
                lease_adv["other"] += 1

    present = {k: (fields_present.get(k, 0) > 0) for k in field_names_wanted}
    return {
        "n_json": len(jsons),
        "fields_present": present,
        "field_counts_top": fields_present.most_common(30),
        "clauseField_counts": clause_field.most_common(),
        "lease_related_advantage": lease_adv,
        "samples_불리": samples_bad,
        "samples_유리": samples_good,
    }


def extract_sample(obj, path: Path) -> dict:
    def find(o, key):
        if isinstance(o, dict):
            if key in o:
                return o[key]
            for v in o.values():
                r = find(v, key)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for it in o:
                r = find(it, key)
                if r is not None:
                    return r
        return None

    article = find(obj, "clauseArticle")
    text = ""
    if isinstance(article, list):
        text = "\n".join(str(x) for x in article)[:800]
    elif isinstance(article, str):
        text = article[:800]
    else:
        # fallback any long string
        text = str(obj)[:500]
    return {
        "path": str(path),
        "clauseField": find(obj, "clauseField"),
        "dvAntageous": find(obj, "dvAntageous"),
        "illdcssBasiss": find(obj, "illdcssBasiss"),
        "relateLaword": find(obj, "relateLaword"),
        "unfavorableProvision": find(obj, "unfavorableProvision"),
        "clause_text": text,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cands = find_candidate_zips()
    result = {
        "status": None,
        "candidates_found": [{"path": str(p), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime} for p in cands],
        "aihub_page": "https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&dataSetSn=580&topMenu=100",
    }
    if not cands:
        result["status"] = "대기 중"
        result["note"] = "ROOT/Downloads/Desktop 등에서 판결서·약관 관련 zip 미발견(또는 아직 생성 전). 다운로드 완료 후 재실행."
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "WAITING.txt").write_text(result["note"] + "\n", encoding="utf-8")
        print("WAITING no candidates")
        return

    # filter to keyword-ish preferentially
    prefer = [p for p in cands if any(n in p.name for n in ("약관", "판결", "텍스트", "법률"))]
    watch = prefer or cands
    stable, meta = wait_stable(watch, rounds=3, interval=15)
    result["stability"] = meta
    if not stable:
        result["status"] = "대기 중"
        result["note"] = "후보 zip 크기 변화 중(다운로드 진행으로 판단). 크기 안정화 후 재실행."
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("WAITING unstable")
        return

    # classify judgment vs terms; extract only terms
    extracted = []
    judgment_only = []
    for z in stable:
        try:
            with zipfile.ZipFile(z, "r") as zf:
                names = zf.namelist()
        except Exception as e:
            result.setdefault("zip_errors", []).append({"path": str(z), "error": repr(e)})
            continue
        if looks_like_judgment(z.name, names) and not looks_like_terms(z.name, names):
            judgment_only.append({"path": str(z), "bytes": z.stat().st_size, "n_entries": len(names)})
            continue
        if looks_like_terms(z.name, names) or "약관" in z.name:
            dest = OUT / z.stem
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(dest)
            extracted.append({"zip": str(z), "dest": str(dest), "bytes": z.stat().st_size, "n_entries": len(names)})
        else:
            # ambiguous large zip: record only
            result.setdefault("ambiguous_zips", []).append({"path": str(z), "bytes": z.stat().st_size})

    result["judgment_zips_not_extracted"] = judgment_only
    result["terms_extracted"] = extracted
    if not extracted:
        result["status"] = "대기 중" if not judgment_only else "일부"
        result["note"] = "안정 zip은 있으나 약관으로 분류된 압축이 없음. 판결서만 있으면 해제하지 않음(요구사항)."
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("no terms extracted")
        return

    analysis = analyze_terms(OUT)
    result["analysis"] = analysis
    result["status"] = "있음"
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE terms", len(extracted), "json", analysis.get("n_json"))


if __name__ == "__main__":
    main()
