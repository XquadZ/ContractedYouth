# TRANSFER_CHECK

검사 대상: `C:\Users\DMLAB_Server1\Contracted_Youth`  
읽기만 수행. 파일 수정·삭제, commit/push/reset 없음.  
키 값은 앞 4자만 적는다.

## 요약

| 항목 | 결과 | 근거 |
|---|---|---|
| 원격 공개 여부 | 미확인 | `.git` 없음. `gh` 없음. GitHub 웹에서 Public/Private 확인 필요 |
| law_yakgwan_6_14.txt | 없음 | 이 PC 사용자 프로필 검색 0건. 글자 수·해시 비교 불가 |
| system_rag.txt | 미확인 | 글자 수 517. SHA-256 `9e48cdc8023610498541d425b3697ae5fcd17ab428955c24bb3a87afa64ccdc8`. 예전 PC 해시 기록 없음 |
| user_e2.txt | 미확인 | 글자 수 196. SHA-256 `3c74545ad3c02b2f1bcc91924fd2eb9e0bf817903018edc4e621d90e5adb07c2`. 예전 PC 해시 기록 없음 |
| 비밀값 발견 | 1 (작업 트리 1 / 이력 미확인) | `freellm\.env:1` ENCRYPTION_KEY `b782****` |
| AI Hub 데이터 커밋 | 미확인 (작업 트리 2369개, 106194569 bytes) | `.git` 없어 커밋 여부 확인 불가. 작업 트리에 있음 |
| 모델 파일 커밋 | 0 (작업 트리) / 이력 미확인 | `.gguf` `.safetensors` `.bin` 0개. `models\` 없음 |
| 재현 파일 누락 | 14개 | 아래 4장 |

## 1. 저장소 기본 정보

클론 경로로 지정된 곳: `C:\Users\DMLAB_Server1\Contracted_Youth`

```
dotgit=False
```

```
git -C C:\Users\DMLAB_Server1\Contracted_Youth remote -v
fatal: not a git repository (or any of the parent directories): .git
REMOTE_EXIT=128
```

```
git -C C:\Users\DMLAB_Server1\Contracted_Youth log -1 --format="%H %ad %an"
fatal: not a git repository (or any of the parent directories): .git
LOG_EXIT=128
```

```
git -C C:\Users\DMLAB_Server1\Contracted_Youth branch --show-current
BRANCH_EXIT=128
```

```
git -C C:\Users\DMLAB_Server1\Contracted_Youth status --short
fatal: not a git repository (or any of the parent directories): .git
STATUS_EXIT=128
status_output_lines=1
```

`git status --short` 의 정상 출력 줄 수는 0. 위 1줄은 fatal 메시지다. 현재 브랜치 없음.

`docs\GIT_SETUP.md` 23행의 remote 는 자리표시자 `https://github.com/<USER>/<REPO>.git` 이다. 실제 URL 없음. 토큰이 박힌 URL 없음.

`gh repo view --json visibility,nameWithOwner` 는 실행되지 않음.

```
gh_not_found
```

`where.exe gh` 는 일치 파일 없음. 공개 여부는 **미확인**. GitHub 웹에서 해당 저장소의 Public/Private 를 확인해 달라.

이 PC의 다른 git 저장소(`C:\Users\DMLAB_Server1\AI_Service`, `C:\Users\DMLAB_Server1\capstone`)는 remote 가 다르고, 대상 3개 파일은 그 안에 0건이었다. WORK 검사에 넣지 않았다.

## 2. 핵심 파일

`where /r C:\Users\DMLAB_Server1 law_yakgwan_6_14.txt` → `WHERE_EXIT=1` (파일 없음).  
WORK 재귀 검색에서 `law_yakgwan_6_14.txt` 0건. `system_rag.txt` 2건, `user_e2.txt` 2건.

### system_rag.txt (2개, 해시 동일)

`exp_gap1\prompts\system_rag.txt` 와 `exp_gap2\prompts\system_rag.txt`

```
BYTES=1157 CHARS=517 LINES=12 SHA256=9e48cdc8023610498541d425b3697ae5fcd17ab428955c24bb3a87afa64ccdc8
BOM=False UTF8_OK=True CRLF=0 LF_ONLY=12 CR_ONLY=0
CHARS_LF=517 CHARS_CRLF=529
```

### user_e2.txt (2개, 해시 동일)

`exp_gap1\prompts\user_e2.txt` 와 `exp_gap2\prompts\user_e2.txt`

```
BYTES=392 CHARS=196 LINES=6 SHA256=3c74545ad3c02b2f1bcc91924fd2eb9e0bf817903018edc4e621d90e5adb07c2
BOM=False UTF8_OK=True CRLF=0 LF_ONLY=6 CR_ONLY=0
CHARS_LF=196 CHARS_CRLF=202
```

### law_yakgwan_6_14.txt

파일 0. 글자 수 2540 과 비교 불가. LF 정규화·CRLF 정규화 글자 수 없음. 제6조~제14조 패턴 0/9.

제목 확인 결과 (전부 없음): 일반원칙, 면책조항의 금지, 손해배상액의 예정, 계약의 해제ㆍ해지, 채무의 이행, 고객의 권익 보호, 의사표시의 의제, 대리인의 책임 가중, 소송 제기의 금지.

### git 줄바꿈

```
git ls-files --eol -- exp_gap1/prompts/system_rag.txt
fatal: not a git repository (or any of the parent directories): .git
LS_EXIT=128
```

```
git config --global --get core.autocrlf
GLOBAL_AUTOCRLF_EXIT=1
```

전역 값 출력 없음 (unset). 저장소 local:

```
fatal: --local can only be used inside a git repository
LOCAL_AUTOCRLF_EXIT=128
```

`.gitattributes`: `GITATTRIBUTES=False`. 내용 없음.

있는 두 파일은 CRLF 0, LF 단독만 있다. 예전 PC 해시가 없어 "줄바꿈만 다름" 판정은 하지 않는다.

GAP-1 이 프롬프트를 읽는 코드 (`newline` 인자 없음. `Path.read_text` 기본값은 텍스트 모드에서 `\r\n` 을 `\n` 으로 바꾼다):

```20:23:exp_gap1/scripts/run_gap1.py
SYSTEM_NORAG = (PROMPTS / "system_norag.txt").read_text(encoding="utf-8")
SYSTEM_RAG = (PROMPTS / "system_rag.txt").read_text(encoding="utf-8")
USER_E1 = (PROMPTS / "user_e1.txt").read_text(encoding="utf-8")
USER_E2 = (PROMPTS / "user_e2.txt").read_text(encoding="utf-8")
```

약관 파일:

```14:14:exp_gap1/scripts/build_c2_materials.py
    yak = (DATA / "law_yakgwan_6_14.txt").read_text(encoding="utf-8")
```

글자 수 기록은 `prepare_data.py` 의 `len(blob)` 이다. `blob = "\n\n".join(texts)` 후 `write_text(blob, encoding="utf-8")`. 저장된 `law_yakgwan_meta.json` 은 이 PC에 없다 (`n_chars` 값 2540 은 코드에 하드코딩되어 있지 않음).

### 예전 PC 해시

저장소 안 기록에서 이 3개 파일의 SHA-256 을 찾지 못했다. `exp_gap2\distill_audit\meta.json` (1877 bytes) 에는 파일 해시가 없다. `freellm\ENV_CHECK.md` 의 64자 hex 는 Docker 이미지 digest 이지 이 3개 파일 해시가 아니다.

비교: **미확인**. 예전 PC에서:

```
Get-FileHash "C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1\data\law_yakgwan_6_14.txt" -Algorithm SHA256
Get-FileHash "C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1\prompts\system_rag.txt" -Algorithm SHA256
Get-FileHash "C:\Users\DMLAB\Desktop\학부-AI서비스 개발\exp_gap1\prompts\user_e2.txt" -Algorithm SHA256
```

판정: 파일 없음 → law 는 "없음". 해시 미대조 → system_rag, user_e2 는 "미확인". "다름" diff 20줄은 해당 없음.

## 3. 올라가면 안 되는 것

이력: `git log --all` 불가 (exit 128). **이력에만 있음** 은 전부 미확인. 아래는 작업 트리만.

### 비밀값

텍스트 3143개 스캔. 3MB 초과 3개는 접두 패턴만 추가 스캔 (적중 0).

| 구분 | 건수 | 내용 |
|---|---|---|
| 값이 있는 비밀 | 1 | `freellm\.env:1` 종류 ENCRYPTION_KEY, `b782****` |
| hf_ / gsk_ / csk- / sk-or- / sk- 값 | 0 | |
| HF_TOKEN, OPEN_LAW_KEY, FREELLM_KEY= 값 | 0 | 이름 문자열만. HF_TOKEN 이름 적중은 README, 스크립트, `docs\experiments\2026-10-14.md` |
| OC= | 대부분 | 작업 트리 JSON 의 `OC=REDACTED` 와 스크립트의 `oc()` / `os.environ`. 값으로 남은 OC 키 0 |
| .encryption-key | 이름만 | `.gitignore`, `freellm\encryption_key_meta.txt:1` (경로 문자열 `%APPDATA%\FreeLLMAPI\.encryption-key`). 그 파일은 이 PC에 없음 (`APPDATA` 검사 이전 기록 EXISTS=False) |

추가 스캔한 큰 파일 (접두 적중 0):

```
32296382 data\datasets\LawQA-Ko\law_qa_dataset.jsonl
4716019 experiments\pilot\train_pool_lawqa.jsonl
3053205 experiments\run3\teacher_outputs.jsonl
```

작업 트리 비밀값 1. 이력 미확인.

### AI Hub·약관·실험 jsonl

확장자 `.json` `.jsonl` `.csv` `.zip` 이고 경로에 `aihub` / `약관` / `019` / 계약+서식 이 있는 파일.

```
count=2369 bytes=106194569
EXT json=2367 jsonl=1 csv=1 zip=0
```

106194569 bytes = 106.194569 MB (10^6) = 101.27 MiB (1024^2).

`019` 54건은 별도 데이터셋 폴더가 아니다. `aihub` 파일 이름 안의 `0019` 같은 부분 문자열이다. 위 2369에 이미 포함된다. 경로에 `계약` 과 `서식` 이 같이 있는 추가 파일은 0.

폴더별 개수·바이트 (작업 트리에 있음. 커밋 여부는 미확인):

| n | bytes | 경로 |
|---|---|---|
| 513 | 27038144 | data_contract\aihub_forms\TS_인사_고용_노무_고용계약 |
| 513 | 23895986 | data_contract\aihub_forms\TL_인사_고용_노무_고용계약 |
| 346 | 17508756 | data_contract\aihub_forms\TS_부동산매매_임대차_부동산임대 |
| 346 | 15532782 | data_contract\aihub_forms\TL_부동산매매_임대차_부동산임대 |
| 192 | 5987293 | data_contract\aihub_forms\TS_금전소비대차_채권_채무_채권_채무계약 |
| 192 | 5354198 | data_contract\aihub_forms\TL_금전소비대차_채권_채무_채권_채무계약 |
| 64 | 3003737 | data_contract\aihub_forms\VS_인사_고용_노무_고용계약 |
| 64 | 2659678 | data_contract\aihub_forms\VL_인사_고용_노무_고용계약 |
| 43 | 1987042 | data_contract\aihub_forms\VS_부동산매매_임대차_부동산임대 |
| 43 | 1766193 | data_contract\aihub_forms\VL_부동산매매_임대차_부동산임대 |
| 24 | 738555 | data_contract\aihub_forms\VS_금전소비대차_채권_채무_채권_채무계약 |
| 24 | 661560 | data_contract\aihub_forms\VL_금전소비대차_채권_채무_채권_채무계약 |
| 2 | 26678 | data_contract\law_api\공정위 (약관 파일 2개, 아래) |
| 1 | 26637 | experiments\pilot\eval_aihub_ood.jsonl |
| 1 | 4974 | data_contract\aihub_forms\label_vocab.csv |
| 1 | 2356 | data_contract\law_api\법령용어\lstrmRlt_v2\약관.json |

약관 3개:

```
13339 data_contract\law_api\공정위\g2_full\ftc_임대차_약관_p1.json
13339 data_contract\law_api\공정위\v2\list_임대차_약관.json
2356 data_contract\law_api\법령용어\lstrmRlt_v2\약관.json
```

실험·모델 출력 jsonl 13개, 합계 5346686 bytes. 전부 작업 트리에 있음. 이력 미확인.

| bytes | 경로 |
|---|---|
| 258038 | exp_gap2\distill_export\32B_E2_C2.jsonl |
| 109299 | exp_gap2\distill_export\32B_E2_C4.jsonl |
| 71407 | exp_gap2\distill_export\32B_E2_C5.jsonl |
| 52752 | exp_gap2\distill_export\32B_E2_R.jsonl |
| 146894 | experiments\pilot\teacher_outputs.jsonl |
| 816942 | experiments\run3\eval_outputs.jsonl |
| 276870 | experiments\run3\eval_outputs_A.jsonl |
| 291682 | experiments\run3\eval_outputs_B.jsonl |
| 248390 | experiments\run3\eval_outputs_C.jsonl |
| 4865 | experiments\run3\smoke\eval_outputs.jsonl |
| 4865 | experiments\run3\smoke\eval_outputs_A.jsonl |
| 11477 | experiments\run3\smoke\teacher_outputs.jsonl |
| 3053205 | experiments\run3\teacher_outputs.jsonl |

`exp_gap1\data` 의 e1/e2/e3 jsonl 은 없음. `e2_test1000.jsonl` 없음.

### 모델 파일

`.gguf` `.safetensors` `.bin` 작업 트리 0개, 0 bytes. `models\` 디렉터리 없음. 이력 미확인.

## 4. 재현 파일

| 경로 | 결과 |
|---|---|
| exp_gap1\data\e1.jsonl | 없음 |
| exp_gap1\data\e2.jsonl | 없음 |
| exp_gap1\data\e3.jsonl | 없음 |
| exp_gap1\data\law_yakgwan_6_14.txt | 없음 |
| exp_gap1\prompts\system_norag.txt | 1086 bytes |
| exp_gap1\prompts\system_rag.txt | 1157 bytes |
| exp_gap1\prompts\user_e1.txt | 193 bytes |
| exp_gap1\prompts\user_e2.txt | 392 bytes |
| exp_gap1\prompts\user_e3.txt | 266 bytes |
| exp_gap2\data\e2_test1000.jsonl | 없음 (`exp_gap2\data` 디렉터리 없음) |
| exp_gap2\data\e2_pool_train.jsonl | 없음 |
| exp_gap2\data\e2_c4_candidates.jsonl | 없음 |
| exp_gap2\out\32B_E2_C2.jsonl | 없음 (`exp_gap2\out` 없음) |
| exp_gap2\out\32B_E2_C4.jsonl | 없음 |
| exp_gap2\out\32B_E2_C5.jsonl | 없음 |
| exp_gap2\out\8B_E2_C2.jsonl | 없음 |
| exp_gap2\out\8B_E2_C4.jsonl | 없음 |
| exp_gap2\out\8B_E2_C5.jsonl | 없음 |
| exp_gap2\distill_audit\items.csv | 없음 |

`exp_gap2\distill_audit` 에 있는 파일: `audit.py` 36074 bytes, `meta.json` 1877 bytes.

`exp_gap2\out` 은 없고, 비슷한 이름이 `exp_gap2\distill_export` 에 있다. 줄 수:

```
lines=1000 bytes=258038 32B_E2_C2.jsonl
lines=500 bytes=109299 32B_E2_C4.jsonl
lines=299 bytes=71407 32B_E2_C5.jsonl
lines=200 bytes=52752 32B_E2_R.jsonl
```

8B_E2_C2 / C4 / C5 jsonl 은 `distill_export` 에도 0건. `meta.json` 의 `file_counts` 는 8B_C2=1000, 8B_C4=500 이고 8B_C5 키는 없다. 그 출력 파일은 이 트리에 없다.

누락 14 = gap1 data 4 + gap2 data 3 + gap2 out 6 + items.csv 1. prompts 5개는 있음.
