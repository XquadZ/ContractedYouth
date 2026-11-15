# 프론트엔드 인수인계

백엔드(FastAPI `8091` + A.X `8082`)는 유지하고, UI만 새로 짜도 됩니다.  
**계약서 원문은 서버 디스크에 저장하지 않습니다.** 브라우저 메모리 → API 요청 본문만 사용하세요.

기준 시각: 2026-11-10  
서버: `http://127.0.0.1:8091`

---

## 1. 조원이 보면 되는 파일 (우선순위)

### 필수 — API·백엔드 계약
| 경로 | 역할 |
|---|---|
| `app_rag/server.py` | 전 API 정의 (요청/응답의 소스 오브 트루스) |
| `app_rag/rag/pipeline.py` | SSE 이벤트 (`split`/`facts`/`progress`/`clause`/`done`) |
| `app_rag/rag/report.py` | `done` 이벤트의 `report` 스키마 |
| `app_rag/rag/extract.py` | 업로드 추출·PDF 하이라이트 locate |
| `app_rag/rag/domain.py` | 도메인 점수 (`LAB`/`LEASE`/`LOAN`) |

### 필수 — 현재 동작하는 프론트 참고 구현
| 경로 | 역할 |
|---|---|
| `app_rag/static/review.html` | 검토 워크스페이스 셸 |
| `app_rag/static/review.js` | 업로드·분석 SSE·PDF 하이라이트·탭 UI (**핵심**) |
| `app_rag/static/review-chat.js` | 채팅 UI (로컬 안내, 별도 LLM 채팅 API 없음) |
| `app_rag/static/review-data.js` | 샘플/데모 데이터 |
| `app_rag/static/review.css` | 스타일 |
| `app_rag/static/review-workspace.css` | 워크스페이스 레이아웃 |
| `app_rag/static/index.html` | 랜딩 |
| `app_rag/static/rag-bridge.js` | 랜딩용 A.X 상태 배지 |

### 있으면 좋은 것
| 경로 | 역할 |
|---|---|
| `app_rag/static/mobile.html` / `mobile-app.html` | 모바일 시안 |
| `app_rag/static/feature-tour.js` / `.css` | 랜딩 기능 투어 |
| `app_rag/static/app.js` / `app.css` | 구버전 UI (참고만) |
| `app_rag/samples/*.txt` | `/api/samples`용 예시 계약서 |
| `app_rag/out/mvp_upload/MVP_UPLOAD_REPORT.md` | 업로드 MVP 완료 기준·스크린샷 |
| `app_rag/docs/MVP_PLAN.md` | 제품 단계 계획 |
| `app_rag/CLAUDE.md` | 원문 비저장·외부 API 금지 등 규칙 |

### 건드리지 말 것 (백엔드/평가)
- `rag/` 검색·판정·검증 로직 (API 계약만 소비)
- `eval/`, `datasets/`, `criteria/`, `corpus/` (프론트 불필요)
- `static/*_v1.*`, `*_v2.*`, `_figma_src/`, `_backup_*` (백업·시안 원본)

---

## 2. 로컬 실행

```text
# 터미널 1 — A.X (이미 떠 있으면 생략)
python app_rag/start_ax.py

# 터미널 2 — 웹
python app_rag/server.py
```

브라우저: `http://127.0.0.1:8091`  
검토 화면: `http://127.0.0.1:8091/static/review.html` (랜딩에서 진입)

헬스: `GET /api/health` → `ax: true` 여야 실제 판정 가능.

---

## 3. API 계약 (프론트가 호출하는 것만)

Base: `http://127.0.0.1:8091`  
CORS는 같은 origin 가정. 별도 프론트 포트면 프록시 권장.

### `GET /api/health`
```json
{
  "ax": true,
  "n_records": 104,
  "embed_ok": true,
  "model": "A.X-4.0-Light",
  "port": 8082,
  "sec_per_clause": 2.64
}
```
조항당 예상 초 ≈ `sec_per_clause` (진행률 ETA에 사용).

### `GET /api/samples` → `{ "samples": [{ "id", "title" }] }`
### `GET /api/samples/{id}` → `{ "text": "..." }`

### `POST /api/extract` (multipart)
- form field: `file` (PDF/HWP/HWPX/TXT, ≤10MB)
- 성공 예:
```json
{
  "kind": "pdf",
  "n_pages": 3,
  "pages": [{ "page": 1, "text": "..." }],
  "scan_likely": false,
  "domain_guess": { "domain": "LEASE", "scores": {}, "choices": [] }
}
```
- 실패: `400` `{ "error": "..." }`
- **서버는 파일을 저장하지 않음.** 응답의 `pages[].text`만 메모리에 두고 이후 `/api/analyze`에 합쳐 보냄.

### `POST /api/domain` JSON `{ "text": "..." }`
→ `score_domain` 결과 (`domain`, `scores`, `choices` …)

### `POST /api/analyze` JSON + **SSE**
```json
{ "text": "전체 계약서 텍스트", "no_llm": false, "domain": "LAB" }
```
- `domain`: `"LAB"` | `"LEASE"` | `"LOAN"` | `null`(자동)
- `Content-Type: application/json`
- 응답: `text/event-stream`

| event | data 요지 |
|---|---|
| `meta` | `{ model, no_llm, domain }` |
| `split` | `{ n, segments: [{ segment_id, order, segment_type, article_title, text }] }` |
| `facts` | `{ facts, domain }` |
| `progress` | `{ phase: "judge", n_clauses, done }` |
| `clause` | `{ finding, done, n_clauses }` — finding에 verdict/why/evidence 등 |
| `done` | `{ report: { ... } }` **최종 화면 데이터** |
| `error` | `{ message }` |

SSE 파싱 참고: `static/review.js` (`fetch` + `ReadableStream`, `event:` / `data:` 줄).

### `POST /api/locate` (PDF 하이라이트)
- multipart: `file` + form `quotes` = JSON 문자열 배열
- → 페이지/% 좌표. PDF일 때만.

### `POST /api/pdf_pages`
- multipart: `file`, `max_pages`(기본 8)
- → JPEG data URL 목록 (뷰어용). 디스크 저장 없음.

### `POST /api/split` (선택)
- JSON `{ text }` → 조항 분할만 (분석 없이 미리보기할 때)

---

## 4. `report` 객체 (분석 결과 UI에 필요한 핵심)

`done` → `report` (발췌):

```text
title, model, domain
summary: { n_segments, n_violation, n_risk, n_review, n_ok, n_clause_check, n_doc_question }
critical: [{ label, segment_id, quote, verdict }]
cards: [{ segment_id, article_title, verdict, contract_quote, clause_text, evidence, gap, why, suggestion, ... }]
missing, mismatches
needs_fact / clause_checks / doc_questions / 직접_확인할_것
next_actions: { requests, helpline }
disclaimer, facts, stats, findings, segments
```

**판정 4값:** `위반` | `위험` | `확인 필요` | `문제 없음`  
문서 상단 3단계 문구(백엔드 평가용 정의, UI에 써도 됨):
- 위반·위험 ≥1 → 「고칠 조항 있음」
- 확인 필요 ≥3 → 「확인할 부분 있음」
- 그 외 → 「큰 문제 없음」

확인 질문은 두 갈래:
- **조항 확인 필요** (`clause_checks`)
- **문서 질문** (`doc_questions`) — 조항 판정은 안 바꿈

---

## 5. 화면 흐름 (현행 review.js)

1. 샘플 선택 **또는** 파일 업로드 **또는** 텍스트 붙여넣기  
2. 업로드면 `/api/extract` → 도메인 확인/선택 → 텍스트 합치기  
3. `/api/analyze` SSE → 진행률 표시  
4. `done.report`로 요약 / 필수 / 위험 / 질문 탭 렌더  
5. PDF면 `/api/locate` + `/api/pdf_pages`로 하이라이트  
6. 「리포트 저장」은 **클라이언트에서 txt 다운로드** (서버에 원문 저장 금지)

채팅(`review-chat.js`)은 **별도 질의 API 없음.** 이미 받은 report/카드 내용을 안내하는 로컬 UI입니다. 새 LLM 채팅을 붙이려면 백엔드 합의가 필요합니다.

---

## 6. 프론트 절대 규칙

1. 사용자 계약서 원문을 **서버 디스크·로그·git에 올리지 않기**  
2. 외부 AI API로 계약서 문장 보내지 않기 (판정은 로컬 A.X만)  
3. API 키·토큰 화면에 출력 금지  
4. 예시 화면과 “내 파일” 모드 구분 (배지). 예시는 샘플 API 또는 `review-data.js`  
5. 스캔 PDF(`scan_likely`)면 사용자에게 안내 토스트

---

## 7. 새 스택으로 갈아탈 때

- Vite/React 등이면 **개발 서버 → 8091 프록시** (`/api`, `/static` 샘플 PDF 등)
- 이 문서의 API만 맞으면 `static/` 전면 교체 가능
- 백엔드 스키마 변경이 필요하면 `server.py` 담당과 먼저 맞출 것

---

## 8. 빠른 스모크

```text
curl http://127.0.0.1:8091/api/health
curl http://127.0.0.1:8091/api/samples
```

브라우저: 랜딩 → 검토 → 샘플 `oneroom_lease` 또는 `alba_cafe` 분석 → 위험 탭·하이라이트 확인.

문의 시 첨부: Network 탭의 `/api/analyze` SSE 일부, `/api/health` JSON.
