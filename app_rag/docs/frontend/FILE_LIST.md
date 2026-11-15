# 프론트 조원에게 넘길 파일 체크리스트

저장소 루트: `Contracted_Youth` (또는 `app_rag`만 클론해도 되게 정리할 때는 아래 경로 유지)

## A. 문서 (먼저 읽기)
- [ ] `app_rag/docs/frontend/FRONTEND_HANDOFF.md`
- [ ] `app_rag/docs/frontend/api-cheatsheet.md`
- [ ] `app_rag/CLAUDE.md` (원문 비저장 규칙)
- [ ] `app_rag/docs/MVP_PLAN.md` (제품 범위)

## B. 백엔드 계약 (읽기 전용)
- [ ] `app_rag/server.py`
- [ ] `app_rag/rag/pipeline.py`
- [ ] `app_rag/rag/report.py`
- [ ] `app_rag/rag/extract.py`
- [ ] `app_rag/rag/domain.py`

## C. 현재 UI 참고 구현
- [ ] `app_rag/static/index.html`
- [ ] `app_rag/static/review.html`
- [ ] `app_rag/static/review.js`
- [ ] `app_rag/static/review-chat.js`
- [ ] `app_rag/static/review-data.js`
- [ ] `app_rag/static/review.css`
- [ ] `app_rag/static/review-workspace.css`
- [ ] `app_rag/static/rag-bridge.js`
- [ ] `app_rag/static/feature-tour.js` / `feature-tour.css` (선택)
- [ ] `app_rag/static/mobile.html` / `mobile-app.html` (선택)
- [ ] `app_rag/static/icons/` (있으면 아이콘)

## D. 샘플 텍스트
- [ ] `app_rag/samples/alba_cafe.txt`
- [ ] `app_rag/samples/clean_alba.txt`
- [ ] `app_rag/samples/demo.txt`
- [ ] `app_rag/samples/oneroom_lease.txt`

## E. 제외 (보내지 말 것 / 용량·비밀)
- `data_local/models/*.gguf` (수 GB, 프론트 불필요)
- `datasets/` 원문 대량 jsonl
- `app_rag/out/` 평가 결과 (개인/실험 로그 가능)
- `.env`, 토큰, `LAW_OC` 등 키
- `static/_backup_*`, `static/_figma_src` (원하면 시안만 별도)

## 실행만 백엔드 담당이 해 주는 경우
프론트는 `8091`만 보면 됨. A.X `8082`는 백엔드가 유지.
