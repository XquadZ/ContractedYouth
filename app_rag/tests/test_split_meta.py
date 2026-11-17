# -*- coding: utf-8 -*-
from rag.split import judge_segments, split_contract


def test_dg01_signature_word_stays_clause():
    text = (
        "제1조(보증) 보증인은 보증의 뜻을 서면에 서명하여 표시한다.\n"
        "제2조(원금) 원금은 금 1,000,000원으로 한다.\n"
        "2026년 9월 4일\n"
        "(채권자·갑) 성명 김철수 (서명)\n"
        "주 소 : 서울특별시 영등포구 여의도동 1\n"
        "연 락 처 : 010-0000-0000\n"
        "갑과 을은 계약서 2통을 작성하여 서명하고 각 1통을 보관한다.\n"
    )
    segs = split_contract(text)
    judge = judge_segments(segs)
    blob = "\n".join(s["text"] for s in judge)
    assert "보증의 뜻을 서면에 서명하여 표시한다" in blob
    # D-G01 문장이 meta로 강등되면 안 됨
    meta_blob = "\n".join(s["text"] for s in segs if s["segment_type"] == "meta")
    assert "보증의 뜻을 서면에 서명하여 표시한다" not in meta_blob
    # 꼬리 서명·주소는 meta
    assert any("김철수" in s["text"] and s["segment_type"] == "meta" for s in segs)
    assert any("주 소" in s["text"] and s["segment_type"] == "meta" for s in segs)
    assert any("각 1통을 보관한다" in s["text"] and s["segment_type"] == "meta" for s in segs)


def test_consent_and_page_mark_are_meta_or_dropped():
    text = (
        "제17조(특약) 특약으로 정할 수 있다.\n"
        "1. 입주 전 수리를 협의한다.\n"
        "본인은 임대보증금 보증가입, 민간임대주택의 권리관계 등에 관한 주요 내용에 대한 설명을 듣고 이해했음.\n"
        "임차인 성명:               (서명 또는 날인)\n"
        "5. 개인정보의 제3자 제공 동의서\n"
        "임대사업자는 개인정보를 아래와 같이 제공한다.\n"
        "(6쪽 중 6쪽)\n"
        "210mm×297mm[백상지 80g/㎡]\n"
        "※ 임차인은 동의를 거부할 수 있다.\n"
    )
    segs = split_contract(text)
    types = {s["text"][:20]: s["segment_type"] for s in segs}
    judge = judge_segments(segs)
    judge_blob = "\n".join(s["text"] for s in judge)
    assert "(6쪽 중 6쪽)" not in judge_blob
    assert "210mm" not in judge_blob
    assert "개인정보의 제3자 제공 동의서" not in judge_blob
    assert "설명을 듣고 이해했음" not in judge_blob
    assert "※ 임차인은" not in judge_blob
    # 특약 본문 항목은 남아야
    assert any("입주 전 수리" in s["text"] for s in judge)


def test_note_special_header_kept():
    text = "※ 특약\n1. 별도 특약은 계약서에 적는다.\n"
    segs = split_contract(text)
    # ※ 특약은 특약 머리말로 유지(지금처럼 special/clause 가능). meta로만 강제하지 않음.
    assert any("※ 특약" in s["text"] for s in segs)
