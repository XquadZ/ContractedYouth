# FOLLOWUP — run3 미확인 항목 확인 (근거만)

판정·해석 없음. 근거 없으면 미확인.

## 1. 양자화·학습 설정

### 1-1. BitsAndBytesConfig
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/train_qlora.py 줄 47-52)
```
  47|         bnb = BitsAndBytesConfig(
  48|             load_in_4bit=True,
  49|             bnb_4bit_quant_type="nf4",
  50|             bnb_4bit_use_double_quant=True,
  51|             bnb_4bit_compute_dtype=torch.float16,
  52|         )
```

### 1-2. 모델 로드 from_pretrained
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/train_qlora.py 줄 57-66)
```
  57|         model = AutoModelForCausalLM.from_pretrained(
  58|             BASE_MODEL,
  59|             quantization_config=bnb,
  60|             device_map="auto",
  61|             dtype=torch.float16,
  62|             trust_remote_code=True,
  63|         )
  64|         model = prepare_model_for_kbit_training(model)
  65|         model.gradient_checkpointing_enable()
  66|         model.config.use_cache = False
```

### 1-3. LoRA config
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/train_qlora.py 줄 68-76)
```
  68|         lora = LoraConfig(
  69|             r=16,
  70|             lora_alpha=32,
  71|             lora_dropout=0.05,
  72|             bias="none",
  73|             task_type="CAUSAL_LM",
  74|             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
  75|         )
  76|         model = get_peft_model(model, lora)
```

### 1-4. loss 마스킹 (assistant 토큰만)
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/train_qlora.py 줄 103-133)
```
 103|         def encode_row(ex):
 104|             messages = ex["messages"]
 105|             text = tokenizer.apply_chat_template(
 106|                 messages, tokenize=False, add_generation_prompt=False
 107|             )
 108|             tok = tokenizer(
 109|                 text,
 110|                 truncation=True,
 111|                 max_length=2048,
 112|                 padding=False,
 113|                 return_tensors=None,
 114|             )
 115|             input_ids = tok["input_ids"]
 116|             labels = list(input_ids)
 117|             # mask everything before assistant content
 118|             full = tokenizer.apply_chat_template(
 119|                 messages, tokenize=False, add_generation_prompt=False
 120|             )
 121|             # find last assistant marker
 122|             idx = full.rfind(marker)
 123|             if idx >= 0:
 124|                 prefix = full[: idx + len(marker)]
 125|                 prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
 126|                 n_mask = min(len(prefix_ids), len(labels))
 127|                 for i in range(n_mask):
 128|                     labels[i] = -100
 129|             else:
 130|                 # fallback: mask first half
 131|                 for i in range(len(labels) // 2):
 132|                     labels[i] = -100
 133|             return {"input_ids": input_ids, "attention_mask": tok["attention_mask"], "labels": labels}
```

### 1-5. TrainingArguments
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/train_qlora.py 줄 151-188)
```
 151|         # transformers 5.x: warmup_ratio removed from TrainingArguments in some builds
 152|         n_train = max(len(train_rows), 1)
 153|         steps_per_epoch = max(1, (n_train + 16 - 1) // 16)  # batch1 * grad_accum16
 154|         total_steps = steps_per_epoch * (2 if max_steps <= 0 else 1)
 155|         if max_steps > 0:
 156|             total_steps = max_steps
 157|         warmup_steps = max(1, int(total_steps * 0.03))
 158| 
 159|         ta_kwargs = dict(
 160|             output_dir=str(out_dir / "checkpoints"),
 161|             num_train_epochs=2 if max_steps <= 0 else 1,
 162|             max_steps=max_steps if max_steps > 0 else -1,
 163|             per_device_train_batch_size=1,
 164|             per_device_eval_batch_size=1,
 165|             gradient_accumulation_steps=16,
 166|             learning_rate=2e-4,
 167|             lr_scheduler_type="cosine",
 168|             warmup_steps=warmup_steps,
 169|             logging_steps=10 if max_steps <= 0 else 1,
 170|             save_strategy="epoch" if max_steps <= 0 else "no",
 171|             fp16=True,
 172|             bf16=False,
 173|             optim="paged_adamw_8bit",
 174|             report_to=[],
 175|             seed=SEED,
 176|             gradient_checkpointing=True,
 177|             remove_unused_columns=False,
 178|             dataloader_pin_memory=False,
 179|         )
 180|         # eval strategy key differs across versions
 181|         eval_val = "epoch" if eval_ds is not None and max_steps <= 0 else "no"
 182|         try:
 183|             args_tr = TrainingArguments(**ta_kwargs, eval_strategy=eval_val)
 184|         except TypeError:
 185|             try:
 186|                 args_tr = TrainingArguments(**ta_kwargs, evaluation_strategy=eval_val)
 187|             except TypeError:
 188|                 args_tr = TrainingArguments(**ta_kwargs)
```

### 1-6. 실행 로그에 남은 설정값

#### adapter_B/train_meta.json
```json
{
  "side": "B",
  "base_model": "C:\\Users\\DMLAB\\pilot_root\\models\\Qwen2.5-14B-Instruct",
  "gpu": "0",
  "max_steps": 0,
  "train_n": 834,
  "val_n": 44,
  "torch": "2.9.1+cu126",
  "cuda": "12.6",
  "model_revision": "C:\\Users\\DMLAB\\pilot_root\\models\\Qwen2.5-14B-Instruct",
  "transformers_model_type": "qwen2"
}
```

#### adapter_C/train_meta.json
```json
{
  "side": "C",
  "base_model": "C:\\Users\\DMLAB\\pilot_root\\models\\Qwen2.5-14B-Instruct",
  "gpu": "1",
  "max_steps": 0,
  "train_n": 834,
  "val_n": 44,
  "torch": "2.9.1+cu126",
  "cuda": "12.6",
  "model_revision": "C:\\Users\\DMLAB\\pilot_root\\models\\Qwen2.5-14B-Instruct",
  "transformers_model_type": "qwen2"
}
```

#### adapter_B trainer_state (latest) 일부 필드
```json
{
  "logging_steps": 10,
  "max_steps": 106,
  "num_train_epochs": 2,
  "train_batch_size": 1,
  "save_steps": 500
}
```
- path: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\adapter_B\checkpoints\checkpoint-53\trainer_state.json`

#### adapter_C trainer_state (latest) 일부 필드
```json
{
  "logging_steps": 10,
  "max_steps": 106,
  "num_train_epochs": 2,
  "train_batch_size": 1,
  "save_steps": 500
}
```
- path: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\adapter_C\checkpoints\checkpoint-53\trainer_state.json`

#### train_*_console.log 에서 키워드 검색 결과
- load_in_4bit / bnb_4bit_quant_type / bnb_4bit_compute_dtype / fp16·bf16 설정 문자열: 미확인 (해당 키워드 로그 줄 없음)

#### train_B_console.log 학습 중 learning_rate 로그 예시 (원문)
- {'loss': '1.518', 'grad_norm': '0.2971', 'learning_rate': '0.0001983', 'epoch': '0.1918'}
- {'loss': '1.347', 'grad_norm': '0.237', 'learning_rate': '0.0001883', 'epoch': '0.3837'}
- {'loss': '1.322', 'grad_norm': '0.2223', 'learning_rate': '0.0001702', 'epoch': '0.5755'}

참고: `max_length=2048` 은 encode_row 토크나이저 호출에 있음 (위 1-4 발췌).

## 2. 첫 본 실행(01:36) 중단 / 두 번째(12:57) resume 여부

### 2-1. progress.log 전문 (해당 구간 포함)
```
﻿[2026-10-12 01:36:56] === run_all BEGIN pid=1868 ===
[2026-10-12 01:36:56] START 3-1_select :: python select_items.py
[2026-10-12 01:36:59] END 3-1_select exit=0 elapsed_sec=2.9
[2026-10-12 01:36:59] START 3-2_teacher :: python gen_teacher.py
[2026-10-12 12:57:22] === run_all BEGIN pid=11856 ===
[2026-10-12 12:57:22] START 3-1_select :: python select_items.py
[2026-10-12 12:57:25] END 3-1_select exit=0 elapsed_sec=3.1
[2026-10-12 12:57:25] START 3-2_teacher :: python gen_teacher.py
[2026-10-12 15:28:10] END 3-2_teacher exit=0 elapsed_sec=9044.7
[2026-10-12 15:28:12] START 3-3_build_sft :: python build_sft.py
[2026-10-12 15:28:25] END 3-3_build_sft exit=0 elapsed_sec=13.8
[2026-10-12 15:28:25] START 3-4_train :: python train_qlora.py --force
[2026-10-12 16:45:26] END 3-4_train exit=0 elapsed_sec=4620.7
[2026-10-12 16:45:26] START 3-5_eval :: python gen_eval.py
[2026-10-12 19:11:34] END 3-5_eval exit=0 elapsed_sec=8767.4
[2026-10-12 19:11:34] === run_all END ===
[2026-10-12 19:11:34] appended results to RUN3_REPORT.md
```

### 2-2. finish_smoke_and_run.log (01:36 전후)
```
﻿[2026-10-12 01:03:54] BEGIN wait for C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct\DOWNLOAD_OK.txt
[2026-10-12 01:03:54] waiting download shards_GB=3.01
[2026-10-12 01:04:54] waiting download shards_GB=4.27
[2026-10-12 01:05:54] waiting download shards_GB=5.51
[2026-10-12 01:06:54] waiting download shards_GB=6.37
[2026-10-12 01:07:54] waiting download shards_GB=7.16
[2026-10-12 01:08:54] waiting download shards_GB=7.92
[2026-10-12 01:09:54] waiting download shards_GB=8.71
[2026-10-12 01:10:54] waiting download shards_GB=9.50
[2026-10-12 01:11:54] waiting download shards_GB=10.29
[2026-10-12 01:12:54] waiting download shards_GB=11.06
[2026-10-12 01:13:54] waiting download shards_GB=11.85
[2026-10-12 01:14:54] waiting download shards_GB=12.64
[2026-10-12 01:15:54] waiting download shards_GB=13.43
[2026-10-12 01:16:54] waiting download shards_GB=14.20
[2026-10-12 01:17:54] waiting download shards_GB=14.99
[2026-10-12 01:18:54] waiting download shards_GB=15.78
[2026-10-12 01:19:54] waiting download shards_GB=16.58
[2026-10-12 01:20:54] waiting download shards_GB=17.34
[2026-10-12 01:21:54] waiting download shards_GB=18.13
[2026-10-12 01:22:54] waiting download shards_GB=18.92
[2026-10-12 01:23:54] waiting download shards_GB=19.71
[2026-10-12 01:24:54] waiting download shards_GB=20.47
[2026-10-12 01:25:54] waiting download shards_GB=21.26
[2026-10-12 01:26:54] waiting download shards_GB=22.05
[2026-10-12 01:27:54] waiting download shards_GB=22.84
[2026-10-12 01:28:54] waiting download shards_GB=23.61
[2026-10-12 01:29:54] waiting download shards_GB=24.40
[2026-10-12 01:30:54] waiting download shards_GB=25.19
[2026-10-12 01:31:54] waiting download shards_GB=25.98
[2026-10-12 01:32:54] waiting download shards_GB=26.75
[2026-10-12 01:33:54] download marker present
[2026-10-12 01:34:05] START smoke 3-4 train 5 steps
[2026-10-12 01:35:17] END smoke 3-4 exit=1 sec=72.1
[2026-10-12 01:35:17] START smoke 3-5 eval 2
[2026-10-12 01:36:56] END smoke 3-5 exit=0 sec=98.8
[2026-10-12 01:36:56] SMOKE DONE {"finished_at":"2026-10-12 01:36:56","train_exit":1,"eval_exit":0,"smoke_dir":"C:\\Users\\DMLAB\\pilot_root\\run3\\smoke"}
[2026-10-12 01:36:56] START full run_all
```

### 2-3. run_all.log
미확인 (`run3/run_all.log` 파일 없음)

### 2-4. run_all_console.log
```
[2026-10-12 12:57:22] === run_all BEGIN pid=11856 ===
[2026-10-12 12:57:22] START 3-1_select :: python select_items.py
[2026-10-12 12:57:25] END 3-1_select exit=0 elapsed_sec=3.1
[2026-10-12 12:57:25] START 3-2_teacher :: python gen_teacher.py
[2026-10-12 15:28:10] END 3-2_teacher exit=0 elapsed_sec=9044.7
[2026-10-12 15:28:12] START 3-3_build_sft :: python build_sft.py
[2026-10-12 15:28:25] END 3-3_build_sft exit=0 elapsed_sec=13.8
[2026-10-12 15:28:25] START 3-4_train :: python train_qlora.py --force
[2026-10-12 16:45:26] END 3-4_train exit=0 elapsed_sec=4620.7
[2026-10-12 16:45:26] START 3-5_eval :: python gen_eval.py
[2026-10-12 19:11:34] END 3-5_eval exit=0 elapsed_sec=8767.4
[2026-10-12 19:11:34] === run_all END ===
[2026-10-12 19:11:34] appended results to RUN3_REPORT.md
```

### 2-5. hf_download_progress.log (끝부분)
```
[2026-10-12 01:15:58] done exit=0 size=3995328080 model-00003-of-00008.safetensors
[2026-10-12 01:15:58] GET model-00004-of-00008.safetensors have=247926784 need>=3900000000
[2026-10-12 01:20:24] done exit=0 size=3995338432 model-00004-of-00008.safetensors
[2026-10-12 01:20:24] GET model-00005-of-00008.safetensors have=765329408 need>=3900000000
[2026-10-12 01:24:14] done exit=0 size=3979624824 model-00005-of-00008.safetensors
[2026-10-12 01:24:14] GET model-00006-of-00008.safetensors have=502362112 need>=3900000000
[2026-10-12 01:28:23] done exit=0 size=3995328080 model-00006-of-00008.safetensors
[2026-10-12 01:28:23] GET model-00007-of-00008.safetensors have=767344640 need>=3900000000
[2026-10-12 01:32:13] done exit=0 size=3995328080 model-00007-of-00008.safetensors
[2026-10-12 01:32:13] GET model-00008-of-00008.safetensors have=315031552 need>=1600000000
[2026-10-12 01:33:52] done exit=0 size=1698703696 model-00008-of-00008.safetensors
[2026-10-12 01:33:52] DONE C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct
```

### 2-6. gen_teacher resume 관련 로그 (`done=`/`todo=`)
미확인 (보존된 로그에 `items=... done=... todo=...` 줄 없음. `run_all_console.log`는 12:57 재시작 시점부터만 존재)

### 2-7. teacher_outputs.jsonl 파일 시각·건수
- path: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\teacher_outputs.jsonl`
- st_ctime: 2026-10-12 01:42:00
- st_mtime: 2026-10-12 15:28:05
- line count: 898
- first id: R0001
- id at index 430: R0430
- id at index 431: R0431
- last id: R0898
- ids == R0001..R{n:04d} contiguous: True

### 2-8. OS LastBootUpTime (재시작 시각)
- LastBootUpTime: 2026-10-12 05:05:03

### 2-9. progress.log 상 3-2 소요와 건수 관계 (숫자만)
- 두 번째 실행 `END 3-2_teacher ... elapsed_sec=9044.7` (progress.log 원문 위 2-1)
- 9044.7 / 22 ≈ 411.1 (가정 초/건 22는 계산용; 로그 평균 아님)
- 898 * 22 = 19756
- 468 * 22 = 10296
- gen_teacher.py resume 코드:
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/gen_teacher.py 줄 141-146)
```
 141|     items = load_jsonl(args.items)
 142|     if args.limit and args.limit > 0:
 143|         items = items[: args.limit]
 144|     done = existing_ids(args.out, "id")
 145|     todo = [r for r in items if str(r["id"]) not in done]
 146|     log(f"items={len(items)} done={len(done)} todo={len(todo)}")
```

첫 실행 중단의 직접 원인 문자열이 로그에 있는지: progress.log에 01:36 START 3-2 이후 END 없이 12:57 BEGIN이 이어짐. 중단 원인 문자열(예: reboot/killed) 로그 원문: 미확인

## 3. 스모크 3-4 / 3-5 실행 여부

### 3-1. finish_smoke_and_run.log 원문
```
[2026-10-12 01:34:05] START smoke 3-4 train 5 steps
[2026-10-12 01:35:17] END smoke 3-4 exit=1 sec=72.1
[2026-10-12 01:35:17] START smoke 3-5 eval 2
[2026-10-12 01:36:56] END smoke 3-5 exit=0 sec=98.8
[2026-10-12 01:36:56] SMOKE DONE {"finished_at":"2026-10-12 01:36:56","train_exit":1,"eval_exit":0,"smoke_dir":"C:\\Users\\DMLAB\\pilot_root\\run3\\smoke"}
```

### 3-2. smoke_summary.json
```json
﻿{
    "finished_at":  "2026-10-12 01:36:56",
    "train_exit":  1,
    "eval_exit":  0,
    "smoke_dir":  "C:\\Users\\DMLAB\\pilot_root\\run3\\smoke"
}
```

### 3-3. smoke/adapter_B/ERROR.txt 원문
```
train_failed: TypeError: TrainingArguments.__init__() got an unexpected keyword argument 'warmup_ratio'
Traceback (most recent call last):
  File "C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\train_qlora.py", line 151, in train_one
    args_tr = TrainingArguments(
TypeError: TrainingArguments.__init__() got an unexpected keyword argument 'warmup_ratio'
```

### 3-4. smoke 평가 산출물 건수
- `eval_outputs.jsonl`: 2
- `eval_outputs_A.jsonl`: 2
- `eval_outputs_B.jsonl`: 파일없음
- `eval_outputs_C.jsonl`: 파일없음

### 3-5. smoke/gen_eval_A_console.log 끝부분
```
Loading weights:  92%|█████████▏| 532/579 [00:32<00:02, 19.43it/s]
Loading weights:  92%|█████████▏| 535/579 [00:32<00:02, 15.70it/s]
Loading weights:  93%|█████████▎| 540/579 [00:32<00:02, 19.49it/s]
Loading weights:  94%|█████████▍| 544/579 [00:32<00:01, 19.93it/s]
Loading weights:  94%|█████████▍| 547/579 [00:33<00:02, 15.32it/s]
Loading weights:  95%|█████████▌| 552/579 [00:33<00:01, 19.15it/s]
Loading weights:  96%|█████████▌| 556/579 [00:33<00:01, 19.77it/s]
Loading weights:  97%|█████████▋| 559/579 [00:33<00:01, 15.04it/s]
Loading weights:  97%|█████████▋| 564/579 [00:34<00:00, 18.88it/s]
Loading weights:  98%|█████████▊| 568/579 [00:34<00:00, 18.18it/s]
Loading weights:  99%|█████████▊| 571/579 [00:34<00:00, 14.97it/s]
Loading weights:  99%|█████████▉| 576/579 [00:34<00:00, 18.60it/s]
Loading weights: 100%|██████████| 579/579 [00:34<00:00, 16.62it/s]
[A] base only
[A] todo=2

eval_A:   0%|          | 0/2 [00:00<?, ?q/s]
eval_A:  50%|#####     | 1/2 [00:23<00:23, 23.21s/q]
eval_A: 100%|##########| 2/2 [00:50<00:00, 25.65s/q]
eval_A: 100%|##########| 2/2 [00:50<00:00, 25.28s/q]
```

### 3-6. run3/smoke/ 파일 목록과 크기
- `_chk.txt`	247 bytes
- `_eval_items_all.json`	2475 bytes
- `adapter_B/ERROR.txt`	369 bytes
- `adapter_C/ERROR.txt`	369 bytes
- `build_sft_report.json`	257 bytes
- `EVAL_COMPARE.md`	4868 bytes
- `eval_outputs.jsonl`	4867 bytes
- `eval_outputs_A.jsonl`	4867 bytes
- `final_ids.txt`	21 bytes
- `gen_eval_A_console.log`	11748 bytes
- `items.jsonl`	2069307 bytes
- `llama_server_teacher.log`	4626 bytes
- `nvidia_smi_after_teacher.txt`	55 bytes
- `sft_B.jsonl`	8618 bytes
- `sft_C.jsonl`	5863 bytes
- `teacher_outputs.jsonl`	11480 bytes
- `train_B_console.log`	14213 bytes
- `train_C_console.log`	14346 bytes

## 4. 학습·평가 입력 형식

### 4-1. sft_B.jsonl 첫 2건
#### B row 1
```json
{
  "id": "R0001",
  "domain": "고용",
  "split": "train",
  "messages": [
    {
      "role": "system",
      "content": "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
    },
    {
      "role": "user",
      "content": "甲·乙·丙은 사용자 丁으로부터 3인의 임금합계액으로 액면금 600만원인 약속어음 1매를 교부받아 戊로부터 각자의 몫의 금액으로 나눈 여러 매의 약속어음으로 할인 받았으나, 丁으로부터 교부받은 최초의 어음이 지급거절 되었습니다. 이 경우 위 3인은 戊에 대하여 600만원의 채무전액을 부담하지 않고, 각자 자기 몫으로 받은 어음금액상당의 채무만 부담할 수는 없는지요?"
    },
    {
      "role": "assistant",
      "content": "여러 명이 관련된 채권관계에 관하여 민법에서 채권자나 채무자가 수인인 경우에 특별한 의사표시가 없으면 각 채권자 또는 각 채무자는 균등한 비율로 권리가 있고 의무를 부담한다고 규정하고 있으며(민법 제408조), 채권의 목적이 그 성질 또는 당사자의 의사표시에 의하여 불가분인 경우에 채권자가 수인인 때에는 각 채권자는 모든 채권자를 위하여 이행을 청구할 수 있고, 채무자는 모든 채권자를 위하여 각 채권자에게 이행할 수 있다고 규정하고 있습니다(민법 제409조). 그리고 민법상 다수당사자의 채권관계에 관한 판례를 보면, 민법상 다수당사자의 채권관계는 원칙적으로 분할채권관계이고, 채권의 성질상 또는 당사자약정에 기초하여 특히 불가분으로 하는 경우에 한하여 불가분채권관계로 되는 것이라고 하였습니다(대법원 1992. 10. 27. 선고 90다13628 판결).그런데 위 사안과 같이 수인이 그 임금합계액으로 발행받은 1매의 어음을 각자 받을 몫의 임금액으로 나눈 여러 매의 어음으로 할인받은 경우 그 채권관계가 분할채권관계인지 불가분채권관계인지 문제되는데 이에 관하여 판례를 보면, 금전소비대차에 있어 수인의 채무자가 각기 일정한 돈을 빌리는 경우에 특별한 의사표시가 없으면 이 채무는 분할채무라 할 것이고, 이러한 특별한 의사표시가 있거나 채권목적이 그 성질상 불가분인 경우에 한하여 불가분채권이 성립되는 것이며, 이러한 법리는 수인의 채무자가 채무전부를 각자 이행할 의무가 있는 경우에도 또한 같다고 할 것이므로, 수인의 골재운송업자들이 그 운임합계액으로 소외회사로부터 약속어음 1매를 발행 받아 그 어음을 각자 받을 몫의 금액으로 나눈 여러 매의 어음으로 할인 받은 것이라면 위 소비대차관계는 그 성질상 불가분채무 또는 연대채무라고 볼 수 없어 당사자간에 특별한 의사표시가 없는 한 채무자 각자가 각각 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만 지는 분할채무라고 함이 상당하다고 하였습니다(대법원 1985. 4. 23. 선고 84다카2159 판결).따라서 위 사안의 경우 甲·乙·丙은 戊에 대하여 각자 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만을 진다고 할 수 있을 것으로 보입니다."
    }
  ]
}
```
#### B row 2
```json
{
  "id": "R0002",
  "domain": "계약",
  "split": "train",
  "messages": [
    {
      "role": "system",
      "content": "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
    },
    {
      "role": "user",
      "content": "저는 A에게 건물을 임대하였는데, A가 차임을 3년 이상 연체하였습니다. 제가 A에게 차임 연체를 이유로 계약을 해지하면서 미지급 월차임 및 차임상당 부당이득금 청구소송을 제기하자, A는 소 제기일로부터 소급하여 3년 이전에 발생한 월차임 지급채권은 소멸시효가 완성되어 소멸하였다고 주장하고 있는데, 소멸시효가 완성된 월차임을 보증금에서 공제하고 지급할 수는 없는 것인지요."
    },
    {
      "role": "assistant",
      "content": "임대차보증금이 임대인에게 교부되어 있더라도 임대인은 임대차관계가 계속되고 있는 동안에는 그 임대차보증금에서 연체차임을 충당할 것인지 여부를 자유로이 선택할 수 있으므로(대법원 2005. 5. 12. 선고 2005다459, 466 판결 등 참조), 임대차계약 종료 전에는 연체차임이 공제 등의 별도의 의사표시 없이 임대차보증금에서 당연히 공제되는 것이 아닙니다(대법원 2013. 2. 28. 선고 2011다49608 판결 등 참조). 월차임 지급채권은 민법 제163조 제1호가 정한 1년 이내의 기간으로 정한 금전의 지급을 목적으로 한 채권에 해당하여 3년의 단기소멸시효가 적용되므로, 소 제기일로부터 소급하여 3년 이전에 발생한 월차임 지급채권은 소멸시효가 완성된 것으로 보입니다. 그런데 판례에 의하면, 임대차보증금은 차임의 미지급, 목적물의 멸실이나 훼손 등 임대차 관계에서 발생할 수 있는 임차인의 모든 채무를 담보하는 것이므로, 차임의 지급이 연체되면 장차 임대차 관계가 종료되었을 때 임대차보증금으로 충당될 것으로 생각하는 것이 당사자의 일반적인 의사이고, 임대차보증금의 액수가 차임에 비해 상당히 큰 금액인 경우가 많은 우리 사회의 실정에 비추어 보면, 차임 지급채무가 상당기간 연체되고 있음에도, 임대인이 임대차계약을 해지하지 아니하고 임차인도 연체차임에 대한 담보가 충분하다는 것에 의지하여 임대차관계를 지속하는 경우에는, 임대인과 임차인 모두 차임채권이 소멸시효와 상관없이 임대차보증금에 의하여 담보되는 것으로 신뢰하고, 나아가 장차 임대차보증금에서 충당 공제되는 것을 용인하겠다는 묵시적 의사를 가지고 있는 것이 일반적이라고 할 수 있습니다. 따라서 임대차 존속 중 차임이 연체되고 있음에도 임대차보증금에서 연체차임을 충당하지 않고 있었던 임대인의 신뢰와 차임연체 상태에서 임대차관계를 지속해 온 임차인의 묵시적 의사를 감안하면 연체차임은 민법 제495조의 유추적용에 의하여 임대차보증금에서 공제할 수 있다고 할 것입니다(대법원 2016. 11. 25. 선고 2016다211309 판결)."
    }
  ]
}
```

### 4-2. sft_C.jsonl 첫 2건
#### C row 1
```json
{
  "id": "R0001",
  "domain": "고용",
  "split": "train",
  "messages": [
    {
      "role": "system",
      "content": "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
    },
    {
      "role": "user",
      "content": "甲·乙·丙은 사용자 丁으로부터 3인의 임금합계액으로 액면금 600만원인 약속어음 1매를 교부받아 戊로부터 각자의 몫의 금액으로 나눈 여러 매의 약속어음으로 할인 받았으나, 丁으로부터 교부받은 최초의 어음이 지급거절 되었습니다. 이 경우 위 3인은 戊에 대하여 600만원의 채무전액을 부담하지 않고, 각자 자기 몫으로 받은 어음금액상당의 채무만 부담할 수는 없는지요?"
    },
    {
      "role": "assistant",
      "content": "1. 🔍 핵심 쟁점: 甲·乙·丙이 戊에게 600만원 전액을 갚아야 하는지, 아니면 각자 받은 어음 금액만큼만 책임지는지가 문제입니다.\n\n2. 📜 관련 법 원칙: 여러 사람이 채무자일 때, 특별한 약정이 없으면 각자가 자기 몫만큼만 책임집니다(민법 제408조). 채권이 분할될 수 있다면, 채무도 분할됩니다.\n\n3. 💡 이유:  \n1. 甲·乙·丙은 丁으로부터 받은 600만원 어음을 나누어 각자 할인받았습니다.  \n2. 이는 각자가 받은 금액만큼만 빌린 것으로 보이며, 특별한 약정이 없으므로 분할채무로 봅니다.  \n3. 판례(대법원 1985. 4. 23. 84다카2159)에 따르면, 이런 경우 각자가 자기 몫의 채무만 부담합니다.\n\n4. 📝 이렇게 하세요: 甲·乙·丙은 각자 받은 어음 금액만큼만 戊에게 책임지면 됩니다.\n\n구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."
    }
  ]
}
```
#### C row 2
```json
{
  "id": "R0002",
  "domain": "계약",
  "split": "train",
  "messages": [
    {
      "role": "system",
      "content": "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
    },
    {
      "role": "user",
      "content": "저는 A에게 건물을 임대하였는데, A가 차임을 3년 이상 연체하였습니다. 제가 A에게 차임 연체를 이유로 계약을 해지하면서 미지급 월차임 및 차임상당 부당이득금 청구소송을 제기하자, A는 소 제기일로부터 소급하여 3년 이전에 발생한 월차임 지급채권은 소멸시효가 완성되어 소멸하였다고 주장하고 있는데, 소멸시효가 완성된 월차임을 보증금에서 공제하고 지급할 수는 없는 것인지요."
    },
    {
      "role": "assistant",
      "content": "1. 🔍 핵심 쟁점: A가 3년 이상 차임을 안 내자 소송을 냈는데, A는 일부 차임이 소멸시효가 지났다고 주장하고 있다. 보증금에서 이 금액을 빼서 돌려줄 수 있는지가 문제입니다.\n\n2. 📜 관련 법 원칙: 차임을 1년마다 지급해야 하므로, 3년 전의 차임은 소멸시효가 지났다고 봅니다. 하지만 보증금은 차임 미지급 등을 보장하는 역할을 하기 때문에, 이에 대한 일반적인 이해와 신뢰가 있습니다.\n\n3. 💡 이유:  \n1. 임대차계약이 끝나기 전까지는 보증금에서 연체차임을 빼는 것은 임대인이 직접 선택해야 합니다.  \n2. 하지만 장기간 차임을 안 내도 계약을 끝내지 않은 것은, 보증금이 차임을 대신할 것이라 생각하고 계약을 유지했다는 뜻으로 볼 수 있습니다.  \n3. 이에 따라 소멸시효가 지났다고 하더라도 보증금에서 연체차임을 빼는 것이 허용될 수 있습니다.\n\n4. 📝 이렇게 하세요: 소멸시효가 지났다고 주장하는 A의 의견에도 불구하고, 보증금에서 연체차임을 공제할 수 있다고 주장하며 소송을 진행하세요.\n\n구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."
    }
  ]
}
```

### 4-3. 학습 전처리 적용 결과 1건 (train_qlora.encode_row와 동일 로직)

- tokenizer path: `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\adapter_B`
- sample id: R0001
- marker: `<|im_start|>assistant`
- marker char index in full text: 298
- n_mask (labels=-100 prefix tokens): 188
- len(input_ids): 946
- labels 중 -100 개수: 188
- labels 중 non-mask 개수: 758

#### chat template 적용 문자열 전문
```
<|im_start|>system
너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다.<|im_end|>
<|im_start|>user
甲·乙·丙은 사용자 丁으로부터 3인의 임금합계액으로 액면금 600만원인 약속어음 1매를 교부받아 戊로부터 각자의 몫의 금액으로 나눈 여러 매의 약속어음으로 할인 받았으나, 丁으로부터 교부받은 최초의 어음이 지급거절 되었습니다. 이 경우 위 3인은 戊에 대하여 600만원의 채무전액을 부담하지 않고, 각자 자기 몫으로 받은 어음금액상당의 채무만 부담할 수는 없는지요?<|im_end|>
<|im_start|>assistant
여러 명이 관련된 채권관계에 관하여 민법에서 채권자나 채무자가 수인인 경우에 특별한 의사표시가 없으면 각 채권자 또는 각 채무자는 균등한 비율로 권리가 있고 의무를 부담한다고 규정하고 있으며(민법 제408조), 채권의 목적이 그 성질 또는 당사자의 의사표시에 의하여 불가분인 경우에 채권자가 수인인 때에는 각 채권자는 모든 채권자를 위하여 이행을 청구할 수 있고, 채무자는 모든 채권자를 위하여 각 채권자에게 이행할 수 있다고 규정하고 있습니다(민법 제409조). 그리고 민법상 다수당사자의 채권관계에 관한 판례를 보면, 민법상 다수당사자의 채권관계는 원칙적으로 분할채권관계이고, 채권의 성질상 또는 당사자약정에 기초하여 특히 불가분으로 하는 경우에 한하여 불가분채권관계로 되는 것이라고 하였습니다(대법원 1992. 10. 27. 선고 90다13628 판결).그런데 위 사안과 같이 수인이 그 임금합계액으로 발행받은 1매의 어음을 각자 받을 몫의 임금액으로 나눈 여러 매의 어음으로 할인받은 경우 그 채권관계가 분할채권관계인지 불가분채권관계인지 문제되는데 이에 관하여 판례를 보면, 금전소비대차에 있어 수인의 채무자가 각기 일정한 돈을 빌리는 경우에 특별한 의사표시가 없으면 이 채무는 분할채무라 할 것이고, 이러한 특별한 의사표시가 있거나 채권목적이 그 성질상 불가분인 경우에 한하여 불가분채권이 성립되는 것이며, 이러한 법리는 수인의 채무자가 채무전부를 각자 이행할 의무가 있는 경우에도 또한 같다고 할 것이므로, 수인의 골재운송업자들이 그 운임합계액으로 소외회사로부터 약속어음 1매를 발행 받아 그 어음을 각자 받을 몫의 금액으로 나눈 여러 매의 어음으로 할인 받은 것이라면 위 소비대차관계는 그 성질상 불가분채무 또는 연대채무라고 볼 수 없어 당사자간에 특별한 의사표시가 없는 한 채무자 각자가 각각 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만 지는 분할채무라고 함이 상당하다고 하였습니다(대법원 1985. 4. 23. 선고 84다카2159 판결).따라서 위 사안의 경우 甲·乙·丙은 戊에 대하여 각자 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만을 진다고 할 수 있을 것으로 보입니다.<|im_end|>

```

#### 마스크 경계 표시 (prefix=masked / assistant=loss)
```
<<<MASKED_PREFIX>>>
<|im_start|>system
너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다.<|im_end|>
<|im_start|>user
甲·乙·丙은 사용자 丁으로부터 3인의 임금합계액으로 액면금 600만원인 약속어음 1매를 교부받아 戊로부터 각자의 몫의 금액으로 나눈 여러 매의 약속어음으로 할인 받았으나, 丁으로부터 교부받은 최초의 어음이 지급거절 되었습니다. 이 경우 위 3인은 戊에 대하여 600만원의 채무전액을 부담하지 않고, 각자 자기 몫으로 받은 어음금액상당의 채무만 부담할 수는 없는지요?<|im_end|>
<|im_start|>assistant
<<<ASSISTANT_LOSS>>>

여러 명이 관련된 채권관계에 관하여 민법에서 채권자나 채무자가 수인인 경우에 특별한 의사표시가 없으면 각 채권자 또는 각 채무자는 균등한 비율로 권리가 있고 의무를 부담한다고 규정하고 있으며(민법 제408조), 채권의 목적이 그 성질 또는 당사자의 의사표시에 의하여 불가분인 경우에 채권자가 수인인 때에는 각 채권자는 모든 채권자를 위하여 이행을 청구할 수 있고, 채무자는 모든 채권자를 위하여 각 채권자에게 이행할 수 있다고 규정하고 있습니다(민법 제409조). 그리고 민법상 다수당사자의 채권관계에 관한 판례를 보면, 민법상 다수당사자의 채권관계는 원칙적으로 분할채권관계이고, 채권의 성질상 또는 당사자약정에 기초하여 특히 불가분으로 하는 경우에 한하여 불가분채권관계로 되는 것이라고 하였습니다(대법원 1992. 10. 27. 선고 90다13628 판결).그런데 위 사안과 같이 수인이 그 임금합계액으로 발행받은 1매의 어음을 각자 받을 몫의 임금액으로 나눈 여러 매의 어음으로 할인받은 경우 그 채권관계가 분할채권관계인지 불가분채권관계인지 문제되는데 이에 관하여 판례를 보면, 금전소비대차에 있어 수인의 채무자가 각기 일정한 돈을 빌리는 경우에 특별한 의사표시가 없으면 이 채무는 분할채무라 할 것이고, 이러한 특별한 의사표시가 있거나 채권목적이 그 성질상 불가분인 경우에 한하여 불가분채권이 성립되는 것이며, 이러한 법리는 수인의 채무자가 채무전부를 각자 이행할 의무가 있는 경우에도 또한 같다고 할 것이므로, 수인의 골재운송업자들이 그 운임합계액으로 소외회사로부터 약속어음 1매를 발행 받아 그 어음을 각자 받을 몫의 금액으로 나눈 여러 매의 어음으로 할인 받은 것이라면 위 소비대차관계는 그 성질상 불가분채무 또는 연대채무라고 볼 수 없어 당사자간에 특별한 의사표시가 없는 한 채무자 각자가 각각 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만 지는 분할채무라고 함이 상당하다고 하였습니다(대법원 1985. 4. 23. 선고 84다카2159 판결).따라서 위 사안의 경우 甲·乙·丙은 戊에 대하여 각자 자기 몫으로 받은 어음액면금액 상당의 채무변제책임만을 진다고 할 수 있을 것으로 보입니다.<|im_end|>

```

### 4-4. gen_eval.py 평가 프롬프트·생성 설정
(파일: C:/Users/DMLAB/Desktop/학부-AI서비스 개발/run3/gen_eval.py 줄 94-115)
```
  94|         pbar = tqdm(
  95|             todo, desc=f"eval_{model_tag}", unit="q",
  96|             file=NewlineTqdmStream(), ascii=True, mininterval=1.0, dynamic_ncols=False,
  97|         )
  98|         for it in pbar:
  99|             messages = [
 100|                 {"role": "system", "content": SYSTEM_SFT},
 101|                 {"role": "user", "content": it["question"]},
 102|             ]
 103|             prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
 104|             inputs = tok(prompt, return_tensors="pt").to(model.device)
 105|             t0 = time.perf_counter()
 106|             with torch.no_grad():
 107|                 gen = model.generate(
 108|                     **inputs,
 109|                     max_new_tokens=768,
 110|                     do_sample=False,
 111|                     pad_token_id=tok.pad_token_id,
 112|                 )
 113|             elapsed = time.perf_counter() - t0
 114|             new_tokens = gen[0][inputs["input_ids"].shape[-1]:]
 115|             text = tok.decode(new_tokens, skip_special_tokens=True)
```

SYSTEM_SFT 정의 (common.py):

(파일: run3/common.py 줄 30)
```
  30| SYSTEM_SFT = "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
```

#### 실제 평가 입력 문자열 1건 (eval_outputs 첫 행 기준 재구성)
- eval_id: LAWQA-고용-001
- model in row (참고): A
```
<|im_start|>system
너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다.<|im_end|>
<|im_start|>user
근로계약서 미작성 노동부 진정냈더니 사업주가 전화해서 70에 합의하자고 해서 알았다고 한게 공갈협박 인가요?<|im_end|>
<|im_start|>assistant

```

#### 생성 설정 지정 여부
- `max_new_tokens=768`: 코드에 있음 (위 발췌)
- `do_sample=False`: 코드에 있음 (위 발췌)
- `temperature`: 코드 발췌 구간에 없음 → 미확인(미지정)
- `repetition_penalty`: 코드 발췌 구간에 없음 → 미확인(미지정)
- `pad_token_id=tok.pad_token_id`: 코드에 있음
