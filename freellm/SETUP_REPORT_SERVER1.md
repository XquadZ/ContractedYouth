# SETUP_REPORT_SERVER1

시각: 2026-10-20. 키 값은 기록하지 않는다.

## 1. 조사 요약와 경로

경로 **C**. 근거는 `freellm\ENV_CHECK.md`.

- 호스트 `DESKTOP-QFEENP2`, 사용자 `desktop-qfeenp2\dmlab_server1`.
- 이전 PC 경로 `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\freellm` 는 `PATH_EXISTS=False`.
- 조사 당시 `netstat` 의 31415·3001 수신 줄 0 (`NETSTAT_EXIT=1`). `%APPDATA%\FreeLLMAPI` 없음.
- 이 PC는 Docker `29.2.1`, Node `v24.16.0` 이 있어 portable zip 조건(Docker·Node가 없으면)에 해당하지 않음.
- 이미지 `ghcr.io/tashfeenahmed/freellmapi:v0.16.5`. 바인딩 `127.0.0.1:3001`. `restart: "no"`.

## 2. 실행 주소·버전·시작/중지

| 항목 | 값 |
|---|---|
| 주소 | `http://127.0.0.1:3001` |
| API base | `http://127.0.0.1:3001/v1` (`FREELLM_BASE` 가 있으면 그 값) |
| 이미지 | `ghcr.io/tashfeenahmed/freellmapi:v0.16.5` |
| digest | `sha256:b602fa2e581e63fc1543076e6175d405c677b63123b1fbfe753cf86614a01bea` |
| 시작 | `cd freellm` 후 `docker compose up -d` |
| 중지 | `docker compose stop` |

키: 프로세스에서 `UNI_API_KEY` 길이 59 (`key_source=UNI_API_KEY:process`). 사용자 환경변수 `UNI_API_KEY` 길이도 59. `FREELLM_KEY` 사용자 길이 39는 읽지 않음. `client.py` 는 `UNI_API_KEY` 를 먼저, 없으면 `FREELLM_KEY` 를 프로세스 환경 다음 Windows 레지스트리에서 읽는다. 변경 전 사본은 `freellm\client.py.bak`.

`GET /v1/models` (통합 키) HTTP 200, body 130881 bytes. 저장: `freellm\models_raw.json`.

모델 수: 전체 277. `available=true` 23. `available=false` 254.

## 3. 시험 모델

목록에 Groq·Cerebras·OpenRouter 가 붙은 id 는 없다. `gpt-oss-120b` 는 id 1개, `available=true`. `openrouter` 문자열 id 0개.

시험 id (목록 그대로):

- `gpt-oss-120b` (`reasoning_effort=low`, HTTP 400 없음, 적용함)
- `nemotron-3-super-120b` (대형, `available=true`. OpenRouter 표기 없음)
- `gemma-4-31b` (두 번째 대형, `available=true`. OpenRouter 표기 없음)

`model="auto"` 는 `ValueError`. 호출하지 않음.

설정: temperature 0, max_tokens 512. 재시도 최대 5 (429·5xx·타임아웃, 지수 대기).

프롬프트: `exp_gap1\prompts\system_rag.txt` (1157 bytes), `user_e2.txt` (392 bytes). `{choices}` 는 `prepare_data.py` 의 제6조~제14조 기본 제목. `law_yakgwan_6_14.txt` 는 0건이라 `<자료>` 블록을 넣지 않음 (`law_file=no`, `law_chars=0`).

입력: `freellm\smoke_inputs.jsonl` 3줄 (S1, S2, S3). 결과: `freellm\smoke_results.jsonl` 9줄. 재채점 전 사본 `smoke_results.jsonl.bak`. `json_ok` 는 HTTP 200 이고 출력 객체에 `articles` 가 있을 때만 true.

자료 없이 돌린 이전 표는 `freellm\smoke_results.jsonl` (9줄)에 남아 있다. 아래는 `law_yakgwan_6_14.txt` 를 `<자료>`로 넣은 재실행이다. `read_text` 기준 자료 글자 수 2540. 선택지는 `exp_gap1\data\e2_choices.json` 의 `choices_line` (122자, 제13조 없음). 입력은 S1~S3만. 결과 `freellm\smoke_results_law.jsonl` 12줄.

대체 판정: `openai/` `nvidia/` 같은 접두사와 `:free` 를 지우고 소문자로 맞춘 뒤 비교. 제공사는 응답 헤더 `X-Routed-Via` 의 첫 구간. 그 헤더가 없으면 미확인. Docker 로그는 보지 않았다.

## 4. 연결 시험 (자료 포함)

| model | 실제 model | 대체 | 3건 성공 | JSON 파싱 | 한국어 | 평균 지연 | 비고 |
|---|---|---|---|---|---|---|---|
| gpt-oss-120b | openai/gpt-oss-120b | false | 3/3 | 3/3 | 3/3 | 1136.9 ms | X-Routed-Via=`groq/openai/gpt-oss-120b`. 제공사 groq. reasoning_effort=low 적용. 입력 토큰 2106/2108/2104 |
| qwen3.8-27b | qwen/qwen3.8-27b | false | 3/3 | 3/3 | 3/3 | 542.7 ms | X-Routed-Via=`groq/qwen/qwen3.8-27b`. 제공사 groq |
| nemotron-3-super-120b | nvidia/nemotron-3-super-120b-a12b:free | true | 3/3 | 1/3 | 1/3 | 6201.0 ms | X-Routed-Via=`openrouter/...:free`. 접두사·`:free` 제거 후에도 `nemotron-3-super-120b-a12b` 라서 대체. S1·S2 JSON 아님(출력 512) |
| gemma-4-31b | (없음) | false | 0/3 | 0/3 | 0/3 | 11.6 ms | HTTP 429, attempt=2 (재시도 1회). 헤더 없음. 제공사 미확인 |

연결 성공 모델: 3 (`gpt-oss-120b`, `qwen3.8-27b`, `nemotron-3-super-120b`). 정규화 후 대체가 남은 모델: nemotron 1개.

## 5. 미확인

- `GAP1_REPORT.md` 가 SRC·DST 에 없어 E2-0000 등 7건의 보고서 문구 대조는 못 했다. id 자체는 `e2.jsonl` 에 있다.
- `gemma-4-31b` 제공사. 429 응답에 `X-Routed-Via` 가 없었다.
- WORK 에 `.git` 이 없어 커밋 여부는 확인하지 않음. 조항 파일은 `.gitignore` 에 넣었다. git add 는 하지 않음.
