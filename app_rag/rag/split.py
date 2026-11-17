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

# --- SPLIT_META: 꼬리·서식 부속 ---
DATE_ONLY_FLEX = re.compile(
    r"^("
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일"
    r"|\d{4}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}"
    r"|20_{2,4}\s*년\s*_{1,4}\s*월\s*_{1,4}\s*일"
    r")\s*$"
)
SIGN_MARK = re.compile(r"(\(서명\)|\(인\)|\(서명\s*또는\s*날인\)|\(서명\s*또는\s*인\))")
PERSON_FIELD = re.compile(
    r"^(성\s*명|성명|주\s*소|주소|연\s*락\s*처|연락처|전화|주민등록번호|사업체명|대\s*표\s*자|대표자)\s*:"
)
PARTY_START = re.compile(
    r"^(\(채권자\s*[·･・]?\s*갑\)|\(채무자\s*[·･・]?\s*을\)|\(사업주\)|\(근로자\)|\(임대인\)|\(임차인\)|\(연대보증인\))"
)
DELIVERY_LINE = re.compile(
    r"(계약서\s*2통을\s*작성하여.*각\s*1통을\s*보관한다|계약\s*당사자가\s*이의\s*없음을\s*확인하고.*서명)"
)
PAGE_MARK = re.compile(r"^\(\s*\d+\s*쪽\s*중\s*\d+\s*쪽\s*\)$")
PAPER_MARK = re.compile(r"^\d+\s*mm\s*[x×]\s*\d+\s*mm\s*\[", re.I)
CONSENT_TITLE = re.compile(r"개인정보.*(제\s*3\s*자\s*제공\s*동의|수집\s*[·･・]?\s*이용\s*동의)")
ACK_UNDERSTAND = re.compile(r"본인은.+설명을\s*듣고.+이해했음")
NOTE_LINE = re.compile(r"^※")
NOTE_KEEP_SPECIAL = re.compile(r"^※\s*(기타|특약)")


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER.sub("", text or "")


def _clean(text: str) -> str:
    # PDF 추출본은 줄 앞에 공백이 붙어 ARTICLE_SPLIT(^제N조)·①·번호 분할이 깨질 수 있다.
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return "\n".join(ln.lstrip() for ln in t.splitlines())


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
    if DATE_ONLY.match(s) or DATE_ONLY_FLEX.match(s):
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


def _is_drop_line(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if PAGE_MARK.match(t):
        return True
    if PAPER_MARK.match(t):
        return True
    return False


def _is_tail_meta_line(s: str) -> bool:
    """마지막 조항 뒤에 오는 날짜·서명·인적·교부 줄. 줄 전체가 맞을 때만."""
    t = (s or "").strip()
    if not t:
        return True
    if ARTICLE_HEAD.match(t) or _is_unit_start(t):
        return False
    if DATE_ONLY_FLEX.match(t) or DATE_ONLY.match(t):
        return True
    if SIGN_MARK.search(t) and len(t) <= 40:
        return True
    if PERSON_FIELD.match(t):
        return True
    if PARTY_START.match(t):
        return True
    if DELIVERY_LINE.search(t):
        return True
    return False


def _is_note_meta_line(s: str) -> bool:
    t = (s or "").strip()
    if not NOTE_LINE.match(t):
        return False
    if NOTE_KEEP_SPECIAL.match(t):
        return False
    return True


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


def _piece(kind: str, title: str, text: str) -> dict:
    return {"segment_type": kind, "article_title": title, "text": text}


def _bare_text(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("[") and "]" in t[:80]:
        return t.split("]", 1)[1].strip()
    return t


def _peel_trailing_meta_lines(text: str) -> tuple[str, list[str]]:
    """조각 끝의 꼬리 메타 줄을 떼어낸다."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "", []
    peeled: list[str] = []
    while lines:
        last = lines[-1]
        bare = _bare_text(last)
        if ARTICLE_HEAD.match(bare) or _is_unit_start(bare):
            break
        if _is_drop_line(bare) or _is_drop_line(last):
            lines.pop()
            continue
        if _is_tail_meta_line(bare) or _is_tail_meta_line(last):
            peeled.append(lines.pop())
            continue
        break
    peeled.reverse()
    return "\n".join(lines).strip(), peeled


def _line_needs_form_split(ln: str) -> bool:
    bare = _bare_text(ln)
    return bool(
        _is_drop_line(bare)
        or _is_drop_line(ln)
        or CONSENT_TITLE.search(bare)
        or ACK_UNDERSTAND.search(bare)
        or _is_note_meta_line(bare)
    )


def _apply_form_and_tail_meta(pieces: list[dict]) -> list[dict]:
    """쪽·용지 삭제, 동의서·※·확인문구 meta, 마지막 조항 꼬리 meta."""
    if not pieces:
        return []

    # 서식 부속 패턴이 섞인 조각: 해당 줄만 분리하고 본문 줄은 묶는다
    expanded: list[dict] = []
    for p in pieces:
        t = (p.get("text") or "").strip()
        if not t:
            continue
        kind0 = p.get("segment_type") or "clause"
        title0 = p.get("article_title") or ""
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if len(lines) > 1 and any(_line_needs_form_split(ln) for ln in lines):
            buf: list[str] = []
            for ln in lines:
                if _line_needs_form_split(ln):
                    if buf:
                        expanded.append(_piece(kind0, title0, "\n".join(buf)))
                        buf = []
                    expanded.append(_piece(kind0, title0, ln))
                else:
                    buf.append(ln)
            if buf:
                expanded.append(_piece(kind0, title0, "\n".join(buf)))
        else:
            expanded.append(_piece(kind0, title0, t))

    out: list[dict] = []
    consent_mode = False
    i = 0
    while i < len(expanded):
        cur = expanded[i]
        t = (cur.get("text") or "").strip()
        bare = _bare_text(t)
        kind = cur.get("segment_type") or "clause"
        title = cur.get("article_title") or ""

        if _is_drop_line(bare) or _is_drop_line(t):
            i += 1
            continue

        if ARTICLE_HEAD.match(bare):
            consent_mode = False

        if CONSENT_TITLE.search(bare):
            consent_mode = True
            out.append(_piece("meta", "", t))
            i += 1
            continue

        if consent_mode:
            if ARTICLE_HEAD.match(bare):
                consent_mode = False
            else:
                out.append(_piece("meta", "", t))
                i += 1
                continue

        if ACK_UNDERSTAND.search(bare):
            out.append(_piece("meta", "", t))
            if i + 1 < len(expanded):
                nxt_t = (expanded[i + 1].get("text") or "").strip()
                nb = _bare_text(nxt_t)
                if _is_tail_meta_line(nb) or (SIGN_MARK.search(nb) and len(nb) <= 60):
                    out.append(_piece("meta", "", nxt_t))
                    i += 2
                    continue
            i += 1
            continue

        if _is_note_meta_line(bare):
            out.append(_piece("meta", "", t))
            i += 1
            continue

        out.append(_piece(kind, title, t))
        i += 1

    # 문서 끝에서 꼬리 메타 조각 강등 + 마지막 조항 조각 내부 꼬리 줄 분리
    j = len(out) - 1
    while j >= 0 and out[j]["segment_type"] == "meta":
        j -= 1
    while j >= 0:
        if out[j]["segment_type"] not in ("clause", "special"):
            break
        t = out[j]["text"]
        bare = _bare_text(t)
        # 조각 전체가 꼬리면 meta
        if "\n" not in t and (_is_tail_meta_line(bare) or _is_tail_meta_line(t)):
            if not (ARTICLE_HEAD.match(bare) or _is_unit_start(bare)):
                out[j] = _piece("meta", "", t)
                j -= 1
                continue
        # 여러 줄이면 끝 꼬리만 분리
        kept, peeled = _peel_trailing_meta_lines(t)
        if peeled:
            title = out[j].get("article_title") or ""
            kind = out[j]["segment_type"]
            new_rows = []
            if kept:
                new_rows.append(_piece(kind, title, kept))
            new_rows.extend(_piece("meta", "", ln) for ln in peeled)
            out[j : j + 1] = new_rows
            # peeled는 이미 meta; kept가 있으면 더 이상 뒤로 가지 않음
            break
        break

    return [p for p in out if (p.get("text") or "").strip()]


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

    pieces = _apply_form_and_tail_meta(pieces)
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
