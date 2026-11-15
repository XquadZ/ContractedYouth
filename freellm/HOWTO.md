# FreeLLMAPI 시작·중지 (자동 부팅 설정 안 함)

## 설치 기록
| 항목 | 값 |
|---|---|
| 시도 순서 | (a) Docker 없음 → (b) Windows portable zip 사용 |
| 방식 | **(b) GitHub Releases portable** `FreeLLMAPI-0.16.5-win.zip` |
| 버전 | **v0.16.5** |
| 설치 경로 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\freellm\app\FreeLLMAPI.exe` |
| Setup exe (보관) | `freellm\install\FreeLLMAPI-Setup-0.16.5.exe` |
| 데이터 | `%APPDATA%\FreeLLMAPI\` (`freeapi.db`, `config.json`, `logs\`) |
| ENCRYPTION_KEY | 생성됨(앱 자동). 저장 위치: `%APPDATA%\FreeLLMAPI\.encryption-key` (값 미기록) |
| 실제 listen | **`http://127.0.0.1:31415`** (Desktop 기본. README의 3001은 Docker/서버 기본. config에 3001을 써도 재기동 시 31415로 유지됨) |

## 시작
```powershell
Start-Process "C:\Users\DMLAB\Desktop\학부-AI서비스 개발\freellm\app\FreeLLMAPI.exe"
```
- 트레이 아이콘 → **Open Dashboard** → 브라우저 `http://127.0.0.1:31415`
- 통합 키: 트레이 **Copy Key** 또는 Keys 페이지 헤더 (값은 로그에 넣지 말 것)
- 클라이언트 base URL: `http://127.0.0.1:31415/v1`
- 환경변수: `FREELLM_KEY` = 통합 키, `FREELLM_BASE` = `http://127.0.0.1:31415/v1` (선택)

## 중지
```powershell
Get-Process FreeLLMAPI -ErrorAction SilentlyContinue | Stop-Process
```
또는 트레이 아이콘 → Quit.

## 키 등록
1. 대시보드 **Keys**에서 제공사 API 키 추가
2. Fallback Chain에서 모델 순서 조정(대체/고정은 SETUP_REPORT에 추후 기록)
3. 통합 키를 사용자 환경변수 `FREELLM_KEY`에만 저장 (`.env` 가능, git 추적 금지)

## 확인 명령
```powershell
netstat -ano | findstr 31415
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:31415/
curl.exe -s -i http://127.0.0.1:31415/v1/models
# 키 있을 때: curl.exe -s -H "Authorization: Bearer %FREELLM_KEY%" http://127.0.0.1:31415/v1/models
```

## 이 PC (DESKTOP-QFEENP2, 2026-10-20)

위 절의 `C:\Users\DMLAB\Desktop\...` 와 포트 31415는 이전 PC portable 기록이다. 그 경로는 이 PC에 없다 (`PATH_EXISTS=False`).

이 PC는 Docker 29.2.1과 Node v24.16.0이 있어 portable zip을 쓰지 않았다. 이미지는 `ghcr.io/tashfeenahmed/freellmapi:v0.16.5`. 바인딩 `127.0.0.1:3001`. `restart: "no"`. GPU 옵션 없음.

작업 디렉터리: `C:\Users\DMLAB_Server1\Contracted_Youth\freellm`

실행:

```powershell
docker compose up -d
```

중지:

```powershell
docker compose stop
```

대시보드: `http://127.0.0.1:3001`  
암호화 키 파일: `freellm\.env` (값은 기록하지 않음).  
이전 본문 사본: `HOWTO.md.bak`
