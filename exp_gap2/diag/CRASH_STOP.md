# CRASH / GPU LOST — STOP (no auto-restart)

detected_at: 2026-10-19T16:07:13
LastBootUpTime: 2026-10-19T15:48:27
phase: [B] 8B Q8_0 CUDA_VISIBLE_DEVICES=0
n_done: 0 / 100
last_id: (none — failed during model load / health wait)
status: GPU0 lost (nvidia-smi exit; handle lost for 00000000:01:00.0)
display_gpu: 0 (monitor was on GPU0)
GPU1_run: NOT STARTED (stopped after GPU0 failure per no-auto-restart)
action: STOPPED. Reboot required to recover GPU. Do not resume automatically.

## nvidia-smi (원문)
```
Unable to determine the device handle for GPU0000:01:00.0: GPU is lost.  Reboot the system to recover this GPU



```
