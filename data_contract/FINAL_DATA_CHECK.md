# FINAL_DATA_CHECK — 2026-10-15 10:43

ROOT = `C:\Users\DMLAB\Desktop\학부-AI서비스 개발`

## 1. F1–F12 상태표

| ID | 항목 | 상태 | 실제 수치 | 기대와의 차이 |
|---|---|---|---|---|
| F1 | 표준계약서 | **정상** | manifest=27 missing=0 hash_mismatch=0 extracted=[{'file': 'L1.txt', 'exists': True, 'chars': 2642}, {'file': 'L2.txt', 'exists': True, 'chars': 944}, {'file': 'L3.txt', 'exists': True, 'chars': 930}, {'file': 'L4.txt', 'exists': True, 'chars': 2125}, {'file': 'L5.txt', 'exists': True, 'chars': 759}, {'file': 'L6.txt', 'exists': True, 'chars': 750}] | — |
| F2 | AI Hub 계약 서식 | **정상** | labels=1182 소분류={'주거용부동산임대계약서': 70, '근로(고용)계약서': 167, '아르바이트계약서': 31} vocab=True | {'근로(고용)계약서': 0, '아르바이트계약서': 0, '주거용부동산임대계약서': 0} |
| F3 | AI Hub 약관(580) | **없음** | 약관 원천/라벨 없음 (WAITING/NOT_FOUND 플레이스홀더만) | 기대: dataSetSn=580 약관 원천/라벨 |
| F4 | 법령 현행 10개 | **정상** | parse_ok=10/10 | — |
| F5 | 연혁 | **정상** | path=C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\law_api\연혁_g3 판수={'근로기준법': 1, '근로기준법 시행령': 1, '주택임대차보호법': 1, '주택임대차보호법 시행령': 1, '민법': 1, '보증인 보호를 위한 특별법': 1} 혼입=0 | 혼입 0 기대 |
| F6 | 최저임금 2022–2026 | **정상** | {'2022': '9,160', '2023': '9,620', '2024': '9,860', '2025': '10,030', '2026': '10,320'} | match 5/5 |
| F7 | 판례 | **정상** | unique=7414 bodies=7414 filter=216 | filter 기대 216, 차이 0 |
| F8 | 해석례 | **일부** | expc_bodies=515 ministry_bodies=1729 mismatch_kw=0 | expc 기대 515, 차이 0 |
| F9 | 공정위 | **정상** | lists≈5 bodies_unique=158 | — |
| F10 | 사례집 | **일부** | pdf_bytes=35722003 pages=101 ocr_txt=101 hangul=0.25776665083108763 | OCR 한글비율≥0.7 기대 → 미달 |
| F11 | 모델 | **정상** | hf_match=True incomplete=6 gguf=[{'path': 'C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\EXAONE-4.0-32B-GGUF\\EXAONE-4.0-32B-Q6_K.gguf', 'bytes': 26259021600}, {'path': 'C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\Qwen3-32B-GGUF\\Qwen3-32B-Q6_K.gguf', 'bytes': 26883306112}, {'path': 'C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\EXAONE-4.0-32B-GGUF\\EXAONE-4.0-32B-Q6_K.gguf', 'bytes': 26259021600}, {'path': 'C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\Qwen3-32B-GGUF\\Qwen3-32B-Q6_K.gguf', 'bytes': 26883306112}] | GGUF/해시 항목 확인 |
| F12 | 수동 다운로드 | **일부** | n=5 titles=['Open API target=lsHistory 승인 확인', 'AI Hub 판결서·약관 데이터 (dataSetSn=580)', 'Open API target=lstrm 승인 확인', 'Open API target=mojCgmExpc 승인 확인', 'Open API target=cgmExpc 승인 확인'] | 수동 0 기대 |

## 2. 폴더 정리 요약

### 0) WRONG(AI_Service) 탐색
- `C:\Users\DMLAB\AI_Service` — files=0, bytes=0, mtime=None, children=[]

### 1) 분류 요약 (FOLDER_DIFF.csv)
- diff 행 수: 0
- 분류별 파일 수: {}
- 분류별 총 바이트: {}
- (c) WRONG에만 있음: **0건**

### 2) 복사 (FOLDER_MERGE_LOG.csv)
- 복사 성공 수: 0 / 바이트: 0
- 충돌(b) 수: 0

### 3) 경로 참조
- `AI_Service` 문자열 발견 파일 수: 4
  - `data_contract\final_data_check.json` (11줄)
  - `data_contract\FINAL_DATA_CHECK.md` (4줄)
  - `data_contract\scripts\final_data_check.py` (14줄)
  - `data_contract\scripts\final_data_check_old_202610151040.py` (14줄)
- 자동 수정한 스크립트/설정: 0

## 3. WRONG 보존·이전 여부

WRONG 폴더는 삭제하지 않았음. 내용이 ROOT로 모두 옮겨졌는지: **예** (근거: `C:\Users\DMLAB\AI_Service` 파일 수 0·바이트 0 — 옮길 (c) 항목 없음)

## 4. 사람이 할 일

- 수동 다운로드 잔여 **5**:
  - Open API target=lsHistory 승인 확인
  - AI Hub 판결서·약관 데이터 (dataSetSn=580)
  - Open API target=lstrm 승인 확인
  - Open API target=mojCgmExpc 승인 확인
  - Open API target=cgmExpc 승인 확인
- 충돌(b) 없음
- AI Hub 약관(580) 다운로드 후 `after_manual.py` 실행
- 사례집 OCR 품질 재작업(한글비율 미달) 검토

## 부록: 상세

### F1
```json
{
  "id": "F1",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\standard_forms",
  "status": "정상",
  "detail": {
    "manifest_rows": 27,
    "missing_files": 0,
    "hash_mismatch": 0,
    "extracted": [
      {
        "file": "L1.txt",
        "exists": true,
        "chars": 2642
      },
      {
        "file": "L2.txt",
        "exists": true,
        "chars": 944
      },
      {
        "file": "L3.txt",
        "exists": true,
        "chars": 930
      },
      {
        "file": "L4.txt",
        "exists": true,
        "chars": 2125
      },
      {
        "file": "L5.txt",
        "exists": true,
        "chars": 759
      },
      {
        "file": "L6.txt",
        "exists": true,
        "chars": 750
      }
    ]
  }
}
```

### F2
```json
{
  "id": "F2",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\aihub_forms",
  "status": "정상",
  "detail": {
    "label_json_n": 1182,
    "소분류": {
      "주거용부동산임대계약서": 70,
      "근로(고용)계약서": 167,
      "아르바이트계약서": 31
    },
    "label_vocab": true,
    "label_vocab_rows": 130,
    "expect_diff": {
      "근로(고용)계약서": 0,
      "아르바이트계약서": 0,
      "주거용부동산임대계약서": 0
    }
  }
}
```

### F3
```json
{
  "id": "F3",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\aihub_terms",
  "status": "없음",
  "detail": {
    "files": 2,
    "placeholders": [
      "NOT_FOUND.txt",
      "WAITING.txt"
    ],
    "data_files": [],
    "note": "약관 원천/라벨 없음 (WAITING/NOT_FOUND 플레이스홀더만)"
  }
}
```

### F4
```json
{
  "id": "F4",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api",
  "status": "정상",
  "detail": {
    "laws": [
      {
        "name": "근로기준법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\근로기준법_285279.json",
        "parse_ok": true,
        "MST": "285279",
        "시행일": "20261008",
        "법령명_in_json": "근로기준법",
        "조문단위_수": 146,
        "조문_수": 116
      },
      {
        "name": "근로기준법 시행령",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\근로기준법 시행령_270551.json",
        "parse_ok": true,
        "MST": "270551",
        "시행일": "20251023",
        "법령명_in_json": "근로기준법 시행령",
        "조문단위_수": 80,
        "조문_수": 60
      },
      {
        "name": "최저임금법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_v2_exact\\bodies\\최저임금법_218303.json",
        "parse_ok": true,
        "MST": "218303",
        "시행일": "20200526",
        "법령명_in_json": "최저임금법",
        "조문단위_수": 40,
        "조문_수": 31
      },
      {
        "name": "최저임금법 시행령",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_v2_exact\\bodies\\최저임금법 시행령_206564.json",
        "parse_ok": true,
        "MST": "206564",
        "시행일": "20190101",
        "법령명_in_json": "최저임금법 시행령",
        "조문단위_수": 27,
        "조문_수": 22
      },
      {
        "name": "주택임대차보호법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\주택임대차보호법_276291.json",
        "parse_ok": true,
        "MST": "276291",
        "시행일": "20260102",
        "법령명_in_json": "주택임대차보호법",
        "조문단위_수": 42,
        "조문_수": 31
      },
      {
        "name": "주택임대차보호법 시행령",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\주택임대차보호법 시행령_287183.json",
        "parse_ok": true,
        "MST": "287183",
        "시행일": "20260701",
        "법령명_in_json": "주택임대차보호법 시행령",
        "조문단위_수": 36,
        "조문_수": 35
      },
      {
        "name": "민법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\민법_284415.json",
        "parse_ok": true,
        "MST": "284415",
        "시행일": "20260317",
        "법령명_in_json": "민법",
        "조문단위_수": 1337,
        "조문_수": 1118
      },
      {
        "name": "이자제한법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_v2_exact\\bodies\\이자제한법_268667.json",
        "parse_ok": true,
        "MST": "268667",
        "시행일": "20250722",
        "법령명_in_json": "이자제한법",
        "조문단위_수": 8,
        "조문_수": 8
      },
      {
        "name": "이자제한법 제2조제1항의 최고이자율에 관한 규정",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_v2_exact\\bodies\\이자제한법 제2조제1항의 최고이자율에 관한 규정_230727.json",
        "parse_ok": true,
        "MST": "230727",
        "시행일": "20210707",
        "법령명_in_json": "이자제한법 제2조제1항의 최고이자율에 관한 규정",
        "조문단위_수": 1
      },
      {
        "name": "보증인 보호를 위한 특별법",
        "file": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3\\bodies\\보증인 보호를 위한 특별법_251943.json",
        "parse_ok": true,
        "MST": "251943",
        "시행일": "20231221",
        "법령명_in_json": "보증인 보호를 위한 특별법",
        "조문단위_수": 11,
        "조문_수": 11
      }
    ],
    "parse_ok_n": 10
  }
}
```

### F5
```json
{
  "id": "F5",
  "status": "정상",
  "detail": {
    "법령별_판수": {
      "근로기준법 시행령": 1,
      "근로기준법 시행령_270551_old": 1,
      "근로기준법": 1,
      "근로기준법_285279_old": 1,
      "민법": 1,
      "민법_284415_old": 1,
      "보증인 보호를 위한 특별법": 1,
      "보증인 보호를 위한 특별법_251943_old": 1,
      "주택임대차보호법 시행령": 1,
      "주택임대차보호법 시행령_287183_old": 1,
      "주택임대차보호법": 1,
      "주택임대차보호법_276291_old": 1
    },
    "혼입_건수": 0,
    "혼입_샘플": [],
    "g3_대상_판수": {
      "근로기준법": 1,
      "근로기준법 시행령": 1,
      "주택임대차보호법": 1,
      "주택임대차보호법 시행령": 1,
      "민법": 1,
      "보증인 보호를 위한 특별법": 1
    },
    "연혁_g3_혼입": 0
  },
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\연혁_g3"
}
```

### F6
```json
{
  "id": "F6",
  "status": "정상",
  "detail": {
    "years": {
      "2022": {
        "expected": "9,160",
        "found": "9,160",
        "evidence": {
          "file": "law_api\\행정규칙\\최저임금_v2\\body_2022_2100000203520.json",
          "snip": "        \" ○ 2022년 적용 최저임금은 시간급 9,160원이며, 사업의 종류별 구분 없이 모"
        },
        "body_files": [
          "body_2022_2100000203520.json"
        ]
      },
      "2023": {
        "expected": "9,620",
        "found": "9,620",
        "evidence": {
          "file": "law_api\\행정규칙\\최저임금_v2\\body_2023_2100000213591.json",
          "snip": "        \" ○ 2023년 적용 최저임금은 시간급 9,620원이며, 사업의 종류별 구분 없이 모"
        },
        "body_files": [
          "body_2023_2100000213591.json"
        ]
      },
      "2024": {
        "expected": "9,860",
        "found": "9,860",
        "evidence": {
          "file": "law_api\\행정규칙\\최저임금_v2\\pdfs\\2024_2024년 적용 최저임금 고시(고용노동부 고시 제2023-43호).pdf.txt",
          "snip": "모 든 산 업 9,860 원"
        },
        "body_files": [
          "body_2024_2100000227560.json"
        ]
      },
      "2025": {
        "expected": "10,030",
        "found": "10,030",
        "evidence": {
          "file": "law_api\\행정규칙\\최저임금_v2\\pdfs\\2025_2025년 적용 최저임금 고시(고용노동부 고시 제2024-50호).pdf.txt",
          "snip": "모 든 산 업 10,030 원"
        },
        "body_files": [
          "body_2025_2100000245668.json"
        ]
      },
      "2026": {
        "expected": "10,320",
        "found": "10,320",
        "evidence": {
          "file": "law_api\\행정규칙\\최저임금_v2\\pdfs\\2026_2026년 적용 최저임금 고시(고용노동부 고시 제2025-47호).pdf.txt",
          "snip": "모 든 산 업 10,320 원"
        },
        "body_files": [
          "body_2026_2100000262710.json"
        ]
      }
    },
    "match_n": 5
  },
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\행정규칙\\최저임금_v2"
}
```

### F7
```json
{
  "id": "F7",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\판례",
  "status": "정상",
  "detail": {
    "목록_고유수": 7414,
    "본문_파일수": 7414,
    "필터통과_본문수": 216,
    "기대_필터통과": 216,
    "차이": 0
  }
}
```

### F8
```json
{
  "id": "F8",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\법령해석례",
  "status": "일부",
  "detail": {
    "expc_bodies": 515,
    "기대_expc": 515,
    "ministry_g2_bodies": 1729,
    "g2_keyword_rows": {
      "고용노동부|근로계약": {
        "totalCnt": 1261,
        "saved_list": 1261,
        "saved_body": 1261,
        "match": true
      },
      "고용노동부|최저임금": {
        "totalCnt": 38,
        "saved_list": 38,
        "saved_body": 38,
        "match": true
      },
      "고용노동부|주휴": {
        "totalCnt": 183,
        "saved_list": 183,
        "saved_body": 183,
        "match": true
      },
      "고용노동부|수습": {
        "totalCnt": 39,
        "saved_list": 39,
        "saved_body": 39,
        "match": true
      },
      "고용노동부|임대차": {
        "totalCnt": 29,
        "saved_list": 29,
        "saved_body": 29,
        "match": true
      },
      "고용노동부|보증금": {
        "totalCnt": 13,
        "saved_list": 13,
        "saved_body": 13,
        "match": true
      },
      "고용노동부|이자": {
        "totalCnt": 72,
        "saved_list": 72,
        "saved_body": 72,
        "match": true
      },
      "국토교통부|근로계약": {
        "totalCnt": 3,
        "saved_list": 3,
        "saved_body": 3,
        "match": true
      },
      "국토교통부|최저임금": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "국토교통부|주휴": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "국토교통부|수습": {
        "totalCnt": 3,
        "saved_list": 3,
        "saved_body": 3,
        "match": true
      },
      "국토교통부|임대차": {
        "totalCnt": 123,
        "saved_list": 123,
        "saved_body": 123,
        "match": true
      },
      "국토교통부|보증금": {
        "totalCnt": 41,
        "saved_list": 41,
        "saved_body": 41,
        "match": true
      },
      "국토교통부|이자": {
        "totalCnt": 33,
        "saved_list": 33,
        "saved_body": 33,
        "match": true
      },
      "법제처|근로계약": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법제처|최저임금": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법제처|주휴": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법제처|수습": {
        "totalCnt": 1,
        "saved_list": 1,
        "saved_body": 1,
        "match": true
      },
      "법제처|임대차": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법제처|보증금": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법제처|이자": {
        "totalCnt": 0,
        "saved_list": 0,
        "saved_body": 0,
        "match": true
      },
      "법무부|근로계약": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|최저임금": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|주휴": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|수습": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|임대차": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|보증금": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      },
      "법무부|이자": {
        "totalCnt": null,
        "saved_list": 0,
        "saved_body": 0,
        "match": false
      }
    },
    "totalCnt_불일치_키워드": [],
    "미승인_또는_실패_키워드": [
      "법무부|근로계약",
      "법무부|최저임금",
      "법무부|주휴",
      "법무부|수습",
      "법무부|임대차",
      "법무부|보증금",
      "법무부|이자"
    ],
    "note": "expc·승인된 부처는 totalCnt 일치. 미승인 target
```

### F9
```json
{
  "id": "F9",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\law_api\\공정위",
  "status": "정상",
  "detail": {
    "목록_파일수": 5,
    "본문_고유수": 158,
    "본문_파일수": 223,
    "g2_rows": [
      {
        "target": "ftc",
        "keyword": "임대차 약관",
        "totalCnt": 24,
        "saved_list": 24,
        "saved_body": 24
      },
      {
        "target": "ftc",
        "keyword": "임대차계약서",
        "totalCnt": 153,
        "saved_list": 153,
        "saved_body": 153
      }
    ]
  }
}
```

### F10
```json
{
  "id": "F10",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\cases",
  "status": "일부",
  "detail": {
    "pdf_bytes": 35722003,
    "pages": 101,
    "ocr_page_txt": 101,
    "ocr_all": true,
    "avg_hangul_ratio": 0.25776665083108763,
    "quality_ok": false
  }
}
```

### F11
```json
{
  "id": "F11",
  "status": "정상",
  "detail": {
    "hf_hash_compare": [
      {
        "repo": "Qwen/Qwen3-8B",
        "file": "model-00001-of-00005.safetensors",
        "match": true
      },
      {
        "repo": "Qwen/Qwen3-8B",
        "file": "model-00002-of-00005.safetensors",
        "match": true
      },
      {
        "repo": "Qwen/Qwen3-8B",
        "file": "model-00003-of-00005.safetensors",
        "match": true
      },
      {
        "repo": "Qwen/Qwen3-8B",
        "file": "model-00004-of-00005.safetensors",
        "match": true
      },
      {
        "repo": "Qwen/Qwen3-8B",
        "file": "model-00005-of-00005.safetensors",
        "match": true
      },
      {
        "repo": "nlpai-lab/KURE-v1",
        "file": "model.safetensors",
        "match": true
      },
      {
        "repo": "BAAI/bge-m3",
        "file": "pytorch_model.bin",
        "match": true
      }
    ],
    "all_match": true,
    "Qwen3-8B": {
      "exists": true,
      "bytes": 16397466102,
      "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B"
    },
    "KURE-v1": {
      "exists": true,
      "bytes": 2288778632,
      "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\KURE-v1"
    },
    "bge-m3": {
      "exists": true,
      "bytes": 4587326037,
      "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\bge-m3"
    },
    "gguf_qwen3_32b": [
      {
        "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\EXAONE-4.0-32B-GGUF\\EXAONE-4.0-32B-Q6_K.gguf",
        "bytes": 26259021600
      },
      {
        "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\Qwen3-32B-GGUF\\Qwen3-32B-Q6_K.gguf",
        "bytes": 26883306112
      },
      {
        "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\EXAONE-4.0-32B-GGUF\\EXAONE-4.0-32B-Q6_K.gguf",
        "bytes": 26259021600
      },
      {
        "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\models\\Qwen3-32B-GGUF\\Qwen3-32B-Q6_K.gguf",
        "bytes": 26883306112
      }
    ],
    "incomplete_n": 6,
    "incomplete_paths": [
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\ewHVStNi_qTCwOvZyUK4XvcG7h0=.5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282.2359eee0.incomplete",
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\fNjCg19rjPb4Qv_8lvghvyvUVYM=.b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a.8a59a8f1.incomplete",
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\fNjCg19rjPb4Qv_8lvghvyvUVYM=.b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a.c8066dd7.incomplete",
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\ucOYR0sM0bukMpWiwV3qkLpQbMA=.31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f.9647bb55.incomplete",
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\ucOYR0sM0bukMpWiwV3qkLpQbMA=.31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f.e2cd7e84.incomplete",
      "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\models\\Qwen3-8B\\.cache\\huggingface\\download\\W6LiZUqSlTR2RfaiI-PdlBA4Fcg=.c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836.14d6a41d.incomplete"
    ]
  }
}
```

### F12
```json
{
  "id": "F12",
  "path": "C:\\Users\\DMLAB\\Desktop\\학부-AI서비스 개발\\data_contract\\MANUAL_DOWNLOADS.html",
  "status": "일부",
  "detail": {
    "n": 5,
    "titles": [
      "Open API target=lsHistory 승인 확인",
      "AI Hub 판결서·약관 데이터 (dataSetSn=580)",
      "Open API target=lstrm 승인 확인",
      "Open API target=mojCgmExpc 승인 확인",
      "Open API target=cgmExpc 승인 확인"
    ]
  }
}
```
