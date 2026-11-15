# Git 커밋·푸시 안내

Git for Windows가 설치되어 있습니다:  
`C:\Program Files\Git\cmd\git.exe`

## 로컬 커밋 (이미 준비된 경우)

```bat
set PATH=C:\Program Files\Git\cmd;%PATH%
cd /d "C:\Users\DMLAB\Desktop\학부-AI서비스 개발"
git status
git log -1 --oneline
```

## 원격 푸시 (최초)

1. GitHub/GitLab 등에서 빈 저장소 생성  
2. 아래 실행 (URL만 교체):

```bat
set PATH=C:\Program Files\Git\cmd;%PATH%
cd /d "C:\Users\DMLAB\Desktop\학부-AI서비스 개발"
git remote add origin https://github.com/<USER>/<REPO>.git
git branch -M main
git push -u origin main
```

SSH를 쓰면 `git@github.com:<USER>/<REPO>.git` 형태.

## 제외되는 것 (.gitignore)

- `models/`, GGUF·safetensors, AI Hub 풀패키지  
- 판례/해석례 **본문** 대량 JSON, OCR png, 도구 zip  
- 루트 정션 폴더(중복 방지) — 실체는 `experiments/`, `data/` 쪽만 추적
