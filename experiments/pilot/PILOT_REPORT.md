# PILOT_REPORT — 법률 SLM 파일럿 (0~2단계)

작성일: 2026-10-11  
ROOT: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발`  
작업 폴더: `ROOT\pilot\`  
규칙: random seed = 42, UTF-8 / CSV는 utf-8-sig  
**3단계(대량 생성·학습)는 진행하지 않음.**

---

## 0단계. 환경 확인

### 0-1. OS / Python / 가상환경

| 항목 | 값 |
|---|---|
| OS | Microsoft Windows 10 Pro, 10.0.19045, 64-bit |
| Python | 3.13.9 (`C:\Users\DMLAB\anaconda3` base) |
| conda envs | `base` (활성으로 사용), `pytorch` 존재 |
| 활성화 | `conda activate base` (이번 작업은 base에서 실행) |

### 0-2. GPU / RAM / 디스크

**nvidia-smi (요약, 실행 시각 2026-10-11 23:01 KST 근처)**

```
NVIDIA-SMI 560.94    Driver 560.94    CUDA 12.6
GPU 0: NVIDIA TITAN RTX   24576 MiB
GPU 1: NVIDIA TITAN RTX   24576 MiB
합계 VRAM: 48 GB (Titan 2장) — 확인됨
```

| 항목 | 값 |
|---|---|
| 시스템 RAM | 63.9 GB total / 당시 여유 약 53.7 GB |
| C: 디스크 | 여유 약 2,684 GB (모델 다운로드 전 기준; 60GB 미만 아님) |

### 0-3. 입력 파일

| 파일 | 존재 | 비고 |
|---|---|---|
| `ROOT\AUDIT_RESULTS.csv` | 있음 | 200행. 헤더: audit_id, source, domain, 관련성, 문제코드, 판정메모, 법령확인필요, question |
| `ROOT\AUDIT_SAMPLES.jsonl` | 있음 | 200줄 (aihub 100 + lawqa 100) |

### 0-4. LawQA-Ko

- `ROOT\datasets\LawQA-Ko\` 최초에는 없었음.
- `load_dataset("jihye-moon/LawQA-Ko")` 는 이 환경에서 httpx decompress 오류로 실패:
  - `TypeError: Decompressor.decompress() got an unexpected keyword argument 'output_buffer_limit'`
- 대응: 이미 받아 둔 `ROOT\LawQA-Ko\law_qa_dataset.jsonl` (14,819행)을 `datasets.Dataset` 으로 로드 후  
  `save_to_disk(ROOT\datasets\LawQA-Ko)` 저장.
- HF dataset_info sha (참고): `6319b9aa1b7d20d32dff206f01ef95643824672a`  
  (로컬 jsonl 직접 저장이므로 Hub revision과 바이트 단위 동일성은 미확인. **인덱스 일치만 검증함.**)

**행 인덱스 일치 검증 (필수)**

```
match: 100 /100
```

AUDIT_SAMPLES.jsonl 의 lawqa 100건 모두  
`ds["train"][origin_ref]["question"] == 레코드의 question` 성립.

### 0-5. 설치/사용 패키지

이번 세션에서 `pip install datasets` 수행. 사용 버전:

| 패키지 | 버전 |
|---|---|
| datasets | 5.1.0 |
| pandas | 2.3.3 |
| huggingface_hub | 2.2.0 |

부수: pyarrow 가 26.0.0 으로 올라가 streamlit(요구 `<22`)과 충돌 경고가 났음. 본 파일럿 스크립트에는 영향 없음.

---

## 1단계. 평가셋 고정 + LawQA 학습풀

스크립트: `pilot/build_sets.py`  
실행 명령:

```powershell
cd "C:\Users\DMLAB\Desktop\학부-AI서비스 개발"
$env:PYTHONIOENCODING='utf-8'
python ".\pilot\build_sets.py" *> ".\pilot\build_sets_console.log"
```

콘솔 로그(핵심, UTF-8 기준 stats와 동일):

```
LawQA train rows: 14819
[1-1] eval_lawqa: 53 (expected 54)
[1-1] eval_aihub_ood: 35 (expected 35)
[1-1] missing_sample_ids: 0
[1-2] exclude origin_ref count: 100
[1-3] unassigned (dropped): 5104
[1-3] filter stage counts:
  start: 14819
  a_answer_not_null: 14817
  b_exclude_audit_lawqa: 14717
  c_exact_dedup: 14654
  d_near_dedup_vs_eval: 14652
  e_answer_len_ge_150: 12948
  f_no_old_law: 12275
  g_no_out_domain_words: 7058
  h_domain_assigned: 1954
[1-3] domain counts: {'고용': 420, '계약': 1079, '채권채무': 455}
[1-4] pilot_set total: 450
  고용: pool=420 → sampled 150
  계약: pool=1079 → sampled 150
  채권채무: pool=455 → sampled 150
[1-4] pilot ∩ exclude: 0
[1-4] pilot ∩ eval_lawqa origin_ref: 0
```

### 1-1. 평가셋

| 산출물 | 건수 | 예상 | 비고 |
|---|---:|---:|---|
| `pilot/eval_lawqa.jsonl` | **53** | 54 | 아래 원인 |
| `pilot/eval_aihub_ood.jsonl` | **35** | 35 | 일치 |

**eval_lawqa 53인 원인:**  
조건 `관련성 ∈ {R,N}` 이고 `문제코드` 빈칸인 lawqa 행이 데이터상 53건.  
lawqa R/N 66건 중 문제코드가 있는 13건(I/O/D/F/O,K 등)이 제외됨.  
missing_sample_ids = 0 (AUDIT_SAMPLES 조인 실패 없음).

### 1-2. 학습 제외 목록

AUDIT_SAMPLES lawqa 100건의 `origin_ref` 전부 제외 → **100건**.

### 1-3. 학습풀 필터 단계별 건수

| 단계 | 남은 건수 |
|---|---:|
| start | 14819 |
| a) answer 결측 제거 | 14817 |
| b) 제외 목록 제거 | 14717 |
| c) 정확 중복 제거 | 14654 |
| d) 평가셋 유사(Jaccard≥0.6) 제거 | 14652 |
| e) answer 길이 <150 제거 | 12948 |
| f) 구법 신호 제거 | 12275 |
| g) 도메인 외 단어 제거 | 7058 |
| h) 도메인 배정 | **1954** (미배정 drop 5104) |

도메인별 최종: 고용 420 / 계약 1079 / 채권채무 455  
출력: `pilot/train_pool_lawqa.jsonl`

**d) 유사 중복 제거 상위 쌍 (제거 2건 전부 = top10에 해당)**

1. sim=1.0, candidate row_idx=41  
   - 후보: `근로자 甲은 사용자 乙과 근로기간을 1년으로 정한 근로계약을 체결하였는데 이미 두 번이 갱신되어 甲은 3년째 일을 하고 있습니다. 그런데 乙은 갑자기 정당한 이유 없이 甲에게 갱신거절을 하였습니다. 을의 갱신거절을 정당한 것인가요?`  
   - eval: 동일 문장(끝 공백 차이)

2. sim=0.7027, candidate row_idx=1177  
   - 후보: `저는 상가의 소유자는 아니지만 이를 임대할 권한을 가진 사람과 상가 임대차계약을 체결하고 보증금을 지급한 임차인인데, 이와 같이 상가의 소유자와 임대차계약을 체결하지 않은 경우에도 상가임대차보호법상 소액임차인의 최우선변제권자로서 보호받을 수 있나요?`  
   - eval: 동일 구조의 **주택** 임대차 질문

**도메인별 무작위 3건 예시 (seed=42, question/answer 원문 앞부분)**

- 고용 row_idx=12410: Q에 `알바` 부분문자열 매칭으로 배정. (전문은 train_pool / stats 파일 참고)  
- 고용 row_idx=100: `근로자` 매칭  
- 고용 row_idx=26: `근로계약`, `퇴사` 매칭  
- 계약·채권채무 예시는 `pilot/build_sets_stats.json` 의 `examples` 필드에 원문 저장.

### 1-4. 파일럿 학습셋

| 항목 | 값 |
|---|---|
| `pilot/pilot_set.jsonl` | **450** (150×3) |
| 풀 <150 도메인 | 없음 (세 도메인 모두 ≥150) |
| pilot ∩ exclude | **0** |
| pilot ∩ eval origin_ref | **0** |

---

## 2단계. 교사 모델 비교

스크립트: `pilot/teacher_compare.py`

### 2-1. llama.cpp

- 사전 빌드: ggml-org/llama.cpp release **b11556**  
  `llama-b11556-bin-win-cuda-12.4-x64.zip` + `cudart-llama-bin-win-cuda-12.4-x64.zip`  
  설치 위치: `ROOT\tools\llama.cpp\`
- 버전 출력:

```
version: 0.6.0-dev (build 11556, commit a9d27ac69)
built with Clang 20.1.8 for Windows x86_64
```

### 2-2. 모델 (공식 GGUF, Q6_K)

| 구분 | 저장소 | 파일 | 양자화 | 크기 |
|---|---|---|---|---|
| A | `LGAI-EXAONE/EXAONE-4.0-32B-GGUF` | `EXAONE-4.0-32B-Q6_K.gguf` | Q6_K | 26,259,021,600 bytes (24.46 GB) |
| B | `Qwen/Qwen3-32B-GGUF` | `Qwen3-32B-Q6_K.gguf` | Q6_K | 26,883,306,112 bytes (25.04 GB) |

다운로드 위치: `ROOT\models\...`  
디스크 여유 ≫ 60GB — 진행함.  
임의 대체 모델 없음.

**Windows 한글 경로 이슈:** llama-server가 `학부-AI서비스 개발` 절대경로의 jinja 파일을 열지 못함.  
대응: `C:\Users\DMLAB\pilot_root` → ROOT 정션 생성 후 해당 ASCII 경로로 서버 기동.

### 2-3. 실행

서버 명령 (모델별 1회):

```
llama-server -m <gguf> -ngl 99 --tensor-split 1,1 -c 8192 --port 8080 --host 127.0.0.1 --jinja [EXAONE: --chat-template-file <jinja>]
```

생성 파라미터: temperature 0.3, top_p 0.9, max_tokens 1200  

문항: `pilot_set.jsonl` 에서 도메인별 7·7·6 (seed 42) → `pilot/teacher_items.jsonl` (**20문항**)

**사고(thinking) 끄기**

| 모델 | 적용 | `<think>` 태그 |
|---|---|---|
| EXAONE | API `chat_template_kwargs: {"enable_thinking": false}` + 공식 `chat_template.jinja` | 0건 (think_tag_count=0) |
| Qwen3 | API `enable_thinking: false` + user 메시지 끝 `/no_think` | 0건 |

### 2-4. 산출물

- `pilot/teacher_outputs.jsonl` — 40행 (20문항 × 2모델)
- `pilot/TEACHER_COMPARE.md` — 문항별 나란히 배치 (판정 문구 없음)
- `pilot/teacher_compare_stats.json`

### 2-5. 자동 집계

| 지표 | EXAONE-4.0-32B-Q6_K | Qwen3-32B-Q6_K |
|---|---:|---:|
| n | 20 | 20 |
| [SKIP] | 0 | 0 |
| 4섹션(1.~4.) 비율 | 1.0 | 1.0 |
| 마지막 안내문(대한법률구조공단) 비율 | 1.0 | 1.0 |
| 평균 gen_sec | 18.45 | 30.37 |
| 평균 out_tokens | 281.0 | 464.55 |
| 평균 tok/s | 15.24 | 15.31 |
| `<think>` 포함 | 0 | 0 |
| 변호사 답변에 없는 "제○조" | T07:제347조 | (없음) |

콘솔 로그 전문: `pilot/teacher_compare_console.log`  
서버 로그: `pilot/llama_server_EXAONE-4.0-32B-Q6_K.log`, `pilot/llama_server_Qwen3-32B-Q6_K.log`

---

## 산출물 목록

```
pilot/
  build_sets.py
  teacher_compare.py
  eval_lawqa.jsonl
  eval_aihub_ood.jsonl
  train_pool_lawqa.jsonl
  pilot_set.jsonl
  teacher_items.jsonl
  teacher_outputs.jsonl
  TEACHER_COMPARE.md
  build_sets_stats.json
  teacher_compare_stats.json
  build_sets_console.log
  teacher_compare_console.log
  PILOT_REPORT.md          ← 본 파일
```

---

## 중지

2단계 완료. **3단계(대량 생성·학습)는 별도 지시 전까지 진행하지 않음.**
