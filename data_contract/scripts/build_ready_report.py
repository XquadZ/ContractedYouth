# -*- coding: utf-8 -*-
"""DATA_READY_REPORT.md 갱신."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
DC = ROOT / "data_contract"
OUT = DC / "DATA_READY_REPORT.md"


def load(rel):
    p = DC / rel
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def disk_c():
    return round(shutil.disk_usage("C:\\").free / (1024**3), 2)


def main():
    s1 = load("s1_results.json") or {}
    s1emp = load("s1_employment_nonlabor.json") or {}
    s2 = load("s2_results.json") or {}
    s3 = load("s3_results.json") or {}
    s4 = load("cases/s4_results.json") or {}
    s5local = load("s5_local_models.json") or []
    s5res = load("s5_results.json") or {}
    s5dl = load("s5_downloads.json") or (s5res.get("downloads") if isinstance(s5res, dict) else None) or []
    s5ver = load("s5_verify.json") or {}
    s5teacher = load("s5_teacher_survey.json") or {}
    samples_md = (DC / "s1_samples.md").read_text(encoding="utf-8") if (DC / "s1_samples.md").exists() else ""
    pkg_line = next((ln for ln in samples_md.splitlines() if ln.startswith("## full_package")), "미확인")

    downloads = s5dl if isinstance(s5dl, list) else []

    def dl_status(name):
        d = next((x for x in downloads if name in str(x.get("repo_id") or "")), None)
        if d and d.get("ok"):
            return "있음", f"{d.get('GB')} GB"
        # verify
        for m in (s5ver.get("models") or []):
            if name.split("/")[-1] in str(m.get("path") or m.get("repo_id") or "") and m.get("exists") and not m.get("incomplete_remaining"):
                return "있음", f"{m.get('total_GB')} GB"
        p = DC / "models" / name.split("/")[-1]
        if p.exists():
            return "일부", "다운로드/검증 진행중"
        return "없음", "-"

    rows = []
    b = (s1.get("bucket_counts_label_json") or {})
    rows.append(("AIHub 계약 서식(05 zip)", "있음" if s1 else "미확인", str(DC / "aihub_forms"),
                 f"라벨 {s1.get('label_json_count')} / 고용{b.get('고용')} 임대{b.get('부동산임대')} 금전{b.get('금전대차')}", "§1"))
    rows.append(("AIHub 풀패키지(~160GB)", "있음(모델·도커)", str(ROOT / "계약 법률 문서 서식 데이터"),
                 pkg_line.replace("## full_package ", ""), "§1"))
    rows.append(("AIHub 판결서·약관", s2.get("status") or "미확인", str(DC / "aihub_terms"),
                 (s2.get("note") or "")[:80], "§2"))
    rows.append(("법령 Open API", s3.get("status") or "미확인", str(DC / "law_api"),
                 f"oc_configured={s3.get('oc_configured')}", "§3"))
    rows.append(("임대차분쟁조정사례집 PDF", s4.get("status") or "미확인", str(s4.get("path") or DC / "cases"),
                 f"pages={s4.get('n_pages')} cases={s4.get('case_count_unique_markers')} bytes={s4.get('bytes')}", "§4"))
    for repo in ("Qwen/Qwen3-8B", "nlpai-lab/KURE-v1", "BAAI/bge-m3"):
        st, sz = dl_status(repo)
        rows.append((repo, st, str(DC / "models" / repo.split("/")[-1]), sz, "§5"))
    rows.append(("교사 후보 *35B* 조사", "있음(조사만)" if s5teacher.get("models") is not None else "미확인",
                 str(DC / "s5_teacher_survey.json"), f"n={len(s5teacher.get('models') or [])}", "§5"))

    lines = []
    lines += ["# DATA_READY_REPORT — 계약서 분석 데이터·모델 준비", "",
              f"- C: 여유 {disk_c()} GB",
              f"- s5 disk_before/after: {s5res.get('disk_before_GB') if isinstance(s5res, dict) else None} / {s5res.get('disk_after_GB') if isinstance(s5res, dict) else None}",
              "", "## 상태 요약표", "",
              "| 항목 | 상태 | 경로 | 건수·크기 | 근거 |",
              "|---|---|---|---|---|"]
    for a, b_, c, d, e in rows:
        lines.append(f"| {a} | {b_} | `{c}` | {d} | {e} |")
    lines.append("")

    # §1 brief
    lines += ["---", "", "## §1. AIHub 계약 서식", ""]
    if s1:
        lines.append(f"- zip {len(s1.get('zips') or [])}개 해제 → `{s1.get('out')}`")
        lines.append(f"- taxonomy: `{s1.get('taxonomy_counts')}`")
        lines.append(f"- 기타고용 비근로성 추정: {s1emp.get('non_laborish_in_기타')} / {s1emp.get('기타고용_total')}")
        lines.append(f"- label_vocab: `{s1.get('label_vocab_csv')}`")
        lines.append("- 조항 텍스트 존재, 다수 플레이스홀더(`○○`,`(@회사명)`). 상세 샘플: `s1_samples.md`")
    lines.append("")

    # §2
    lines += ["---", "", "## §2. 판결서·약관", ""]
    lines.append(f"- status: **{s2.get('status')}**")
    lines.append(f"- note: {s2.get('note')}")
    lines.append(f"- candidates: `{s2.get('candidates_found')}`")
    if s2.get("analysis"):
        lines.append("```json")
        lines.append(json.dumps(s2.get("analysis"), ensure_ascii=False, indent=2)[:6000])
        lines.append("```")
    lines.append("")

    # §3
    lines += ["---", "", "## §3. 법령 Open API", ""]
    lines.append(f"- status: **{s3.get('status')}** / oc_configured={s3.get('oc_configured')} (값은 미출력)")
    guide = s3.get("guide") or {}
    lines.append("### 가이드 근거")
    lines.append("```json")
    lines.append(json.dumps(guide, ensure_ascii=False, indent=2)[:9000])
    lines.append("```")
    for k, v in (s3.get("sections") or {}).items():
        lines.append(f"### {k}")
        if not isinstance(v, dict):
            lines.append(str(v))
            continue
        lines.append(
            f"- 요청수={v.get('요청수')} 성공수={v.get('성공수')} 실패수={v.get('실패수')} "
            f"저장={len(v.get('저장') or [])}"
        )
        if v.get("sample_head_300"):
            lines.append(f"- sample_head_300: {v.get('sample_head_300')}")
        if v.get("hourly_table"):
            lines.append(f"- 최저임금 시간급: `{v.get('hourly_table')}`")
        if v.get("by_keyword"):
            lines.append(f"- 판례 키워드별: `{v.get('by_keyword')}`")
            lines.append(f"- unique_list={v.get('unique_list')} bodies_saved={v.get('bodies_saved')}")
        if v.get("실패"):
            lines.append(f"- 실패 일부: `{json.dumps(v.get('실패')[:5], ensure_ascii=False)[:1500]}`")
        if v.get("law_ids"):
            lines.append(f"- law_ids: `{v.get('law_ids')}`")
    lines.append("")

    # §4
    lines += ["---", "", "## §4. 주택임대차분쟁조정사례집", ""]
    lines.append(f"- status: **{s4.get('status')}**")
    lines.append(f"- path: `{s4.get('path')}` bytes={s4.get('bytes')}")
    lines.append(f"- pages: {s4.get('n_pages')}")
    lines.append(f"- case_count: {s4.get('case_count_unique_markers')}")
    lines.append(f"- first_case_title: {s4.get('first_case_title')}")
    lines.append(f"- first_case_text_head_300: {s4.get('first_case_text_head_300')}")
    lines.append(f"- note: {s4.get('text_layer') or s4.get('source_note')}")
    lines.append("")

    # §5
    lines += ["---", "", "## §5. 모델", "", "### 로컬 기존", ""]
    lines.append("| kind | name | GB | type | path |")
    lines.append("|---|---|---:|---|---|")
    for m in s5local[:30]:
        lines.append(f"| {m.get('kind')} | {m.get('name')} | {m.get('GB')} | {m.get('quant_guess') or m.get('model_type')} | `{m.get('path')}` |")
    lines.append("")
    lines.append("### 다운로드")
    for d in downloads:
        cfg = d.get("config_summary") or d.get("config") or {}
        lines.append(
            f"- `{d.get('repo_id')}` ok={d.get('ok')} GB={d.get('GB')} files={d.get('n_files')} "
            f"err={d.get('error')} type={cfg.get('model_type')} vocab={cfg.get('vocab_size')} "
            f"max_pos={cfg.get('max_position_embeddings')} license={d.get('license')}"
        )
    lines.append("")
    lines.append("### 해시 검증")
    for m in (s5ver.get("models") or []):
        lines.append(
            f"- `{m.get('repo_id') or m.get('path')}` files={m.get('n_files')} "
            f"GB={m.get('total_GB')} incomplete={m.get('incomplete_remaining')}"
        )
        for f in (m.get("files") or [])[:30]:
            lines.append(f"  - {f.get('rel')} bytes={f.get('bytes')} sha256={f.get('sha256')}")
        if len(m.get("files") or []) > 30:
            lines.append(f"  - ... +{len(m['files'])-30} more (see s5_verify.json)")
    lines.append("")
    lines.append("### 교사 후보(다운로드 금지)")
    lines.append(f"- Qwen3-8B vocab: {s5teacher.get('qwen3_8b_vocab')}")
    lines.append("| id | vocab | match8B | experts | license | GGUF | listedGB | estQ4/Q6 |")
    lines.append("|---|---:|:---:|---|---|---|---:|---|")
    for m in s5teacher.get("models") or []:
        if "SAE" in (m.get("id") or ""):
            continue
        lines.append(
            f"| `{m.get('id')}` | {m.get('vocab_size')} | {m.get('vocab_match_qwen3_8b')} | "
            f"{m.get('num_experts')}/{m.get('num_experts_per_tok')} | {m.get('license')} | "
            f"{m.get('gguf_official_repo') or m.get('has_gguf_in_repo')} | {m.get('total_GB_listed')} | "
            f"{m.get('est_Q4_GB')}/{m.get('est_Q6_GB')} |"
        )
    lines.append("")

    lines += ["---", "", "## 사람이 해야 할 일", ""]
    todos = []
    if (s2.get("status") or "").startswith("대기"):
        todos.append("AI Hub 판결서·약관(dataSetSn=580) zip 다운로드 완료 후 `scripts/s2_watch_and_run.py` 재실행")
    if s4.get("text_layer") and "없음" in str(s4.get("text_layer")):
        todos.append("사례집 PDF가 스캔본 — Tesseract OCR 설치 후 사례 수/첫 사례 텍스트 추출, 또는 텍스트 레이어 PDF 확보")
    if s3.get("status") != "calls_completed":
        todos.append("법령 API 수집 완료될 때까지 대기 또는 `s3_full_collect.py` 재실행")
    if any(not d.get("ok") for d in downloads) or not downloads:
        todos.append("모델 다운로드 완료·`s5_verify.json` 해시 확인")
    todos.append("교사 35B급 확정 후 GGUF/원본 선택 다운로드")
    for i, t in enumerate(todos, 1):
        lines.append(f"{i}. {t}")
    if not todos:
        lines.append("- (필수 수동 항목 없음)")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
