# app_rag v2 보고

학습 모델 없음. A.X 4.0 Light (8082) temperature 0, max_tokens 512, ctx 8192. Qwen 없음.

## 실행 명령

```text
python app_rag\run_report_v1.py --file app_rag\samples\alba_cafe.txt --out app_rag\out\baseline_v1.json
python app_rag\run_report.py --convert-corpus
python app_rag\run_report.py --file app_rag\samples\alba_cafe.txt --out app_rag\out\report_v2.json
python app_rag\eval\to_jsonl.py
python app_rag\server.py
```

## 2장 분할 결과

파일: `app_rag/out/split_samples.json`

명령:

```text
python -c "from rag.split import split_contract; ..."
```

| 계약서 | n | clause | special | meta |
|---|---:|---:|---:|---:|
| alba_cafe.txt | 12 | 11 | 0 | 1 |
| demo.txt | 4 | 3 | 0 | 1 |
| oneroom_lease.txt | 11 | 10 | 0 | 1 |

카페 알바는 번호 항이 단위다. 제목·당사자 서문은 meta라 판정에 넣지 않는다. demo는 제1–3조가 항 없이 조 전체 1단위다. 원룸은 제N조(특약 …) 형태라 특약 제목 칸이 아니라 clause로 남는다.

## 검색 하한

`RETRIEVE_FLOOR = 0.016`, `k = 3`, RRF k=60.

카페 알바 v2에서 채택된 RRF는 0.028~0.033 (`report_v2.json` candidates). BM25만 쓸 때 1등 RRF는 `1/(60+1)≈0.01639`이다. 그 아래는 버린다. 이후 바꾸려면 먼저 묻는다.

## 1장 BASELINE vs v2

같은 파일 `app_rag/samples/alba_cafe.txt`.

| 항목 | v1 | v2 |
|---|---|---|
| 명령 경과 | 52840ms | 146368ms (bge-m3 적재 포함) |
| 조항 수 | 12 (제목 포함) | 11 (meta 제외) |
| JSON 파싱 | 12/12 | 11/11 |
| 위험/위반 | risk 5 | 위반 5 |
| 문제 없음 | safe 6 | 2 |
| 확인 필요 | review 1 | 4 |
| 시급 9,860원 | safe | 위반 (숫자 규칙, 2026 최저임금 10,320) |
| 휴게 없음 | risk · 근기법:제54조 | 위반 · law:근로기준법:54 |
| 지각 벌금 | risk · 고른 ID 없음 | 위반 · 위약금 예정 |
| 사회보험 검색 | 주임법:제3조의2 | 근로기준법 쪽 (domain 필터) |
| 조항별 지연 | 미확인 (v1 미기록) | 2.7–4.9초, `out/analyze.jsonl` |
| embed | 없음 | bge-m3 ok |
| quote_mismatch | 없음 (검증 단계 없음) | 5 |
| 버린 근거 ID | 없음 | 0 |
| 계약서 원문 저장 | baseline_v1.json에 있음 | report_v2.json에서 제외 |

v1 원문: `app_rag/out/baseline_v1.json`, `app_rag/out/BASELINE.md`  
v2 원문: `app_rag/out/report_v2.json`, `app_rag/out/report_v2.md`  
로그: `app_rag/out/analyze.jsonl` (조항 수·지연·판정·근거 ID만)

## 9장 평가 수치

`labor_contract_synthetic_pairs_pretty.json`을 eval, `_incoming`, `data_contract`, Downloads, Desktop에서 찾지 못했다.

```text
python app_rag\eval\to_jsonl.py
MISSING labor_contract_synthetic_pairs_pretty.json
```

탐지율·오탐률·확인 필요 비율은 **미확인**. 변환·규격검사·조립·평가 코드는 `app_rag/eval/`에 있다. 조원 파일을 넣으면 위 명령으로 이어서 돌리면 된다.

## tag_proposal.csv 요약

경로: `app_rag/corpus/tag_proposal.csv`. 53건 변환, `std_item`은 레코드에 넣지 않았다.

변환에서 본문 없어 버린 6건 (`out/corpus_skipped.json`): 기간제법 제17조·제6조, 퇴직급여법 제8조·제9조, 고용보험법·산재법 적용 범위. 이유 `empty_text` / `법령 미수집`.

제안은 조문 제목·본문 키워드다. `근로자`가 거의 모든 근로 조문에 붙어 LAB-01이 과다하게 뜬다. 사람이 보기 전에는 쓰지 않는다.

## 화면

`python app_rag\server.py` → `http://127.0.0.1:8091`

프론트는 비교앱과 같은 종이 톤이다. 파이프라인 단계(나누기 → 사실표 → 검색 → A.X 판정 → 검증 → 리포트)와 조항 카드(원문 인용 / 법령 꼬리표 / 차이 / 이유 / 수정 문구 / 넘긴 ID·고른 ID)가 실제 `/api/analyze` SSE에 붙어 있다.
