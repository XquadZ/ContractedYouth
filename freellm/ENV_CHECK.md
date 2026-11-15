# ENV_CHECK

조사 시각: 2026-10-20. 설치 전 명령 출력. 키 값은 기록하지 않는다.

## 1. hostname / whoami

```
DESKTOP-QFEENP2
desktop-qfeenp2\dmlab_server1
---USER---
DMLAB_Server1
---COMPUTERNAME---
DESKTOP-QFEENP2
```

## 2. 이전 PC 경로

명령: `Test-Path -LiteralPath 'C:\Users\DMLAB\Desktop\학부-AI서비스 개발\freellm'`

```
PATH_EXISTS=False
previous path missing
---DMLAB_USER---
DMLAB_PROFILE_EXISTS=False
```

`C:\Users\DMLAB` 프로필이 없다. 이 PC(DESKTOP-QFEENP2, 사용자 DMLAB_Server1)와 이전 PC는 다른 컴퓨터다. SETUP 기록, PROVIDERS.md, client.py는 이 PC에서 읽지 못했다.

## 3. WORK 폴더

`C:\Users\DMLAB_Server1\Contracted_Youth`

PowerShell `Get-ChildItem -Force` 깊이 1·2:

```
WORK_EXISTS=True
=== DEPTH 1 ===
=== DEPTH 2 ===
```

`cmd /c dir /a` (종료 코드 0). 콘솔 코드 페이지 때문에 한글이 깨져 보였고, 파일 행은 아래와 같다.

```
2026-10-20  <DIR>  .
2026-10-20  <DIR>  ..
0개 파일  0 바이트
2개 디렉터리
```

파일 수 0. 하위 폴더 수 0.

이름 확인 결과 없음: `exp_gap1`, `exp_gap2`, `data_contract`, `prompts`.

## 4. FreeLLMAPI 실행·설치 흔적

```
=== NETSTAT ===
=== NETSTAT_EXIT=1 ===
```

`netstat -ano | findstr ":31415 :3001"` 일치 줄 0. 대응 PID 없음.

```
APPDATA=C:\Users\DMLAB_Server1\AppData\Roaming
FREELLMAPI_DIR_EXISTS=False
```

`%APPDATA%\FreeLLMAPI\` 없음. 파일 이름 0개.

프로세스 검색: 이름 또는 명령줄에 `freellm`이 있는 프로세스 0개. 포트 31415·3001을 연 프로세스 0개.

`where.exe freellm`, `where.exe freellmapi`: 둘 다 일치 파일 없음 (findstr/where 종료 코드 1).

`docker ps -a` 에 freellmapi 컨테이너 없음. 당시 컨테이너:

```
2b1ef85a49df distillwalk/dwk:latest Exited (0) 4 months ago  dwk-inference
ef88c32012ad milvusdb/milvus:v2.4.5 Up 2 days 0.0.0.0:9091->9091/tcp, [::]:9091->9091/tcp, 0.0.0.0:19530->19530/tcp, [::]:19530->19530/tcp milvus-standalone
e26010571bc7 quay.io/coreos/etcd:v3.5.0 Up 2 days 2379-2380/tcp milvus-etcd
eeecd931e1a4 minio/minio:RELEASE.2023-03-20T20-16-18Z Up 2 days (healthy) 9000/tcp milvus-minio
```

`docker images` 에서 `freellm` 일치 0건 (`FINDSTR_EXIT=1`).

## 5. Python / openai

```
=== PYTHON ===
Python 3.13.5
PY_EXIT=0
```

`py -3` 은 이 셸에서 명령으로 인식되지 않음 (`CommandNotFoundException`).

```
=== PIP OPENAI ===
Name: openai
Version: 1.107.0
Summary: The official Python library for the openai API
Home-page: https://github.com/openai/openai-python
Author:
Author-email: OpenAI <support@openai.com>
License: Apache-2.0
Location: C:\Users\DMLAB_Server1\anaconda3\Lib\site-packages
Requires: anyio, distro, httpx, jiter, pydantic, sniffio, tqdm, typing-extensions
Required-by: langchain-openai
PIP_EXIT=0
```

## 6. FREELLM_KEY

값은 출력하지 않음. Process / User / Machine 세 범위 모두 비어 있음.

```
FREELLM_KEY_Process=없음 len=0
FREELLM_KEY_User=없음 len=0
FREELLM_KEY_Machine=없음 len=0
```

(콘솔 코드 페이지에서 `없음` 글자가 깨져 표시됨. 판정은 빈 문자열, len=0.)

## 7. Docker / Node / git

```
=== DOCKER ===
Docker version 29.2.1, build a5c7197
DOCKER_EXIT=0
=== NODE ===
v24.16.0
NODE_EXIT=0
=== GIT ===
git version 2.51.2.windows.1
```

```
Docker Compose version v5.0.2
```

`git -C C:\Users\DMLAB_Server1\Contracted_Youth rev-parse --is-inside-work-tree` 종료 코드 128:

```
fatal: not a git repository (or any of the parent directories): .git
```

`GITIGNORE_EXISTS=False`

## 경로 선택

선택: **C** (이 PC에 FreeLLMAPI 없음 → 설치).

근거:

- A 아님. 4번의 `netstat` 종료 코드 1, 31415·3001 수신 줄 0.
- B 아님. `%APPDATA%\FreeLLMAPI` 없음, `where` 없음, freellm 이미지·컨테이너 0건.
- D 하지 않음. 이전 경로 `PATH_EXISTS=False`. 네트워크로 이전 PC에 붙이지 않음.
- 설치 방식: portable `FreeLLMAPI-0.16.5-win.zip` 조건은 "Docker·Node가 없으면"이다. 7번에서 Docker 29.2.1과 Node v24.16.0이 있으므로 그 조건에 해당하지 않는다. README Docker Compose 절차를 쓰고 이미지는 `ghcr.io/tashfeenahmed/freellmapi:v0.16.5`로 고정한다. 공식 compose의 `restart: unless-stopped`는 쓰지 않고 `restart: "no"`로 둔다. 포트는 `127.0.0.1:3001`만 연다.

설치 명령 출력은 이 파일 아래 "설치 기록"에 이어서 붙인다.

## 추가 조사 (같은 날, 첫 dir 이후)

첫 `dir /a` 는 파일 0, 하위 폴더 0 이었다. 그 다음 목록에서는 파일이 있었다. `freellm` 쪽 복사본의 LastWriteTime 은 `2026-10-20 12:24:41`.

깊이 1 (재귀 파일 수):

```
DIR  data            subdirs=2  files_recursive=40
DIR  data_contract   subdirs=5  files_recursive=2927
DIR  docs            subdirs=3  files_recursive=12
DIR  experiments     subdirs=3  files_recursive=133
DIR  exp_gap1        subdirs=2  files_recursive=12
DIR  exp_gap2        subdirs=5  files_recursive=46
DIR  freellm         subdirs=0  files_recursive=12
DIR  scripts         subdirs=0  files_recursive=1
DIR  tools           subdirs=0  files_recursive=1
FILE .gitignore      bytes=3213
FILE README.md       bytes=1921
```

`exp_gap1`, `exp_gap2`, `data_contract` 있음.

프롬프트:

```
exp_gap1\prompts\system_rag.txt  1157
exp_gap1\prompts\user_e2.txt      392
exp_gap2\prompts\system_rag.txt  1157
exp_gap2\prompts\user_e2.txt      392
```

`law_yakgwan*` 파일 수 0. `%APPDATA%\FreeLLMAPI` 는 재확인해도 `EXISTS=False`.

`freellm\HOWTO.md` 와 `SETUP_REPORT.md` 는 이전 PC portable (`127.0.0.1:31415`, `C:\Users\DMLAB\Desktop\...`) 기록이다. 실행 파일은 이 PC에 없다. 경로 판정은 그대로 C.

## 설치 기록

방식: Docker Compose. 이미지 `ghcr.io/tashfeenahmed/freellmapi:v0.16.5`. portable zip 아님. 이유: Docker `29.2.1`, Node `v24.16.0` 이 있어 "Docker·Node가 없으면 portable" 조건에 해당하지 않음. 공식 compose 의 `restart: unless-stopped` 와 `:latest`, `build:` 는 넣지 않음. `restart: "no"`. 포트 `127.0.0.1:3001` 만.

`docker compose pull` 마지막 줄:

```
Image ghcr.io/tashfeenahmed/freellmapi:v0.16.5 Pulled
```

이미지:

```
Id=sha256:b602fa2e581e63fc1543076e6175d405c677b63123b1fbfe753cf86614a01bea Created=2026-10-19T10:47:09.887590542Z
["ghcr.io/tashfeenahmed/freellmapi@sha256:b602fa2e581e63fc1543076e6175d405c677b63123b1fbfe753cf86614a01bea"]
```

`docker compose up -d`:

```
Network freellm_default Creating
Network freellm_default Created
Volume freellm_freellmapi-data Creating
Volume freellm_freellmapi-data Created
Container freellm-freellmapi-1 Creating
Container freellm-freellmapi-1 Created
Container freellm-freellmapi-1 Starting
Container freellm-freellmapi-1 Started
```

```
freellm-freellmapi-1 Up 12 seconds (healthy) 127.0.0.1:3001->3001/tcp
running health=healthy image=ghcr.io/tashfeenahmed/freellmapi:v0.16.5
RestartPolicy=no Binds={"3001/tcp":[{"HostIp":"127.0.0.1","HostPort":"3001"}]}
```

ENCRYPTION_KEY: README PowerShell `RandomNumberGenerator` 32바이트 hex. 값 미기록. 저장 위치 `C:\Users\DMLAB_Server1\Contracted_Youth\freellm\.env`. 검사: `ENV_BYTES=90`, `ENV_KEY_LINE_OK=True`, `ENV_PORT_LINE=True`. 로그에 `ENCRYPTION_KEY=` 없음 (`LOG_HAS_ENCRYPTION_KEY_ASSIGN=False`, `LOG_LONG_HEX_COUNT=0`).

`GET http://127.0.0.1:3001/` :

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 1572
CURL_HTTP_CODE=200
```

`GET http://127.0.0.1:3001/v1/models` (Authorization 없음):

```
HTTP/1.1 401 Unauthorized
Content-Type: application/json; charset=utf-8
Content-Length: 69
CURL_HTTP_CODE=401
{"error":{"message":"Invalid API key","type":"authentication_error"}}
```

`netstat -ano | findstr ":3001"`:

```
TCP    127.0.0.1:3001         0.0.0.0:0              LISTENING       23532
```

PID 23532 = `com.docker.backend`.

`.gitignore`: 저장소 아님 (`git diff` 종료 코드 129, `fatal`/`not a git repository`). 들어온 파일에 `.env`, `freellm/app/`, `**/.encryption-key` 가 이미 있음. `*.encryption-key` 한 줄이 없어 `.gitignore.bak` 를 남기고 추가함. diff:

```
--- .gitignore.bak
+++ .gitignore
@@
 **/.encryption-key
+*.encryption-key
```

`FREELLM_KEY` Process/User/Machine len=0. 5장·6장 연결 시험은 하지 않음.
