# DATA_READY_REPORT — 계약서 분석 데이터·모델 준비

- C: 여유 2570.55 GB
- s5 disk_before/after: {'C': 2583.75} / {'C': 2570.55}

## 상태 요약표

| 항목 | 상태 | 경로 | 건수·크기 | 근거 |
|---|---|---|---|---|
| AIHub 계약 서식(05 zip) | 있음 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_forms` | 라벨 1182 / 고용577 임대389 금전216 | §1 |
| AIHub 풀패키지(~160GB) | 있음(모델·도커) | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터` | path=C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터 files=35 GB=161.46 | §1 |
| AIHub 판결서·약관 | 대기 중 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\aihub_terms` | ROOT/Downloads/Desktop 등에서 판결서·약관 관련 zip 미발견(또는 아직 생성 전). 다운로드 완료 후 재실행. | §2 |
| 법령 Open API | calls_completed | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\law_api` | oc_configured=True | §3 |
| 임대차분쟁조정사례집 PDF | parsed_image_pdf | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\cases\주택임대차분쟁조정사례집.pdf` | pages=101 cases=미확인(텍스트 레이어 없음, OCR 필요) bytes=35722003 | §4 |
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