# 계약서 RAG 리포트 v2

입력은 계약서 텍스트. 참고는 `corpus/records.json`. 생성은 로컬 A.X 4.0 Light (8082).
학습 모델 없음. Qwen 없음. 외부 API 없음. 계약서 원문은 디스크에 쓰지 않는다.

```text
계약서
  → 항 단위 분할 (조 제목 부착, meta는 판정에서 제외)
  → 사실표 (정규식)
  → domain·std_item 필터 후 BM25(문자 bigram) + bge-m3 코사인 RRF, 상위 3, 하한 0.016
  → A.X JSON 판정 (judge.txt, temperature 0, max_tokens 512)
  → 코드 검증 (근거 ID, 인용, 숫자 규칙, 지시문)
  → 리포트 (치명 항목 → 요약 → 카드 → 누락 → 불일치 → 확인할 것 → 다음 행동)
```

A.X 설정(temperature 0, max_tokens 512, ctx 8192)은 v1과 같다.

## 실행

```text
python app_rag\start_ax.py
python app_rag\run_report.py --file app_rag\samples\alba_cafe.txt
python app_rag\run_report.py --file 계약서.txt --no-llm
```

화면:

```text
python app_rag\server.py
```

브라우저 `http://127.0.0.1:8091`. 과정(나누기→사실표→검색→판정→검증→리포트)이 조항마다 보인다.

### 공개 주소(cloudflared)

공개 주소(cloudflared)는 시연·공유할 때만 켜고 끝나면 끈다. 서버가 터널을 자동으로 켜지 않는다.

```text
# 켜기 (별도 터미널). 로컬 8091을 임시 공개 URL로 연결
cloudflared tunnel --url http://127.0.0.1:8091

# 끄기
# 해당 터미널에서 Ctrl+C
```

관리자(user1) 비밀번호는 `app_rag/data_local/ADMIN_PASSWORD.txt`에 저장된다(git 제외). 값은 로그·채팅에 출력하지 않는다.

출력: `app_rag/out/report.json`, `report.md`. 로그 `app_rag/out/analyze.jsonl`에는 조항 수·지연·판정·근거 ID만 남는다.

## 평가

```text
python app_rag\eval\to_jsonl.py
python app_rag\eval\validate.py
python app_rag\eval\assemble.py
python app_rag\eval\run_eval.py
```

정답 계약서는 `datasets/work/v3_1/01_계약서.jsonl`, `datasets/property/v2_fixed/01_계약서.jsonl`, `datasets/money/v3_fixed/01_위반계약서_60건.jsonl` 이다. 옛 `labor_contract_synthetic_pairs_pretty.json` / `work/v2_ours` / `work/v3_merged` / `money/v3` / `property/` 바로 아래 파일은 쓰지 않는다.

## 참고 JSON

스키마는 `corpus/SCHEMA.md`. `std_item` 제안만 `corpus/tag_proposal.csv`. 확인 전에는 레코드의 `std_item`은 비어 있다.
