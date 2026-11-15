# -*- coding: utf-8 -*-
"""FOLLOWUP.md 생성 전용 (실험 산출물 수정 없음)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
RUN3 = ROOT / "run3"
OUT = RUN3 / "FOR_CLAUDE" / "FOLLOWUP.md"
SMOKE = RUN3 / "smoke"


def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_jsonl(path: Path, n: int | None = None) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if n is not None and len(rows) >= n:
                    break
    return rows


def code_excerpt(path: Path, start: int, end: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    chunk = lines[start - 1 : end]
    numbered = [f"{i+start:4d}| {ln}" for i, ln in enumerate(chunk)]
    return f"(파일: {path.as_posix()} 줄 {start}-{end})\n```\n" + "\n".join(numbered) + "\n```"


def smoke_listing() -> str:
    if not SMOKE.exists():
        return "미확인"
    lines = []
    for p in sorted(SMOKE.rglob("*")):
        if p.is_file():
            rel = p.relative_to(SMOKE).as_posix()
            lines.append(f"- `{rel}`\t{p.stat().st_size} bytes")
    return "\n".join(lines) if lines else "미확인"


def main() -> None:
    parts: list[str] = []
    parts.append("# FOLLOWUP — run3 미확인 항목 확인 (근거만)")
    parts.append("")
    parts.append("판정·해석 없음. 근거 없으면 미확인.")
    parts.append("")

    # ----- 1 -----
    parts.append("## 1. 양자화·학습 설정")
    parts.append("")
    tq = RUN3 / "train_qlora.py"
    parts.append("### 1-1. BitsAndBytesConfig")
    parts.append(code_excerpt(tq, 47, 52))
    parts.append("")
    parts.append("### 1-2. 모델 로드 from_pretrained")
    parts.append(code_excerpt(tq, 57, 66))
    parts.append("")
    parts.append("### 1-3. LoRA config")
    parts.append(code_excerpt(tq, 68, 76))
    parts.append("")
    parts.append("### 1-4. loss 마스킹 (assistant 토큰만)")
    parts.append(code_excerpt(tq, 103, 133))
    parts.append("")
    parts.append("### 1-5. TrainingArguments")
    parts.append(code_excerpt(tq, 151, 188))
    parts.append("")
    parts.append("### 1-6. 실행 로그에 남은 설정값")
    parts.append("")
    # train_meta
    for side in ["B", "C"]:
        meta = RUN3 / f"adapter_{side}" / "train_meta.json"
        parts.append(f"#### adapter_{side}/train_meta.json")
        if meta.exists():
            parts.append("```json")
            parts.append(meta.read_text(encoding="utf-8").rstrip())
            parts.append("```")
        else:
            parts.append("미확인")
        parts.append("")
    # trainer_state fields
    for side in ["B", "C"]:
        cands = sorted((RUN3 / f"adapter_{side}" / "checkpoints").glob("checkpoint-*/trainer_state.json"))
        parts.append(f"#### adapter_{side} trainer_state (latest) 일부 필드")
        if cands:
            st = json.loads(cands[-1].read_text(encoding="utf-8"))
            keys = ["logging_steps", "max_steps", "num_train_epochs", "train_batch_size", "save_steps"]
            parts.append("```json")
            parts.append(json.dumps({k: st.get(k) for k in keys}, ensure_ascii=False, indent=2))
            parts.append("```")
            parts.append(f"- path: `{cands[-1]}`")
        else:
            parts.append("미확인")
        parts.append("")
    # console search
    parts.append("#### train_*_console.log 에서 키워드 검색 결과")
    found_any = False
    for side in ["B", "C"]:
        logp = RUN3 / f"train_{side}_console.log"
        if not logp.exists():
            continue
        for i, ln in enumerate(logp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if any(k in ln for k in ["load_in_4bit", "bnb_4bit", "nf4", "BitsAndBytes", "fp16", "bf16", "gradient_checkpointing", "per_device_train_batch", "gradient_accumulation", "max_length", "max_seq"]):
                parts.append(f"- `{logp.name}:{i}`: {ln}")
                found_any = True
    if not found_any:
        parts.append("- load_in_4bit / bnb_4bit_quant_type / bnb_4bit_compute_dtype / fp16·bf16 설정 문자열: 미확인 (해당 키워드 로그 줄 없음)")
    parts.append("")
    parts.append("#### train_B_console.log 학습 중 learning_rate 로그 예시 (원문)")
    tb = RUN3 / "train_B_console.log"
    if tb.exists():
        hits = [ln for ln in tb.read_text(encoding="utf-8", errors="replace").splitlines() if "'learning_rate'" in ln or '"learning_rate"' in ln]
        if hits:
            for ln in hits[:3]:
                parts.append(f"- {ln}")
        else:
            # HF uses single quotes in print sometimes
            hits2 = [ln for ln in tb.read_text(encoding="utf-8", errors="replace").splitlines() if "learning_rate" in ln]
            if hits2:
                for ln in hits2[:3]:
                    parts.append(f"- {ln}")
            else:
                parts.append("미확인")
    else:
        parts.append("미확인")
    parts.append("")
    parts.append("참고: `max_length=2048` 은 encode_row 토크나이저 호출에 있음 (위 1-4 발췌).")
    parts.append("")

    # ----- 2 -----
    parts.append("## 2. 첫 본 실행(01:36) 중단 / 두 번째(12:57) resume 여부")
    parts.append("")
    parts.append("### 2-1. progress.log 전문 (해당 구간 포함)")
    parts.append("```")
    parts.append(read(RUN3 / "progress.log").rstrip() or "미확인")
    parts.append("```")
    parts.append("")
    parts.append("### 2-2. finish_smoke_and_run.log (01:36 전후)")
    fl = read(RUN3 / "finish_smoke_and_run.log").splitlines()
    parts.append("```")
    for ln in fl:
        if any(x in ln for x in ["01:3", "01:2", "01:1", "01:0", "SMOKE", "run_all", "download marker", "3-4", "3-5"]):
            parts.append(ln)
    parts.append("```")
    parts.append("")
    parts.append("### 2-3. run_all.log")
    if (RUN3 / "run_all.log").exists():
        parts.append("```")
        parts.append(read(RUN3 / "run_all.log"))
        parts.append("```")
    else:
        parts.append("미확인 (`run3/run_all.log` 파일 없음)")
    parts.append("")
    parts.append("### 2-4. run_all_console.log")
    parts.append("```")
    parts.append(read(RUN3 / "run_all_console.log").rstrip() or "미확인")
    parts.append("```")
    parts.append("")
    parts.append("### 2-5. hf_download_progress.log (끝부분)")
    hfl = read(RUN3 / "hf_download_progress.log").splitlines()
    parts.append("```")
    parts.extend(hfl[-12:] if hfl else ["미확인"])
    parts.append("```")
    parts.append("")
    parts.append("### 2-6. gen_teacher resume 관련 로그 (`done=`/`todo=`)")
    # search
    resume_hits = []
    for p in RUN3.glob("*.log"):
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if "done=" in ln and "todo=" in ln:
                resume_hits.append(f"{p.name}:{i}: {ln}")
    if resume_hits:
        for h in resume_hits:
            parts.append(f"- {h}")
    else:
        parts.append("미확인 (보존된 로그에 `items=... done=... todo=...` 줄 없음. `run_all_console.log`는 12:57 재시작 시점부터만 존재)")
    parts.append("")
    parts.append("### 2-7. teacher_outputs.jsonl 파일 시각·건수")
    top = RUN3 / "teacher_outputs.jsonl"
    if top.exists():
        st = top.stat()
        import datetime as dt
        ctime = dt.datetime.fromtimestamp(st.st_ctime)
        mtime = dt.datetime.fromtimestamp(st.st_mtime)
        rows = load_jsonl(top)
        ids = [r["id"] for r in rows]
        parts.append(f"- path: `{top}`")
        parts.append(f"- st_ctime: {ctime.isoformat(sep=' ', timespec='seconds')}")
        parts.append(f"- st_mtime: {mtime.isoformat(sep=' ', timespec='seconds')}")
        parts.append(f"- line count: {len(rows)}")
        parts.append(f"- first id: {ids[0] if ids else '미확인'}")
        parts.append(f"- id at index 430: {ids[429] if len(ids) >= 430 else '미확인'}")
        parts.append(f"- id at index 431: {ids[430] if len(ids) >= 431 else '미확인'}")
        parts.append(f"- last id: {ids[-1] if ids else '미확인'}")
        # contiguous?
        expect = [f"R{i:04d}" for i in range(1, len(ids) + 1)]
        parts.append(f"- ids == R0001..R{{n:04d}} contiguous: {ids == expect}")
    else:
        parts.append("미확인")
    parts.append("")
    parts.append("### 2-8. OS LastBootUpTime (재시작 시각)")
    try:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        boot = (r.stdout or "").strip()
        parts.append(f"- LastBootUpTime: {boot if boot else '미확인'}")
    except Exception:
        parts.append("- LastBootUpTime: 미확인")
    parts.append("")
    parts.append("### 2-9. progress.log 상 3-2 소요와 건수 관계 (숫자만)")
    parts.append("- 두 번째 실행 `END 3-2_teacher ... elapsed_sec=9044.7` (progress.log 원문 위 2-1)")
    parts.append(f"- 9044.7 / 22 ≈ {round(9044.7/22, 1)} (가정 초/건 22는 계산용; 로그 평균 아님)")
    parts.append(f"- 898 * 22 = {898*22}")
    parts.append(f"- 468 * 22 = {468*22}")
    parts.append("- gen_teacher.py resume 코드:")
    parts.append(code_excerpt(RUN3 / "gen_teacher.py", 141, 146))
    parts.append("")
    parts.append("첫 실행 중단의 직접 원인 문자열이 로그에 있는지: progress.log에 01:36 START 3-2 이후 END 없이 12:57 BEGIN이 이어짐. "
                 "중단 원인 문자열(예: reboot/killed) 로그 원문: 미확인")
    parts.append("")

    # ----- 3 -----
    parts.append("## 3. 스모크 3-4 / 3-5 실행 여부")
    parts.append("")
    parts.append("### 3-1. finish_smoke_and_run.log 원문")
    parts.append("```")
    for ln in fl:
        if "smoke" in ln.lower() or "3-4" in ln or "3-5" in ln or "SMOKE" in ln:
            parts.append(ln)
    parts.append("```")
    parts.append("")
    parts.append("### 3-2. smoke_summary.json")
    ss = RUN3 / "smoke_summary.json"
    if ss.exists():
        parts.append("```json")
        parts.append(ss.read_text(encoding="utf-8").rstrip())
        parts.append("```")
    else:
        parts.append("미확인")
    parts.append("")
    parts.append("### 3-3. smoke/adapter_B/ERROR.txt 원문")
    errb = SMOKE / "adapter_B" / "ERROR.txt"
    if errb.exists():
        parts.append("```")
        parts.append(errb.read_text(encoding="utf-8", errors="replace").rstrip())
        parts.append("```")
    else:
        parts.append("미확인")
    parts.append("")
    parts.append("### 3-4. smoke 평가 산출물 건수")
    for name in ["eval_outputs.jsonl", "eval_outputs_A.jsonl", "eval_outputs_B.jsonl", "eval_outputs_C.jsonl"]:
        p = SMOKE / name
        n = len(load_jsonl(p)) if p.exists() else "파일없음"
        parts.append(f"- `{name}`: {n}")
    parts.append("")
    parts.append("### 3-5. smoke/gen_eval_A_console.log 끝부분")
    ga = SMOKE / "gen_eval_A_console.log"
    if ga.exists():
        lines = ga.read_text(encoding="utf-8", errors="replace").splitlines()
        parts.append("```")
        parts.extend(lines[-20:])
        parts.append("```")
    else:
        parts.append("미확인")
    parts.append("")
    parts.append("### 3-6. run3/smoke/ 파일 목록과 크기")
    parts.append(smoke_listing())
    parts.append("")

    # ----- 4 -----
    parts.append("## 4. 학습·평가 입력 형식")
    parts.append("")
    parts.append("### 4-1. sft_B.jsonl 첫 2건")
    for i, r in enumerate(load_jsonl(RUN3 / "sft_B.jsonl", 2), 1):
        parts.append(f"#### B row {i}")
        parts.append("```json")
        parts.append(json.dumps(r, ensure_ascii=False, indent=2))
        parts.append("```")
    parts.append("")
    parts.append("### 4-2. sft_C.jsonl 첫 2건")
    for i, r in enumerate(load_jsonl(RUN3 / "sft_C.jsonl", 2), 1):
        parts.append(f"#### C row {i}")
        parts.append("```json")
        parts.append(json.dumps(r, ensure_ascii=False, indent=2))
        parts.append("```")
    parts.append("")
    parts.append("### 4-3. 학습 전처리 적용 결과 1건 (train_qlora.encode_row와 동일 로직)")
    parts.append("")
    try:
        from transformers import AutoTokenizer
        base = None
        for cand in [
            RUN3 / "adapter_B",
            Path(r"C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct"),
        ]:
            if (cand / "tokenizer_config.json").exists() or (cand / "tokenizer.json").exists():
                base = str(cand)
                break
        if base is None:
            parts.append("미확인 (tokenizer 경로 없음)")
        else:
            tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            ex = load_jsonl(RUN3 / "sft_B.jsonl", 1)[0]
            messages = ex["messages"]
            try:
                probe = tokenizer.apply_chat_template(
                    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
                    tokenize=False,
                )
                marker = "<|im_start|>assistant"
                if marker not in probe:
                    marker = "assistant\n"
            except Exception:
                marker = "<|im_start|>assistant"
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            tok = tokenizer(text, truncation=True, max_length=2048, padding=False, return_tensors=None)
            input_ids = tok["input_ids"]
            labels = list(input_ids)
            full = text
            idx = full.rfind(marker)
            n_mask = 0
            if idx >= 0:
                prefix = full[: idx + len(marker)]
                prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
                n_mask = min(len(prefix_ids), len(labels))
                for i in range(n_mask):
                    labels[i] = -100
            parts.append(f"- tokenizer path: `{base}`")
            parts.append(f"- sample id: {ex.get('id')}")
            parts.append(f"- marker: `{marker}`")
            parts.append(f"- marker char index in full text: {idx}")
            parts.append(f"- n_mask (labels=-100 prefix tokens): {n_mask}")
            parts.append(f"- len(input_ids): {len(input_ids)}")
            parts.append(f"- labels 중 -100 개수: {sum(1 for x in labels if x == -100)}")
            parts.append(f"- labels 중 non-mask 개수: {sum(1 for x in labels if x != -100)}")
            parts.append("")
            parts.append("#### chat template 적용 문자열 전문")
            parts.append("```")
            parts.append(text)
            parts.append("```")
            parts.append("")
            parts.append("#### 마스크 경계 표시 (prefix=masked / assistant=loss)")
            if idx >= 0:
                parts.append("```")
                parts.append("<<<MASKED_PREFIX>>>")
                parts.append(full[: idx + len(marker)])
                parts.append("<<<ASSISTANT_LOSS>>>")
                parts.append(full[idx + len(marker) :])
                parts.append("```")
            else:
                parts.append("미확인 (marker not found)")
    except Exception as e:
        parts.append(f"미확인 ({type(e).__name__}: {e})")
    parts.append("")
    parts.append("### 4-4. gen_eval.py 평가 프롬프트·생성 설정")
    ge = RUN3 / "gen_eval.py"
    parts.append(code_excerpt(ge, 94, 115))
    parts.append("")
    parts.append("SYSTEM_SFT 정의 (common.py):")
    parts.append(code_excerpt(RUN3 / "common.py", 19, 20) if False else "")
    # find SYSTEM_SFT line
    common = (RUN3 / "common.py").read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(common, 1):
        if ln.startswith("SYSTEM_SFT"):
            parts.append(f"(파일: run3/common.py 줄 {i})\n```\n{i:4d}| {ln}\n```")
            break
    parts.append("")
    parts.append("#### 실제 평가 입력 문자열 1건 (eval_outputs 첫 행 기준 재구성)")
    ev = load_jsonl(RUN3 / "eval_outputs.jsonl", 1)
    if not ev:
        parts.append("미확인")
    else:
        r0 = ev[0]
        from common import SYSTEM_SFT  # may fail if cwd wrong
        try:
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(str(RUN3 / "adapter_B"), trust_remote_code=True)
            messages = [
                {"role": "system", "content": SYSTEM_SFT},
                {"role": "user", "content": r0["question"]},
            ]
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            parts.append(f"- eval_id: {r0.get('eval_id')}")
            parts.append(f"- model in row (참고): {r0.get('model')}")
            parts.append("```")
            parts.append(prompt)
            parts.append("```")
        except Exception as e:
            # fallback without import common
            sys_line = next((ln for ln in common if ln.startswith("SYSTEM_SFT")), "")
            import ast
            system = ast.literal_eval(sys_line.split("=", 1)[1].strip()) if "=" in sys_line else "미확인"
            parts.append(f"- eval_id: {r0.get('eval_id')}")
            parts.append(f"- system (from common.py parse): {system}")
            parts.append(f"- user: {r0.get('question')}")
            parts.append(f"- chat template 적용 결과: 미확인 ({type(e).__name__}: {e})")
    parts.append("")
    parts.append("#### 생성 설정 지정 여부")
    parts.append("- `max_new_tokens=768`: 코드에 있음 (위 발췌)")
    parts.append("- `do_sample=False`: 코드에 있음 (위 발췌)")
    parts.append("- `temperature`: 코드 발췌 구간에 없음 → 미확인(미지정)")
    parts.append("- `repetition_penalty`: 코드 발췌 구간에 없음 → 미확인(미지정)")
    parts.append("- `pad_token_id=tok.pad_token_id`: 코드에 있음")
    parts.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(str(OUT))
    print(OUT.stat().st_size)


if __name__ == "__main__":
    # ensure import path
    import sys
    sys.path.insert(0, str(RUN3))
    main()
