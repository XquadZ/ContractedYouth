# FreeLLMAPI README 요약 (Install / Limitations / Disclaimer)

출처: https://github.com/tashfeenahmed/freellmapi (조회 시점 tag **v0.16.5**)

## Install (요약)
- 권장: Docker one-liner / Compose → 기본 `http://localhost:3001`
- Windows: Releases의 **Setup `.exe`** 또는 **portable `-win.zip`**
- 대안: Node 20+ 로 소스 `npm run dev`
- `ENCRYPTION_KEY`: Docker/소스 설치 시 `openssl rand -hex 32` 또는 PowerShell RNG로 생성 후 `.env`에 저장. Desktop 앱은 키 미설정 시 `%APPDATA%\FreeLLMAPI\.encryption-key`에 로컬 키 자동 생성(로그에 값 미출력).
- 대시보드 Keys 페이지에 제공사 키 등록 → 통합 `freellmapi-…` 키로 OpenAI 호환 `/v1` 사용.
- 카탈로그: freellmapi.co 서명 피드 자동 동기화(무료 설치는 monthly snapshot).

## Limitations (요약)
- 프론티어 모델 없음, 지연 가변, SLA 없음.
- 하루 후반에 상위 모델 일일 한도 소진 시 체감 성능 저하 → UTC 자정에 리셋.
- 상세: docs/en/architecture/#limitations

## Disclaimer (요약)
- **개인 실험·학습용. 프로덕션 아님.**
- 실서비스 전 유료 API로 교체할 것.
- 각 업스트림 제공사 약관은 계정 생성 시 동의한 그대로 적용되며, 이 프록시를 거쳐도 준수 책임은 사용자에게 있음.
