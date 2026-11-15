# LAB_GUIDE_CHECK

## 실행 명령

```text
hwp5txt datasets\work\표준_근로계약서(7종)(19.6월).hwp  > app_rag\criteria\_std_forms\_raw_all.txt
python app_rag\criteria\_extract_laws.py
python app_rag\criteria\_extract_laws2.py
python app_rag\criteria\_build_lab_docs.py
```

hwp5txt returncode=0, raw_chars=6319 (추출 성공).

## 1. 표준계약서 3종 항목 표

# 표준근로계약서 3종 항목

## 01_기간정함없음.txt (1078자)
| 번호 | 항목 |
|---|---|
| 1 | 근로개시일 |
| 2 | 근무장소 |
| 3 | 업무의 내용 |
| 4 | 소정근로시간(휴게시간) |
| 5 | 근무일/휴일·주휴일 |
| 6 | 임금 |
| 7 | 연차유급휴가 |
| 8 | 사회보험 적용여부 |
| 9 | 근로계약서 교부 |
| 10 | 근로계약·취업규칙 성실이행 |
| 11 | 기타(근로기준법령) |

## 02_기간정함있음.txt (1096자)
| 번호 | 항목 |
|---|---|
| 1 | 근로계약기간 |
| 2 | 근무장소 |
| 3 | 업무의 내용 |
| 4 | 소정근로시간(휴게시간) |
| 5 | 근무일/휴일·주휴일 |
| 6 | 임금 |
| 7 | 연차유급휴가 |
| 8 | 사회보험 적용여부 |
| 9 | 근로계약서 교부 |
| 10 | 근로계약·취업규칙 성실이행 |
| 11 | 기타(근로기준법령) |

## 03_단시간근로자.txt (1108자)
| 번호 | 항목 |
|---|---|
| 1 | 근로개시일(기간 선택 기재) |
| 2 | 근무장소 |
| 3 | 업무의 내용 |
| 4 | 근로일 및 근로일별 근로시간·주휴일 |
| 5 | 임금·초과근로 가산임금률 |
| 6 | 연차유급휴가(비례) |
| 7 | 사회보험 적용여부 |
| 8 | 근로계약서 교부 |
| 9 | 근로계약·취업규칙 성실이행 |
| 10 | 기타(근로기준법령) |


## 3. 카드 글자 수

| id | title | 글자 수 | 500자 이내 |
|---|---|---:|---|
| LAB-TERM | 계약기간 | 158 | Y |
| LAB-PLACE | 근무장소 | 153 | Y |
| LAB-DUTY | 업무 내용 | 145 | Y |
| LAB-REST | 근로시간·휴게 | 214 | Y |
| LAB-HOLIDAY | 휴일·주휴 | 200 | Y |
| LAB-WAGE | 임금(구성·계산·지급) | 171 | Y |
| LAB-MINWAGE | 최저임금 | 253 | Y |
| LAB-PROBATION | 수습 | 164 | Y |
| LAB-OT | 연장·야간·휴일 가산 | 160 | Y |
| LAB-PT-OT | 단시간 초과근로 가산 | 152 | Y |
| LAB-ANNUAL | 연차유급휴가 | 162 | Y |
| LAB-INSURE | 사회보험 | 158 | Y |
| LAB-DELIVER | 계약서 교부 | 106 | Y |
| LAB-DISMISS | 해고 예고 | 151 | Y |
| LAB-SEVERANCE | 퇴직금 | 128 | Y |
| LAB-PENALTY | 위약금·손해배상 예정 | 113 | Y |
| LAB-OFFSET | 전차금 상계·강제 저축 | 144 | Y |
| LAB-WAIVER | 법 적용 배제·신고 금지·취업규칙 불리 변경 | 197 | Y |

카드 수: 18, 최대 글자: 253 (`LAB-MINWAGE`)

### match_keywords 겹침

| 키워드 | 카드들 |
|---|---|
| 시급 | LAB-WAGE, LAB-MINWAGE |

## 4. toxic_code → 카드

| code | violation_name | card |
|---|---|---|
| L-I03 | 계약기간 날짜 오류·불명확 | LAB-TERM |
| L-M10 | 근로계약서 미교부 | LAB-DELIVER |
| L-T01 | 최저임금 미달 / 수습 감액 요건 위반 | LAB-MINWAGE / LAB-PROBATION |
| L-T02 | 최저임금 미달 / 수습 감액 요건 위반 | LAB-MINWAGE / LAB-PROBATION |
| L-T03 | 전차금 상계 / 위약금·손해배상액 예정 | LAB-PENALTY / LAB-OFFSET |
| L-T04 | 임금 임의 공제·직접 지급 위반 | LAB-WAGE |
| L-T05 | 휴게시간 미부여·부족 | LAB-REST |
| L-T06 | 주휴일 배제 | LAB-HOLIDAY |
| L-T07 | 단시간 초과근로 가산 배제 | LAB-PT-OT |
| L-T08 | 연장·야간·휴일 가산 배제 | LAB-OT |
| L-T09 | 근로시간 일방 변경 가능성 | LAB-REST |
| L-T10 | 퇴직금 포함·포기 약정 | LAB-SEVERANCE |
| L-T11 | 해고 예고 없음 | LAB-DISMISS |
| L-T12 | 사회보험 미가입·위장 프리랜서 | LAB-INSURE |
| L-T13 | 위약금·손해배상액 예정 / 강제 저축·저축금 관리 | LAB-PENALTY / LAB-OFFSET |
| L-T14 | 전차금 상계 | LAB-OFFSET |
| L-T15 | 연차유급휴가 미부여·포기 | LAB-ANNUAL |
| L-T16 | 근무장소 일방 변경 가능성 | LAB-PLACE |
| L-T17 | 업무 일방 추가 가능성 | LAB-DUTY |
| L-T18 | 법 적용 배제·신고 금지 | LAB-WAIVER |
| L-T19 | 취업규칙 일방 불리 변경 | LAB-WAIVER |

### 카드가 없는 코드

- 없음 (목록의 모든 코드가 하나 이상의 카드에 매핑됨)

## [미확인] 목록

1. 시행령 별표1 본문 텍스트 없음 (제목만)
2. 기간제법
3. 근로자퇴직급여 보장법
4. 4대보험 개별법
5. 신고·진정 방해 세부 제재
6. 리포트 상단 임계값 2/3 (UX 제안)

## corpus에 없어 missing_basis로 남긴 ID

| card | missing_basis |
|---|---|
| LAB-REST | law:근로기준법:50 |
| LAB-PT-OT | 기간제법_가산_조항 |
| LAB-INSURE | 고용보험법, 국민연금법, 건강보험법, 산업재해보상보험법 |
| LAB-SEVERANCE | 근로자퇴직급여 보장법 |
| LAB-WAIVER | law:근로기준법:94 |

## 별표1 확인 결과

- 파일: `근로기준법 시행령_body_MST.json`
- 별표 키 존재: True, 별표1 제목: True
- 본문 텍스트 샘플: False → **[미확인]으로 처리**
- 제목 예시: ['상시 4명 이하의 근로자를 사용하는 사업 또는 사업장에 적용하는 법 규정(제7조 관련)', '단시간근로자의 근로조건 결정기준 등에 관한 사항(제9조제1항 관련)']
