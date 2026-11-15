# USB_IMPORT

SRC = `D:\ai` (수정·삭제 없음). DST = `C:\Users\DMLAB_Server1\Contracted_Youth`.
복사 시각 2026-10-20. 키 값은 기록하지 않는다.

## 1. USB 조사

드라이브 D: Used 787660800 bytes, Free 60712714240. SRC 안 파일만 집계하면 더 작다.

```
TOTAL_FILES=21
TOTAL_BYTES=14003379
```

3단계:

```
DEPTH 0 . dirs=2 files=0
  DIR exp_gap1
  DIR exp_gap2
DEPTH 1 exp_gap1 dirs=1 files=0
  DIR exp_gap1\data
DEPTH 2 exp_gap1\data dirs=0 files=6
DEPTH 1 exp_gap2 dirs=2 files=0
  DIR exp_gap2\data
  DIR exp_gap2\out
DEPTH 2 exp_gap2\data dirs=0 files=7
DEPTH 2 exp_gap2\out dirs=0 files=8
```

확장자: `.jsonl` 13개 11796786 bytes, `.json` 7개 2200453 bytes, `.txt` 1개 6140 bytes.
`.gguf` `.safetensors` `.npy` 0. 스크립트 0. `exp_gap1\prompts` 없음. `exp_gap1\out` 없음. `exp_gap2\prompts` 없음. `distill_audit\items.csv` 없음.

| 경로 | 크기 | 줄 수 |
|---|---|---|
| exp_gap1\data\e1.jsonl | 없음 | |
| exp_gap1\data\e2.jsonl | 145677 | 200 |
| exp_gap1\data\e3.jsonl | 없음 | |
| exp_gap1\data\law_yakgwan_6_14.txt | 6140 | 53 (CRLF 52) |
| exp_gap2\data\e2_test1000.jsonl | 1564483 | 1000 |
| exp_gap2\data\e2_pool_train.jsonl | 1991158 | 1262 |
| exp_gap2\data\e2_c4_candidates.jsonl | 1086036 | 500 |
| exp_gap2\data\e1_pool_train.jsonl | 4423948 | 4685 |
| exp_gap2\data\e2_c5_neighbors.json | 2155631 | JSON 객체 키 1000 |
| exp_gap2\out\32B_E2_C2.jsonl | 566508 | 1000 |
| exp_gap2\out\32B_E2_C4.jsonl | 265649 | 500 |
| exp_gap2\out\32B_E2_C5.jsonl | 169547 | 299 |
| exp_gap2\out\32B_E2_R.jsonl | 116155 | 200 |
| exp_gap2\out\8B_E2_C2.jsonl | 581669 | 1000 |
| exp_gap2\out\8B_E2_C4.jsonl | 243076 | 500 |
| exp_gap2\out\8B_E2_C5.jsonl | 526028 | 1000 |
| exp_gap2\out\8B_E2_R.jsonl | 116852 | 200 |
| exp_gap2\distill_audit\items.csv | 없음 | |

비밀값 패턴 (`OC=`, `OPEN_LAW_KEY`, `HF_TOKEN`, `hf_`, `gsk_`, `csk-`, `sk-or-`, `freellmapi-`, `ENCRYPTION_KEY`, `.encryption-key`): 텍스트 21개 스캔, hits=0. 복사 제외 파일 0.

## 2. 복사

```
copied=21 skip_same=0 conflict=0 mismatch=0 skipped_model=0 rows=21
```

복사 후 SHA-256 일치 21. 불일치 0. 이미 동일해서 건너뛴 파일 0. 충돌 0.
목록: `freellm\usb_manifest.csv` (path, bytes, sha256, status). 파일 내용은 넣지 않음.

## 3. 검증

`law_yakgwan_6_14.txt`: BOM 없음. CRLF=52, LF 단독=0. 디스크 글자 수 2592. `read_text` / LF 정규화 글자 수 2540. 제6조~제14조 9/9.

| 조 | 제목 |
|---|---|
| 6 | 일반원칙 |
| 7 | 면책조항의 금지 |
| 8 | 손해배상액의 예정 |
| 9 | 계약의 해제ㆍ해지 |
| 10 | 채무의 이행 |
| 11 | 고객의 권익 보호 |
| 12 | 의사표시의 의제 |
| 13 | 대리인의 책임 가중 |
| 14 | 소송 제기의 금지 등 |

`e2.jsonl` 200줄. `GAP1_REPORT.md` 는 SRC와 DST에 0건이라 오답 샘플 문구 대조는 미확인. 요청 id 7개는 파일에 있다.

| id | gold_articles | 조항 앞부분 |
|---|---|---|
| E2-0000 | [6] | (000의 000 가맹계약서) 제17조 영업의 명의변경 및 양도양수 |
| E2-0002 | [10] | (00000) 제13조 (보험금 지급에 관한 세부규정) |
| E2-0003 | [11] | 제6조 (보증금의 처리) |
| E2-0004 | [7] | 제23조제8항(기타규정) |
| E2-0005 | [11] | 제5조(관리 및 소유권) 2항 |
| E2-0006 | [6] | (하와이 6일 허니문) |
| E2-0007 | [6] | 제9조(기한이익의 상실) |

건수: `e2_test1000` 1000, `e2_c4_candidates` 500, 32B C2 1000, 32B C4 500, 32B C5 299, 8B C2 1000, 8B C4 500, 8B C5 1000.

조인 실패 (id가 표본에 없는 줄 수):

| 출력 | e2_test1000 | e2_c4_candidates | e2.jsonl | e2_c5_neighbors 키 |
|---|---|---|---|---|
| 32B/8B C2 | 0 | 500 / 500 |  | 0 |
| 32B/8B C4 | 0 | 0 |  | 0 |
| 32B C5 | 0 | 0 |  | 0 |
| 8B C5 | 0 | 500 |  | 0 |
| 32B_E2_R, 8B_E2_R | 200 | 200 | 0 | 200 |

C2·C4·C5 는 `e2_test1000` 과 조인 실패 0. R 200줄은 `e2.jsonl` 과 조인 실패 0.

학습 후보 재계산 (`audit.py` 의 위모두 조건, 토크나이저 없이, 파일은 쓰지 않음):

```
UNIQUE 491 C2=315 C4=219 C5=185
OVERLAP C2C4=109 C2C5=74 C4C5=103 ALL3=58
GAP1_NORM_CORR32 0
GAP1_SRC_CORR32 0
GAP1_NORM_KEEP 0
GAP1_SRC_KEEP 0
LEARN 32B_C2 correct=482 all=315
LEARN 32B_C4 correct=363 all=219
LEARN 32B_C5 correct=220 all=185
```

`meta.json` 의 unique 491, 교집합 109/74/103/58, GAP-1 겹침 0, 위모두 315/219/185 와 같다. `items.csv` 는 여전히 없음.

## 4. 연결 시험

자료 포함 재실행은 `SETUP_REPORT_SERVER1.md` 4장과 `smoke_results_law.jsonl`. 성공 모델 3. 정규화 후 대체는 nemotron 만.

## 5. .gitignore

기존: `exp_gap2/data/`, `exp_gap1/data/**/*.jsonl`, `exp_gap2/out/**/*8B*`.
빠져 있던 조항 txt·json 과 32B 출력 jsonl 을 추가. 사본 `.gitignore.before-usb.bak`. `git diff --no-index` exit 1 (차이 있음):

```
+exp_gap1/data/
+exp_gap2/out/**/*.jsonl
```

git add 는 하지 않음. WORK 는 git 저장소가 아니다 (`dotgit=False` 가 이전 조사에 있음).
