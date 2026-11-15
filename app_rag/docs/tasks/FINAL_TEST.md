# 최종 시험 (FINAL_TEST) — 카드 없음 / 중립 / 튜닝 × 모델 3개, test 한 번

**목적**
- 카드(힌트)가 성능을 얼마나 올리는지를 시험용(test) 데이터로 확인한다.
- 그 숫자를 얼마나 믿을 수 있는지 통계로 낸다.

`CLAUDE.md` 규칙과 `FAIR_RERUN.md`의 **공정 조건(1장)**을 그대로 따른다. 모든 모델이 같은 가린 문장과 바이트 단위로 같은 user 메시지를 받고, system 문장은 없으며, 같은 코드로 돈다.
- 파일은 지우지 않는다. 고칠 파일은 `*_v숫자.py`로 백업한다.
- 결과는 새 폴더 `out\quant_test\`에 둔다.
- 사용자는 이 작업 동안 자리에 없을 수 있다. **묻지 말고** 맨 아래 표대로 처리한다.

## 0. test 규칙 (가장 중요)
- **test는 조건마다 한 번만 돌린다.** test 결과를 본 뒤에 카드·프롬프트·규칙·설정을 고치고 다시 돌리지 않는다. 결과가 나빠도 그대로 적는다.
- 에러로 중간에 멈추면, 이미 끝난 조각은 다시 돌리지 않고 **남은 조각만** 이어서 돌린다(캐시와 rows로 확인).
- 모델별 "최적 설정"은 **dev에서 고른 것**만 test에 쓴다. test에서 최적을 고르지 않는다(sweep_best를 test에 쓰지 않는다).

## 1. 카드 없음 조건 추가
- `CARDS_VERSION=none`을 추가한다. 이때는 `use_criteria=False`로 돌아간다.
  - 카드 블록, 카드 근거 조문 병합, `criteria_extra_rules`가 모두 빠진다.
  - 검색한 법 조문 3개와 검증 코드는 그대로 둔다.
  - `eval\quant_run.py` 138행의 `use_criteria = True` 고정을 이 설정에 따르게 바꾼다(백업 `quant_run_v숫자.py`).
- 기본값은 지금처럼 tuned로 둔다.
- 확인: 조각 3개로 none 프롬프트를 만들어, 카드 문구가 없고 법 조문은 neutral·tuned와 같은지 본다. 결과는 `out\quant_test\none_prompt_check.md`

## 2. A단계: dev에서 카드 없음 실행 (설정 고르기용)
| 실행 | 모델 | 시간·비용 |
|---|---|---|
| dev-none-luna | gpt-6-luna (추론 끔) | 약 $0.1 |
| dev-none-EX | EXAONE (8083) | 약 1.5시간 |
| dev-none-AX | A.X (8082) | 약 30분 |

- 결과는 `out\quant_test\dev\`에 둔다. neutral·tuned의 dev 결과는 `out\quant_fair\`의 것을 쓴다.
- 이 실행을 하는 이유: 카드 없음 조건의 모델별 최적 설정을 **test를 보기 전에 dev에서** 고르기 위해서다.

### 설정 고정 (freeze)
A단계가 끝나면 `out\quant_test\freeze.json`에 아래를 적는다. 그 뒤로는 바꾸지 않는다.
- 조건(none / neutral / tuned) × 모델 3개마다 쓸 설정 두 가지
  - **고정 설정:** `axok=False num2way=True ne_risky_only=True num_year_doc=True clean_v2=True R=R0 K=2`
  - **dev 최적 설정:** neutral·tuned는 `quant_fair\summary.json`의 best, none은 A단계 결과의 `sweep_best`
- 해시: `rag\*.py`, `eval\*.py`, 카드 3벌, 프롬프트 파일, `config\min_wage.yaml`
- 점수 공식은 두 가지 다 계산한다: 지금 공식, "확인 필요 3개 이상이면 최대 79점" 수정안

## 3. B단계: test 실행 (조건마다 한 번)
| 실행 | 모델 | 카드 | 예상 |
|---|---|---|---|
| T-none-luna / T-neu-luna / T-tun-luna | gpt-6-luna | none / neutral / tuned | 합계 약 $0.9 (Batch면 약 $0.45) |
| T-none-EX / T-neu-EX / T-tun-EX | EXAONE | none / neutral / tuned | 각 약 3~4시간 |
| T-none-AX / T-neu-AX / T-tun-AX | A.X | none / neutral / tuned | 각 약 1시간 |

- test 데이터: `dev_test_split_v2.json`의 test(근로 33, 임대 40, 차용 47장, clean twin 포함). 조각 수는 근로 463, 임대 761, 차용 367개다.
- 시작 전 확인:
  - test 조각 전부에 가리기를 돌려 바뀐 조각 수를 `out\quant_test\mask_check_test.md`에 적는다. 모델은 부르지 않는다. 일반 단어가 가려지면 GPT는 건너뛴다.
  - 실행마다 (doc_id, segment_id) 집합이 같은지 확인한다.
- 로컬 실행은 60분을 넘지만 **사용자가 미리 허락했다.** 멈추지 말고 진행한다. 로컬은 한 번에 한 모델만 올리고, GPT는 동시에 돌려도 된다.
- 결과 파일: `out\quant_test\{모델}_{none|neutral|tuned}_{도메인}_rows.jsonl`과 meta

### GPT
- `gpt-6-luna`만 부른다. 다른 OpenAI 모델은 부르지 않는다. 추론 설정은 FAIR_RERUN과 같다.
- **Batch를 다시 시도한다.** 지난번 실패 원인(`duplicate_custom_id`)을 고친다. 같은 프롬프트는 해시로 한 번만 보내고, `custom_id`는 프롬프트 해시로 한다.
  - 그래도 실패하거나 2시간이 넘으면 일반 요청으로 보내고 적는다.
- GPT 전체 상한은 **$1.5**(A단계 포함)다. 실행 전에 비용을 추정해서 적는다.

## 4. 통계 (`eval\final_test_analyze.py`)
비율은 모두 분자/분모와 함께 적는다.

### 4-1. 기본 표 (test)
- 조건 3개 × 모델 3개 × 도메인 3개, 그리고 도메인 합계
- 항목: 경고 포착 / 위반·위험으로 잡음(탐지) / 오탐 / 과잉 경고 / 깨끗 통과 / 독소 계약서 놓침 / 점수 기준(깨끗→안전, 독소→비안전, 공식 2가지) / 파싱 실패 / 1장 시간
- 설정은 freeze의 고정 설정과 dev 최적 설정, 두 줄로 낸다.

### 4-2. 신뢰구간 두 가지
- **Wilson 95%**(조각 단위)
- **계약서 단위 bootstrap 95%**: 같은 계약서 안의 조각들은 서로 비슷해서 독립이 아니다. 그래서 계약서를 단위로 2000번 다시 뽑는다(seed 42).
- 두 구간을 나란히 적고, 발표 숫자는 bootstrap 구간을 쓴다.

### 4-3. 카드 효과 (같은 모델, 같은 조각끼리 짝지어 비교)
- 모델마다 neutral − none, tuned − none, tuned − neutral의 차이
- 차이의 bootstrap 95% 구간과 McNemar exact p (경고 포착, 탐지, 오탐)
- 해석은 한 줄로 쓴다: "구간이 0을 안 걸치면 카드 효과가 있다고 말할 수 있다"

### 4-4. 모델 비교
- 조건마다 luna vs EXAONE, luna vs A.X, EXAONE vs A.X를 McNemar로 비교한다(경고 포착, 탐지, 오탐).
- 검정 수가 많으므로 p값 옆에 **Holm 보정 p**도 적는다.

### 4-5. dev와 test 차이
- 같은 조건·모델·설정에서 dev와 test의 차이, test의 bootstrap 구간
- dev 값이 test 구간 밖이면 "dev에 맞춰졌을 가능성"으로 표시한다.

### 4-6. dev에 없던 독소 유형
- 근로 test 독소 중 **dev에 없는 toxic_code 5종(test 독소의 25%)**은 따로 경고 포착·탐지를 낸다. 처음 보는 유형에도 통하는지 보기 위해서다.
- 임대·차용은 test 유형이 모두 dev에 있다고 적는다.
- 유형 목록은 `..\datasets` 정답 파일의 `toxic_code`에서 직접 센다.

### 4-7. 데이터 차이 (참고표, 모델 안 씀)
- dev/test의 계약서 수, 조각 수, 라벨 비율, 조항 길이, toxic_code 분포 차이(TVD), test에만 있는 유형 비율
- 문장 겹침: test 문장 중 dev와 똑같은 문장의 비율(toxic / safe 따로)

## 5. 보고
- `out\FINAL_TEST_REPORT.md`
  - freeze 내용
  - 4장의 표 전부
  - 비용(조각당 평균 입력·출력·추론 토큰)
  - 실행 시간
  - 미확인 항목
- `docs\PROGRESS.md`에 FINAL_TEST 절을 추가한다.
- 끝나면 EXAONE(8083)을 띄워 두고 멈춘다.

## 묻지 말고 이렇게 한다
| 상황 | 할 일 |
|---|---|
| GPT 비용 추정이 $1.5 초과 | test GPT는 neutral과 none만 돌리고 tuned는 건너뛴다. 그래도 넘으면 GPT는 전부 건너뛴다. 적는다 |
| 실제 누적 GPT 비용이 $1.5에 닿음 | 그 자리에서 GPT를 멈추고 "부분 결과"로 표시한다 |
| test 가리기에서 일반 단어가 가려짐 | GPT는 건너뛴다. 로컬은 계속한다. 바뀐 곳을 적는다 |
| 실행 중 에러 | 남은 조각만 2번까지 다시 시도한다. 그래도 안 되면 그 실행만 빼고 적는다 |
| 조각 집합이 실행마다 다름 | 다른 조각을 적고, 비교는 공통 조각으로만 한다 |
| 규칙 2(로컬 모델·검색 설정)를 바꿔야 할 것 같음 | 바꾸지 않는다. 이유만 적는다 |
| test 결과가 나쁨 | 아무것도 고치지 않는다. 그대로 적는다 |

## 채팅 보고 (짧게)
- 카드 효과 표: 모델마다 none → neutral → tuned, test, bootstrap 구간
- 모델 비교 요약 (Holm 보정 p)
- dev → test 차이, 처음 보는 유형의 결과
- 점수 공식 두 가지
- 비용·시간·미확인
