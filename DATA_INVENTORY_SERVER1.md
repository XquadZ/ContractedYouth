# Server1 데이터 전수 점검

- 작성: 2026-10-20. 읽기 전용. 압축은 풀지 않고 zip 내부만 열람.
- WORK = `C:\Users\DMLAB_Server1\Contracted_Youth`
- USB = `D:\ai` (**있음**. 내용: `exp_gap1\data`, `exp_gap2\data`·`out`만)
- 보조: `WORK\inventory\` (`A_019.json`, `B_forms.json`, `D_law_api.json`, `A_terms_clauseField.csv`)

## 요약표

| 항목 | 위치 | 건수 | 상태 | 한 줄 설명 |
|---|---|---|---|---|
| A 약관 | WORK `019.../01.데이터` zip (aihub_terms는 플레이스홀더) | 라벨 JSON 9000 (유리 6300 / 불리 2700). 조항 `clauseArticle` 항목 10200 | 사용 가능 | 압축만 있음. 불리 조항 relateLaword·illdcssBasiss 100% 채워짐(내용은 약관법 조문 인용) |
| A 판결서 | 위와 동일 zip | 라벨 JSON 9000 (민사 4273 / 형사 2626 / 행정 2101) | 사용 가능 | 구조화 판결 요소+분류코드. 원천은 XML 9000 |
| A 제공 모델 | 없음 | 0 | 없음 | 019 폴더에 모델·학습코드·README 없음 |
| B 계약서식 | WORK `data_contract\aihub_forms` | JSON 2364 (파싱 2364). 파일명 알바 62 / 근로 334 / 주거임대 140 / 차용·보증 0 (채권양도 242·채무승계 190) | 사용 가능 | 라벨 메타(TL+VL) 알바 31·근로 167·주거 70·기타고용 379 |
| C 표준계약서 | WORK `data\standard_forms` | MANIFEST 27행. 추출 txt는 L1–L6만 6개 | 일부 문제 | 근로·주택임대·차용·보증 원본은 있음. H/D 추출 txt 없음. 연소자 추출 없음 |
| D 현행 법령 | WORK `data_contract\law_api\현행` | body 기준 법령 10종(+최고이자율 규정). 기간제법·약관규제법·대부업법·고용보험법·산재보험법 없음 | 일부 문제 | 조문 노드는 body JSON에 있음 |
| D 판례 | `law_api\판례` | 목록 레코드 10921, 고유 판례일련번호 **7414**. 본문 필드 0 | 일부 문제 | 검색 목록만. 판시사항·요지·전문 없음. 400에서 잘린 형태 아님 |
| D 해석례 | `law_api\법령해석례` | 파일 112 (json 82 / html 28 / other 2). 목록 레코드는 수집됨, 질의요지·회답·이유 필드 0 | 일부 문제 | 목록 API만. HTML(권한/페이지) 28 |
| D 공정위 | `law_api\공정위` | 목록 행 251, 고유 결정문 158. 사건명에 약관 10. 이유 필드 없음 | 일부 문제 | 검색은 임대차 약관·임대차계약서. 본문 미수집 |
| E 사례집 | `data_contract\cases` | 원본 PDF **없음**. OCR txt 101쪽분 + 스크린샷 8 | 일부 문제 | URL만 있음. OCR 품질 낮음(빈 파일 다수) |
| F 카탈로그 v0.2 | 없음 | checks **없음** | 없음 | catalog_v0.2.json, _checks.csv, CHANGELOG 전부 없음 |
| G LawQA-Ko | WORK `data\datasets\LawQA-Ko` | jsonl **14819** | 사용 가능 | question/precedent/answer. 라이선스명 파일에 없음 |
| H 리포트 | WORK 곳곳 | 지정 목록 중 있음 3 / 없음 6 (+DISTILL_AUDIT는 export 경로) | 일부 문제 | GAP1/GAP2/S2/VERIFY 없음 |
| I GPU | 이 PC | RTX 4090 24564 MiB, 드라이버 577.00 | 사용 가능 | Qwen3-8B/32B·EXAONE GGUF·KURE-v1 로컬 가중치 없음. HF 캐시에 bge-m3 등 |

---

## A. AI Hub 019 「법률, 규정 (판결서, 약관 등) 텍스트 분석 데이터」

**위치:** WORK `019.법률, 규정 (판결서, 약관 등) 텍스트 분석 데이터\` (파일 8, 156.7 MB).  
USB 없음. `data_contract\aihub_terms\`는 `NOT_FOUND.txt`·`WAITING.txt`만. `data\datasets\019...` 없음.

**형식:** 하위 `01.데이터`만. 압축 8개(TS/TL/VS/VL × 판결문/약관). 모델 파일 없음.

### A-1 하위 구성 (zip 멤버 수, 압축 미해제)

| zip | 구분 | 멤버 | JSON | XML | 바이트 |
|---|---|---:|---:|---:|---:|
| TL_1.판결문.zip | Training 라벨 | 8026 | 8000 | 0 | 32410769 |
| TL_2.약관.zip | Training 라벨 | 8007 | 8000 | 0 | 7826110 |
| TS_1.판결문.zip | Training 원천 | 8025 | 0 | 8000 | 49340464 |
| TS_2.약관.zip | Training 원천 | 8006 | 0 | 8000 | 57030570 |
| VL_1.판결문.zip | Validation 라벨 | 1025 | 1000 | 0 | 4056301 |
| VL_2.약관.zip | Validation 라벨 | 1006 | 1000 | 0 | 929148 |
| VS_1.판결문.zip | Validation 원천 | 1025 | 0 | 1000 | 6089786 |
| VS_2.약관.zip | Validation 원천 | 1006 | 0 | 1000 | 6602212 |

약관 라벨 폴더: `01.유리` / `02.불리`. 판결문 라벨 폴더: `01.민사` / `02.형사` / `03.행정` (+연도 구간).  
깨진 JSON **0** (라벨 JSON 전수 파싱). HTML 페이지 0.

### A-2 약관

- **전체 문서(라벨 JSON) 수:** 9000 (TL 8000 + VL 1000).
- **clauseArticle 항목 수(조항 텍스트 리스트 길이 합):** 10200.
- **dvAntageous:** `1`=6300, `2`=2700. 다른 값 0. (1=유리, 2=불리로 사용됨 — 폴더명 01.유리/02.불리와 일치).
- **분야 필드 이름:** `clauseField` (값이 `"1"`…`"43"` 숫자 코드). 코드북·한글 분야명 파일 **없음 → 확인 필요**.
- 분야별 유리·불리 건수 (라벨 JSON 9000, `clauseField` 코드 43개. 합 9000 = 유리 6300 + 불리 2700). 한글 분야명은 없음. 전수표는 `inventory\A_terms_clauseField.csv`.

| 코드 | 전체 | 유리(1) | 불리(2) | 코드 | 전체 | 유리(1) | 불리(2) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 500 | 100 | 400 | 23 | 164 | 164 | 0 |
| 2 | 450 | 100 | 350 | 24 | 98 | 98 | 0 |
| 3 | 408 | 100 | 308 | 25 | 302 | 252 | 50 |
| 4 | 101 | 101 | 0 | 26 | 201 | 128 | 73 |
| 5 | 538 | 40 | 498 | 27 | 237 | 237 | 0 |
| 6 | 173 | 100 | 73 | 28 | 115 | 75 | 40 |
| 7 | 161 | 99 | 62 | 29 | 39 | 25 | 14 |
| 8 | 178 | 167 | 11 | 30 | 146 | 146 | 0 |
| 9 | 196 | 196 | 0 | 31 | 336 | 336 | 0 |
| 10 | 99 | 99 | 0 | 32 | 494 | 442 | 52 |
| 11 | 272 | 272 | 0 | 33 | 324 | 181 | 143 |
| 12 | 120 | 120 | 0 | 34 | 117 | 100 | 17 |
| 13 | 161 | 161 | 0 | 35 | 122 | 120 | 2 |
| 14 | 135 | 135 | 0 | 36 | 267 | 100 | 167 |
| 15 | 156 | 156 | 0 | 37 | 100 | 100 | 0 |
| 16 | 200 | 200 | 0 | 38 | 150 | 98 | 52 |
| 17 | 197 | 197 | 0 | 39 | 273 | 98 | 175 |
| 18 | 100 | 100 | 0 | 40 | 161 | 161 | 0 |
| 19 | 199 | 199 | 0 | 41 | 110 | 91 | 19 |
| 20 | 230 | 230 | 0 | 42 | 141 | 120 | 21 |
| 21 | 108 | 108 | 0 | 43 | 304 | 131 | 173 |
| 22 | 117 | 117 | 0 | | | | |
- **불리 2700건 중 채움:** `relateLaword` 2700/2700 (**100.0%**), `illdcssBasiss` 2700/2700 (**100.0%**).
- **illdcssBasiss 샘플 2 (150자):**
  1. `매매물건에 하자가 있는 경우 매수인은 매도인에게 하자없는 물건을 청구할 수 있고, 매도인은 완전물로 급부하여야 하며, 물건인도에 소요되는 비용은 하자있는 목적물을 인도한 매도인이 부담하는 것이 신의칙에 합당하다. / 불량제품 교환시 소요되는 배송비용을 가맹점에 부담시키`
  2. `분양계약에 의하여 발생하는 일체의 의무를 분양계약의 당사자가 아닌 제3자의 지위에 있는 위탁자가 부담하는 것으로 규정함으로써 피청구인이 매도인으로서 부담해야 할 법률상,계약상 의무를 배제하고 있다.`
- **relateLaword:** 값은 약관법 조문 본문(「제6조(일반원칙)…」 등). `…법` 토큰 기준 **약관법 외 법령이 잡힌 불리 건 3/2700 = 0.11%**. 상위 10개는 법령명이 아니라 약관법 조문 앞부분(제6조 786, 제9조 380, 제8조 367, 제11조 286, 제7조 272, 제14조 198, 제10조 144, 제9조 해제 59, 제12조 48, 제9조 해제ㆍ해지 32).
- **유리 샘플 필드:** `clauseField, ftcCnclsns, clauseArticle, dvAntageous, comProvision`.
- **불리 추가 필드:** `illdcssBasiss, relateLaword, unfavorableProvision`.

### A-3 판결서

- 라벨 JSON 9000. 경로 기준 사건 종류: 민사 4273, 형사 2626, 행정 2101 (합 9000).
- **과제 유형:** 별도 NER/요약 전용 필드명은 없음. 상위 키 `info, concerned, org, disposal, mentionedItems, assrs, facts, dcss, close`. `facts.bsisFacts`, `dcss.courtDcss`, `close.cnclsns`가 사실·판단·결론 텍스트. `info.caseField` / `trailField` / `detailField`는 분류 코드. → **구조화 판결 분석(요소 분할+분류)** 로 보는 것이 맞음. 요약문 단독 라벨은 확인 필요.
- 샘플: 사건명 `손해배상(기)`, 법원 `광주고등법원`, caseField=1, trailField=2.
- 원천 XML 9000 (TS 8000 + VS 1000). XML 스키마 전수는 안 함.

### A-4 함께 제공된 AI 모델

- 019 폴더 안 모델 파일·학습 코드·성능 README: **없음**.
- 라이선스 문서: **없음** (zip만).

**상태:** 데이터 zip은 사용 가능. 분야명 코드북·제공 모델은 없음.

---

## B. AI Hub 계약서식

**위치:** WORK `data_contract\aihub_forms\` (파일 2365, JSON 2364, csv 1, 약 101.2 MB). USB 없음.

### B-1 정식 이름

- 라벨 JSON `document.type` = `계약 법률 문서`.
- 예전 리포트는 `계약 법률 문서 서식 데이터` / AI Hub 서식 zip. dataSetSn 숫자는 이 폴더 README에 **없음 → 확인 필요**.
- `label_vocab.csv` 있음 (4974 bytes).

### B-2 소분류별 문서 수

**파일명 접두 (원천+라벨 전부 2364 JSON):**

| 소분류(파일명) | 수 |
|---|---:|
| 기타고용계약서 | 758 |
| 상업용부동산임대계약서 | 638 |
| 근로계약서 | 334 |
| 채권양도계약서 | 242 |
| 채무승계계약서 | 190 |
| 주거용부동산임대계약서 | 140 |
| 아르바이트계약서 | 62 |
| 합 | 2364 |

**라벨 메타 `detail_category` (TL+VL 1182):** 기타고용계약서 379, 상업용부동산임대계약서 319, 근로(고용)계약서 167, 채권양도계약서 121, 채무승계계약서 95, 주거용부동산임대계약서 70, 아르바이트계약서 31. 합 1182. 원천 TS/VS는 이 메타가 null.

- 아르바이트계약서: **있음** (파일명 62 / 라벨메타 31).
- 근로(고용)계약서: **있음** (파일명 334 / 라벨메타 167).
- 주거용부동산임대계약서: **있음** (파일명 140 / 라벨메타 70).
- 금전소비대차(차용증)·보증 계약서 **소분류 없음**. 금전 쪽은 채권양도·채무승계만.

분할: TL 1051, TS 1051, VL 131, VS 131. JSON 파싱 성공 **2364**, HTML 0, 빈 파일 0, 깨진 JSON 0.

### B-3 문서 구조

- 라벨(TL/VL): `document.metadata.file_info` + `document.sections[]` → 각 `content.content_labels` (리스트), `content.description` (텍스트).
- 원천(TS/VS): `document.sub_documents[]` → `content_labels`, `contents[].text`. `detail_category` null.
- 라벨(TL+VL) `content_labels` 종류 **127**. 상위 30:

| 순위 | 라벨 | 빈도 | 순위 | 라벨 | 빈도 |
|---:|---|---:|---:|---|---:|
| 1 | 기타 | 9561 | 16 | 관리비 및 제세공과금 | 838 |
| 2 | 계약의 내용 | 8257 | 17 | 준거법 | 835 |
| 3 | 계약의 해제, 해지 | 4910 | 18 | 원상회복의무 | 809 |
| 4 | 손해배상의 예정 | 2429 | 19 | 관할법원 | 786 |
| 5 | 계약금의 지급 | 2037 | 20 | 계약 변경에 대한 합의 | 769 |
| 6 | 계약기간 | 1757 | 21 | 임금액 | 758 |
| 7 | 계약의 당사자 | 1495 | 22 | 면책 | 741 |
| 8 | 임차보증금 | 1398 | 23 | 담당 업무 | 732 |
| 9 | 계약서의 교부 | 1195 | 24 | 업무 수행을 위한 협조, 협의 | 732 |
| 10 | 계약의 목적 | 1177 | 25 | 금지사항 | 715 |
| 11 | 계약 체결 일자 | 1116 | 26 | 비밀 유지 | 706 |
| 12 | 통지의무 | 1093 | 27 | 대금 지급 방법 | 678 |
| 13 | 차임 | 921 | 28 | 신의성실 | 628 |
| 14 | 지적재산권 | 881 | 29 | 근로 시간 | 581 |
| 15 | 근로계약의 종료 | 878 | 30 | 양도 및 전대 금지 | 563 |

원천(TS/VS)까지 합치면 숫자 코드 라벨이 섞여 종류 327 (`inventory\B_forms.json` top30).

### B-4 조항(섹션) 수 — 라벨 파일 기준

| 유형 | 문서(라벨메타) | sections 합 | `is_article_title` true |
|---|---:|---:|---:|
| 아르바이트계약서 | 31 | 1145 | 256 |
| 근로(고용)계약서 | 167 | 8792 | 2056 |
| 주거용부동산임대계약서 | 70 | 2160 | 637 |

조항 수는 `is_article_title`이 true인 섹션. sections 합은 제목·본문·날인을 포함한 값. 원천 파일은 `sections`가 없어 이 합에 안 넣음.

### B-5 실제 값 vs 자리표시자 (`(@…)`) — 각 20문서

| 유형 | 표본 | `(@…)` 있는 문서 | 비율 | `(@…)` 합 | 금액(원) | 날짜 | 시급/임금 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 아르바이트 | 20 | 0 | 0/20 | 0 | 4 | 0 | 14 |
| 근로(고용) | 20 | 8 | 8/20 | 70 | 1 | 7 | 14 |
| 주거임대 | 20 | 2 | 2/20 | 8 | 1 | 0 | 0 |

표본은 TL 파일명 정렬 앞 20개, 텍스트는 `description`. 자리표시자 `\(@…\)`, 금액 `\d원`, 날짜 `YYYY년 M월` 또는 `YYYY-MM-DD`, 임금은 `시급|임금`. **혼합.** 자리표시자만 있는 데이터는 아님.

**상태:** 사용 가능 (JSON 2364 전부 파싱).

---

## C. 표준계약서

**위치:** WORK `data\standard_forms\` (파일 34, 2.8 MB). `standard_forms\` 루트·`data_contract\standard_forms`는 없음.

### C-1 MANIFEST.csv

행 **27** (id: L1–L6 각 1, H1–H3e 각 2=HWP+PDF, D1 2, D2 1). 열: id, 양식명, 판본, 게시일, 출처URL, 파일명, 형식, 크기, sha256, 다운로드일시, 상태, 공포일, 시행일.  
발행 기관은 열에 없고 REPORT.md 기준: 고용노동부(L), 법무부(H1·H2·H2a), 국토교통부령 별지(H3 계열), 대한법률구조공단(D). sha256은 리포트에 넣지 않음.

| id | 양식명 | 기관 | 시행·개정 | 파일명 |
|---|---|---|---|---|
| L1 | 표준근로계약서 – 단시간근로자 (2025.3 개정) | 고용노동부 | 시행일 해당 없음. 게시 2025-03-07 | `labor/L1-L3_표준근로계약서묶음(5종)_2025-03.hwp` |
| L2 | 표준근로계약서 – 기간의 정함이 있는 경우 (2025.3 개정) | 고용노동부 | 같음 | 위와 같은 hwp |
| L3 | 표준근로계약서 – 기간의 정함이 없는 경우 (2025.3 개정) | 고용노동부 | 같음 | 위와 같은 hwp |
| L4 | 표준근로계약서 – 단시간근로자 (2019판) | 고용노동부 | 게시 2019-07-01 | `labor/L4-L6_표준근로계약서묶음(7종)_2019-06.hwp` |
| L5 | 표준근로계약서 – 기간의 정함이 있는 경우 (2019판) | 고용노동부 | 같음 | 위와 같은 hwp |
| L6 | 표준근로계약서 – 기간의 정함이 없는 경우 (2019판) | 고용노동부 | 같음 | 위와 같은 hwp |
| H1 | 주택임대차표준계약서 (2023.10.6 개정, 현행) | 법무부 | 게시 2023-10-06 | `lease/H1_..._2023-10-06(사용용).hwp` |
| H1 | 같은 양식 PDF | 법무부 | 같음 | `lease/H1_..._2023-10-06(원본게시용).pdf` |
| H2 | 주택임대차표준계약서 (2022년 수정판) | 법무부 | 게시 2022-11-21 | `lease/H2_..._2022(사용용).hwp` |
| H2 | 같은 양식 PDF | 법무부 | 같음 | `lease/H2_..._2022(원본게시용).pdf` |
| H2a | 주택임대차표준계약서 (2023년 수정판, 구판) | 법무부 | 게시 2023-04-18 | `lease/H2a_..._2023-04(사용용).hwp` |
| H2a | 같은 양식 PDF | 법무부 | 같음 | `lease/H2a_..._2023-04(원본게시용).pdf` |
| H3 | 민간임대주택 표준임대차계약서 (별지 제24호, 현행) | 국토교통부령 | 공포 2025-10-31, 시행 2025-10-31. 게시 문구는 시행 2025-12-19 | `lease/H3_..._2025-10-31.hwp` |
| H3 | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3_..._2025-10-31.pdf` |
| H3a | 별지 제24호 구판 (2020-12-10 ~ 2022-01-14) | 국토교통부령 | 공포·시행 2020-12-10 | `lease/H3a_..._2020-12-10시행.hwp` |
| H3a | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3a_..._2020-12-10시행.pdf` |
| H3b | 별지 제24호 구판 (2022-01-15 ~ 2022-12-31) | 국토교통부령 | 공포 2022-01-14, 시행 2022-01-15 | `lease/H3b_..._2022-01-15시행.hwp` |
| H3b | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3b_..._2022-01-15시행.pdf` |
| H3c | 별지 제24호 구판 (2023-01-01 ~ 2023-08-02) | 국토교통부령 | 공포 2022-12-30, 시행 2023-01-01 | `lease/H3c_..._2023-01-01시행.hwp` |
| H3c | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3c_..._2023-01-01시행.pdf` |
| H3d | 별지 제24호 구판 (2023-08-03 ~ 2025-06-03) | 국토교통부령 | 공포·시행 2023-08-03 | `lease/H3d_..._2023-08-03시행.hwp` |
| H3d | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3d_..._2023-08-03시행.pdf` |
| H3e | 별지 제24호 구판 (2025-06-04 ~ 2025-10-30) | 국토교통부령 | 공포·시행 2025-06-04 | `lease/H3e_..._2025-06-04시행.hwp` |
| H3e | 같은 양식 PDF | 국토교통부령 | 같음 | `lease/H3e_..._2025-06-04시행.pdf` |
| D1 | 금전차용계약서 | 대한법률구조공단 | 시행일 해당 없음. 저장경로상 2018-07-12 | `loan/D1_금전차용계약서(KLAC서식1769)_현행.hwp` |
| D1 | 금전소비대차 계약서(지연손해금 특약) | 대한법률구조공단 | 같음 | `loan/D1_금전소비대차계약서-지연손해금특약(KLAC서식1770)_현행.hwp` |
| D2 | 보증계약서(일반) | 대한법률구조공단 | 저장경로상 2018-07-13 | `loan/D2_보증계약서-일반(KLAC서식1807)_현행.hwp` |

출처 URL (MANIFEST 원문):

| id | URL |
|---|---|
| L1–L3 | `https://www.moel.go.kr/common/downloadFile.do?file_seq=20250800411&bbs_seq=20250300356&bbs_id=29&file_ext=hwp` |
| L4–L6 | `https://www.moel.go.kr/common/downloadFile.do?file_seq=20190700012&bbs_seq=20190700008&bbs_id=29&file_ext=hwp` |
| H1 hwp | `https://www.moj.go.kr/bbs/moj/118/459549/download.do` |
| H1 pdf | `https://www.moj.go.kr/bbs/moj/118/459550/download.do` |
| H2 hwp | `https://www.moj.go.kr/bbs/moj/118/447219/download.do` |
| H2 pdf | `https://www.moj.go.kr/bbs/moj/118/447218/download.do` |
| H2a hwp | `https://www.moj.go.kr/bbs/moj/118/452787/download.do` |
| H2a pdf | `https://www.moj.go.kr/bbs/moj/118/452786/download.do` |
| H3 hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=159325997` |
| H3 pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=159325999` |
| H3a hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=88548061` |
| H3a pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=88548065` |
| H3b hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=112097915` |
| H3b pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=112097917` |
| H3c hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=123113999` |
| H3c pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=123114001` |
| H3d hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=131862343` |
| H3d pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=131862345` |
| H3e hwp | `https://www.law.go.kr/LSW/flDownload.do?flSeq=152599599` |
| H3e pdf | `https://www.law.go.kr/LSW/flDownload.do?flSeq=152599601` |
| D1 차용 | `https://support.klac.or.kr/cmm/fms/FileDown_docs.do?repositoryPath=%2FECM%2F2018%2F07%2F12%2F22%2F04%2F89b62603-1414-4294-bd6e-a09ca5ca1290&filename=%EA%B8%88%EC%A0%84%EC%B0%A8%EC%9A%A9%EA%B3%84%EC%95%BD%EC%84%9C.hwp` |
| D1 소비대차 | `https://support.klac.or.kr/cmm/fms/FileDown_docs.do?repositoryPath=%2FECM%2F2018%2F07%2F12%2F22%2F03%2Ff4d779d4-09e1-4833-9d88-e9acc6d02418&filename=%EA%B8%88%EC%A0%84%EC%86%8C%EB%B9%84%EB%8C%80%EC%B0%A8%20%EA%B3%84%EC%95%BD%EC%84%9C(%EC%A7%80%EC%97%B0%EC%86%90%ED%95%B4%EA%B8%88%20%ED%8A%B9%EC%95%BD).hwp` |
| D2 | `https://support.klac.or.kr/cmm/fms/FileDown_docs.do?repositoryPath=%2FECM%2F2018%2F07%2F13%2F14%2F09%2F95a22a5b-0674-411e-b111-454912824b5a&filename=%EB%B3%B4%EC%A6%9D%EA%B3%84%EC%95%BD%EC%84%9C(%EC%9D%BC%EB%B0%98).hwp` |

### C-2 `_extracted\`

| 파일 | 제목(첫 줄) | 글자 수 | 제N조 수 |
|---|---|---:|---:|
| L1.txt | 단시간근로자 표준근로계약서 | 2642 | 1 |
| L2.txt | 표준근로계약서(기간의 정함이 있는 경우) | 944 | 1 |
| L3.txt | 표준근로계약서(기간의 정함이 없는 경우) | 930 | 1 |
| L4.txt | 단시간근로자 표준근로계약서 | 2125 | 1 |
| L5.txt | 표준근로계약서(기간의 정함이 있는 경우) | 759 | 1 |
| L6.txt | 표준근로계약서(기간의 정함이 없는 경우) | 750 | 1 |

**H*, D* 추출 txt: 0개.** 조항 수가 1인 것은 서식이 “제N조” 형식이 아니기 때문.

### C-3 커버 유형

- 있음: 단시간 근로, 기간 정함 있음/없음 근로(2025·2019), 주택임대차 표준(여러 판), 민간임대 표준(여러 판), 금전차용/금전소비대차 서식, 보증계약서(일반).
- **없음(추출 기준):** 연소자 표준근로 단독 txt (묶음 HWP 안에는 있으나 사용하지 않음 — REPORT). 상가임대는 `_excluded`만.

### C-4 `_excluded\` (REPORT.md)

3파일: 상가건물임대차표준계약서 2026-05-12 HWP·PDF, 상가건물 임대차 권리금계약서 HWP. 범위 밖이라 MANIFEST 미수록, 삭제는 안 함.

**상태:** 원본은 사용 가능. 추출 텍스트는 L만.

---

## D. 법령 API (`data_contract\law_api\`)

위치 WORK. USB 없음. `_guide_evidence.json` 있음.

### D-1 폴더별 파일·JSON·HTML·빈 파일

| 폴더 | 파일 | json_ok | html | empty | other |
|---|---:|---:|---:|---:|---:|
| 현행 | 21 | 19 | 1 | 0 | 1 (SKIPPED_OC.txt) |
| 연혁 | 39 | 37 | 1 | 0 | 1 |
| 연혁_g3 | 24 | 12 | 12 | 0 | 0 |
| 연혁_v2_exact | 20 | 10 | 10 | 0 | 0 |
| 판례 | 117 | 116 | 0 | 0 | 1 |
| 법령해석례 | 112 | 82 | 28 | 0 | 2 |
| 공정위 | 8 | 5 | 2 | 0 | 1 |
| 법령용어 | 24 | 18 | 5 | 0 | 1 |
| 행정규칙 | 15 | 14 | 0 | 0 | 1 |

HTML에는 `<html` 또는 “권한” 포함 페이지가 섞여 있음 (폴더별 합 59). 빈 파일 0.

수집 리포트: `data_contract\DATA_READY_REPORT.md`, `FINAL_DATA_CHECK.md` (날짜 2026-10-15). 예전 PC 경로가 본문에 남아 있음.

### D-2 현행 법령

body JSON 기준 이름·시행일(파일명 `_body_MST.json`):

| 법령명 | 시행일 필드 | 조문 노드 수 |
|---|---|---:|
| 근로기준법 | 20261008 | 146 |
| 근로기준법 시행령 | 20251023 | 80 |
| 최저임금법 | 20200526 | 40 |
| 최저임금법 시행령 | 20190101 | 27 |
| 주택임대차보호법 | 20260102 | 42 |
| 주택임대차보호법 시행령 | 20260701 | 36 |
| 민법 | 20260317 | 1337 |
| 보증인 보호를 위한 특별법 | 20231221 | 11 |
| 이자제한법 | 20250722 | 8 |
| 이자제한법 제2조제1항의 최고이자율에 관한 규정 | 20210707 | 1 |

- **있음:** 근로기준법(+시행령), 최저임금법, 주택임대차보호법(+시행령), 민법, 보증인 보호법, 이자제한법.
- **없음:** 기간제법, 약관규제법, 대부업법, 고용보험법, 산재보험법.
- 조문 단위: body는 `조문번호` 등 노드로 분리됨. search JSON은 목록이라 조문 0.

### D-3 판례

- 파일 117, 목록 레코드 10921, **고유 판례일련번호 7414**.
- 400건 절단 **아님**.
- 수집 질의는 파일명에 남음: `계약갱신요구권_포기`, `근로계약_위약금`, `보증_서면`, `보증금_반환_특약`, `수습기간_임금`, `원상복구_특약`, `위약예정` 등. 별도 query 로그 파일은 없음.
- 사건명 상위 20: 요양불승인처분취소 706, 유족급여및장의비부지급처분취소 633, 임금 387, 손해배상(기) 299, 손해배상청구사건 140, 대여금 128, 구상금 89, 손해배상(자) 81, 임금등 80, 손해배상 71, 퇴직금 63, 요양급여불승인처분취소 63, 부당이득금 58, 배당이의 58, 청구이의 57, 유족급여 및 장의비… 56, 임대차보증금 53, 해고무효확인등 52, 보험금 51, 보증채무금 50. (목록 중복 포함 빈도)
- **판시사항·판결요지·전문 필드: 목록 레코드에 없음 (채움 0/10921).** 본문 PrecService 파일 0.

### D-4 법령해석례

- 파일 112, json 82, html 28.
- 목록 레코드 스캔 시 질의요지·회답·이유 키 **없음**(채움 0). 본문 파일 여부는 확인 필요(목록 스키마만 확인).

### D-5 공정위

- 자료: Open API `target=ftc` **결정문 목록**. 문서유형(행 기준): 의결서 216, 시정권고서 35.
- 파일 8 (json 5, html 2, txt 1). 검색 키워드: `임대차 약관` 2파일, `임대차계약서` 3파일.
- 목록 행 **251**, 고유 `결정문일련번호` **158**. 사건명에 `약관`이 있는 행 33, 고유 **10**.
- **이유 문장 필드 없음** (키: id, 사건번호, 결정문일련번호, 문서유형, 결정번호, 결정일자, 사건명, 회의종류, 결정문상세링크). 본문 미수집. 샘플(사건명): `경상남도개발공사의 표준임대차계약서상 불공정약관조항에 대한 건`.

### D-6 법령용어

파일 24, json 18, html 5. JSON 안의 목록 레코드 **103**. 키 예: `일상용어명`, `용어관계`, `법령용어명`. 정의 본문 필드는 없음.

### D-7 수집 리포트

- `data_contract\DATA_READY_REPORT.md` (법령 API calls_completed).
- `data_contract\FINAL_DATA_CHECK.md` (2026-10-15 10:43). 판례 unique=7414와 이번 계수 일치.

**상태:** 일부 문제 (본문·일부 법령·HTML).

---

## E. 사례집

`data_contract\cases\`. 원본 `주택임대차분쟁조정사례집.pdf` **없음**.  
`MANUAL_URL.txt`: 국토부 게시 및 PDF 다운로드 URL 2줄.  
있음: `_page_*.html`, `_p1.png`–`_p8.png`, `ocr\p001.txt`–`p101.txt`, `ocr\ALL.txt` (53777자), `s4_results.json`.  
OCR 빈 파일 다수(p003, p005, p009–011 등). 발행 기관은 URL상 법무부·국토부. 쪽수 101(파일명 기준).

**상태:** 일부 문제.

---

## F. 카탈로그

`data_contract\catalog\` **없음**. USB에도 없음.  
`catalog_v0.2.json`, `_checks.csv`, `CHANGELOG_v0.2.md` **없음**.  
checks 72 / slots 33 / law_nodes 59, category 분포, 유형별 check 수, inject_examples, unresolved L-T12·H-T06: **확인 불가 (파일 없음)**.

---

## G. 기타

### G-1 LawQA-Ko

경로 `data\datasets\LawQA-Ko\`. jsonl **14819**. 필드 `question, precedent, answer`.  
출처 README: easylaw 백문백답 + 대한법률구조공단 상담/사이버상담 병합 (HF jihye-moon). **라이선스 파일·라이선스명 없음 → 확인 필요**.  
샘플1 Q: `최저임금제도란 무엇이며, 최저임금액은 어떻게 결정되는지요?` A: `최저임금제도란 국가가 임금액의 최저한도를 정하여…`(150자 절단). precedent 빈 문자열.

### G-2 eval_aihub_ood.jsonl

- 생성: `experiments\pilot\build_sets.py` (AUDIT_RESULTS.csv에서 source==aihub).
- 건수 **35**. 필드 `audit_id, domain, 관련성, question, answer, origin_ref`.
- origin_ref 예: `TL_01. 민사법_001. 판결문_0001. 질의응답.zip::민사법_판결문_질의응답_58669.json` → **019가 아닌 ‘민사법 판결문 질의응답’ 데이터**. 해당 zip은 WORK에 **없음**.

### G-3 A–F 밖, json/jsonl/csv/txt ≥100 폴더

| 경로 | 비고 |
|---|---|
| `data_contract\aihub_forms` | B (2364 json) |
| `data_contract\law_api` | D |
| `data_contract\cases\ocr` | E OCR |
| `experiments\pilot` | jsonl 평가셋 |
| `experiments\run3` | 실험 산출 |
| `experiments\prep_contract` | 전처리 |
| `exp_gap2` | 실험 데이터/out |

`019`는 zip이라 이 기준에 안 들어감.

---

## H. 실험 결과·리포트

| 파일 | 상태 | 경로 |
|---|---|---|
| DATA_READY_REPORT.md | 있음 | `data_contract\DATA_READY_REPORT.md` |
| FINAL_DATA_CHECK.md | 있음 | `data_contract\FINAL_DATA_CHECK.md` |
| VERIFY_REPORT.md | 없음 | |
| VERIFY_CHECKS.csv | 없음 | |
| S2_REPORT.md | 없음 | |
| S2B_REPORT.md | 없음 | |
| GAP1_REPORT.md | 없음 | |
| GAP2_REPORT.md | 없음 | |
| DISTILL_AUDIT.md | 있음(다른 폴더) | `exp_gap2\distill_export\DISTILL_AUDIT.md` (`distill_audit\`에는 없음) |
| distill_audit\meta.json | 있음 | `exp_gap2\distill_audit\meta.json` |

지정 목록 기준 **있음 3 + DISTILL 경로 상이 1 / 없음 6**.

기타 있음: `experiments\pilot\PILOT_REPORT.md`, `experiments\run3\RUN3_REPORT.md`, `experiments\prep_contract\PREP_REPORT.md`, `data\standard_forms\REPORT.md`.

exp_gap2 결과:

- `e1_logprob_*.jsonl`: **없음** (스크립트 `scripts\run_e1_logprob.py`만).
- 기준선 B0–B3, K1/K5: **결과 파일 없음**.
- 근접 중복: `exp_gap2\data\e2_c5_neighbors.json` 있음 (2155631 bytes). `data\e2_c5_neighbors.json`은 없음.
- out: `8B_E2_{C2,C4,C5,R}.jsonl`, `32B_E2_{C2,C4,C5,R}.jsonl`.
- USB `D:\ai\exp_gap2`에 data 7 + out 8 동일 계열 복사.

지정 리포트 있음 3 / 없음 6.

---

## I. 모델·장비

### I-1 모델 파일 (요청 목록)

| 모델 | 이 PC | 경로·용량 |
|---|---|---|
| Qwen3-8B HF | 없음 | 예전: `data_contract\models\Qwen3-8B` (15.271 GB, 리포트 인용) |
| Qwen3-8B GGUF Q8_0 | 없음 | |
| Qwen3-32B GGUF | 없음 | 예전: `models\Qwen3-32B-GGUF\...Q6_K.gguf` |
| EXAONE-4.0-32B GGUF | 없음 | 예전 경로만 리포트에 있음 |
| KURE-v1 | 없음 | 예전 2.132 GB |
| bge-m3 | **HF 캐시** | `C:\Users\DMLAB_Server1\.cache\huggingface\hub\models--BAAI--bge-m3` **13076.5 MB**, 파일 67 |
| KLUE-RoBERTa | 이름 그대로는 없음 | |
| KoELECTRA | 없음 | |
| 법률 BERT | 없음 | |
| A.X 4.0 Light | 없음 | |
| Kanana | 없음 | |

한국어 인코더(캐시, 이름은 요청과 다름): `models--monologg--kobert` 704.3 MB, `BM-K--KoSimCSE-roberta` 845.4 MB, `jhgan--ko-sroberta-multitask` 845.4 MB, `EleutherAI--polyglot-ko-1.3b` 5275.8 MB.

WORK\models, data_contract\models, USB 루트 GGUF: **0**.

### I-2 nvidia-smi (전문)

조회 시각 2026-10-20 20:30:30.

```
Tue Oct 20 20:30:30 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 577.00                 Driver Version: 577.00         CUDA Version: 12.9     |
| GPU 0  NVIDIA GeForce RTX 4090      WDDM  |   00000000:01:00.0  On |                  Off |
|  0%   39C    P8             28W /  450W |    8419MiB /  24564MiB |     29%      Default |
+-----------------------------------------------------------------------------------------+
| Processes: PID Type Process GPU Memory
| 952 C+G StartMenuExperienceHost.exe
| 1076 C+G claude.exe
| 5248 C+G RazerAppEngine.exe
| 11824 C+G NVIDIA Overlay.exe
| 16668 C+G NVIDIA Overlay.exe
| 17260 C+G claude.exe
| 19232 C+G PaintStudio.View.exe
| 22248 C+G explorer.exe
| 22472 C+G CefSharp.BrowserSubprocess.exe
| 22664 C+G Notion.exe
| 25720 C+G SearchApp.exe
| 26648 C+G LockApp.exe
| 27632 C+G CalculatorApp.exe
| 31824 C+G msedge.exe
| 35836 C+G chrome.exe
| 36828 C+G msedgewebview2.exe
| 37440 C+G TextInputHost.exe
| 39624 C   anaconda3\envs\capstone_final\python.exe
| 40524 C+G Cursor.exe
| 44208 C+G ShellExperienceHost.exe
| 46132 C+G SystemSettings.exe
| 55004 C+G Docker Desktop.exe
| 57412 C+G SearchApp.exe
| 73868 C+G PhoneExperienceHost.exe
```

GPU 메모리 칸의 프로세스별 사용량은 전부 N/A.

### I-3 디스크·RAM

- C: 사용 1325.08 GB / 여유 **537.28 GB** / 합 1862.36 GB.
- D(USB): 사용 0.73 / 여유 56.54 / 합 57.28 GB.
- RAM: **63.92 GB** (가용 약 31.8 GB, 조회 시점).

### I-4 Python

- `C:\Users\DMLAB_Server1\anaconda3\python.exe` 3.13.5.
- torch **2.6.0+cu124**, `cuda True`, n=1.
- transformers **4.56.1**.
- **peft 없음**.
- llama-server / llama-cli: PATH **없음**.

---

## 확인 불가 목록

1. `clauseField` 숫자 → 한글 분야명 코드북 (파일 없음).
2. 판결 `caseField`/`trailField`/`detailField` 코드 의미 전수 (경로 민사·형사·행정은 전수).
3. 약관/판결 원천 XML 필드 전수.
4. 계약서식 공식 dataSetSn·라이선스 문서.
5. 해석례 본문(질의요지·회답·이유) — 목록만 확인.
6. 공정위 결정문 본문의 불공정 이유 문장. 목록 고유 결정문은 158, 사건명에 약관이 있는 고유는 10.
7. 법령용어 정의 본문. 목록 레코드는 103.
8. 카탈로그 v0.2 전부.
9. 사례집 원본 PDF·정확한 발행 정보.
10. eval_aihub_ood 원본 `질의응답.zip` (이 PC에 없음).
11. LawQA-Ko SPDX/라이선스명.
12. Qwen3-8B/32B, EXAONE GGUF, KURE-v1, A.X, Kanana, llama-server 위치 (없음).
13. GAP1/GAP2/S2/VERIFY 리포트 내용 (파일 없음).
14. e1_logprob·B0–B3·K1/K5 수치 (결과 파일 없음).
15. `민법_search.json`이 검색 히트에 `난민법`을 포함 — 목록 오염. 현행 본문은 `민법_body_MST.json`을 씀.

---

## 3장. 예전 PC 대비 누락

예전 루트 `C:\Users\DMLAB\Desktop\학부-AI서비스 개발`.

| 항목 | 예전 PC 경로 | 이 PC 상태 | 다시 받을 출처 |
|---|---|---|---|
| 계약서식 aihub_forms | `data_contract\aihub_forms` | **있음** (WORK 동일 상대경로) | AI Hub |
| 약관·판결 추출본 aihub_terms | `data_contract\aihub_terms` | 플레이스홀더만. **019 zip은 WORK 루트에 있음(미해제)** | AI Hub 019 |
| 계약서식 풀패키지(~160GB, 모델·도커) | `계약 법률 문서 서식 데이터` | **없음** | AI Hub |
| law_api | `data_contract\law_api` | **있음** (본문 미완·일부 법령 없음) | 법령 Open API |
| cases 원본 PDF | `data_contract\cases\주택임대차분쟁조정사례집.pdf` | **없음** (OCR·URL만) | 국토부 게시 URL |
| catalog | `data_contract\catalog` | **없음** | 직접 생성 |
| data_contract\models (Qwen3-8B, KURE-v1, bge-m3) | `data_contract\models\` | **없음** (bge-m3는 HF 캐시) | HF / 예전 복사 |
| models GGUF (Qwen3-32B, EXAONE-4.0-32B) | `models\...\*.gguf` | **없음** | HF GGUF |
| standard_forms | `standard_forms\` | **있음** (`data\standard_forms`) | 고용부·법무부·법령·KLAC |
| exp_gap1 | `exp_gap1\` | **있음** (WORK+USB data) | 직접 생성 |
| exp_gap2 | `exp_gap2\` | **있음** (WORK+USB) | 직접 생성 |
| 기간제법·약관규제법·대부업법·고용보험법·산재보험법 현행 | law_api 현행 | **없음** | 법령 API |
| 판례/해석례/공정위 본문 | law_api | **목록만** | 법령 API |
| GAP1_REPORT / GAP2_REPORT / S2* / VERIFY* | 리포트 | **없음** | 직접 생성 |
| 카탈로그 checks 72 | catalog_v0.2 | **없음** | 직접 생성 |
