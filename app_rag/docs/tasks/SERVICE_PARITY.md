# 서비스와 평가 결과 맞추기 (SERVICE_PARITY) — 시연 전 최우선

## 문제
WRAP_UP 5장 확인에서 `..\datasets\test_hwp_pdfs_v4_claude\LOAN_toxic_LOAN-0016.pdf`를 서비스(8091, EXAONE)로 분석했다. 결과는 **11조각 전부 "문제 없음", 점수 100, 안전**이었다(`out\wrap_up\ch5_loan_analyze.json`).

같은 계약서를 FINAL_TEST 평가 경로(EXAONE, 지금 카드)로 돌린 결과(`out\quant_test\EXAONE_tuned_LOAN_rows.jsonl`, doc_id=LOAN-0016)는 이렇다.
- S03 "연 26%" → **위반**, S07 "대물반환 예약" → **위반**
- S01·S06·S08 → 확인 필요

**즉 서비스 경로가 평가한 시스템과 다르게 동작한다.** 이대로 시연하면 독소 계약서가 "안전"으로 나온다.
- 참고: summary에 `n_doc_question: 10`이 찍혀 있다. 조각 대부분이 "문서 질문"으로 빠졌을 가능성이 있다.

`CLAUDE.md` 규칙을 따른다.
- 백업은 `*_v숫자`로 한다.
- 카드·판정 프롬프트·검증 규칙·검색 설정은 바꾸지 않는다. **평가한 경로가 기준이다. 서비스 경로를 평가 경로에 맞춘다.**
- test 평가를 다시 돌리지 않는다. 아래 비교는 서비스 버그 확인용이다.

## 1. 원인 찾기
1. 서비스와 **같은 함수**(`/api/extract` → `/api/analyze`가 부르는 코드)로 LOAN-0016 PDF를 분석한다. 조각마다 아래를 `out\parity\LOAN-0016_service.jsonl`에 적는다.
   - 나눈 조각 텍스트(가린 뒤), 도메인, 선택된 카드 ID, 검색된 근거 ID, user 프롬프트 해시
   - 모델 원래 출력(verdict, parse_ok), 검증 뒤 verdict, review_source, needs_fact 처리(doc_question 여부)
   - 최종 리포트에 들어간 verdict
2. 평가 경로 결과(위 rows 파일)와 조각을 글자 겹침으로 짝지어 표를 만든다(`out\parity\LOAN-0016_compare.md`).
   - 열: 정답 조각 / 서비스 조각 / 평가 verdict / 서비스 원래 출력 / 서비스 최종 verdict
   - **어느 단계에서 갈라지는지** 적는다: 조각 나누기 / 도메인 / 카드 / 검색 / 프롬프트 / 모델 호출 / 파싱 / 검증 / needs_fact→doc_question / 리포트 집계
3. 특히 확인할 곳:
   - WRAP_UP에서 고친 `llm_router.py`(`user_m` → `user`)와 `report.py`
   - 서비스가 EXAONE 응답 실패나 파싱 실패를 "문제 없음"으로 처리하는 곳이 있는지
   - 서비스의 검증 설정(MODEL_VERIFY)과 needs_fact 처리가 평가 경로(`eval\quant_run.py`)와 같은지

## 2. 고치기
- 갈라지는 단계만 고친다. 서비스가 평가 경로와 같은 함수와 같은 설정을 쓰게 하는 게 원칙이다.
- **모델 호출이나 파싱이 실패한 조각은 절대 "문제 없음"으로 두지 않는다.** "확인 필요(분석 실패)"로 표시하고 화면에 알린다.

## 3. 확인 (서비스 경로로, 3장)
- `..\datasets\test_hwp_pdfs_v4_claude\`의 `LOAN_toxic_LOAN-0016.pdf`, `LAB_toxic_WORK-0001.pdf`, `LEASE_toxic_LEASE-0027.pdf`
- 계약서마다 표를 만든다: 정답 독소 조각별 **평가 verdict vs 서비스 verdict**, 점수·등급, 걸린 시간
- 통과 기준:
  1. 평가에서 위반·위험·확인 필요였던 독소 조각 중 서비스에서도 위반·위험·확인 필요인 비율 **90% 이상**
  2. 평가에서 위반이 1개라도 있던 계약서가 서비스에서 "안전"으로 나오지 않을 것
- 3번 시도해도 못 넘으면 갈라지는 단계와 숫자를 적고 멈춘다.

## 보고
- `out\parity\PARITY_REPORT.md`
- 채팅에는 짧게: 원인(어느 단계, 어느 파일 몇 행), 고친 것, 3장 비교 표, 미확인 항목
- 끝나면 8091(exaone)과 EXAONE(8083)을 띄워 둔 채 멈춘다.
