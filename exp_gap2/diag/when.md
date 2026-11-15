# GAP-2 diag [A] When (조회만, 원문 근거)

조회 시각: 2026-10-19 (세션). 32B 중지 후 수행. out\ 미수정.

## 1. NVIDIA 드라이버 버전·설치 날짜

### nvidia-smi (원문 발췌)
```
Driver Version: 560.94
CUDA Version: 12.6
```
전체: `diag/nvidia_smi_full.txt`

### Win32_PnPSignedDriver (원문)
```
DeviceName    : NVIDIA TITAN RTX
DriverVersion : 32.0.15.6094
DriverDate    : 2024-08-14 오전 9:00:00
InfName       : oem22.inf
```
(동일 내용 GPU×2). 파일: `diag/nvidia_driver_raw.txt`  
참고: DriverDate는 드라이버 패키지 날짜(2024-08-14). 이 PC에 설치된 날짜와 다를 수 있음.

### Uninstall 레지스트리 InstallDate (원문)
```
DisplayName    : NVIDIA 그래픽 드라이버 560.94
DisplayVersion : 560.94
InstallDate    : 20260930
Publisher      : NVIDIA Corporation

DisplayName    : NVIDIA Install Application
DisplayVersion : 2.1002.438.0
InstallDate    : 20260930
```
→ 이 PC 설치일: **2026-09-30**. 파일: `diag/nvidia_uninstall_entries.txt`

## 2. 2026-10-10 ~ 10-19 Windows Update·드라이버 업데이트

### Windows Update Client (Id 19/43/44) — 원문 파일 `diag/wu_oct10_19.txt`
해당 기간에 기록된 설치 성공(Id=19)은 대부분 **Microsoft Defender 보안 인텔리전스(KB2267602)** 및:
- 2026-10-15: Defender 플랫폼 KB4052623
- 2026-10-14: 악성 소프트웨어 제거 도구 KB890830
- 2026-10-10: Microsoft Store(9WZDNCRFJBMP)

**NVIDIA 그래픽 드라이버 업데이트 기록은 이 구간 WU 로그에 없음.**  
(드라이버 InstallDate 20260930은 이 구간 이전.)

### Setup 로그
`diag/setup_oct10_19.txt` (조회 결과 별도 저장).

## 3. 안정성/하드웨어 오류·비정상 종료 — 최초 날짜(조회 범위 내)

### Kernel-Power Id=41 (비정상 종료 후 부팅) — `diag/kernel_power_41.txt`
조회된 가장 오래된 항목(MaxEvents 50 범위):
```
2025-06-04 10:36:00 Id=41 ...
```
(그 이전은 이 조회 한도에 없음.)

### BugCheck (WER 1001) — `diag/bugcheck.txt`
조회된 가장 오래된 BugCheck:
```
2025-09-09 00:35:24 BugCheck ... 0x00000119 ...
```
최근 반복 BugCheck **0x00000133** (DPC_WATCHDOG), 예:
```
2026-10-19 15:49:25 BugCheck ... 0x00000133 ...
2026-10-19 13:26:45 BugCheck ... 0x00000133 ...
2026-10-16 16:59:02 BugCheck ... 0x00000133 ...
2026-10-12 05:06:07 BugCheck ... 0x00000133 ...
```

### WHEA-Logger — `diag/whea.txt`
조회된 가장 오래된 Id=1 (하드웨어 오류):
```
2025-09-16 02:03:58 WHEA Id=1 ...
```
(수정된 오류 Id=19는 더 이전에도 다수.)

### 오늘(진단 직전) 추가 크래시
```
LastBootUpTime: 2026-10-19 15:48:27
2026-10-19 15:48:35 Id=41
2026-10-19 15:48:56 Id=6008 ... 오후 3:47:05 예기치 않은 종료 ...
2026-10-19 15:49:25 BugCheck 0x00000133
```
→ C5 재개(15:42~, n≈276) 직후 구간에서 또 강제 재부팅. 중지 시점 C5 줄 수 **299** (out 조회, 삭제 없음).

## 4. GAP-1 실행 기간 중 Kernel-Power 41 여부

### GAP-1 out 파일 mtime (근거)
```
exp_gap1/out *.jsonl LastWriteTime Min=2026-10-15 17:06:26 Max=2026-10-15 19:59:26
```
→ GAP-1 LLM 본실행 산출 시각대: **2026-10-15 오후**.

### 해당일 Kernel-Power 41
`diag/kernel_power_41.txt`에서 **2026-10-15 항목 없음**.

Oct 12에는 KP41 있음(03:54, 05:05)이나, GAP-1 out mtime 기준 본실행 구간(10/15)과는 날짜가 다름.

**결론(사실만):** GAP-1 out이 찍힌 **2026-10-15**에는 Kernel-Power 41 기록이 **없다**.

---
원문 덤프 파일: `nvidia_driver_raw.txt`, `nvidia_smi_full.txt`, `nvidia_uninstall_entries.txt`, `wu_oct10_19.txt`, `kernel_power_41.txt`, `event_6008.txt`, `bugcheck.txt`, `whea.txt`, `system_critical_60d.txt`
