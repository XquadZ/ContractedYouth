# -*- coding: utf-8 -*-
"""Merge fix_abcdef_results into DATA_READY_REPORT.md (append/replace A-F section)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DC = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract")
RES = DC / "fix_abcdef_results.json"
REPORT = DC / "DATA_READY_REPORT.md"


def md_escape(s):
    return (s or "").replace("|", "\\|")


def main():
    r = json.loads(RES.read_text(encoding="utf-8"))
    lines = []
    lines.append("")
    lines.append("---")
    lines.append(f"## 검토 수정 A–F (성공=기대 JSON 구조) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("판정 기준: HTTP 상태코드가 아니라 **응답 본문이 기대한 JSON 키/구조를 갖는지**.")
    lines.append("")

    A = r["A"]
    lines.append("### A. 3-5 법령해석례 · 3-6 공정위 · 3-7 법령용어")
    lines.append("")
    lines.append("#### 기존 저장 HTML 오류 문구")
    for label, msgs in A.get("old_html_errors", {}).items():
        lines.append(f"- **{label}**")
        if not msgs:
            lines.append("  - (HTML 파일 없음/미검출)")
        for m in msgs:
            lines.append(f"  - `{m['file']}`: {m['error_text'][:240]}")
    lines.append("")
    if A.get("expc_unauthorized"):
        e = A["expc_unauthorized"]
        lines.append(f"- **target=expc**: 미승인. 오류: {e.get('error_text','')[:200]}")
        lines.append(f"  - 가이드: {e.get('guide')}")
        lines.append(f"  - 조치: {e.get('conclusion')}")
    lines.append("")
    lines.append("| 기관/API | target | 목록(JSON) | 본문 | 샘플 앞 300자 |")
    lines.append("|---|---|---:|---:|---|")
    for org, info in A.get("ministry", {}).items():
        samp = (info.get("sample_head_300") or "")[:80].replace("\n", " ")
        lines.append(
            f"| {org} | `{info.get('target') or info.get('target_tried')}` | "
            f"{info.get('list_responses_ok', 0) if info.get('ok') else 'FAIL'} | "
            f"{info.get('bodies_ok', 0) if info.get('ok') else '—'} | {md_escape(samp)} |"
        )
    f = A.get("ftc", {})
    lines.append(
        f"| 공정위 | `ftc` | {f.get('list_responses_ok')} | {f.get('bodies_ok')} | "
        f"{md_escape((f.get('sample_head_300') or '')[:80].replace(chr(10),' '))} |"
    )
    L = A.get("lstrm", {})
    lines.append(f"| 법령용어(원) | `lstrm` | {'OK' if L.get('ok') else '미승인'} | — | {md_escape((L.get('error_text') or '')[:80])} |")
    R = A.get("lstrmRlt", {})
    lines.append(
        f"| 법령용어연계 | `lstrmRlt` | {R.get('list_or_service_ok')} | {R.get('bodies_ok')} | "
        f"{md_escape((R.get('sample_head_300') or '')[:80].replace(chr(10),' '))} |"
    )
    lines.append("")

    B = r["B"]
    lines.append("### B. 연혁 (법령명 완전일치 · 2022-01-01 이후 시행판)")
    lines.append("")
    gh = B.get("guide_history_api", {})
    lines.append("- 가이드 목록: " + gh.get("guideList", ""))
    lines.append(
        f"- **법령 연혁 API**: target=`lsHistory`, type=**HTML only** "
        f"(목록: [{gh.get('lsHistory_list',{}).get('url','')}]({gh.get('lsHistory_list',{}).get('url','')}), "
        f"본문: [{gh.get('lsHistory_body',{}).get('url','')}]({gh.get('lsHistory_body',{}).get('url','')}))"
    )
    lines.append(f"- 구조화 본문: {gh.get('also_used')}")
    if B.get("note_현행_fallback"):
        lines.append(f"- 참고: {B['note_현행_fallback']}")
    lines.append("")
    mism = B.get("mismatched_previous_bodies") or []
    lines.append(f"#### 이전 본문 중 법령명 불일치(시행령·시행규칙 혼입 등): {len(mism)}건")
    for m in mism[:30]:
        lines.append(f"- `{m['file']}`: expected=`{m['expected']}` actual=`{m['actual_법령명']}`")
    if len(mism) > 30:
        lines.append(f"- … 외 {len(mism)-30}건")
    lines.append("")
    for name, info in B.get("laws", {}).items():
        lines.append(f"#### {name} — 시행판 {info.get('n_versions')} · 본문 {info.get('bodies_ok')}")
        lines.append("")
        lines.append("| 시행일 | 공포번호 | MST |")
        lines.append("|---|---|---|")
        for row in info.get("table") or []:
            lines.append(f"| {row.get('시행일')} | {row.get('공포번호')} | {row.get('MST')} |")
        lines.append("")

    C = r["C"]
    lines.append("### C. 최저임금 고시 (적용 최저임금 고시, nw=1·2, 선원 제외)")
    lines.append("")
    lines.append(f"- 검색어: `{C.get('query')}` · nw={C.get('nw')}")
    if C.get("excluded_선원"):
        lines.append(f"- 제외(선원): {len(C['excluded_선원'])}건 예) {C['excluded_선원'][:3]}")
    lines.append("")
    lines.append("| 연도 | 고시명 | 시간급 | 근거 인용 |")
    lines.append("|---|---|---|---|")
    for y, info in sorted(C.get("years", {}).items()):
        lines.append(
            f"| {y} | {md_escape(str(info.get('name') or ''))} | {info.get('hourly') or '—'} | "
            f"{md_escape(str(info.get('evidence') or info.get('note') or info.get('error') or '')[:120])} |"
        )
    lines.append("")

    D = r["D"]
    lines.append("### D. 판례 특약/약정 필터")
    lines.append("")
    lines.append("```python")
    lines.append(D.get("filter_code", ""))
    lines.append("```")
    e400 = D.get("existing_400", {})
    lines.append(
        f"- 기존 본문 {e400.get('n_files')}건 중 판시사항/판결요지에 특약|약정: "
        f"**{e400.get('pass_판시사항_or_판결요지_특약_약정')}**건"
    )
    ff = D.get("full_list_fetch", {})
    lines.append(
        f"- 목록 unique {ff.get('unique_list_n')}건 전체 필터 적용 → 통과 본문 **{ff.get('pass_count')}**건 "
        f"(신규 fetch {ff.get('bodies_fetched_new_or_reused')})"
    )
    lines.append("")
    lines.append("| 키워드 | 필터 통과 수 |")
    lines.append("|---|---:|")
    for kw, n in sorted(D.get("by_keyword_pass", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {kw} | {n} |")
    lines.append("")

    E = r["E"]
    lines.append("### E. AI Hub 금전소비대차 · 금전대차계약서 소분류")
    lines.append("")
    lines.append(f"- 금전대차계약서 소분류 존재: **{E.get('has_금전대차계약서_detail')}** → {E.get('conclusion')}")
    lines.append("")
    lines.append("| 대 | 중 | 소 | 건수 |")
    lines.append("|---|---|---|---:|")
    for row in E.get("money_taxonomy") or []:
        lines.append(f"| {row.get('대')} | {row.get('중')} | {row.get('소')} | {row.get('count')} |")
    lines.append("")
    lines.append("원본 zip 목록:")
    for z in E.get("source_zips") or []:
        lines.append(f"- `{z['zip']}` ({z['bytes']:,} bytes)")
    lines.append("")

    F = r["F"]
    lines.append("### F. 모델 해시 (HF LFS oid sha256 ↔ 로컬)")
    lines.append("")
    lines.append("| repo | file | local_sha256 | hf_lfs_sha256 | match |")
    lines.append("|---|---|---|---|---|")
    for row in F.get("hash_compare") or []:
        lines.append(
            f"| {row['repo']} | `{row['file']}` | `{row['local_sha256']}` | "
            f"`{row.get('hf_lfs_sha256') or '—'}` | {row.get('match')} |"
        )
    lines.append("")
    lines.append(f"incomplete_remaining = **{F.get('incomplete_n')}** (삭제하지 않음)")
    for inc in F.get("incomplete_remaining_paths") or []:
        lines.append(f"- `{inc['path']}` ({inc['bytes']:,} bytes)")
    lines.append("")

    # append to report
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    marker = "## 검토 수정 A–F"
    if marker in old:
        old = old.split(marker)[0].rstrip() + "\n"
    REPORT.write_text(old + "\n".join(lines), encoding="utf-8")
    print("updated", REPORT)


if __name__ == "__main__":
    main()
