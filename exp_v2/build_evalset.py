# -*- coding: utf-8 -*-
"""설계 v2 1단계 산출물 생성. 기존 파일은 읽기만 하고 exp_v2에만 쓴다. LLM 호출 없음."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
DATA = EXP / "data"
CTX = EXP / "contexts"
LAW_DIR = WORK / "data_contract" / "law_api" / "현행"
CAT_PATH = WORK / "data_contract" / "catalog" / "catalog_v0.2.json"
TPL_PATH = EXP / "evalgen" / "clause_templates_v1.jsonl"
RULE_PATH = EXP / "evalgen" / "rule_recall_v1.jsonl"
FORMS = WORK / "data_contract" / "aihub_forms"
S2_PATH = WORK / "reports_restored" / "S2_REPORT.md"
S2B_PATH = WORK / "reports_restored" / "S2B_REPORT.md"
FIELD_CSV = WORK / "inventory" / "A_terms_clauseField.csv"
LEASE_DIR = WORK / "data" / "standard_forms" / "lease"
PDF_TXT_DIR = WORK / "data" / "standard_forms" / "_extracted"

DETAIL_DOMAIN = {
    "아르바이트계약서": "LAB",
    "근로(고용)계약서": "LAB",
    "주거용부동산임대계약서": "LEASE",
}
NAMES = ["김민수", "박서연", "이준호", "최유진", "정하늘"]
CIRC = ["①", "②", "③", "④", "⑤"]
MIN_WAGE = {2022: 9160, 2023: 9620, 2024: 9860, 2025: 10030, 2026: 10320}
TITLE_ONLY = re.compile(r"제\s*\d+\s*조\s*(의\s*\d+)?\s*(\([^)]*\))?\s*")
BGE_SNAP = Path(
    r"C:\Users\DMLAB_Server1\.cache\huggingface\hub\models--BAAI--bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class CellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._buf: list[str] = []
        self.cells: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            if self._depth == 0:
                self._buf = []
            self._depth += 1

    def handle_endtag(self, tag):
        if tag == "td" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
                if text:
                    self.cells.append(text)

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)


def cells_text(html_path: Path) -> str:
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    parser = CellParser()
    parser.feed(raw)
    # 중첩 표는 바깥 셀에 안쪽 글자가 다시 들어간다. 긴 셀이 짧은 셀을 포함하면 짧은 쪽을 뺀다.
    cells = parser.cells
    kept = []
    for i, cell in enumerate(cells):
        if any(i != j and cell in other and len(other) > len(cell) for j, other in enumerate(cells)):
            continue
        kept.append(cell)
    return "\n".join(kept)


def retry_h3() -> list[dict]:
    out = EXP / "h3_retry"
    out.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice")
    rows = []
    hwps = sorted(LEASE_DIR.glob("H3*.hwp"))
    for hwp in hwps:
        stem = hwp.stem
        html_path = out / f"{stem}.html"
        text = ""
        method = ""
        status = "추출 실패"
        proc = subprocess.run(
            ["hwp5html", "--html", "--output", str(html_path), str(hwp)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if html_path.exists() and html_path.stat().st_size > 0:
            extracted = cells_text(html_path)
            if len(extracted) >= 100:
                text = extracted
                method = "hwp5html"
                status = "성공"
        if status != "성공" and soffice:
            txt_path = out / f"{stem}.soffice.txt"
            subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", str(out), str(hwp)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            produced = out / f"{stem}.txt"
            if produced.exists() and produced.stat().st_size >= 100:
                text = produced.read_text(encoding="utf-8", errors="replace")
                method = "soffice"
                status = "성공"
                produced.rename(txt_path)
        if status != "성공":
            pdf = hwp.with_suffix(".pdf")
            pdf_txt = PDF_TXT_DIR / f"{stem}.pdf.txt"
            if pdf.exists() and pdf_txt.exists():
                text = pdf_txt.read_text(encoding="utf-8")
                method = "pdf"
                status = "pdf 사용"
        dest = out / f"{stem}.txt"
        if status == "추출 실패":
            dest.write_text("", encoding="utf-8")
        else:
            dest.write_text(text, encoding="utf-8")
        articles = sorted(set(re.findall(r"제\s*\d+\s*조", text)))
        rows.append(
            {
                "file": hwp.name,
                "title": stem,
                "status": status,
                "method": method,
                "chars": len(text),
                "unique_articles": len(articles),
                "hwp5html_exit": proc.returncode,
                "soffice": bool(soffice),
                "txt": str(dest),
            }
        )
    return rows


def codebook() -> tuple[list[dict], list[str]]:
    codes = []
    with FIELD_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            triple = (int(row["n_all"]), int(row["n_dv1_유리"]), int(row["n_dv2_불리"]))
            codes.append((row["clauseField"], triple))
    s2_rows = []
    for line in S2_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line)
        if not m:
            continue
        name = m.group(1).strip()
        if name == "분야" or set(name) <= set("-"):
            continue
        s2_rows.append((name, int(m.group(2)), int(m.group(3)), int(m.group(4))))
    by_code = defaultdict(list)
    for code, triple in codes:
        by_code[triple].append(code)
    by_name = defaultdict(list)
    for name, n, a, b in s2_rows:
        by_name[(n, a, b)].append(name)
    out_rows = []
    for code, triple in codes:
        names = by_name.get(triple, [])
        same = by_code[triple]
        if len(names) == 1 and len(same) == 1:
            status = "확정"
            s2_name = names[0]
            note = ""
        else:
            status = "미확정"
            s2_name = ""
            if not names:
                note = "S2 건수와 1:1로 맞지 않음"
            elif len(same) != 1:
                note = "같은 건수를 가진 코드가 둘 이상"
            else:
                note = "같은 건수를 가진 분야명이 둘 이상"
        out_rows.append(
            {
                "clauseField": code,
                "n_all": triple[0],
                "n_dv1": triple[1],
                "n_dv2": triple[2],
                "s2_name": s2_name,
                "status": status,
                "note": note,
            }
        )
    unmatched = []
    matched_names = {r["s2_name"] for r in out_rows if r["status"] == "확정"}
    for name, n, a, b in s2_rows:
        if name not in matched_names:
            unmatched.append(f"{name} ({n}/{a}/{b})")
    s2b = S2B_PATH.read_text(encoding="utf-8")
    has_field = "clauseField" in s2b or "코드북" in s2b
    dest = EXP / "clausefield_map.csv"
    with dest.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["clauseField", "n_all", "n_dv1", "n_dv2", "s2_name", "status", "note"],
        )
        writer.writeheader()
        writer.writerows(out_rows)
    return out_rows, unmatched, has_field


def norm_article_no(value) -> str:
    s = str(value).strip().replace(" ", "")
    m = re.fullmatch(r"0*(\d+)(?:의0*(\d+))?", s)
    if not m:
        return s
    base = str(int(m.group(1)))
    if m.group(2):
        return f"{base}의{int(m.group(2))}"
    return base


def unit_article_key(unit: dict) -> str:
    base = norm_article_no(unit.get("조문번호"))
    branch = str(unit.get("조문가지번호") or "").strip()
    if branch.isdigit() and int(branch):
        return f"{base}의{int(branch)}"
    return base


def target_article(article: str) -> str | None:
    s = str(article).replace(" ", "")
    m = re.fullmatch(r"제(\d+)조(?:의(\d+))?", s)
    if not m:
        return None
    base = str(int(m.group(1)))
    if m.group(2):
        return f"{base}의{int(m.group(2))}"
    return base


def flatten_unit(unit: dict) -> tuple[str, str]:
    parts: list[str] = []

    def add(value) -> None:
        text = str(value or "").strip()
        if text:
            parts.append(text)

    add(unit.get("조문내용"))
    hangs = unit.get("항") or []
    if isinstance(hangs, dict):
        hangs = [hangs]
    for hang in hangs:
        if not isinstance(hang, dict):
            continue
        add(hang.get("항내용"))
        hos = hang.get("호") or []
        if isinstance(hos, dict):
            hos = [hos]
        for ho in hos:
            if not isinstance(ho, dict):
                continue
            add(ho.get("호내용"))
            moks = ho.get("목") or []
            if isinstance(moks, dict):
                moks = [moks]
            for mok in moks:
                if isinstance(mok, dict):
                    add(mok.get("목내용"))
    return "\n".join(parts), str(unit.get("조문제목") or "").strip()


def load_law_bodies() -> dict[str, dict]:
    found = {}
    for path in LAW_DIR.glob("*_body_MST.json"):
        obj = json.loads(path.read_text(encoding="utf-8"))
        info = (obj.get("법령") or {}).get("기본정보") or {}
        name = info.get("법령명_한글")
        if not name:
            continue
        units = ((obj.get("법령") or {}).get("조문") or {}).get("조문단위")
        if isinstance(units, dict):
            units = [units]
        found[name] = {
            "path": path,
            "enforce": str(info.get("시행일자") or ""),
            "units": units or [],
        }
    return found


def build_law_texts(cat: dict) -> tuple[list[dict], dict]:
    bodies = load_law_bodies()
    full_of = cat["laws"]
    notes = defaultdict(list)
    for check in cat["checks"]:
        for basis in check.get("legal_basis") or []:
            node_id = f"{basis.get('law')}:{basis.get('article')}"
            note = (basis.get("note") or "").strip()
            if note and note not in notes[node_id]:
                notes[node_id].append(note)
    rows = []
    index = {}
    for node in cat["law_nodes"]:
        node_id = node["id"]
        law_short = node.get("law_short") or ""
        article = node.get("article") or ""
        law_full = full_of.get(law_short, node.get("law_full") or law_short)
        row = {
            "id": node_id,
            "법령명": law_full,
            "조문 번호": article,
            "조문 제목": "",
            "본문": "",
            "출처 파일": "",
            "시행일": "",
            "text_source": "",
            "fail_reason": "",
        }
        if law_short == "판례":
            row["본문"] = "\n".join(notes.get(node_id, []))
            row["text_source"] = "note_only"
            if not row["본문"]:
                row["fail_reason"] = "판례 본문 미수집, 카탈로그 note 없음"
            else:
                row["fail_reason"] = "판례 본문 미수집"
            rows.append(row)
            index[node_id] = row
            continue
        body = bodies.get(law_full)
        if body is None:
            row["text_source"] = "missing"
            row["fail_reason"] = "법령 미수집"
            rows.append(row)
            index[node_id] = row
            continue
        row["출처 파일"] = str(body["path"].relative_to(WORK))
        row["시행일"] = body["enforce"]
        target = target_article(article)
        matched = None
        if target is None:
            # 본문·적용 범위처럼 조문 번호가 아닌 노드. 본문은 조문단위 전체를 붙인다.
            chunks = []
            for unit in body["units"]:
                text, title = flatten_unit(unit)
                if text:
                    chunks.append(text)
                if title and not row["조문 제목"]:
                    row["조문 제목"] = title
            matched_text = "\n".join(chunks)
            if article == "본문" and matched_text:
                row["본문"] = matched_text
                row["text_source"] = "body"
            else:
                row["text_source"] = "missing"
                row["fail_reason"] = "조문 못 찾음"
        else:
            for unit in body["units"]:
                if unit_article_key(unit) == target and unit.get("조문여부") != "전문":
                    matched = unit
                    break
            if matched is None:
                for unit in body["units"]:
                    if unit_article_key(unit) == target:
                        matched = unit
                        break
            if matched is None:
                row["text_source"] = "missing"
                row["fail_reason"] = "조문 못 찾음"
            else:
                text, title = flatten_unit(matched)
                row["본문"] = text
                row["조문 제목"] = title
                row["시행일"] = str(matched.get("조문시행일자") or body["enforce"])
                row["text_source"] = "body" if text else "missing"
                if not text:
                    row["fail_reason"] = "조문 본문 비어 있음"
        rows.append(row)
        index[node_id] = row
    return rows, index


def basis_ids(check: dict) -> list[str]:
    out = []
    for basis in check.get("legal_basis") or []:
        node_id = f"{basis.get('law')}:{basis.get('article')}"
        if node_id not in out:
            out.append(node_id)
    return out


def render_nodes(ids: list[str], law_index: dict) -> str:
    blocks = []
    for node_id in ids:
        node = law_index[node_id]
        title = node["조문 제목"]
        head = f"[{node['id']}] {node['법령명']} {node['조문 번호']}"
        if title:
            head += f" {title}"
        blocks.append(head + "\n" + (node["본문"] or ""))
    return "\n\n".join(blocks)


def bigrams(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    return [compact[i : i + 2] for i in range(len(compact) - 1)]


class BM25:
    def __init__(self, docs: list[str]) -> None:
        self.tfs = []
        self.lens = []
        df = Counter()
        for doc in docs:
            tf = Counter(bigrams(doc))
            self.tfs.append(tf)
            length = sum(tf.values())
            self.lens.append(length)
            df.update(tf.keys())
        self.df = df
        self.n = len(docs)
        self.avg = (sum(self.lens) / self.n) if self.n else 0.0

    def rank(self, query: str, k: int = 5) -> list[int]:
        qtf = Counter(bigrams(query))
        scores = []
        k1, b = 1.5, 0.75
        for i, tf in enumerate(self.tfs):
            score = 0.0
            dl = self.lens[i] or 1
            for term, qf in qtf.items():
                freq = tf.get(term)
                if not freq:
                    continue
                n = self.df[term]
                idf = math.log(1 + (self.n - n + 0.5) / (n + 0.5))
                score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / self.avg)) * qf
            scores.append(score)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return order[:k]


def suspect_flags(text: str, domain: str) -> list[str]:
    reasons = []
    if domain == "LAB":
        years = [int(y) for y in re.findall(r"(20\d{2})\s*년", text) if int(y) in MIN_WAGE]
        threshold = MIN_WAGE[years[0]] if len(years) == 1 else MIN_WAGE[2026]
        year_label = str(years[0]) if len(years) == 1 else "2026"
        for match in re.finditer(r"(?:시급|시간당)\s*(?:은|를|을|:)?\s*([\d,]{3,})\s*원", text):
            amount = int(match.group(1).replace(",", ""))
            if amount < threshold:
                reasons.append(f"L-T01 시급 {amount}원 < {year_label}년 최저임금 {threshold}원")
        if re.search(r"휴게.{0,30}(?:부여하지|주지|두지)\s*않", text) or re.search(
            r"휴게\s*시간(?:을|를)?\s*(?:없|미부여)", text
        ):
            reasons.append("L-T05 휴게를 부여하지 않는다는 문구")
        work = re.search(r"(\d+)\s*시간", text)
        rest = re.search(r"휴게.{0,40}?(\d+)\s*(분|시간)", text)
        if work and rest:
            hours = int(work.group(1))
            rest_min = int(rest.group(1)) * (60 if rest.group(2) == "시간" else 1)
            if hours >= 8 and rest_min < 60:
                reasons.append(f"L-T05 근로 {hours}시간에 휴게 {rest_min}분")
            elif hours >= 4 and rest_min < 30:
                reasons.append(f"L-T05 근로 {hours}시간에 휴게 {rest_min}분")
        if "수습" in text:
            for match in re.finditer(r"임금의\s*(\d+(?:\.\d+)?)\s*%\s*를?\s*지급", text):
                rate = float(match.group(1))
                if rate < 90:
                    reasons.append(f"L-T02 수습 중 임금의 {rate:g}% 지급(10% 초과 감액)")
    if domain == "LEASE":
        if re.search(r"증액|인상|상향|올리", text):
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", text):
                rate = float(match.group(1))
                if rate > 5:
                    reasons.append(f"H-T03 증액·인상 문구와 {rate}%")
    return reasons


def swap_parties(text: str) -> tuple[str, int]:
    pairs = [("사업주", "근로자"), ("임대인", "임차인"), ("채권자", "채무자")]
    tmp = text
    count = 0
    for i, (left, right) in enumerate(pairs):
        count += tmp.count(left) + tmp.count(right)
        tmp = tmp.replace(left, f"__L{i}__").replace(right, f"__R{i}__")
    for i, (left, right) in enumerate(pairs):
        tmp = tmp.replace(f"__L{i}__", right).replace(f"__R{i}__", left)
    return tmp, count


def looks_like_title_only(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 20:
        return True
    return TITLE_ONLY.fullmatch(stripped) is not None


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    CTX.mkdir(parents=True, exist_ok=True)
    cat = json.loads(CAT_PATH.read_text(encoding="utf-8"))
    checks = {c["id"]: c for c in cat["checks"]}
    slots = {s["id"]: s for s in cat["slots"]}
    node_ids = [n["id"] for n in cat["law_nodes"]]

    print("codebook", flush=True)
    code_rows, unmatched_names, s2b_has_field = codebook()

    print("h3", flush=True)
    h3_rows = retry_h3()

    print("law texts", flush=True)
    law_rows, law_index = build_law_texts(cat)
    law_path = EXP / "law_node_texts.jsonl"
    write_jsonl(law_path, law_rows)
    art54 = law_index["근기법:제54조"]["본문"]
    art54_ok = "4시간인 경우에는 30분 이상" in art54

    ctype_domain = {"LAB_PT": "LAB", "LAB_FX": "LAB", "LEASE": "LEASE", "LOAN": "LOAN"}
    node_domains = defaultdict(set)
    for check in cat["checks"]:
        domains = {ctype_domain[c] for c in check.get("contract_types") or [] if c in ctype_domain}
        for node_id in basis_ids(check):
            node_domains[node_id].update(domains)

    print("templates", flush=True)
    templates = load_jsonl(TPL_PATH)
    problems = []
    by_pair = defaultdict(list)
    for row in templates:
        by_pair[row["pair_id"]].append(row)
        if not str(row.get("clause") or "").strip():
            problems.append(f"{row.get('id')} 문장이 비어 있음")
        if row.get("check_id") not in checks:
            problems.append(f"{row.get('id')} check_id {row.get('check_id')} 가 카탈로그에 없음")
    for pair_id, group in by_pair.items():
        flags = [bool(r["risky"]) for r in group]
        if flags.count(True) != 1 or flags.count(False) != 1:
            problems.append(f"{pair_id} 위험·안전 쌍이 1:1이 아님")
        kinds = {r["kind"] for r in group}
        if len(kinds) != 1:
            problems.append(f"{pair_id} kind가 쌍 안에서 다름")
    domain_count = Counter(r["domain"] for r in templates)
    kind_count = Counter(r["kind"] for r in templates)
    risky_count = Counter(bool(r["risky"]) for r in templates)

    surface_rng = random.Random(42)
    t3 = []
    for src in templates:
        check = checks.get(src["check_id"])
        slot_id = check.get("slot") if check else ""
        slot_name = slots[slot_id]["name"] if slot_id in slots else slot_id
        gold = basis_ids(check) if check else []
        n = surface_rng.randint(3, 12)
        circ = CIRC[surface_rng.randrange(5)]
        surfaces = [
            ("0", src["clause"]),
            ("A", f"제{n}조({slot_name}) {src['clause']}"),
            ("B", f"{circ} {src['clause']}"),
        ]
        for surface, clause in surfaces:
            item_id = src["id"] if surface == "0" else f"{src['id']}-{surface}"
            t3.append(
                {
                    "id": item_id,
                    "pair_id": src["pair_id"],
                    "check_id": src["check_id"],
                    "domain": src["domain"],
                    "risky": bool(src["risky"]),
                    "kind": src["kind"],
                    "surface": surface,
                    "clause": clause,
                    "gold_law_nodes": gold,
                    "slot": slot_id,
                }
            )
    t3_path = DATA / "t3_clauses.jsonl"
    write_jsonl(t3_path, t3)

    statute_by_domain = defaultdict(list)
    for node_id in node_ids:
        if node_id.startswith("판례:"):
            continue
        for domain in sorted(node_domains.get(node_id, ())):
            statute_by_domain[domain].append(node_id)
    t4 = []
    for row in t3:
        if row["surface"] != "0" or not row["risky"]:
            continue
        gold = [g for g in row["gold_law_nodes"] if not g.startswith("판례:")]
        choices = statute_by_domain[row["domain"]]
        t4.append(
            {
                "id": row["id"],
                "pair_id": row["pair_id"],
                "check_id": row["check_id"],
                "domain": row["domain"],
                "clause": row["clause"],
                "gold": gold,
                "choices": choices,
                "n_choices": len(choices),
                "slot": row["slot"],
            }
        )
    t4_path = DATA / "t4_items.jsonl"
    write_jsonl(t4_path, t4)

    rules = load_jsonl(RULE_PATH)
    t1 = []
    for row in rules:
        item = dict(row)
        flags = {}
        for node_id in row.get("law_nodes") or []:
            node = law_index.get(node_id)
            flags[node_id] = bool(node and node["text_source"] == "body" and node["본문"])
        item["law_node_text_ok"] = flags
        item["all_law_nodes_secured"] = all(flags.values()) if flags else False
        t1.append(item)
    t1_path = DATA / "t1_items.jsonl"
    write_jsonl(t1_path, t1)

    print("t2", flush=True)
    label_to_slots = defaultdict(lambda: defaultdict(list))
    for slot in cat["slots"]:
        for label in slot.get("aihub_labels") or []:
            label_to_slots[slot["domain"]][label].append(slot["id"])
    doc_files = []
    for path in FORMS.rglob("*.json"):
        if not (path.parent.name.startswith("TL_") or path.parent.name.startswith("VL_")):
            continue
        doc_files.append(path)
    raw_docs = Counter()
    sections = []
    excluded_short = 0
    excluded_title = 0
    docs_with_label = {}
    for path in doc_files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc = obj.get("document") or {}
        meta = ((doc.get("metadata") or {}).get("file_info") or {})
        detail = ((meta.get("document_category") or {}).get("detail_category")) or ""
        if detail not in DETAIL_DOMAIN:
            continue
        sec_list = doc.get("sections") or []
        if not any(isinstance((sec.get("content") or {}).get("content_labels"), list) for sec in sec_list):
            continue
        doc_name = meta.get("document_name") or path.stem
        raw_docs[detail] += 1
        docs_with_label[str(path)] = doc_name
        domain = DETAIL_DOMAIN[detail]
        for idx, sec in enumerate(sec_list):
            content = sec.get("content") or {}
            desc = content.get("description") or ""
            if not isinstance(desc, str):
                continue
            desc = desc.strip()
            if len(desc) < 20:
                excluded_short += 1
                continue
            if TITLE_ONLY.fullmatch(desc):
                excluded_title += 1
                continue
            labels = [str(x) for x in (content.get("content_labels") or [])]
            mapped = []
            unmapped = []
            for label in labels:
                hit = label_to_slots[domain].get(label) or []
                if hit:
                    for slot_id in hit:
                        if slot_id not in mapped:
                            mapped.append(slot_id)
                else:
                    unmapped.append(label)
            if mapped:
                slot_list = mapped + (["기타"] if unmapped else [])
                primary = mapped[0]
            else:
                slot_list = ["기타"]
                primary = "기타"
            sections.append(
                {
                    "doc_id": doc_name,
                    "path": str(path),
                    "category": detail,
                    "domain": domain,
                    "section_index": idx,
                    "clause": desc,
                    "content_labels": labels,
                    "slots": slot_list,
                    "primary_slot": primary,
                    "unmapped_labels": unmapped,
                }
            )
    docs = sorted({s["path"] for s in sections})
    split_rng = random.Random(42)
    split_rng.shuffle(docs)
    n_train = int(len(docs) * 0.8)
    train_docs = set(docs[:n_train])
    test_docs = set(docs[n_train:])
    test_sections = [s for s in sections if s["path"] in test_docs]
    pools = defaultdict(list)
    for sec in test_sections:
        pools[sec["primary_slot"]].append(sec)
    for slot_id in sorted(pools):
        split_rng.shuffle(pools[slot_id])
    picked = []
    counts = Counter()
    while len(picked) < 400:
        progressed = False
        for slot_id in sorted(pools):
            if pools[slot_id] and counts[slot_id] < 15 and len(picked) < 400:
                picked.append(pools[slot_id].pop(0))
                counts[slot_id] += 1
                progressed = True
        if not progressed:
            break
    picked.sort(key=lambda s: (s["doc_id"], s["section_index"], s["path"]))
    t2 = []
    for i, sec in enumerate(picked, start=1):
        t2.append(
            {
                "id": f"T2-{i:04d}",
                "doc_id": sec["doc_id"],
                "category": sec["category"],
                "clause": sec["clause"],
                "content_labels": sec["content_labels"],
                "slots": sec["slots"],
                "primary_slot": sec["primary_slot"],
            }
        )
    t2_path = DATA / "t2_clauses.jsonl"
    write_jsonl(t2_path, t2)
    map_rows = []
    for domain, table in label_to_slots.items():
        for label, slot_ids in sorted(table.items()):
            map_rows.append(
                {
                    "domain": domain,
                    "aihub_label": label,
                    "slots": "|".join(slot_ids),
                    "unmapped": "",
                }
            )
    map_path = DATA / "t2_label_map.csv"
    with map_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["domain", "aihub_label", "slots", "unmapped"])
        writer.writeheader()
        writer.writerows(map_rows)

    pool_sections = [s for s in sections if s["path"] in test_docs]
    pool_sections.sort(key=lambda s: (s["doc_id"], s["section_index"], s["path"]))
    natural = []
    for i, sec in enumerate(pool_sections, start=1):
        reasons = suspect_flags(sec["clause"], sec["domain"])
        natural.append(
            {
                "id": f"NP-{i:04d}",
                "doc_id": sec["doc_id"],
                "category": sec["category"],
                "clause": sec["clause"],
                "label": None,
                "suspect": bool(reasons),
                "suspect_reasons": reasons,
            }
        )
    natural_path = DATA / "natural_pool.jsonl"
    write_jsonl(natural_path, natural)
    flagged = [r for r in natural if r["suspect"]]
    sample_rng = random.Random(42)
    suspect_samples = sample_rng.sample(flagged, min(10, len(flagged)))
    mention_wage = sum(1 for r in natural if "시급" in r["clause"] or "시간당" in r["clause"])
    mention_rest = sum(1 for r in natural if "휴게" in r["clause"])
    mention_raise = sum(
        1
        for r in natural
        if r["category"] == "주거용부동산임대계약서" and re.search(r"증액|인상|상향", r["clause"])
    )

    print("contexts", flush=True)
    corpus_ids = node_ids
    corpus_text = [render_nodes([nid], law_index) for nid in corpus_ids]
    bm25 = BM25([law_index[nid]["본문"] for nid in corpus_ids])
    query_rows = [r for r in t3] + t4
    unique_queries = []
    seen_q = set()
    for row in query_rows:
        if row["clause"] not in seen_q:
            seen_q.add(row["clause"])
            unique_queries.append(row["clause"])
    bm25_top = {q: [corpus_ids[i] for i in bm25.rank(q, 5)] for q in unique_queries}
    bge_top = {}
    bge_error = ""
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(str(BGE_SNAP), local_files_only=True)
        doc_vec = model.encode(
            [law_index[nid]["본문"] or law_index[nid]["id"] for nid in corpus_ids],
            normalize_embeddings=True,
            batch_size=16,
            show_progress_bar=False,
        )
        qry_vec = model.encode(unique_queries, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        import numpy as np

        sims = np.matmul(qry_vec, doc_vec.T)
        for qi, query in enumerate(unique_queries):
            order = list(np.argsort(-sims[qi])[:5])
            bge_top[query] = [corpus_ids[i] for i in order]
    except Exception as exc:
        bge_error = f"{type(exc).__name__}: {exc}"

    ctx_rng = random.Random(42)
    a3_short = []

    def build_context_rows(items: list[dict], gold_key: str) -> dict[str, list[dict]]:
        grouped = {"A1": [], "A2": [], "A3": [], "A4": []}
        for item in items:
            gold = list(item[gold_key])
            domain = item["domain"]
            pool = [nid for nid in node_ids if domain in node_domains.get(nid, ()) and nid not in gold]
            dist2 = ctx_rng.sample(pool, min(2, len(pool))) if pool else []
            order2 = gold + dist2
            ctx_rng.shuffle(order2)
            dist8_n = min(8, len(pool))
            dist8 = ctx_rng.sample(pool, dist8_n) if pool else []
            order8 = gold + dist8
            ctx_rng.shuffle(order8)
            if dist8_n < 8:
                a3_short.append({"id": item["id"], "distractors": dist8_n, "pool": len(pool)})
            a1 = render_nodes(gold, law_index)
            a2 = render_nodes(order2, law_index)
            a3 = render_nodes(order8, law_index)
            grouped["A1"].append(
                {"id": item["id"], "condition": "A1", "node_ids": gold, "n_chars": len(a1), "text": a1}
            )
            grouped["A2"].append(
                {
                    "id": item["id"],
                    "condition": "A2",
                    "node_ids": order2,
                    "n_distractors": len(dist2),
                    "n_chars": len(a2),
                    "text": a2,
                }
            )
            grouped["A3"].append(
                {
                    "id": item["id"],
                    "condition": "A3",
                    "node_ids": order8,
                    "n_distractors": dist8_n,
                    "n_chars": len(a3),
                    "text": a3,
                }
            )
            b_ids = bm25_top.get(item["clause"], [])
            g_ids = bge_top.get(item["clause"], [])
            b_text = render_nodes(b_ids, law_index)
            g_text = render_nodes(g_ids, law_index) if g_ids else ""
            grouped["A4"].append(
                {
                    "id": item["id"],
                    "condition": "A4",
                    "bm25": {"node_ids": b_ids, "n_chars": len(b_text), "text": b_text},
                    "bge": {"node_ids": g_ids, "n_chars": len(g_text), "text": g_text},
                }
            )
        return grouped

    # T3 전체 다음 T4. 같은 Random(42) 흐름.
    t3_ctx = build_context_rows(t3, "gold_law_nodes")
    t4_ctx = build_context_rows(t4, "gold")
    ctx_paths = {}
    for name, grouped in (("t3", t3_ctx), ("t4", t4_ctx)):
        for cond, rows in grouped.items():
            path = CTX / f"{name}_{cond}.jsonl"
            write_jsonl(path, rows)
            ctx_paths[f"{name}_{cond}"] = path

    def hits(rows: list[dict], retriever: str) -> dict[str, float]:
        out = {}
        risky = [r for r in t3 if r["surface"] == "0" and r["risky"]]
        by_id = {r["id"]: r for r in rows}
        for k in (1, 3, 5):
            hit = 0
            for item in risky:
                got = by_id[item["id"]][retriever]["node_ids"][:k]
                if any(g in got for g in item["gold_law_nodes"]):
                    hit += 1
            out[f"hit@{k}"] = hit
        out["n"] = len(risky)
        return out

    hit_bm25 = hits(t3_ctx["A4"], "bm25")
    hit_bge = hits(t3_ctx["A4"], "bge") if bge_top else {"hit@1": 0, "hit@3": 0, "hit@5": 0, "n": 67, "error": bge_error}

    print("counterfactual", flush=True)
    name_rng = random.Random(42)
    cf = []
    surface0 = [r for r in t3 if r["surface"] == "0"]
    for row in surface0:
        prefixes = []
        if row["domain"] == "LAB":
            picked_names = name_rng.sample(NAMES, 2)
            for name in picked_names:
                prefixes.append(f"(주)한빛마트(이하 '사업주')와 근로자 {name} 간의 약정: ")
        elif row["domain"] == "LEASE":
            for _ in range(2):
                a, b = name_rng.sample(NAMES, 2)
                prefixes.append(f"임대인 {a}와 임차인 {b} 간의 약정: ")
        else:
            for _ in range(2):
                a, b = name_rng.sample(NAMES, 2)
                prefixes.append(f"채권자 {a}와 채무자 {b} 간의 약정: ")
        for vi, prefix in enumerate(prefixes, start=1):
            cf.append(
                {
                    "id": f"{row['id']}-IRR{vi}",
                    "source_id": row["id"],
                    "variant": "irrelevant",
                    "domain": row["domain"],
                    "clause": prefix + row["clause"],
                    "original_risky": row["risky"],
                    "expected_change": False,
                    "label": row["risky"],
                    "needs_review": False,
                }
            )
        swapped, n_swap = swap_parties(row["clause"])
        cf.append(
            {
                "id": f"{row['id']}-SWAP",
                "source_id": row["id"],
                "variant": "swap",
                "domain": row["domain"],
                "clause": swapped,
                "original_risky": row["risky"],
                "n_role_tokens": n_swap,
                "changed": swapped != row["clause"],
                "label": None,
                "needs_review": True,
            }
        )
    cf_path = DATA / "counterfactual.jsonl"
    write_jsonl(cf_path, cf)
    swaps = [r for r in cf if r["variant"] == "swap"]
    review_rng = random.Random(42)
    swap_samples = review_rng.sample(swaps, min(20, len(swaps)))

    numeric_pairs = []
    for pair_id, group in sorted(by_pair.items()):
        if group and all(r["kind"] == "numeric" for r in group):
            numeric_pairs.append((group[0]["check_id"], pair_id))
    numeric_by_check = defaultdict(list)
    for check_id, pair_id in numeric_pairs:
        numeric_by_check[check_id].append(pair_id)

    def mean_chars(rows: list[dict], key="n_chars") -> float:
        if not rows:
            return 0.0
        return sum(r[key] for r in rows) / len(rows)

    ctx_means = {
        "t3_A1": mean_chars(t3_ctx["A1"]),
        "t3_A2": mean_chars(t3_ctx["A2"]),
        "t3_A3": mean_chars(t3_ctx["A3"]),
        "t3_A4_bm25": sum(r["bm25"]["n_chars"] for r in t3_ctx["A4"]) / len(t3_ctx["A4"]),
        "t3_A4_bge": sum(r["bge"]["n_chars"] for r in t3_ctx["A4"]) / len(t3_ctx["A4"]),
        "t4_A1": mean_chars(t4_ctx["A1"]),
        "t4_A2": mean_chars(t4_ctx["A2"]),
        "t4_A3": mean_chars(t4_ctx["A3"]),
        "t4_A4_bm25": sum(r["bm25"]["n_chars"] for r in t4_ctx["A4"]) / len(t4_ctx["A4"]),
        "t4_A4_bge": sum(r["bge"]["n_chars"] for r in t4_ctx["A4"]) / len(t4_ctx["A4"]),
    }

    secured = [r for r in law_rows if r["text_source"] == "body" and r["본문"]]
    failed = [r for r in law_rows if r["text_source"] != "body"]
    t1_domain = Counter(r["domain"] for r in t1)
    t3_surface = Counter(r["surface"] for r in t3)
    t3_risky = Counter(bool(r["risky"]) for r in t3)
    t3_kind = Counter(r["kind"] for r in t3)
    t4_domain = Counter(r["domain"] for r in t4)
    t2_slot = Counter(r["primary_slot"] for r in t2)
    slot_names = {s["id"]: s["name"] for s in cat["slots"]}
    slot_names["기타"] = "기타"
    cf_irr = sum(1 for r in cf if r["variant"] == "irrelevant")
    cf_swap = sum(1 for r in cf if r["variant"] == "swap")
    cf_swap_changed = sum(1 for r in swaps if r["changed"])

    artifacts = [
        t1_path,
        t2_path,
        t3_path,
        t4_path,
        natural_path,
        cf_path,
        law_path,
        map_path,
        EXP / "clausefield_map.csv",
    ] + list(ctx_paths.values())
    hashes = {str(p.relative_to(WORK)): sha256_file(p) for p in artifacts}

    confirmed = sum(1 for r in code_rows if r["status"] == "확정")
    choice_line = ", ".join(f"{d} {len(statute_by_domain[d])}" for d in ("LAB", "LEASE", "LOAN"))
    t2_slot_line = ", ".join(f"{slot_names.get(k, k)} {v}" for k, v in sorted(t2_slot.items()))
    h3_ok = sum(1 for r in h3_rows if r["status"] == "성공")
    h3_pdf = sum(1 for r in h3_rows if r["status"] == "pdf 사용")

    def fmt(n: float) -> str:
        return f"{n:.1f}"

    lines = []
    lines.append("# 설계 v2 1단계 평가셋")
    lines.append("")
    lines.append("LLM 호출 없음. 임베딩은 로컬 bge-m3만 사용했다. 기존 파일은 수정하지 않았다.")
    lines.append("")
    lines.append("| 산출물 | 건수 | 구성 | SHA-256 |")
    lines.append("|---|---:|---|---|")
    lines.append(
        f"| t1_items | {len(t1)} | "
        + ", ".join(f"{k} {v}" for k, v in sorted(t1_domain.items()))
        + f" / 본문 모두 확보 {sum(1 for r in t1 if r['all_law_nodes_secured'])} | `{hashes[str(t1_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| t2_clauses | {len(t2)} | slot별 {t2_slot_line} | `{hashes[str(t2_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| t3_clauses | {len(t3)} | 위험 {t3_risky[True]} / 안전 {t3_risky[False]}, "
        f"numeric {t3_kind['numeric']} / text {t3_kind['text']}, "
        f"surface 0 {t3_surface['0']} / A {t3_surface['A']} / B {t3_surface['B']} | `{hashes[str(t3_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| t4_items | {len(t4)} | "
        + ", ".join(f"{k} {v}" for k, v in sorted(t4_domain.items()))
        + f" / 선택지 {choice_line} | `{hashes[str(t4_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| natural_pool | {len(natural)} | 의심 플래그 {len(flagged)} | `{hashes[str(natural_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| counterfactual | {len(cf)} | 무관 {cf_irr} / 교환 {cf_swap} (역할어가 바뀐 문장 {cf_swap_changed}) | `{hashes[str(cf_path.relative_to(WORK))]}` |"
    )
    lines.append(
        f"| law_node_texts | {len(law_rows)} | 본문 확보 {len(secured)} | `{hashes[str(law_path.relative_to(WORK))]}` |"
    )
    lines.append(
        "| contexts A1–A4 | T3 402행×4, T4 67행×4 | "
        f"T3 평균 글자 A1 {fmt(ctx_means['t3_A1'])} / A2 {fmt(ctx_means['t3_A2'])} / A3 {fmt(ctx_means['t3_A3'])} / "
        f"A4-BM25 {fmt(ctx_means['t3_A4_bm25'])} / A4-bge {fmt(ctx_means['t3_A4_bge'])}. "
        f"T4 평균 글자 A1 {fmt(ctx_means['t4_A1'])} / A2 {fmt(ctx_means['t4_A2'])} / A3 {fmt(ctx_means['t4_A3'])} / "
        f"A4-BM25 {fmt(ctx_means['t4_A4_bm25'])} / A4-bge {fmt(ctx_means['t4_A4_bge'])} | 아래 파일별 해시 |"
    )
    lines.append("")
    lines.append("## 자료 조건 파일 해시")
    lines.append("")
    lines.append("| 파일 | SHA-256 |")
    lines.append("|---|---|")
    for key in sorted(ctx_paths):
        rel = ctx_paths[key].relative_to(WORK).as_posix()
        lines.append(f"| `{rel}` | `{hashes[str(ctx_paths[key].relative_to(WORK))]}` |")
    lines.append(f"| `exp_v2/data/t2_label_map.csv` | `{hashes[str(map_path.relative_to(WORK))]}` |")
    lines.append(f"| `exp_v2/clausefield_map.csv` | `{hashes[str((EXP / 'clausefield_map.csv').relative_to(WORK))]}` |")
    lines.append("")
    lines.append("A0는 빈 조건이라 파일을 만들지 않았다. A5 유사 사례는 보류다. 템플릿에는 학습 분할이 없어 정답 유출 위험이 있으므로 파일을 만들지 않았다.")
    lines.append("")
    lines.append("## 1. 해시 검증")
    lines.append("")
    expected = {
        "catalog_v0.2.json": "a2781f407358d0366b660c1923dcde6be3f301fa3b691f11cba386be33e9267b",
        "clause_templates_v1.jsonl": "18efce82602bb1957279572ce81d40ccd7af2cef4ec9a7c3bf1d87d8201579ad",
        "rule_recall_v1.jsonl": "119c5965f4090f969073f4da045685b14b1c9e4a5d84dac64d46a7bcf029572c",
    }
    locations = {
        "catalog_v0.2.json": CAT_PATH,
        "clause_templates_v1.jsonl": TPL_PATH,
        "rule_recall_v1.jsonl": RULE_PATH,
    }
    for name, digest in expected.items():
        got = sha256_file(locations[name])
        lines.append(f"- `{name}` {got} {'일치' if got == digest else '불일치'}")
    zip_root = WORK / "restore_pack_v2.zip"
    zip_in = WORK / "_incoming" / "restore_pack_v2.zip"
    lines.append(
        f"- 복구 묶음 위치: 작업 폴더 루트 `{zip_root.name}` 존재 {zip_root.exists()}. `_incoming` 쪽 존재 {zip_in.exists()}."
    )
    lines.append(
        f"- 카탈로그: checks {len(cat['checks'])}, slots {len(cat['slots'])}, law_nodes {len(cat['law_nodes'])}."
    )
    ctype_n = Counter(ct for c in cat["checks"] for ct in c.get("contract_types") or [])
    lines.append(
        "- 계약유형별 check 수: "
        + ", ".join(f"{k} {ctype_n[k]}" for k in ("LAB_PT", "LAB_FX", "LEASE", "LOAN"))
    )
    lines.append(
        f"- 템플릿 {len(templates)}줄. 분야 "
        + ", ".join(f"{k} {domain_count[k]}" for k in ("LAB", "LEASE", "LOAN"))
        + f". kind numeric {kind_count['numeric']} / text {kind_count['text']}. "
        f"위험 {risky_count[True]} / 안전 {risky_count[False]}. 쌍 {len(by_pair)}."
    )
    lines.append("")
    lines.append("## 코드북 대응")
    lines.append("")
    lines.append(
        f"S2 분야표의 (건수, 유리, 불리)가 약관 clauseField 집계와 딱 하나만 맞는 코드 {confirmed}개. 나머지 {len(code_rows) - confirmed}개는 미확정."
    )
    lines.append(f"S2B 본문에 clauseField·코드북 표가 있는지: {s2b_has_field}. S2B는 분야 코드 표를 주지 않아 대응에 쓰지 않았다.")
    if unmatched_names:
        lines.append("S2에는 있으나 코드와 1:1이 아닌 분야: " + ", ".join(unmatched_names))
    lines.append("")
    lines.append("## 2. 법령 보충과 H3 추출")
    lines.append("")
    key_len = len(os.environ.get("OPEN_LAW_KEY") or "")
    lines.append(f"OPEN_LAW_KEY 프로세스 환경변수 길이 {key_len}. 이 소절은 건너뛰었다.")
    if key_len == 0:
        lines.append("")
        lines.append("예전 PC에서 쓰던 법령 API 키(OC)를 Windows 사용자 환경변수 OPEN_LAW_KEY로 등록하고 Cursor를 재시작해 주세요.")
        lines.append("")
    lines.append(f"LibreOffice soffice: {'있음 ' + shutil.which('soffice') if shutil.which('soffice') else 'PATH에 없음'}.")
    lines.append("")
    lines.append("| 파일 | 결과 | 방법 | 글자 수 | 제N조 종류 |")
    lines.append("|---|---|---|---:|---:|")
    for row in h3_rows:
        lines.append(
            f"| {row['title']} | {row['status']} | {row['method'] or '-'} | {row['chars']} | {row['unique_articles']} |"
        )
    lines.append("")
    lines.append(f"hwp5html 성공 {h3_ok}, pdf로 대체 {h3_pdf}, 추출 실패 {sum(1 for r in h3_rows if r['status'] == '추출 실패')}.")
    lines.append("")
    lines.append("## 3. 제54조 문자열 검사")
    lines.append("")
    lines.append(f"`근기법:제54조` 본문에 \"4시간인 경우에는 30분 이상\" 포함: {art54_ok}")
    if art54_ok:
        for part in art54.split("\n"):
            if "4시간인 경우에는 30분 이상" in part:
                lines.append("")
                lines.append("해당 줄:")
                lines.append("")
                lines.append("```")
                lines.append(part)
                lines.append("```")
    lines.append("")
    lines.append(f"법조문 노드 {len(law_rows)}, 본문 확보 {len(secured)}, 확보 실패 {len(failed)}.")
    lines.append("")
    for row in failed:
        lines.append(f"- {row['id']}: {row['fail_reason']} (text_source={row['text_source']})")
    lines.append("")
    lines.append("## 4. T2·자연 조항")
    lines.append("")
    lines.append(
        "라벨 메타가 있는 문서 수: "
        + ", ".join(f"{k} {raw_docs[k]}" for k in ("아르바이트계약서", "근로(고용)계약서", "주거용부동산임대계약서"))
    )
    lines.append(
        f"섹션 제외: 20자 미만 {excluded_short}, 제목만 {excluded_title}. "
        f"남은 섹션 {len(sections)}. 문서 {len(docs)} 중 train {len(train_docs)} / test {len(test_docs)} (seed 42, train 비율 0.8의 내림)."
    )
    lines.append("매핑은 문서 분야와 같은 domain의 슬롯 `aihub_labels`만 사용했다. 어디에도 없는 라벨은 기타다.")
    lines.append(f"T2 test 층화 결과 {len(t2)}건. 자연 조항 풀은 test 문서의 남은 섹션 {len(natural)}건이고 label은 null이다.")
    lines.append(
        "의심 규칙은 조항 하나만 보고 돌릴 수 있는 숫자 규칙만 썼다. "
        "L-T01은 시급·시간당 금액이 문장 안 연도의 최저임금(연도가 하나만 없으면 2026년 10,320원)보다 작은 경우. "
        "L-T02는 수습 문구와 함께 임금의 N%를 지급한다고 적고 N이 90 미만인 경우. "
        "L-T05는 휴게를 주지 않는다는 문구, 또는 근로 N시간과 휴게 시간이 같이 있고 4시간 이상에 30분 미만·8시간 이상에 60분 미만인 경우. "
        "H-T03은 증액·인상 문구와 5%를 넘는 비율이 같이 있는 경우. 판정 라벨은 넣지 않았다."
    )
    lines.append(
        f"풀 안에서 시급·시간당 문구 {mention_wage}건, 휴게 문구 {mention_rest}건, 주거 임대의 증액·인상 문구 {mention_raise}건."
    )
    lines.append(f"의심 플래그 {len(flagged)}건. 샘플 {len(suspect_samples)}건(150자):")
    lines.append("")
    for row in suspect_samples:
        snippet = row["clause"].replace("\n", " ")[:150]
        lines.append(f"- `{row['id']}` {'; '.join(row['suspect_reasons'])} / {snippet}")
    lines.append("")
    lines.append("## 5. A4 검색 hit@k")
    lines.append("")
    lines.append("T3 위험 문장, surface 0, 67건. gold 노드가 상위 k 안에 하나라도 있으면 hit. 판례 note도 gold에 포함된다.")
    lines.append("")
    lines.append("| 검색기 | hit@1 | hit@3 | hit@5 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| BM25 문자 bigram | {hit_bm25['hit@1']} | {hit_bm25['hit@3']} | {hit_bm25['hit@5']} |")
    if bge_error:
        lines.append(f"| bge-m3 | 실패 | 실패 | 실패 |")
        lines.append("")
        lines.append(f"bge-m3 오류: {bge_error}")
    else:
        lines.append(f"| bge-m3 | {hit_bge['hit@1']} | {hit_bge['hit@3']} | {hit_bge['hit@5']} |")
    lines.append("")
    if a3_short:
        lines.append(f"A3에서 오답을 8개 채우지 못한 항목 {len(a3_short)}건. 가능 개수만 넣었다.")
        for row in a3_short[:20]:
            lines.append(f"- {row['id']}: 오답 {row['distractors']} / 후보 {row['pool']}")
        lines.append("")
    lines.append("## 6. 당사자 교환 샘플")
    lines.append("")
    lines.append(
        f"무관 요소 변경 {cf_irr}건은 판단이 변하지 않는 것으로 두었다. "
        f"당사자 교환 {cf_swap}건은 label null, needs_review true. 역할어가 실제로 바뀐 문장 {cf_swap_changed}건."
    )
    lines.append(f"숫자 변경 세트는 만들지 않았다. numeric 쌍 {len(numeric_pairs)}개.")
    for check_id, pairs in sorted(numeric_by_check.items()):
        lines.append(f"- {check_id}: {', '.join(pairs)}")
    lines.append("")
    lines.append("교환 샘플 20건:")
    lines.append("")
    for row in swap_samples:
        snippet = row["clause"].replace("\n", " ")[:180]
        lines.append(f"- `{row['id']}` 원래 risky={row['original_risky']} 바뀜={row['changed']} / {snippet}")
    lines.append("")
    lines.append("## 템플릿 문제")
    lines.append("")
    if problems:
        for item in problems:
            lines.append(f"- {item}")
    else:
        lines.append("문구를 고치지 않았다. 비어 있는 문장, 짝이 깨진 쌍, 카탈로그에 없는 check_id는 없었다.")
    lines.append("")
    lines.append("## 재현")
    lines.append("")
    lines.append("표기 변형의 조 번호·원문자, 문서 분할과 층화, A2·A3 오답, 가상 이름, 교환 샘플, 의심 샘플은 각각 Random(42)다.")
    lines.append("가상 이름 5개: 김민수, 박서연, 이준호, 최유진, 정하늘. 근로 문장의 상호는 예시와 같이 (주)한빛마트로 고정했다.")
    report_path = EXP / "EVALSET_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("REPORT", report_path)
    print("t3", len(t3), "t4", len(t4), "t2", len(t2), "natural", len(natural), "flagged", len(flagged))
    print("secured", len(secured), "art54", art54_ok, "bge_error", bge_error)
    print("h3", [(r["status"], r["chars"]) for r in h3_rows])


if __name__ == "__main__":
    main()
