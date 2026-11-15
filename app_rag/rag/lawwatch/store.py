# -*- coding: utf-8 -*-
"""법령 버전 저장소: data_local/law_versions/{법령명}/{식별자}.json + index.json."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.lawwatch.parse import basic_meta, extract_articles, extract_byeol, load_mst
from rag.paths import APP, CORPUS
from rag.lawwatch.paths import LAW_API_CURRENT, LAW_API_HISTORY, LAW_VERSIONS, TARGET_LAWS_FILE
from rag.yamlutil import load as load_yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_dir_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "unknown"


def law_dir(law_name: str) -> Path:
    d = LAW_VERSIONS / safe_dir_name(law_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def index_path(law_name: str) -> Path:
    return law_dir(law_name) / "index.json"


def load_index(law_name: str) -> dict:
    p = index_path(law_name)
    if not p.exists():
        return {"law": law_name, "versions": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_index(law_name: str, index: dict) -> Path:
    p = index_path(law_name)
    p.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _body_payload(law: dict, *, source_path: str, status: str, fetched_at: str | None = None) -> dict:
    meta = basic_meta(law)
    articles = extract_articles(law, meta["name"])
    byeol = extract_byeol(law)
    return {
        "meta": {**meta, "status": status, "source_path": source_path, "fetched_at": fetched_at or _now_iso()},
        "articles": [{"id": a["id"], "article_no": a["article_no"], "title": a["title"], "text": a["text"]} for a in articles],
        "byeol": byeol,
        "raw": law,
    }


def register_body(
    law: dict,
    *,
    status: str,
    source_path: str,
    identifier: str | None = None,
    fetched_at: str | None = None,
) -> dict:
    meta = basic_meta(law)
    name = meta["name"]
    if not name:
        raise ValueError(f"법령명 없음: {source_path}")
    ident = identifier or meta.get("mst") or meta.get("law_key") or meta.get("announce_no") or "unknown"
    ident = safe_dir_name(str(ident))
    payload = _body_payload(law, source_path=source_path, status=status, fetched_at=fetched_at)
    out = law_dir(name) / f"{ident}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    index = load_index(name)
    versions = [v for v in index.get("versions") or [] if v.get("id") != ident]
    versions.append(
        {
            "id": ident,
            "mst": meta.get("mst") or "",
            "announce_no": meta.get("announce_no") or "",
            "announced": meta.get("announced"),
            "effective": meta.get("effective"),
            "status": status,
            "fetched_at": payload["meta"]["fetched_at"],
            "file": out.name,
            "source_path": source_path,
            "n_articles": len(payload["articles"]),
            "n_byeol": len(payload["byeol"]),
        }
    )
    versions.sort(key=lambda v: (v.get("effective") or "", v.get("announced") or "", v.get("id") or ""))
    index["law"] = name
    index["law_id"] = meta.get("law_id") or index.get("law_id") or ""
    index["versions"] = versions
    index["updated_at"] = _now_iso()
    save_index(name, index)
    return {"law": name, "id": ident, "path": str(out), "meta": payload["meta"]}


def load_version(law_name: str, ident: str) -> dict:
    p = law_dir(law_name) / f"{safe_dir_name(ident)}.json"
    if not p.exists():
        # try exact
        p = law_dir(law_name) / f"{ident}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def list_laws() -> list[str]:
    if not LAW_VERSIONS.exists():
        return []
    out = []
    for d in sorted(LAW_VERSIONS.iterdir()):
        if d.is_dir() and (d / "index.json").exists():
            out.append(d.name)
    return out


def collect_target_law_names() -> list[str]:
    """corpus records + 카드 basis + 숫자 고시."""
    names: set[str] = set()
    # corpus
    if CORPUS.exists():
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        for rec in data.get("records") or []:
            rid = rec.get("id") or ""
            parts = rid.split(":")
            if len(parts) >= 3 and parts[0] in ("law", "decree", "notice"):
                names.add(parts[1])
    # cards
    for domain in ("LAB", "LEASE", "LOAN"):
        for folder in (APP / "criteria", APP / "criteria" / "neutral"):
            path = folder / f"{domain}_cards.yaml"
            if not path.exists():
                continue
            rows = load_yaml(path) or []
            for card in rows:
                if not isinstance(card, dict):
                    continue
                for bid in card.get("basis") or []:
                    parts = str(bid).split(":")
                    if len(parts) >= 3:
                        names.add(parts[1])
    # 숫자 고시/규정(카드 basis ID에 없어도 추적)
    names.update(
        {
            "이자제한법 제2조제1항의 최고이자율에 관한 규정",
            "최저임금법",
            "최저임금법 시행령",
            "최저임금고시",
        }
    )
    # 현행 폴더 전체를 넣지 않는다 — corpus·카드 basis(+숫자 고시)만.
    return sorted(names)


def write_target_laws(*, exclude_extra: bool = True) -> dict:
    """target_laws.json을 corpus·카드 basis(+숫자 고시)만으로 다시 쓴다. 버전 파일은 지우지 않음."""
    from datetime import datetime, timezone

    targets = collect_target_law_names()
    stored = list_laws()
    excluded = sorted(set(stored) - set(targets))
    payload = {
        "laws": targets,
        "excluded_from_tracking": excluded,
        "exclude_note": "corpus·카드 basis에 없는 저장소 폴더는 추적만 제외(파일 유지)",
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    LAW_VERSIONS.mkdir(parents=True, exist_ok=True)
    TARGET_LAWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _find_current_body(law_name: str) -> Path | None:
    p = LAW_API_CURRENT / f"{law_name}_body_MST.json"
    if p.exists():
        return p
    for f in LAW_API_CURRENT.glob("*_body_MST.json"):
        if f.name.startswith(law_name):
            return f
    return None


def _find_history_bodies(law_name: str) -> list[Path]:
    out = []
    if not LAW_API_HISTORY.exists():
        return out
    for f in LAW_API_HISTORY.glob(f"{law_name}_body_MST_*.json"):
        out.append(f)
    for f in LAW_API_HISTORY.glob(f"{law_name}_body_*.json"):
        if "MST" not in f.name:
            # raw 연혁도 시도
            out.append(f)
    # 중복 제거, MST 우선
    seen = set()
    uniq = []
    for f in out:
        if f.name in seen:
            continue
        seen.add(f.name)
        uniq.append(f)
    return uniq


def bootstrap_from_law_api(*, include_history: bool = True) -> dict:
    """현행·연혁 MST를 저장소에 등록하고 target_laws.json을 쓴다."""
    LAW_VERSIONS.mkdir(parents=True, exist_ok=True)
    targets = collect_target_law_names()
    report = {"targets": targets, "registered": [], "skipped": [], "errors": []}
    TARGET_LAWS_FILE.write_text(
        json.dumps({"laws": targets, "built_at": _now_iso()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 현행 전부 등록 (대상에 없어도 body가 있으면)
    current_files = sorted(LAW_API_CURRENT.glob("*_body_MST.json")) if LAW_API_CURRENT.exists() else []
    for path in current_files:
        try:
            law = load_mst(path)
            meta = basic_meta(law)
            name = meta["name"] or path.name.replace("_body_MST.json", "")
            if targets and name not in targets and path.name.replace("_body_MST.json", "") not in targets:
                # 현행 폴더는 corpus 기준선이므로 모두 등록
                pass
            info = register_body(law, status="현행", source_path=str(path), identifier=meta.get("mst") or meta.get("law_key") or "current")
            report["registered"].append(info)
        except Exception as exc:
            report["errors"].append({"path": str(path), "error": str(exc)})

    if include_history and LAW_API_HISTORY.exists():
        for path in sorted(LAW_API_HISTORY.glob("*_body_MST_*.json")):
            try:
                law = load_mst(path)
                meta = basic_meta(law)
                # 파일명 법령과 본문 법령명이 어긋난 연혁이 있어 파일명 우선 힌트
                file_law = path.name.split("_body_MST_")[0]
                name = meta["name"] or file_law
                # 본문 법령명이 파일명과 다르면 파일명 기준으로 폴더를 잡되 meta에 표시
                if meta["name"] and meta["name"] != file_law:
                    # 잘못 매핑된 파일은 스킵하지 않고 본문 법령명으로 등록 + note
                    pass
                mst_from_file = path.stem.split("_")[-1]
                info = register_body(
                    law,
                    status="과거",
                    source_path=str(path),
                    identifier=meta.get("mst") or mst_from_file,
                )
                info["file_law_hint"] = file_law
                report["registered"].append(info)
            except Exception as exc:
                report["errors"].append({"path": str(path), "error": str(exc)})

    summary_path = LAW_VERSIONS / "bootstrap_report.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def register_synthetic_past(
    law_name: str,
    *,
    base_ident: str,
    new_ident: str,
    effective: str,
    announced: str | None,
    article_text_map: dict[str, str],
    byeol_extra: list[dict] | None = None,
    note: str = "",
) -> dict:
    """저장 본문을 바탕으로 과거 조문 텍스트만 바꾼 버전을 등록(개정문 근거)."""
    base = load_version(law_name, base_ident)
    raw = base.get("raw") or {}
    from copy import deepcopy

    law = deepcopy(raw)
    # articles override in payload
    payload_articles = []
    for art in base.get("articles") or []:
        text = article_text_map.get(art["id"], art["text"])
        payload_articles.append({**art, "text": text})
    byeol = list(base.get("byeol") or [])
    if byeol_extra:
        byeol = byeol + byeol_extra
    meta = dict(base.get("meta") or {})
    meta.update(
        {
            "name": law_name,
            "effective": effective,
            "announced": announced or meta.get("announced"),
            "status": "과거",
            "fetched_at": _now_iso(),
            "source_path": meta.get("source_path") or "",
            "synthetic": True,
            "synthetic_note": note,
            "based_on": base_ident,
        }
    )
    out = law_dir(law_name) / f"{safe_dir_name(new_ident)}.json"
    payload = {"meta": meta, "articles": payload_articles, "byeol": byeol, "raw": law}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    index = load_index(law_name)
    versions = [v for v in index.get("versions") or [] if v.get("id") != new_ident]
    versions.append(
        {
            "id": new_ident,
            "mst": meta.get("mst") or "",
            "announce_no": meta.get("announce_no") or "",
            "announced": meta.get("announced"),
            "effective": effective,
            "status": "과거",
            "fetched_at": meta["fetched_at"],
            "file": out.name,
            "source_path": meta.get("source_path"),
            "synthetic": True,
            "n_articles": len(payload_articles),
            "n_byeol": len(byeol),
            "note": note,
        }
    )
    versions.sort(key=lambda v: (v.get("effective") or "", v.get("id") or ""))
    index["versions"] = versions
    index["updated_at"] = _now_iso()
    save_index(law_name, index)
    return {"law": law_name, "id": new_ident, "path": str(out)}


def current_version_entry(law_name: str) -> dict | None:
    index = load_index(law_name)
    cur = [v for v in index.get("versions") or [] if v.get("status") == "현행"]
    if cur:
        return cur[-1]
    vers = index.get("versions") or []
    return vers[-1] if vers else None


def find_version_by_effective(law_name: str, effective: str) -> dict | None:
    index = load_index(law_name)
    for v in index.get("versions") or []:
        if v.get("effective") == effective:
            return v
    return None
