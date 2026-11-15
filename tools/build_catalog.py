# -*- coding: utf-8 -*-
"""점검 항목 카탈로그(그래프) v0.1 생성 스크립트.
산출: catalog_v0.1.json (그래프), catalog_v0.1_checks.csv (검토용 표), catalog_v0.1_graph.mmd (시각화용)
법 조문은 모두 verified=False — 법령 API 원문 대조 전.
"""
import json, csv, sys, os

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

def L(law, art, note=""):
    return {"law": law, "article": art, "verified": False, **({"note": note} if note else {})}

LAWS = {
    "근기법": "근로기준법", "근기령": "근로기준법 시행령", "기간제법": "기간제 및 단시간근로자 보호 등에 관한 법률",
    "최임법": "최저임금법", "최임령": "최저임금법 시행령", "퇴직급여법": "근로자퇴직급여 보장법",
    "주임법": "주택임대차보호법", "주임령": "주택임대차보호법 시행령", "민법": "민법",
    "이자법": "이자제한법", "이자규정": "이자제한법 제2조제1항의 최고이자율에 관한 규정",
    "보증법": "보증인 보호를 위한 특별법",
}
# 법령 API 미수집: 기간제법, 퇴직급여법 → 추가 수집 필요
NOT_COLLECTED = ["기간제법", "퇴직급여법"]

PARAMS = {
    "min_wage_hourly": {"2022": 9160, "2023": 9620, "2024": 9860, "2025": 10030, "2026": 10320},
    "max_interest_rate_annual": {"from_2021-07-07": 0.20},
    "lease_increase_cap": 0.05,
    "weekly_holiday_threshold_hours": 15,
    "break_rule": [{"work_hours_gt": 4, "break_min": 30}, {"work_hours_gt": 8, "break_min": 60}],
    "probation_cut": {"max_rate": 0.10, "max_months": 3, "min_contract_years": 1, "excluded": "단순노무업무(고용노동부 고시 직종)"},
    "small_business_threshold": 5,
}

CONTRACT_TYPES = [
    {"id": "LAB_PT", "name": "근로계약(단시간·알바)", "standard_forms": ["L1", "L4"],
     "aihub": ["아르바이트계약서", "근로(고용)계약서"]},
    {"id": "LAB_FX", "name": "근로계약(기간제·기간없음)", "standard_forms": ["L2", "L3", "L5", "L6"],
     "aihub": ["근로(고용)계약서"]},
    {"id": "LEASE", "name": "주택임대차(원룸·오피스텔 주거용)", "standard_forms": ["H1", "H2", "H2a", "H3*(민간임대)"],
     "aihub": ["주거용부동산임대계약서"]},
    {"id": "LOAN", "name": "금전차용·보증", "standard_forms": ["D1", "D2"], "aihub": []},
]

# 조항 칸: AI Hub content_label과 표준계약서 항목을 함께 매핑
SLOTS = [
    # 근로
    ("S_L_PARTY", "LAB", "당사자", ["계약의 당사자", "사용자의 인적사항", "근로자의 인적사항"], "서문"),
    ("S_L_TERM", "LAB", "근로계약기간·개시일", ["근로 계약 기간", "계약기간"], "1."),
    ("S_L_PLACE", "LAB", "근무장소·업무", ["근무 장소", "담당 업무"], "2.~3."),
    ("S_L_HOURS", "LAB", "근로시간·휴게", ["근로 시간"], "4."),
    ("S_L_DAYS", "LAB", "근로일·휴일(주휴)", ["휴일"], "4.~5."),
    ("S_L_WAGE", "LAB", "임금(금액·구성·가산)", ["임금액", "기타급여"], "5./6."),
    ("S_L_PAY", "LAB", "임금 지급일·지급방법", ["임금 지급일", "임금 지급 방법"], "5./6."),
    ("S_L_LEAVE", "LAB", "연차유급휴가", ["휴가"], "6./7."),
    ("S_L_INS", "LAB", "사회보험", ["사회보험의 가입"], "7./8."),
    ("S_L_COPY", "LAB", "계약서 교부", ["계약서의 교부"], "8./9."),
    ("S_L_PROB", "LAB", "수습", ["수습 기간"], "(표준 없음)"),
    ("S_L_END", "LAB", "퇴직·해고", ["근로계약의 종료", "퇴직 절차", "퇴직금", "계약의 해제, 해지"], "(표준 없음)"),
    ("S_L_PENALTY", "LAB", "손해배상·위약", ["손해배상의 예정", "위약벌"], "(표준 없음)"),
    ("S_L_SPECIAL", "LAB", "기타·특약", ["기타", "계약의 내용"], "10./11."),
    # 임대차
    ("S_H_PARTY", "LEASE", "당사자·서명", ["계약의 당사자", "임대인의 인적사항", "임차인의 인적사항", "임대인의 기명날인", "임차인의 기명날인"], "말미"),
    ("S_H_OBJ", "LEASE", "목적물 표시", ["부동산의 표시"], "1."),
    ("S_H_MONEY", "LEASE", "보증금·차임·지급일정", ["임차보증금", "차임", "대금 지급 방법"], "제1조"),
    ("S_H_MGMT", "LEASE", "관리비", ["관리비 및 제세공과금"], "제1조(관리비)"),
    ("S_H_TERM", "LEASE", "임대차기간·갱신", ["계약기간", "기간의 갱신"], "제2조"),
    ("S_H_ADJ", "LEASE", "차임·보증금 증감", ["임대료 및 관리비의 조정"], "(표준 없음)"),
    ("S_H_REPAIR", "LEASE", "수선·유지보수", ["유지 보수의무", "시설물의 개조 및 설치"], "제3조/특약"),
    ("S_H_RESTORE", "LEASE", "원상회복", ["원상회복의무"], "제7조"),
    ("S_H_TERMIN", "LEASE", "해제·해지", ["계약의 해제, 해지"], "제5~6조"),
    ("S_H_PENALTY", "LEASE", "위약금·손해배상", ["손해배상의 예정", "연체이자"], "제8조"),
    ("S_H_RIGHTS", "LEASE", "대항력·우선변제·정보제공", [], "확인사항/특약"),
    ("S_H_SPECIAL", "LEASE", "특약사항", ["기타", "금지사항", "비용상환 청구권 포기 특약", "임대목적물 출입권 및 출입통제권"], "특약"),
    # 차용
    ("S_D_PARTY", "LOAN", "당사자·서명", ["채권자의 인적사항", "채무자의 인적사항", "채권자의 기명날인", "채무자의 기명날인"], "서문/말미"),
    ("S_D_PRINC", "LOAN", "원금·지급", ["계약의 내용"], "제1조"),
    ("S_D_INT", "LOAN", "이자", [], "이자"),
    ("S_D_REPAY", "LOAN", "변제기·변제방법", ["채무의 이행", "채무이행", "변제충당"], "변제"),
    ("S_D_DEFAULT", "LOAN", "지연손해금·기한이익상실", ["계약의 해제, 해지"], "(서식별)"),
    ("S_D_COLL", "LOAN", "담보·대물변제", [], "(서식별)"),
    ("S_D_GUAR", "LOAN", "보증", ["보증"], "보증인"),
]

def C(id, types, slot, cat, sev, title, cond, detect, basis=None, scope=None, inject=None, params=None):
    return {"id": id, "contract_types": types, "slot": slot, "category": cat, "severity": sev,
            "title": title, "condition": cond, "detect": detect, "legal_basis": basis or [],
            "scope_conditions": scope or [], "inject_examples": inject or [], "params": params or []}

LAB = ["LAB_PT", "LAB_FX"]
CHECKS = [
 # ---------- 근로: 누락 ----------
 C("L-M01", LAB, "S_L_WAGE", "missing", "violation", "임금 금액·계산방법 미기재",
   "임금액 또는 구성항목·계산방법이 서면에 없음", "rule+model",
   [L("근기법", "제17조"), L("기간제법", "제17조")], inject=["(임금 항목 삭제)"]),
 C("L-M02", LAB, "S_L_PAY", "missing", "violation", "임금 지급일·지급방법 미기재",
   "지급일 또는 지급방법이 없음", "rule", [L("근기법", "제17조"), L("기간제법", "제17조")]),
 C("L-M03", LAB, "S_L_HOURS", "missing", "violation", "소정근로시간 미기재",
   "시작·종료 시각 또는 1일/1주 시간이 없음", "rule", [L("근기법", "제17조"), L("기간제법", "제17조")]),
 C("L-M04", LAB, "S_L_HOURS", "missing", "violation", "휴게시간 미기재",
   "휴게시간 기재 없음", "rule", [L("기간제법", "제17조")]),
 C("L-M05", ["LAB_PT"], "S_L_DAYS", "missing", "violation", "단시간: 근로일·근로일별 근로시간 미기재",
   "단시간근로자 계약인데 요일별 근로일·시간이 없음", "rule", [L("기간제법", "제17조", "단시간근로자 서면명시 사항")]),
 C("L-M06", LAB, "S_L_DAYS", "missing", "violation", "휴일(주휴일) 미기재",
   "주휴일 기재 없음(주 15시간 미만이면 해당 없음 표기 가능)", "rule", [L("근기법", "제17조"), L("근기법", "제55조")]),
 C("L-M07", LAB, "S_L_LEAVE", "missing", "violation", "연차유급휴가 미기재",
   "연차 관련 기재 없음", "rule", [L("근기법", "제17조"), L("근기법", "제60조")],
   scope=["상시 5인 이상(5인 미만은 연차 미적용)"]),
 C("L-M08", ["LAB_FX", "LAB_PT"], "S_L_TERM", "missing", "violation", "근로계약기간(기간제) 미기재",
   "기간제인데 종료일 없음", "rule", [L("기간제법", "제17조")]),
 C("L-M09", LAB, "S_L_PLACE", "missing", "violation", "근무장소·업무 미기재",
   "근무장소 또는 업무내용 없음", "rule", [L("근기령", "제8조"), L("기간제법", "제17조")]),
 C("L-M10", LAB, "S_L_COPY", "missing", "info", "계약서 교부 조항 없음",
   "교부 문구 없음(교부 의무 자체는 법정 의무)", "rule", [L("근기법", "제17조")]),
 # ---------- 근로: 독소 ----------
 C("L-T01", LAB, "S_L_WAGE", "toxic", "invalid", "최저임금 미달 시급",
   "시급(또는 환산 시급) < 계약 연도 최저임금", "rule",
   [L("최임법", "제6조")], params=["min_wage_hourly"],
   inject=["시급은 8,500원으로 한다.", "일급 60,000원(1일 8시간 근무)"]),
 C("L-T02", LAB, "S_L_PROB", "toxic", "invalid", "수습 감액 요건 위반",
   "1년 미만 계약에 감액 / 3개월 초과 감액 / 10% 초과 감액 / 단순노무직 감액", "rule+model",
   [L("최임법", "제5조"), L("최임령", "제3조")], params=["probation_cut", "min_wage_hourly"],
   inject=["수습기간 3개월 동안은 최저임금의 80%를 지급한다.", "6개월 수습기간 동안 시급의 90%를 지급한다."]),
 C("L-T03", LAB, "S_L_PENALTY", "toxic", "invalid", "위약금·손해배상 예정(지각·중도퇴사 벌금)",
   "근로계약 불이행에 대한 위약금 또는 손해배상액을 미리 정함", "model",
   [L("근기법", "제20조")],
   inject=["지각 1회당 10,000원을 급여에서 차감한다.", "계약기간 내 퇴사 시 1개월분 급여를 위약금으로 지급한다."]),
 C("L-T04", LAB, "S_L_PAY", "toxic", "invalid", "임금에서 임의 공제",
   "유니폼비·파손 변상·교육비 등을 임금에서 일방 공제", "model",
   [L("근기법", "제43조")],
   inject=["유니폼 비용 30,000원은 첫 달 급여에서 공제한다.", "매장 기물 파손 시 해당 금액을 급여에서 공제한다."]),
 C("L-T05", LAB, "S_L_HOURS", "toxic", "violation", "휴게시간 미달·미부여",
   "4시간 근로에 30분, 8시간에 1시간 미만이거나 '부여하지 않을 수 있다'", "rule+model",
   [L("근기법", "제54조")], params=["break_rule"],
   inject=["휴게시간은 업무 사정에 따라 부여하지 않을 수 있다.", "근무시간 09:00~18:00(휴게 30분)"]),
 C("L-T06", LAB, "S_L_DAYS", "toxic", "violation", "주 15시간 이상인데 주휴 배제",
   "1주 소정근로 15시간 이상인데 주휴일·주휴수당을 없앰", "rule+model",
   [L("근기법", "제55조"), L("근기법", "제18조", "제3항: 15시간 미만 적용 제외"), L("근기령", "제30조")],
   params=["weekly_holiday_threshold_hours"],
   inject=["주휴수당은 지급하지 않는다.(주 5일, 1일 5시간 근무)"]),
 C("L-T07", ["LAB_PT"], "S_L_WAGE", "toxic", "violation", "단시간 초과근로 가산임금 배제",
   "소정근로시간 초과 근로에 50% 가산 없음을 정함", "model",
   [L("기간제법", "제6조")], scope=["상시 5인 이상 여부 확인 필요"],
   inject=["정해진 시간 외 추가 근무는 동일 시급으로 계산한다."]),
 C("L-T08", LAB, "S_L_WAGE", "toxic", "violation", "연장·야간·휴일 가산수당 배제",
   "연장·야간·휴일근로 가산 없음을 정함", "model",
   [L("근기법", "제56조")], scope=["상시 5인 이상만 적용"],
   inject=["야간 근무도 주간과 동일한 시급을 적용한다."]),
 C("L-T09", LAB, "S_L_HOURS", "toxic", "unfavorable", "근로시간 일방 변경 권한",
   "사용자가 업무 사정에 따라 근로시간·근로일을 일방 변경할 수 있게 함", "model",
   [L("근기법", "제4조", "근로조건 대등결정"), L("근기법", "제17조")],
   inject=["근무시간은 매장 사정에 따라 사업주가 변경할 수 있다."]),
 C("L-T10", LAB, "S_L_END", "toxic", "invalid", "퇴직금 분할·포함 지급 약정",
   "월급·시급에 퇴직금을 포함하거나 매월 나눠 지급", "model",
   [L("퇴직급여법", "제8조"), L("퇴직급여법", "제9조")],
   scope=["계속근로 1년 이상·주 15시간 이상일 때 퇴직금 발생"],
   inject=["퇴직금은 매월 급여에 포함하여 지급한 것으로 본다."]),
 C("L-T11", LAB, "S_L_END", "toxic", "violation", "예고 없는 해고 조항",
   "사용자가 언제든 즉시 해고할 수 있게 함", "model",
   [L("근기법", "제26조", "해고예고 30일"), L("근기법", "제23조", "정당한 이유: 5인 이상")],
   inject=["사업주는 필요시 근로자를 즉시 해고할 수 있다."]),
 C("L-T12", LAB, "S_L_INS", "toxic", "violation", "사회보험 미가입 합의",
   "4대보험 미가입을 합의하거나 보험료 대신 금액 지급", "model",
   [L("근기법", "제17조", "근거 보완 필요: 고용보험법·산재보험법 등 미수집")],
   scope=["가입 예외 요건(소정근로 월 60시간 미만 등) 확인 필요"],
   inject=["4대보험은 가입하지 않으며 대신 시급에 500원을 더한다."]),
 C("L-T13", LAB, "S_L_SPECIAL", "toxic", "invalid", "강제저축·저축금 관리",
   "근로계약에 덧붙여 저축 또는 저축금 관리를 정함", "model", [L("근기법", "제22조")]),
 C("L-T14", LAB, "S_L_SPECIAL", "toxic", "invalid", "전차금 상계",
   "선불금을 임금과 상계", "model", [L("근기법", "제21조")]),
 # ---------- 근로: 불일치 ----------
 C("L-I01", LAB, "S_L_HOURS", "inconsistent", "info", "근로시간 합계 불일치",
   "요일별 시간 합 ≠ 1주 소정시간 / 시작·종료·휴게로 계산한 시간 ≠ 기재 시간", "rule"),
 C("L-I02", LAB, "S_L_WAGE", "inconsistent", "info", "임금 환산 불일치",
   "시급×시간과 월(일)급 기재 금액이 맞지 않음", "rule"),
 C("L-I03", LAB, "S_L_TERM", "inconsistent", "info", "계약기간 날짜 오류",
   "종료일 < 시작일, 존재하지 않는 날짜", "rule"),
 C("L-I04", LAB, "S_L_WAGE", "inconsistent", "info", "숫자·한글 금액 불일치", "숫자 금액과 한글 금액이 다름", "rule"),
 C("L-I05", LAB, "S_L_SPECIAL", "inconsistent", "info", "본문·특약 충돌", "본문 조건과 특약이 서로 다름", "model"),
 # ---------- 근로: 확인 불가 ----------
 C("L-U01", LAB, "S_L_SPECIAL", "uncheckable", "info", "사업장 상시근로자 수(5인) 확인 필요",
   "가산수당·연차·해고제한 적용 여부가 5인 기준에 따라 달라짐", "rule",
   [L("근기법", "제11조"), L("근기령", "제7조", "별표1")], params=["small_business_threshold"]),

 # ---------- 임대차: 누락 ----------
 C("H-M01", ["LEASE"], "S_H_MONEY", "missing", "violation", "보증금·차임·지급일정 미기재",
   "보증금/월차임 금액 또는 계약금·잔금 일정 없음", "rule", []),
 C("H-M02", ["LEASE"], "S_H_TERM", "missing", "violation", "임대차기간 미기재", "시작·종료일 없음", "rule",
   [L("주임법", "제4조")]),
 C("H-M03", ["LEASE"], "S_H_OBJ", "missing", "violation", "목적물 표시 미기재", "주소·호수·면적 없음", "rule", []),
 C("H-M04", ["LEASE"], "S_H_MGMT", "missing", "caution", "관리비 금액·항목 미기재",
   "관리비 여부·금액·포함 항목 없음", "rule", [], scope=["2023 표준계약서는 관리비 기재란 있음"]),
 C("H-M05", ["LEASE"], "S_H_REPAIR", "missing", "caution", "수선 부담 범위 미기재", "누가 어떤 수리를 하는지 없음", "rule",
   [L("민법", "제623조")]),
 C("H-M06", ["LEASE"], "S_H_MONEY", "missing", "caution", "보증금 반환 시기·방법 미기재",
   "종료 시 반환 시기 없음", "rule", [L("민법", "제536조", "동시이행")]),
 C("H-M07", ["LEASE"], "S_H_RIGHTS", "missing", "caution", "선순위 권리 처리 특약 없음",
   "근저당 말소·증액 금지 등 특약 없음(등기부 확인 필요)", "rule", []),
 C("H-M08", ["LEASE"], "S_H_RIGHTS", "missing", "caution", "임대인 정보 제시(선순위 확정일자·미납세금) 확인란 없음",
   "2023 표준계약서의 정보 제시 확인 내용 없음", "rule", [L("주임법", "제3조의7", "시행 2023 — 원문 확인 필요")]),
 C("H-M09", ["LEASE"], "S_H_TERMIN", "missing", "caution", "중도해지 조건 미기재", "중도 퇴거 시 처리 없음", "rule", []),
 # ---------- 임대차: 독소 ----------
 C("H-T01", ["LEASE"], "S_H_TERM", "toxic", "invalid", "2년 미만 기간을 임차인에게 불리하게 강제",
   "2년 미만 약정 + 기간 종료 시 무조건 퇴거 등", "rule+model",
   [L("주임법", "제4조"), L("주임법", "제10조")],
   inject=["임대차 기간은 1년으로 하며, 만료 시 임차인은 즉시 퇴거한다."]),
 C("H-T02", ["LEASE"], "S_H_TERM", "toxic", "invalid", "계약갱신요구권 포기",
   "갱신요구권 행사 포기·배제", "model", [L("주임법", "제6조의3"), L("주임법", "제10조")],
   inject=["임차인은 계약갱신요구권을 행사하지 않기로 한다."]),
 C("H-T03", ["LEASE"], "S_H_ADJ", "toxic", "invalid", "5% 초과 증액 약정",
   "갱신·존속 중 차임·보증금 5% 초과 증액 또는 1년 내 재증액", "rule+model",
   [L("주임법", "제7조"), L("주임령", "제8조")], params=["lease_increase_cap"],
   inject=["월세는 매년 10%씩 인상한다."]),
 C("H-T04", ["LEASE"], "S_H_TERMIN", "toxic", "invalid", "1회 연체 즉시 해지",
   "차임 1회(1기) 연체로 해지 가능", "model", [L("민법", "제640조"), L("민법", "제652조")],
   inject=["월세를 1회라도 연체하면 임대인은 즉시 계약을 해지할 수 있다."]),
 C("H-T05", ["LEASE"], "S_H_MONEY", "toxic", "unfavorable", "새 임차인 입주 후 보증금 반환",
   "보증금 반환을 신규 임차인 입주·계약을 조건으로 함", "model",
   [L("민법", "제536조"), L("주임법", "제10조", "적용 여부 검토 필요")],
   inject=["보증금은 새로운 임차인이 입주한 후에 반환한다."]),
 C("H-T06", ["LEASE"], "S_H_RESTORE", "toxic", "unfavorable", "통상 손모까지 원상복구 부담",
   "자연 마모·노후까지 임차인 부담, 전체 도배·장판 교체 비용 전가", "model",
   [L("민법", "제615조"), L("민법", "제654조"), L("판례", "통상손모 관련 — 판례 데이터에서 확정")],
   inject=["퇴거 시 임차인은 사용기간과 관계없이 도배·장판 전체 교체 비용을 부담한다."]),
 C("H-T07", ["LEASE"], "S_H_REPAIR", "toxic", "unfavorable", "대규모 수선까지 임차인 부담",
   "보일러·배관 등 주요 설비 수리비 전부 임차인 부담", "model",
   [L("민법", "제623조"), L("판례", "대법원 94다34692 — 확인 필요")],
   inject=["보일러, 배관 등 모든 시설의 수리비는 임차인이 부담한다."]),
 C("H-T08", ["LEASE"], "S_H_PENALTY", "toxic", "unfavorable", "과다한 위약금·보증금 몰수",
   "중도해지·특약 위반 시 보증금 몰수, 수개월분 차임 위약금", "model",
   [L("민법", "제398조", "제2항 감액")],
   inject=["임차인이 특약을 위반하면 보증금 전액은 임대인에게 귀속된다."]),
 C("H-T09", ["LEASE"], "S_H_RIGHTS", "toxic", "invalid", "전입신고·확정일자·임차권등기 금지",
   "대항력·우선변제 수단을 금지하거나 포기", "model",
   [L("주임법", "제3조"), L("주임법", "제3조의2"), L("주임법", "제3조의3"), L("주임법", "제10조")],
   inject=["임차인은 전입신고를 하지 않기로 한다."]),
 C("H-T10", ["LEASE"], "S_H_SPECIAL", "toxic", "unfavorable", "임대인 일방 해지·무단 출입",
   "임대인이 언제든 해지하거나 사전 통지 없이 출입 가능", "model",
   [L("주임법", "제4조"), L("주임법", "제10조")],
   inject=["임대인은 필요한 경우 언제든지 방에 출입할 수 있다."]),
 C("H-T11", ["LEASE"], "S_H_SPECIAL", "toxic", "caution", "필요비·유익비 상환청구권 포기",
   "비용상환청구권 포기 특약(임의규정이라 유효할 수 있음 — 주의 안내)", "model",
   [L("민법", "제626조")],
   inject=["임차인은 퇴거 시 설치한 시설에 대한 비용을 청구하지 않는다."]),
 # ---------- 임대차: 불일치 ----------
 C("H-I01", ["LEASE"], "S_H_MONEY", "inconsistent", "info", "계약금+중도금+잔금 ≠ 보증금", "합계 불일치", "rule"),
 C("H-I02", ["LEASE"], "S_H_MONEY", "inconsistent", "info", "숫자·한글 금액 불일치", "", "rule"),
 C("H-I03", ["LEASE"], "S_H_TERM", "inconsistent", "info", "기간 날짜 오류·기간 표기 불일치", "", "rule"),
 C("H-I04", ["LEASE"], "S_H_PARTY", "inconsistent", "info", "당사자 이름 불일치(본문 vs 서명란)", "", "rule"),
 C("H-I05", ["LEASE"], "S_H_SPECIAL", "inconsistent", "info", "본문·특약 충돌", "", "model"),
 # ---------- 임대차: 확인 불가 ----------
 C("H-U01", ["LEASE"], "S_H_RIGHTS", "uncheckable", "info", "등기부 확인 필요(소유자·선순위 근저당)",
   "계약서만으로 확인 불가 — 고정 안내", "rule", []),
 C("H-U02", ["LEASE"], "S_H_OBJ", "uncheckable", "info", "건축물대장 확인 필요(용도·위반건축물)",
   "계약서만으로 확인 불가 — 고정 안내", "rule", []),

 # ---------- 차용·보증 ----------
 C("D-M01", ["LOAN"], "S_D_PRINC", "missing", "violation", "원금 미기재", "", "rule", []),
 C("D-M02", ["LOAN"], "S_D_REPAY", "missing", "caution", "변제기 미기재", "갚을 날짜 없음", "rule", [L("민법", "제603조")]),
 C("D-M03", ["LOAN"], "S_D_INT", "missing", "caution", "이자 약정 미기재", "이자 여부·이율 없음(약정 없으면 무이자)", "rule", [L("민법", "제600조")]),
 C("D-M04", ["LOAN"], "S_D_PARTY", "missing", "violation", "당사자 특정·서명 누락", "", "rule", []),
 C("D-T01", ["LOAN"], "S_D_INT", "toxic", "invalid", "최고이자율(연 20%) 초과",
   "약정 이율 > 연 20%(초과분 무효)", "rule", [L("이자법", "제2조"), L("이자규정", "본문")],
   params=["max_interest_rate_annual"], inject=["이자는 월 3%로 한다."]),
 C("D-T02", ["LOAN"], "S_D_INT", "toxic", "unfavorable", "선이자 공제",
   "빌려줄 때 이자를 미리 떼고 지급", "rule+model", [L("이자법", "제3조", "간주이자 — 확인 필요")],
   inject=["대여금 100만원 중 이자 10만원을 공제하고 90만원을 지급한다."]),
 C("D-T03", ["LOAN"], "S_D_DEFAULT", "toxic", "unfavorable", "과다 지연손해금",
   "연체 시 고율 지연손해금", "rule+model", [L("이자법", "제6조", "배상액 감액 — 확인 필요"), L("민법", "제398조")]),
 C("D-T04", ["LOAN"], "S_D_DEFAULT", "toxic", "caution", "1회 연체 시 기한이익 상실",
   "한 번 연체로 잔액 전부 즉시 상환", "model", [], inject=["1회라도 상환이 지연되면 남은 금액 전부를 즉시 갚는다."]),
 C("D-T05", ["LOAN"], "S_D_COLL", "toxic", "invalid", "원리금 초과 대물변제 예약",
   "갚지 못하면 원리금보다 비싼 물건을 넘김", "model", [L("민법", "제607조"), L("민법", "제608조")],
   inject=["기한 내 갚지 못하면 채무자의 노트북과 자전거의 소유권은 채권자에게 넘어간다."]),
 C("D-G01", ["LOAN"], "S_D_GUAR", "missing", "invalid", "보증 서면·기명날인 누락",
   "보증인의 서명 또는 기명날인 있는 서면 없음(효력 없음)", "rule",
   [L("민법", "제428조의2"), L("보증법", "제3조")]),
 C("D-G02", ["LOAN"], "S_D_GUAR", "missing", "invalid", "보증 최고액 미기재",
   "보증채무 최고액이 서면에 특정되지 않음", "rule",
   [L("민법", "제428조의3", "근보증"), L("보증법", "제4조", "조문 번호 확인 필요")]),
 C("D-G03", ["LOAN"], "S_D_GUAR", "missing", "caution", "보증기간 미기재",
   "기간 약정 없음(법정 기간 적용)", "rule", [L("보증법", "제7조", "확인 필요")]),
 C("D-I01", ["LOAN"], "S_D_PRINC", "inconsistent", "info", "숫자·한글 금액 불일치", "", "rule"),
 C("D-I02", ["LOAN"], "S_D_INT", "inconsistent", "info", "이자 계산 불일치", "이율과 이자 금액이 맞지 않음", "rule"),
 C("D-I03", ["LOAN"], "S_D_REPAY", "inconsistent", "info", "날짜 오류", "변제기 < 대여일", "rule"),
]

def build():
    slots = [{"id": s[0], "domain": s[1], "name": s[2], "aihub_labels": s[3], "standard_ref": s[4]} for s in SLOTS]
    slot_ids = {s["id"] for s in slots}
    for c in CHECKS:
        assert c["slot"] in slot_ids, c["id"]
    ids = [c["id"] for c in CHECKS]
    assert len(ids) == len(set(ids)), "duplicate id"
    # 그래프 엣지
    edges = []
    for ct in CONTRACT_TYPES:
        dom = "LAB" if ct["id"].startswith("LAB") else ct["id"]
        for s in slots:
            if s["domain"] == dom:
                edges.append({"from": ct["id"], "to": s["id"], "rel": "has_slot"})
    law_nodes = {}
    for c in CHECKS:
        edges.append({"from": c["slot"], "to": c["id"], "rel": "has_check"})
        for b in c["legal_basis"]:
            lid = f'{b["law"]}:{b["article"]}'
            law_nodes[lid] = {"id": lid, "law_short": b["law"], "law_full": LAWS.get(b["law"], b["law"]),
                              "article": b["article"], "verified": False,
                              "collected": b["law"] not in NOT_COLLECTED and b["law"] != "판례"}
            edges.append({"from": c["id"], "to": lid, "rel": "based_on"})
    return {
        "version": "0.1-draft", "status": "조문 미대조(verified=false). 법령 API 원문으로 확인 필요.",
        "params": PARAMS, "laws": LAWS, "not_collected_laws": NOT_COLLECTED,
        "contract_types": CONTRACT_TYPES, "slots": slots, "checks": CHECKS,
        "law_nodes": list(law_nodes.values()), "edges": edges,
    }

def main():
    os.makedirs(OUT, exist_ok=True)
    g = build()
    with open(os.path.join(OUT, "catalog_v0.1.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    slotname = {s["id"]: s["name"] for s in g["slots"]}
    with open(os.path.join(OUT, "catalog_v0.1_checks.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "계약유형", "조항칸", "유형", "심각도", "항목", "판정 조건", "탐지", "근거(미대조)", "적용 조건", "주입 예시"])
        for c in g["checks"]:
            w.writerow([c["id"], ",".join(c["contract_types"]), slotname[c["slot"]], c["category"], c["severity"],
                        c["title"], c["condition"], c["detect"],
                        "; ".join(f'{LAWS.get(b["law"], b["law"])} {b["article"]}' + (f' ({b["note"]})' if b.get("note") else "") for b in c["legal_basis"]),
                        "; ".join(c["scope_conditions"]), " / ".join(c["inject_examples"])])
    # 요약 출력
    from collections import Counter
    print("checks", len(g["checks"]), "slots", len(g["slots"]), "law_nodes", len(g["law_nodes"]), "edges", len(g["edges"]))
    print(Counter((c["contract_types"][0][:3], c["category"]) for c in g["checks"]))
    print("not collected law refs:", sorted({n["id"] for n in g["law_nodes"] if not n["collected"]}))

if __name__ == "__main__":
    main()
