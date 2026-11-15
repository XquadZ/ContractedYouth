# -*- coding: utf-8 -*-
"""참고 JSON 로드. 새 스키마. 필수 필드가 없으면 그 레코드는 쓰지 않는다."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from rag.paths import CORPUS, LAW_NODES, TAG_PROPOSAL
from rag.yamlutil import load as load_yaml

ARTICLE_MAX = 600
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

REQUIRED = ("id", "doc_type", "title", "text", "source", "url", "effective_date", "domain", "std_item")
DOC_TYPES = {"법률", "시행령", "고시", "판례", "표준계약서", "해석례"}
LAW_SHORT = {
    "근기법": "근로기준법",
    "근기령": "근로기준법 시행령",
    "기간제법": "기간제 및 단시간근로자 보호 등에 관한 법률",
    "최임법": "최저임금법",
    "최임령": "최저임금법 시행령",
    "퇴직급여법": "근로자퇴직급여 보장법",
    "주임법": "주택임대차보호법",
    "주임령": "주택임대차보호법 시행령",
    "민법": "민법",
    "이자법": "이자제한법",
    "이자규정": "이자제한법 제2조제1항의 최고이자율에 관한 규정",
    "보증법": "보증인 보호를 위한 특별법",
    "고용보험법": "고용보험법",
    "산재법": "산업재해보상보험법",
}
LAW_DOMAIN = {
    "근로기준법": ["LAB"],
    "근로기준법 시행령": ["LAB"],
    "기간제 및 단시간근로자 보호 등에 관한 법률": ["LAB"],
    "최저임금법": ["LAB"],
    "최저임금법 시행령": ["LAB"],
    "근로자퇴직급여 보장법": ["LAB"],
    "고용보험법": ["LAB"],
    "산업재해보상보험법": ["LAB"],
    "주택임대차보호법": ["LEASE"],
    "주택임대차보호법 시행령": ["LEASE"],
    "민법": ["LEASE", "LOAN"],
    "이자제한법": ["LOAN"],
    "이자제한법 제2조제1항의 최고이자율에 관한 규정": ["LOAN"],
    "보증인 보호를 위한 특별법": ["LOAN"],
}
LAW_URL = "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=query"


def validate_record(raw: dict) -> tuple[dict | None, str | None]:
    if not isinstance(raw, dict):
        return None, "not_object"
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        return None, "missing:" + ",".join(missing)
    rec_id = str(raw.get("id") or "").strip()
    text = raw.get("text")
    title = raw.get("title")
    doc_type = raw.get("doc_type")
    if not rec_id:
        return None, "empty_id"
    if not isinstance(text, str) or not text.strip():
        return None, "empty_text"
    if not isinstance(title, str) or not title.strip():
        return None, "empty_title"
    if doc_type not in DOC_TYPES:
        return None, "bad_doc_type"
    domain = raw.get("domain") if isinstance(raw.get("domain"), list) else []
    std_item = raw.get("std_item") if isinstance(raw.get("std_item"), list) else []
    return {
        "id": rec_id,
        "doc_type": doc_type,
        "title": title.strip(),
        "text": text.strip(),
        "source": str(raw.get("source") or ""),
        "url": str(raw.get("url") or ""),
        "effective_date": str(raw.get("effective_date") or ""),
        "domain": [str(x) for x in domain],
        "std_item": [str(x) for x in std_item],
        "legacy_id": str(raw.get("legacy_id") or ""),
    }, None


def load_corpus(path: Path | None = None) -> tuple[list[dict], list[dict]]:
    target = path or CORPUS
    skipped = []
    if not target.exists():
        return [], [{"id": str(target), "reason": "file_missing"}]
    obj = json.loads(target.read_text(encoding="utf-8"))
    rows = obj.get("records") if isinstance(obj, dict) else obj
    if not isinstance(rows, list):
        return [], [{"id": str(target), "reason": "not_list"}]
    out = []
    for i, row in enumerate(rows):
        rec, err = validate_record(row)
        if rec:
            if is_seafarer_min_wage(rec):
                skipped.append({"id": rec["id"], "reason": "seafarer_min_wage_notice"})
                continue
            out.append(rec)
        else:
            skipped.append({"id": (row.get("id") if isinstance(row, dict) else i), "reason": err})
    return expand_long_articles(out), skipped


def is_seafarer_min_wage(rec: dict) -> bool:
    blob = " ".join([str(rec.get("id") or ""), rec.get("title") or "", rec.get("text") or "", rec.get("legacy_id") or ""])
    return "선원" in blob and "최저임금" in blob


def _hang_parts(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    idxs = [i for i, ch in enumerate(raw) if ch in CIRCLED and (i == 0 or raw[i - 1] in "\n ")]
    if not idxs:
        return [raw]
    parts = []
    if idxs[0] != 0:
        head = raw[: idxs[0]].strip()
        if head:
            parts.append(head)
    for i, start in enumerate(idxs):
        end = idxs[i + 1] if i + 1 < len(idxs) else len(raw)
        piece = raw[start:end].strip()
        if piece:
            parts.append(piece)
    return parts or [raw]


def _hang_num(piece: str):
    if not piece:
        return None
    ch = piece.lstrip()[:1]
    if ch in CIRCLED:
        return CIRCLED.index(ch) + 1
    return None


def expand_long_articles(records: list[dict]) -> list[dict]:
    """조 1개=1레코드. 600자가 넘으면 항마다 나누고 제목을 앞에 붙인다."""
    out = []
    for rec in records:
        if rec.get("doc_type") not in ("법률", "시행령"):
            out.append(rec)
            continue
        parts = str(rec.get("id") or "").split(":")
        if len(parts) >= 4 and parts[-1].isdigit():
            out.append(rec)
            continue
        text = rec.get("text") or ""
        if len(text) <= ARTICLE_MAX:
            out.append(rec)
            continue
        parts = _hang_parts(text)
        hangs = []
        preamble = []
        for part in parts:
            num = _hang_num(part)
            if num is None:
                preamble.append(part)
            else:
                hangs.append((num, part))
        if not hangs:
            out.append(rec)
            continue
        if preamble:
            hangs[0] = (hangs[0][0], "\n".join(preamble + [hangs[0][1]]).strip())
        title = rec.get("title") or ""
        for num, part in hangs:
            body = part
            if title and not body.startswith(title):
                body = title + "\n" + body
            cloned = dict(rec)
            cloned["id"] = f"{rec['id']}:{num}"
            cloned["text"] = body
            out.append(cloned)
    return out


def _doc_type(law_name: str, old_id: str) -> str:
    if old_id.startswith("판례:") or "판례" in law_name:
        return "판례"
    if "시행령" in law_name:
        return "시행령"
    if "규정" in law_name or "고시" in law_name:
        return "고시"
    return "법률"


def _article_num(article: str) -> str:
    s = (article or "").strip()
    if s == "본문" or not s:
        return s or "본문"
    s = s.replace("조", "")
    s = s.replace("제", "")
    s = re.sub(r"\s+", "", s)
    return s or "본문"


def _new_id(doc_type: str, law_name: str, article: str, old_id: str) -> str:
    if doc_type == "판례":
        rest = old_id.split(":", 1)[-1]
        return "case:" + re.sub(r"\s+", "", rest)
    prefix = {"법률": "law", "시행령": "decree", "고시": "notice"}.get(doc_type, "law")
    return f"{prefix}:{law_name}:{_article_num(article)}"


def _date(raw: str) -> str:
    s = re.sub(r"\D", "", raw or "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return ""


def _title(law_name: str, article: str, head: str) -> str:
    art = article or ""
    if head:
        return f"{law_name} {art}({head})" if art else f"{law_name} ({head})"
    return f"{law_name} {art}".strip()


def convert_law_nodes(src: Path | None = None) -> tuple[list[dict], list[dict]]:
    path = src or LAW_NODES
    skipped = []
    records = []
    if not path.exists():
        return [], [{"id": str(path), "reason": "file_missing"}]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        old_id = str(row.get("id") or f"row-{i}")
        law_name = (row.get("법령명") or "").strip()
        if law_name in LAW_SHORT:
            law_name = LAW_SHORT.get(old_id.split(":")[0], law_name)
        short = old_id.split(":")[0]
        law_name = LAW_SHORT.get(short, law_name or short)
        article = (row.get("조문 번호") or "").strip()
        head = (row.get("조문 제목") or "").strip()
        text = (row.get("본문") or row.get("text") or "").strip()
        doc_type = _doc_type(law_name, old_id)
        rec = {
            "id": _new_id(doc_type, law_name, article, old_id),
            "doc_type": doc_type,
            "title": _title(law_name, article, head) if law_name != "판례" else (article or old_id),
            "text": text,
            "source": "국가법령정보센터" if doc_type != "판례" else "판례 메모",
            "url": "",
            "effective_date": _date(str(row.get("시행일") or "")),
            "domain": LAW_DOMAIN.get(law_name, []),
            "std_item": [],
            "legacy_id": old_id,
        }
        if is_seafarer_min_wage(rec):
            skipped.append({"id": old_id, "reason": "seafarer_min_wage_notice"})
            continue
        ok, err = validate_record(rec)
        if ok:
            records.append(ok)
        else:
            skipped.append({"id": old_id, "reason": err, "fail_reason": row.get("fail_reason") or ""})
    return expand_long_articles(records), skipped


def propose_tags(records: list[dict], rules_path: Path) -> list[dict]:
    from rag.yamlutil import load

    spec = load(rules_path)
    rules = spec.get("rules") or []
    rows = []
    for rec in records:
        blob = (rec.get("title") or "") + " " + (rec.get("text") or "")
        hits = []
        keys = []
        for rule in rules:
            kws = rule.get("keywords") or []
            matched = [k for k in kws if k and k in blob]
            if matched:
                hits.append(rule["id"])
                keys.append("+".join(matched[:3]))
        rows.append(
            {
                "id": rec["id"],
                "제안 std_item": "|".join(hits),
                "근거 키워드": " / ".join(keys),
            }
        )
    return rows


def write_tag_proposal(rows: list[dict], path: Path | None = None) -> Path:
    dest = path or TAG_PROPOSAL
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "제안 std_item", "근거 키워드"])
        writer.writeheader()
        writer.writerows(rows)
    return dest


def write_records(records: list[dict], path: Path | None = None) -> Path:
    dest = path or CORPUS
    payload = {"records": records}
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
