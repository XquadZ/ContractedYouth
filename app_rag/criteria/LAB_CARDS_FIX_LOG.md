# LAB_CARDS_FIX_LOG

백업: `LAB_GUIDE_v1.md`, `LAB_cards_v1.yaml`
파이프라인 연결: 하지 않음

## 1. 라벨 이동 (violation → check_if)

| 카드 | 전 | 후 |
|---|---|---|
| LAB-TERM | violation에 「시작일이 종료일보다 뒤」 | check_if 「날짜가 없는 날이거나 앞뒤가 바뀜 → 실제 시작·종료일」. violation에는 종료일 공란만 유지 |
| LAB-PLACE | violation 「일방 근무지 변경」 | check_if로 이동(+ 변경 범위·업무상 필요·불이익·협의). violation 비움 |
| LAB-DUTY | violation 「일방 업무 추가·변경」 | check_if로 이동(동일 사실). violation 비움 |

가이드 §1·§2·§3 본문도 동일하게 수정.

## 2. needs_facts 축소

- **총 needs_facts 개수(전→후):** 25 → 24

| 카드 | 전 needs_facts | 후 needs_facts |
|---|---|---|
| LAB-TERM | ['계약_유형'] | ['계약_유형'] |
| LAB-PLACE | [] | [] |
| LAB-DUTY | [] | [] |
| LAB-REST | ['일_근로시간', '주_근로시간', '상시근로자수'] | ['일_근로시간', '주_근로시간', '상시근로자수'] |
| LAB-HOLIDAY | ['주_소정근로시간', '상시근로자수'] | ['주_소정근로시간'] |
| LAB-WAGE | [] | [] |
| LAB-MINWAGE | ['시급_또는_월급', '소정근로시간', '수습여부', '계약기간_1년이상', '단순노무여부', '적용연도'] | ['시급_또는_월급', '소정근로시간', '수습여부', '계약기간_1년이상', '단순노무여부', '적용연도'] |
| LAB-PROBATION | ['수습여부', '계약기간_1년이상', '단순노무여부'] | ['수습여부', '계약기간_1년이상', '단순노무여부'] |
| LAB-OT | ['상시근로자수'] | ['상시근로자수'] |
| LAB-PT-OT | ['단시간여부', '약정_소정근로'] | ['단시간여부', '약정_소정근로', '상시근로자수'] |
| LAB-ANNUAL | ['주_소정근로시간', '상시근로자수'] | ['주_소정근로시간', '상시근로자수'] |
| LAB-INSURE | ['근로자성'] | ['근로자성'] |
| LAB-DELIVER | [] | [] |
| LAB-DISMISS | ['계속근로기간', '상시근로자수'] | ['계속근로기간'] |
| LAB-SEVERANCE | ['계속근로기간', '주_소정근로시간'] | ['계속근로기간', '주_소정근로시간'] |
| LAB-PENALTY | [] | [] |
| LAB-OFFSET | [] | [] |
| LAB-WAIVER | [] | [] |

### 카드 사실 이름 ↔ facts.py 키

| 카드 사실 이름 | facts.py 키 |
|---|---|
| 계속근로기간 | 없음 |
| 계약_유형 | domain |
| 계약기간_1년이상 | 없음 (contract_period·start_date/end_date로 계산 가능하나 미구현) |
| 근로자성 | 없음 |
| 단순노무여부 | 없음 |
| 단시간여부 | 없음 |
| 상시근로자수 | 없음 |
| 소정근로시간 | 없음 (work_hours_per_day와 유사하나 별키 없음) |
| 수습여부 | 없음 (probation_months 있으면 간접) |
| 시급_또는_월급 | hourly_wage / monthly_wage (둘 중) |
| 약정_소정근로 | 없음 |
| 일_근로시간 | work_hours_per_day |
| 적용연도 | 없음 (start_date 연도 추정 가능하나 미구현) |
| 주_근로시간 | 없음 (주 근로시간 직접 키 없음; work_days_per_week×work_hours_per_day로 추정 가능하나 미구현) |
| 주_소정근로시간 | 없음 |

### facts.py가 못 뽑는 사실 (현재 카드에 남은 것 포함)

- 계속근로기간
- 계약기간_1년이상
- 근로자성
- 단순노무여부
- 단시간여부
- 상시근로자수
- 소정근로시간
- 수습여부
- 약정_소정근로
- 적용연도
- 주_근로시간
- 주_소정근로시간
- (참고, 카드에서 빠졌거나 간접만) 단순노무여부, 근로자성, 계속근로기간 — 계속근로기간은 DISMISS에 유지·키는 없음

### 다음 단계 규칙 (미구현 · 기록만)

> 카드의 needs_fact가 사실표에 **이미 있으면** 확인 필요로 바꾸지 않고 그 값으로 판단한다.

## 3. 가이드 오류·5인 미만 표

| 항목 | 전 | 후 |
|---|---|---|
| §2 명시의무 5인 이상 | 명시의무는 5인 이상 원칙 | 제17조는 4명 이하에도 적용으로 정정 + §0에 적용 범위 표 추가 |
| 5인 미만 표 | 없음 | `[지식·원문 대조 필요]` 표 삽입 |

## 4. 작은 수정

| 카드/위치 | 전 | 후 |
|---|---|---|
| LAB-DISMISS keywords | 해고요고 | 해고예고 |
| LAB-PT-OT basis/missing | 기간제법_가산_조항 | missing_basis=`기간제법 제6조 제3항`, basis는 제18 보조, check_if에 상시 5명 미만, needs에 상시근로자수 |
| LAB-HOLIDAY check_if | (주휴수당 포함 시급 없음) | 주휴수당 시급 포함 → 구분·최저임금 확인 |
| LAB-PENALTY check_if | 예정/실손해만 | 교육비 반환 약정 합리성 확인 추가 |
| LAB-REST violation | 40시간 초과 상시 | `(상시 5명 이상)` 명시, missing_basis 제50 corpus 후보 |
| LAB-MINWAGE safe | 2026년 10,320원 고정 | config/min_wage.yaml 연도 기준 |
| LAB-OT safe | 가산을 부정하지 않음 | 법정 가산 지급 명시 또는 배제 문구 없음 |

## 5. 확인 표

### 카드 글자 수 (basis·본문 필드, missing_basis 제외)

| id | title | 글자 | ≤500 |
|---|---|---:|---|
| LAB-TERM | 계약기간 | 176 | Y |
| LAB-PLACE | 근무장소 | 182 | Y |
| LAB-DUTY | 업무 내용 | 174 | Y |
| LAB-REST | 근로시간·휴게 | 212 | Y |
| LAB-HOLIDAY | 휴일·주휴 | 247 | Y |
| LAB-WAGE | 임금(구성·계산·지급) | 171 | Y |
| LAB-MINWAGE | 최저임금 | 270 | Y |
| LAB-PROBATION | 수습 | 164 | Y |
| LAB-OT | 연장·야간·휴일 가산 | 164 | Y |
| LAB-PT-OT | 단시간 초과근로 가산 | 159 | Y |
| LAB-ANNUAL | 연차유급휴가 | 162 | Y |
| LAB-INSURE | 사회보험 | 134 | Y |
| LAB-DELIVER | 계약서 교부 | 106 | Y |
| LAB-DISMISS | 해고 예고 | 145 | Y |
| LAB-SEVERANCE | 퇴직금 | 117 | Y |
| LAB-PENALTY | 위약금·손해배상 예정 | 188 | Y |
| LAB-OFFSET | 전차금 상계·강제 저축 | 144 | Y |
| LAB-WAIVER | 법 적용 배제·신고 금지·취업규칙 불리 변경 | 185 | Y |

최대: ('LAB-MINWAGE', '최저임금', 270)

### violation / check_if / needs_facts 개수 전→후

| id | v_전 | v_후 | c_전 | c_후 | n_전 | n_후 |
|---|---:|---:|---:|---:|---:|---:|
| LAB-TERM | 2 | 1 | 1 | 2 | 1 | 1 |
| LAB-PLACE | 1 | 0 | 1 | 2 | 0 | 0 |
| LAB-DUTY | 1 | 0 | 1 | 2 | 0 | 0 |
| LAB-REST | 3 | 3 | 2 | 2 | 3 | 3 |
| LAB-HOLIDAY | 1 | 1 | 2 | 3 | 2 | 1 |
| LAB-WAGE | 4 | 4 | 1 | 1 | 0 | 0 |
| LAB-MINWAGE | 2 | 2 | 2 | 2 | 6 | 6 |
| LAB-PROBATION | 2 | 2 | 1 | 1 | 3 | 3 |
| LAB-OT | 1 | 1 | 2 | 2 | 1 | 1 |
| LAB-PT-OT | 1 | 1 | 1 | 2 | 2 | 3 |
| LAB-ANNUAL | 2 | 2 | 2 | 2 | 2 | 2 |
| LAB-INSURE | 2 | 2 | 1 | 1 | 1 | 1 |
| LAB-DELIVER | 2 | 2 | 1 | 1 | 0 | 0 |
| LAB-DISMISS | 1 | 1 | 1 | 1 | 2 | 1 |
| LAB-SEVERANCE | 2 | 2 | 1 | 1 | 2 | 2 |
| LAB-PENALTY | 1 | 1 | 1 | 2 | 0 | 0 |
| LAB-OFFSET | 2 | 2 | 1 | 1 | 0 | 0 |
| LAB-WAIVER | 3 | 3 | 1 | 1 | 0 | 0 |

needs_facts 합계: **25 → 24**

### 정답 데이터 문장 겹침 (15자↑, 3-gram Jaccard ≥ 0.5)

걸린 줄 수: 1 (안전 예시 1줄은 날짜 표기를 바꿔 재작성해 제거)

| score | guide 줄 | gold 쪽 |
|---:|---|---|
| 0.571 | 1. 이 계약에 없는 사항은 근로기준법령에 따른다. | 기타: 이 계약에 정함이 없는 사항은 근로기준법령에 따른다. |

표준계약서 관용 문구와 겹침 → 유지. 독소 예시 겹침 없음.
