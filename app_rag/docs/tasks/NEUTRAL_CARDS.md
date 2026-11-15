# 중립 카드로 다시 비교 (NEUTRAL_CARDS)

**목적:** 지금 카드·규칙은 A.X와 EXAONE 결과를 보면서 같은 dev로 고친 것이다. 그래서 GPT에 불리할 수 있다. **모델 결과를 보고 고치기 전 버전(중립 버전)**으로 GPT와 EXAONE을 다시 돌려 공정하게 비교한다.

`CLAUDE.md` 규칙을 따른다. dev만 쓴다(`dev_test_split_v2.json`, clean twin, clean_v2). test는 돌리지 않는다. 지금 버전 파일은 덮어쓰지 않는다. 중립 버전은 **새 이름**으로 만든다.

## 1. 중립 버전 만들기 (`criteria\neutral\`, `prompts\judge_neutral.txt`)
기준: **법령·표준계약서·라벨 기준(toxic/check)만 반영한 내용**은 남기고, **모델 결과를 보고 고친 내용**은 뺀다.

| 대상 | 중립 버전 | 빼는 것 |
|---|---|---|
| 근로 카드 | `LAB_cards_v3.yaml` (라벨 기준 정렬 + uses_facts/blocking_if 분리까지) | v4의 A.X 실험 수정, 지금 버전의 safe 보강, LAB-GENERAL |
| 임대 카드 | 지금 `LEASE_cards.yaml`에서 **LEASE-GENERAL만 뺀 것** | LEASE-GENERAL (EXAONE 실패 분석을 보고 만든 카드) |
| 차용 카드 | 지금 `LOAN_cards.yaml`에서 **LOAN-GENERAL만 뺀 것** | LOAN-GENERAL |
| 판정 프롬프트 | `judge.txt`에 카드 지시를 **처음 설계한 2줄만** 넣은 것(아래) | A.X 실험 중 추가된 카드 지시 줄(`criteria_extra_rules`의 나머지) |
| 검증 규칙 | 지금 코드 그대로 | — 변형(AXOK, NUM2WAY, R, K 등)은 replay로 **모델마다 각자 최적**을 고르므로 공정하다 |

판정 프롬프트 카드 지시 2줄(처음 설계):
- "조항이 criteria의 safe에 해당하고 violation·check_if에 해당하지 않으면 '문제 없음'으로 답한다."
- "check_if에 해당할 때만 '확인 필요'로 답하고, needs_fact에 그 사실을 적는다."

확인할 것:
- `LAB_cards_v3.yaml`이 정말 "모델 결과를 보기 전" 버전인지 `LAB_CARDS_FIX_LOG.md`와 PROGRESS 기록으로 확인한다. 아니면 그 조건에 맞는 버전을 찾고 이유를 적는다.
- 지금 `criteria_extra_rules`에 들어가는 줄 전체를 보고서에 붙이고, 각 줄이 언제 왜 들어갔는지 적는다.
- 중립 버전과 지금 버전의 카드 수, 파일 해시를 표로 낸다.
- 코드에 `CARDS_VERSION=neutral|tuned` 설정을 두고, 기본값은 지금처럼 tuned로 둔다.

## 2. 실행 (중립 버전, dev 세 도메인)
| 실행 | 모델 | 예상 |
|---|---|---|
| N-G1 | gpt-4o-mini | 약 $0.3 |
| N-G2 | gpt-4.1 | 약 $3.4 |
| N-EX | EXAONE 32B (8083) | 약 2시간 |
| N-AX | A.X (8082) | 약 35분 |

- GPT 비용 상한은 **$8**. 넘을 것 같으면 멈추고 묻는다. 캐시와 비용 기록 방식은 WEEK_FINAL A장과 같다.
- **EXAONE도 중립 버전으로 돌리는 이유:** GPT만 중립으로 돌리면 이번엔 반대로 EXAONE이 유리해진다. 같은 카드끼리 비교해야 공정하다.
- 원래 출력은 `out\quant_neutral\`에 저장한다. replay 변형과 모델별 최적 조합 고르기는 QUANT_FULL과 같다.

## 3. 결과 표
**표 1: 같은 카드끼리 비교** (중립 버전, 모델 4개 × 세 도메인)
- 경고 포착 / 오탐 / 과잉 경고 / 깨끗 통과 / 독소 계약서 놓침 / 계약서 1장 시간
- 신뢰구간, 분자/분모 포함

**표 2: 튜닝 효과** (모델마다, 도메인마다)
- 중립 → 튜닝(지금, GPT_EVAL_REPORT 결과)의 변화량
- EXAONE의 개선폭이 GPT보다 눈에 띄게 크면 "카드가 EXAONE에 맞춰졌다"는 뜻이다. 표 아래에 한 줄로 해석한다.

**McNemar:** 중립 버전에서 EXAONE vs G1, EXAONE vs G2, G1 vs G2 (경고 포착, 오탐)

**점수 공식:**
- 지금 공식으로 계산하고, "확인 필요 3개 이상이면 최대 79점" 수정안으로도 계산한다(replay).
- 깨끗한 계약서의 안전 비율과 독소 계약서의 비안전 비율을 낸다.
- 수정안을 쓸지는 사용자가 정한다.

## 4. 보고
`out\NEUTRAL_CARDS_REPORT.md`. 채팅에는 짧게:
- 표 1, 표 2
- McNemar 요약
- 점수 공식 전/후
- 실제 비용
- 미확인 항목

끝나면 EXAONE을 띄워 두고 멈춘다(test 최종 평가는 이 결과를 보고 따로 지시한다).
