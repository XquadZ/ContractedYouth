# -*- coding: utf-8 -*-
"""prep_contract/PREP_REPORT.md 생성."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PREP = ROOT / "prep_contract"


def load(name: str):
    p = PREP / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    t1t = load("t1_teacher_results.json")
    t1s = load("t1_student_results.json")
    t2 = load("t2_results.json")
    t3 = load("t3_results.json")
    t4 = load("t4_results.json")

    fails = []
    if t1t is None:
        fails.append("T1 teacher: 결과 파일 없음 (미확인/미완료)")
    else:
        for r in t1t if isinstance(t1t, list) else []:
            if not r.get("load_ok") or not r.get("infer_ok"):
                fails.append(f"T1 teacher ctx={r.get('ctx')}: load={r.get('load_ok')} infer={r.get('infer_ok')} err={r.get('error','')[:120]}")
    if t1s is None:
        fails.append("T1 student: 결과 파일 없음 (미확인/미완료)")
    elif isinstance(t1s, dict) and t1s.get("error"):
        fails.append(f"T1 student: {str(t1s.get('error'))[:200]}")
    elif isinstance(t1s, list):
        for r in t1s:
            if not r.get("infer_ok"):
                fails.append(f"T1 student ctx={r.get('ctx')}: {str(r.get('error',''))[:120]}")
    if t2 is None:
        fails.append("T2: 결과 없음")
    else:
        for r in t2.get("rows", []):
            if not r.get("ok"):
                fails.append(f"T2 FAIL {r.get('rel')}: {r.get('error')}")
            elif "표 누락" in str(r.get("table_status", "")):
                fails.append(f"T2 표 누락 {r.get('rel')} chars={r.get('chars')} status={r.get('table_status')}")
    if t3 is None:
        fails.append("T3: 결과 없음")
    elif t3.get("status") == "OC 미설정":
        fails.append("T3: OC 미설정 (LAW_OC 비어 있음) — 전체 건너뜀")
    elif t3.get("status") != "calls_completed":
        fails.append(f"T3: status={t3.get('status')}")
    if t4 is None:
        fails.append("T4: 결과 없음")

    lines = []
    lines.append("# PREP_REPORT — 계약서 분석 실험 준비 측정")
    lines.append("")
    lines.append("## 실패/미확인 항목 요약")
    lines.append("")
    if fails:
        for f in fails:
            lines.append(f"- {f}")
    else:
        lines.append("- (없음)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## T1. 긴 문맥 처리량·VRAM")
    lines.append("")
    lines.append("### 모델 경로")
    lines.append("")
    lines.append("- 교사 GGUF: `C:\\Users\\DMLAB\\pilot_root\\models\\Qwen3-32B-GGUF\\Qwen3-32B-Q6_K.gguf`")
    lines.append("- 학생 베이스 (run3/adapter_B/train_meta.json): `C:\\Users\\DMLAB\\pilot_root\\models\\Qwen2.5-14B-Instruct`")
    lines.append("- 측정 조건: 입력≈ctx×0.8 토큰 한국어, 출력 max 512, thinking 끔")
    lines.append("")
    lines.append("### 교사 (llama-server Qwen3-32B-Q6_K)")
    lines.append("")
    lines.append("| ctx | load_ok | infer_ok | input_tokens | prompt tok/s | gen tok/s | elapsed_sec | VRAM(after load) | error |")
    lines.append("|---:|:---:|:---:|---:|---:|---:|---:|---|---|")
    if isinstance(t1t, list):
        for r in t1t:
            vram = (r.get("vram_after_load") or "").replace("\n", " ; ")
            lines.append(
                f"| {r.get('ctx')} | {r.get('load_ok')} | {r.get('infer_ok')} | {r.get('input_tokens_measured')} | "
                f"{r.get('prompt_tok_s')} | {r.get('gen_tok_s')} | {r.get('elapsed_sec')} | `{vram[:160]}` | "
                f"{(r.get('error') or '')[:80]} |"
            )
        lines.append("")
        for r in t1t:
            for key, label in [
                ("vram_after_load", "after load"),
                ("vram_after_infer", "after infer"),
            ]:
                if r.get(key):
                    lines.append(f"<details><summary>nvidia-smi teacher ctx={r.get('ctx')} {label}</summary>")
                    lines.append("")
                    lines.append("```")
                    lines.append(r.get(key))
                    lines.append("```")
                    lines.append("</details>")
                    lines.append("")
            if r.get("error"):
                lines.append(f"<details><summary>error teacher ctx={r.get('ctx')}</summary>")
                lines.append("")
                lines.append("```")
                lines.append(str(r.get("error"))[:4000])
                lines.append("```")
                lines.append("</details>")
                lines.append("")
    else:
        lines.append("| — | — | — | — | — | — | — | 미확인 | 미확인 |")
    lines.append("")
    lines.append("원본 JSON: `prep_contract/t1_teacher_results.json` / 로그 `t1_teacher_console.log`")
    lines.append("")
    lines.append("### 학생 (HF 4bit nf4 float16)")
    lines.append("")
    lines.append("| ctx | load_ok | infer_ok | input_tokens | prompt tok/s (approx) | gen tok/s (approx) | elapsed_sec | overall tok/s | error |")
    lines.append("|---:|:---:|:---:|---:|---:|---:|---:|---:|---|")
    if isinstance(t1s, list):
        for r in t1s:
            lines.append(
                f"| {r.get('ctx')} | {r.get('load_ok')} | {r.get('infer_ok')} | {r.get('input_tokens_measured')} | "
                f"{r.get('prompt_tok_s_approx_via_max1')} | {r.get('gen_tok_s_approx')} | {r.get('elapsed_sec')} | "
                f"{r.get('overall_tok_s')} | {(str(r.get('error') or ''))[:80]} |"
            )
        lines.append("")
        lines.append("참고: HF `generate` 단일 호출이라 prompt/gen tok/s는 분리 미측정. "
                     "`prompt_tok_s_approx_via_max1` / `gen_tok_s_approx`는 스크립트 근사값.")
        lines.append("")
        if t1s and t1s[0].get("vram_after_load"):
            lines.append("<details><summary>nvidia-smi student after load (공통)</summary>")
            lines.append("")
            lines.append("```")
            lines.append(t1s[0].get("vram_after_load"))
            lines.append("```")
            lines.append("</details>")
            lines.append("")
        for r in t1s:
            vram = r.get("vram_after_infer") or r.get("vram_after_error")
            if vram:
                tag = "infer" if r.get("infer_ok") else "error"
                lines.append(f"<details><summary>nvidia-smi student ctx={r.get('ctx')} after {tag}</summary>")
                lines.append("")
                lines.append("```")
                lines.append(vram)
                lines.append("```")
                lines.append("</details>")
                lines.append("")
            if r.get("error"):
                lines.append(f"<details><summary>error ctx={r.get('ctx')}</summary>")
                lines.append("")
                lines.append("```")
                lines.append(str(r.get("error"))[:4000])
                lines.append("```")
                lines.append("</details>")
                lines.append("")
    elif isinstance(t1s, dict):
        lines.append(f"| — | {t1s.get('load_ok')} | — | — | — | — | — | — | {(str(t1s.get('error') or ''))[:100]} |")
    else:
        lines.append("| — | — | — | — | — | — | — | — | 미확인 |")
    lines.append("")
    lines.append("원본 JSON: `prep_contract/t1_student_results.json`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## T2. 문서 → 텍스트 추출")
    lines.append("")
    if t2:
        lines.append("### 도구 상태")
        lines.append("```json")
        lines.append(json.dumps(t2.get("tool_status"), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        lines.append(f"- 대상 파일 수: {t2.get('n_files')}")
        lines.append("")
        lines.append("| 파일 | 형식 | 성공 | 글자 수 | 표 추출 여부 | method |")
        lines.append("|---|---|:---:|---:|---|---|")
        for r in t2.get("rows", []):
            lines.append(
                f"| `{r.get('rel')}` | {r.get('ext')} | {r.get('ok')} | {r.get('chars')} | "
                f"{r.get('table_status')} | {(r.get('meta') or {}).get('method')} |"
            )
        lines.append("")
        lines.append("### 파일별 앞 300자")
        lines.append("")
        for r in t2.get("rows", []):
            lines.append(f"#### `{r.get('rel')}`")
            lines.append("```")
            lines.append(r.get("preview_300") or (r.get("error") or ""))
            lines.append("```")
            lines.append("")
    else:
        lines.append("미확인")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## T3. 국가법령정보센터 Open API")
    lines.append("")
    if t3:
        lines.append(f"- status: **{t3.get('status')}**")
        lines.append(f"- oc_configured: {t3.get('oc_configured')}")
        lines.append(f"- note: {t3.get('note', '')}")
        if t3.get("error_body"):
            lines.append("")
            lines.append("### 오류 응답 본문")
            lines.append("```")
            lines.append(str(t3.get("error_body"))[:5000])
            lines.append("```")
        if t3.get("history_test"):
            lines.append("")
            lines.append("### 연혁/시행일 조회")
            lines.append("```json")
            lines.append(json.dumps(t3.get("history_test"), ensure_ascii=False, indent=2)[:8000])
            lines.append("```")
        if t3.get("history_doc_evidence"):
            lines.append("")
            lines.append("### 연혁/시행일 조회 (문서 근거, OC 미설정으로 실호출 없음)")
            lines.append("```json")
            lines.append(json.dumps(t3.get("history_doc_evidence"), ensure_ascii=False, indent=2)[:8000])
            lines.append("```")
        if t3.get("status") == "OC 미설정":
            lines.append("")
            lines.append("결론: LAW_OC 미설정 → a/b/c API 호출 전부 건너뜀. "
                         "문서상 `efYd`(시행일자 범위) 파라미터는 존재하나, "
                         "2022-01-01 시점 본문 단건 조회 성공 여부는 **미확인**.")
    else:
        lines.append("미확인")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## T4. run3 정리 점검")
    lines.append("")
    if t4:
        for side, info in (t4.get("adapters") or {}).items():
            lines.append(f"### adapter_{side}")
            lines.append(f"- eval load path (gen_eval.py): `{info.get('eval_load_path_used_by_gen_eval')}`")
            lines.append(f"- eval_loads_checkpoint_subdir: {info.get('eval_loads_checkpoint_subdir')}")
            lines.append(f"- note: {info.get('eval_note')}")
            lines.append(f"- size_compare: `{json.dumps(info.get('size_compare'))}`")
            lines.append("- checkpoints:")
            for c in info.get("checkpoints") or []:
                lines.append(
                    f"  - `{c.get('name')}` step={c.get('trainer_global_step')} "
                    f"epoch={c.get('trainer_epoch')} size={c.get('adapter_model_size')}"
                )
            lines.append("")
            lines.append("<details><summary>gen_eval.py 관련 줄</summary>")
            lines.append("")
            lines.append("```")
            lines.extend(t4.get("gen_eval_py_excerpt") or [])
            lines.append("```")
            lines.append("</details>")
            lines.append("")
        lines.append("### 평가에 쓰인 checkpoint?")
        lines.append("")
        lines.append(
            "근거: `gen_eval.py`는 `RUN3/adapter_{A|B|C}` 경로를 `PeftModel.from_pretrained`에 전달하며 "
            "`checkpoints/checkpoint-*` 하위 경로를 지정하지 않음. "
            "루트 `adapter_B`/`adapter_C`는 학습 종료 시 `save_pretrained`된 최종 어댑터. "
            "trainer_state 기준 마지막 step은 checkpoint-106 (global_step=106, epoch=2.0). "
            "따라서 평가 로드 대상은 checkpoint-53이 아니라 **루트 adapter(=학습 종료 저장본, 통상 106과 동일 계열)**."
        )
        lines.append("")
        lines.append("### ROOT 내 1GB 이상 파일 (삭제 안 함)")
        lines.append("")
        lines.append("| GB | bytes | path |")
        lines.append("|---:|---:|---|")
        for f in t4.get("files_ge_1gb") or []:
            lines.append(f"| {f.get('GB')} | {f.get('bytes')} | `{f.get('path')}` |")
    else:
        lines.append("미확인")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 산출물 경로")
    lines.append("")
    for name in [
        "t1_teacher_results.json", "t1_student_results.json", "t1_teacher_console.log",
        "t2_results.json", "t2_out/", "extract.py",
        "t3_results.json", "t4_results.json", "PREP_REPORT.md",
    ]:
        p = PREP / name
        lines.append(f"- `{p}` exists={p.exists()}")

    (PREP / "PREP_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", PREP / "PREP_REPORT.md", (PREP / "PREP_REPORT.md").stat().st_size)


if __name__ == "__main__":
    main()
