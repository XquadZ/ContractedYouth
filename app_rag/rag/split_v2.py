# -*- coding: utf-8 -*-
"""계약서를 항 단위로 나눈다. 판정에는 clause/special만 보낸다."""
from __future__ import annotations

import re

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
ARTICLE_HEAD = re.compile(r"^제\s*(\d+)\s*조(?:의\s*(\d+))?\s*(\([^)]+\))?", re.M)
ARTICLE_SPLIT = re.compile(r"(?=^제\s*\d+\s*조)", re.M)
HANG_SPLIT = re.compile(rf"(?=^[{CIRCLED}])", re.M)
NUM_SPLIT = re.compile(r"(?=^\d{1,2}\.\s)", re.M)
DASH_SPLIT = re.compile(r"(?=^[-–•]\s)", re.M)
SPECIAL_HEAD = re.compile(r"^특\s*약|특약\s*사항|그\s*밖의\s*약정", re.I)
TITLE_LINE = re.compile(r"(계약서|근로계약|임대차|차용증|금전소비대차)$")
PARTY_LINE = re.compile(
    r"(이하\s*[\"“]?|사업주|근로자|임대인|임차인|채권자|채무자|성명|주민등록|생년월일|주소\s*:|과\(와\).*체결)"
)
SIGN_LINE = re.compile(r"(서명|날인|기명|인\s*$|서명란)")
DATE_ONLY = re.compile(r"^\s*\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일\s*$")
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")
TABLE_LINE = re.compile(r"^[^:\n]{1,40}:\s*\S")
MIN_LEN = 20


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER.sub("", text or "")


def _clean(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _article_title(block: str) -> str:
    first = (block.splitlines() or [""])[0].strip()
    match = ARTICLE_HEAD.match(first)
    if not match:
        return first[:40]
    num, sub, paren = match.group(1), match.group(2), match.group(3) or ""
    head = f"제{num}조"
    if sub:
        head += f"의{sub}"
    if paren:
        head += paren
    else:
        rest = first[match.end() :].strip(" :.-")
        if rest:
            head += f"({rest})"
    return head


def _split_hangs(body: str) -> list[str]:
    raw = body.strip()
    if not raw:
        return []
    idxs = [m.start() for m in HANG_SPLIT.finditer(raw)]
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


def _split_numbered(body: str) -> list[str]:
    raw = body.strip()
    if not raw:
        return []
    splitter = NUM_SPLIT if NUM_SPLIT.search(raw) else DASH_SPLIT
    idxs = [m.start() for m in splitter.finditer(raw)]
    if not idxs:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if idxs[0] != 0:
        idxs = [0] + idxs
    parts = []
    for i, start in enumerate(idxs):
        end = idxs[i + 1] if i + 1 < len(idxs) else len(raw)
        piece = raw[start:end].strip()
        if piece:
            parts.append(piece)
    return parts or [raw]


def _is_unit_start(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if s[0] in CIRCLED:
        return True
    if re.match(r"^\d{1,2}\.\s", s):
        return True
    if re.match(r"^제\s*\d+\s*조", s):
        return True
    return False


def _is_meta_line(line: str, index: int, total: int) -> bool:
    s = line.strip()
    if not s:
        return True
    if _is_unit_start(s):
        return False
    if DATE_ONLY.match(s):
        return True
    if SIGN_LINE.search(s):
        return True
    if PARTY_LINE.search(s) and not s.startswith("제"):
        return True
    if index == 0 and (TITLE_LINE.search(s) or ("계약" in s and len(s) <= 40)):
        return True
    if total > 1 and index == 0 and "계약서" in s and not s.startswith("제"):
        return True
    return False


def _same_unit(a: dict, b: dict) -> bool:
    return a.get("segment_type") == b.get("segment_type") and (a.get("article_title") or "") == (b.get("article_title") or "")


def _merge_short(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    work = [dict(r) for r in rows]
    out: list[dict] = []
    i = 0
    while i < len(work):
        cur = work[i]
        short = _compact_len(cur["text"]) < MIN_LEN and not _is_unit_start(cur["text"])
        if short:
            nxt = work[i + 1] if i + 1 < len(work) else None
            if nxt is not None and _same_unit(cur, nxt) and not _is_unit_start(nxt["text"]):
                nxt["text"] = (cur["text"] + "\n" + nxt["text"]).strip()
                i += 1
                continue
            if nxt is not None and _same_unit(cur, nxt):
                nxt["text"] = (cur["text"] + "\n" + nxt["text"]).strip()
                i += 1
                continue
            if out and _same_unit(out[-1], cur) and not _is_unit_start(cur["text"]):
                out[-1]["text"] = (out[-1]["text"] + "\n" + cur["text"]).strip()
                i += 1
                continue
        out.append(cur)
        i += 1
    return out


def _split_table_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) >= 2 and sum(1 for ln in lines if TABLE_LINE.match(ln)) >= 2:
        return lines
    return [text.strip()] if (text or "").strip() else []


def _format_clause(title: str, body: str) -> str:
    body = body.strip()
    if not title:
        return body
    if body.startswith("[") and "]" in body[:80]:
        return body
    return f"[{title}] {body}"


def split_contract(text: str) -> list[dict]:
    raw = _clean(text)
    if not raw:
        return []
    special_at = None
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if SPECIAL_HEAD.search(line.strip()) and not ARTICLE_HEAD.match(line.strip()):
            special_at = i
            break
    main = "\n".join(lines[:special_at]) if special_at is not None else raw
    special_blob = "\n".join(lines[special_at:]) if special_at is not None else ""

    pieces: list[dict] = []
    art_idxs = [m.start() for m in ARTICLE_SPLIT.finditer(main)]
    if art_idxs:
        preamble = main[: art_idxs[0]].strip()
        if preamble:
            for ln in preamble.splitlines():
                if not ln.strip():
                    continue
                pieces.append(
                    {
                        "segment_type": "meta",
                        "article_title": "",
                        "text": ln.strip(),
                    }
                )
        for i, start in enumerate(art_idxs):
            end = art_idxs[i + 1] if i + 1 < len(art_idxs) else len(main)
            block = main[start:end].strip()
            title = _article_title(block)
            # 줄바꿈이 있어도 첫 줄(조문 머리 뒤 본문)을 버리지 않는다.
            # 예전: first_nl 이후만 body → PDF 줄바꿈 독소 수치(연 26% 등) 유실.
            first_line, _, rest = block.partition("\n")
            first_body = ARTICLE_HEAD.sub("", first_line, count=1).strip()
            body = "\n".join(x for x in (first_body, rest.strip()) if x).strip()
            if not body:
                body = block.strip()
            hangs = _split_hangs(body) if body else []
            if not hangs:
                hangs = [body or block.strip()]
            elif len(hangs) == 1 and not hangs[0].startswith(tuple(CIRCLED)):
                hangs = [hangs[0]]
            for hang in hangs:
                for chunk in _split_table_lines(hang) or [hang]:
                    pieces.append({"segment_type": "clause", "article_title": title, "text": chunk})
    else:
        numbered = _split_numbered(main) if (NUM_SPLIT.search(main) or DASH_SPLIT.search(main)) else [ln.strip() for ln in main.splitlines() if ln.strip()]
        n = len(numbered)
        for i, piece in enumerate(numbered):
            kind = "meta" if _is_meta_line(piece, i, n) else "clause"
            title = ""
            num = re.match(r"^(\d{1,2}\.)\s*([^:\n]{0,40})", piece)
            if num and kind == "clause":
                title = f"{num.group(1)} {(num.group(2) or '').strip(' :')}"
            pieces.append({"segment_type": kind, "article_title": title, "text": piece})

    if special_blob.strip():
        head, _, rest = special_blob.partition("\n")
        body = rest if rest else special_blob
        if SPECIAL_HEAD.search(head.strip()) and not (NUM_SPLIT.search(body) or DASH_SPLIT.search(body) or HANG_SPLIT.search(body)):
            chunks = [ln.strip() for ln in body.splitlines() if ln.strip()]
        else:
            blob = body if SPECIAL_HEAD.search(head.strip()) else special_blob
            chunks = _split_numbered(blob)
        for chunk in chunks:
            if SPECIAL_HEAD.search(chunk) and _compact_len(chunk) < MIN_LEN:
                continue
            pieces.append({"segment_type": "special", "article_title": "특약", "text": chunk})

    merged = _merge_short(pieces)
    out = []
    for order, row in enumerate(merged, start=1):
        title = row.get("article_title") or ""
        body = row["text"].strip()
        if row["segment_type"] in ("clause", "special") and title:
            shown = _format_clause(title, body)
        else:
            shown = body
        out.append(
            {
                "segment_id": f"seg-{order:03d}",
                "order": order,
                "segment_type": row["segment_type"],
                "article_title": title,
                "text": shown,
            }
        )
    return out


def judge_segments(segments: list[dict]) -> list[dict]:
    return [s for s in segments if s["segment_type"] in ("clause", "special")]


def meta_segments(segments: list[dict]) -> list[dict]:
    return [s for s in segments if s["segment_type"] == "meta"]
