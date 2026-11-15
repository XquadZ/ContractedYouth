# app_compare 화면 개선본 (static만 교체)

교체 파일: static/index.html, static/app.css, static/app.js
서버 API는 그대로 사용합니다: /api/samples, /api/samples/{id}, /api/analyze(SSE: meta/clause/done), /api/evidence, /api/replay
선택: /api/samples 의 각 항목에 "title"(예: "카페 알바 계약서")을 넣으면 예시 버튼에 그 이름이 보입니다. 없으면 id를 씁니다.

mock_server.py: 모델 없이 화면만 확인하는 가짜 서버 (python mock_server.py 8765 → http://127.0.0.1:8765/)
