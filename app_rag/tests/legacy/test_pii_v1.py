# -*- coding: utf-8 -*-
"""rag.pii 마스킹 테스트 (20+)."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.pii import mask_pii, mask_text  # noqa: E402


def test_rrn():
    t, c = mask_pii("주민등록번호 901234-1234567")
    assert "901234-*******" in t
    assert "1234567" not in t
    assert c["rrn"] == 1


def test_phone_mobile():
    t, c = mask_pii("연락처 010-1234-5678")
    assert t.endswith("***-****-5678") or "***-****-5678" in t
    assert "1234" not in t.split("***-****-")[0] or c["phone"] == 1
    assert c["phone"] == 1


def test_phone_not_date_iso():
    t, c = mask_pii("근로개시일 2026-03-02")
    assert "2026-03-02" in t
    assert c["phone"] == 0


def test_phone_not_date_dot():
    t, c = mask_pii("계약일 2026.3.2 시작")
    assert "2026.3.2" in t
    assert c["phone"] == 0


def test_money_not_account():
    t, c = mask_pii("보증금 1,900,000원")
    assert "1,900,000원" in t
    assert c["account"] == 0


def test_wage_not_account():
    t, c = mask_pii("시급 10,320원")
    assert "10,320원" in t
    assert c["account"] == 0


def test_account_mask():
    t, c = mask_pii("계좌번호 1234-5678-901234")
    assert "1234-****-" in t
    assert c["account"] == 1


def test_article_untouched():
    t, c = mask_pii("근로기준법 제54조 제1항")
    assert "제54조 제1항" in t


def test_worker_not_name():
    t, c = mask_pii("근로자는 성실히 근무한다.")
    assert "근로자는 성실히" in t
    assert c["name"] == 0


def test_name_after_role():
    t, c = mask_pii("근로자: 김철수")
    assert "김*" in t or "김**" in t
    assert "철수" not in t
    assert c["name"] == 1


def test_lessor_name_needs_colon():
    # 역할어는 콜론이 있을 때만 가린다.
    t, c = mask_pii("임대인 이영희")
    assert t == "임대인 이영희"
    assert c["name"] == 0


def test_keep_common_words():
    samples = [
        "갑은 을의 신청을 제한하지 않는다.",
        "임금은 을에게 지급한다.",
        "근로자 대표와 협의한다.",
        "임차인 주거 안정을 고려한다.",
        "보증금은 갑이 보관한다.",
        "신청을 제한하지 않는다.",
        "주민등록을 마친 자에게 알린다.",
        "계약을 해지할 수 있다.",
        "채무를 변제한다.",
        "보수를 지급한다.",
        "사업주는 근로자에게 통지한다.",
    ]
    assert len(samples) >= 10
    for raw in samples:
        t, c = mask_pii(raw)
        assert t == raw, raw
        assert c["name"] == 0


def test_mask_name_fields():
    cases = [
        ("성명: 홍길동", "홍길동"),
        ("임대인: 김철수", "김철수"),
        ("을 : 이영희", "이영희"),
        ("이름 박민수", "박민수"),
    ]
    for raw, secret in cases:
        t, c = mask_pii(raw)
        assert secret not in t, raw
        assert c["name"] == 1
        assert "*" in t


def test_email():
    t, c = mask_pii("메일 a.bc@example.com")
    assert "a***@example.com" in t
    assert c["email"] == 1


def test_address_seoul():
    t, c = mask_pii("주소 서울특별시 강남구 테헤란로 123")
    assert "서울특별시 강남구 ***" in t
    assert "테헤란로" not in t
    assert c["address"] == 1


def test_address_gyeonggi():
    t, c = mask_pii("경기도 성남시 분당구 정자로 1")
    assert "경기도 성남시 ***" in t
    assert c["address"] == 1


def test_creditor_name():
    t, c = mask_pii("채권자: 박민수")
    assert c["name"] == 1
    assert "민수" not in t


def test_multiple():
    raw = "근로자: 최유진 전화 010-9999-8888 주민 880101-2345678"
    t, c = mask_pii(raw)
    assert c["name"] >= 1 and c["phone"] == 1 and c["rrn"] == 1
    assert "9999" not in t
    assert "2345678" not in t


def test_mask_text_alias():
    assert "*******" in mask_text("900101-1234567")


def test_empty():
    t, c = mask_pii("")
    assert t == ""
    assert sum(c.values()) == 0


def test_gap_eul_names():
    t, c = mask_pii("갑: 한지민 / 을: 오세훈")
    assert c["name"] == 2


def test_phone_with_spaces():
    t, c = mask_pii("연락처 010 2222 3333")
    assert c["phone"] == 1
    assert "3333" in t


def test_no_mask_law_only():
    t, c = mask_pii("민법 제398조에 따른다.")
    assert t == "민법 제398조에 따른다."
    assert sum(c.values()) == 0


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    ok = fail = 0
    for fn in tests:
        try:
            fn()
            ok += 1
            print("PASS", fn.__name__)
        except Exception as e:
            fail += 1
            print("FAIL", fn.__name__, e)
            traceback.print_exc()
    print(f"RESULT {ok}/{ok+fail}")
    raise SystemExit(1 if fail else 0)
