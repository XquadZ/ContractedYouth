# -*- coding: utf-8 -*-
"""run3 → FOR_CLAUDE 외부 검토용 묶음. 집계·수집만 (판정 없음)."""
from __future__ import annotations

import json
import random
import re
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
PILOT = ROOT / "pilot"
RUN3 = ROOT / "run3"
OUT = RUN3 / "FOR_CLAUDE"
SEED = 42
FOOTER = "구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."
HEADER_MARKERS = ["1. 🔍", "2. 📜", "3. 💡", "4. 📝"]
DEBT_EXCLUDE = [
    "가등기", "근저당", "저당권", "양도담보", "소유권이전등기", "말소등기",
    "회복등기", "표현대리", "대물변제", "어음", "수표", "가처분",
]
DOMAINS = ["고용", "계약", "채권채무"]
ARTICLE_RE = re.compile(r"제\d+조(?:의\d+)?")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{4,}")
MAX_NEW_TOKENS = 768


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_text(path: Path) -> str:
    if not path.exists():
        return "(파일없음)"
    return path.read_text(encoding="utf-8", errors="replace")


def headers_ok(text: str) -> bool:
    pos = -1
    for h in HEADER_MARKERS:
        i = text.find(h)
        if i < 0 or i < pos:
            return False
        pos = i
    return True


def footer_ok(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return bool(lines) and lines[-1] == FOOTER


def sentence_repeat_ge3(text: str) -> bool:
    # split on punctuation / newlines (fixed-width lookbehind only)
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    units = []
    for p in parts:
        s = p.strip()
        if len(s) >= 8:
            units.append(s)
    if not units:
        return False
    c = Counter(units)
    return any(v >= 3 for v in c.values())


def debt_hit(text: str) -> bool:
    return any(w in text for w in DEBT_EXCLUDE)


def select_filter_counts() -> dict:
    pool = load_jsonl(PILOT / "train_pool_lawqa.jsonl")
    before = Counter(r["domain"] for r in pool)
    after_filtered: dict[str, int] = defaultdict(int)
    dropped_debt = 0
    for r in pool:
        d = r["domain"]
        if d == "채권채무" and debt_hit(str(r["question"]) + str(r["answer"])):
            dropped_debt += 1
            continue
        after_filtered[d] += 1
    items = load_jsonl(RUN3 / "items.jsonl")
    final = Counter(r["domain"] for r in items)
    return {
        "train_pool_n": len(pool),
        "domain_before": dict(before),
        "domain_after_filter": {d: after_filtered[d] for d in DOMAINS},
        "dropped_debt": dropped_debt,
        "items_n": len(items),
        "items_domain": dict(final),
    }


def load_forbidden_refs() -> set[int]:
    forbidden: set[int] = set()
    audit = ROOT / "AUDIT_SAMPLES.jsonl"
    if audit.exists():
        with audit.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("source") == "lawqa" and r.get("origin_ref") is not None:
                    forbidden.add(int(r["origin_ref"]))
    for r in load_jsonl(PILOT / "eval_lawqa.jsonl"):
        if r.get("origin_ref") is not None:
            forbidden.add(int(r["origin_ref"]))
    return forbidden


def integrity_checks() -> dict:
    sft_b = load_jsonl(RUN3 / "sft_B.jsonl")
    sft_c = load_jsonl(RUN3 / "sft_C.jsonl")
    items = {r["id"]: r for r in load_jsonl(RUN3 / "items.jsonl")}

    def split_ids(rows: list[dict], split: str) -> set[str]:
        return {r["id"] for r in rows if r.get("split") == split}

    b_train, c_train = split_ids(sft_b, "train"), split_ids(sft_c, "train")
    b_val, c_val = split_ids(sft_b, "val"), split_ids(sft_c, "val")
    all_ids = b_train | b_val | c_train | c_val

    row_idxs = set()
    missing_in_items = []
    for i in all_ids:
        if i in items:
            row_idxs.add(int(items[i]["row_idx"]))
        else:
            missing_in_items.append(i)

    forbidden = load_forbidden_refs()
    overlap = row_idxs & forbidden

    sys_b = {m["content"] for r in sft_b for m in r.get("messages", []) if m.get("role") == "system"}
    sys_c = {m["content"] for r in sft_c for m in r.get("messages", []) if m.get("role") == "system"}

    return {
        "sft_B_n": len(sft_b),
        "sft_C_n": len(sft_c),
        "train_B_n": len(b_train),
        "train_C_n": len(c_train),
        "train_ids_equal": b_train == c_train,
        "train_symmetric_diff_n": len(b_train ^ c_train),
        "val_B_n": len(b_val),
        "val_C_n": len(c_val),
        "val_ids_equal": b_val == c_val,
        "val_symmetric_diff_n": len(b_val ^ c_val),
        "union_id_n": len(all_ids),
        "union_row_idx_n": len(row_idxs),
        "forbidden_ref_n": len(forbidden),
        "overlap_row_idx_forbidden_n": len(overlap),
        "overlap_examples": sorted(list(overlap))[:20],
        "ids_missing_from_items_n": len(missing_in_items),
        "system_prompts_B": sorted(sys_b),
        "system_prompts_C": sorted(sys_c),
        "system_prompts_identical": sys_b == sys_c and len(sys_b) == 1,
    }


def find_trainer_state(side: str) -> Path | None:
    base = RUN3 / f"adapter_{side}" / "checkpoints"
    if not base.exists():
        return None
    cands = sorted(base.glob("checkpoint-*/trainer_state.json"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def training_excerpt(side: str) -> dict:
    adapter_cfg_path = RUN3 / f"adapter_{side}" / "adapter_config.json"
    meta_path = RUN3 / f"adapter_{side}" / "train_meta.json"
    state_path = find_trainer_state(side)
    out = {
        "side": side,
        "adapter_config_path": str(adapter_cfg_path) if adapter_cfg_path.exists() else "미확인",
        "adapter_config": json.loads(adapter_cfg_path.read_text(encoding="utf-8")) if adapter_cfg_path.exists() else "미확인",
        "train_meta_path": str(meta_path) if meta_path.exists() else "미확인",
        "train_meta": json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else "미확인",
        "trainer_state_path": str(state_path) if state_path else "미확인",
        "trainer_state_training_fields": "미확인",
        "quantization_config_in_saved_files": "미확인",
        "log_history": [],
    }
    if state_path and state_path.exists():
        st = json.loads(state_path.read_text(encoding="utf-8"))
        out["log_history"] = st.get("log_history", [])
        # fields present in trainer_state (not full TrainingArguments)
        keys = [
            "epoch", "eval_steps", "global_step", "logging_steps", "max_steps",
            "num_train_epochs", "save_steps", "train_batch_size", "total_flos",
        ]
        out["trainer_state_training_fields"] = {k: st.get(k, "미확인") for k in keys}
    # search console for bitsandbytes / BitsAndBytes
    console = RUN3 / f"train_{side}_console.log"
    if console.exists():
        txt = console.read_text(encoding="utf-8", errors="replace")
        hits = [ln for ln in txt.splitlines() if re.search(r"bitsandbytes|BitsAndBytes|nf4|4.bit|load_in_4bit", ln, re.I)]
        out["quantization_console_lines"] = hits[:20] if hits else []
    else:
        out["quantization_console_lines"] = []
    return out


def loss_table_md(log_history: list[dict]) -> str:
    lines = ["| step | loss | eval_loss | learning_rate | epoch |", "|---:|---:|---:|---:|---:|"]
    for h in log_history:
        step = h.get("step", "")
        loss = h.get("loss", "")
        eloss = h.get("eval_loss", "")
        lr = h.get("learning_rate", "")
        ep = h.get("epoch", "")
        lines.append(f"| {step} | {loss} | {eloss} | {lr} | {ep} |")
    return "\n".join(lines)


def eval_aggregates() -> tuple[str, dict]:
    rows = load_jsonl(RUN3 / "eval_outputs.jsonl")
    tok = None
    tok_note = "미확인"
    try:
        from transformers import AutoTokenizer
        model_path = RUN3 / "adapter_B"
        # tokenizer saved with adapter
        tok = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
        tok_note = f"tokenizer: {model_path}"
    except Exception as e:
        try:
            from transformers import AutoTokenizer
            local = Path(r"C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct")
            tok = AutoTokenizer.from_pretrained(str(local), trust_remote_code=True)
            tok_note = f"tokenizer: {local}"
        except Exception as e2:
            tok_note = f"미확인 (load failed: {type(e).__name__}/{type(e2).__name__})"

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r.get("model", "?"), r.get("source", "?"))].append(r)

    # also overall per model
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_model[r.get("model", "?")].append(r)

    def stats_for(subset: list[dict]) -> dict:
        lens = [len(r.get("output") or "") for r in subset]
        secs = [float(r.get("gen_sec") or 0) for r in subset]
        n = len(subset)
        hdr = sum(1 for r in subset if headers_ok(r.get("output") or ""))
        ftr = sum(1 for r in subset if footer_ok(r.get("output") or ""))
        cjk = sum(1 for r in subset if CJK_RUN_RE.search(r.get("output") or ""))
        rep = sum(1 for r in subset if sentence_repeat_ge3(r.get("output") or ""))
        trunc = 0
        novel_article_rows = 0
        novel_articles: list[str] = []
        for r in subset:
            out = r.get("output") or ""
            ref = r.get("reference_answer") or ""
            if tok is not None:
                ntok = len(tok.encode(out, add_special_tokens=False))
                if ntok >= MAX_NEW_TOKENS:
                    trunc += 1
            arts_out = set(ARTICLE_RE.findall(out))
            arts_ref = set(ARTICLE_RE.findall(ref))
            novel = sorted(arts_out - arts_ref)
            if novel:
                novel_article_rows += 1
                for a in novel:
                    novel_articles.append(f"{r.get('eval_id')}/{r.get('model')}:{a}")
        return {
            "n": n,
            "char_mean": round(statistics.mean(lens), 2) if lens else None,
            "char_median": statistics.median(lens) if lens else None,
            "trunc_ge_768_tokens": trunc if tok is not None else "미확인",
            "headers_all_ratio": round(hdr / n, 4) if n else None,
            "footer_exact_ratio": round(ftr / n, 4) if n else None,
            "cjk_run4_n": cjk,
            "sentence_repeat_ge3_n": rep,
            "novel_article_row_n": novel_article_rows,
            "novel_articles": novel_articles,
            "gen_sec_mean": round(statistics.mean(secs), 3) if secs else None,
        }

    md = []
    md.append(f"- tokenizer for truncation count: {tok_note}")
    md.append(f"- max_new_tokens threshold: {MAX_NEW_TOKENS}")
    md.append("")
    md.append("| model | source | n | char_mean | char_median | trunc>=768tok | headers_all_ratio | footer_exact_ratio | cjk_run4_n | sent_repeat>=3_n | novel_article_rows | gen_sec_mean |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    detail = {}
    for key in sorted(groups.keys()):
        st = stats_for(groups[key])
        detail[f"{key[0]}/{key[1]}"] = st
        md.append(
            f"| {key[0]} | {key[1]} | {st['n']} | {st['char_mean']} | {st['char_median']} | "
            f"{st['trunc_ge_768_tokens']} | {st['headers_all_ratio']} | {st['footer_exact_ratio']} | "
            f"{st['cjk_run4_n']} | {st['sentence_repeat_ge3_n']} | {st['novel_article_row_n']} | {st['gen_sec_mean']} |"
        )
    md.append("")
    md.append("### novel articles list (eval output has 제N조 not in reference_answer)")
    md.append("")
    all_novel = []
    for st in detail.values():
        all_novel.extend(st.get("novel_articles") or [])
    if all_novel:
        md.append(f"- count(list entries)={len(all_novel)}")
        for x in all_novel:
            md.append(f"- {x}")
    else:
        md.append("- (none)")
    return "\n".join(md), {"groups": detail, "tok_note": tok_note}


def fail_examples_from_report(report: dict) -> str:
    lines = []
    fe = report.get("fail_examples") or {}
    teacher = {r["id"]: r for r in load_jsonl(RUN3 / "teacher_outputs.jsonl")}
    for reason, examples in fe.items():
        lines.append(f"#### 사유: {reason}")
        if not examples:
            lines.append("- 예시 없음")
            continue
        ex = examples[0]
        eid = ex.get("id")
        full = teacher.get(eid, {})
        lines.append(f"- id: {eid}")
        lines.append(f"- reason field: {ex.get('reason')}")
        lines.append("- teacher output 원문:")
        lines.append("```")
        lines.append(full.get("output") if full else (ex.get("output") or "(미확인)"))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def write_teacher_sample() -> int:
    final_ids = set()
    p = RUN3 / "final_ids.txt"
    if p.exists():
        final_ids = {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()}
    else:
        # fallback: sft ids
        final_ids = {r["id"] for r in load_jsonl(RUN3 / "sft_B.jsonl")}

    teachers = [r for r in load_jsonl(RUN3 / "teacher_outputs.jsonl") if r.get("id") in final_ids]
    by_dom: dict[str, list[dict]] = defaultdict(list)
    for r in teachers:
        by_dom[r.get("domain", "?")].append(r)

    rng = random.Random(SEED)
    quotas = {"고용": 7, "계약": 7, "채권채무": 6}
    picked: list[dict] = []
    for d, q in quotas.items():
        pool = list(by_dom.get(d, []))
        rng.shuffle(pool)
        picked.extend(pool[:q])

    lines = []
    lines.append(f"# teacher_sample seed={SEED} quotas={quotas} picked={len(picked)}")
    lines.append(f"# final_ids pool size used={len(teachers)}")
    lines.append("")
    for r in picked:
        lines.append("=" * 80)
        lines.append(f"id: {r.get('id')}")
        lines.append(f"domain: {r.get('domain')}")
        lines.append("")
        lines.append("[question]")
        lines.append(r.get("question") or "")
        lines.append("")
        lines.append("[answer]")
        lines.append(r.get("answer") or "")
        lines.append("")
        lines.append("[output]")
        lines.append(r.get("output") or "")
        lines.append("")
    out = OUT / "teacher_sample.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    return len(picked)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # file 2: eval_outputs.txt
    src_eval = RUN3 / "eval_outputs.jsonl"
    dst_eval = OUT / "eval_outputs.txt"
    if src_eval.exists():
        shutil.copyfile(src_eval, dst_eval)
    else:
        dst_eval.write_text("(파일없음)\n", encoding="utf-8")

    # file 3: teacher sample
    n_sample = write_teacher_sample()

    # aggregates
    sel = select_filter_counts()
    integ = integrity_checks()
    report_path = RUN3 / "build_sft_report.json"
    build_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    train_b = training_excerpt("B")
    train_c = training_excerpt("C")
    eval_md, eval_detail = eval_aggregates()

    # SUMMARY.md
    parts: list[str] = []
    parts.append("# FOR_CLAUDE SUMMARY")
    parts.append("")
    parts.append("집계·수집만. 판정 문구 없음. 확인 못 한 항목은 미확인.")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 1) RUN3_REPORT.md 전문")
    parts.append("")
    parts.append(read_text(RUN3 / "RUN3_REPORT.md"))
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 2) progress.log 전문")
    parts.append("")
    parts.append("```")
    parts.append(read_text(RUN3 / "progress.log").rstrip())
    parts.append("```")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 3) 3-1 문항 선정 건수")
    parts.append("")
    parts.append(f"- train_pool_lawqa.jsonl 총건수: {sel['train_pool_n']}")
    parts.append(f"- 채권채무 추가필터 제외 건수: {sel['dropped_debt']}")
    parts.append("")
    parts.append("| domain | 필터 전 | 필터 후 | items 최종 |")
    parts.append("|---|---:|---:|---:|")
    for d in DOMAINS:
        parts.append(
            f"| {d} | {sel['domain_before'].get(d, 0)} | "
            f"{sel['domain_after_filter'].get(d, 0)} | {sel['items_domain'].get(d, 0)} |"
        )
    parts.append(f"| **합계** | {sum(sel['domain_before'].values())} | "
                 f"{sum(sel['domain_after_filter'].values())} | {sel['items_n']} |")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 4) 3-3 검증 (build_sft_report.json)")
    parts.append("")
    parts.append("### build_sft_report.json 전문")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(build_report, ensure_ascii=False, indent=2) if build_report else "미확인")
    parts.append("```")
    parts.append("")
    parts.append("### 탈락 사유별 건수")
    parts.append("")
    rc = build_report.get("reason_counts") or {}
    parts.append("| reason | count |")
    parts.append("|---|---:|")
    if rc:
        for k, v in rc.items():
            parts.append(f"| {k} | {v} |")
    else:
        parts.append("| (없음/미확인) |  |")
    parts.append("")
    parts.append("### 사유별 예시 1건 (teacher output 원문)")
    parts.append("")
    parts.append(fail_examples_from_report(build_report))
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 5) 데이터 무결성 확인")
    parts.append("")
    parts.append(f"- sft_B 건수: {integ['sft_B_n']}")
    parts.append(f"- sft_C 건수: {integ['sft_C_n']}")
    parts.append(f"- train id 집합 동일 여부: {integ['train_ids_equal']} (B={integ['train_B_n']}, C={integ['train_C_n']}, 대칭차집합={integ['train_symmetric_diff_n']})")
    parts.append(f"- val id 집합 동일 여부: {integ['val_ids_equal']} (B={integ['val_B_n']}, C={integ['val_C_n']}, 대칭차집합={integ['val_symmetric_diff_n']})")
    parts.append(f"- train∪val id 수: {integ['union_id_n']}, 대응 row_idx 수: {integ['union_row_idx_n']}")
    parts.append(f"- forbidden origin_ref 수 (AUDIT lawqa ∪ eval_lawqa): {integ['forbidden_ref_n']}")
    parts.append(f"- row_idx ∩ forbidden 크기: {integ['overlap_row_idx_forbidden_n']}")
    if integ["overlap_examples"]:
        parts.append(f"- overlap examples: {integ['overlap_examples']}")
    parts.append(f"- items.jsonl에 없는 sft id 수: {integ['ids_missing_from_items_n']}")
    parts.append(f"- system prompts B: {integ['system_prompts_B']}")
    parts.append(f"- system prompts C: {integ['system_prompts_C']}")
    parts.append(f"- system 프롬프트 동일(단일값): {integ['system_prompts_identical']}")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 6) 학습 설정 발췌 (저장 파일 기준)")
    parts.append("")
    for side, tr in [("B", train_b), ("C", train_c)]:
        parts.append(f"### Model {side}")
        parts.append("")
        parts.append(f"- adapter_config path: `{tr['adapter_config_path']}`")
        parts.append("")
        parts.append("#### adapter_config.json")
        parts.append("```json")
        parts.append(json.dumps(tr["adapter_config"], ensure_ascii=False, indent=2) if isinstance(tr["adapter_config"], dict) else str(tr["adapter_config"]))
        parts.append("```")
        parts.append("")
        parts.append(f"- train_meta path: `{tr['train_meta_path']}`")
        parts.append("```json")
        parts.append(json.dumps(tr["train_meta"], ensure_ascii=False, indent=2) if isinstance(tr["train_meta"], dict) else str(tr["train_meta"]))
        parts.append("```")
        parts.append("")
        parts.append(f"- trainer_state path: `{tr['trainer_state_path']}`")
        parts.append("#### trainer_state 내 training 관련 필드")
        parts.append("```json")
        parts.append(json.dumps(tr["trainer_state_training_fields"], ensure_ascii=False, indent=2) if isinstance(tr["trainer_state_training_fields"], dict) else str(tr["trainer_state_training_fields"]))
        parts.append("```")
        parts.append("")
        parts.append(f"- quantization_config_in_saved_files: {tr['quantization_config_in_saved_files']}")
        parts.append(f"- quantization 관련 console 줄 수: {len(tr.get('quantization_console_lines') or [])}")
        if tr.get("quantization_console_lines"):
            parts.append("```")
            parts.extend(tr["quantization_console_lines"])
            parts.append("```")
        else:
            parts.append("- (console에서 bitsandbytes/nf4 문자열 없음 → 양자화 config 상세는 미확인)")
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 7) loss 표 (trainer_state.json log_history)")
    parts.append("")
    parts.append("### B")
    parts.append("")
    parts.append(loss_table_md(train_b.get("log_history") or []))
    parts.append("")
    parts.append("### C")
    parts.append("")
    parts.append(loss_table_md(train_c.get("log_history") or []))
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 8) 평가 생성 자동 집계")
    parts.append("")
    parts.append(f"- eval_outputs.jsonl 총 행수: {len(load_jsonl(RUN3 / 'eval_outputs.jsonl'))}")
    parts.append("")
    parts.append(eval_md)
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## bundle meta")
    parts.append("")
    parts.append(f"- teacher_sample picked: {n_sample}")
    parts.append(f"- OUT: {OUT}")
    parts.append("")

    summary_path = OUT / "SUMMARY.md"
    summary_path.write_text("\n".join(parts), encoding="utf-8")

    # print file list + sizes (요청 산출물)
    print("FOR_CLAUDE files:")
    for name in ["SUMMARY.md", "eval_outputs.txt", "teacher_sample.txt", "bundle.py"]:
        p = OUT / name
        if p.exists():
            print(f"{p.name}\t{p.stat().st_size}\tbytes")
        else:
            print(f"{p.name}\tMISSING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
