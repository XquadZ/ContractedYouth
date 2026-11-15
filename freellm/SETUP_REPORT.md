# FreeLLMAPI SETUP_REPORT (준비 단계 — 키 등록 대기)

조회·설치 시각: 2026-10-19

## 1. 설치 방식·버전·실행/중지
| 항목 | 내용 |
|---|---|
| Docker | 미설치 → (a) 불가 |
| Node | PATH에 없음 → (c) 보류 |
| 채택 | **(b) portable** `FreeLLMAPI-0.16.5-win.zip` |
| 버전 | **v0.16.5** |
| 경로 | `freellm\app\FreeLLMAPI.exe` |
| ENCRYPTION_KEY | 생성됨. 저장: `%APPDATA%\FreeLLMAPI\.encryption-key` (값 미기록, 64 bytes) |
| listen | **`127.0.0.1:31415`** (Desktop 기본; README Docker 기본 3001과 다름) |
| 시작/중지 | `freellm\HOWTO.md` |

### 대시보드·API 프로브 원문 (키 없음)
- `GET http://127.0.0.1:31415/` → **HTTP 200**, size=1572
- `GET http://127.0.0.1:31415/v1/models` (Authorization 없음) → **HTTP 401**
  - body: `{"error":{"message":"Invalid API key","type":"authentication_error"}}`
- `netstat`: `TCP 127.0.0.1:31415 ... LISTENING` (전문: `probe_no_key.txt`)
- `.env` gitignore: 루트 `.gitignore`에 `.env` / `.env.*` 있음 + `freellm\.gitignore`

## 2. 제공사 표
→ `freellm\PROVIDERS.md` (약관 확인 칸은 사용자 작성)

**상태: 사용자 키 등록 대기.** 「등록했어」 후 아래 3~6 채움.

## 3. models.csv / 교사 후보
_(미실행 — 키 등록 후)_

## 4. 연결 시험 표
_(미실행 — 키 등록 후)_

## 5. 대체 끄기
_(키 등록·문서 확인 후 기록)_

## 6. 미확인
- Desktop이 config `port:3001`을 덮어쓰고 31415 유지하는 이유(앱 기본값)
- 제공사별 약관 두 항목(학습 사용 / 출력 학습 제한) — 사용자 확인
- Cloudflare·HF·NVIDIA 무료 한도 숫자(계정·문서 변동)
