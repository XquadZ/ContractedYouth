# 제공사 가입·키 발급 목록 (사용자 직접 등록)

카탈로그 참고: https://freellmapi.co/models · README Supported providers  
약관 칸은 **빈칸**. 사용자가 확인 후 채우거나 원문 인용.

**우선 추천(★)** = 문서상 오픈 웨이트 대형(≥70B 또는 MoE 총≥100B) 무료 엔드포인트 확인된 곳.

| 우선 | 제공사 | 가입 | 키 발급 | 무료 한도(문서 원문·요약) | ≥70B/MoE≥100B 예 | 이용약관 URL | 데이터사용정책 URL | 입력→학습? | 출력→타모델학습 제한? |
|---|---|---|---|---|---|---|---|---|---|
| ★ | Groq | https://console.groq.com | https://console.groq.com/keys | `openai/gpt-oss-120b`: RPM 30, RPD 1K, TPM 8K, TPD 200K (console.groq.com/docs/rate-limits 표) | gpt-oss-120b (120B) | https://groq.com/terms-of-use/ | https://groq.com/privacy-policy/ | _(빈칸)_ | _(빈칸)_ |
| ★ | Cerebras | https://cloud.cerebras.ai | Cloud Console → API keys | Free Trial: `$5` 크레딧·결제수단 필요·30일. `gpt-oss-120b` Free Trial: RPM 5, uncached TPM 30K, TPH/TPD 1M (inference-docs.cerebras.ai/support/rate-limits). 영구 free tier 없음(동일 FAQ). | gpt-oss-120b | https://www.cerebras.ai/terms-of-service | https://www.cerebras.ai/privacy-policy | _(빈칸)_ | _(빈칸)_ |
| ★ | OpenRouter (free) | https://openrouter.ai | https://openrouter.ai/keys | 모델별 `:free` 엔드포인트. 한도는 모델/계정 페이지 표기(변동). 카탈로그: openrouter.ai/models | 예: 문서·카탈로그의 `*:free` 대형 오픈웨이트(가입 후 `/v1/models`로 확정) | https://openrouter.ai/terms | https://openrouter.ai/privacy | _(빈칸)_ | _(빈칸)_ |
| ★ | NVIDIA NIM / build | https://build.nvidia.com | API key 페이지(콘솔) | 무료 크레딧·모델별 한도(콘솔 Limits). freellmapi 카탈로그에 NVIDIA 항목 있음 | 카탈로그의 대형 오픈웨이트(가입 후 확정) | https://www.nvidia.com/en-us/about-nvidia/terms-of-service/ | https://www.nvidia.com/en-us/about-nvidia/privacy-policy/ | _(빈칸)_ | _(빈칸)_ |
| ★ | Cloudflare Workers AI | https://dash.cloudflare.com | Workers AI / API Tokens | Workers AI 무료 한도는 Cloudflare 요금제·모델 문서 기준(변동). 카탈로그에 Workers AI 다수 | 예: `@cf/qwen/qwen3.8-27b` 등은 27B(대형70B 미만 — 후보 재확인 필요) | https://www.cloudflare.com/website-terms/ | https://www.cloudflare.com/privacypolicy/ | _(빈칸)_ | _(빈칸)_ |
| ★ | Hugging Face (Inference) | https://huggingface.co/join | https://huggingface.co/settings/tokens | Serverless/Inference Providers 무료 한도는 HF 문서·계정별(변동) | Hub의 대형 오픈웨이트 + Inference 제공 시 | https://huggingface.co/terms-of-service | https://huggingface.co/privacy | _(빈칸)_ | _(빈칸)_ |
| | Google AI Studio | https://aistudio.google.com | API key | 무료 쿼터는 Google AI Studio 문서·콘솔 기준 | Gemini 계열(클로즈드 웨이트 다수) | https://policies.google.com/terms | https://policies.google.com/privacy | _(빈칸)_ | _(빈칸)_ |
| | Mistral | https://console.mistral.ai | API keys | 무료/시험 한도는 콘솔 | 오픈 웨이트 모델 제공 시 문서 확인 | https://mistral.ai/terms | https://mistral.ai/terms#privacy-policy | _(빈칸)_ | _(빈칸)_ |
| | Cohere | https://dashboard.cohere.com | API keys | Trial 한도 콘솔 | Command 계열 등 | https://cohere.com/terms-of-use | https://cohere.com/privacy | _(빈칸)_ | _(빈칸)_ |
| | Z.ai (Zhipu) | https://z.ai 또는 open.bigmodel.cn | API key | 무료 쿼터 문서·콘솔 | GLM 대형(오픈/클로즈 혼재 — 문서 확인) | 사이트 Terms | 사이트 Privacy | _(빈칸)_ | _(빈칸)_ |

## 대시보드에 넣을 때
1. FreeLLMAPI 실행 중인지 확인: `http://127.0.0.1:31415`
2. **Keys** 페이지에서 위 제공사 키 추가
3. 통합 키(Copy Key)를 사용자 PC 환경변수 `FREELLM_KEY`에만 저장 (채팅에 붙이지 말 것)
4. 끝나면 채팅에 **「등록했어」** 라고만 답하면 5장(모델 목록)·6장(연결 시험)으로 진행한다.

## 사용자가 약관에서 확인할 두 항목
1. **입력 데이터를 제공사 학습에 사용하는가**
2. **출력을 다른 모델 학습에 쓰는 것을 제한하는가**
