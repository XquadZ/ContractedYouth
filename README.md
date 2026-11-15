# ContractedYouth

26-2/teamProject — 대학교 학부 프로젝트용 워크스페이스.

초기에 **법률 QA(LawQA) SLM** 실험을 했고, 이후 **대학생 계약서 분석**(알바 근로계약 / 원룸·오피스텔 임대차 / 차용·보증) 데이터·모델 준비로 전환했습니다.

## 빠른 시작

```text
docs/STRUCTURE.md          ← 폴더 용도·정션 설명
docs/experiments/          ← 일별 실험 기록
data_contract/             ← 계약 분석용 수집·검증 (현재 메인)
app_rag/                   ← 계약 검토 웹 서비스 (메인 앱)
exp_gap2/distill_export/   ← 교사(32B) reason만 (조항 원문·개인정보 제외)
freellm/                   ← FreeLLMAPI 준비 문서·클라이언트 (바이너리 제외)
experiments/               ← run3 / pilot / prep_contract
```

## 디렉터리 용도

| 경로 | 용도 |
|---|---|
| `app_rag/` | 계약 검토 서비스 (FastAPI·기준 카드·LAW_WATCH) |
| `data_contract/` | 법령 API·판례·서식·사례집 OCR·임베딩 모델·준비 리포트 |
| `exp_gap1/` / `exp_gap2/` | GAP 실험 스크립트·프롬프트·증류 export |
| `freellm/` | FreeLLMAPI HOWTO·client (앱 바이너리는 Releases에서) |
| `experiments/run3/` | LawQA SFT / QLoRA / 평가 |
| `experiments/pilot/` | 교사 모델 비교·파일럿 셋 |
| `models/` | GGUF 등 (git 제외) |
| `docs/` | README 보조 문서·실험 일지 |

## Git에 올리는 것 / 올리지 않는 것

- **포함:** 코드·프롬프트·문서, `exp_gap2/distill_export/`(교사 reason만)
- **제외:** AI Hub 원본 약관 패키지, 조항 원문·임베딩, FreeLLMAPI `.exe`/zip, API 키·`.env`·`data_local/`·모델 가중치

## 환경

- Windows, Python (Anaconda)
- 비밀값: `LAW_OC`, `HF_TOKEN`, `FREELLM_KEY` 등 **환경변수만**

## 라이선스·데이터 고지

AI Hub·국가법령정보·공정위 등 원 데이터는 각 제공처 이용약관을 따릅니다.  
이 저장소는 학부 학습·연구 목적의 정리본입니다.
