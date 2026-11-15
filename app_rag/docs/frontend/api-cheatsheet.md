# API 치트시트

```bash
BASE=http://127.0.0.1:8091
```

## Health / Samples
```bash
curl -s $BASE/api/health
curl -s $BASE/api/samples
curl -s $BASE/api/samples/alba_cafe
```

## Domain
```bash
curl -s -X POST $BASE/api/domain \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"근로계약서 시급 월급 휴게\"}"
```

## Extract (파일)
```bash
curl -s -X POST $BASE/api/extract -F "file=@./contract.pdf"
```

## Analyze (SSE) — 핵심
```bash
curl -N -X POST $BASE/api/analyze \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"제1조 ...\",\"no_llm\":false,\"domain\":\"LAB\"}"
```

이벤트 예:
```text
event: meta
data: {"model":"A.X-4.0-Light","no_llm":false,"domain":"LAB"}

event: progress
data: {"phase":"judge","n_clauses":10,"done":3}

event: done
data: {"report":{ ... }}
```

브라우저에서는 `EventSource`가 POST를 못 하므로 **fetch + ReadableStream** 사용 (`review.js` 참고).

## PDF locate / pages
```bash
curl -s -X POST $BASE/api/locate \
  -F "file=@./contract.pdf" \
  -F 'quotes=["보증금","월세"]'

curl -s -X POST $BASE/api/pdf_pages \
  -F "file=@./contract.pdf" \
  -F "max_pages=4"
```

## finding / card verdict 값
`위반` | `위험` | `확인 필요` | `문제 없음`
