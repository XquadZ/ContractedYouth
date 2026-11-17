# -*- coding: utf-8 -*-
"""리포트 조립. 확률·점수는 넣지 않는다."""
from __future__ import annotations

import re

from rag.dates import DATE_INVALID_TMPL, DATE_MISSING_NOTE

DATE_ORDER_NOTE = "계약 종료일이 시작일보다 빨라요."
from rag.paths import REQUIRED_ITEMS
from rag.yamlutil import load as load_yaml

DISCLAIMER = "이 결과는 계약서 이해를 돕는 정보이며 법률 자문이 아닙니다."
HELPLINE = "고용노동부 1350, 대한법률구조공단 132"


def build_report(payload: dict) -> dict:
    findings = payload.get("findings") or []
    domain = payload.get("domain") or "LAB"
    facts = payload.get("facts") or {}
    segments = payload.get("segments") or []
    counts = {"위반": 0, "위험": 0, "확인 필요": 0, "문제 없음": 0}
    for row in findings:
        v = row.get("verdict") or "확인 필요"
        counts[v] = counts.get(v, 0) + 1
    critical = []
    for row in findings:
        for label in row.get("critical") or []:
            critical.append(
                {
                    "label": label,
                    "segment_id": row.get("segment_id"),
                    "quote": row.get("contract_quote") or row.get("text") or "",
                    "verdict": row.get("verdict"),
                }
            )
    cards = [_card(row) for row in findings]
    doc_text = "\n".join((s.get("text") or "") for s in segments)
    for extra in _fact_conflict_cards(facts, doc_text=doc_text):
        cards.append(extra)
        v = extra.get("verdict") or "확인 필요"
        counts[v] = counts.get(v, 0) + 1
    missing = missing_items(findings, domain)
    mismatches = find_mismatches(segments, facts)
    needs = []
    doc_questions = []
    clause_checks = []
    for row in findings:
        nf = row.get("needs_fact")
        action = row.get("needs_fact_action")
        if nf:
            needs.append({
                "segment_id": row.get("segment_id"),
                "fact": nf,
                "action": action,
            })
        # blocking_if로 조항이 '확인 필요'가 된 경우 → 조항 확인 필요
        if action == "blocking_if" or (
            row.get("verdict") == "확인 필요" and "blocking_if" in (row.get("notes") or [])
        ):
            clause_checks.append({
                "segment_id": row.get("segment_id"),
                "fact": nf,
                "article_title": row.get("article_title") or "",
                "verdict": row.get("verdict"),
                "kind": "조항 확인 필요",
            })
        # 비-blocking needs_fact → 직접 확인할 것(문서 질문). 판정은 바꾸지 않음.
        dq = row.get("doc_question")
        if action == "doc_question" or dq:
            doc_questions.append({
                "segment_id": row.get("segment_id"),
                "fact": (dq or {}).get("fact") if isinstance(dq, dict) else nf,
                "ax_verdict": (dq or {}).get("ax_verdict") if isinstance(dq, dict) else row.get("ax_verdict"),
                "article_title": row.get("article_title") or "",
                "verdict": row.get("verdict"),
                "kind": "문서 질문",
            })
    requests = [c["suggestion"] for c in cards if c.get("suggestion")]
    date_note = DATE_MISSING_NOTE if facts.get("date_missing") else ""
    if date_note:
        requests = [date_note] + requests
    # 법령 버전 안내
    law_as_of = facts.get("start_date") or facts.get("contract_date") or ""
    version_notices: list[str] = []
    for row in findings:
        for n in row.get("version_notices") or []:
            if n and n not in version_notices:
                version_notices.append(n)
        for cv in row.get("card_versions") or []:
            ef = cv.get("effective_from")
            if ef and cv.get("version") is not None:
                note = f"계약일 기준(시행 {ef}) 적용"
                # 과거 버전 표시는 카드에 버전이 있을 때만
                if note not in version_notices and cv.get("apply_rule") == "contract_date":
                    # 리포트 카드별 표시용 — 전역 안내는 예정 개정만
                    pass
        for n in version_notices:
            if n and n not in requests and ("바뀌어요" in n or "다를 수 있어요" in n or "계약일을 찾지" in n):
                requests.append(n)
    from rag.score import compute_score

    # 누락·불일치: 목록이 있으면 반영, 없으면 미반영(0)
    n_missing = len(missing or [])
    n_mismatch = len(mismatches or [])
    score_info = compute_score(
        n_violation=counts.get("위반", 0),
        n_risk=counts.get("위험", 0),
        n_check=counts.get("확인 필요", 0),
        n_missing=n_missing,
        n_mismatch=n_mismatch,
        missing_reflected=True,
        mismatch_reflected=True,
        check_cap79=True,
    )
    return {
        "title": "계약서 점검 리포트",
        "model": payload.get("model") or "A.X-4.0-Light",
        "domain": domain,
        "summary": {
            "n_segments": len(findings),
            "n_violation": counts.get("위반", 0),
            "n_risk": counts.get("위험", 0),
            "n_review": counts.get("확인 필요", 0),
            "n_ok": counts.get("문제 없음", 0),
            "n_clause_check": len(clause_checks),
            "n_doc_question": len(doc_questions),
        },
        "score": score_info["score"],
        "grade": score_info["grade"],
        "score_detail": score_info,
        "critical": critical,
        "cards": cards,
        "missing": missing,
        "mismatches": mismatches,
        "needs_fact": needs,
        "직접_확인할_것": {
            "조항_확인_필요": clause_checks,
            "문서_질문": doc_questions,
        },
        "clause_checks": clause_checks,
        "doc_questions": doc_questions,
        "next_actions": {
            "requests": requests,
            "helpline": HELPLINE,
        },
        "disclaimer": DISCLAIMER,
        "date_note": date_note,
        "법령_기준일": law_as_of or None,
        "law_as_of": law_as_of or None,
        "card_versions_used": [
            cv
            for row in findings
            for cv in (row.get("card_versions") or [])
            if cv.get("version") is not None
        ],
        "version_notices": version_notices,
        "facts": {k: v for k, v in facts.items() if k != "raw"},
        "stats": payload.get("stats") or {},
        "analyze_model": payload.get("analyze_model"),
        "demo_notice": payload.get("demo_notice"),
    }


def _pct_phrase(rate: float) -> str:
    pct = float(rate) * 100.0
    if abs(pct - round(pct)) < 1e-9:
        return f"연 {int(round(pct))}%"
    return f"연 {pct:g}%"


def _fact_conflict_cards(facts: dict, doc_text: str = "") -> list[dict]:
    """문서 안 이자율·원금이 서로 다를 때 확인 필요 카드 추가.
    원금은 '이번/추가/총 … 차용' 합산 관계면 불일치로 보지 않는다."""
    out: list[dict] = []
    rates = facts.get("interest_rates") or []
    uniq_rates = sorted({float(r["rate"]) for r in rates if r.get("rate") is not None})
    if len(uniq_rates) >= 2:
        joined = ", ".join(_pct_phrase(r) for r in uniq_rates)
        out.append(
            {
                "segment_id": "fact:interest_rate_conflict",
                "order": None,
                "article_title": "이자율 불일치",
                "verdict": "확인 필요",
                "contract_quote": "",
                "clause_text": "",
                "evidence": [],
                "gap": "",
                "why": f"같은 계약서 안에 이자율이 서로 다르게 적혀 있습니다({joined}). 어느 것이 실제 약정인지 확인하세요.",
                "suggestion": "어느 이자율이 실제 약정인지 확인하세요.",
                "state": "ok",
                "notes": ["interest_rate_conflict"],
                "anomaly": [],
                "ax_verdict": None,
                "rule": {},
                "card_versions": [],
                "law_version_note": None,
                "critical": [],
                "used_ids": [],
                "passed_ids": [],
            }
        )
    principals = facts.get("principals") or []
    uniq_p = sorted({int(p["value"]) for p in principals if p.get("value") is not None})
    if len(uniq_p) >= 2 and not _principals_are_cumulative(doc_text, uniq_p, principals):
        joined_p = ", ".join(f"{v:,}원" for v in uniq_p)
        out.append(
            {
                "segment_id": "fact:principal_conflict",
                "order": None,
                "article_title": "원금 불일치",
                "verdict": "확인 필요",
                "contract_quote": "",
                "clause_text": "",
                "evidence": [],
                "gap": "",
                "why": f"같은 계약서 안에 원금이 서로 다르게 적혀 있습니다({joined_p}). 어느 것이 실제 약정인지 확인하세요.",
                "suggestion": "어느 원금이 실제 약정인지 확인하세요.",
                "state": "ok",
                "notes": ["principal_conflict"],
                "anomaly": [],
                "ax_verdict": None,
                "rule": {},
                "card_versions": [],
                "law_version_note": None,
                "critical": [],
                "used_ids": [],
                "passed_ids": [],
            }
        )
    return out


def _principals_are_cumulative(text: str, values: list[int], principals: list[dict] | None = None) -> bool:
    """이번/추가/총 차용 문맥에서 큰 금액이 작은 금액 합과 같으면 True."""
    t = text or ""
    blob = t
    if principals:
        blob += "\n" + "\n".join((p.get("snippet") or "") for p in principals)
    if not re.search(r"(?:이번|추가|총).{0,24}차용", blob):
        return False
    vals = sorted({int(v) for v in values})
    if len(vals) < 2:
        return False
    largest = vals[-1]
    smaller = vals[:-1]
    if sum(smaller) == largest:
        return True
    # 총액이 본문에 있고 principals 합과 같으면 합산 관계
    total_sum = sum(vals)
    from rag.facts import hangul_amount_to_int, _to_int, NUM

    for m in re.finditer(rf"총\s*([가-힣]+|{NUM})\s*원", blob):
        raw = m.group(1)
        tot = _to_int(raw) if re.search(r"\d", raw) else hangul_amount_to_int(raw)
        if tot and int(tot) == total_sum:
            return True
        if tot and int(tot) == largest:
            return True
    return False



_INTEREST_CAP_NOTICE_ID = "notice:이자제한법 제2조제1항의 최고이자율에 관한 규정:본문"
_INTEREST_CAP_NOTICE_CACHE: dict | None = None


def _interest_cap_notice() -> dict | None:
    """corpus에 있는 최고이자율 규정(연 20%) 레코드. 검색 설정은 건드리지 않고 표시용."""
    global _INTEREST_CAP_NOTICE_CACHE
    if _INTEREST_CAP_NOTICE_CACHE is not None:
        return _INTEREST_CAP_NOTICE_CACHE or None
    try:
        from rag.paths import CORPUS
        import json

        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        records = data.get("records") or data if isinstance(data, list) else (data.get("records") or [])
        for rec in records:
            if rec.get("id") == _INTEREST_CAP_NOTICE_ID:
                _INTEREST_CAP_NOTICE_CACHE = {
                    "id": rec.get("id"),
                    "quote": (rec.get("text") or "").strip(),
                    "title": rec.get("title") or "이자제한법 제2조제1항의 최고이자율에 관한 규정",
                    "source_tag": "[법령]",
                    "doc_type": rec.get("doc_type") or "시행령",
                }
                return _INTEREST_CAP_NOTICE_CACHE
    except Exception:
        _INTEREST_CAP_NOTICE_CACHE = {}
        return None
    _INTEREST_CAP_NOTICE_CACHE = {}
    return None


def _attach_interest_cap_evidence(evidence: list) -> list:
    """이자제한법 제2조 근거가 있으면 최고이자율 규정(연 20%)을 함께 붙인다."""
    evs = list(evidence or [])
    if not evs:
        return evs
    has_art2 = any(
        ("이자제한법" in ((e.get("title") or "") + (e.get("id") or "")) and "제2조" in ((e.get("title") or "") + (e.get("id") or "")))
        for e in evs
    )
    if not has_art2:
        return evs
    if any(_INTEREST_CAP_NOTICE_ID in (e.get("id") or "") for e in evs):
        return evs
    notice = _interest_cap_notice()
    if notice:
        evs.append(dict(notice))
    return evs


def _card(row: dict) -> dict:
    law_note = None
    for cv in row.get("card_versions") or []:
        if cv.get("effective_from") and cv.get("version") is not None:
            if cv.get("apply_rule") in ("contract_date", "performance_period"):
                law_note = f"계약일 기준(시행 {cv.get('effective_from')}) 적용"
            elif cv.get("apply_rule") == "in_force":
                law_note = f"현행 기준(시행 {cv.get('effective_from')}) 적용"
            break
    evidence = _attach_interest_cap_evidence(row.get("evidence") or [])
    return {
        "segment_id": row.get("segment_id"),
        "order": row.get("order"),
        "article_title": row.get("article_title") or "",
        "verdict": row.get("verdict"),
        "contract_quote": row.get("contract_quote") or "",
        "clause_text": row.get("text") or "",
        "evidence": evidence,
        "gap": row.get("gap") or "",
        "why": row.get("why") or "",
        "suggestion": row.get("suggestion") or "",
        "state": row.get("state"),
        "notes": row.get("notes") or [],
        "anomaly": row.get("anomaly") or [],
        "ax_verdict": row.get("ax_verdict"),
        "rule": row.get("rule") or {},
        "card_versions": row.get("card_versions") or [],
        "law_version_note": law_note,
        "needs_fact": row.get("needs_fact"),
        "needs_fact_action": row.get("needs_fact_action"),
        "doc_question": row.get("doc_question"),
        "latency_ms": row.get("latency_ms"),
        "passed_ids": [h["id"] for h in (row.get("hits") or [])],
        "used_ids": [e["id"] for e in evidence],
        "filter_mode": row.get("filter_mode"),
        "std_items": row.get("std_items") or [],
        "critical": row.get("critical") or [],
    }


def _load_required() -> dict:
    try:
        spec = load_yaml(REQUIRED_ITEMS) or {}
        if spec.get("LAB"):
            return spec
    except Exception:
        spec = {}
    current = None
    domain = None
    out = {"LAB": [], "LEASE": [], "LOAN": []}
    for raw in REQUIRED_ITEMS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and not line.startswith("-"):
            domain = line[:-1]
            continue
        if line.startswith("- id:") and domain:
            current = {"id": line.split(":", 1)[1].strip()}
            out.setdefault(domain, []).append(current)
        elif current is not None and line.startswith("name:"):
            current["name"] = line.split(":", 1)[1].strip()
        elif current is not None and line.startswith("basis:"):
            current["basis"] = line.split(":", 1)[1].strip()
    return out


def missing_items(findings: list[dict], domain: str) -> list[dict]:
    spec = _load_required()
    required = spec.get(domain) or []
    present = set()
    for row in findings:
        for sid in row.get("std_items") or []:
            present.add(sid)
        blob = (row.get("article_title") or "") + (row.get("text") or "")
        for item in required:
            name = item.get("name") or ""
            if name and name[:2] in blob:
                present.add(item["id"])
    out = []
    for item in required:
        iid = item["id"]
        if iid in present:
            continue
        out.append({"id": iid, "name": item.get("name"), "basis": item.get("basis"), "status": "not_present"})
    return out


def find_mismatches(segments: list[dict], facts: dict) -> list[dict]:
    """meta 조각과 사실표: 숫자·한글 금액, 날짜, 이름."""
    out = []
    meta = "\n".join(s.get("text") or "" for s in segments if s.get("segment_type") == "meta")
    hangul_money = re_hangul_money(meta)
    for label, key in (("시급", "hourly_wage"), ("월급", "monthly_wage"), ("보증금", "deposit"), ("월세", "monthly_rent")):
        num = facts.get(key)
        if num is None or not hangul_money:
            continue
        for korean, value in hangul_money:
            if abs(value - float(num)) > 0 and korean in meta and str(int(num)) in meta:
                if value != float(num):
                    out.append({"type": "money_mismatch", "label": label, "hangul": korean, "hangul_value": value, "digits": num})
    names = re.findall(r"(사업주|근로자|임대인|임차인)\s*[:=]?\s*([가-힣]{2,5})", meta)
    seen = {}
    for role, name in names:
        prev = seen.get(role)
        if prev and prev != name:
            out.append({"type": "name_mismatch", "role": role, "a": prev, "b": name})
        seen[role] = name
    dates = re.findall(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", meta)
    for y, m, d in dates:
        yy, mm, dd = int(y), int(m), int(d)
        bad = mm < 1 or mm > 12 or dd < 1 or dd > 31
        if bad:
            out.append({"type": "date_error", "value": f"{yy}-{mm:02d}-{dd:02d}"})
    for raw in facts.get("date_invalid") or []:
        out.append({"type": "date_invalid", "value": raw, "note": DATE_INVALID_TMPL.format(raw=raw)})
    start = facts.get("start_date")
    end = facts.get("end_date")
    if start and end and str(end) < str(start):
        out.append({"type": "date_order", "start": start, "end": end, "note": DATE_ORDER_NOTE})
    return out


def re_hangul_money(text: str) -> list[tuple[str, int]]:
    import re

    unit = {"만": 10000, "억": 100000000, "천": 1000, "백": 100}
    out = []
    for match in re.finditer(r"([일이삼사오육칠팔구십백천만억]+)\s*원", text or ""):
        raw = match.group(1)
        try:
            out.append((raw, _hangul_to_int(raw)))
        except Exception:
            continue
    return out


def _hangul_to_int(s: str) -> int:
    digits = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
    total = 0
    chunk = 0
    num = 0
    for ch in s:
        if ch in digits:
            num = digits[ch]
        elif ch == "십":
            chunk += (num or 1) * 10
            num = 0
        elif ch == "백":
            chunk += (num or 1) * 100
            num = 0
        elif ch == "천":
            chunk += (num or 1) * 1000
            num = 0
        elif ch == "만":
            total += (chunk + num or 1) * 10000
            chunk = 0
            num = 0
        elif ch == "억":
            total += (chunk + num or 1) * 100000000
            chunk = 0
            num = 0
    return total + chunk + num


def to_markdown(report: dict) -> str:
    s = report["summary"]
    law_as_of = report.get("법령_기준일") or report.get("law_as_of")
    lines = [
        f"# {report['title']}",
        "",
        f"- 모델: {report['model']}",
        f"- 유형: {report.get('domain')}",
        f"- 위반 {s['n_violation']} / 위험 {s['n_risk']} / 확인 필요 {s['n_review']} / 문제 없음 {s['n_ok']}",
    ]
    if law_as_of:
        lines.append(f"- 법령 기준일: {law_as_of}")
    for n in report.get("version_notices") or []:
        lines.append(f"- 참고: {n}")
    lines += [
        "",
        "## 치명 항목",
        "",
    ]
    if report.get("critical"):
        for item in report["critical"]:
            lines.append(f"- **{item['label']}** ({item.get('segment_id')}): {item.get('quote')}")
    else:
        lines.append("- 해당 없음")
    lines += ["", "## 조항 카드", ""]
    for card in report.get("cards") or []:
        lines += [
            f"### {card.get('order')}. {card.get('verdict')} · {card.get('article_title') or card.get('segment_id')}",
            "",
            "**계약서 원문 인용**",
            "",
            card.get("contract_quote") or card.get("clause_text") or "",
            "",
            "**표준·법 기준**",
            "",
        ]
        if card.get("evidence"):
            for ev in card["evidence"]:
                lines.append(f"- {ev.get('source_tag')} {ev.get('id')} {ev.get('title')}: {ev.get('quote')}")
        else:
            lines.append("- 근거 없음")
        lines += ["", "**차이**", "", card.get("gap") or "", "", "**왜 문제인지**", "", card.get("why") or "", ""]
        if card.get("suggestion"):
            lines += ["**수정 문구**", "", card["suggestion"], ""]
        if card.get("law_version_note"):
            lines += [f"*{card['law_version_note']}*", ""]
        if card.get("rule") and card["rule"].get("fired"):
            lines += [f"(숫자 규칙: {card['rule'].get('why')} / A.X 판정 {card.get('ax_verdict')})", ""]
    lines += ["## 누락 항목", ""]
    if report.get("missing"):
        for item in report["missing"]:
            lines.append(f"- `{item['id']}` {item['name']} — not_present ({item.get('basis')})")
    else:
        lines.append("- 필수 항목이 조항에서 확인됨")
    lines += ["", "## 불일치", ""]
    if report.get("mismatches"):
        for item in report["mismatches"]:
            lines.append(f"- {item}")
    else:
        lines.append("- 해당 없음")
    lines += ["", "## 직접 확인할 것", ""]
    if report.get("needs_fact"):
        for item in report["needs_fact"]:
            lines.append(f"- {item['segment_id']}: {item['fact']}")
    else:
        lines.append("- 없음")
    lines += [
        "",
        "## 다음 행동",
        "",
        "상대에게 보낼 수정 요청:",
        "",
    ]
    for req in report.get("next_actions", {}).get("requests") or []:
        lines.append(f"- {req}")
    lines += [
        "",
        f"상담 창구: {report.get('next_actions', {}).get('helpline')}",
        "",
        "## 고지",
        "",
        report.get("disclaimer") or DISCLAIMER,
        "",
    ]
    return "\n".join(lines)
