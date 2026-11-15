# -*- coding: utf-8 -*-
"""G1~G7 데이터 수집 마무리. OC/토큰 미출력. 성공=기대 JSON 구조."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
LAW = DC / "law_api"
OUT = DC / "g1_g7_results.json"
SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"
NOW = datetime.now().strftime("%Y%m%d%H%M")

EXPC_KW = ["근로계약", "최저임금", "주휴", "수습", "임대차", "보증금", "이자"]
LSTRM_KW = ["근로계약", "임대차", "보증금", "위약금", "최저임금", "차용", "이자", "수습", "주휴", "약관", "특약", "원상복구"]
FTC_KW = ["임대차 약관", "임대차계약서"]
PREC_KW = [
    "임대차 특약 무효", "원상복구 특약", "임대차 위약금", "보증금 반환 특약", "계약갱신요구권 포기",
    "근로계약 위약금", "위약예정", "임금 공제", "수습기간 임금", "주휴수당", "휴게시간",
    "이자제한법 초과", "보증 서면", "차용증",
]
MINISTRY = {
    "고용노동부": "moelCgmExpc",
    "국토교통부": "molitCgmExpc",
    "법제처": "molegCgmExpc",
    "법무부": "mojCgmExpc",
}
# 이전에 미승인/권한없음이었던 target
PROBE_TARGETS = [
    ("expc", SEARCH, {"type": "JSON", "query": "근로계약", "display": 5, "search": 2}),
    ("lstrm", SEARCH, {"type": "JSON", "query": "근로", "display": 5}),
    ("mojCgmExpc", SEARCH, {"type": "JSON", "query": "근로", "display": 3, "search": 2}),
    ("cgmExpc", SEARCH, {"type": "JSON", "query": "근로", "display": 3, "search": 2}),
    ("ftc", SEARCH, {"type": "JSON", "query": "임대차 약관", "display": 3, "search": 2}),
    ("ftc_XML", SEARCH, {"type": "XML", "query": "임대차 약관", "display": 3, "search": 2}),
]

G3_LAWS = [
    "근로기준법",
    "근로기준법 시행령",
    "주택임대차보호법",
    "주택임대차보호법 시행령",
    "민법",
    "보증인 보호를 위한 특별법",
]

MANUAL_ITEMS: list[dict] = []


def oc() -> str:
    v = os.environ.get("LAW_OC", "").strip()
    if v:
        return v
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
        v, _ = winreg.QueryValueEx(k, "LAW_OC")
        return str(v).strip()


def redact(t: str) -> str:
    t = re.sub(r"OC=[^&\s\"']+", "OC=REDACTED", t or "")
    t = re.sub(r'("OC"\s*:\s*")[^"]+(")', r"\1REDACTED\2", t)
    return t


def archive_if_exists(path: Path):
    if path.exists() and path.is_file():
        bak = path.with_name(path.stem + f"_old_{NOW}" + path.suffix)
        if not bak.exists():
            shutil.copy2(path, bak)


def save(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        archive_if_exists(path)
    path.write_text(redact(text), encoding="utf-8")


def http_get(params: dict, base: str = SEARCH) -> str:
    q = urllib.parse.urlencode(params)
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    t = raw.decode(enc)
                    break
                except Exception:
                    t = raw.decode("utf-8", "replace")
            time.sleep(0.65)
            return t
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"http_get failed: {last}")


def is_html(t: str) -> bool:
    h = t.lstrip()[:80].lower()
    return h.startswith("<!doctype") or h.startswith("<html") or "<html" in t[:300].lower()


def html_message(t: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", t, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]


def parse_json(t: str):
    try:
        return json.loads(t)
    except Exception:
        return None


def add_manual(item: dict):
    MANUAL_ITEMS.append(item)


# ---------- G1 ----------
def g1_probe(key: str) -> dict:
    results = {}
    for name, base, extra in PROBE_TARGETS:
        params = {"OC": key, "target": name.replace("_XML", ""), **extra}
        try:
            t = http_get(params, base)
        except Exception as e:
            results[name] = {"ok": False, "error": repr(e)}
            continue
        if is_html(t):
            msg = html_message(t)
            unauth = "미신청" in msg or "권한" in msg
            results[name] = {"ok": False, "unauthorized": unauth, "error_text": msg, "kind": "HTML"}
        else:
            j = parse_json(t) if params.get("type") == "JSON" else None
            if params.get("type") == "JSON":
                ok = isinstance(j, dict) and len(j) > 0
                results[name] = {
                    "ok": ok,
                    "kind": "JSON",
                    "keys": list(j.keys())[:8] if j else [],
                    "head": redact(t)[:200],
                }
            else:
                # XML
                ok = t.strip().startswith("<") and "미신청" not in html_message(t)
                results[name] = {"ok": ok, "kind": "XML", "head": redact(t)[:200]}
        print("G1 probe", name, results[name].get("ok"), results[name].get("kind"))
    return results


def collect_expc(key: str) -> dict:
    outd = LAW / "법령해석례" / "expc_v3"
    outd.mkdir(parents=True, exist_ok=True)
    ids = {}
    n_list = 0
    for kw in EXPC_KW:
        page = 1
        while page <= 50:
            t = http_get({
                "OC": key, "target": "expc", "type": "JSON", "query": kw,
                "search": 2, "display": 100, "page": page,
            })
            j = parse_json(t)
            if is_html(t) or not j:
                break
            # common containers
            node = j.get("Expc") or j.get("ExpcSearch") or j.get("LawSearch") or next(iter(j.values()), {})
            if not isinstance(node, dict):
                break
            save(outd / f"list_{kw}_p{page}.json", t)
            n_list += 1
            items = node.get("expc") or node.get("law") or []
            if isinstance(items, dict):
                items = [items]
            for it in items if isinstance(items, list) else []:
                eid = it.get("법령해석일련번호") or it.get("법령해석례일련번호")
                if not eid:
                    m = re.search(r"[?&]ID=(\d+)", it.get("법령해석상세링크") or "")
                    eid = m.group(1) if m else None
                if eid:
                    ids[str(eid)] = it
            total = int(node.get("totalCnt") or 0)
            if not items or page * 100 >= total or len(items) < 100:
                break
            page += 1
    n_body = 0
    sample = None
    for eid in ids:
        tb = http_get({"OC": key, "target": "expc", "type": "JSON", "ID": eid}, SERVICE)
        jb = parse_json(tb)
        if is_html(tb) or not jb:
            continue
        # accept any JSON service wrapper
        save(outd / "bodies" / f"{eid}.json", tb)
        n_body += 1
        if sample is None:
            sample = redact(tb)[:300]
        if n_body % 50 == 0:
            print("expc bodies", n_body, "/", len(ids))
    return {
        "list_responses": n_list,
        "unique_ids": len(ids),
        "bodies": n_body,
        "sample_head_300": sample,
        "success_criterion": "JSON list + JSON body",
    }


def collect_lstrm(key: str) -> dict:
    outd = LAW / "법령용어" / "lstrm_v3"
    outd.mkdir(parents=True, exist_ok=True)
    ids = {}
    n_list = 0
    for kw in LSTRM_KW:
        page = 1
        while page <= 20:
            t = http_get({
                "OC": key, "target": "lstrm", "type": "JSON", "query": kw,
                "display": 100, "page": page,
            })
            j = parse_json(t)
            if is_html(t) or not j:
                break
            node = j.get("Lstrm") or j.get("LstrmSearch") or j.get("LawSearch") or next(iter(j.values()), {})
            if not isinstance(node, dict):
                break
            save(outd / f"list_{kw}_p{page}.json", t)
            n_list += 1
            items = None
            for k, v in node.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break
                if isinstance(v, dict) and ("용어명" in v or "법령용어명" in v):
                    items = [v]
                    break
            items = items or []
            for it in items:
                tid = it.get("법령용어일련번호") or it.get("용어일련번호") or it.get("ID")
                if not tid:
                    m = re.search(r"[?&](?:ID|MST)=(\d+)", str(it))
                    tid = m.group(1) if m else None
                if tid:
                    ids[str(tid)] = it
            total = int(node.get("totalCnt") or node.get("검색결과개수") or 0)
            if not items or (total and page * 100 >= total) or len(items) < 100:
                break
            page += 1
    n_body = 0
    sample = None
    for tid in ids:
        for idk in ("ID", "MST"):
            tb = http_get({"OC": key, "target": "lstrm", "type": "JSON", idk: tid}, SERVICE)
            jb = parse_json(tb)
            if is_html(tb) or not jb:
                continue
            save(outd / "bodies" / f"{tid}.json", tb)
            n_body += 1
            if sample is None:
                sample = redact(tb)[:300]
            break
    return {
        "list_responses": n_list,
        "unique_ids": len(ids),
        "bodies": n_body,
        "sample_head_300": sample,
    }


def run_G1(key: str) -> dict:
    probe = g1_probe(key)
    sec = {"probe": probe, "expc_collect": None, "lstrm_collect": None}
    if probe.get("expc", {}).get("ok"):
        print("G1 collect expc...")
        sec["expc_collect"] = collect_expc(key)
    else:
        add_manual({
            "id": "g1_expc",
            "title": "법령해석례 API(expc) 승인 확인",
            "why": "3-5 법령해석례 자동 수집에 필요",
            "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
            "action": "open.law.go.kr 마이페이지에서 target=expc 승인 상태 확인·재신청",
            "dest": "승인 후 python data_contract\\scripts\\after_manual.py",
            "targets": ["expc"],
        })
    if probe.get("lstrm", {}).get("ok"):
        print("G1 collect lstrm...")
        sec["lstrm_collect"] = collect_lstrm(key)
    else:
        add_manual({
            "id": "g1_lstrm",
            "title": "법령용어 API(lstrm) 승인 확인",
            "why": "3-7 법령용어 자동 수집에 필요",
            "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
            "action": "open.law.go.kr 마이페이지에서 target=lstrm 승인 상태 확인·재신청",
            "dest": "승인 후 python data_contract\\scripts\\after_manual.py",
            "targets": ["lstrm"],
        })
    for name, info in probe.items():
        tgt = name.replace("_XML", "")
        if info.get("unauthorized") or (not info.get("ok") and info.get("kind") == "HTML" and "미신청" in (info.get("error_text") or "")):
            if tgt in ("expc", "lstrm"):
                continue  # already added
            add_manual({
                "id": f"g1_{tgt}",
                "title": f"Open API target={tgt} 승인 확인",
                "why": f"이전에 권한 없음이었던 target={tgt} 재승인 필요",
                "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
                "action": f"마이페이지에서 target={tgt} 승인 상태 확인",
                "dest": "승인만 확인하면 됨(수집은 after_manual에서 재시도)",
                "targets": [tgt],
            })
    return sec


# ---------- G2 ----------
def list_items_from_json(j: dict, *prefer_keys):
    if not j:
        return [], 0
    node = None
    for k in prefer_keys:
        if k in j and isinstance(j[k], dict):
            node = j[k]
            break
    if node is None:
        node = next((v for v in j.values() if isinstance(v, dict)), {})
    total = int(node.get("totalCnt") or 0)
    items = []
    for v in node.values():
        if isinstance(v, list):
            items.extend([x for x in v if isinstance(x, dict)])
        elif isinstance(v, dict) and any(x in v for x in ("안건명", "사건명", "법령명한글", "행정규칙명", "결정문일련번호", "판례정보일련번호")):
            items.append(v)
    return items, total


def paginate_collect(key, target, kw, out_prefix, id_fn, body_target=None, container_keys=(), max_pages=100, reuse_body_dirs=None):
    """Return totalCnt, list_n, body_n, ids. Fetches all list pages; bodies for each unique id."""
    ids = {}
    list_n = 0
    total_seen = 0
    page = 1
    body_target = body_target or target
    reuse_body_dirs = reuse_body_dirs or []
    while page <= max_pages:
        params = {"OC": key, "target": target, "type": "JSON", "query": kw, "display": 100, "page": page}
        if target.endswith("CgmExpc") or target == "expc":
            params["search"] = 2
        if target in ("ftc", "prec"):
            params["search"] = 2
        t = http_get(params)
        j = parse_json(t)
        if is_html(t) or not j:
            break
        save(Path(str(out_prefix) + f"_p{page}.json"), t)
        list_n += 1
        items, total = list_items_from_json(j, *container_keys) if container_keys else list_items_from_json(j)
        total_seen = max(total_seen, total)
        for it in items:
            eid = id_fn(it)
            if eid:
                ids[str(eid)] = it
        if not items or page * 100 >= (total or 0) or len(items) < 100:
            break
        page += 1
    body_n = 0
    bodies_dir = Path(str(out_prefix)).parent / "bodies_g2"
    bodies_dir.mkdir(parents=True, exist_ok=True)
    for eid in ids:
        dest = bodies_dir / f"{target}_{eid}.json"
        if dest.exists():
            body_n += 1
            continue
        reused = False
        for rd in reuse_body_dirs:
            for cand in Path(rd).glob(f"*{eid}.json"):
                shutil.copy2(cand, dest)
                body_n += 1
                reused = True
                break
            if reused:
                break
        if reused:
            continue
        tb = http_get({"OC": key, "target": body_target, "type": "JSON", "ID": eid}, SERVICE)
        if is_html(tb) or not parse_json(tb):
            continue
        save(dest, tb)
        body_n += 1
    return total_seen, len(ids), body_n, list_n


def id_from_link(it, *keys):
    for k in keys:
        if it.get(k) not in (None, ""):
            return str(it[k])
    for lk in ("법령해석상세링크", "판례상세링크", "결정문상세링크", "법령상세링크"):
        m = re.search(r"[?&](?:ID|MST)=(\d+)", it.get(lk) or "")
        if m:
            return m.group(1)
    return None


def _list_all_pages(key, target, kw, out_prefix, id_fn, container_keys=(), max_pages=100):
    """List-only pagination. Returns totalCnt, ids dict."""
    ids = {}
    total_seen = 0
    page = 1
    while page <= max_pages:
        params = {"OC": key, "target": target, "type": "JSON", "query": kw, "display": 100, "page": page}
        if target.endswith("CgmExpc") or target in ("expc", "ftc", "prec"):
            params["search"] = 2
        t = http_get(params)
        j = parse_json(t)
        if is_html(t) or not j:
            return total_seen, ids, html_message(t) if is_html(t) else "no json"
        save(Path(str(out_prefix) + f"_p{page}.json"), t)
        items, total = list_items_from_json(j, *container_keys) if container_keys else list_items_from_json(j)
        total_seen = max(total_seen, total)
        for it in items:
            eid = id_fn(it)
            if eid:
                ids[str(eid)] = it
        if not items or page * 100 >= (total or 0) or len(items) < 100:
            break
        page += 1
    return total_seen, ids, None


def _fetch_bodies(key, target, ids, bodies_dir: Path, reuse_dirs=None):
    reuse_dirs = reuse_dirs or []
    bodies_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    missing = []
    for eid in ids:
        dest = bodies_dir / f"{target}_{eid}.json"
        if dest.exists():
            n += 1
            continue
        reused = False
        for rd in reuse_dirs:
            for cand in Path(rd).glob(f"*{eid}.json"):
                shutil.copy2(cand, dest)
                n += 1
                reused = True
                break
            if reused:
                break
        if not reused:
            missing.append(eid)
    for i, eid in enumerate(missing):
        dest = bodies_dir / f"{target}_{eid}.json"
        tb = http_get({"OC": key, "target": target, "type": "JSON", "ID": eid}, SERVICE)
        if is_html(tb) or not parse_json(tb):
            continue
        save(dest, tb)
        n += 1
        if (i + 1) % 50 == 0:
            print("G2 bodies", target, i + 1, "/", len(missing), "ok", n)
    return n


def run_G2(key: str) -> dict:
    rows = []
    # --- ministry: list all keywords, then one body pass per target ---
    for org, tgt in MINISTRY.items():
        out_base = LAW / "법령해석례" / "g2_full"
        out_base.mkdir(parents=True, exist_ok=True)
        kw_meta = {}
        union_ids = {}

        def idfn(it):
            return id_from_link(it, "법령해석일련번호", "법령해석례일련번호")

        for kw in EXPC_KW:
            outp = out_base / f"{org}_{kw}"
            total, ids, err = _list_all_pages(key, tgt, kw, outp, idfn, container_keys=("CgmExpc", "Expc", "ExpcSearch"))
            if err and not ids:
                rows.append({"target": tgt, "org": org, "keyword": kw, "totalCnt": None, "saved_list": 0, "saved_body": 0, "error": err[:200]})
                continue
            kw_meta[kw] = {"totalCnt": total, "ids": set(ids)}
            union_ids.update(ids)
            print("G2 list", tgt, kw, "total", total, "ids", len(ids))
        bodies_dir = out_base / "bodies_g2"
        reuse = [LAW / "법령해석례" / "ministry_v2" / "bodies", bodies_dir]
        body_n_union = _fetch_bodies(key, tgt, union_ids, bodies_dir, reuse) if union_ids else 0
        for kw, meta in kw_meta.items():
            n_body = sum(1 for eid in meta["ids"] if (bodies_dir / f"{tgt}_{eid}.json").exists())
            rows.append({
                "target": tgt, "org": org, "keyword": kw,
                "totalCnt": meta["totalCnt"], "saved_list": len(meta["ids"]),
                "saved_body": n_body, "union_bodies_target": body_n_union,
            })

    # --- FTC ---
    ftc_base = LAW / "공정위" / "g2_full"
    ftc_base.mkdir(parents=True, exist_ok=True)
    ftc_union = {}
    ftc_meta = {}

    def ftc_id(it):
        return id_from_link(it, "결정문일련번호")

    for kw in FTC_KW:
        outp = ftc_base / f"ftc_{kw.replace(' ', '_')}"
        total, ids, err = _list_all_pages(key, "ftc", kw, outp, ftc_id, container_keys=("Ftc",))
        if err and not ids:
            rows.append({"target": "ftc", "keyword": kw, "totalCnt": None, "error": err[:200]})
            continue
        ftc_meta[kw] = {"totalCnt": total, "ids": set(ids)}
        ftc_union.update(ids)
    ftc_bodies = ftc_base / "bodies_g2"
    reuse_ftc = [LAW / "공정위" / "v2" / "bodies", ftc_bodies]
    _fetch_bodies(key, "ftc", ftc_union, ftc_bodies, reuse_ftc)
    for kw, meta in ftc_meta.items():
        n_body = sum(1 for eid in meta["ids"] if (ftc_bodies / f"ftc_{eid}.json").exists())
        rows.append({"target": "ftc", "keyword": kw, "totalCnt": meta["totalCnt"], "saved_list": len(meta["ids"]), "saved_body": n_body})

    # --- prec: list all + fill missing bodies once ---
    prec_union = {}
    prec_meta = {}
    bodies_dir = LAW / "판례" / "bodies"

    def prec_id(it):
        link = it.get("판례상세링크") or ""
        m = re.search(r"[?&]ID=(\d+)", link)
        if m:
            return m.group(1)
        return it.get("판례정보일련번호") or it.get("판례일련번호")

    for kw in PREC_KW:
        outp = LAW / "판례" / "g2_lists" / f"prec_{kw.replace(' ', '_')}"
        outp.parent.mkdir(parents=True, exist_ok=True)
        total, ids, err = _list_all_pages(key, "prec", kw, outp, prec_id, container_keys=("PrecSearch",))
        if err and not ids:
            rows.append({"target": "prec", "keyword": kw, "totalCnt": None, "error": err[:200]})
            continue
        prec_meta[kw] = {"totalCnt": total, "ids": set(ids)}
        prec_union.update(ids)
        print("G2 prec list", kw, total, len(ids))
    # fetch missing into bodies/
    missing = [pid for pid in prec_union if not (bodies_dir / f"{pid}.json").exists()]
    for i, pid in enumerate(missing):
        tb = http_get({"OC": key, "target": "prec", "type": "JSON", "ID": pid}, SERVICE)
        if is_html(tb) or not parse_json(tb):
            continue
        save(bodies_dir / f"{pid}.json", tb)
        if (i + 1) % 50 == 0:
            print("G2 prec bodies", i + 1, "/", len(missing))
    for kw, meta in prec_meta.items():
        n_body = sum(1 for pid in meta["ids"] if (bodies_dir / f"{pid}.json").exists())
        rows.append({"target": "prec", "keyword": kw, "totalCnt": meta["totalCnt"], "saved_list": len(meta["ids"]), "saved_body": n_body})

    return {"rows": rows}


# ---------- G3 ----------
def parse_ls_history_html(html: str, expected_name: str) -> dict:
    """Best-effort extract article texts from lsHistory HTML."""
    text = html
    # strip scripts
    text_plain = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    articles = []
    # common patterns: 제N조
    for m in re.finditer(r"(제\s*\d+\s*조(?:의\s*\d+)?)\s*[\(（]?([^\)）<\n]{0,80})[\)）]?\s*", text_plain):
        articles.append({"조문번호": re.sub(r"\s+", "", m.group(1)), "제목": m.group(2).strip()})
    # get body chunks
    chunks = {}
    parts = re.split(r"(제\s*\d+\s*조(?:의\s*\d+)?)", text_plain)
    i = 1
    while i < len(parts) - 1:
        num = re.sub(r"\s+", "", parts[i])
        body = re.sub(r"<[^>]+>", " ", parts[i + 1])
        body = re.sub(r"\s+", " ", body).strip()[:2000]
        chunks[num] = body
        i += 2
    return {
        "법령명_expected": expected_name,
        "n_articles_detected": len(chunks),
        "articles": {k: v[:500] for k, v in list(chunks.items())[:30]},
        "parse_method": "HTML strip + 제N조 regex split",
    }


def extract_article_from_law_json(j: dict, article_no: str) -> str:
    """Find 제N조 text in law JSON body."""
    blob = json.dumps(j, ensure_ascii=False)
    # try structured
    def walk(o):
        found = []
        if isinstance(o, dict):
            jo = str(o.get("조문번호") or o.get("조번호") or "")
            if article_no.replace(" ", "") in jo.replace(" ", "") or jo.replace(" ", "") == article_no.replace(" ", ""):
                content = o.get("조문내용") or o.get("조문") or o.get("항내용") or ""
                if isinstance(content, list):
                    content = " ".join(str(x) for x in content)
                found.append(str(content))
            for v in o.values():
                found.extend(walk(v))
        elif isinstance(o, list):
            for x in o:
                found.extend(walk(x))
        return found
    hits = walk(j)
    if hits:
        return re.sub(r"\s+", " ", hits[0])[:800]
    # regex fallback
    m = re.search(rf"{re.escape(article_no)}[^제]{{0,20}}(.{{20,600}})", blob)
    return (m.group(0)[:800] if m else "")


def run_G3(key: str) -> dict:
    outd = LAW / "연혁_g3"
    outd.mkdir(parents=True, exist_ok=True)
    method = {
        "list_api": "target=law JSON + efYd=20220101~오늘 + 법령명한글 완전일치",
        "guide_lsHistory": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide",
        "guide_lsHistory_body": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide",
        "note": "lsHistory는 type=HTML only. 구조화는 law+MST JSON 우선, 실패 시 HTML 저장+파싱",
    }
    today = datetime.now().strftime("%Y%m%d")
    laws = {}
    mismatches = []
    for name in G3_LAWS:
        rows = []
        page = 1
        while page <= 30:
            t = http_get({
                "OC": key, "target": "law", "type": "JSON", "query": name,
                "efYd": f"20220101~{today}", "display": 100, "page": page, "sort": "efasc",
            })
            j = parse_json(t)
            if is_html(t) or not j or "LawSearch" not in j:
                break
            save(outd / f"{name}_list_p{page}.json", t)
            items, total = list_items_from_json(j, "LawSearch")
            for it in items:
                actual = it.get("법령명한글") or ""
                if actual != name:
                    if actual:
                        mismatches.append({"expected": name, "actual": actual, "MST": it.get("법령일련번호")})
                    continue
                lid = str(it.get("법령일련번호") or "")
                if not lid or any(r["MST"] == lid for r in rows):
                    continue
                ef = str(it.get("시행일자") or "")
                if ef.isdigit() and int(ef) < 20220101:
                    continue
                rows.append({
                    "시행일": it.get("시행일자"),
                    "공포일": it.get("공포일자"),
                    "공포번호": it.get("공포번호") if not isinstance(it.get("공포번호"), dict) else "31593_check",
                    "MST": lid,
                    "현행연혁코드": it.get("현행연혁코드"),
                    "본문저장": False,
                    "본문유형": None,
                })
            if not items or page * 100 >= total or len(items) < 100:
                break
            page += 1

        # also lsHistory HTML list for evidence
        th = http_get({
            "OC": key, "target": "lsHistory", "type": "HTML", "query": name,
            "efYd": f"20220101~{today}", "display": 100,
        })
        save(outd / f"{name}_lsHistory.html", th)

        for r in rows:
            tb = http_get({"OC": key, "target": "law", "type": "JSON", "MST": r["MST"]}, SERVICE)
            jb = parse_json(tb)
            if jb and not is_html(tb) and "없습니다" not in tb[:80]:
                m = re.search(r'"법령명[^"]*"\s*:\s*"([^"]+)"', tb)
                actual = m.group(1) if m else ""
                if actual == name:
                    save(outd / "bodies" / f"{name}_{r['MST']}.json", tb)
                    r["본문저장"] = True
                    r["본문유형"] = "law_JSON_MST"
                    continue
            # HTML fallback
            thb = http_get({"OC": key, "target": "lsHistory", "type": "HTML", "MST": r["MST"]}, SERVICE)
            save(outd / "bodies_html" / f"{name}_{r['MST']}.html", thb)
            parsed = parse_ls_history_html(thb, name)
            save(outd / "bodies_parsed" / f"{name}_{r['MST']}.json", json.dumps(parsed, ensure_ascii=False, indent=2))
            r["본문저장"] = parsed["n_articles_detected"] > 0
            r["본문유형"] = "lsHistory_HTML_parsed"
            if not r["본문저장"]:
                # national law center history URL
                url = f"https://www.law.go.kr/lsInfoP.do?lsiSeq={r['MST']}"
                add_manual({
                    "id": f"g3_{name}_{r['MST']}",
                    "title": f"{name} 연혁 본문 (시행 {r['시행일']})",
                    "why": "API로 본문/파싱 실패 — 수동 확인·저장 필요",
                    "url": url,
                    "action": f"연혁 화면에서 시행일 {r['시행일']} 판 본문 확인/저장",
                    "dest": str(LAW / "연혁_g3" / "manual"),
                })
        laws[name] = {"versions": rows, "n": len(rows), "bodies_ok": sum(1 for r in rows if r["본문저장"])}
        print("G3", name, "versions", len(rows), "bodies", laws[name]["bodies_ok"])

    # verification articles
    verify = {}
    for law_name, art in [("주택임대차보호법", "제7조"), ("근로기준법", "제17조")]:
        compare = []
        for r in laws.get(law_name, {}).get("versions") or []:
            p = outd / "bodies" / f"{law_name}_{r['MST']}.json"
            text = ""
            if p.exists():
                j = parse_json(p.read_text(encoding="utf-8"))
                text = extract_article_from_law_json(j or {}, art)
            else:
                pp = outd / "bodies_parsed" / f"{law_name}_{r['MST']}.json"
                if pp.exists():
                    pj = json.loads(pp.read_text(encoding="utf-8"))
                    text = (pj.get("articles") or {}).get(art, "") or (pj.get("articles") or {}).get(art.replace("제", "제 "), "")
            compare.append({"시행일": r["시행일"], "MST": r["MST"], "조문텍스트": text[:500]})
        # diff highlight
        changed = []
        prev = None
        for c in compare:
            if prev is not None and c["조문텍스트"] != prev:
                changed.append({"from_시행일": None, "to_시행일": c["시행일"], "new": c["조문텍스트"][:300]})
            prev = c["조문텍스트"]
        verify[f"{law_name}_{art}"] = {"rows": compare, "changes_detected": len(set(x["조문텍스트"] for x in compare if x["조문텍스트"])) > 1}

    return {
        "method": method,
        "laws": laws,
        "mismatches_rejected": mismatches[:50],
        "mismatch_count": len(mismatches),
        "verify": verify,
        "excluded_note": "최저임금법·시행령·이자제한 최고이자율 규정은 2022 이전 시행판이 현행이라 G3 제외(기존 리포트 근거 유지)",
    }


# ---------- G4 ----------
def run_G4() -> dict:
    patterns = ["580", "판결", "약관", "terms", "judgment", "Ruling", "AIHub"]
    roots = [
        Path.home() / "Downloads",
        Path(r"C:\Users\DMLAB\Downloads"),
        Path(r"C:\Users\DMLAB\Desktop"),
        ROOT,
        DC,
    ]
    found = []
    partial = []
    for base in roots:
        if not base.exists():
            continue
        try:
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                name = p.name.lower()
                if name.endswith((".crdownload", ".part", ".tmp")):
                    if any(x in name for x in ["580", "약관", "판결", "aihub"]):
                        partial.append(str(p))
                    continue
                if p.suffix.lower() in {".zip", ".tar", ".gz"} or p.is_dir():
                    pass
                rel = str(p)
                score = sum(1 for kw in ["약관", "판결", "580", "terms", "judgment"] if kw.lower() in rel.lower())
                if score and p.suffix.lower() in {".zip", ".7z", ".rar"}:
                    found.append({"path": str(p), "bytes": p.stat().st_size, "score": score})
        except Exception:
            continue
    # dedupe
    seen = set()
    uniq = []
    for f in sorted(found, key=lambda x: -x["score"]):
        if f["path"] in seen:
            continue
        seen.add(f["path"])
        uniq.append(f)

    result = {"candidates": uniq[:30], "partial_ignored": partial[:20], "processed": None}
    if not uniq:
        add_manual({
            "id": "g4_aihub580",
            "title": "AI Hub 판결서·약관 데이터 (dataSetSn=580)",
            "why": "약관 유리/불리 라벨·임대차 샘플에 필요",
            "url": "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=580",
            "action": "약관 관련 원천·라벨 파일만 선택해 다운로드",
            "dest": "Downloads 그대로 두면 after_manual.py가 처리",
        })
        result["status"] = "not_found"
        return result

    # process zips that look like terms
    terms_dir = DC / "aihub_terms"
    terms_dir.mkdir(parents=True, exist_ok=True)
    processed = []
    for f in uniq[:5]:
        p = Path(f["path"])
        if "약관" not in p.name and "terms" not in p.name.lower() and "580" not in p.name:
            # still try if only candidate
            if len(uniq) > 3 and f["score"] < 2:
                continue
        try:
            if p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as zf:
                    names = zf.namelist()[:50]
                    # extract only 약관-related
                    for n in zf.namelist():
                        if "약관" in n or "terms" in n.lower() or "유리" in n or "불리" in n:
                            dest = terms_dir / Path(n).name
                            if not dest.exists():
                                with zf.open(n) as src, open(dest, "wb") as out:
                                    shutil.copyfileobj(src, out)
                processed.append({"zip": str(p), "sample_names": names})
        except Exception as e:
            processed.append({"zip": str(p), "error": repr(e)})
    result["processed"] = processed
    result["status"] = "found" if processed else "candidates_only_unprocessed"
    if not processed:
        add_manual({
            "id": "g4_aihub580",
            "title": "AI Hub 판결서·약관 데이터 (dataSetSn=580)",
            "why": "후보 파일은 있으나 약관 부분 해제/확인 실패 — 공식 페이지에서 약관 원천·라벨만 선택 다운로드",
            "url": "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=580",
            "action": "약관 관련 원천·라벨 파일만 선택",
            "dest": "Downloads",
        })
    return result


# ---------- G5 ----------
def run_G5() -> dict:
    src = ROOT / "datasets" / "05.계약 법률 문서 서식 데이터"
    zips = sorted(src.rglob("*.zip")) if src.exists() else []
    entries = {}
    has_geumjeon_daecha = False
    for z in zips:
        if "금전" not in z.name:
            continue
        try:
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
            entries[str(z.relative_to(src))] = names[:40]
            if any("금전대차계약서" in n for n in names):
                has_geumjeon_daecha = True
        except Exception as e:
            entries[str(z.relative_to(src))] = [f"ERR {e}"]

    # taxonomy from extracted
    from collections import Counter
    c = Counter()
    forms = DC / "aihub_forms"
    for p in forms.rglob("*.json"):
        if not any(x.startswith(("TL_", "VL_")) for x in p.parts):
            continue
        if "금전" not in str(p):
            continue
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cat = (((o.get("document") or {}).get("metadata") or {}).get("file_info") or {}).get("document_category") or {}
        c[(cat.get("main_category"), cat.get("sub_category"), cat.get("detail_category"))] += 1

    aihub = {"tried": False, "key_present": False, "listing": None}
    key = os.environ.get("AIHUB_APIKEY") or os.environ.get("AIHUB_API_KEY") or ""
    if not key:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                try:
                    key, _ = winreg.QueryValueEx(k, "AIHUB_APIKEY")
                except FileNotFoundError:
                    try:
                        key, _ = winreg.QueryValueEx(k, "AIHUB_API_KEY")
                    except FileNotFoundError:
                        key = ""
        except Exception:
            key = ""
    if str(key).strip():
        aihub["key_present"] = True
        aihub["tried"] = True
        # try aihubshell -mode l
        import subprocess
        try:
            r = subprocess.run(
                ["aihubshell", "-mode", "l", "-datasetkey", "71834"],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "AIHUB_APIKEY": str(key).strip()},
            )
            aihub["listing"] = (r.stdout or "")[:3000] + (r.stderr or "")[:500]
            if "금전대차" in (r.stdout or ""):
                has_geumjeon_daecha = True
                add_manual({
                    "id": "g5_geumjeon",
                    "title": "AI Hub 금전대차계약서 파일 (dataset 71834)",
                    "why": "원본 목록에 금전대차 관련 파일 존재 — 별도 다운로드 필요",
                    "url": "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71834",
                    "action": "aihubshell/페이지에서 금전대차 관련 파일 선택 다운로드",
                    "dest": "Downloads",
                })
        except FileNotFoundError:
            aihub["listing"] = "aihubshell 미설치"
        except Exception as e:
            aihub["listing"] = repr(e)
    else:
        aihub["note"] = "키 없음 — aihubshell 목록 조회 건너뜀"

    conclusion = "개방 zip에 없음 / 데이터셋에 개방 안 됨"
    if has_geumjeon_daecha:
        conclusion = "원본 목록에 금전대차 관련 파일 있음 → G7 수동 다운로드"
    else:
        # record not in dataset
        pass

    return {
        "has_금전대차계약서_in_open_zip": has_geumjeon_daecha,
        "zip_entry_samples": entries,
        "taxonomy": [{"대": a, "중": b, "소": c_, "count": n} for (a, b, c_), n in c.most_common()],
        "aihubshell": aihub,
        "conclusion": conclusion if not has_geumjeon_daecha else "G7 수동",
        "dataset_url": "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71834",
    }


# ---------- G6 ----------
def run_G6() -> dict:
    pdf = DC / "cases" / "주택임대차분쟁조정사례집.pdf"
    ocr_dir = DC / "cases" / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        return {"ok": False, "error": "PDF 없음"}

    # prefer tesseract
    engine = None
    tess_cmd = shutil.which("tesseract")
    if not tess_cmd:
        # common install paths
        for p in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if Path(p).exists():
                tess_cmd = p
                break
    if not tess_cmd:
        # try winget install (may need user approval)
        import subprocess
        try:
            subprocess.run(
                ["winget", "install", "-e", "--id", "UB-Mannheim.TesseractOCR", "--accept-package-agreements", "--accept-source-agreements"],
                capture_output=True, text=True, timeout=600,
            )
        except Exception:
            pass
        for p in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if Path(p).exists():
                tess_cmd = p
                break

    use_gpu = False
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        # if any substantial CUDA process, CPU
        use_gpu = False  # conservative: system has many processes; use CPU
    except Exception:
        use_gpu = False

    pages_text = []
    n_pages = 0
    try:
        import fitz  # pymupdf
        doc = fitz.open(pdf)
        n_pages = doc.page_count
        if tess_cmd:
            engine = f"tesseract:{tess_cmd}"
            import subprocess
            env = os.environ.copy()
            user_tess = Path(os.environ.get("LOCALAPPDATA", "")) / "tesseract" / "tessdata"
            if (user_tess / "kor.traineddata").exists():
                env["TESSDATA_PREFIX"] = str(user_tess)
            for i in range(n_pages):
                page = doc.load_page(i)
                # 300 dpi
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_path = ocr_dir / f"p{i+1:03d}.png"
                pix.save(str(img_path))
                txt_path = ocr_dir / f"p{i+1:03d}.txt"
                try:
                    subprocess.run(
                        [tess_cmd, str(img_path), str(txt_path.with_suffix("")), "-l", "kor+eng"],
                        capture_output=True, timeout=180, env=env,
                    )
                    text = txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else ""
                except Exception as e:
                    text = f"[OCR_ERR {e}]"
                    txt_path.write_text(text, encoding="utf-8")
                pages_text.append(text)
                if (i + 1) % 10 == 0:
                    print("G6 OCR", i + 1, "/", n_pages)
                # remove png to save space? user said no delete — keep
        else:
            engine = "easyocr_cpu"
            import easyocr
            reader = easyocr.Reader(["ko", "en"], gpu=use_gpu)
            for i in range(n_pages):
                page = doc.load_page(i)
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_path = ocr_dir / f"p{i+1:03d}.png"
                pix.save(str(img_path))
                result = reader.readtext(str(img_path), detail=0)
                text = "\n".join(result)
                (ocr_dir / f"p{i+1:03d}.txt").write_text(text, encoding="utf-8")
                pages_text.append(text)
                if (i + 1) % 5 == 0:
                    print("G6 EasyOCR", i + 1, "/", n_pages)
        doc.close()
    except Exception as e:
        return {"ok": False, "error": repr(e), "engine": engine}

    combined = "\n\n".join(f"----- PAGE {i+1} -----\n{t}" for i, t in enumerate(pages_text))
    save(ocr_dir / "ALL.txt", combined)

    import random
    random.seed(42)
    sample_idx = sorted(random.sample(range(n_pages), min(5, n_pages)))
    samples = []
    for i in sample_idx:
        t = pages_text[i]
        hangul = len(re.findall(r"[가-힣]", t))
        broken = len(re.findall(r"[�□￿]", t)) + t.count("\x00")
        total_chars = max(len(t), 1)
        samples.append({
            "page": i + 1,
            "head_300": t[:300],
            "hangul_ratio": hangul / total_chars,
            "broken_ratio": broken / total_chars,
        })
    avg_hangul = sum(s["hangul_ratio"] for s in samples) / max(len(samples), 1)

    # TOC extraction
    toc_pages = []
    titles = []
    for i, t in enumerate(pages_text[:15]):
        if "목차" in t or "차례" in t:
            toc_pages.append(i + 1)
            for line in t.splitlines():
                line = line.strip()
                if re.search(r"사례|조정|사건", line) and len(line) >= 4:
                    titles.append(line)
    # also scan all for 사례 N
    case_titles = []
    for i, t in enumerate(pages_text):
        for m in re.finditer(r"(사\s*례\s*\d+\s*[.:)\-]?\s*.{2,80})", t):
            case_titles.append(m.group(1).strip())

    quality_ok = avg_hangul >= 0.70
    return {
        "ok": True,
        "engine": engine,
        "use_gpu": use_gpu,
        "n_pages": n_pages,
        "samples": samples,
        "avg_hangul_ratio": avg_hangul,
        "quality_ok": quality_ok,
        "toc_pages": toc_pages,
        "case_title_count": len(set(case_titles)),
        "case_titles_sample": list(dict.fromkeys(case_titles))[:80],
        "stopped_low_quality": not quality_ok,
    }


# ---------- G7 HTML + after_manual ----------
def write_manual_html(items: list[dict]):
    path = DC / "MANUAL_DOWNLOADS.html"
    archive_if_exists(path)
    if not items:
        html = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>수동 다운로드</title>
<style>body{font-family:sans-serif;max-width:800px;margin:2rem auto;padding:0 1rem}</style></head>
<body><p><code>python data_contract\\scripts\\after_manual.py</code></p>
<h1>수동 작업 없음</h1></body></html>"""
        path.write_text(html, encoding="utf-8")
        return path

    cards = []
    for it in items:
        cards.append(f"""
<article class="card" id="{it.get('id','')}">
  <h2>{it.get('title','')}</h2>
  <p class="why">{it.get('why','')}</p>
  <p><a class="btn" href="{it.get('url','#')}" target="_blank" rel="noopener">다운로드 페이지 열기</a></p>
  <p><strong>할 일:</strong> {it.get('action','')}</p>
  <p><strong>저장 위치:</strong> <code>{it.get('dest','Downloads')}</code></p>
  <p class="status">상태: 대기</p>
</article>""")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>수동 다운로드 — data_contract</title>
<style>
body{{font-family:"Pretendard",system-ui,sans-serif;background:#f6f3ee;color:#1a1a1a;margin:0;padding:1.5rem}}
.wrap{{max-width:860px;margin:0 auto}}
.cmd{{background:#1e293b;color:#e2e8f0;padding:.75rem 1rem;border-radius:8px;font-family:ui-monospace,monospace}}
.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:1.25rem 1.5rem;margin:1rem 0}}
.btn{{display:inline-block;background:#0f766e;color:#fff;text-decoration:none;padding:.55rem 1rem;border-radius:8px}}
.why{{color:#444}} .status{{color:#b45309;font-weight:600}}
</style>
</head>
<body><div class="wrap">
<p class="cmd">python data_contract\\scripts\\after_manual.py</p>
<h1>수동 다운로드 ({len(items)})</h1>
{''.join(cards)}
</div></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def write_after_manual():
    path = DC / "scripts" / "after_manual.py"
    archive_if_exists(path)
    path.write_text(r'''# -*- coding: utf-8 -*-
"""Downloads에서 G7 수동 파일을 찾아 복사·해제 후 해당 단계 재실행."""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
DOWNLOADS = [
    Path.home() / "Downloads",
    Path(r"C:\Users\DMLAB\Downloads"),
    Path(r"C:\Users\DMLAB\Desktop"),
]
NOW = datetime.now().strftime("%Y%m%d%H%M")


def is_complete(p: Path) -> bool:
    return p.is_file() and not p.name.endswith((".crdownload", ".part", ".tmp"))


def find_files(keywords):
    hits = []
    for d in DOWNLOADS:
        if not d.exists():
            continue
        for p in d.iterdir():
            if not is_complete(p):
                continue
            if any(k.lower() in p.name.lower() for k in keywords):
                hits.append(p)
    return hits


def main():
    log = {"ran_at": NOW, "actions": []}
    # G4 AI Hub 580
    hits = find_files(["580", "약관", "판결서", "terms"])
    dest = DC / "aihub_terms"
    dest.mkdir(parents=True, exist_ok=True)
    for h in hits:
        if h.suffix.lower() == ".zip":
            target = dest / h.name
            if not target.exists():
                shutil.copy2(h, target)
            try:
                with zipfile.ZipFile(target) as zf:
                    for n in zf.namelist():
                        if "약관" in n or "terms" in n.lower():
                            out = dest / Path(n).name
                            if not out.exists():
                                with zf.open(n) as src, open(out, "wb") as f:
                                    shutil.copyfileobj(src, f)
                log["actions"].append({"g4": str(h)})
            except Exception as e:
                log["actions"].append({"g4_error": repr(e)})

    # G5 금전대차
    hits = find_files(["금전대차", "71834"])
    dest5 = DC / "aihub_forms" / "manual_금전대차"
    dest5.mkdir(parents=True, exist_ok=True)
    for h in hits:
        shutil.copy2(h, dest5 / h.name)
        log["actions"].append({"g5": str(h)})

    # G3 manual folder hint
    man = LAW = DC / "law_api" / "연혁_g3" / "manual"
    man.mkdir(parents=True, exist_ok=True)

    # Re-run collection pieces if OC available
    try:
        from run_g1_g7 import oc, run_G1, run_G3, run_G4, run_G5, write_manual_html, MANUAL_ITEMS
        import run_g1_g7 as M
        M.MANUAL_ITEMS.clear()
        key = oc()
        if key:
            g1 = run_G1(key)
            g3 = run_G3(key)
            log["actions"].append({"rerun": "G1/G3", "g1_ok": bool(g1), "g3_ok": bool(g3)})
        g4 = run_G4()
        g5 = run_G5()
        write_manual_html(M.MANUAL_ITEMS)
        log["manual_remaining"] = len(M.MANUAL_ITEMS)
    except Exception as e:
        log["rerun_error"] = repr(e)

    out = DC / "after_manual_log.json"
    out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    print("See DATA_READY_REPORT.md / MANUAL_DOWNLOADS.html")


if __name__ == "__main__":
    main()
''', encoding="utf-8")
    return path


def dump(result: dict):
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    import sys
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    key = oc()
    assert key, "LAW_OC missing"
    result = {"started": NOW, "manual": []}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            for k, v in prev.items():
                if k.startswith("G") and isinstance(v, dict) and v.get("_done"):
                    result[k] = v
            if prev.get("manual"):
                result["manual"] = prev["manual"]
        except Exception:
            pass

    steps = [
        ("G1", lambda: run_G1(key)),
        ("G2", lambda: run_G2(key)),
        ("G3", lambda: run_G3(key)),
        ("G4", run_G4),
        ("G5", run_G5),
        ("G6", run_G6),
    ]
    for name, fn in steps:
        if name in result and isinstance(result[name], dict) and result[name].get("_done") and not result[name].get("_error"):
            print(name, "skip", flush=True)
            # restore manual items for unauthorized from G1 probe
            if name == "G1":
                probe = (result["G1"].get("probe") or {})
                for tname, info in probe.items():
                    tgt = tname.replace("_XML", "")
                    if info.get("ok"):
                        continue
                    if info.get("unauthorized") or (info.get("kind") == "HTML" and "미신청" in (info.get("error_text") or "")):
                        if not any(m.get("id") == f"g1_{tgt}" or (tgt in (m.get("targets") or [])) for m in MANUAL_ITEMS):
                            add_manual({
                                "id": f"g1_{tgt}",
                                "title": f"Open API target={tgt} 승인 확인",
                                "why": f"target={tgt} 권한 없음/실패",
                                "url": "https://open.law.go.kr/LSO/openApi/useInfo.do",
                                "action": f"open.law.go.kr 마이페이지에서 target={tgt} 승인 상태 확인",
                                "dest": "승인 후 python data_contract\\scripts\\after_manual.py",
                                "targets": [tgt],
                            })
            continue
        print("=" * 40, name, flush=True)
        try:
            result[name] = fn()
            result[name]["_done"] = True
        except Exception as e:
            result[name] = {"_error": repr(e), "_done": False}
            print(name, "ERROR", e, flush=True)
        result["manual"] = MANUAL_ITEMS
        dump(result)

    write_after_manual()
    write_manual_html(MANUAL_ITEMS)
    result["manual"] = MANUAL_ITEMS
    result["manual_count"] = len(MANUAL_ITEMS)
    dump(result)
    print("WROTE", OUT, "manual", len(MANUAL_ITEMS), flush=True)


if __name__ == "__main__":
    main()
