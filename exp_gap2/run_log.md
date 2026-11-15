# GAP-2 A단계 run_log

시작 시각(로컬): 2026-10-19 (재개 세션)

## 1. 실행 전 점검

### 관리자 여부
```
False
```

### nvidia-smi -pl / -lgc (원문)
```
Failed to set power management limit for GPU 00000000:01:00.0: Insufficient Permissions
Terminating early due to previous errors.
Failed to set power management limit for GPU 00000000:02:00.0: Insufficient Permissions
Terminating early due to previous errors.
The current user does not have permission to change clocks for GPU 00000000:01:00.0.
Terminating early due to previous errors.
The current user does not have permission to change clocks for GPU 00000000:02:00.0.
Terminating early due to previous errors.
```
- `-lgc` 미지원/권한 없음 → 전력 제한만으로 진행 (이미 power.limit=220W).

### 쿼리 (원문)
```
index, power.limit [W], clocks.max.sm [MHz], clocks.current.sm [MHz], temperature.gpu
0, 220.00 W, 2100 MHz, 390 MHz, 40
1, 220.00 W, 2100 MHz, 300 MHz, 35
```
→ power.limit 양쪽 220 W → 실행 게이트 통과.

### GPU 프로세스 (원문 요약)
- llama-server / 실험 python: 없음
- Display 쪽: explorer, Cursor, Edge, KakaoTalk, SearchApp 등 (C+G)
- compute apps: Insufficient Permissions로 pid 일부만 보임

### out jsonl 점검
| 파일 | lines | valid_json | unique_ids | broken |
|---|---|---|---|---|
| 32B_E2_C5.jsonl | 67 | 66 | 66 | 1 → `32B_E2_C5.jsonl.broken`으로 이동 후 good 66줄로 재기록 |
| 32B_E2_C4.jsonl | 0 | 0 | 0 | 0 |

이전 보고 건수(44/65/67) 차이:
- 44: 10/16 복구 중 중단
- 65: 10/17~19 재개 누적
- 67: 이번 크래시 직전 줄 수(그중 1줄 JSON 깨짐) → 유효 **66**

## 2. llama-server 명령줄 (GAP-1/GAP-2 원문과 동일, A단계)

```
llama-server.exe
  -m C:\Users\DMLAB\pilot_root\models\Qwen3-32B-GGUF\Qwen3-32B-Q6_K.gguf
  --host 127.0.0.1 --port 8080
  -c 8192
  -ngl 99
  -np 1
  --cache-ram 8192
  --reasoning off
  --reasoning-budget 0
  -ts 0.5,0.5
env: CUDA_VISIBLE_DEVICES=0,1
```
코드: `exp_gap1/scripts/llm_server.py::start_server` (A단계에서는 `stable=False`, cache_ram=8192)

## 3. 러너 A단계
- sleep 2초 / 요청
- append + flush + fsync
- 순서: C4 500 → C5 남은 분(~934, 목표 1000)
- thinking 안 함
- B단계(`-b/-ub`) 미적용

## 4. 100건마다 진행
(아래에 append)


## server started A-stage @ 2026-10-19T14:04:50.497077

### start C4 done=0 pending=500 total=500 @ 2026-10-19T14:04:50.513411

## GPU log path note
C:\gpu_log.csv access denied → using `exp_gap2\out\gpu_log.csv` instead.
C4 started: pending=500 @ 2026-10-19 14:04:50

- progress C4: ok=100 fail=0 file≈100 elapsed_min=10.8 mean_lat_ms_last100=4466.748077000016 gpu_max_temp=None gpu_max_power=None @ 2026-10-19T14:15:39

## A-stage interrupt (not OS crash)
- 2026-10-19 14:15: UnicodeEncodeError on progress log (U+2248). C4 saved n=100/500. Fixed ascii; resuming.


## server started A-stage @ 2026-10-19T14:16:38.151538

### start C4 done=100 pending=400 total=500 @ 2026-10-19T14:16:38.178750
- progress C4: ok=100 fail=0 file_n=200 elapsed_min=10.6 mean_lat_ms_last100=4363.852973000016 gpu_max_temp=78.0 gpu_max_power=191.4 @ 2026-10-19T14:27:16
- progress C4: ok=200 fail=0 file_n=300 elapsed_min=21.7 mean_lat_ms_last100=4602.818979999988 gpu_max_temp=79.0 gpu_max_power=180.16 @ 2026-10-19T14:38:20
- progress C4: ok=300 fail=0 file_n=400 elapsed_min=32.7 mean_lat_ms_last100=4557.508269000018 gpu_max_temp=80.0 gpu_max_power=188.65 @ 2026-10-19T14:49:20
- progress C4: ok=400 fail=0 file_n=500 elapsed_min=43.8 mean_lat_ms_last100=4590.544754000057 gpu_max_temp=80.0 gpu_max_power=187.1 @ 2026-10-19T15:00:23

### end C4: {"cond": "C4", "n_ok": 400, "n_fail": 0, "file_n": 500, "setting": "A"}

### start C5 done=66 pending=934 total=1000 @ 2026-10-19T15:00:25.638374
- progress C5: ok=100 fail=0 file_n=166 elapsed_min=12.1 mean_lat_ms_last100=5228.3792000000085 gpu_max_temp=83.0 gpu_max_power=186.45 @ 2026-10-19T15:12:30
- progress C5: ok=200 fail=0 file_n=266 elapsed_min=24.6 mean_lat_ms_last100=5491.647794 gpu_max_temp=84.0 gpu_max_power=190.99 @ 2026-10-19T15:25:03

## C4 integrity @ 2026-10-19T15:26:46
```json
{
  "lines": 500,
  "valid_json": 500,
  "unique_ids": 500,
  "dup_ids": [],
  "n_dup_ids": 0,
  "missing": [],
  "extra": [],
  "parse_fail_first": 0,
  "broken_lines": 0
}
```
Scoring rule: if duplicate id, use FIRST record only.

## C4 score (table C)
- 8B top1: 51.2% [46.6, 55.6] (n=500)
- 32B top1: 62.0% [57.6, 66.0] (n=500)
- 32B-8B: 10.8% [6.2, 15.6] (n=500) -> 갭 있음
- random baseline: 33.3%
- setting: A; n=500; first_record_only for dups
```json
{
  "n_gold": 500,
  "8B_top1": {
    "mean": 0.512,
    "lo": 0.466,
    "hi": 0.556,
    "n": 500
  },
  "32B_top1": {
    "mean": 0.62,
    "lo": 0.576,
    "hi": 0.66,
    "n": 500
  },
  "8B_any_hit": {
    "mean": 0.512,
    "lo": 0.466,
    "hi": 0.556,
    "n": 500
  },
  "32B_any_hit": {
    "mean": 0.62,
    "lo": 0.576,
    "hi": 0.66,
    "n": 500
  },
  "diff_32_8_top1": {
    "mean": 0.108,
    "lo": 0.062,
    "hi": 0.156,
    "n": 500
  },
  "gap_label": "갭 있음",
  "random_baseline": 0.333,
  "setting": "A",
  "dup_rule": "first_record_only",
  "code": "exp_gap2/scripts/c4_verify_and_score.py"
}
```

## Encoding harden (diff summary)
- resume_a_stage.py / new scripts: PYTHONUTF8=1, PYTHONIOENCODING=utf-8
- console logs ASCII only; progress_log wrapped try/except
- C4 finished early by previous runner; requests stopped for cooldown; C5 paused at n~276
- C4 score: 8B top1 51.2% [46.6,55.6]; 32B 62.0% [57.6,66.0]; diff +10.8pp [6.2,15.6] gap yes; random 33.3%; setting A; n=500; no dups/missing/parse_fail


## Cooldown 15min START @ 2026-10-19T15:27:34
```
index, temperature.gpu, power.draw [W], power.limit [W], clocks.current.sm [MHz]
0, 68, 32.83 W, 220.00 W, 375 MHz
1, 63, 12.34 W, 220.00 W, 300 MHz
```

## C4 GPU stats from gpu_log (14:04:50-15:00:30)
rows=3266
GPU0 maxT=80.0 meanT=74.1 maxP=191.40 lim95_rate=0.000 n=1633
GPU1 maxT=75.0 meanT=69.4 maxP=187.10 lim95_rate=0.000 n=1633

## Cooldown 15min END @ 2026-10-19T15:42:34
```
index, temperature.gpu, power.draw [W], power.limit [W], clocks.current.sm [MHz]
0, 46, 30.83 W, 220.00 W, 390 MHz
1, 41, 9.06 W, 220.00 W, 300 MHz
```

## C5 start after cooldown + clock lock
- user: clock lock done
- cooldown: 2026-10-19T15:27:34 -> 2026-10-19T15:42:34
- C5 resume from n=276

```
index, power.limit [W], clocks.max.sm [MHz], clocks.current.sm [MHz], temperature.gpu
0, 220.00 W, 2100 MHz, 390 MHz, 46
1, 220.00 W, 2100 MHz, 300 MHz, 40

```


## C5 resume precheck @ 2026-10-19T15:42:56
```
index, power.limit [W], clocks.max.sm [MHz], clocks.current.sm [MHz], temperature.gpu
0, 220.00 W, 2100 MHz, 390 MHz, 46
1, 220.00 W, 2100 MHz, 300 MHz, 41

```

### C5 resume done=276 pending=724
