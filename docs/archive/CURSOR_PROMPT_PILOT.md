# 작업: 법률 SLM 파일럿 — 0단계(환경) + 1단계(평가셋·학습풀) + 2단계(교사 모델 비교)

2단계가 끝나면 반드시 멈추고 결과만 보고할 것. 3단계(대량 생성·학습)는 별도 지시 전까지 진행 금지.

---

## 배경 (먼저 읽을 것)

- 학부 수업 프로젝트: 대학생용 생활법률(고용·임대차·금전거래) 설명 소형 LLM.
- 방법: 큰 '교사' 모델이 변호사 답변을 대학생용 4단계 해설로 다시 쓰고, 그 해설로 작은 '학생' 모델(Qwen2.5-14B, QLoRA)을 학습한다.
- 비교 실험: (A) 학습 안 한 기본 모델, (B) 변호사 원문 답변으로 학습, (C) 4단계 해설로 학습.
- 데이터: LawQA-Ko (Hugging Face `jihye-moon/LawQA-Ko`, train 14,819건, 컬럼 question / precedent / answer).
  다른 컴퓨터에서 200건(AI Hub 100 + LawQA 100)을 사람이 검수했고 그 결과가 `AUDIT_RESULTS.csv` 이다.
  이 중 '문제 없음' 판정 건은 **평가 전용**이며 학습 데이터에 섞이면 실험 전체가 무효가 된다.
- 이번 작업은 파일럿이다: 평가셋 고정 → 학습 후보 풀 구축 → 교사 모델 2개 비교(20문항). 학습은 하지 않는다.

## 공통 규칙

- 원문 텍스트(question/answer)는 절대 수정·요약하지 말 것. 필터링과 추출만 한다.
- random seed = 42
- 모든 결과에 근거를 남길 것: 실행 명령, 콘솔 출력 전문, 건수표, 표본 예시.
  "완료/통과/✓"만 쓰지 말 것. 확인하지 못한 항목은 "미확인"으로 표시.
- ROOT = `C:\Users\DMLAB\Desktop\학부-AI서비스 개발`
  (경로에 한글·공백이 있으므로 모든 스크립트에서 pathlib 사용, 셸 명령에서는 따옴표로 감쌀 것)
- 작업 폴더: `ROOT\pilot\` (없으면 생성). 파일 입출력 인코딩은 UTF-8 (CSV 읽기는 utf-8-sig).

---

## 0단계. 환경 확인 (가장 먼저, 결과를 리포트 맨 위에 기록)

1. OS, Python 버전, 사용할 가상환경(conda 등) 이름과 활성화 방법.
2. `nvidia-smi` 출력 전문 (GPU 이름·VRAM. Titan 2장 합계 48GB인지 확인), 시스템 RAM 용량, 남은 디스크 용량.
3. 입력 파일 확인 — 하나라도 없으면 아무것도 만들지 말고 즉시 멈추고 보고. 비슷한 파일을 찾아 대신 쓰지 말 것.
   - `ROOT\AUDIT_RESULTS.csv`  (헤더: audit_id, source, domain, 관련성, 문제코드, 판정메모, 법령확인필요, question / 200행)
   - `ROOT\AUDIT_SAMPLES.jsonl` (200줄. lawqa 레코드의 origin_ref = LawQA train split 행 인덱스)
4. LawQA-Ko 준비:
   - `ROOT\datasets\LawQA-Ko\` 가 있으면 `datasets.load_from_disk` 로 연다.
   - 없으면 `datasets.load_dataset("jihye-moon/LawQA-Ko")` 로 내려받아 `save_to_disk(ROOT\datasets\LawQA-Ko)` 로 저장한다.
     내려받은 리비전(커밋 해시)을 기록한다.
   - **행 인덱스 일치 검증(필수):** AUDIT_SAMPLES.jsonl 의 lawqa 100건 각각에 대해
     `ds["train"][origin_ref]["question"] == 레코드의 question` 인지 확인하고 일치 건수를 기록한다.
     100/100 이 아니면 즉시 멈추고 불일치 예시 3건을 보고한다 (다른 컴퓨터와 데이터 순서가 다르다는 뜻이므로 이후 단계가 전부 틀어짐).
5. 필요한 패키지(datasets, pandas 등)를 설치했다면 목록을 기록한다.

---

## 1단계. 평가셋 고정 + LawQA 학습풀 구축  (스크립트: `pilot/build_sets.py`)

### 1-1. 평가셋 (학습 절대 금지)
- 조건: AUDIT_RESULTS.csv 에서 `관련성` ∈ {R, N} 이고 `문제코드` 가 빈 칸인 행.
- question/answer 원문은 AUDIT_SAMPLES.jsonl 에서 audit_id 로 가져온다.
- 출력:
  - `pilot/eval_lawqa.jsonl` (source == lawqa)
  - `pilot/eval_aihub_ood.jsonl` (source == aihub, 분포 밖 보조 평가용)
  - 각 레코드: audit_id, domain, 관련성, question, answer(원문), origin_ref
- 예상 건수: lawqa 54, aihub 35. 다르면 그대로 기록하고 원인 확인.

### 1-2. 학습 제외 목록
- AUDIT_SAMPLES.jsonl 의 lawqa 100건 전체(판정 결과와 무관하게) origin_ref 를 제외 목록에 넣는다.

### 1-3. LawQA 학습풀 필터 (train split 14,819건)
순서대로 적용하고 단계마다 남은 건수를 기록할 것.
- a) answer 결측 제거
- b) 1-2 제외 목록 제거
- c) 정확 중복 제거: question 을 공백·특수문자 제거 후 소문자화한 문자열이 같으면 1건만 남김
- d) 평가셋 유사 중복 제거: 후보 question 과 eval_lawqa 54건 question 의 문자 3-gram Jaccard 유사도 ≥ 0.6 이면 제거
  (제거된 쌍 중 유사도 상위 10쌍을 리포트에 원문으로 첨부)
- e) answer 길이 150자 미만 제거
- f) 구법 신호 제거: answer 에 "구 ○○법" 형태(정규식 `구\s?[「」『』\w]*법`), "개정되기 전의 것", "개정 전" 이 있으면 제거
- g) 도메인 외 제거: question+answer 에 아래 단어가 하나라도 있으면 제거
  `["고소","형법","처벌","징역","벌금","배임","횡령","절도","장물","공갈","사기죄",
    "상고","항소","공시송달","재심","경매","배당","공탁","가압류","압류","추심",
    "개인회생","파산","산업재해","산재","유족급여","부가가치세","소득세","행정심판","취소소송"]`
- h) 도메인 배정 (question 기준, 고용 > 계약 > 채권채무 우선순위로 하나만):
  - 고용: 아르바이트, 알바, 근로계약, 임금, 월급, 시급, 주휴, 최저임금, 퇴직금, 해고, 퇴사, 사직, 연차, 수습, 근로자
  - 계약: 임대차, 임대인, 임차인, 집주인, 세입자, 전세, 월세, 보증금, 원룸, 자취, 계약갱신, 원상복구
  - 채권채무: 빌려, 빌린, 대여금, 차용, 갚, 변제, 지급명령, 차용증
  - 어디에도 안 걸리면 제외
- 출력: `pilot/train_pool_lawqa.jsonl` (row_idx, domain, question, answer)
- 리포트: 단계별 남은 건수 표, 도메인별 최종 건수, 도메인별 무작위 3건 원문 예시

### 1-4. 파일럿 학습셋 샘플링
- train_pool 에서 도메인별 최대 150건 무작위 추출 → `pilot/pilot_set.jsonl` (최대 450건)
- 풀이 150 미만인 도메인은 전부 쓰고 그 사실을 기록
- 검증: pilot_set 의 row_idx 와 제외 목록·평가셋 origin_ref 의 교집합이 0건인지 출력

---

## 2단계. 교사 모델 비교 (20문항 × 2모델)  (스크립트: `pilot/teacher_compare.py`)

### 2-1. 런타임
- llama.cpp (CUDA 빌드) 사용. 없으면 설치하고 `llama-server --version` 출력 기록.

### 2-2. 모델 준비 (GGUF, Q6_K 우선. 없으면 Q5_K_M)
- 모델 A: EXAONE 4.0 32B Instruct — LG AI Research 공식 GGUF 저장소 우선
- 모델 B: Qwen3-32B — Qwen 공식 GGUF 저장소 우선
- 실제 사용한 저장소 이름, 파일명, 양자화, 파일 크기를 기록
- 공식 GGUF 가 없거나 모델명이 다르면 임의로 대체하지 말고 멈추고 보고
- 다운로드 위치: `ROOT\models\` (디스크 여유가 60GB 미만이면 멈추고 보고)

### 2-3. 실행
- llama-server 로 한 번에 한 모델씩:
  `llama-server -m <gguf> -ngl 99 --tensor-split 1,1 -c 8192 --port 8080`
- 두 모델 모두 사고(thinking) 모드 끄기:
  - Qwen3: chat template 에서 enable_thinking=false 또는 user 메시지 끝에 `/no_think`
  - EXAONE 4.0: 모델 카드에 안내된 비추론(non-reasoning) 모드로 호출
  - 적용 방법과, 실제 출력에 `<think>` 태그가 없는지 리포트에 기록
- 생성 파라미터: temperature 0.3, top_p 0.9, max_tokens 1200
- 문항: pilot_set.jsonl 에서 도메인별 7·7·6건 무작위 (seed 42) → `pilot/teacher_items.jsonl`
  (풀이 부족한 도메인은 가능한 만큼 뽑고 기록)
- 모델·문항별 생성 시간(초), 출력 토큰 수, 초당 토큰 수 기록

### 2-4. 프롬프트 (두 모델 동일, 수정 금지)

[system]
```
너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다. 확실하지 않은 내용은 단정하지 않는다.
```

[user]
```
아래는 실제 법률 상담 질문과, 변호사가 작성한 답변입니다.
변호사 답변을 근거로, 법률을 모르는 대학생이 이해할 수 있는 해설을 작성하세요.

[질문]
{question}

[변호사 답변]
{answer}

[작성 규칙]
- 결론은 반드시 변호사 답변의 결론과 같아야 합니다.
- 법조문 번호와 판례 번호는 변호사 답변에 나온 것만 쓰세요. 그 외에는 번호 없이 원칙만 설명하세요.
- 질문이나 답변에 없는 사실(금액·날짜·행위)을 지어내지 마세요.
- "변호사 답변에 따르면", "위 답변에서" 같은 표현을 쓰지 말고, 질문자에게 직접 설명하듯 쓰세요.
- 변호사 답변이 질문에 실제로 답하지 않거나, 내용이 부족해 해설을 쓸 수 없으면 다른 내용 없이 [SKIP] 만 출력하세요.

[출력 형식]
1. 🔍 핵심 쟁점: 무엇이 문제인지 1~2문장
2. 📜 관련 법 원칙: 적용되는 법리를 쉬운 말로
3. 💡 이유: 결론에 이르는 논리를 단계별로
4. 📝 이렇게 하세요: 질문자가 할 수 있는 구체적 행동
마지막 줄: 구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다.
```

### 2-5. 산출물
- `pilot/teacher_outputs.jsonl`: item_id, domain, question, answer(원문), model, output, gen_sec, out_tokens
- `pilot/TEACHER_COMPARE.md`: 문항별로 [질문] [변호사 답변] [모델 A 출력] [모델 B 출력] 을 나란히 배치.
  판정·평가 문구는 쓰지 말 것 (판정은 사람이 한다).
- 자동 집계만 추가: 모델별 [SKIP] 건수, 4개 섹션 헤더(1.~4.) 모두 있는 비율, 마지막 안내문 포함 비율,
  출력에 등장한 "제○조" 중 변호사 답변에 없는 조문 번호 목록(모델별)

---

## 최종 보고: `pilot/PILOT_REPORT.md`
- 0·1·2단계 각각: 실행 명령, 콘솔 출력 전문, 건수표, 예시
- 확인하지 못한 항목은 "미확인"으로 명시
- 2단계가 끝나면 멈출 것
