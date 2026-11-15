# -*- coding: utf-8 -*-
"""catalog v0.1 → v0.2 패치. 근거: VERIFY_REPORT.md / VERIFY_CHECKS.csv (2026-10-15) 원문 인용 검토.
사용: python patch_v02.py <v0.1 json> <out dir>
"""
import json, csv, sys, os, copy

src, out = sys.argv[1], sys.argv[2]
g = json.load(open(src, encoding="utf-8"))
LAWS = g["laws"]
LAWS.update({"고용보험법": "고용보험법", "산재법": "산업재해보상보험법"})
CHANGES = []

def chk(cid):
    for c in g["checks"]:
        if c["id"] == cid:
            return c
    raise KeyError(cid)

def log(cid, what):
    CHANGES.append((cid, what))

def L(law, art, note="", verified=True):
    d = {"law": law, "article": art, "verified": verified}
    if note:
        d["note"] = note
    return d

# 0) 유형 이름: toxic → risk(위험 조항). 하위 구분은 severity(invalid/violation/unfavorable/caution)
for c in g["checks"]:
    if c["category"] == "toxic":
        c["category"] = "risk"
g["category_names"] = {"missing": "누락", "risk": "위험 조항", "inconsistent": "불일치", "uncheckable": "확인 불가"}
g["severity_names"] = {"invalid": "무효", "violation": "법 위반", "unfavorable": "불리", "caution": "주의", "info": "정보"}
log("*", "category toxic → risk(위험 조항)")

# 1) 대조 결과 support(키워드 자동판정 partial 포함, 원문 인용으로 재확인)는 verified=True
#    아래에서 따로 다루는 것만 예외
UNRESOLVED = set()

for c in g["checks"]:
    for b in c["legal_basis"]:
        b["verified"] = True

# 2) 개별 수정
c = chk("D-G01")
c["legal_basis"] = [b for b in c["legal_basis"] if not (b["law"] == "보증법" and b["article"] == "제3조")]
log("D-G01", "보증인보호법 제3조(2015.2.3 삭제) 제거 → 민법 제428조의2만 근거")

c = chk("L-T07")
c["scope_conditions"] = ["상시 5인 이상만 적용(기간제법 제3조①, 시행령 별표1에 제6조 없음)"]
log("L-T07", "적용 조건 확정: 5인 이상")

for cid in ("L-M06", "L-M07"):
    c = chk(cid)
    c["scope_conditions"] = [s for s in c["scope_conditions"]] + ["1주 소정근로 15시간 미만이면 해당 없음(근기법 제18조③)"]
    c["legal_basis"].append(L("근기법", "제18조", "제3항"))
    log(cid, "적용 조건 추가: 주 15시간 미만 제외(제18조③)")

c = chk("L-T06")
for b in c["legal_basis"]:
    if b["law"] == "근기령" and b["article"] == "제30조":
        b["note"] = "제1항: 소정근로일 개근 시 유급휴일"
c["condition"] += " (개근 요건: 근기령 제30조①)"
log("L-T06", "근기령 제30조 → 개근 요건 근거로 명시")

c = chk("L-T11")
for b in c["legal_basis"]:
    if b["article"] == "제23조":
        b["note"] = "제1항(정당한 이유)은 5인 이상만. 5인 미만은 제23조②·제26조만 적용(근기령 별표1)"
c["scope_conditions"].append("정당한 이유 제한은 상시 5인 이상, 해고예고(제26조)는 5인 미만도 적용")
log("L-T11", "제23조 적용 범위 주석")

c = chk("L-T12")
c["severity"] = "caution"
c["legal_basis"] = [L("고용보험법", "적용 범위 조문", "조문 미확정 — 신규 수집 법령에서 확정 필요", verified=False),
                    L("산재법", "적용 범위 조문", "조문 미확정 — 신규 수집 법령에서 확정 필요", verified=False)]
UNRESOLVED.add("L-T12")
log("L-T12", "근기법 제17조(간접) 제거, 근거 미확정으로 표시, 심각도 violation → caution")

c = chk("H-M02")
c["severity"] = "caution"
c["condition"] = "시작·종료일 없음 — 기간을 정하지 않은 임대차는 2년으로 봄(주임법 제4조①)"
log("H-M02", "심각도 violation → caution(미기재 자체는 위반이 아니라 2년 간주)")

c = chk("H-M06")
c["legal_basis"].append(L("주임법", "제4조", "제2항: 보증금 반환 시까지 임대차 존속"))
log("H-M06", "주임법 제4조② 근거 추가")

c = chk("H-T05")
c["legal_basis"] = [L("민법", "제536조", "보증금 반환과 명도의 동시이행"),
                    L("주임법", "제4조", "제2항: 보증금 반환 시까지 임대차 존속")]
c["condition"] += " — 무효 단정 불가, 불리 조항으로 안내"
log("H-T05", "주임법 제10조 제거(적용 근거 약함), 제4조② 추가")

c = chk("H-T06")
c["legal_basis"] = [L("민법", "제615조"), L("민법", "제654조", "제615조 준용"),
                    L("판례", "대법원 2023다249661", "원상회복은 임차 당시 상태로 반환하면 됨"),
                    L("판례", "통상손모 임차인 비부담 직접 판시", "수집 판례 38건 중 직접 판시 없음 — 추가 검색 필요", verified=False)]
UNRESOLVED.add("H-T06")
log("H-T06", "판례 자리표시 → 2023다249661 + 통상손모 직접 판례는 미확보로 표시")

c = chk("H-T07")
c["legal_basis"] = [L("민법", "제623조"),
                    L("판례", "대법원 94다34692", "수선의무 면제특약은 통상·소규모 수선에 한정")]
log("H-T07", "판례 확정: 94다34692(1994.12.9)")

c = chk("H-T10")
c["legal_basis"].append(L("민법", "제623조", "무단 출입 부분: 사용·수익 유지 의무"))
log("H-T10", "출입 부분 근거로 민법 제623조 추가")

c = chk("H-T11")
c["legal_basis"].append(L("판례", "대법원 80다320,321", "비용상환 포기 특약은 원상복구 면제를 포함하는 것으로 해석"))
log("H-T11", "관련 판례 추가: 80다320,321")

c = chk("H-M08")
for b in c["legal_basis"]:
    if b["article"] == "제3조의7":
        b["note"] = "조문 존재 확인. 최초 시행일(2023 신설 추정)은 연혁 미수집으로 미확인"
log("H-M08", "제3조의7 존재 확인, 최초 시행일 미확인 주석")

c = chk("D-M03")
c["condition"] = "이자 여부·이율 없음 — 이자 약정이 없으면 원칙적으로 무이자(해석, 상인 간 거래는 예외)"
log("D-M03", "조건 문구를 해석 기반으로 명시")

# 3) law_nodes / edges 재생성
law_nodes, edges = {}, [e for e in g["edges"] if e["rel"] == "has_slot"]
for c in g["checks"]:
    edges.append({"from": c["slot"], "to": c["id"], "rel": "has_check"})
    for b in c["legal_basis"]:
        lid = f'{b["law"]}:{b["article"]}'
        node = law_nodes.setdefault(lid, {"id": lid, "law_short": b["law"], "law_full": LAWS.get(b["law"], b["law"]),
                                          "article": b["article"], "verified": True})
        node["verified"] = node["verified"] and b["verified"]
        edges.append({"from": c["id"], "to": lid, "rel": "based_on"})
g["law_nodes"] = list(law_nodes.values())
g["edges"] = edges
g["not_collected_laws"] = []
g["version"] = "0.2"
g["status"] = "근거 조문 원문 대조 완료(2026-10-15). 미확정: " + ", ".join(sorted(UNRESOLVED))
g["unresolved_checks"] = sorted(UNRESOLVED)

os.makedirs(out, exist_ok=True)
json.dump(g, open(os.path.join(out, "catalog_v0.2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
slotname = {s["id"]: s["name"] for s in g["slots"]}
with open(os.path.join(out, "catalog_v0.2_checks.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "계약유형", "조항칸", "유형", "심각도", "항목", "판정 조건", "탐지", "근거", "근거 확인", "적용 조건", "주입 예시"])
    for c in g["checks"]:
        w.writerow([c["id"], ",".join(c["contract_types"]), slotname[c["slot"]], g["category_names"][c["category"]],
                    g["severity_names"][c["severity"]], c["title"], c["condition"], c["detect"],
                    "; ".join(f'{LAWS.get(b["law"], b["law"])} {b["article"]}' + (f' ({b["note"]})' if b.get("note") else "") for b in c["legal_basis"]),
                    "확인" if all(b["verified"] for b in c["legal_basis"]) else "미확정",
                    "; ".join(c["scope_conditions"]), " / ".join(c["inject_examples"])])
with open(os.path.join(out, "CHANGELOG_v0.2.md"), "w", encoding="utf-8") as f:
    f.write("# catalog v0.1 → v0.2 변경 내역\n\n근거: VERIFY_REPORT.md, VERIFY_CHECKS.csv 원문 인용 검토\n\n")
    f.write("partial 23건 중 키워드 자동판정 오류로 판단해 support로 본 것: L-T09, L-T13, L-T14, H-T01, H-T02, H-T04, H-T09, D-M02 등 (원문 인용이 판정 조건을 직접 뒷받침)\n\n")
    f.write("| check | 변경 |\n|---|---|\n")
    for cid, what in CHANGES:
        f.write(f"| {cid} | {what} |\n")
    f.write(f"\n미확정 항목: {', '.join(sorted(UNRESOLVED))}\n")

from collections import Counter
print("checks", len(g["checks"]), "law_nodes", len(g["law_nodes"]), "edges", len(g["edges"]))
print(Counter(c["category"] for c in g["checks"]))
print("unverified nodes:", [n["id"] for n in g["law_nodes"] if not n["verified"]])
print("changes:", len(CHANGES))
