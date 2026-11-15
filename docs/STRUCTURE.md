# 폴더 구조 (용도별)

ROOT = `학부-AI서비스 개발`

기존 스크립트의 절대경로(`...\run3`, `...\data_contract` 등)가 깨지지 않도록,  
**실제 내용은 용도별 폴더로 옮기고** 예전 경로에는 Windows **디렉터리 정션(junction)** 을 남겨 두었습니다.

## 트리

```
학부-AI서비스 개발/
├── README.md
├── .gitignore
├── docs/                      # 문서·실험 일지·아카이브
│   ├── experiments/           # 일별 실험 기록 (md)
│   ├── archive/               # 루트에 있던 감사/프롬프트 등
│   ├── papers/                # 관련 논문
│   └── STRUCTURE.md
├── experiments/               # 실험 코드·산출물
│   ├── run3/                  # LawQA SFT/QLoRA/평가
│   ├── pilot/                 # 교사 모델 비교·파일럿 셋
│   └── prep_contract/         # 계약 분석 준비 T1–T4
├── data/                      # 데이터 원본·표준서식
│   ├── standard_forms/
│   ├── datasets/
│   ├── aihub_full_package/    # AI Hub ~160GB 풀패키지
│   └── data_contract/         # → ../data_contract 정션
├── data_contract/             # 계약 분석용 수집·검증 (현재 메인)
├── models/                    # GGUF·로컬 LLM 가중치
├── tools/                     # llama.cpp, 카탈로그 스크립트 등
└── scripts/                   # 루트 유틸 (폴더 정리 등)
```

## 정션 목록 (예전 이름 → 실제 위치)

| 예전/별칭 경로 | 실제 경로 |
|---|---|
| `run3/` | `experiments/run3/` |
| `pilot/` | `experiments/pilot/` |
| `prep_contract/` | `experiments/prep_contract/` |
| `standard_forms/` | `data/standard_forms/` |
| `datasets/` | `data/datasets/` |
| `계약 법률 문서 서식 데이터/` | `data/aihub_full_package/` |
| `관련 논문/` | `docs/papers/관련논문/` |
| `data/data_contract/` | `data_contract/` |

## 용도 한눈에

| 용도 | 위치 |
|---|---|
| 계약서 분석 데이터 준비 | `data_contract/` |
| LawQA SLM 실험 | `experiments/run3/` |
| 교사/파일럿 | `experiments/pilot/` |
| 계약 준비 측정 | `experiments/prep_contract/` |
| 표준계약서 | `data/standard_forms/` |
| 공개 데이터셋 zip | `data/datasets/` |
| 거대 모델 가중치 | `models/`, `data_contract/models/` |
| 실험 일지 | `docs/experiments/` |
