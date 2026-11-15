# -*- coding: utf-8 -*-
"""Merge g1_g7_results.json into DATA_READY_REPORT.md."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
RES = DC / "g1_g7_results.json"
REPORT = DC / "DATA_READY_REPORT.md"


def main():
    r = json.loads(RES.read_text(encoding="utf-8"))
    manual = r.get("manual") or []
    lines = []
    lines.append("")
    lines.append("---")
    lines.append(f"## §G 수집 마무리 (G1–G7) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("성공 판정: HTTP가 아니라 **응답 본문이 기대한 JSON/XML 구조인지**.")
    lines.append("")
    lines.append("### 상태표 (G1–G6)")
    lines.append("")
    lines.append("| 단계 | 상태 | 요약 |")
    lines.append("|---|---|---|")

    def st(name, summary):
        sec = r.get(name) or {}
        if sec.get("_error"):
            return "실패", sec["_error"][:120]
        if not sec.get("_done") and name not in r:
            return "미실행", ""
        return "완료", summary

    g1 = r.get("G1") or {}
    probe = g1.get("probe") or {}
    ok_t = [k for k, v in probe.items() if v.get("ok")]
    fail_t = [k for k, v in probe.items() if not v.get("ok")]
    s, d = st("G1", f"정상 {ok_t} / 실패 {fail_t}; expc_bodies={(g1.get('expc_collect') or {}).get('bodies')}; lstrm_bodies={(g1.get('lstrm_collect') or {}).get('bodies')}")
    lines.append(f"| G1 승인 API 재호출 | {s} | {d} |")

    g2 = r.get("G2") or {}
    nrows = len(g2.get("rows") or [])
    s, d = st("G2", f"표 행 {nrows} (target×키워드 totalCnt vs 저장)")
    lines.append(f"| G2 페이지 상한 | {s} | {d} |")

    g3 = r.get("G3") or {}
    laws = g3.get("laws") or {}
    s, d = st("G3", f"법령 {len(laws)}종, mismatch_rejected={g3.get('mismatch_count')}")
    lines.append(f"| G3 연혁 확정 | {s} | {d} |")

    g4 = r.get("G4") or {}
    s, d = st("G4", f"status={g4.get('status')} candidates={len(g4.get('candidates') or [])}")
    lines.append(f"| G4 AI Hub 580 | {s} | {d} |")

    g5 = r.get("G5") or {}
    s, d = st("G5", g5.get("conclusion") or "")
    lines.append(f"| G5 금전대차계약서 | {s} | {d} |")

    g6 = r.get("G6") or {}
    s, d = st("G6", f"engine={g6.get('engine')} pages={g6.get('n_pages')} hangul_avg={g6.get('avg_hangul_ratio')} quality_ok={g6.get('quality_ok')}")
    lines.append(f"| G6 사례집 OCR | {s} | {d} |")
    lines.append(f"| G7 수동 다운로드 | 완료 | 항목 {len(manual)} → `MANUAL_DOWNLOADS.html` |")
    lines.append("")

    # G1 detail
    lines.append("### §G1. 승인 API 재호출")
    lines.append("")
    lines.append("| target | 결과 | 오류/키 |")
    lines.append("|---|---|---|")
    for name, info in probe.items():
        if info.get("ok"):
            lines.append(f"| `{name}` | JSON/XML 정상 | keys={info.get('keys')} |")
        else:
            lines.append(f"| `{name}` | 권한없음/실패 | {(info.get('error_text') or info.get('error') or '')[:160]} |")
    if g1.get("expc_collect"):
        e = g1["expc_collect"]
        lines.append(f"- expc 수집: 목록응답 {e.get('list_responses')} / unique {e.get('unique_ids')} / 본문 {e.get('bodies')}")
        lines.append(f"  - 샘플: `{(e.get('sample_head_300') or '')[:200]}`")
    if g1.get("lstrm_collect"):
        e = g1["lstrm_collect"]
        lines.append(f"- lstrm 수집: 목록응답 {e.get('list_responses')} / unique {e.get('unique_ids')} / 본문 {e.get('bodies')}")
        lines.append(f"  - 샘플: `{(e.get('sample_head_300') or '')[:200]}`")
    lines.append("")

    # G2
    lines.append("### §G2. 페이지 상한 (totalCnt vs 저장)")
    lines.append("")
    lines.append("| target | 키워드 | totalCnt | 저장 목록 수 | 저장 본문 수 |")
    lines.append("|---|---|---:|---:|---:|")
    for row in g2.get("rows") or []:
        lines.append(
            f"| `{row.get('target')}` | {row.get('keyword')} | {row.get('totalCnt')} | "
            f"{row.get('saved_list')} | {row.get('saved_body')} |"
        )
    lines.append("")

    # G3
    lines.append("### §G3. 연혁 법령 확정")
    lines.append("")
    m = g3.get("method") or {}
    lines.append(f"- 방법: {m.get('list_api')}")
    lines.append(f"- lsHistory 가이드: {m.get('guide_lsHistory')} / {m.get('guide_lsHistory_body')}")
    lines.append(f"- {g3.get('excluded_note')}")
    lines.append(f"- 법령명 불일치 거부(혼입): **{g3.get('mismatch_count', 0)}건** (완전일치만 저장)")
    lines.append("")
    for name, info in laws.items():
        lines.append(f"#### {name} — {info.get('n')}판 · 본문 {info.get('bodies_ok')}")
        lines.append("")
        lines.append("| 시행일 | 공포일 | 공포번호 | MST | 본문저장 | 유형 |")
        lines.append("|---|---|---|---|---|---|")
        for row in info.get("versions") or []:
            lines.append(
                f"| {row.get('시행일')} | {row.get('공포일')} | {row.get('공포번호')} | {row.get('MST')} | "
                f"{row.get('본문저장')} | {row.get('본문유형')} |"
            )
        lines.append("")
        lines.append("시행령·시행규칙 혼입 0건(목록에서 법령명 완전일치만 채택).")
        lines.append("")

    lines.append("#### 검증: 주택임대차보호법 제7조 / 근로기준법 제17조")
    lines.append("")
    for key, v in (g3.get("verify") or {}).items():
        lines.append(f"**{key}** (문구 상이 여부: {v.get('changes_detected')})")
        lines.append("")
        lines.append("| 시행일 | MST | 조문 텍스트(앞부분) |")
        lines.append("|---|---|---|")
        for row in v.get("rows") or []:
            tx = (row.get("조문텍스트") or "").replace("|", "\\|").replace("\n", " ")[:200]
            lines.append(f"| {row.get('시행일')} | {row.get('MST')} | {tx} |")
        lines.append("")

    # G4
    lines.append("### §G4. AI Hub 판결서·약관 (580)")
    lines.append("")
    lines.append(f"- status: **{g4.get('status')}**")
    lines.append(f"- 임시파일(미완료) 무시: {len(g4.get('partial_ignored') or [])}건")
    for c in (g4.get("candidates") or [])[:10]:
        lines.append(f"- candidate: `{c.get('path')}` ({c.get('bytes')})")
    lines.append("")

    # G5
    lines.append("### §G5. 금전대차계약서")
    lines.append("")
    lines.append(f"- 결론: **{g5.get('conclusion')}**")
    lines.append(f"- aihubshell: {g5.get('aihubshell')}")
    lines.append("")
    lines.append("| 대 | 중 | 소 | 건수 |")
    lines.append("|---|---|---|---:|")
    for row in g5.get("taxonomy") or []:
        lines.append(f"| {row.get('대')} | {row.get('중')} | {row.get('소')} | {row.get('count')} |")
    lines.append("")
    lines.append("zip 내부 경로 샘플:")
    for zp, names in (g5.get("zip_entry_samples") or {}).items():
        lines.append(f"- `{zp}`: {names[:8]}")
    lines.append("")

    # G6
    lines.append("### §G6. 주택임대차분쟁조정사례집 OCR")
    lines.append("")
    if g6.get("_error") or g6.get("error"):
        lines.append(f"- 오류: {g6.get('_error') or g6.get('error')}")
    else:
        lines.append(f"- engine: {g6.get('engine')} / GPU={g6.get('use_gpu')} / pages={g6.get('n_pages')}")
        lines.append(f"- 평균 한글비율: {g6.get('avg_hangul_ratio')} / quality_ok={g6.get('quality_ok')}")
        lines.append(f"- 목차 페이지: {g6.get('toc_pages')} / 사례 제목 수≈{g6.get('case_title_count')}")
        if g6.get("stopped_low_quality"):
            lines.append("- **품질 미달(한글비율 < 70%) — 기록만 하고 중단**")
        lines.append("")
        for s in g6.get("samples") or []:
            lines.append(f"**p{s.get('page')}** hangul={s.get('hangul_ratio'):.2f} broken={s.get('broken_ratio'):.2f}")
            lines.append("```")
            lines.append((s.get("head_300") or "")[:300])
            lines.append("```")
        lines.append("")
        lines.append("사례 제목 샘플:")
        for t in (g6.get("case_titles_sample") or [])[:30]:
            lines.append(f"- {t}")
    lines.append("")

    # G7
    lines.append("### §G7. 수동 다운로드")
    lines.append("")
    lines.append(f"- 파일: `data_contract/MANUAL_DOWNLOADS.html`")
    lines.append(f"- after_manual: `python data_contract\\scripts\\after_manual.py`")
    lines.append(f"- 항목 수: **{len(manual)}**")
    for it in manual:
        lines.append(f"  - {it.get('title')}")
    lines.append("")

    lines.append("## 사람이 할 일")
    lines.append("")
    if not manual:
        lines.append("- 수동 작업 없음 (`MANUAL_DOWNLOADS.html` 확인)")
    else:
        lines.append(f"- `MANUAL_DOWNLOADS.html` 항목 **{len(manual)}**개:")
        for it in manual:
            lines.append(f"  - {it.get('title')}")
    lines.append("")

    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    # update top status table rows if present
    # append G section (replace previous G section)
    marker = "## §G 수집 마무리"
    if marker in old:
        old = old.split(marker)[0].rstrip() + "\n"
    # also trim old "사람이 할 일" at end if duplicated — keep earlier ones, new one at end
    # Update AIHub 판결서 row briefly
    if g4.get("status"):
        old = re.sub(
            r"(\| AIHub 판결서·약관 \| )[^|]+(\|)",
            rf"\1{g4.get('status')}\2",
            old,
            count=1,
        )
    if g6.get("ok"):
        old = re.sub(
            r"(\| 임대차분쟁조정사례집 PDF \| )[^|]+(\|)",
            rf"\1OCR_{'ok' if g6.get('quality_ok') else 'low_quality'}\2",
            old,
            count=1,
        )

    REPORT.write_text(old + "\n".join(lines), encoding="utf-8")
    print("updated", REPORT)


if __name__ == "__main__":
    main()
