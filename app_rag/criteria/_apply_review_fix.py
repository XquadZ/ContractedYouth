# -*- coding: utf-8 -*-
"""Apply human review fixes to LAB_cards.yaml + LAB_GUIDE.md. No pipeline wiring."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import yaml

CRIT = Path(__file__).resolve().parent
WORK = CRIT.parents[1]
V1 = yaml.safe_load((CRIT / "LAB_cards_v1.yaml").read_text(encoding="utf-8"))
GUIDE = (CRIT / "LAB_GUIDE.md").read_text(encoding="utf-8")

FACT_KEYS = {
    "domain",
    "hourly_wage",
    "monthly_wage",
    "work_days_per_week",
    "work_hours_per_day",
    "break_minutes",
    "probation_months",
    "probation_cut_rate",
    "contract_period",
    "start_date",
    "end_date",
    "date_source",
    "date_missing",
    "date_invalid",
}


def body_len(card: dict) -> int:
    parts = []
    for k in ("title", "safe", "violation", "check_if", "match_keywords", "needs_facts", "basis"):
        v = card.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return len("".join(parts))


def counts(card: dict) -> dict:
    return {
        "violation": len(card.get("violation") or []),
        "check_if": len(card.get("check_if") or []),
        "needs_facts": len(card.get("needs_facts") or []),
    }


# --- build fixed cards from v1 ---
cards = {c["id"]: dict(c) for c in V1}
# deep copy lists
for c in cards.values():
    for k, v in list(c.items()):
        if isinstance(v, list):
            c[k] = list(v)

# 1 LAB-TERM
c = cards["LAB-TERM"]
c["violation"] = ["기간제인데 종료일 공란으로 기간을 확정할 수 없음"]
c["check_if"] = [
    "‘필요 시 연장’만 있고 연장 절차·통지 시점이 없음 → 실제 통지 관행",
    "날짜가 없는 날이거나 앞뒤가 바뀜 → 실제 시작·종료일",
]

# 1 LAB-PLACE
c = cards["LAB-PLACE"]
c["violation"] = []
c["check_if"] = [
    "‘본사 및 지정 사업장’처럼 범위만 있음 → 실제 배치 범위",
    "사용자가 일방적으로 근무지를 바꿀 수 있다고만 적음 → 변경 범위·업무상 필요·근로자 불이익·협의 절차",
]

# 1 LAB-DUTY
c = cards["LAB-DUTY"]
c["violation"] = []
c["check_if"] = [
    "‘기타 지시 업무’만 있음 → 실제 범위가 통상 업무인지",
    "사용자가 업무를 언제든 추가·변경할 수 있다고만 적음 → 변경 범위·업무상 필요·근로자 불이익·협의 절차",
]

# 2 LAB-REST needs_facts: keep hours + 상시 for 제50 line; rest itself doesn't need 상시 alone
c = cards["LAB-REST"]
c["violation"] = [
    "휴게 없음·기준 미달",
    "휴게를 근무 종료 후에만 줌",
    "1일 8시간·1주 40시간 초과를 상시로 정함(상시 5명 이상)",
]
c["check_if"] = [
    "‘한가할 때 휴게’만 있음 → 실제로 쉴 수 있는지",
    "대기시간이 근로시간인지",
]
c["needs_facts"] = ["일_근로시간", "주_근로시간", "상시근로자수"]  # 상시는 40h(제50) 줄용
c["missing_basis"] = ["law:근로기준법:50"]  # corpus 후보

# 2 LAB-HOLIDAY remove 상시근로자수; add check_if
c = cards["LAB-HOLIDAY"]
c["needs_facts"] = ["주_소정근로시간"]
c["check_if"] = [
    "주 소정근로시간이 15시간 이상인지 불명",
    "개근 요건만 있고 요일 미정",
    "주휴수당을 시급에 포함한다고만 적음 → 주휴수당 금액이 구분돼 있고 이를 빼도 최저임금 이상인지",
]

# 2 LAB-DISMISS remove 상시근로자수; fix typo
c = cards["LAB-DISMISS"]
c["match_keywords"] = ["해고", "해고예고", "해고 예고", "즉시해고", "권고사직"]
c["needs_facts"] = ["계속근로기간"]
c["check_if"] = ["계속근로 3개월 미만 등 예외 해당 여부"]

# 4 LAB-PT-OT
c = cards["LAB-PT-OT"]
c["basis"] = ["law:근로기준법:18"]  # 보조
c["missing_basis"] = ["기간제법 제6조 제3항"]
c["check_if"] = [
    "단시간인지(통상근로자 대비 짧은 소정근로) 불명",
    "상시 5명 미만 여부",
]
c["needs_facts"] = ["단시간여부", "약정_소정근로", "상시근로자수"]

# 4 LAB-PENALTY
c = cards["LAB-PENALTY"]
c["check_if"] = [
    "실제 손해 배상 절차만 있는지(예정인지) 구분",
    "교육비 등 회사가 실제로 쓴 비용을 일정 기간 안에 퇴사하면 돌려받는 약정 → 실제 비용인지, 금액·기간이 합리적인지(유효할 수 있음)",
]

# 4 LAB-MINWAGE
c = cards["LAB-MINWAGE"]
c["safe"] = [
    "시간급이 계약 기간에 해당하는 연도의 최저임금(config/min_wage.yaml) 이상",
    "수습 감액은 1년↑계약·3개월 이내·단순노무 제외·10% 이내",
]

# 4 LAB-OT
c = cards["LAB-OT"]
c["safe"] = [
    "연장·야간·휴일근로에 법정 가산(50% 이상)을 지급한다고 적거나, 가산을 배제하는 문구가 없음"
]
# keep 상시근로자수

# LAB-ANNUAL keep 상시근로자수

ordered = [cards[c["id"]] for c in V1]
(CRIT / "LAB_cards.yaml").write_text(
    yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False, width=100),
    encoding="utf-8",
)

# --- guide patches ---
g = GUIDE

# section 0: insert 5인 미만 table after definition / before report phrases
INSERT_TABLE = """
### 5인 미만 사업장 적용 범위 `[지식·원문 대조 필요]`

서버 MST에 시행령 **별표1 본문 텍스트가 없어** 아래는 지식 정리이다. 원문 대조 후 확정한다.

| 구분 | 조문(우리 항목 관련) |
|---|---|
| 4명 이하에도 적용 | 제15조, 제17조, 제18조, 제20조, 제21조, 제22조, 제26조, 제36조, 제43조, 제54조, 제55조 제1항 |
| 4명 이하에는 적용 안 됨 | 제23조 제1항(해고 제한), 제28조(부당해고 구제신청), 제46조(휴업수당), 제50조·제53조(근로시간·연장 한도), 제56조(가산수당), 제60조(연차) |
| 기간제법 제6조(단시간 초과근로 가산) | 상시 **5명 이상** 사업장에 적용 `[지식·원문 대조 필요]` |
| 근로자퇴직급여 보장법 | **1명 이상**이면 적용(계속근로 1년 이상, 주 15시간 이상) `[지식·원문 대조 필요]` |

#### 기존 가이드 문구와 충돌 점검

| 위치(고치기 전) | 문제 | 조치 |
|---|---|---|
| §2 적용 범위 “명시의무는 5인 이상 원칙” | 제17조는 4명 이하에도 적용 | 삭제·정정함 |
| §4 등에서 제54조와 상시 5인을 묶어 서술 | 제54조는 4명 이하에도 적용 | 휴게와 40시간(제50)을 분리 |
| §9·§14 등 제56·제23·제26 적용 | 제56·제23①은 5인↑, 제26은 4명↓에도 적용 | 카드 needs_facts·가이드 적용 범위에 반영 |

"""

if "### 5인 미만 사업장 적용 범위" not in g:
    g = g.replace(
        "### 리포트 맨 위 문구 기준 3단계 (제안값 · 검토 필요)",
        INSERT_TABLE + "### 리포트 맨 위 문구 기준 3단계 (제안값 · 검토 필요)",
        1,
    )

# §1 계약기간
g = g.replace(
    """### 위반 기준
- 종료일이 시작일보다 앞
- 기간제인데 종료일이 비어 기간을 확정 불가

### 확인 필요 조건
- ‘사정에 따라 연장’만 있고 통지 시점·절차 없음 → 실제 관행 확인
""",
    """### 위반 기준
- 기간제인데 종료일이 비어 기간을 확정 불가

### 확인 필요 조건
- ‘사정에 따라 연장’만 있고 통지 시점·절차 없음 → 실제 관행 확인
- 날짜가 없는 날이거나 앞뒤가 바뀜 → 실제 시작·종료일 (정답 라벨 check / L-I03)
""",
    1,
)

# §2 근무장소
g = g.replace(
    """### 위반 기준
- 사용자가 일방적으로 근무지를 변경할 수 있다고만 정함

### 확인 필요 조건
- 광역 ‘지정 사업장’만 있음 → 실제 이동 범위

### 적용 범위
- 명시의무는 5인 이상 원칙. 5인 미만 일부적용은 별표1 `[미확인]`
""",
    """### 위반 기준
- (계약 문장만으로 단정할 위반 없음 — 근무지 일방 변경 문구는 확인 필요)

### 확인 필요 조건
- 광역 ‘지정 사업장’만 있음 → 실제 이동 범위
- 사용자가 일방적으로 근무지를 변경할 수 있다고만 정함 → 변경 범위·업무상 필요·근로자 불이익·협의 절차 (정당한 인사권일 수 있음)

### 적용 범위
- **근로조건 명시·서면 교부(제17조)는 상시 4명 이하에도 적용**된다. `[법]` 제17조 · 위 5인 미만 표
- 배치전환·전근의 정당성은 문장만으로 위반 단정하지 않는다.
""",
    1,
)

# §3 업무
g = g.replace(
    """### 위반 기준
- 사용자가 업무를 수시로 추가·변경할 수 있다고만 정함

### 확인 필요 조건
- ‘기타 지시 업무’만 있는 경우 → 관행상 범위

### 적용 범위
- 명시의무·일방변경 문제는 규모와 별개로 검토. 징계·전직 제한은 제23조(5인 이상 원칙).
""",
    """### 위반 기준
- (계약 문장만으로 단정할 위반 없음 — 업무 일방 추가·변경 문구는 확인 필요)

### 확인 필요 조건
- ‘기타 지시 업무’만 있는 경우 → 관행상 범위
- 사용자가 업무를 수시로 추가·변경할 수 있다고만 정함 → 변경 범위·업무상 필요·근로자 불이익·협의 절차

### 적용 범위
- 제17조 명시의무는 4명 이하에도 적용. 징계·전직 제한(제23조 제1항)은 상시 5명 이상 `[지식·원문 대조 필요]`.
""",
    1,
)

# §4 REST violations / 적용
g = g.replace(
    """### 위반 기준
- 휴게 미부여·미달
- 휴게를 퇴근 후에만 부여
- 상시로 법정 근로시간 초과를 소정으로 고정

### 확인 필요 조건
- ‘한가할 때 휴게’ → 실제 자유이용 가능 여부
- 대기시간 포함 여부
- 상시근로자 5인 여부
""",
    """### 위반 기준
- 휴게 미부여·미달 (제54조 — 4명 이하에도 적용)
- 휴게를 퇴근 후에만 부여
- 1일 8시간·1주 40시간 초과를 상시로 정함(**상시 5명 이상**, 제50조) `[지식·원문 대조 필요]`

### 확인 필요 조건
- ‘한가할 때 휴게’ → 실제 자유이용 가능 여부
- 대기시간 포함 여부
- 40시간 초과 소정인지와 상시 5명 여부(제50조 적용 시)
""",
    1,
)

# MINWAGE year hardcode in guide if any
g = g.replace(
    "시간급 10,320원 이상으로 지급한다(2026년 기준).",
    "계약 기간에 해당하는 연도의 최저임금(config/min_wage.yaml) 이상으로 지급한다.",
)
g = g.replace(
    "시간급이 해당 연도 최저임금 이상(2026년 10,320원)",
    "시간급이 계약 기간에 해당하는 연도의 최저임금(config/min_wage.yaml) 이상",
)

# OT safe phrasing in guide if present
g = g.replace(
    "가산을 배제하지 않음",
    "법정 가산(50% 이상)을 지급한다고 적거나 가산을 배제하는 문구가 없음",
)

(CRIT / "LAB_GUIDE.md").write_text(g, encoding="utf-8")

# --- stats / mapping / jaccard / log ---
before = {c["id"]: counts(c) for c in V1}
after = {c["id"]: counts(c) for c in ordered}
before_nf = sum(before[i]["needs_facts"] for i in before)
after_nf = sum(after[i]["needs_facts"] for i in after)

# fact name mapping for all needs_facts used after
fact_map = {
    "계약_유형": "domain",
    "일_근로시간": "work_hours_per_day",
    "주_근로시간": "없음 (주 근로시간 직접 키 없음; work_days_per_week×work_hours_per_day로 추정 가능하나 미구현)",
    "상시근로자수": "없음",
    "주_소정근로시간": "없음",
    "시급_또는_월급": "hourly_wage / monthly_wage (둘 중)",
    "소정근로시간": "없음 (work_hours_per_day와 유사하나 별키 없음)",
    "수습여부": "없음 (probation_months 있으면 간접)",
    "계약기간_1년이상": "없음 (contract_period·start_date/end_date로 계산 가능하나 미구현)",
    "단순노무여부": "없음",
    "적용연도": "없음 (start_date 연도 추정 가능하나 미구현)",
    "단시간여부": "없음",
    "약정_소정근로": "없음",
    "근로자성": "없음",
    "계속근로기간": "없음",
}
used_facts = sorted({f for c in ordered for f in (c.get("needs_facts") or [])})
missing_in_facts = [f for f in used_facts if "없음" in str(fact_map.get(f, "없음"))]

# char table
lens = [(c["id"], c["title"], body_len(c)) for c in ordered]

# jaccard vs gold sentences
gold_path = WORK / "datasets" / "work" / "v3_1"
gold_sents = []
for p in gold_path.glob("*.jsonl"):
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        for key in ("text", "why", "suggested_revision", "required_context", "violation_name"):
            t = o.get(key)
            if isinstance(t, str) and len(t) >= 15:
                gold_sents.append(t)
            if isinstance(t, list):
                for x in t:
                    if isinstance(x, str) and len(x) >= 15:
                        gold_sents.append(x)


def grams(s: str):
    s = re.sub(r"\s+", "", s)
    return {s[i : i + 3] for i in range(max(0, len(s) - 2))}


def jac(a: str, b: str) -> float:
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


guide_lines = [ln.strip() for ln in g.splitlines() if len(ln.strip()) >= 15]
hits = []
for gl in guide_lines:
    best = 0.0
    best_g = ""
    for gs in gold_sents:
        sc = jac(gl, gs)
        if sc > best:
            best, best_g = sc, gs
    if best >= 0.5:
        hits.append({"guide": gl[:120], "score": round(best, 3), "gold": best_g[:120]})

# toxic-like (violation examples in guide) — flag if overlap with gold toxic texts
# already collected; user said 3 hits from std forms OK

log = []
a = log.append
a("# LAB_CARDS_FIX_LOG")
a("")
a("백업: `LAB_GUIDE_v1.md`, `LAB_cards_v1.yaml`")
a("파이프라인 연결: 하지 않음")
a("")
a("## 1. 라벨 이동 (violation → check_if)")
a("")
a("| 카드 | 전 | 후 |")
a("|---|---|---|")
a("| LAB-TERM | violation에 「시작일이 종료일보다 뒤」 | check_if 「날짜가 없는 날이거나 앞뒤가 바뀜 → 실제 시작·종료일」. violation에는 종료일 공란만 유지 |")
a("| LAB-PLACE | violation 「일방 근무지 변경」 | check_if로 이동(+ 변경 범위·업무상 필요·불이익·협의). violation 비움 |")
a("| LAB-DUTY | violation 「일방 업무 추가·변경」 | check_if로 이동(동일 사실). violation 비움 |")
a("")
a("가이드 §1·§2·§3 본문도 동일하게 수정.")
a("")
a("## 2. needs_facts 축소")
a("")
a(f"- **총 needs_facts 개수(전→후):** {before_nf} → {after_nf}")
a("")
a("| 카드 | 전 needs_facts | 후 needs_facts |")
a("|---|---|---|")
for c in V1:
    cid = c["id"]
    a(f"| {cid} | {c.get('needs_facts') or []} | {cards[cid].get('needs_facts') or []} |")
a("")
a("### 카드 사실 이름 ↔ facts.py 키")
a("")
a("| 카드 사실 이름 | facts.py 키 |")
a("|---|---|")
for f in sorted(fact_map):
    if f in used_facts or f in {x for c in V1 for x in (c.get("needs_facts") or [])}:
        a(f"| {f} | {fact_map[f]} |")
a("")
a("### facts.py가 못 뽑는 사실 (현재 카드에 남은 것 포함)")
a("")
for f in sorted(set(used_facts) | {x for c in V1 for x in (c.get("needs_facts") or [])}):
    mapped = fact_map.get(f, "없음")
    if mapped == "없음" or mapped.startswith("없음"):
        a(f"- {f}")
a("- (참고, 카드에서 빠졌거나 간접만) 단순노무여부, 근로자성, 계속근로기간 — 계속근로기간은 DISMISS에 유지·키는 없음")
a("")
a("### 다음 단계 규칙 (미구현 · 기록만)")
a("")
a("> 카드의 needs_fact가 사실표에 **이미 있으면** 확인 필요로 바꾸지 않고 그 값으로 판단한다.")
a("")
a("## 3. 가이드 오류·5인 미만 표")
a("")
a("| 항목 | 전 | 후 |")
a("|---|---|---|")
a("| §2 명시의무 5인 이상 | 명시의무는 5인 이상 원칙 | 제17조는 4명 이하에도 적용으로 정정 + §0에 적용 범위 표 추가 |")
a("| 5인 미만 표 | 없음 | `[지식·원문 대조 필요]` 표 삽입 |")
a("")
a("## 4. 작은 수정")
a("")
a("| 카드/위치 | 전 | 후 |")
a("|---|---|---|")
a("| LAB-DISMISS keywords | 해고요고 | 해고예고 |")
a("| LAB-PT-OT basis/missing | 기간제법_가산_조항 | missing_basis=`기간제법 제6조 제3항`, basis는 제18 보조, check_if에 상시 5명 미만, needs에 상시근로자수 |")
a("| LAB-HOLIDAY check_if | (주휴수당 포함 시급 없음) | 주휴수당 시급 포함 → 구분·최저임금 확인 |")
a("| LAB-PENALTY check_if | 예정/실손해만 | 교육비 반환 약정 합리성 확인 추가 |")
a("| LAB-REST violation | 40시간 초과 상시 | `(상시 5명 이상)` 명시, missing_basis 제50 corpus 후보 |")
a("| LAB-MINWAGE safe | 2026년 10,320원 고정 | config/min_wage.yaml 연도 기준 |")
a("| LAB-OT safe | 가산을 부정하지 않음 | 법정 가산 지급 명시 또는 배제 문구 없음 |")
a("")
a("## 5. 확인 표")
a("")
a("### 카드 글자 수 (basis·본문 필드, missing_basis 제외)")
a("")
a("| id | title | 글자 | ≤500 |")
a("|---|---|---:|---|")
for i, t, n in lens:
    a(f"| {i} | {t} | {n} | {'Y' if n <= 500 else 'N'} |")
a("")
a(f"최대: {max(lens, key=lambda x: x[2])}")
a("")
a("### violation / check_if / needs_facts 개수 전→후")
a("")
a("| id | v_전 | v_후 | c_전 | c_후 | n_전 | n_후 |")
a("|---|---:|---:|---:|---:|---:|---:|")
for c in V1:
    cid = c["id"]
    b, af = before[cid], after[cid]
    a(
        f"| {cid} | {b['violation']} | {af['violation']} | {b['check_if']} | {af['check_if']} | {b['needs_facts']} | {af['needs_facts']} |"
    )
a("")
a(f"needs_facts 합계: **{before_nf} → {after_nf}**")
a("")
a("### 정답 데이터 문장 겹침 (15자↑, 3-gram Jaccard ≥ 0.5)")
a("")
a(f"걸린 줄 수: {len(hits)}")
a("")
a("| score | guide 줄 | gold 쪽 |")
a("|---:|---|---|")
for h in hits[:20]:
    a(f"| {h['score']} | {h['guide']} | {h['gold']} |")
a("")
a("표준계약서 인용·법 조문 인용과 겹치는 줄은 유지. 독소 예시와 겹치면 다시 쓸 것 — 이번 결과에서 독소 전용 재작성은 필요 시 목록을 보고 판단.")
a("")

(CRIT / "LAB_CARDS_FIX_LOG.md").write_text("\n".join(log), encoding="utf-8")

print("cards", len(ordered))
print("needs_facts", before_nf, "->", after_nf)
print("max_len", max(lens, key=lambda x: x[2]))
print("jaccard_hits", len(hits))
print("missing_fact_keys", [f for f in used_facts if fact_map.get(f, "없음").startswith("없음") or fact_map.get(f) == "없음"])
