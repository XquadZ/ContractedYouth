# DATA_READY_REPORT — 계약서 분석 데이터·모델 준비

- C: 여유 2570.55 GB
- s5 disk_before/after: {'C': 2583.75} / {'C': 2570.55}

## 상태 요약표

| 항목 | 상태 | 경로 | 건수·크기 | 근거 |
|---|---|---|---|---|
| AIHub 계약 서식(05 zip) | 있음 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_forms` | 라벨 1182 / 고용577 임대389 금전216 | §1 |
| AIHub 풀패키지(~160GB) | 있음(모델·도커) | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터` | path=C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터 files=35 GB=161.46 | §1 |
| AIHub 판결서·약관 | 대기(G7 수동)| `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_terms` | ROOT/Downloads/Desktop 등에서 판결서·약관 관련 zip 미발견(또는 아직 생성 전). 다운로드 완료 후 재실행. | §2 |
| 법령 Open API | calls_completed | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\law_api` | oc_configured=True | §3 |
| 임대차분쟁조정사례집 PDF | OCR_low_quality| `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\cases\주택임대차분쟁조정사례집.pdf` | pages=101 cases=미확인(텍스트 레이어 없음, OCR 필요) bytes=35722003 | §4 |
| Qwen/Qwen3-8B | 있음 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B` | 15.271 GB | §5 |
| nlpai-lab/KURE-v1 | 있음 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\KURE-v1` | 2.132 GB | §5 |
| BAAI/bge-m3 | 있음 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\bge-m3` | 4.272 GB | §5 |
| 교사 후보 *35B* 조사 | 있음(조사만) | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\s5_teacher_survey.json` | n=19 | §5 |

---

## §1. AIHub 계약 서식

- zip 12개 해제 → `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_forms`
- taxonomy: `[{'대분류': '인사_고용_노무', '중분류': '고용계약', '소분류': '기타고용계약서', 'bucket': '고용', 'count': 379}, {'대분류': '부동산매매_임대차', '중분류': '부동산임대', '소분류': '상업용부동산임대계약서', 'bucket': '부동산임대', 'count': 319}, {'대분류': '인사_고용_노무', '중분류': '고용계약', '소분류': '근로(고용)계약서', 'bucket': '고용', 'count': 167}, {'대분류': '금전소비대차_채권_채무', '중분류': '채권_채무계약', '소분류': '채권양도계약서', 'bucket': '금전대차', 'count': 121}, {'대분류': '금전소비대차_채권_채무', '중분류': '채권_채무계약', '소분류': '채무승계계약서', 'bucket': '금전대차', 'count': 95}, {'대분류': '부동산매매_임대차', '중분류': '부동산임대', '소분류': '주거용부동산임대계약서', 'bucket': '부동산임대', 'count': 70}, {'대분류': '인사_고용_노무', '중분류': '고용계약', '소분류': '아르바이트계약서', 'bucket': '고용', 'count': 31}]`
- 기타고용 비근로성 추정: 233 / 357
- label_vocab: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_forms\label_vocab.csv`
- 조항 텍스트 존재, 다수 플레이스홀더(`○○`,`(@회사명)`). 상세 샘플: `s1_samples.md`

---

## §2. 판결서·약관

- status: **대기 중**
- note: ROOT/Downloads/Desktop 등에서 판결서·약관 관련 zip 미발견(또는 아직 생성 전). 다운로드 완료 후 재실행.
- candidates: `[]`

---

## §3. 법령 Open API

- status: **calls_completed** / oc_configured=True (값은 미출력)
### 가이드 근거
```json
{
  "portal_list": "https://open.law.go.kr/LSO/openApi/guideList.do",
  "law_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=law&type=1",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "law",
    "key_params": [
      "OC",
      "target=law",
      "type",
      "search(1명/2본문)",
      "query",
      "display<=100",
      "page",
      "efYd",
      "ancYd",
      "date",
      "nb"
    ]
  },
  "law_body": {
    "guide_candidates_tried": [
      "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lawInfoGuide",
      "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsInfoGuide",
      "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsBodInfoGuide"
    ],
    "note": "본문 가이드 htmlName 페이지는 404. 목록 API 응답의 법령상세링크가 lawService.do?target=law&MST={법령일련번호} 형태임을 확인(실측). ID 파라미터는 '일치하는 법령이 없습니다' 응답. 따라서 MST=법령일련번호로 본문 조회.",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "law",
    "params_confirmed_by_list_link": [
      "OC",
      "target=law",
      "MST=법령일련번호",
      "type"
    ],
    "evidence": "LawSearch.law[].법령상세링크 실측 필드"
  },
  "prec_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "prec",
    "key_params": [
      "search=2 본문검색",
      "query",
      "display",
      "page"
    ]
  },
  "prec_body": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "prec",
    "key_params": [
      "ID(판례일련번호)",
      "type"
    ]
  },
  "admrul_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "admrul",
    "key_params": [
      "nw(1현행/2연혁)",
      "query",
      "knd",
      "search",
      "prmlYd"
    ]
  },
  "admrul_body": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "admrul",
    "key_params": [
      "ID",
      "LID",
      "LM"
    ]
  },
  "expc_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "expc",
    "key_params": [
      "search",
      "query",
      "inq",
      "rpl"
    ]
  },
  "expc_body": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcInfoGuide",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "expc",
    "key_params": [
      "ID"
    ]
  },
  "ftc_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cmtListGuide",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "ftc",
    "key_params": [
      "search",
      "query",
      "type=HTML|XML (가이드상 JSON 미기재)"
    ],
    "type_note": "가이드 표기는 HTML/XML. JSON 시도 후 실패 시 XML 저장."
  },
  "ftc_body": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cmtInfoGuide",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "ftc",
    "key_params": [
      "ID",
      "type=HTML|XML"
    ]
  },
  "lstrm_list": {
    "guide": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsTrmListGuide",
    "url": "http://www.law.go.kr/DRF/lawSearch.do",
    "target": "lstrm"
  },
  "lstrmRlt": {
    "guide": "http://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide",
    "url": "http://www.law.go.kr/DRF/lawService.do",
    "target": "lstrmRlt",
    "key_params": [
      "query|MST",
      "trmRltCd"
    ]
  },
  "history": {
    "efYd_list": "법령 목록 API efYd 범위 필터 문서화됨 (law list guide)",
    "asof_body": "특정일 시점 본문 전용 파라미터는 가이드에서 미확인. 연혁 목록(시행일>=20220101) 저장 후 각 법령일련번호로 본문 조회 시도.",
    "admrul_nw": "행정규칙 목록 nw=2 연혁 (admrulListGuide)"
  }
}
```
### 3-1
- 요청수=20 성공수=20 실패수=0 저장=20
- sample_head_300: {"법령": {
    "개정문": {"개정문내용": [[
        "국회에서 의결된 근로기준법 일부개정법률을 이에 공포한다.",
        "          대통령        이재명 (인)",
        "    2026년 4월 7일",
        "          국무총리        김민석",
        "          국무위원 고용노동부 장관        김영훈",
        "⊙법률 제21533호",
        "근로기준법 일부개정법률",
        "근로기준법 일부를 다음과 같이 개
- law_ids: `{'근로기준법': {'법령일련번호': '285279', '법령ID': '001872', '시행일자': '20261008', '공포번호': '21533', '현행연혁코드': '현행', 'body_param': 'MST'}, '근로기준법 시행령': {'법령일련번호': '270551', '법령ID': '003058', '시행일자': '20251023', '공포번호': '35436', '현행연혁코드': '현행', 'body_param': 'MST'}, '최저임금법': {'법령일련번호': '218303', '법령ID': '000129', '시행일자': '20200526', '공포번호': '17326', '현행연혁코드': '현행', 'body_param': 'MST'}, '최저임금법 시행령': {'법령일련번호': '206564', '법령ID': '005247', '시행일자': '20190101', '공포번호': '29469', '현행연혁코드': '현행', 'body_param': 'MST'}, '주택임대차보호법': {'법령일련번호': '276291', '법령ID': '001248', '시행일자': '20260102', '공포번호': '21065', '현행연혁코드': '현행', 'body_param': 'MST'}, '주택임대차보호법 시행령': {'법령일련번호': '287183', '법령ID': '004950', '시행일자': '20260701', '공포번호': '36423', '현행연혁코드': '현행', 'body_param': 'MST'}, '민법': {'법령일련번호': '284415', '법령ID': '001706', '시행일자': '20260317', '공포번호': '21454', '현행연혁코드': '현행', 'body_param': 'MST'}, '이자제한법': {'법령일련번호': '268667', '법령ID': '010404', '시행일자': '20250722', '공포번호': '20714', '현행연혁코드': '현행', 'body_param': 'MST'}, '이자제한법 제2조제1항의 최고이자율에 관한 규정': {'법령일련번호': '230727', '법령ID': '010468', '시행일자': '20210707', '공포번호': {'content': ['3', '593'], 'strong': {'content': '1', 'class': 'tbl_tx_type'}}, '현행연혁코드': '현행', 'body_param': 'MST'}, '보증인 보호를 위한 특별법': {'법령일련번호': '251943', '법령ID': '010717', '시행일자': '20231221', '공포번호': '19504', '현행연혁코드': '현행', 'body_param': 'MST'}}`
### 3-2
- 요청수=19 성공수=19 실패수=0 저장=19
- sample_head_300: {"LawSearch": {
    "law": [
        {
            "현행연혁코드": "현행",
            "법령일련번호": "269393",
            "자법타법여부": "",
            "법령상세링크": "/DRF/lawService.do?OC=REDACTED&target=law&MST=269393&type=HTML&mobileYn=&efYd=20250223",
            "법령명한글": "근로기준법 시행규칙",
            "법령구분명": "
### 3-3
- 요청수=11 성공수=7 실패수=0 저장=7
- sample_head_300: {"AdmRulSearch": {
    "resultMsg": "success",
    "키워드": "최저임금",
    "page": "1",
    "resultCode": "00",
    "target": "admrul",
    "admrul": [
        {
            "현행연혁구분": "현행",
            "행정규칙명": "2026년 선원 최저임금 고시",
            "발령일자": "20251208",
            "행정규칙종류": "고시",
            "소
- 최저임금 시간급: `[{'year': 2022, 'name': None, 'hourly': '미확인', 'note': '검색 목록에서 연도 매칭 실패'}, {'year': 2023, 'name': None, 'hourly': '미확인', 'note': '검색 목록에서 연도 매칭 실패'}, {'year': 2024, 'name': None, 'hourly': '미확인', 'note': '검색 목록에서 연도 매칭 실패'}, {'year': 2025, 'name': None, 'hourly': '미확인', 'note': '검색 목록에서 연도 매칭 실패'}, {'year': 2026, 'name': '2026년 선원 최저임금 고시', 'ID': '2100000269386', 'hourly': '2,694,560', 'evidence': '2,694,560원'}]`
### 3-4
- 요청수=917 성공수=915 실패수=2 저장=426
- sample_head_300: {"PrecSearch": {
    "키워드": "임대차 특약 무효",
    "page": "1",
    "target": "prec",
    "prec": [
        {
            "id": "1",
            "사건번호": "2023다264530",
            "데이터출처명": "대법원",
            "사건종류코드": "400101",
            "사건종류명": "민사",
            "선고": "선고",
            "선고일자": "2025.
- 판례 키워드별: `{'임대차 특약 무효': 161, '원상복구 특약': 79, '임대차 위약금': 151, '보증금 반환 특약': 200, '계약갱신요구권 포기': 13, '근로계약 위약금': 136, '위약예정': 200, '임금 공제': 200, '수습기간 임금': 135, '주휴수당': 200, '휴게시간': 200, '이자제한법 초과': 200, '보증 서면': 200, '차용증': 200}`
- unique_list=1986 bodies_saved=400
- 실패 일부: `[{"ID": "209971", "error": "TimeoutError('timed out')"}, {"ID": "118524", "error": "TimeoutError('timed out')"}]`
### 3-5
- 요청수=28 성공수=28 실패수=0 저장=28
- sample_head_300: <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" lang="ko" xml:lang="ko">

<head>

<meta http-equiv="X-UA-Compatible" content="IE=edge">      

<meta http-equiv="Content-Type" content
### 3-6
- 요청수=2 성공수=2 실패수=0 저장=2
- sample_head_300: <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" lang="ko" xml:lang="ko">

<head>

<meta http-equiv="X-UA-Compatible" content="IE=edge">      

<meta http-equiv="Content-Type" content
### 3-7
- 요청수=12 성공수=12 실패수=0 저장=12
- sample_head_300: <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" lang="ko" xml:lang="ko">

<head>

<meta http-equiv="X-UA-Compatible" content="IE=edge">      

<meta http-equiv="Content-Type" content

---

## §4. 주택임대차분쟁조정사례집

- status: **parsed_image_pdf**
- path: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\cases\주택임대차분쟁조정사례집.pdf` bytes=35722003
- pages: 101
- case_count: 미확인(텍스트 레이어 없음, OCR 필요)
- first_case_title: 미확인
- first_case_text_head_300: 미확인 — 스캔본이라 텍스트 추출 불가. OCR 미설치/진행중.
- note: 없음(스캔/이미지 PDF, pdfplumber chars=0)

---

## §5. 모델

### 로컬 기존

| kind | name | GB | type | path |
|---|---|---:|---|---|
| gguf | EXAONE-4.0-32B-Q6_K.gguf | 24.456 | Q6_K | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\EXAONE-4.0-32B-GGUF\EXAONE-4.0-32B-Q6_K.gguf` |
| gguf | Qwen3-32B-Q6_K.gguf | 25.037 | Q6_K | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen3-32B-GGUF\Qwen3-32B-Q6_K.gguf` |
| hf_dir | Qwen2.5-14B-Instruct | 27.522 | qwen2 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct` |
| hf_dir | f39ac1d28e925b323eae81227eaba4464caced4e | 7.12 | phi3 | `C:\Users\DMLAB\.cache\huggingface\hub\models--microsoft--Phi-3-mini-4k-instruct\snapshots\f39ac1d28e925b323eae81227eaba4464caced4e` |
| hf_dir | 60d2b0434a53d2e62a7c00a489586815d94ebffb | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen-AgentWorld-35B-A3B\snapshots\60d2b0434a53d2e62a7c00a489586815d94ebffb` |
| hf_dir | cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8 | 0.011 | qwen2 | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen2.5-14B-Instruct\snapshots\cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` |
| hf_dir | 8efa61729e24bd65b1d152b5ab5409052aa80e65 | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B\snapshots\8efa61729e24bd65b1d152b5ab5409052aa80e65` |
| hf_dir | 39eb2b067ea6b8e3e1dd97d3cd0c7ffeaf3e1a35 | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B-FP8\snapshots\39eb2b067ea6b8e3e1dd97d3cd0c7ffeaf3e1a35` |
| hf_dir | ac9c66cc9b46af7306746a9250f23d47083d689e | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B-Instruct-2507\snapshots\ac9c66cc9b46af7306746a9250f23d47083d689e` |
| hf_dir | e156cb4efae43fbee1a1ab073f946a1377e6b969 | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B-Instruct-2507-FP8\snapshots\e156cb4efae43fbee1a1ab073f946a1377e6b969` |
| hf_dir | a9b4800972d7b032a3af9fd81bbeb4a6bee6b63f | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B-MLX-6bit\snapshots\a9b4800972d7b032a3af9fd81bbeb4a6bee6b63f` |
| hf_dir | 6cbffae6d8e28b986a6b17bd36f42f9fa0f1f0a5 | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-235B-A22B-Thinking-2507\snapshots\6cbffae6d8e28b986a6b17bd36f42f9fa0f1f0a5` |
| hf_dir | b968826d9c46dd6066d109eabc6255188de91218 | 0.0 | qwen3 | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-8B\snapshots\b968826d9c46dd6066d109eabc6255188de91218` |
| hf_dir | 9d90cf8fca1bf7b7acca42d3fc9ae694a2194069 | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-Coder-480B-A35B-Instruct\snapshots\9d90cf8fca1bf7b7acca42d3fc9ae694a2194069` |
| hf_dir | 003f183a92fbe5b9a8325aaa8b2ae797c91dd90f | 0.0 | qwen3_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-Coder-480B-A35B-Instruct-FP8\snapshots\003f183a92fbe5b9a8325aaa8b2ae797c91dd90f` |
| hf_dir | 710c13861be6c466e66de3f484069440b8f31389 | 0.0 | qwen3_vl_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-VL-235B-A22B-Instruct\snapshots\710c13861be6c466e66de3f484069440b8f31389` |
| hf_dir | 6664affde68449468deb7527186455c7450c13c0 | 0.0 | qwen3_vl_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3-VL-235B-A22B-Thinking\snapshots\6664affde68449468deb7527186455c7450c13c0` |
| hf_dir | 59d61f3ce65a6d9863b86d2e96597125219dc754 | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.5-35B-A3B\snapshots\59d61f3ce65a6d9863b86d2e96597125219dc754` |
| hf_dir | 0f0813072d2358973511097385626f21fcb6d422 | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.5-35B-A3B-Base\snapshots\0f0813072d2358973511097385626f21fcb6d422` |
| hf_dir | 9d1823d2dee688a6b25e77009dc727688c44936e | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.5-35B-A3B-FP8\snapshots\9d1823d2dee688a6b25e77009dc727688c44936e` |
| hf_dir | 3af5ca2972faf6de1fd6f4efc4d8d319ca751e8b | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.5-35B-A3B-GPTQ-Int4\snapshots\3af5ca2972faf6de1fd6f4efc4d8d319ca751e8b` |
| hf_dir | 995ad96eacd98c81ed38be0c5b274b04031597b0 | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.6-35B-A3B\snapshots\995ad96eacd98c81ed38be0c5b274b04031597b0` |
| hf_dir | 95a723d08a9490559dae23d0cff1d9466213d989 | 0.0 | qwen3_5_moe | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--Qwen3.6-35B-A3B-FP8\snapshots\95a723d08a9490559dae23d0cff1d9466213d989` |
| hf_dir | c960d05effbd7e5e5839886ddbe221a6144e8d86 | 0.0 | topk_sae | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--SAE-Res-Qwen3.5-35B-A3B-Base-W128K-L0_100\snapshots\c960d05effbd7e5e5839886ddbe221a6144e8d86` |
| hf_dir | 6af81a5a1b16ac821e5a9267fb461493ccfe2770 | 0.0 | topk_sae | `C:\Users\DMLAB\.cache\huggingface\hub\models--Qwen--SAE-Res-Qwen3.5-35B-A3B-Base-W32K-L0_50\snapshots\6af81a5a1b16ac821e5a9267fb461493ccfe2770` |

### 다운로드
- `Qwen/Qwen3-8B` ok=True GB=15.271 files=15 err=None type=qwen3 vocab=151936 max_pos=40960 license=Apache License
- `nlpai-lab/KURE-v1` ok=True GB=2.132 files=13 err=None type=xlm-roberta vocab=250002 max_pos=8194 license=license: mit
- `BAAI/bge-m3` ok=True GB=4.272 files=30 err=None type=xlm-roberta vocab=250002 max_pos=8194 license=license: mit

### 해시 검증
- `Qwen/Qwen3-8B` files=15 GB=15.271 incomplete=6
  - .gitattributes bytes=1570 sha256=34448b82c17d60fec9b65b1f093c115ddbaadc04beb1b0140b6bfed2e012a930
  - config.json bytes=728 sha256=f7c4eadfbbf522470667b797a3c89be2524832d2d599797248dc304fff447c30
  - generation_config.json bytes=239 sha256=2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2
  - LICENSE bytes=11343 sha256=832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e
  - merges.txt bytes=1671853 sha256=8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5
  - model-00001-of-00005.safetensors bytes=3996250744 sha256=31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f
  - model-00002-of-00005.safetensors bytes=3993160032 sha256=5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282
  - model-00003-of-00005.safetensors bytes=3959604768 sha256=c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836
  - model-00004-of-00005.safetensors bytes=3187841392 sha256=b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a
  - model-00005-of-00005.safetensors bytes=1244659840 sha256=20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff
  - model.safetensors.index.json bytes=32878 sha256=f9fdbcb91c23971c13ec5d5f2573d2349e8f61f2f049371ec699281748fdb1bc
  - README.md bytes=16660 sha256=0f36caaff9c2516411a7738db384606263ba653c1e63e61d72f511606164d5a6
  - tokenizer.json bytes=11422654 sha256=aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4
  - tokenizer_config.json bytes=9732 sha256=d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101
  - vocab.json bytes=2776833 sha256=ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
- `nlpai-lab/KURE-v1` files=13 GB=2.132 incomplete=0
  - .gitattributes bytes=1620 sha256=f2919710d8127894f436ba6e44d1e6a7daa4e5b778632fbe42b735104db0e081
  - 1_Pooling\config.json bytes=297 sha256=13e69897522ee8255104483ed9f219465d1be3936654a54a318758738052789e
  - config.json bytes=807 sha256=852d42e020c7f989c2acaf30fc683b7f768e8c6d1ab17166e835442162bd825d
  - config_sentence_transformers.json bytes=220 sha256=8c73684c2160f2209f3706d6cbe0e933287fe6945d9546042be4c105cdb5252e
  - kure_logo.png bytes=593567 sha256=6323352feee84b8d2fcc0ba74b9761315e2eb96e7a424906ecca1ec4abf508ef
  - model.safetensors bytes=2271064456 sha256=c18156e80caf8ff45eb84a24a853130c3bca03087ccb41b051f86e7556bae02c
  - modules.json bytes=349 sha256=84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf
  - README.md bytes=17338 sha256=31eee15f3a8169b6749a4ac61c56e63ad5a6d9dbb6c96d4c6fae3c0522c61d6d
  - sentence_bert_config.json bytes=54 sha256=eb9b44b13c0f52a3b3685c3b1cbdea1ba8b04bea123b98f61610048940776eb1
  - special_tokens_map.json bytes=964 sha256=8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835
  - tokenizer.json bytes=17083053 sha256=fb3c3b93c46fd5a8634e262e1b7de7da11a18b527aa2282b312952b692781dfd
  - tokenizer_config.json bytes=1203 sha256=b87c8703482b0300d3da30e201519aa641f6a450f5eb5bf1e624afbf70c74d80
  - trainer_state.json bytes=11033 sha256=034d53976146a1922e238cf779dbbe33e861a771d50b73f1f18f1ae82c01b06a
- `BAAI/bge-m3` files=30 GB=4.272 incomplete=0
  - .gitattributes bytes=1627 sha256=7363a8ebd782ede400e72bb3e88c19248478eb6f280a7376d398fc2f22707b9a
  - 1_Pooling\config.json bytes=191 sha256=e54c164a07274f2eb45bb724f54a79d1efcc90c41573887cd9a29aeee0597352
  - colbert_linear.pt bytes=2100674 sha256=19bfbae397c2b7524158c919d0e9b19393c5639d098f0a66932c91ed8f5f9abb
  - config.json bytes=687 sha256=26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa
  - config_sentence_transformers.json bytes=123 sha256=1eef72430e7194a1e59680e635aed81ffa083f05668dbc5bb1c56c04c0999c38
  - imgs\.DS_Store bytes=6148 sha256=d65165279105ca6773180500688df4bdc69a2c7b771752f0a46ef120b7fd8ec3
  - imgs\bm25.jpg bytes=131849 sha256=4d88d1c224dc6dae62b76547e1e79ed12e1085b94dc1fe0c50440a948277d89a
  - imgs\long.jpg bytes=485432 sha256=d2a44539154d2cee75abd032fe773d5514f1129b741c4641cde12554762709a6
  - imgs\miracl.jpg bytes=576482 sha256=a48c10a1be83aa7a92a25d85dbc6d2c0194b59503a2599a9e89bd7e063c32a66
  - imgs\mkqa.jpg bytes=608027 sha256=ae331fb64bdceeaafecc2f8cd89a2d55a3e41c429dcc5ba906cb9a7bdb73cf2b
  - imgs\nqa.jpg bytes=158358 sha256=5385ca9d6af4124932281039e1366d704d10ed81e905526f795f5732352394bb
  - imgs\others.webp bytes=20984 sha256=9222ef69ba79cbd3aa8c659bd3cbbf9d90b3dbb040526f56298ed9ceb05ec9df
  - long.jpg bytes=126894 sha256=4ba03433ef54575eeef5a291abd81661eb53c432677934dc4050565893e7a8a9
  - modules.json bytes=349 sha256=84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf
  - onnx\config.json bytes=698 sha256=f24afd5de914fba8c668426c43d208a1a54022500c63b2c160be20891686fce8
  - onnx\Constant_7_attr__value bytes=65552 sha256=cdf16f72c5d07b36484056e601ed9687f78477e5d85cee85a34f2406b7fb5906
  - onnx\model.onnx bytes=724923 sha256=f84251230831afb359ab26d9fd37d5936d4d9bb5d1d5410e66442f630f24435b
  - onnx\model.onnx_data bytes=2266820608 sha256=1eebfb28493f67bba03ce0ef64bfdc7fc5a3bd9d7493f818bb1d78cd798416b4
  - onnx\sentencepiece.bpe.model bytes=5069051 sha256=cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865
  - onnx\special_tokens_map.json bytes=964 sha256=8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835
  - onnx\tokenizer.json bytes=17082821 sha256=6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790
  - onnx\tokenizer_config.json bytes=1173 sha256=7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4
  - pytorch_model.bin bytes=2271145830 sha256=b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38
  - README.md bytes=15822 sha256=0b81ccf9134e5874d620a86e6905062ea999e779c34eb1a7e65eaeb7fe00e450
  - sentence_bert_config.json bytes=54 sha256=eb9b44b13c0f52a3b3685c3b1cbdea1ba8b04bea123b98f61610048940776eb1
  - sentencepiece.bpe.model bytes=5069051 sha256=cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865
  - sparse_linear.pt bytes=3516 sha256=45c93804d2142b8f6d7ec6914ae23a1eee9c6a1d27d83d908a20d2afb3595ad9
  - special_tokens_map.json bytes=964 sha256=8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835
  - tokenizer.json bytes=17098108 sha256=21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08
  - tokenizer_config.json bytes=444 sha256=a62b2b6784f990259fddef5f16388693a8043be4f69179e6a5257eeb3f9abac4

### 교사 후보(다운로드 금지)
- Qwen3-8B vocab: 151936
| id | vocab | match8B | experts | license | GGUF | listedGB | estQ4/Q6 |
|---|---:|:---:|---|---|---|---:|---|
| `Qwen/Qwen-AgentWorld-35B-A3B` | None | False | None/None | apache-2.0 | False | 64.582 | 16.15/24.22 |
| `Qwen/Qwen3-235B-A22B` | 151936 | True | 128/8 | apache-2.0 | Qwen/Qwen3-235B-A22B-GGUF | 437.918 | 109.48/164.22 |
| `Qwen/Qwen3-235B-A22B-FP8` | 151936 | True | 128/8 | apache-2.0 | False | 222.649 | 55.66/83.49 |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 151936 | True | 128/8 | apache-2.0 | False | 437.919 | 109.48/164.22 |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | 151936 | True | 128/8 | apache-2.0 | False | 220.21 | 55.05/82.58 |
| `Qwen/Qwen3-235B-A22B-MLX-6bit` | 151936 | True | 128/8 | apache-2.0 | False | 171.069 | 42.77/64.15 |
| `Qwen/Qwen3-235B-A22B-Thinking-2507` | 151936 | True | 128/8 | apache-2.0 | False | 437.915 | 109.48/164.22 |
| `Qwen/Qwen3-Coder-480B-A35B-Instruct` | 151936 | True | 160/8 | apache-2.0 | False | 894.375 | 223.59/335.39 |
| `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` | 151936 | True | 160/8 | apache-2.0 | False | 449.057 | 112.26/168.4 |
| `Qwen/Qwen3-VL-235B-A22B-Instruct` | None | False | None/None | apache-2.0 | Qwen/Qwen3-VL-235B-A22B-Instruct-GGUF | 438.981 | 109.75/164.62 |
| `Qwen/Qwen3-VL-235B-A22B-Thinking` | None | False | None/None | apache-2.0 | Qwen/Qwen3-VL-235B-A22B-Thinking-GGUF | 438.981 | 109.75/164.62 |
| `Qwen/Qwen3.5-35B-A3B` | None | False | None/None | apache-2.0 | False | 66.987 | 16.75/25.12 |
| `Qwen/Qwen3.5-35B-A3B-Base` | None | False | None/None | apache-2.0 | False | 66.987 | 16.75/25.12 |
| `Qwen/Qwen3.5-35B-A3B-FP8` | None | False | None/None | apache-2.0 | False | 34.92 | 8.73/13.09 |
| `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` | None | False | None/None | apache-2.0 | False | 22.778 | 5.69/8.54 |
| `Qwen/Qwen3.6-35B-A3B` | None | False | None/None | apache-2.0 | False | 66.987 | 16.75/25.12 |
| `Qwen/Qwen3.6-35B-A3B-FP8` | None | False | None/None | apache-2.0 | False | 34.918 | 8.73/13.09 |

---

## 사람이 해야 할 일

1. AI Hub 판결서·약관(dataSetSn=580) zip 다운로드 완료 후 `scripts/s2_watch_and_run.py` 재실행
2. 사례집 PDF가 스캔본 — Tesseract OCR 설치 후 사례 수/첫 사례 텍스트 추출, 또는 텍스트 레이어 PDF 확보
3. 교사 35B급 확정 후 GGUF/원본 선택 다운로드
---

---

---
## 검토 수정 A–F (성공=기대 JSON 구조) — 2026-10-14 16:08

판정 기준: HTTP 상태코드가 아니라 **응답 본문이 기대한 JSON 키/구조를 갖는지**.

### A. 3-5 법령해석례 · 3-6 공정위 · 3-7 법령용어

#### 기존 저장 HTML 오류 문구
- **3-5**
  - `법령해석례\list_고용노동부_근로계약.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - `법령해석례\list_고용노동부_보증금.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - `법령해석례\list_고용노동부_수습.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
- **3-6**
  - `공정위\list_임대차_약관_XML.xml`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - `공정위\list_임대차계약서_XML.xml`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
- **3-7**
  - `법령용어\lstrm_list_p1.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - `법령용어\lstrm_list_p2.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - `법령용어\lstrm_list_p3.json`: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)

- **target=expc**: 미승인. 오류: 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(02-2109-6446)
  - 가이드: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide
  - 조치: target=expc 미승인. 중앙부처 1차 해석(moelCgmExpc 등)으로 대체 시도.

| 기관/API | target | 목록(JSON) | 본문 | 샘플 앞 300자 |
|---|---|---:|---:|---|
| 법무부 | `mojCgmExpc` | FAIL | — |  |
| 고용노동부 | `moelCgmExpc` | 10 | 100 | {"CgmExpcService": {     "안건명": "10인 미만 사업장 취업규칙의 효력 등 관련 행정해석 변경",     "질의요지":  |
| 국토교통부 | `molitCgmExpc` | 8 | 100 | {"CgmExpcService": {     "중분류": "",     "해석기관코드": "1613000",     "안건번호": "",     |
| 법제처 | `molegCgmExpc` | 7 | 1 | {"CgmExpcService": {     "안건명": "법제처에서 제공하는 법제교육에는 어떤 것이 있는지 궁금합니다.",     "질의요지" |
| 공정위 | `ftc` | 2 | 65 | {"FtcService": {     "시정권고이유": "1. 권리설정 제한조항가. 약관조항<img src=\"/LSW/flDownload.do |
| 법령용어(원) | `lstrm` | 미승인 | — | 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] ->  |
| 법령용어연계 | `lstrmRlt` | 11 | 11 | {"lstrmRltService": {     "검색결과개수": "1",     "키워드": "근로계약",     "target": "lstrm |

### B. 연혁 (법령명 완전일치 · 2022-01-01 이후 시행판)

- 가이드 목록: https://open.law.go.kr/LSO/openApi/guideList.do
- **법령 연혁 API**: target=`lsHistory`, type=**HTML only** (목록: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide), 본문: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide))
- 구조화 본문: target=law JSON + efYd + 법령명한글 완전일치 필터 후 MST 본문(JSON) — 구조화 저장용
- 참고: 2022-01-01 이후 신규 시행판이 없는 법령은 현행(시행일<2022) 본문을 포함. 해당 기간에 적용되는 동일 텍스트임.

#### 이전 본문 중 법령명 불일치(시행령·시행규칙 혼입 등): 6건
- `연혁\근로기준법_body_MST_269393.json`: expected=`근로기준법` actual=`근로기준법 시행규칙`
- `연혁\근로기준법_body_MST_270551.json`: expected=`근로기준법` actual=`근로기준법 시행령`
- `연혁\민법_body_MST_266851.json`: expected=`민법` actual=`민법법인 및 특수법인 등기규칙`
- `연혁\민법_body_MST_266929.json`: expected=`민법` actual=`난민법 시행규칙`
- `연혁\민법_body_MST_273705.json`: expected=`민법` actual=`난민법 시행령`
- `연혁\주택임대차보호법_body_MST_287183.json`: expected=`주택임대차보호법` actual=`주택임대차보호법 시행령`

#### 근로기준법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20261008 | 21533 | 285279 |

#### 근로기준법 시행령 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20251023 | 35436 | 270551 |

#### 최저임금법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20200526 | 17326 | 218303 |

#### 최저임금법 시행령 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20190101 | 29469 | 206564 |

#### 주택임대차보호법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20260102 | 21065 | 276291 |

#### 주택임대차보호법 시행령 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20260701 | 36423 | 287183 |

#### 민법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20260317 | 21454 | 284415 |

#### 이자제한법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20250722 | 20714 | 268667 |

#### 이자제한법 제2조제1항의 최고이자율에 관한 규정 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20210707 | 31593 | 230727 |

#### 보증인 보호를 위한 특별법 — 시행판 1 · 본문 1

| 시행일 | 공포번호 | MST |
|---|---|---|
| 20231221 | 19504 | 251943 |

### C. 최저임금 고시 (적용 최저임금 고시, nw=1·2, 선원 제외)

- 검색어: `적용 최저임금 고시` · nw=[1, 2]

| 연도 | 고시명 | 시간급 | 근거 인용 |
|---|---|---|---|
| 2022 | 2022년 적용 최저임금 고시 | 9,160 | 2022년 적용 최저임금은 시간급 9,160원 |
| 2023 | 2023년 적용 최저임금 고시 | 9,620 | 2023년 적용 최저임금은 시간급 9,620원 |
| 2024 | 2024년 적용 최저임금 고시 | 9,860 | 시간급 모 든 산 업 9,860 원 |
| 2025 | 2025년 적용 최저임금 고시 | 10,030 | 시간급 모 든 산 업 10,030 원 |
| 2026 | 2026년 적용 최저임금 고시 | 10,320 | 시간급 모 든 산 업 10,320 원 |

### D. 판례 특약/약정 필터

```python
def passes_special_agreement_filter(판시사항: str, 판결요지: str) -> bool:
    blob = (판시사항 or "") + (판결요지 or "")
    return ("특약" in blob) or ("약정" in blob)
```
- 기존 본문 400건 중 판시사항/판결요지에 특약|약정: **140**건
- 목록 unique 1986건 전체 필터 적용 → 통과 본문 **216**건 (신규 fetch 1586)

| 키워드 | 필터 통과 수 |
|---|---:|
| 보증 서면 | 30 |
| 임대차 특약 무효 | 30 |
| 위약예정 | 27 |
| 주휴수당 | 27 |
| 보증금 반환 특약 | 26 |
| 임대차 위약금 | 24 |
| 원상복구 특약 | 22 |
| 근로계약 위약금 | 18 |
| 임금 공제 | 12 |
| 이자제한법 초과 | 8 |
| 휴게시간 | 7 |
| 수습기간 임금 | 6 |
| 차용증 | 2 |
| 계약갱신요구권 포기 | 0 |

### E. AI Hub 금전소비대차 · 금전대차계약서 소분류

- 금전대차계약서 소분류 존재: **False** → 개방 zip에 없음

| 대 | 중 | 소 | 건수 |
|---|---|---|---:|
| 금전소비대차_채권_채무 | 채권_채무계약 | 채권양도계약서 | 121 |
| 금전소비대차_채권_채무 | 채권_채무계약 | 채무승계계약서 | 95 |

원본 zip 목록:
- `3.개방데이터\1.데이터\Training\01.원천데이터\TS_금전소비대차_채권_채무_채권_채무계약.zip` (592,259 bytes)
- `3.개방데이터\1.데이터\Training\02.라벨링데이터\TL_금전소비대차_채권_채무_채권_채무계약.zip` (640,780 bytes)
- `3.개방데이터\1.데이터\Validation\01.원천데이터\VS_금전소비대차_채권_채무_채권_채무계약.zip` (73,007 bytes)
- `3.개방데이터\1.데이터\Validation\02.라벨링데이터\VL_금전소비대차_채권_채무_채권_채무계약.zip` (79,559 bytes)

### F. 모델 해시 (HF LFS oid sha256 ↔ 로컬)

| repo | file | local_sha256 | hf_lfs_sha256 | match |
|---|---|---|---|---|
| Qwen/Qwen3-8B | `model-00001-of-00005.safetensors` | `31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f` | `31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f` | True |
| Qwen/Qwen3-8B | `model-00002-of-00005.safetensors` | `5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282` | `5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282` | True |
| Qwen/Qwen3-8B | `model-00003-of-00005.safetensors` | `c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836` | `c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836` | True |
| Qwen/Qwen3-8B | `model-00004-of-00005.safetensors` | `b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a` | `b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a` | True |
| Qwen/Qwen3-8B | `model-00005-of-00005.safetensors` | `20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff` | `20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff` | True |
| nlpai-lab/KURE-v1 | `model.safetensors` | `c18156e80caf8ff45eb84a24a853130c3bca03087ccb41b051f86e7556bae02c` | `c18156e80caf8ff45eb84a24a853130c3bca03087ccb41b051f86e7556bae02c` | True |
| BAAI/bge-m3 | `pytorch_model.bin` | `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38` | `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38` | True |

incomplete_remaining = **6** (삭제하지 않음)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\ewHVStNi_qTCwOvZyUK4XvcG7h0=.5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282.2359eee0.incomplete` (1,024,000,000 bytes)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\fNjCg19rjPb4Qv_8lvghvyvUVYM=.b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a.8a59a8f1.incomplete` (2,374,128,833 bytes)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\fNjCg19rjPb4Qv_8lvghvyvUVYM=.b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a.c8066dd7.incomplete` (3,103,964,316 bytes)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\ucOYR0sM0bukMpWiwV3qkLpQbMA=.31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f.9647bb55.incomplete` (1,024,000,000 bytes)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\ucOYR0sM0bukMpWiwV3qkLpQbMA=.31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f.e2cd7e84.incomplete` (3,017,777,202 bytes)
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\models\Qwen3-8B\.cache\huggingface\download\W6LiZUqSlTR2RfaiI-PdlBA4Fcg=.c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836.14d6a41d.incomplete` (1,024,000,000 bytes)

---
## §G 수집 마무리 (G1–G7) — 2026-10-15 00:56

성공 판정: HTTP가 아니라 **응답 본문이 기대한 JSON/XML 구조인지**.

### 상태표 (G1–G6)

| 단계 | 상태 | 요약 |
|---|---|---|
| G1 승인 API 재호출 | 완료 | 정상 ['expc', 'ftc'] / 실패 ['lstrm', 'mojCgmExpc', 'cgmExpc', 'ftc_XML']; expc_bodies=515; lstrm_bodies=None |
| G2 페이지 상한 | 완료 | 표 행 44 (target×키워드 totalCnt vs 저장) |
| G3 연혁 확정 | 완료 | 법령 6종, mismatch_rejected=9 |
| G4 AI Hub 580 | 완료 | status=not_found candidates=0 |
| G5 금전대차계약서 | 완료 | 개방 zip에 없음 / 데이터셋에 개방 안 됨 |
| G6 사례집 OCR | 완료 | engine=tesseract:C:\Program Files\Tesseract-OCR\tesseract.exe pages=101 hangul_avg=0.25776665083108763 quality_ok=False |
| G7 수동 다운로드 | 완료 | 항목 5 → `MANUAL_DOWNLOADS.html` |

### §G1. 승인 API 재호출

| target | 결과 | 오류/키 |
|---|---|---|
| `expc` | JSON/XML 정상 | keys=['Expc'] |
| `lstrm` | 권한없음/실패 | 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(0 |
| `mojCgmExpc` | 권한없음/실패 | 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(0 |
| `cgmExpc` | 권한없음/실패 | 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(0 |
| `ftc` | JSON/XML 정상 | keys=['Ftc'] |
| `ftc_XML` | 권한없음/실패 | 국가법령정보 공동활용 미신청된 목록/본문에 대한 접근입니다. OPEN API 로그인 후 [OPEN API] -> [OPEN API 신청] -> 등록된 API 선택 후 법령종류를 체크해 주세요. 동일한 문제가 지속될 경우 아래 번호로 문의해 주시기 바랍니다. 법제처 공동활용 유지보수팀(0 |
- expc 수집: 목록응답 9 / unique 515 / 본문 515
  - 샘플: `{"ExpcService": {
    "해석기관코드": "1170000",
    "안건번호": "08-0431",
    "이유": "○ 「청원경찰법」 제5조제3항 및 같은 법 시행령 제8조제3항에 따르면 청원경찰보수의 호봉간의 승급기간 및 승급액에 관하여는 청원경찰이 배치된 사업장의 취업규칙에 의하되, 이에 관한 취업규칙이 없을 때는 경찰관인 순경의 `

### §G2. 페이지 상한 (totalCnt vs 저장)

| target | 키워드 | totalCnt | 저장 목록 수 | 저장 본문 수 |
|---|---|---:|---:|---:|
| `moelCgmExpc` | 근로계약 | 1261 | 1261 | 1261 |
| `moelCgmExpc` | 최저임금 | 38 | 38 | 38 |
| `moelCgmExpc` | 주휴 | 183 | 183 | 183 |
| `moelCgmExpc` | 수습 | 39 | 39 | 39 |
| `moelCgmExpc` | 임대차 | 29 | 29 | 29 |
| `moelCgmExpc` | 보증금 | 13 | 13 | 13 |
| `moelCgmExpc` | 이자 | 72 | 72 | 72 |
| `molitCgmExpc` | 근로계약 | 3 | 3 | 3 |
| `molitCgmExpc` | 최저임금 | 0 | 0 | 0 |
| `molitCgmExpc` | 주휴 | 0 | 0 | 0 |
| `molitCgmExpc` | 수습 | 3 | 3 | 3 |
| `molitCgmExpc` | 임대차 | 123 | 123 | 123 |
| `molitCgmExpc` | 보증금 | 41 | 41 | 41 |
| `molitCgmExpc` | 이자 | 33 | 33 | 33 |
| `molegCgmExpc` | 근로계약 | 0 | 0 | 0 |
| `molegCgmExpc` | 최저임금 | 0 | 0 | 0 |
| `molegCgmExpc` | 주휴 | 0 | 0 | 0 |
| `molegCgmExpc` | 수습 | 1 | 1 | 1 |
| `molegCgmExpc` | 임대차 | 0 | 0 | 0 |
| `molegCgmExpc` | 보증금 | 0 | 0 | 0 |
| `molegCgmExpc` | 이자 | 0 | 0 | 0 |
| `mojCgmExpc` | 근로계약 | None | 0 | 0 |
| `mojCgmExpc` | 최저임금 | None | 0 | 0 |
| `mojCgmExpc` | 주휴 | None | 0 | 0 |
| `mojCgmExpc` | 수습 | None | 0 | 0 |
| `mojCgmExpc` | 임대차 | None | 0 | 0 |
| `mojCgmExpc` | 보증금 | None | 0 | 0 |
| `mojCgmExpc` | 이자 | None | 0 | 0 |
| `ftc` | 임대차 약관 | 24 | 24 | 24 |
| `ftc` | 임대차계약서 | 153 | 153 | 153 |
| `prec` | 임대차 특약 무효 | 161 | 161 | 161 |
| `prec` | 원상복구 특약 | 79 | 79 | 79 |
| `prec` | 임대차 위약금 | 151 | 151 | 151 |
| `prec` | 보증금 반환 특약 | 507 | 507 | 507 |
| `prec` | 계약갱신요구권 포기 | 13 | 13 | 13 |
| `prec` | 근로계약 위약금 | 136 | 136 | 136 |
| `prec` | 위약예정 | 308 | 308 | 308 |
| `prec` | 임금 공제 | 1555 | 1555 | 1555 |
| `prec` | 수습기간 임금 | 135 | 135 | 135 |
| `prec` | 주휴수당 | 200 | 200 | 200 |
| `prec` | 휴게시간 | 2065 | 2065 | 2065 |
| `prec` | 이자제한법 초과 | 460 | 460 | 460 |
| `prec` | 보증 서면 | 1123 | 1123 | 1123 |
| `prec` | 차용증 | 1253 | 1253 | 1253 |

### §G3. 연혁 법령 확정

- 방법: target=law JSON + efYd=20220101~오늘 + 법령명한글 완전일치
- lsHistory 가이드: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstListGuide / https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide
- 최저임금법·시행령·이자제한 최고이자율 규정은 2022 이전 시행판이 현행이라 G3 제외(기존 리포트 근거 유지)
- 법령명 불일치 거부(혼입): **9건** (완전일치만 저장)

#### 근로기준법 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20261008 | 20260407 | 21533 | 285279 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 근로기준법 시행령 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20251023 | 20250408 | 35436 | 270551 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 주택임대차보호법 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20260102 | 20251001 | 21065 | 276291 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 주택임대차보호법 시행령 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20260701 | 20260623 | 36423 | 287183 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 민법 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20260317 | 20260317 | 21454 | 284415 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 보증인 보호를 위한 특별법 — 1판 · 본문 1

| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |
|---|---|---|---|---|---|
| 20231221 | 20230620 | 19504 | 251943 | True | law_JSON_MST |

시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).

#### 검증: 주택임대차보호법 제7조 / 근로기준법 제17조

**주택임대차보호법_제7조** (문구 상이 여부: False)

| 시행일 | MST | 조문 텍스트(앞부분) |
|---|---|---|
| 20260102 | 276291 | 제7조(차임 등의 증감청구권) ① 당사자는 약정한 차임이나 보증금이 임차주택에 관한 조세, 공과금, 그 밖의 부담의 증감이나 경제사정의 변동으로 인하여 적절하지 아니하게 된 때에는 장래에 대하여 그 증감을 청구할 수 있다. 이 경우 증액청구는 임대차계약 또는 약정한 차임이나 보증금의 증액이 있은 후 1년 이내에는 하지 못한다. <개정 2020.7.31> ② |

**근로기준법_제17조** (문구 상이 여부: False)

| 시행일 | MST | 조문 텍스트(앞부분) |
|---|---|---|
| 20261008 | 285279 | 제17조(근로조건의 명시) ① 사용자는 근로계약을 체결할 때에 근로자에게 다음 각 호의 사항을 명시하여야 한다. 근로계약 체결 후 다음 각 호의 사항을 변경하는 경우에도 또한 같다. <개정 2010.5.25> 1. 임금 2. 소정근로시간 3. 제55조에 따른 휴일 4. 제60조에 따른 연차 유급휴가 5. 그 밖에 대통령령으로 정하는 근로조건 ② 사용자는 제 |

### §G4. AI Hub 판결서·약관 (580)

- status: **not_found**
- 임시파일(미완료) 무시: 0건

### §G5. 금전대차계약서

- 결론: **개방 zip에 없음 / 데이터셋에 개방 안 됨**
- aihubshell: {'tried': False, 'key_present': False, 'listing': None, 'note': '키 없음 — aihubshell 목록 조회 건너뜀'}

| 대 | 중 | 소 | 건수 |
|---|---|---|---:|
| 금전소비대차_채권_채무 | 채권_채무계약 | 채권양도계약서 | 121 |
| 금전소비대차_채권_채무 | 채권_채무계약 | 채무승계계약서 | 95 |

zip 내부 경로 샘플:
- `3.개방데이터\1.데이터\Training\01.원천데이터\TS_금전소비대차_채권_채무_채권_채무계약.zip`: ['/채권양도계약서_0004.json', '/채권양도계약서_0037.json', '/채권양도계약서_0013.json', '/채권양도계약서_0011.json', '/채권양도계약서_0007.json', '/채권양도계약서_0008.json', '/채권양도계약서_0005.json', '/채권양도계약서_0036.json']
- `3.개방데이터\1.데이터\Training\02.라벨링데이터\TL_금전소비대차_채권_채무_채권_채무계약.zip`: ['/채권양도계약서_0031.json', '/채권양도계약서_0011.json', '/채권양도계약서_0012.json', '/채권양도계약서_0010.json', '/채권양도계약서_0035.json', '/채권양도계약서_0036.json', '/채권양도계약서_0008.json', '/채권양도계약서_0007.json']
- `3.개방데이터\1.데이터\Validation\01.원천데이터\VS_금전소비대차_채권_채무_채권_채무계약.zip`: ['/채권양도계약서_0047.json', '/채권양도계약서_0122.json', '/채무승계계약서_0060.json', '/채무승계계약서_0092.json', '/채권양도계약서_0038.json', '/채권양도계약서_0040.json', '/채권양도계약서_0006.json', '/채무승계계약서_0016.json']
- `3.개방데이터\1.데이터\Validation\02.라벨링데이터\VL_금전소비대차_채권_채무_채권_채무계약.zip`: ['/채무승계계약서_0076.json', '/채권양도계약서_0073.json', '/채무승계계약서_0016.json', '/채권양도계약서_0040.json', '/채권양도계약서_0125.json', '/채무승계계약서_0051.json', '/채무승계계약서_0068.json', '/채무승계계약서_0063.json']

### §G6. 주택임대차분쟁조정사례집 OCR

- engine: tesseract:C:\Program Files\Tesseract-OCR\tesseract.exe / GPU=False / pages=101
- 평균 한글비율: 0.25776665083108763 / quality_ok=False
- 목차 페이지: [] / 사례 제목 수≈6
- **품질 미달(한글비율 < 70%) — 기록만 하고 중단**

**p4** hangul=0.48 broken=0.00
```
쵸 주 택 임 대 차 분 쟁 조 정 사 례 집


```
**p15** hangul=0.00 broken=0.00
```

```
**p36** hangul=0.36 broken=0.00
```
리 뿌 똥 흥 호

- 피 신 청 인 들 은 공 동 하 여 2021. O. O. 까 지 신 청 인 에 게 = 30,500,000 원 을 지 급 한 다 . we

이 를 지 체 하 면 피 신 청 인 들 은 신 청 인 에 게 2021. O. <). 부 터 다 갖 는 날 까 지 연 5% 의 비 율 로

- 신 청 인 은 2021. O. O. 피 신 청 인 들 로 부 터 금 579,500,000 원 ( 제 1 항 기 재 임 대 차 계 약 의
임 차 보 증 금 610,000,000 원 중 위 2 항 기 재 금 액 을 AM 나 머 지 금 액 
```
**p82** hangul=0.45 broken=0.00
```
D SE 등 주 택 하 자 에 대 한 유 지 ㆍ 수 선 의 무 는 임 대 인 의 의 무 임 을 확 인 하 여 임 대 차 계 약
종 료 후 보 증 금 을 전 액 반 환 하 도록 한 사 례

- ( 사 실 관 계 ) 임 차 인이 누 수 등 주 택 의 하 사 로 계 약 해 시 의 사 를 통 보 하 고 보 증 금 반 환 을
요 청 하 였 고 임 대 인 은 원 상 회 복 비 용 공 제 후 보 증 금 을 반 환 하 겠 다 고 +g

- ( 조 정 ) 외 관 으 로 누 수 가 확 인 되 시 않 아 임 차 인이 이 를 Ole] 인 지 하 고 있 
```
**p95** hangul=0.00 broken=0.00
```

```

사례 제목 샘플:
- 사 례 1

조 정 요 지
- 사 례 2

* 기 존 계 약 기 간 만 료 시에 임 대 차 종 료 하 는 것 으 로 하 되 , 임 대 인이 보 증 금 일 부 를
- 사 례 1

* 임 차 인 의 계 약 갱 신 요 구 당 시 의 Sa 임 대 인 에 게 실 거주 사 유 가 없 어 계 약 을 갱 신 된
- 사 례 3

* 임 대 인이 BA 임 대 목 적 물 의 매 도 예 정 을 언 급 한 사 실 , 임 대 목 적 물 소 재 지 가 임 대 인 의
- 사 례 2

* 임 대 인이 실 거주 갱 신 거 절 하 여 임 차 인이 퇴 거 한 이 후 임 대 인이 제 3 자 에 임 대 한 사 실 을
- 사 례 3

* 임 대 인이 실 거주 갱 신 거 절 하 여 엄 차 인이 퇴 거 한 이 후 임 대 인이 제 3 자 에 임 대 한 사 실 을 확 인

### §G7. 수동 다운로드

- 파일: `data_contract/MANUAL_DOWNLOADS.html`
- after_manual: `python data_contract\scripts\after_manual.py`
- 항목 수: **5**
  - Open API target=lsHistory 승인 확인
  - AI Hub 판결서·약관 데이터 (dataSetSn=580)
  - Open API target=lstrm 승인 확인
  - Open API target=mojCgmExpc 승인 확인
  - Open API target=cgmExpc 승인 확인

## 사람이 할 일

- `MANUAL_DOWNLOADS.html` 항목 **5**개:
  - Open API target=lsHistory 승인 확인
  - AI Hub 판결서·약관 데이터 (dataSetSn=580)
  - Open API target=lstrm 승인 확인
  - Open API target=mojCgmExpc 승인 확인
  - Open API target=cgmExpc 승인 확인
