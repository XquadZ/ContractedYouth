# -*- coding: utf-8 -*-
"""개인정보 마스킹. 추출 직후·외부 LLM 호출 전에 적용."""
from __future__ import annotations

import re

# 주민등록번호: 앞 6 + - + 뒤 7 → 앞6-*******
_RRN = re.compile(r"(?<!\d)(\d{6})-(\d{7})(?!\d)")

# 전화번호: 날짜(YYYY-MM-DD 등)와 구분. 휴대폰/일반
_PHONE = re.compile(
    r"(?<!\d)(01[016789]|02|0\d{1,2})[-.\s]?(\d{3,4})[-.\s]?(\d{4})(?!\d)"
)

# 계좌: 은행식 숫자-숫자-숫자 (금액·시급 제외는 호출측/추가 검사)
_ACCOUNT = re.compile(r"(?<!\d)(\d{2,6})-(\d{2,6})-(\d{2,8})(?!\d)")

# 이메일
_EMAIL = re.compile(r"([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")

# 주소: 시·도 + 시·군·구 이후
_ADDR = re.compile(
    r"((?:서울|부산|대구|인천|광주|대전|울산|세종|제주)특별시|"
    r"(?:서울|부산|대구|인천|광주|대전|울산)광역시|"
    r"세종특별자치시|제주특별자치도|"
    r"(?:경기|강원|충북|충남|전북|전남|경북|경남)(?:특별자치)?도)\s*"
    r"([가-힣]+(?:시|군|구))"
    r"([^\n,]{0,40})"
)

# 성명·이름: 콜론이 있든 없든 뒤 2~4글자 한글을 가린다.
# 역할어: 콜론(: 또는 ：)이 있을 때만. 바로 앞에 한글이 붙으면 역할어가 아니다
# ("신청을"의 "을" 처럼 조사로 쓰인 경우).
_NAME_AFTER = r"([가-힣]{2,4})(?=(?:\s|$|,|\.|·|/|\(|\)|（|）))"
_NAME_LABEL = re.compile(
    rf"(?<![가-힣])(성명|이름)\s*[:：]?\s*{_NAME_AFTER}"
)
_NAME_ROLE = re.compile(
    rf"(?<![가-힣])(임대인|임차인|사업주|근로자|대표자|채권자|채무자|보증인|갑|을)\s*[:：]\s*{_NAME_AFTER}"
)


def _mask_phone(m: re.Match) -> str:
    a, b, c = m.group(1), m.group(2), m.group(3)
    return f"***-****-{c}"


def _mask_account(m: re.Match) -> str:
    a, b, c = m.group(1), m.group(2), m.group(3)
    # 금액처럼 보이는 패턴 회피: 앞에 '원'이 가깝거나 그룹이 너무 김
    return f"{a}-****-{c[-4:] if len(c) >= 4 else c}"


def _mask_email(m: re.Match) -> str:
    return f"{m.group(1)}***{m.group(3)}"


def _mask_addr(m: re.Match) -> str:
    return f"{m.group(1)} {m.group(2)} ***"


def _mask_name(m: re.Match) -> str:
    role, name = m.group(1), m.group(2)
    # "근로자는" 등: 역할+조사만 있고 이름이 아닌 경우 — 패턴이 : 뒤 이름을 요구하므로
    # 조사가 이름에 붙은 경우(는/이/가/을/를/의/과/와/도/만) 스킵
    if name in ("는", "은", "이", "가", "을", "를", "의", "과", "와", "도", "만"):
        return m.group(0)
    if len(name) >= 2 and name[-1] in "는은이가을를의과와도만께":
        # 이름+조사로 붙은 형태면 조사 제거 시도
        base = name[:-1]
        if len(base) < 2:
            return m.group(0)
        name = base
    return f"{role} {name[0]}{'*' * (len(name) - 1)}"


def _looks_like_date_fragment(text: str, start: int, end: int) -> bool:
    """전화번호 매치가 날짜의 일부인지."""
    window = text[max(0, start - 6) : min(len(text), end + 6)]
    if re.search(r"\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}", window):
        return True
    if re.search(r"\d{4}-\d{1,2}-\d{1,2}", window):
        return True
    return False


def _looks_like_money_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 8) : min(len(text), end + 4)]
    if "원" in window:
        return True
    if re.search(r"(시급|월급|임금|급여|보증금|차임|원금|금액)", window):
        return True
    return False


def mask_pii(text: str) -> tuple[str, dict]:
    """마스킹된 텍스트와 변경 카운트를 반환."""
    src = text or ""
    counts = {
        "rrn": 0,
        "phone": 0,
        "account": 0,
        "email": 0,
        "address": 0,
        "name": 0,
    }

    def sub_rrn(m: re.Match) -> str:
        counts["rrn"] += 1
        return f"{m.group(1)}-*******"

    out = _RRN.sub(sub_rrn, src)

    # 날짜를 잠시 보호한 뒤 전화번호 마스킹 (2026-03-02 등)
    date_holders: list[str] = []

    def _hold_date(m: re.Match) -> str:
        date_holders.append(m.group(0))
        return f"§DATE{len(date_holders)-1}§"

    out = re.sub(
        r"\d{4}\s*[.\/년\-]\s*\d{1,2}\s*[.\/월\-]\s*\d{1,2}\s*일?",
        _hold_date,
        out,
    )

    parts = []
    last = 0
    for m in _PHONE.finditer(out):
        if _looks_like_date_fragment(out, m.start(), m.end()):
            continue
        parts.append(out[last : m.start()])
        parts.append(_mask_phone(m))
        counts["phone"] += 1
        last = m.end()
    parts.append(out[last:])
    out = "".join(parts)
    for i, raw in enumerate(date_holders):
        out = out.replace(f"§DATE{i}§", raw)

    # account with money/date guard
    parts = []
    last = 0
    for m in _ACCOUNT.finditer(out):
        if _looks_like_money_context(out, m.start(), m.end()):
            continue
        if _looks_like_date_fragment(out, m.start(), m.end()):
            continue
        a = m.group(1)
        # 연도(19xx/20xx)로 시작하는 구간은 날짜로 본다
        if re.fullmatch(r"19\d{2}|20\d{2}", a or ""):
            continue
        left = out[max(0, m.start() - 3) : m.start()]
        if "제" in left or "조" in out[m.end() : m.end() + 3]:
            continue
        parts.append(out[last : m.start()])
        parts.append(_mask_account(m))
        counts["account"] += 1
        last = m.end()
    parts.append(out[last:])
    out = "".join(parts)

    def sub_email(m: re.Match) -> str:
        counts["email"] += 1
        return _mask_email(m)

    out = _EMAIL.sub(sub_email, out)

    def sub_addr(m: re.Match) -> str:
        counts["address"] += 1
        return _mask_addr(m)

    out = _ADDR.sub(sub_addr, out)

    def sub_name(m: re.Match) -> str:
        name = m.group(2)
        if name in ("는", "은", "이", "가", "을", "를"):
            return m.group(0)
        masked = _mask_name(m)
        if masked != m.group(0):
            counts["name"] += 1
        return masked

    out = _NAME_LABEL.sub(sub_name, out)
    out = _NAME_ROLE.sub(sub_name, out)
    return out, counts


def mask_text(text: str) -> str:
    masked, _ = mask_pii(text)
    return masked
