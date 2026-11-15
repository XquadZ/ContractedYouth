# Display / monitor GPU

조회 명령 원문 (`nvidia-smi --query-gpu=index,name,display_mode,display_active,pci.bus_id --format=csv`):

(파일 `display_gpu.txt`에 저장)

nvidia-smi 요약:
- GPU **0** (`00000000:01:00.0`): Disp.A = **On**, 디스플레이/데스크톱 프로세스(Cursor, explorer, Edge 등)가 이 GPU에 상주.
- GPU **1** (`00000000:02:00.0`): Disp.A = **Off**, 메모리 사용 0.

→ 모니터/디스플레이가 연결된 GPU 번호: **0**
