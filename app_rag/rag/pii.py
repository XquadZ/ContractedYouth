# -*- coding: utf-8 -*-
"""개인정보 마스킹. 추출 직후·외부 LLM 호출 전에 적용."""
from __future__ import annotations

import re

# 주민등록번호: 하이픈/공백/붙여쓰기 → 앞6-*******
_RRN = re.compile(r"(?<!\d)(\d{6})\s*-\s*(\d{7})(?!\d)")
_RRN_SPACE = re.compile(r"(?<!\d)(\d{6})\s+(\d{7})(?!\d)")
_RRN_COMPACT = re.compile(r"(?<!\d)(\d{6})(\d{7})(?!\d)")

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

# 흔한 성 (HWP_TEST_PDFS_FIX B장)
_SURNAMES = set(
    "김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부"
)

# 역할어 뒤 일반 단어(이름 아님)
_EXCLUDE_NAMES = {
    "대표",
    "사업",
    "근로",
    "본인",
    "측",
    "쌍방",
    "각자",
    "전원",
    "모두",
    "등",
    "주거",
    "안정",
    "보호",
    "권리",
    "의무",
    "통지",
    "협의",
    "동의",
    "신청",
    "보관",
    "지급",
    "변제",
    "해지",
    "계약",
    "보수",
    "임금",
    "급여",
    "보증",
    "연대",
    "당사",
    "상호",
    "상기",
    "하기",
    "갑을",
    "성명",
    "이름",
    "법인",
    "법인명",
    "주소",
    "전화",
}

_ROLES = (
    r"연대보증인|사업주|근로자|임대인|임차인|채권자|채무자|보증인|대표자|대리인|영수자"
)

# 성명·이름: 콜론이 있든 없든 뒤 2~4글자 한글을 가린다.
_NAME_AFTER = r"([가-힣]{2,4})(?=(?:\s|$|,|\.|·|/|\(|\)|（|）))"
_NAME_LABEL = re.compile(
    rf"(?<![가-힣])((?:성\s*명|이\s*름))\s*[:：]?\s*{_NAME_AFTER}"
)
# 칸 라벨(공백 수 무관) + 콜론 필수
_NAME_LABEL_COLON = re.compile(
    rf"(?<![가-힣])((?:대\s*표\s*자|성\s*명|이\s*름))\s*[:：]\s*{_NAME_AFTER}"
)
# 갑/을: 콜론이 있을 때만
_NAME_GAP_EUL = re.compile(
    rf"(?<![가-힣])(갑|을)\s*[:：]\s*{_NAME_AFTER}"
)
# 역할어 + 콜론 + 이름
_NAME_ROLE_COLON = re.compile(
    rf"(?<![가-힣])({_ROLES})\s*[:：]\s*{_NAME_AFTER}"
)
# 역할어 + 공백 + 이름 + 허용 뒤문맥 (콜론 없음)
# 항목명(주민등록번호·주소 등)이 이름 뒤에 이어져도 가린다.
_PII_FIELD = (
    r"(?:주민등록번호|주민번호|생년월일|주소|연락처|전화|휴대폰|계좌번호|계좌)"
)
_TRAIL = rf"(?=(?:\(이하|[과와은는이가/,]|\(|（|\s*\(서명\)|\s+{_PII_FIELD}|\s*(?:\n|$)))"
_NAME_ROLE_SPACE = re.compile(
    rf"(?<![가-힣])({_ROLES})\s+([가-힣]{{2,4}}){_TRAIL}"
)
# 이름 (이하 "역할어" …) — 표준계약서 머리말
_NAME_BEFORE_IHA = re.compile(
    rf"(?<![가-힣])([가-힣]{{2,4}})\s*\(\s*이하\s*[\"“]?\s*({_ROLES}|갑|을)"
)
# 성명/이름 바로 붙거나 다음 줄 + (서명)
_NAME_LABEL_ATTACHED = re.compile(
    rf"(?<![가-힣])((?:성\s*명|이\s*름))\s*([가-힣]{{2,4}})"
)
_NAME_LABEL_NEXTLINE = re.compile(
    rf"(?<![가-힣])((?:성\s*명|이\s*름)(?:\s*\([^)\n]*\))?)\s*[\n\r]+\s*([가-힣]{{2,4}})\s*(?=\(서명\)|\n|$)"
)
_NAME_ACCOUNT_HOLDER = re.compile(
    rf"(?<![가-힣])(예금주)\s*[:：]?\s*[\n\r]*\s*([가-힣]{{2,4}})\s*(?=\n|$)"
)


def _mask_phone(m: re.Match) -> str:
    a, b, c = m.group(1), m.group(2), m.group(3)
    return f"***-****-{c}"


def _mask_account(m: re.Match) -> str:
    a, b, c = m.group(1), m.group(2), m.group(3)
    return f"{a}-****-{c[-4:] if len(c) >= 4 else c}"


def _mask_email(m: re.Match) -> str:
    return f"{m.group(1)}***{m.group(3)}"


def _mask_addr(m: re.Match) -> str:
    return f"{m.group(1)} {m.group(2)} ***"


def _normalize_role_label(label: str) -> str:
    return re.sub(r"\s+", "", label or "")


def _is_plausible_name(name: str, *, require_surname: bool) -> bool:
    if not name or len(name) < 2 or len(name) > 4:
        return False
    if name in _EXCLUDE_NAMES:
        return False
    if name in ("는", "은", "이", "가", "을", "를", "의", "과", "와", "도", "만"):
        return False
    if require_surname and name[0] not in _SURNAMES:
        return False
    return True


def _mask_name(m: re.Match, *, require_surname: bool = False) -> str:
    role, name = m.group(1), m.group(2)
    role_disp = _normalize_role_label(role)
    if name in ("는", "은", "이", "가", "을", "를", "의", "과", "와", "도", "만"):
        return m.group(0)
    if len(name) >= 2 and name[-1] in "는은이가을를의과와도만께":
        base = name[:-1]
        if len(base) < 2:
            return m.group(0)
        name = base
    if not _is_plausible_name(name, require_surname=require_surname):
        return m.group(0)
    return f"{role_disp} {name[0]}{'*' * (len(name) - 1)}"


_BANK_NEAR = re.compile(
    r"(국민|신한|우리|하나|농협|기업|카카오뱅크|토스뱅크|SC제일|우체국|새마을|신협|케이뱅크|부산|대구|경남|광주|전북|제주)(?:은행)?"
)


def _rrn_date_ok(front6: str, gender_digit: str) -> bool:
    """앞6이 유효 날짜(월 01~12, 일 01~31)이고 7번째 자리가 1~8."""
    if len(front6) != 6 or not front6.isdigit():
        return False
    mm, dd = int(front6[2:4]), int(front6[4:6])
    if mm < 1 or mm > 12 or dd < 1 or dd > 31:
        return False
    return gender_digit in "12345678"


def _looks_like_date_fragment(text: str, start: int, end: int) -> bool:
    """전화번호/계좌 매치가 날짜의 일부인지. 앞뒤 숫자 경계를 존중한다."""
    # 매치가 더 긴 숫자열 안의 조각이면(계좌 등) 날짜로 보지 않음 — 호출측 경계와 함께 동작
    left = text[start - 1] if start > 0 else ""
    right = text[end] if end < len(text) else ""
    if left.isdigit() or right.isdigit():
        return False
    window = text[max(0, start - 6) : min(len(text), end + 6)]
    # 독립된 YYYY-MM-DD 형태만
    if re.search(r"(?<!\d)\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?!\d)", window):
        return True
    if re.search(r"(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?!\d)", window):
        return True
    return False


def _bank_context(text: str, start: int) -> bool:
    left = text[max(0, start - 16) : start]
    return bool(_BANK_NEAR.search(left))


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
        front, back = m.group(1), m.group(2)
        # 붙여쓰기·공백 분리는 날짜+성별자리 검사
        if m.re in (_RRN_SPACE, _RRN_COMPACT) and not _rrn_date_ok(front, back[0]):
            return m.group(0)
        counts["rrn"] += 1
        return f"{front}-*******"

    out = _RRN.sub(sub_rrn, src)
    out = _RRN_SPACE.sub(sub_rrn, out)
    out = _RRN_COMPACT.sub(sub_rrn, out)

    # 날짜를 잠시 보호한 뒤 전화번호 마스킹 (2026-03-02 등)
    # 앞뒤 숫자 경계로 계좌 안 날짜 조각이 통째로 보호되지 않게 한다.
    date_holders: list[str] = []

    def _hold_date(m: re.Match) -> str:
        date_holders.append(m.group(0))
        return f"§DATE{len(date_holders)-1}§"

    out = re.sub(
        r"(?<!\d)\d{4}\s*[.\/년\-]\s*\d{1,2}\s*[.\/월\-]\s*\d{1,2}\s*일?(?!\d)",
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

    # account with money/date guard (은행명 앞이면 계좌로 강제)
    parts = []
    last = 0
    for m in _ACCOUNT.finditer(out):
        bankish = _bank_context(out, m.start())
        if not bankish and _looks_like_money_context(out, m.start(), m.end()):
            continue
        if not bankish and _looks_like_date_fragment(out, m.start(), m.end()):
            continue
        a = m.group(1)
        if not bankish and re.fullmatch(r"19\d{2}|20\d{2}", a or ""):
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

    def sub_name(m: re.Match, *, require_surname: bool = False) -> str:
        masked = _mask_name(m, require_surname=require_surname)
        if masked != m.group(0):
            counts["name"] += 1
        return masked

    out = _NAME_LABEL.sub(lambda m: sub_name(m, require_surname=False), out)
    out = _NAME_LABEL_COLON.sub(lambda m: sub_name(m, require_surname=False), out)
    out = _NAME_GAP_EUL.sub(lambda m: sub_name(m, require_surname=False), out)
    out = _NAME_ROLE_COLON.sub(lambda m: sub_name(m, require_surname=False), out)
    out = _NAME_ROLE_SPACE.sub(lambda m: sub_name(m, require_surname=True), out)

    def sub_before_iha(m: re.Match) -> str:
        name, role = m.group(1), m.group(2)
        if not _is_plausible_name(name, require_surname=True):
            return m.group(0)
        counts["name"] += 1
        # 이름만 가리고 (이하 … 는 유지
        rest = m.group(0)[len(name) :]
        return f"{name[0]}{'*' * (len(name) - 1)}{rest}"

    out = _NAME_BEFORE_IHA.sub(sub_before_iha, out)
    out = _NAME_LABEL_ATTACHED.sub(lambda m: sub_name(m, require_surname=True), out)
    out = _NAME_LABEL_NEXTLINE.sub(lambda m: sub_name(m, require_surname=True), out)
    out = _NAME_ACCOUNT_HOLDER.sub(lambda m: sub_name(m, require_surname=True), out)
    return out, counts


def mask_text(text: str) -> str:
    masked, _ = mask_pii(text)
    return masked
