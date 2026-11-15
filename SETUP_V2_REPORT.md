# SETUP_V2_REPORT

작성: 2026-10-20. 기존 데이터 파일은 수정·삭제하지 않음. 새 파일은 지정 경로에만 생성.

| 단계 | 결과 | 근거 |
|---|---|---|
| 카탈로그 복구 | 대기 | `WORK\_incoming\restore_pack.zip` 없음. 해시·개수 미실행 |
| 019 압축 해제 | 성공 | 약관 라벨 JSON 9000 (유리 6300 / 불리 2700). 판결 라벨 JSON 9000 |
| 분야 코드북 | 코드북 없음 | zip 안 xlsx/pdf/hwp 0. `reports_restored\` 없음 |
| 표준계약서 추출 | 21/27 | L1–L6 기존 유지. 신규 중 H3 계열 hwp 6개만 실패(표 표시 36자). pdf·나머지 hwp 성공 |
| 계약서식 인덱스 | 알바 62 / 근로 334 / 주거 140 | 자리표시자 문자 비율 평균 0 / 0.019925 / 0.008384 |
| 법령 보충 | 성공 0 / 실패 0 (건너뜀) | 프로세스 환경변수 `OPEN_LAW_KEY` 길이 0 |
| 판례 본문 | 0/4 | 같은 이유로 API 호출 안 함 |
| 모델 다운로드 | HF 5종 + GGUF 2종 | Qwen·A.X Apache-2.0, KURE·bge MIT, KLUE 카드에 라이선스 문장 없음 |
| llama.cpp | 성공 | 태그 b11755, commit 704366d76, `version: 0.7.0-dev (build 11755)`. 짧은 응답 1건 |
| GPU 100건 연속 | 100/100, 오류 0 | 최고 온도 50 C, 최고 전력 222.37 W. 두 번째 100건 동안 측정 |

---

## 1. 복구 묶음

`WORK\_incoming` 폴더가 없다. `restore_pack.zip` 없음. 이 단계만 대기. 카탈로그 검증(SHA-256 `a2781f407358d0366b660c1923dcde6be3f301fa3b691f11cba386be33e9267b`, checks 72, slots 33, law_nodes 59, LAB_PT 30, LAB_FX 28, LEASE 27, LOAN 15, inject_examples 28)은 파일이 없어 실행하지 않음.

## 2. 데이터 풀기·정리

### 2-1. 019 압축 해제

원본 zip은 `019.법률, 규정 (판결서, 약관 등) 텍스트 분석 데이터\`에 그대로 둠. 해제 위치 `data_local\aihub019\<zip 이름>\`.

```
EXTRACTED TL_1.판결문.zip json=8000 xml=0 bytes_zip=32410769
EXTRACTED TL_2.약관.zip json=8000 xml=0 bytes_zip=7826110
EXTRACTED TS_1.판결문.zip json=0 xml=8000 bytes_zip=49340464
EXTRACTED TS_2.약관.zip json=0 xml=8000 bytes_zip=57030570
EXTRACTED VL_1.판결문.zip json=1000 xml=0 bytes_zip=4056301
EXTRACTED VL_2.약관.zip json=1000 xml=0 bytes_zip=929148
EXTRACTED VS_1.판결문.zip json=0 xml=1000 bytes_zip=6089786
EXTRACTED VS_2.약관.zip json=0 xml=1000 bytes_zip=6602212
DONE 8
```

해제본 재집계: 약관 라벨 JSON `docs 9000 broken 0 dv {'1': 6300, '2': 2700} clause_items 10200`. 판결 라벨 JSON `judgment_json 9000`.

`.gitignore`에 `data_local/` 추가함.

### 2-2. 분야 코드북

019 zip 멤버 확장자 전수에 xlsx, pdf, hwp, txt, md, csv, docx는 0건(json 18000, xml 18000, 디렉터리 항목). `reports_restored\` 없음(복구 zip 대기). clauseField 숫자 코드를 분야명으로 바꾸지 않음. **코드북 없음.**

### 2-3. 표준계약서 추출

도구: `hwp5txt` (pyhwp 0.1b15), pdf는 pdfplumber 0.11.10. L1.txt–L6.txt는 수정하지 않음. 새 파일은 `data\standard_forms\_extracted\<원본이름>.hwp.txt` 또는 `.pdf.txt`.

MANIFEST 27행 기준 텍스트 확보 21, 실패 6.

| 행 | 유형 | 결과 |
|---|---|---|
| L1–L6 | 근로·단시간 | 기존 txt 유지. 성공 |
| H1, H2, H2a hwp·pdf 각 1 | 주택임대 | 성공 |
| H3, H3a–H3e hwp 6 | 주택임대(민간) | 실패. hwp5txt 결과가 `<표>`만, 36자, 제N조 0 |
| H3, H3a–H3e pdf 6 | 주택임대(민간) | 성공. 글자 8358–9874, 제N조 고유 26 |
| D1 차용·소비대차, D2 보증 | 차용·보증 | 성공 |
| 연소자 | 근로(연소) | 단독 원본 행은 없음. 묶음 hwp 추출본에 `연소근로자` 문구가 있음 |

신규 추출 앞 150자(줄바꿈은 ` / `):

| 파일 | 유형 | 글자 | 제N조 | 성공 | 앞 150자 |
|---|---|---:|---:|---|---|
| H1 사용용 hwp | 주택임대 | 2438 | 12 | 성공 | `<그림> … 주택임대차표준계약서 … 제2조(임대차기간) 임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는 상태로 년` |
| H1 pdf | 주택임대 | 7611 | 14 | 성공 | `이 계약서는 법무부가 국토교통부·서울시 및 관련 전문가들과 함께 민법, 주택임대차보호법, 공인중개사법 등 관계법령에 근거하여 만들었습니다.` |
| H2 사용용 hwp | 주택임대 | 2437 | 12 | 성공 | H1 hwp와 같은 형태의 본문 시작. `제2조(임대차기간)` |
| H2 pdf | 주택임대 | 7207 | 14 | 성공 | H1 pdf와 같은 첫 문장 |
| H2a 사용용 hwp | 주택임대 | 2437 | 12 | 성공 | `제2조(임대차기간)` 포함 |
| H2a pdf | 주택임대 | 7608 | 15 | 성공 | H1 pdf와 같은 첫 문장 |
| H3–H3e hwp 6개 | 주택임대 | 36 | 0 | 실패 | `<표>` 반복 |
| H3 pdf | 주택임대 | 9874 | 26 | 성공 | `■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2025. 10. 31.> 표준임대차계약서` |
| H3a pdf | 주택임대 | 8358 | 26 | 성공 | 같은 서식, `<개정 2020. 12. 10.>` |
| H3b pdf | 주택임대 | 9098 | 26 | 성공 | `<개정 2022. 1. 14.>` |
| H3c pdf | 주택임대 | 9307 | 26 | 성공 | `<개정 2022. 12. 30.>` |
| H3d pdf | 주택임대 | 9506 | 26 | 성공 | `<개정 2023. 8. 3.>` |
| H3e pdf | 주택임대 | 9869 | 26 | 성공 | `<개정 2025. 6. 4.>` |
| D1 소비대차 hwp | 차용 | 627 | 4 | 성공 | `[서식 예] 금전소비대차 계약서(지연손해금 특약) … 차용금원 금 ○○○원 … 제1조(대여일시)` |
| D1 차용 hwp | 차용 | 621 | 5 | 성공 | `[서식 예] 금전차용계약서 … 제1조(당사자)` |
| D2 보증 hwp | 보증 | 457 | 3 | 성공 | `[서식 예] 보증계약서(일반) … 제1조(계약의 목적)` |
| L1–L3 묶음 hwp | 근로·단시간·연소자 | 7351 | 2 | 성공 | `(이하 “사업주”라 함)과(와) … 다음과 같이 근로계약을 체결한다.` 본문에 `연소근로자` |
| L4–L6 묶음 hwp | 근로·단시간·연소자 | 6319 | 2 | 성공 | 같은 시작. 본문에 `연소근로자` |

제N조 수는 고유 번호 개수. 근로 서식은 조 번호가 거의 없어 2이다.

### 2-4. 계약서식 인덱스

`data_local\forms_index.csv` 536행. 파싱 실패 0. 라벨 메타(`detail_category`)가 있는 행은 각 유형의 절반(TL+VL). 원천(TS+VS)은 0.

| 유형 | 문서 | 라벨 메타 있음 | `(@…)` 있는 문서 | 문자 비율 평균 |
|---|---:|---:|---:|---:|
| 아르바이트 | 62 | 31 | 0 | 0 |
| 근로(고용) | 334 | 167 | 252 | 0.019925 |
| 주거용부동산임대 | 140 | 70 | 32 | 0.008384 |

비율 = `\(@[^)]*\)`에 들어간 글자 수 / 본문 글자 수. 조항 수는 라벨 파일의 `is_article_title == true` 개수(열 `n_article`).

## 3. 법령 보충

프로세스 환경변수 `OPEN_LAW_KEY`가 비어 있음(길이 0). 지시에 따라 법령 API와 판례 본문 API를 호출하지 않음. 기존 스크립트는 `LAW_OC`를 읽도록 되어 있으나, 이번 지시는 `OPEN_LAW_KEY`만 사용하라고 하므로 그 이름으로 읽지 않음.

받을 예정이었던 법령: 기간제 및 단시간근로자 보호 등에 관한 법률과 시행령, 약관의 규제에 관한 법률, 고용보험법, 산업재해보상보험법. 판례 4건: 94다34692, 2023다249661, 80다320, 80다321. 저장 예정 경로는 `law_api\현행\`, `law_api\판례_본문\`.

이 환경에 `OPEN_LAW_KEY`를 넣은 뒤 다시 실행해야 한다.

## 4. 모델·추론

다운로드 경로 `data_local\models\`. 32B는 받지 않음.

| 모델 | repo | 파일 수 | 바이트 | config model_type |
|---|---|---:|---:|---|
| KLUE RoBERTa base | `klue/roberta-base` | 19 | 886334048 | roberta |
| KLUE RoBERTa large | `klue/roberta-large` | 19 | 2694748629 | roberta |
| KURE-v1 | `nlpai-lab/KURE-v1` | 27 | 2288776381 | xlm-roberta |
| A.X 4.0 Light | `skt/A.X-4.0-Light` | 33 | 14532309855 | qwen2 |
| Qwen3-8B | `Qwen/Qwen3-8B` | 31 | 16397462968 | qwen3 |
| bge-m3 | 캐시만 | 67 | 13711693785 | 경로 `C:\Users\DMLAB_Server1\.cache\huggingface\hub\models--BAAI--bge-m3` |

요청한 repo id가 모두 존재해서 다른 id로 바꾸지 않음. `skt/A.X-4.0-Light` 확인됨.

GGUF Q8_0 (`convert_hf_to_gguf.py`, llama.cpp b11755, `--outtype q8_0`):

```
INFO:hf-to-gguf:Model successfully exported to ...\Qwen3-8B-Q8_0.gguf
```

파일 8709518784 바이트. 변환 로그의 total_size = 8.7G.

```
INFO:hf-to-gguf:Model successfully exported to ...\A.X-4.0-Light-Q8_0.gguf
```

파일 7719171936 바이트. 아키텍처는 qwen2라 변환이 끝남.

### 라이선스 원문

- Qwen3-8B 카드: `license: apache-2.0`, `license_link: https://huggingface.co/Qwen/Qwen3-8B/blob/main/LICENSE`. LICENSE 파일 11343바이트, SHA-256 `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`. 첫머리:

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/
```

전문은 `data_local\models\licenses\Qwen__Qwen3-8B\LICENSE`.

- A.X 4.0 Light 카드 README: `The A.X 4.0 Light model is licensed under Apache License 2.0.` 앞머리 `license: apache-2.0`. LICENSE 13019바이트, SHA-256 `0d4b6e74abfb37024fba6f841f6b637d5570c3bf00d2dd2c3181dda4b313ae46`. 전문은 `data_local\models\licenses\skt__A.X-4.0-Light\LICENSE`. Qwen LICENSE와 바이트가 달라 같은 파일로 보지 않음.

- KURE-v1 카드: `- **License:** MIT`. LICENSE 파일은 404.

- bge-m3 카드 앞머리: `license: mit`. LICENSE 파일은 404. 가중치는 캐시에 이미 있음.

- KLUE RoBERTa base·large 카드 README(각 1369, 1372바이트)에는 license 문장이 없다. `https://raw.githubusercontent.com/KLUE-benchmark/KLUE/main/LICENSE` 와 `master/LICENSE` 는 HTTP 404. **모델 카드에 라이선스 원문 없음.**

### llama.cpp

다운로드: `llama-b11755-bin-win-cuda-12.4-x64.zip` 271944966 바이트. 경로 `data_local\llama.cpp\b11755\llama-server.exe`. 소스 `data_local\llama.cpp\src\llama.cpp-b11755\` (변환 스크립트).

```
version: 0.7.0-dev (build 11755, commit 704366d76)
built with Clang 20.1.8 for Windows x86_64
```

서버: `llama-server.exe -m Qwen3-8B-Q8_0.gguf --host 127.0.0.1 --port 18080 -c 512 -ngl 99`. `GET /health` → `{"status":"ok"}`.

짧은 요청 1건 (`n_predict` 32, temperature 0, 프롬프트 `안녕하세요. 한 문장으로만 답하세요.`):

```
content  다음은 어떤 문장인지 분류하세요. "이 영화는 정말 재미있었어요. 저는 영화를 보는 것을 좋아해요."
tokens_predicted 32
```

응답은 옴. 측정 후 서버 프로세스는 종료함.

### Python

기존 Anaconda `C:\Users\DMLAB_Server1\anaconda3\python.exe` 3.13.5에 없는 패키지를 설치함. 별도 conda 환경은 만들지 않음. torch CUDA가 이 환경에 이미 있었기 때문이다.

```
torch 2.6.0+cu124
transformers 4.56.1
peft 0.21.2
sentence-transformers 5.1.0
scikit-learn 1.7.2
pdfplumber 0.11.10
pyhwp 0.1b15
cuda True cuda_ver 12.4 gpu NVIDIA GeForce RTX 4090
```

pdfplumber 설치가 pillow를 11.1.0에서 13.0.0으로 올렸다. pip 경고: `streamlit 1.45.1 requires pillow<12`. 실험 코드 파일은 바꾸지 않음.

### GPU 100건

1차 `nvidia-smi -f` 로그 파일은 프로세스가 켜진 동안 0바이트였다. 2차로 `nvidia-smi --query-gpu=timestamp,temperature.gpu,power.draw,utilization.gpu,memory.used --format=csv -l 2` 를 표준출력에 남기고 요청 100건을 다시 보냈다.

```
DONE ok=100 fail=0 sec=30.0
```

로그 18행. 온도 38–50 C, 전력 28.42–222.37 W. 최고 온도 **50**, 최고 전력 **222.37 W**. 오류 행 없음. 메모리 약 16688–16777 MiB. 원문은 `data_local\gpu_qwen8b_100.csv`. GPU가 멈추는 증상은 이 100건에서 보이지 않음.

## 5. 예전 PC에서만 가져올 것

이 PC에서 찾지 못한 항목:

- `exp_gap2\GAP2_REPORT.md`
- `exp_gap2\out\e1_logprob_*.jsonl` (스크립트 `exp_gap2\scripts\run_e1_logprob.py`만 있음)
- 기준선 B0–B3, K1/K5 결과 파일
- 근접 중복 점검 결과 리포트. `exp_gap2\data\e2_c5_neighbors.json` (2155631 바이트)는 있음
- `exp_gap1\out\` 18개 jsonl: 폴더 없음
- (선택) `models\Qwen3-32B-Q6_K.gguf`: 받지 않음
