# 진행 기록

## 1단계. 업로드 → 실제 분석 — 진행함 (기준 충족으로 판정)

### 한 일
- 기존 `out/mvp_upload/MVP_UPLOAD_REPORT.md`를 완료 기준과 대조.
- 미달: PDF 하이라이트 0.64(<0.70), corpus ID 대조표 없음, HWPX 전체 분석 기록 없음.
- 보완: `extract.py` 검색 강화, `review.js`에서 카드당 quote→clause 폴백, housing 재측정 **14/14=1.00**, corpus 대조(housing 11/11·toxic 6/6), HWPX 분석 기록, UI 문자열 확인.
- 백업: `extract_v1.py`, `review_v2.js`.

### 완료 기준 표

| 기준 | 실제 | 근거 파일 |
|---|---|---|
| PDF·HWP·HWPX·TXT·붙여넣기 끝까지 | API/E2E·HWPX·붙여넣기 스크린샷 있음. HWP UI 종료 클릭은 미확인 | `out/mvp_upload/MVP_UPLOAD_REPORT.md` §5·§9, `_stage1_gaps.json`, `04_user_result.png` |
| 스캔 PDF 안내 | 안내 토스트 확인 | `05_scan_toast.png` |
| 근거 corpus ID만 | out_of_corpus=[] | `_stage1_gaps.json` |
| PDF 하이라이트 ≥70% | **1.00 (14/14)** (폴백 후) | `_housing_hl_retry.json` |
| out·로그 원문 없음 | hits=[] | `_e2e_results.json` privacy |
| 예시 화면 / A.X 검색 근거 없음 | 배지·예시 설명 확인 | `01_sample_badge.png`, ui_strings |

### 남은 문제
- HWP 55조각 브라우저 UI 종료까지: 미확인(API는 완료)
- HWPX split이 조각 1개만 나오는 경우 있음(추출 텍스트 구조)

---

## 2단계. 근로 기준 카드 연결 — **중단** (마지막 시도 후 오탐·EXAONE 모델 미발견)

### 한 일
- 시도 5(추가 허용 마지막): AX `확인 필요`+비blocking needs_fact → 문제 없음+문서 질문.
- 보고서: `out/LAB_CARDS_CONNECT_ATTEMPT5.md`
- EXAONE: `start_exaone.py`, `eval/ax_vs_exaone_eval.py` 준비. 모델 파일 없어 비교 미실행.

| 시도 | 변경 | toxic 탐지 | safe 과잉경고 | safe 오탐 | 깨끗한 계약(위반/확인) | 파일 |
|---|---|---|---|---|---|---|
| 기준 B2 | (최초) | 0.421 | 0.632 | 0.057 | 0 / 8 | `lab_cards_connect.json` |
| 1 | soft_skip 등 | 0.421 | 0.517 | 0.057 | 0 / 6 | attempt1 |
| 2 | 카드·프롬프트 강화 | 0.947 | 0.425 | 0.414 | 7 / 3 | attempt2 |
| 3 | 빈 violation 강등 | 0.789 | 0.414 | 0.126 | 2 / 5 | attempt3 |
| 4 | min_wage·doc_question | 0.789 | 0.368 | 0.149 | 3 / 4 | attempt4 |
| **5** | AX확인필요→문제없음(비blocking) | **0.789** | **0.138** | **0.149** | **3** / 1 | attempt5 |

### 완료 기준 표 (시도 5)

| 기준 | 실제 | 통과 |
|---|---|---|
| toxic 탐지 ≥50% | 0.789 (15/19) | 통과 |
| safe 과잉 경고 ≤20% | 0.138 (12/87) | **통과** |
| safe 오탐 ≤5% | 0.149 (13/87) | **미통과** |
| 깨끗: 위반·위험 0, 확인 ≤3 | 위반 3, 확인 1 | **미통과** |
| 덮어쓰기 보고 | 24건 / toxic 1건 | 보고함 |

### ③ EXAONE — **비교 완료** (순차 단독 GPU)
- 파일: `data_local\models\EXAONE-4.0-32B-Q4_K_M.gguf`
- 동시 로드 불가 → A.X 잠시 내리고 EXAONE 단독 평가 후 A.X 재기동.
- 보고: `out/AX_VS_EXAONE_REPORT.md`, 병합 `out/ax_vs_exaone_lab_lease.json`
- LAB: A.X 탐지 우위(0.79 vs 0.58), EXAONE 오탐·과잉 더 낮음.
- LEASE: A.X 탐지 0.81 / EXAONE 0.04 → A.X 압도.
- 현재 A.X 8082 UP, EXAONE 8083 DOWN.

### 현재 코드 상태
- `verify.py` = 시도 5 (`ax_review_to_ok`). A.X 기본 설정 유지.
- **2단계 완료 기준(오탐≤5% 등)은 A.X LAB 기준 여전히 미달** → 3~5단계 진행 안 함.

---

## FIX_ROUND1-A. 데이터: dev 늘리기 + clean twin — 완료

### 한 일
- `datasets/splits/dev_test_split.json` 유지, `dev_test_split_v2.json` 신설 (seed 42, v1 dev 전부 유지 + test→dev).
- clean twin: `datasets/{property,money,work}/clean_twins/01_계약서.jsonl`
- 스크립트: `eval/build_fix_round1_a.py` → `out/fix_round1_a.json`

### 이동(test→dev)
| 도메인 | 목표 | moved |
|---|---|---|
| LEASE | 15/35 | LEASE-0004,0011,0033,0036,0044 |
| LOAN | 18/42 | LOAN-0003,0004,0005,0029,0037,0056 |
| LAB | 12/28 | WORK-0002,0003,0017,0019 |

### A-3 표 (원본+clean twin, v2)

| 도메인 | split | 문서 | 독소문서 | 깨끗문서 | toxic | check | safe |
|---|---|---|---|---|---|---|---|
| LEASE | dev | 20 | 13 | 7 | 37 | 13 | 342 |
| LEASE | test | 40 | 30 | 10 | 71 | 23 | 667 |
| LOAN | dev | 23 | 15 | 8 | 41 | 16 | 115 |
| LOAN | test | 47 | 36 | 11 | 94 | 38 | 235 |
| LAB | dev | 17 | 10 | 7 | 26 | 8 | 201 |
| LAB | test | 33 | 23 | 10 | 67 | 25 | 371 |

- LAB 숫자규칙으로 버린 twin: **0**
- 원본 datasets 01 파일은 수정하지 않음.

---

## FIX_ROUND1-B. 지표 보강 — 완료

### 한 일
- 공통 모듈 `eval/metrics.py`: `score_pair`, Wilson CI `rate`, 경고 포착률, 문서 3단계 판정, 깨끗 통과율, 독소문서 경고율, `ax_review_to_ok` toxic/safe 분리.
- `dev_eval.py` / `lab_cards_connect_eval.py` / `ax_vs_exaone_eval.py`가 동일 채점·비율 함수 사용.
- `splitutil.py`: `dev_test_split_v2.json`·clean twin 경로 지원.
- 백업: `splitutil_v1.py`, `dev_eval_v1.py`, `lab_cards_connect_eval_v3.py`, `ax_vs_exaone_eval_v1.py`

### 추가 지표
| 이름 | 정의 |
|---|---|
| warn_capture_rate | toxic 중 위반·위험·확인 필요 |
| clean_doc_pass_rate | 깨끗 문서 중 "큰 문제 없음" |
| toxic_doc_warn_rate | 독소 문서 중 "고칠 조항 있음" |
| ax_review_to_ok_toxic / _safe | 덮어쓰기 중 정답 toxic / safe |
| rate 문자열 | `p (n/d) CI95[lo,hi]` |

---

## FIX_ROUND1-C. 임대 점수 급등 원인 — 완료

### 원인 (한 줄)
**주원인: `judge.txt`에 카드 관련 지시가 붙은 것** (옛 `judge_v1` 탐지 0.154 → 카드 지시 포함 0.538). 빈 violation 금지는 LEASE에서 억제 효과가 없었고(고치기 전·후 동일 0.538), 카드가 있을 때만 넣도록 수정함.

### 변경
- `judge.txt`: 카드 전용 규칙 → `{criteria_extra_rules}` (백업 `judge_v3.txt`)
- `generate.py`: 카드 있을 때만 extra rules 삽입 (백업 `generate_v3.py`)
- 증거: `out/fix_round1_c.json`, 프롬프트 `out/fix_round1_c_lease_prompt.txt`

### 옛 LEASE dev 10장 비교

| 설정 | detect | warn_capture | fp | overwarn |
|---|---|---|---|---|
| judge_v1 | 0.154 (4/26) | 0.846 | 0.000 | 0.333 |
| judge_v3(카드규칙 항상) | 0.538 (14/26) | 0.769 | 0.000 | 0.210 |
| judge_fixed(조건부) | 0.538 (14/26) | 0.769 | 0.000 | 0.210 |

- AX_VS_EXAONE의 0.808과의 차이는 **미확인**(동일 10장이어도 0.538).

---

## FIX_ROUND1-D. 공정 비교 — **완료**

### 한 일
- 사용자 승인 후 전체 ~110분 실행. 산출 `out/fix_round1_d.json`, 종합 `out/FIX_ROUND1_REPORT.md`
- EXAONE 단독 후 **A.X 8082 복구 확인(UP)**, EXAONE 8083 DOWN

### LAB D1~D4 요약
| | detect | warn_cap | fp | overwarn | 깨끗통과 | ax_ok 덮어쓰기 tox/safe |
|---|---|---|---|---|---|---|
| D1 A.X 켜기 | 0.846 | 0.923 | 0.159 | 0.134 | 0/7 | 1/46 |
| D2 A.X 끄기 | 0.846 | 0.962 | 0.159 | 0.363 | 0/7 | 0 |
| D3 EX 켜기 | 0.615 | 0.692 | 0.045 | 0.065 | 3/7 | **7**/46 |
| D4 EX 끄기 | 0.615 | 0.962 | 0.045 | 0.294 | 1/7 | 0 |

### 임대·차용 A.X 기준점
- LEASE detect 0.514 / warn 0.757 / fp 0.006
- LOAN detect 0.537 / warn 0.951 / fp 0.174

### 0.54 vs 0.808
- C·D 재현값은 ~0.5. AX_VS 0.808은 raw A.X 위반이 더 많았으나 **동일 조건 재현 실패 → 미확인**. 2차 기준은 D BASE 사용.

### 상태
- FIX_ROUND1 A~D 종료. 멈춤. MVP 3단계(임대·차용 카드)는 2차.

---

## FIX_ROUND3-A — 숫자규칙·인용완화 (완료)

### 한 일
- 백업: `rag/facts_v5.py`, `rag/verify_v7.py`, `rag/dates_v2.py`
- 임금 인식: 시급/시간급/시간당/1시간당/시간단위임금 + 월급→시급(주소정×4.345) 환산
- 인용 완화: `<contract>` 래퍼·공백·문장부호·자리표시·조문번호 정규화
- replay: `eval/fix_round3_a.py` → `out/FIX_ROUND3_A.md`, `out/quant3/fix_round3_a.json`

### 숫자
| | 전 | 후 |
|---|---|---|
| 임금 인식(유사문장) | 5/39 | **19/39** |
| quote_mismatch toxic | 67 | **11** |
| quote_mismatch safe | 505 | **35** |
| 독소 계약서 놓침(R0 K2) | 0 | 0 |

- 채택: wage=True, soft_quote=True (코드 반영). toxic 판정 변경 0건.

## FIX_ROUND3-B — 카드 (완료)

### 한 일
- `criteria/LEASE_GUIDE.md`, `LEASE_cards.yaml` (+LEASE-GENERAL) — 14장
- `criteria/LOAN_GUIDE.md`, `LOAN_cards.yaml` (+LOAN-GENERAL) — 11장
- `LAB_cards.yaml`에 LAB-GENERAL·safe 보강 — 19장
- `rag/criteria.py`: 도메인별 카드, GENERAL 폴백, basis→검색 병합(최대+3)
- `rag/generate.py`/`pipeline.py`/`quant_run.py`: 전 도메인 카드 사용

## FIX_ROUND3-C — EXAONE 재실행 (완료)

- `eval/fix_round3_run.py --phase C` → `out/quant3/EXAONE_*_rows.jsonl`, `C_summary.json`
- 독소 놓침 0. 근로 warn 1.00·깨끗 4/6, 임대 깨끗 5/5, 차용 깨끗 6/8. 카드 재다듬기 0회.

## FIX_ROUND3-D — A.X 비교·한계 (완료)

- A.X 3도메인 → `D_summary.json`. McNemar: fp 차이 유의, warn 차이 비유의.
- `out/LIMITATIONS.md`, `out/FIX_ROUND3_REPORT.md`, `out/quant3/tables/one_page.csv`
- EXAONE 8083 유지. **FIX_ROUND3 A~D 종료·멈춤.**

---

## WEEK_FINAL 0→G — 완료 (스크린샷·실LLM 시간만 미확인)

### 0 / B
- CLAUDE.md 규칙 3·5 갱신(백업 CLAUDE_v1). `rag/pii.py` 21/21.

### A
- G1=`gpt-4o-mini`, G2=`gpt-4.1`. 실제 비용 **$3.57**/상한 $15.
- `out/GPT_EVAL_REPORT.md`, `out/quant_gpt/*`. AI Hub 0건.

### C–F
- SQLite·JWT·AES·TTL·점수·ANALYZE_MODEL. 테스트 auth/score/ttl 통과.
- UI: login/admin, review 점수·기록·모델 선택.

### G
- `eval/week_final_e2e.py` API E2E 전부 통과.
- 미확인: demo PDF 실파일·브라우저 스크린샷·모델별 실LLM 1장 시간.
- 최종: `out/WEEK_FINAL_REPORT.md`

---

## NEUTRAL_CARDS — 완료

- 중립: `criteria/neutral/*`, `prompts/judge_neutral.txt`, `CARDS_VERSION=neutral|tuned`
- LAB 중립=`LAB_cards_v3.yaml`(모델 튜닝 전). LEASE/LOAN은 GENERAL 제외.
- GPT 추정 $3.57 → 실제 **$3.62** / 상한 $8.
- `out/quant_neutral/*`, `out/NEUTRAL_CARDS_REPORT.md`
- EXAONE 8083 UP. test 평가는 미실행(지시 대기).
- 이 실험의 GPT 숫자(gpt-4o-mini·gpt-4.1)는 가리기 버그로 비교에서 빼기로 했다. 이후 비교는 FAIR_RERUN.

---

## FAIR_RERUN — 완료

같은 입력으로 luna·EXAONE·A.X × 중립/튜닝을 다시 돌렸다. 이전 GPT 결과는 지우지 않았고 비교에 쓰지 않았다.

- 가리기: dev 799 중 옛 266 → 새 0. 명령 `python -u -X utf8 eval/fair_mask_check.py`, 출력 `out/quant_fair/mask_check.md`.
- 중립 로컬 프롬프트 해시 799/799 일치 → EXAONE·A.X 중립은 `out/quant_neutral`을 `out/quant_fair`로 재사용. 튜닝은 새로 실행.
- GPT는 `gpt-6-luna`만. 실제 비용 **$0.348** / 상한 $1.0. 추론 토큰 0. Batch는 custom_id 중복으로 실패해 일반 요청으로 마쳤다.
- 표·McNemar·점수: `python -u -X utf8 eval/fair_analyze.py` → `out/quant_fair/summary.json`. 보고서 `out/FAIR_RERUN_REPORT.md`.
- 8091 재시작 후 데모 PDF 1장 API 추출: 별표 0→7, 전화 1건만. `out/quant_fair/demo_api_check.json`.
- EXAONE 8083 UP. test 최종 평가는 하지 않음.

---

## FINAL_TEST — 완료

카드 none/neutral/tuned × luna·EXAONE·AX를 **test 한 번** 돌렸다. freeze는 A단계(dev-none)+FAIR best. 결과는 `out/quant_test/`, 보고 `out/FINAL_TEST_REPORT.md`, 통계 `out/quant_test/summary.json`.

| 항목 | 결과 |
|---|---|
| 로컬 EXAONE/AX × 3카드 × 3도메인 | 전부 완료 (463/761/367행) |
| GPT gpt-6-luna | 크레딧 소진 → **부분**. LAB full, LEASE/LOAN partial. **$0.771**/상한 $1.5 |
| 통계 | `final_test_analyze.py` excluded 0. Wilson + doc-bootstrap + McNemar/Holm |
| EXAONE | 8083 leave-up |

주의: GPT LEASE/LOAN partial이라 해당 비교는 공통 조각 기준. test로 재튜닝하지 않음.

---

## WRAP_UP — 완료

FINAL_TEST 이후 서비스 마무리. test 평가는 다시 돌리지 않음. 보고 `out/wrap_up/WRAP_UP_REPORT.md`.

| 장 | 결과 | 근거 |
|---|---|---|
| 1 PII | 통과. dev799/test1591 changed=0, v4 remain=0, unit 24/24 | `out/wrap_up/pii_check.md`, `test_pii_out.txt` |
| 2 점수·모델·GPT | check_cap79 기본, MODEL_VERIFY=freeze, 관리자만 모델 변경, ENABLE_GPT 게이트 | `test_score_out.txt` 6 passed, `ch5_non_admin_model.txt` |
| 3 차용 예시 | LOAN-0037 → `samples/loan_toxic.txt` + `review-data.js` loan | `ch5_samples.json` |
| 4 공개 보안 | ADMIN_PASSWORD 파일, 가입5/시·분석20/일, README 터널 안내 | `data_local/ADMIN_PASSWORD.txt`(값 비공개), `ch5_signup_limit.json` |
| 5 확인 | 403·429·79테스트·LOAN PDF 115.37s 점수100/안전 이름7·loan 목록 | `out/wrap_up/ch5_verify.json` |

서버: 8091 `ANALYZE_MODEL=exaone`, EXAONE 8083 leave-up. 관리자 비밀번호 위치만 `app_rag/data_local/ADMIN_PASSWORD.txt`.

---

## FINAL_POLISH — 완료

A장 SERVICE_PARITY 원인: `split.py` 줄바꿈 첫 줄 유실 + 서비스 `ax_review_to_ok` true. 고침 후 LOAN/LAB/LEASE 독소 일치율 100%, 안전 아님. 보고 `out/parity/PARITY_REPORT.md`, `out/polish/POLISH_REPORT.md`.

| 장 | 결과 | 근거 |
|---|---|---|
| A | split+axok 정렬, 3장 통과 | `parity_pass.json` |
| B | EXAONE 고정·채팅 EXAONE | `f4`·`f5`, `shots_meta.json` |
| C | 사이드바 검토 기록 | `f1`·`f2` |
| D | 금전 텍스트·매매 숨김 | `f3` |
| E | 점수식 보고만 | `score_explain.md` |
| F | 스크린샷 5장 | `out/polish/*.png` |

서버: 8091 exaone, EXAONE 8083 leave-up.

---

## LAW_WATCH — 완료 (개정판)

법령 개정 추적 → 카드 버전(시행일+적용 기준). 보고 `out/lawwatch/LAW_WATCH_REPORT.md`.

| 항목 | 결과 | 명령·출력 |
|---|---|---|
| 저장소 | 현행·연혁 등록, 법령 폴더 14 | `eval/lawwatch_bootstrap.py` → `bootstrap_cases.json` |
| 감지 | offline 11건 변경 없음 | `python -m rag.lawwatch.check --offline` → `latest_check.json` |
| 사례 3 | 이자 contract_date / 주임 in_force / 최임 performance_period, 부칙 원문 | `criteria/versions/*.yaml`, `bootstrap_cases.json` |
| 시연 흐름 | 비교→수정안→승인→점검→되돌리기, 카드·corpus 복구 | `eval/lawwatch_demo.py` → `out/lawwatch/demo/` |
| 단위 | 12 passed | `pytest tests/test_lawwatch.py` → `test_lawwatch_out.txt` |
| 799 같음 | **799/799** (버전 파일 없을 때) | `eval/lawwatch_prompt_parity.py` → `prompt_parity.json` |
| 화면 | 관리자 「법령 변경」탭·API | `static/admin.html`, `/api/admin/lawwatch*` |

test 평가 미실행. 키 미출력.

---


