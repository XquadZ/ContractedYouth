# [B] 단일 GPU 8B 진단 결과

## 모니터 연결 GPU
- **GPU 0** (`00000000:01:00.0`, Disp.A=On)
- GPU 1 Disp.A=Off
- 원문: `display_gpu.txt`, `display_monitor.md`

## GPU0 실행 (CUDA_VISIBLE_DEVICES=0)
- 모델: Qwen3-8B-Q8_0, llama-server, C5 프롬프트 test1000 앞 100건
- 시작 전 60초 대기: 적용 (16:03:34 → 서버 기동 ~16:04:36)
- **결과: GPU lost — 완료 0/100**
- 시점: 모델 로드/health 대기 중 (프롬프트 0건)
- nvidia-smi 원문: `Unable to determine the device handle for GPU0000:01:00.0: GPU is lost. Reboot the system to recover this GPU`
- 최고 온도/전력: 프롬프트 구간 미진입 → 요약 null (`b_gpu0_summary.json`)
- gpu_log(2초): `diag/gpu_log.csv` (로드 직전까지 기록)

## GPU1 실행
- **미시작** (GPU0 lost 후 자동 재시작·연속 실행 금지)

## 중지 기록
- `CRASH_STOP.md`, `b_gpu0_state.json` (status=GPU_LOST_STOP)
- LastBootUpTime at stop: 2026-10-19T15:48:27 (이번 GPU lost는 OS 재부팅 없이 발생)
- out\ 파일 미수정
