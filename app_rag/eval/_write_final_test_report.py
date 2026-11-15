# -*- coding: utf-8 -*-
"""summary.json -> out/FINAL_TEST_REPORT.md"""
from __future__ import annotations

import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
Q = APP / "out" / "quant_test"
d = json.loads((Q / "summary.json").read_text(encoding="utf-8"))
MODELS = ["luna", "EXAONE", "AX"]
VERSIONS = ["none", "neutral", "tuned"]
DOMAINS = ["LAB", "LEASE", "LOAN", "ALL"]
SETTINGS = ["fixed", "best"]

walls = {}
for model in ["EXAONE", "AX", "luna"]:
    for ver in VERSIONS:
        for dom in ["LAB", "LEASE", "LOAN"]:
            for suffix in ["_rows.meta.json", "_partial.meta.json"]:
                mp = Q / f"{model}_{ver}_{dom}{suffix}"
                if not mp.exists():
                    continue
                m = json.loads(mp.read_text(encoding="utf-8"))
                w = m.get("wall") or m.get("wall_s") or m.get("wall_sec")
                if w is None:
                    for k, v in m.items():
                        if "wall" in str(k).lower() and isinstance(v, (int, float)):
                            w = v
                            break
                walls[(model, ver, dom)] = {
                    "n": m.get("n_rows"),
                    "wall": w,
                    "partial": "partial" in suffix,
                }
                break


def cell(key: str):
    return d["tables"].get(key)


def sfmt(s):
    if not isinstance(s, dict):
        return str(s)
    cs = s.get("clean_safe_rate")
    tu = s.get("toxic_not_safe_rate") or s.get("toxic_unsafe_rate")
    if cs is not None or tu is not None:
        return f"clean_safe={cs}; toxic_not_safe={tu}"
    return json.dumps(s, ensure_ascii=False)[:120]


lines: list[str] = []
A = lines.append
A("# FINAL_TEST 보고서")
A("")
A(
    "작업: `docs/tasks/FINAL_TEST.md`. 결과 폴더 `out/quant_test/`. "
    "test는 조건마다 한 번만. freeze 이후 설정·카드·프롬프트를 바꾸지 않았다."
)
A("")
A("## 0. 요약")
A("")
A("- 로컬: EXAONE·AX × none/neutral/tuned × LAB/LEASE/LOAN **전부 완료**(각 463/761/367행).")
A(
    "- GPT(gpt-6-luna): OpenAI 크레딧 소진으로 **부분 결과**. "
    "LAB 3조건은 full rows, LEASE·LOAN은 `*_partial.jsonl`. 누적 **$0.771**."
)
A("- 통계: `eval/final_test_analyze.py` → `out/quant_test/summary.json` (excluded 0).")
A("- EXAONE(8083) leave-up 유지.")
A("")
A("## 1. freeze")
A("")
A("파일: `out/quant_test/freeze.json`")
A("")
A(
    "- 고정 설정: `axok=False num2way=True ne_risky_only=True "
    "num_year_doc=True clean_v2=True R=R0 K=2`"
)
A("- 조건×모델별 best는 freeze의 `best` (none=A단계 sweep, neutral/tuned=FAIR summary).")
A("- 점수 공식 2종: 기본 / 확인필요≥3이면 최대 79점(`score79`).")
A("")

for setting in SETTINGS:
    title = "고정 설정" if setting == "fixed" else "dev 최적 설정"
    A(f"## 2. 기본 표 (test, {title})")
    A("")
    A("비율은 Wilson CI 문자열. 발표용 bootstrap은 §3.")
    A("")
    A(
        "| 모델 | 카드 | 도메인 | 경고포착 | 탐지 | 오탐 | 과잉경고 | "
        "깨끗통과 | 독소놓침 | 점수(기본) | 점수79 | 파싱실패 | 초/장 |"
    )
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for model in MODELS:
        for ver in VERSIONS:
            for dom in DOMAINS:
                t = cell(f"{model}|{ver}|{setting}|{dom}")
                if not t:
                    continue
                cl = t["clause"]
                doc = t["doc"]
                A(
                    f"| {model} | {ver} | {dom} | {cl.get('warn_capture_rate')} | "
                    f"{cl.get('detect_rate')} | {cl.get('fp_rate')} | {cl.get('overwarn_rate')} | "
                    f"{doc.get('clean_pass_rate')} | {doc.get('toxic_miss_n')}/{doc.get('toxic_doc_n')} | "
                    f"{sfmt(t.get('score'))} | {sfmt(t.get('score79'))} | "
                    f"{t.get('parse_fail')} | {t.get('time_sec_per_doc')} |"
                )
    A("")

A("## 3. Bootstrap 95% (계약서 단위, seed=42, n=2000)")
A("")
A("| 모델 | 카드 | 설정 | 도메인 | 지표 | point | lo | hi |")
A("|---|---|---|---|---|---:|---:|---:|")
boots = d.get("boots") or {}
for k in sorted(boots):
    block = boots[k]
    if not isinstance(block, dict):
        continue
    for metric, b in block.items():
        if not isinstance(b, dict) or "point" not in b:
            continue
        A(
            f"| {k.replace('|', ' | ')} | {metric} | "
            f"{b.get('point')} | {b.get('lo')} | {b.get('hi')} |"
        )
A("")

A("## 4. 카드 효과 (McNemar + delta bootstrap)")
A("")
A(
    "해석: bootstrap 구간이 0을 안 걸치면 카드 효과가 있다고 말할 수 있다. "
    "GPT LEASE/LOAN은 partial이라 공통 조각만."
)
A("")
card = d.get("card_fx") or {}
for model in MODELS:
    A(f"### {model}")
    A("")
    fx = card.get(model) or {}
    for cmp_name, label in [
        ("neutral_minus_none", "neutral − none"),
        ("tuned_minus_none", "tuned − none"),
        ("tuned_minus_neutral", "tuned − neutral"),
    ]:
        block = fx.get(cmp_name) or {}
        A(f"#### {label}")
        A("")
        A("| 도메인 | 지표 | Δ point | boot lo | boot hi | covers0 | McNemar p |")
        A("|---|---|---:|---:|---:|---|---:|")
        for dom in ["LAB", "LEASE", "LOAN"]:
            celld = block.get(dom) or {}
            for metric in ["warn_capture", "detect", "fp"]:
                m = celld.get(metric) or {}
                db = m.get("delta_boot") or {}
                mc = m.get("mcnemar") or {}
                A(
                    f"| {dom} | {metric} | {db.get('point')} | {db.get('lo')} | "
                    f"{db.get('hi')} | {db.get('covers_zero')} | {mc.get('p')} |"
                )
        A("")

A("## 5. 모델 비교 (고정 설정, McNemar + Holm)")
A("")
mcmp = d.get("model_cmp") or {}
for ver in VERSIONS:
    A(f"### 카드={ver}")
    A("")
    A("| 도메인 | 쌍 | 지표 | p | p_holm | n | b | c |")
    A("|---|---|---|---:|---:|---:|---:|---:|")
    for dom in ["LAB", "LEASE", "LOAN"]:
        block = ((mcmp.get(ver) or {}).get(dom) or {})
        for pair, cellx in sorted(block.items()):
            for metric in ["warn_capture", "detect", "fp"]:
                m = cellx.get(metric) or {}
                A(
                    f"| {dom} | {pair} | {metric} | {m.get('p')} | {m.get('p_holm')} | "
                    f"{m.get('n')} | {m.get('b')} | {m.get('c')} |"
                )
    A("")

A("## 6. dev vs test (고정 설정)")
A("")
A("| 모델 | 카드 | 도메인 | 표시 |")
A("|---|---|---|---|")
for k, v in sorted((d.get("dev_test") or {}).items()):
    flags = []
    if v.get("dev_warn_outside_test_boot"):
        flags.append("warn:dev밖")
    if v.get("dev_fp_outside_test_boot"):
        flags.append("fp:dev밖")
    if v.get("dev_clean_outside_test_boot"):
        flags.append("clean:dev밖")
    mark = ",".join(flags) if flags else "구간내/해당없음"
    A(f"| {' | '.join(k.split('|'))} | {mark} |")
A("")
A("표시 `dev밖` = dev 값이 test bootstrap 구간 밖 → \"dev에 맞춰졌을 가능성\".")
A("")

A("## 7. 처음 보는 독소 유형 (LAB test only)")
A("")
novel = d.get("novel") or {}
A(
    f"- LAB novel codes ({novel.get('LAB_novel_n')}/{novel.get('LAB_test_toxic_n')} = "
    f"{novel.get('LAB_novel_share')}): `{', '.join(novel.get('LAB_novel') or [])}`"
)
A(
    f"- LEASE/LOAN test-only: 없음 "
    f"(all_in_dev={novel.get('LEASE_all_in_dev')}/{novel.get('LOAN_all_in_dev')})"
)
A("")
A("| 모델 | 카드 | n | 경고포착 | 탐지 |")
A("|---|---|---:|---|---|")
for k, v in sorted((d.get("novel_metrics") or {}).items()):
    A(
        f"| {' | '.join(k.split('|'))} | {v.get('n')} | "
        f"{v.get('warn_capture')} | {v.get('detect')} |"
    )
A("")

A("## 8. 데이터 차이 (참고)")
A("")
A("```json")
A(json.dumps(d.get("data_diff") or {}, ensure_ascii=False, indent=2)[:5000])
A("```")
A("")

A("## 9. 비용·시간")
A("")
cost = d.get("cost") or {}
det = cost.get("detail") or {}
A(f"- GPT spent: **${cost.get('spent_usd')}** / cap $1.5")
A(f"- cache files: {cost.get('n_cache')}")
A(
    f"- tokens in/out/reason: {det.get('prompt_tokens')} / "
    f"{det.get('completion_tokens')} / {det.get('reasoning_tokens')}"
)
A(f"- avg in/out: {det.get('avg_in')} / {det.get('avg_out')}")
A(f"- note: {det.get('note')}")
A("- skip: `gpt_skipped.json` reason=openai_credits_exhausted partial=true")
A("")
A("### 로컬·GPT wall/meta")
A("")
A("| 모델 | 카드 | 도메인 | n_rows | wall_s | partial |")
A("|---|---|---|---:|---:|---|")
for k, v in sorted(walls.items()):
    A(
        f"| {k[0]} | {k[1]} | {k[2]} | {v.get('n')} | {v.get('wall')} | {v.get('partial')} |"
    )
A("")

A("## 10. 미확인·주의")
A("")
A("- GPT LEASE/LOAN은 partial → 해당 도메인 비교는 공통 조각 기준.")
A("- Batch custom_id 해시는 고쳤으나 test는 크레딧 소진으로 regular 중 중단.")
A("- test 결과로 카드/설정을 재튜닝하지 않았다.")
A("- EXAONE(8083) 유지.")
A("")
A("원본 JSON: `out/quant_test/summary.json`")

out = APP / "out" / "FINAL_TEST_REPORT.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("WROTE", out, "lines", len(lines))
sample = cell("EXAONE|none|fixed|LAB")
print("score_keys", list((sample or {}).get("score", {}).keys())[:20] if sample else None)
print("boot_n", len(boots))
