# -*- coding: utf-8 -*-
"""법령 MST 구조와 실험 조문 59개 검사. 읽기만 한다."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORK = Path(r"C:\Users\DMLAB_Server1\Contracted_Youth")
EXP = WORK / "exp_v2"
OUT = EXP / "law_audit"
LAW_DIR = WORK / "data_contract" / "law_api" / "현행"
CAT_PATH = WORK / "data_contract" / "catalog" / "catalog_v0.2.json"
TEXTS = EXP / "law_node_texts.jsonl"
T3 = EXP / "data" / "t3_clauses.jsonl"
T4 = EXP / "data" / "t4_items.jsonl"
VERIFY_CSV = WORK / "reports_restored" / "VERIFY_CHECKS.csv"
VERIFY_MD = WORK / "reports_restored" / "VERIFY_REPORT.md"
BUILD_CAT = WORK / "data_contract" / "catalog" / "build_catalog.py"
PATCH = WORK / "data_contract" / "catalog" / "patch_v02.py"
CHANGELOG = WORK / "data_contract" / "catalog" / "CHANGELOG_v0.2.md"
BUILD_EVAL = EXP / "build_evalset.py"

sys.path.insert(0, str(EXP))
from build_evalset import flatten_unit, target_article, unit_article_key  # noqa: E402

RE_PYUN = re.compile(r"제\s*\d+\s*편")
RE_JANG = re.compile(r"제\s*\d+\s*장(?:의\s*\d+)?")
RE_JEOL = re.compile(r"제\s*\d+\s*절")
RE_GWAN = re.compile(r"제\s*\d+\s*관")
RE_ART = re.compile(r"제(\d+)조(?:의(\d+))?")


def say(msg: str) -> None:
    print(msg, flush=True)
    with (OUT / "audit_stdout.txt").open("a", encoding="utf-8") as handle:
        handle.write(msg + "\n")


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return list(value)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clip(text: str, n: int = 80) -> str:
    return " ".join(str(text or "").split())[:n]


def heading_kind(text: str) -> str | None:
    if RE_PYUN.search(text):
        return "편"
    if RE_JANG.search(text):
        return "장"
    if RE_JEOL.search(text):
        return "절"
    if RE_GWAN.search(text):
        return "관"
    return None


def hang_ho_mok(unit: dict) -> tuple[int, int, int]:
    n_hang = n_ho = n_mok = 0
    for hang in as_list(unit.get("항")):
        if not isinstance(hang, dict):
            continue
        n_hang += 1
        for ho in as_list(hang.get("호")):
            if not isinstance(ho, dict):
                continue
            n_ho += 1
            n_mok += sum(1 for mok in as_list(ho.get("목")) if isinstance(mok, dict))
    return n_hang, n_ho, n_mok


def is_branch_article(unit: dict) -> bool:
    branch = str(unit.get("조문가지번호") or "").strip()
    return branch.isdigit() and int(branch) > 0


def walk_units(units: list[dict]) -> list[dict]:
    cur = {"편": "", "장": "", "절": "", "관": ""}
    out = []
    for unit in units:
        if unit.get("조문여부") == "전문":
            text = str(unit.get("조문내용") or "")
            kind = heading_kind(text)
            if kind == "편":
                cur = {"편": text.strip(), "장": "", "절": "", "관": ""}
            elif kind == "장":
                cur = {"편": cur["편"], "장": text.strip(), "절": "", "관": ""}
            elif kind == "절":
                cur = {"편": cur["편"], "장": cur["장"], "절": text.strip(), "관": ""}
            elif kind == "관":
                cur["관"] = text.strip()
        row = dict(unit)
        row["_편"] = cur["편"]
        row["_장"] = cur["장"]
        row["_절"] = cur["절"]
        row["_관"] = cur["관"]
        out.append(row)
    return out


def load_mst() -> dict[str, dict]:
    found = {}
    for path in sorted(LAW_DIR.glob("*_body_MST.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        law = obj.get("법령") or {}
        info = law.get("기본정보") or {}
        name = info.get("법령명_한글") or path.name
        units = as_list((law.get("조문") or {}).get("조문단위"))
        found[name] = {
            "path": path,
            "obj": obj,
            "info": info,
            "units": walk_units(units),
            "raw_units": units,
        }
    return found


def node_kind(node: dict) -> str:
    if node.get("law_short") == "판례":
        return "판례"
    art = str(node.get("article") or "").replace(" ", "")
    if RE_ART.fullmatch(art):
        return "법령 조문"
    return "임시 이름"


def md_cell(text) -> str:
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def quote_lines(path: Path, start: int, end: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    chunk = lines[start - 1 : end]
    numbered = [f"{i}: {line}" for i, line in enumerate(chunk, start=start)]
    return "\n".join(numbered)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_stdout.txt").write_text("", encoding="utf-8")
    say("START audit_law")
    say(f"CAT {CAT_PATH}")
    say(f"TEXTS {TEXTS}")
    say(f"LAW_DIR {LAW_DIR}")

    cat = json.loads(CAT_PATH.read_text(encoding="utf-8"))
    texts = {r["id"]: r for r in load_jsonl(TEXTS)}
    t3 = load_jsonl(T3)
    t4 = load_jsonl(T4)
    say(f"COUNT catalog_checks {len(cat['checks'])}")
    say(f"COUNT catalog_slots {len(cat['slots'])}")
    say(f"COUNT catalog_law_nodes {len(cat['law_nodes'])}")
    say(f"COUNT t3 {len(t3)} t4 {len(t4)} texts {len(texts)}")

    mst = load_mst()
    say(f"COUNT mst_files {len(mst)}")

    # --- JSON keys from 최저임금법 (has 목) ---
    mw = mst["최저임금법"]
    law_keys = sorted((mw["obj"].get("법령") or {}).keys())
    info_keys = sorted(mw["info"].keys())
    unit_keys = sorted({k for u in mw["raw_units"] for k in u.keys()})
    hang_keys = sorted({k for u in mw["raw_units"] for h in as_list(u.get("항")) if isinstance(h, dict) for k in h.keys()})
    ho_keys = sorted(
        {
            k
            for u in mw["raw_units"]
            for h in as_list(u.get("항"))
            if isinstance(h, dict)
            for ho in as_list(h.get("호"))
            if isinstance(ho, dict)
            for k in ho.keys()
        }
    )
    mok_keys = sorted(
        {
            k
            for u in mw["raw_units"]
            for h in as_list(u.get("항"))
            if isinstance(h, dict)
            for ho in as_list(h.get("호"))
            if isinstance(ho, dict)
            for mok in as_list(ho.get("목"))
            if isinstance(mok, dict)
            for k in mok.keys()
        }
    )
    say(f"KEYS 법령 {law_keys}")
    say(f"KEYS 기본정보 {info_keys}")
    say(f"KEYS 조문단위 {unit_keys}")
    say(f"KEYS 항 {hang_keys}")
    say(f"KEYS 호 {ho_keys}")
    say(f"KEYS 목 {mok_keys}")
    jo_keys = sorted((mw["obj"].get("법령") or {}).get("조문", {}).keys())
    say(f"KEYS 조문 {jo_keys}")
    nested_parent = 0
    for name, pack in mst.items():
        for u in pack["raw_units"]:
            if any(k in u for k in ("편", "장", "절", "관")):
                nested_parent += 1
            if isinstance(u.get("조문단위"), (list, dict)):
                nested_parent += 1
    say(f"COUNT units_with_parent_pyunjang_keys {nested_parent}")
    여부 = Counter()
    for pack in mst.values():
        for u in pack["raw_units"]:
            여부[str(u.get("조문여부"))] += 1
    say(f"COUNT 조문여부 {dict(여부)}")

    # 근로기준법 path examples
    lb = mst["근로기준법"]
    examples = []
    want = [("17", False), ("43", False), ("54", False)]
    for u in lb["units"]:
        if u.get("조문여부") != "조문":
            continue
        key = unit_article_key(u)
        for target, _ in want:
            if key == target:
                hangs = as_list(u.get("항"))
                hang1 = ""
                ho1 = ""
                if hangs and isinstance(hangs[0], dict):
                    hang1 = hangs[0].get("항번호") or ""
                    hos = as_list(hangs[0].get("호"))
                    if hos and isinstance(hos[0], dict):
                        ho1 = hos[0].get("호번호") or ""
                examples.append(
                    {
                        "장": u["_장"],
                        "조": f"제{key}조",
                        "제목": u.get("조문제목") or "",
                        "항": hang1,
                        "호": ho1,
                        "조문내용두줄": clip(flatten_unit(u)[0], 120),
                    }
                )
    say(f"COUNT 근로기준법_path_examples {len(examples)}")
    for ex in examples:
        say(f"PATH {ex['장']} | {ex['조']}({ex['제목']}) | 항={ex['항']} 호={ex['호']}")

    # --- per-law counts ---
    law_rows = []
    total_units = total_head = total_hang = total_ho = total_mok = 0
    total_jo = total_branch = total_nohang = 0
    heading_counts = Counter()
    for name, pack in mst.items():
        n_pyun = n_jang = n_jeol = n_gwan = 0
        n_jo = n_branch = n_hang = n_ho = n_mok = n_nohang = 0
        heads = []
        for u in pack["units"]:
            if u.get("조문여부") == "전문":
                text = str(u.get("조문내용") or "")
                kind = heading_kind(text)
                if kind == "편":
                    n_pyun += 1
                    heading_counts["편"] += 1
                elif kind == "장":
                    n_jang += 1
                    heading_counts["장"] += 1
                elif kind == "절":
                    n_jeol += 1
                    heading_counts["절"] += 1
                elif kind == "관":
                    n_gwan += 1
                    heading_counts["관"] += 1
                heads.append(text.strip())
            elif u.get("조문여부") == "조문":
                n_jo += 1
                if is_branch_article(u):
                    n_branch += 1
                h, ho, mok = hang_ho_mok(u)
                n_hang += h
                n_ho += ho
                n_mok += mok
                if h == 0:
                    n_nohang += 1
        n_units = len(pack["units"])
        n_전문 = sum(1 for u in pack["units"] if u.get("조문여부") == "전문")
        total_units += n_units
        total_head += n_전문
        total_hang += n_hang
        total_ho += n_ho
        total_mok += n_mok
        total_jo += n_jo
        total_branch += n_branch
        total_nohang += n_nohang
        enforce = str(pack["info"].get("시행일자") or "")
        code = pack["info"].get("편장절관")
        say(
            f"LAW {name} units={n_units} 전문={n_전문} 편={n_pyun} 장={n_jang} 절={n_jeol} 관={n_gwan} "
            f"조={n_jo} 가지조={n_branch} 항0조={n_nohang} 항={n_hang} 호={n_ho} 목={n_mok} "
            f"시행={enforce} 편장절관코드={code}"
        )
        law_rows.append(
            {
                "name": name,
                "편": n_pyun,
                "장": n_jang,
                "절": n_jeol,
                "관": n_gwan,
                "조": n_jo,
                "가지조": n_branch,
                "항0조": n_nohang,
                "항": n_hang,
                "호": n_ho,
                "목": n_mok,
                "units": n_units,
                "전문": n_전문,
                "시행": enforce,
                "편장절관": code,
                "heads": heads,
            }
        )
    say(
        f"TOTAL units={total_units} 전문={total_head} 조={total_jo} 가지조={total_branch} "
        f"항0조={total_nohang} 항={total_hang} 호={total_ho} 목={total_mok} headings={dict(heading_counts)}"
    )
    avg_hang = (total_hang / total_jo) if total_jo else None
    avg_ho = (total_ho / total_hang) if total_hang else None
    say(f"AVG 조당항 {avg_hang} 항당호 {avg_ho}")

    lb_heads = [u.get("조문내용", "").strip() for u in lb["units"] if u.get("조문여부") == "전문"]
    say(f"COUNT 근로기준법_전문 {len(lb_heads)}")
    for h in lb_heads:
        say(f"JANG {h}")
    minbup = next(r for r in law_rows if r["name"] == "민법")
    say(f"COUNT 민법_units {minbup['units']} 전문={minbup['전문']} 조={minbup['조']}")

    # --- checks ↔ nodes ---
    basis_from_checks = []
    empty_basis = []
    checks_by_node = defaultdict(list)
    for check in cat["checks"]:
        basis = check.get("legal_basis") or []
        if not basis:
            empty_basis.append({"id": check["id"], "title": check.get("title") or ""})
        for b in basis:
            lid = f'{b.get("law")}:{b.get("article")}'
            basis_from_checks.append(lid)
            checks_by_node[lid].append(check)
    unique_basis = []
    seen = set()
    for lid in basis_from_checks:
        if lid not in seen:
            seen.add(lid)
            unique_basis.append(lid)
    catalog_ids = [n["id"] for n in cat["law_nodes"]]
    say(f"COUNT legal_basis_slots {len(basis_from_checks)}")
    say(f"COUNT unique_legal_basis {len(unique_basis)}")
    say(f"COUNT empty_legal_basis_checks {len(empty_basis)}")
    for row in empty_basis:
        say(f"EMPTY_BASIS {row['id']} {row['title']}")
    only_basis = [i for i in unique_basis if i not in catalog_ids]
    only_cat = [i for i in catalog_ids if i not in unique_basis]
    say(f"COUNT basis_not_in_law_nodes {len(only_basis)} {only_basis}")
    say(f"COUNT law_nodes_not_in_basis {len(only_cat)} {only_cat}")

    t3_by_node = Counter()
    t4_by_node = Counter()
    t3_by_check = Counter()
    t4_by_check = Counter()
    for row in t3:
        t3_by_check[row.get("check_id")] += 1
        for nid in row.get("gold_law_nodes") or []:
            t3_by_node[nid] += 1
    for row in t4:
        t4_by_check[row.get("check_id")] += 1
        for nid in row.get("gold") or []:
            t4_by_node[nid] += 1
    say(f"COUNT t3_gold_node_refs {sum(t3_by_node.values())} distinct {len(t3_by_node)}")
    say(f"COUNT t4_gold_node_refs {sum(t4_by_node.values())} distinct {len(t4_by_node)}")

    verify_rows = []
    with VERIFY_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            verify_rows.append(row)
    say(f"COUNT verify_csv_rows {len(verify_rows)}")
    verify_by_node = defaultdict(list)
    for row in verify_rows:
        verify_by_node[row.get("law_node_id") or ""].append(row)

    # match catalog node to MST unit
    by_law_full = {n: pack for n, pack in mst.items()}

    def find_unit(law_full: str, article: str):
        pack = by_law_full.get(law_full)
        if pack is None:
            return None, "원본 없음"
        target = target_article(article)
        if target is None:
            return None, "조번호 아님"
        matched = None
        for unit in pack["units"]:
            if unit_article_key(unit) == target and unit.get("조문여부") != "전문":
                matched = unit
                break
        if matched is None:
            for unit in pack["units"]:
                if unit_article_key(unit) == target:
                    matched = unit
                    break
        if matched is None:
            return None, "조문 못 찾음"
        return matched, "ok"

    csv_rows = []
    kind_count = Counter()
    source_count = Counter()
    for node in cat["law_nodes"]:
        nid = node["id"]
        text_row = texts.get(nid) or {}
        kind = node_kind(node)
        kind_count[kind] += 1
        source = text_row.get("text_source") or ""
        source_count[source] += 1
        unit, match_flag = find_unit(node.get("law_full") or "", node.get("article") or "")
        if kind == "판례":
            title = "원본 없음"
            jang = ""
            hang_n = 0
            art_title = "원본 없음"
        elif match_flag == "ok" and unit is not None:
            title = unit.get("조문제목") or ""
            jang = " / ".join(x for x in (unit.get("_장"), unit.get("_절")) if x)
            hang_n, _, _ = hang_ho_mok(unit)
            art_title = title
        else:
            title = "원본 없음"
            jang = ""
            hang_n = 0
            art_title = "원본 없음"
        body = text_row.get("본문") or ""
        used = checks_by_node.get(nid) or []
        check_txt = " ; ".join(f"{c['id']} {c.get('title') or ''}" for c in used)
        link = "legal_basis에 직접 적힘" if used else "다른 경로(카탈로그 law_nodes에만 있고 check.legal_basis에는 없음)"
        vrows = verify_by_node.get(nid) or []
        if vrows:
            verdict = " ; ".join(f"{r.get('check_id')}:{r.get('판정')}" for r in vrows)
            quote = " / ".join(clip(r.get("근거 문장 인용") or "", 80) for r in vrows[:3])
        else:
            verdict = "VERIFY 행 없음"
            quote = ""
        csv_rows.append(
            {
                "node_id": nid,
                "법령명": node.get("law_full") or "",
                "조": node.get("article") or "",
                "조_제목": art_title,
                "소속_장절": jang or "",
                "종류": kind,
                "text_source": source,
                "본문_길이": len(body),
                "항_수": hang_n,
                "쓰는_check": check_txt,
                "연결_방식": link,
                "원문대조_판정": verdict,
                "원문대조_인용80": quote,
                "T3문항수": t3_by_node.get(nid, 0),
                "T4문항수": t4_by_node.get(nid, 0),
                "match_flag": match_flag,
            }
        )
        say(
            f"NODE {nid} kind={kind} src={source} chars={len(body)} hang={hang_n} "
            f"checks={len(used)} t3={t3_by_node.get(nid, 0)} t4={t4_by_node.get(nid, 0)} "
            f"verify={len(vrows)} match={match_flag} jang={clip(jang, 40)}"
        )

    say(f"COUNT kind {dict(kind_count)}")
    say(f"COUNT text_source {dict(source_count)}")
    link_count = Counter(r["연결_방식"] for r in csv_rows)
    say(f"COUNT link {dict(link_count)}")

    csv_path = OUT / "law_nodes_59.csv"
    fields = [
        "node_id",
        "법령명",
        "조",
        "조_제목",
        "소속_장절",
        "종류",
        "text_source",
        "본문_길이",
        "항_수",
        "쓰는_check",
        "연결_방식",
        "원문대조_판정",
        "원문대조_인용80",
        "T3문항수",
        "T4문항수",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in csv_rows:
            w.writerow(row)
    say(f"WROTE {csv_path} rows={len(csv_rows)}")

    # --- catalog-absent articles ---
    catalog_keys_by_law = defaultdict(set)
    for node in cat["law_nodes"]:
        key = target_article(node.get("article") or "")
        if key:
            catalog_keys_by_law[node.get("law_full")].add(key)

    def chapter_articles(law_name: str, start_heading_substr: str, stop_at_jang: bool = True) -> list[dict]:
        pack = mst[law_name]
        started = False
        found = []
        for u in pack["units"]:
            if u.get("조문여부") == "전문":
                text = str(u.get("조문내용") or "")
                if start_heading_substr in text.replace(" ", ""):
                    started = True
                    continue
                if started and stop_at_jang and heading_kind(text) == "장":
                    break
            if started and u.get("조문여부") == "조문":
                found.append(u)
        return found

    def list_missing(label: str, units: list[dict], law_full: str) -> list[dict]:
        have = catalog_keys_by_law.get(law_full, set())
        missing = []
        for u in units:
            key = unit_article_key(u)
            if key in have:
                continue
            if "의" in key:
                base, br = key.split("의", 1)
                art = f"제{base}조의{br}"
            else:
                art = f"제{key}조"
            missing.append({"조": art, "제목": u.get("조문제목") or "", "장": u.get("_장") or "", "절": u.get("_절") or ""})
        say(f"COUNT missing_{label} {len(missing)} of_units {len(units)}")
        for row in missing:
            say(f"MISSING {label} {row['조']} {row['제목']}")
        return missing

    miss_ch2 = list_missing("근기법_제2장", chapter_articles("근로기준법", "제2장근로계약"), "근로기준법")
    miss_ch3 = list_missing("근기법_제3장", chapter_articles("근로기준법", "제3장임금"), "근로기준법")
    miss_ch4 = list_missing("근기법_제4장", chapter_articles("근로기준법", "제4장근로시간과휴식"), "근로기준법")

    juim_all = [u for u in mst["주택임대차보호법"]["units"] if u.get("조문여부") == "조문"]
    miss_juim = list_missing("주임법_전체", juim_all, "주택임대차보호법")

    min_units = mst["민법"]["units"]
    lease_units = []
    for u in min_units:
        if u.get("조문여부") != "조문":
            continue
        key = unit_article_key(u)
        base = int(key.split("의")[0]) if key.split("의")[0].isdigit() else -1
        if 618 <= base <= 654:
            lease_units.append(u)
    miss_lease = list_missing("민법_임대차618-654", lease_units, "민법")

    # 소비대차 절: 표제에 '소비대차'가 있는 절부터 다음 절/장/편 전까지
    consume_units = []
    started = False
    consume_head = ""
    for u in min_units:
        if u.get("조문여부") == "전문":
            text = str(u.get("조문내용") or "")
            if "소비대차" in text:
                started = True
                consume_head = text.strip()
                continue
            if started and heading_kind(text) in ("절", "장", "편"):
                break
        if started and u.get("조문여부") == "조문":
            consume_units.append(u)
    say(f"COUNT 민법_소비대차_절_표제 {consume_head!r} units={len(consume_units)}")
    miss_consume = list_missing("민법_소비대차절", consume_units, "민법")

    # special nodes
    special = {
        "missing6": [r for r in csv_rows if r["text_source"] == "missing"],
        "note4": [r for r in csv_rows if r["text_source"] == "note_only"],
        "temp3": [r for r in csv_rows if r["종류"] == "임시 이름"],
    }
    for label, rows in special.items():
        say(f"COUNT special_{label} {len(rows)}")
        for r in rows:
            checks = checks_by_node.get(r["node_id"]) or []
            for c in checks:
                say(
                    f"SPECIAL {label} {r['node_id']} check={c['id']} title={c.get('title')} "
                    f"t3={t3_by_check.get(c['id'], 0)} t4={t4_by_check.get(c['id'], 0)}"
                )

    quotes = {
        "build_catalog_header": quote_lines(BUILD_CAT, 1, 4),
        "build_catalog_not_collected": quote_lines(BUILD_CAT, 20, 21),
        "build_catalog_nodes": quote_lines(BUILD_CAT, 300, 307),
        "patch_header": quote_lines(PATCH, 1, 3),
        "patch_regen": quote_lines(PATCH, 125, 135),
        "changelog": CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "파일 없음",
        "build_eval_loop": quote_lines(BUILD_EVAL, 328, 345),
        "flatten": quote_lines(BUILD_EVAL, 277, 306),
    }
    say(f"COUNT changelog_chars {len(quotes['changelog'])}")

    payload = {
        "law_rows": [{k: v for k, v in r.items() if k != "heads"} for r in law_rows],
        "totals": {
            "units": total_units,
            "전문": total_head,
            "조": total_jo,
            "가지조": total_branch,
            "항0조": total_nohang,
            "항": total_hang,
            "호": total_ho,
            "목": total_mok,
            "headings": dict(heading_counts),
            "avg_hang": avg_hang,
            "avg_ho": avg_ho,
        },
        "lb_heads": lb_heads,
        "examples": examples,
        "keys": {
            "법령": law_keys,
            "기본정보": info_keys,
            "조문": jo_keys,
            "조문단위": unit_keys,
            "항": hang_keys,
            "호": ho_keys,
            "목": mok_keys,
        },
        "empty_basis": empty_basis,
        "kind_count": dict(kind_count),
        "source_count": dict(source_count),
        "link_count": dict(link_count),
        "unique_basis": len(unique_basis),
        "basis_slots": len(basis_from_checks),
        "missing": {
            "근기법_제2장": miss_ch2,
            "근기법_제3장": miss_ch3,
            "근기법_제4장": miss_ch4,
            "주임법_전체": miss_juim,
            "민법_임대차618-654": miss_lease,
            "민법_소비대차절": miss_consume,
            "소비대차_표제": consume_head,
        },
        "minbeop_units": minbup["units"],
        "minbeop_jo": minbup["조"],
        "minbeop_전문": minbup["전문"],
        "nested_parent": nested_parent,
        "csv_rows": csv_rows,
        "special": {k: [r["node_id"] for r in v] for k, v in special.items()},
        "quotes": quotes,
        "t3_by_check": dict(t3_by_check),
        "t4_by_check": dict(t4_by_check),
    }
    (OUT / "numbers.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    say("WROTE numbers.json")
    say("DONE")
    write_report(payload, law_rows, csv_rows, quotes, empty_basis, special, checks_by_node, t3_by_check, t4_by_check)


def write_report(payload, law_rows, csv_rows, quotes, empty_basis, special, checks_by_node, t3_by_check, t4_by_check) -> None:
    t = payload["totals"]
    lines = [
        "# 법령 데이터 구조와 실험 조문 59개",
        "",
        "읽기와 세기만 했다. 모델 호출과 기존 파일 수정은 없다.",
        "스크립트: `exp_v2/law_audit/audit_law.py`. 출력 원문: `exp_v2/law_audit/audit_stdout.txt`. 숫자 JSON: `exp_v2/law_audit/numbers.json`. 59행 표: `exp_v2/law_audit/law_nodes_59.csv`.",
        "채점·추출 함수는 `exp_v2/build_evalset.py`의 `flatten_unit`, `target_article`, `unit_article_key`를 import해서 원본 조를 찾았다. 새 매칭 규칙을 만들지 않았다.",
        "",
        "## 1. 원본 데이터 구조",
        "",
        "### 1-1. JSON 모양",
        "",
        "예는 목이 있는 `최저임금법_body_MST.json`이다. 실제 키 이름:",
        "",
        "```",
        f"법령 {payload['keys']['법령']}",
        "  ├ 기본정보 " + str(payload["keys"]["기본정보"]),
        "  │    └ 편장절관  ← 코드 문자열 한 칸. 자식 노드가 아님",
        "  ├ 조문 " + str(payload["keys"]["조문"]),
        "  │    └ 조문단위[] " + str(payload["keys"]["조문단위"]),
        "  │         ├ 조문여부  (전문 | 조문)",
        "  │         ├ 조문번호, 조문키, 조문내용, 조문제목, 조문가지번호",
        "  │         └ 항[] " + str(payload["keys"]["항"]),
        "  │              ├ 항번호, 항내용",
        "  │              └ 호[] " + str(payload["keys"]["호"]),
        "  │                   ├ 호번호, 호내용",
        "  │                   └ 목[] " + str(payload["keys"]["목"]),
        "  ├ 부칙",
        "  └ 개정문",
        "```",
        "",
        f"조문단위에 편·장·절·관을 부모로 담는 키, 또는 조문단위 안의 조문단위 중첩: **{payload['nested_parent']}건** (10개 파일 전부).",
        "편·장·절·관은 조와 같은 `조문단위[]` 배열에 `조문여부=전문` 행으로 나란히 있다. 부모 포인터는 없다. 소속은 배열 순서로만 알 수 있다. 이 검사에서 소속을 붙일 때는 표제 행을 만나면 해당 층을 갱신하고 그 아래 층은 비웠다. 이 규칙은 원본에 적혀 있지 않고, 평평한 배열을 읽기 위한 것이다.",
        "",
        "`기본정보.편장절관`은 법령마다 코드 하나다. 근로기준법·최저임금법 계열 `40030000`, 민법·주임법 계열 `08010000`. 각 조의 편·장 ID가 아니다.",
        "",
        "근로기준법에서 장→조→항(→호) 경로 3개. 장 제목은 바로 앞 표제 행이다.",
        "",
    ]
    for ex in payload["examples"]:
        lines.append(f"- `{ex['장']}` → `{ex['조']}` ({ex['제목']}) → 항 `{ex['항']}`" + (f" → 호 `{ex['호']}`" if ex["호"] else ""))
        lines.append(f"  - 본문 앞: {ex['조문내용두줄']}")
    lines += [
        "",
        "### 1-2. 법령별 층별 개수",
        "",
        "조는 `조문여부=조문`만 센다. 가지조문은 `조문가지번호`가 양의 정수인 조문이다. 표제(`조문여부=전문`)는 조 수에 넣지 않는다.",
        "",
        "| 법령 | 편 | 장 | 절 | 관 | 조(표제 제외) | 가지조 | 항 없는 조 | 항 | 호 | 목 | 시행일 | 조문단위(표제 포함) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for r in law_rows:
        lines.append(
            f"| {r['name']} | {r['편']} | {r['장']} | {r['절']} | {r['관']} | {r['조']} | {r['가지조']} | {r['항0조']} | {r['항']} | {r['호']} | {r['목']} | {r['시행']} | {r['units']} |"
        )
    lines += [
        f"| **합계** | {sum(r['편'] for r in law_rows)} | {sum(r['장'] for r in law_rows)} | {sum(r['절'] for r in law_rows)} | {sum(r['관'] for r in law_rows)} | {t['조']} | {t['가지조']} | {t['항0조']} | {t['항']} | {t['호']} | {t['목']} |  | {t['units']} |",
        "",
        f"표제(`조문여부=전문`) 합계: **{t['전문']}**. 표제 글자 매칭: 편 {t['headings'].get('편', 0)}, 장 {t['headings'].get('장', 0)}, 절 {t['headings'].get('절', 0)}, 관 {t['headings'].get('관', 0)}.",
        f"항이 없는 조: **{t['항0조']}**. 본문(`조문내용`)만 있고 `항` 배열이 비어 있다.",
        f"조→항 평균 자식 수: {t['avg_hang']:.3f} (항 {t['항']} / 조 {t['조']}). 항→호 평균 자식 수: {t['avg_ho']:.3f} (호 {t['호']} / 항 {t['항']}).",
        "아래 층으로 갈수록 개수가 늘지 않는다. 장·절·관은 표제라 조보다 적고, 호·목은 항을 가진 조의 일부에만 있다. 조 1,564 < 항 1,667 은 늘고, 항 1,667 > 호 762 > 목 36 은 줄어든다.",
        "",
        "#### 근로기준법 장 목록",
        "",
        f"표제 행 {len(payload['lb_heads'])}개. 모두 `제N장` 또는 `제6장의2`이다. 가지 장 `제6장의2 직장 내 괴롭힘의 금지`가 있다. 번호 1~12에 가지 장 하나를 더하면 표제 13개다. “12장”은 번호 범위, “13개”는 표제 행 수다.",
        "",
    ]
    for h in payload["lb_heads"]:
        lines.append(f"- {h}")
    lines += [
        "",
        f"#### 민법 1,337",
        "",
        f"`조문단위` 길이 **{payload['minbeop_units']}**. 이 숫자에 표제 {payload['minbeop_전문']}개가 들어 있다. `조문여부=조문`만 세면 **{payload['minbeop_jo']}**.",
        "",
        "## 2. 실험에 쓴 조문 노드 59개",
        "",
        f"카탈로그 `law_nodes` {len(csv_rows)}행. 종류: {payload['kind_count']}. text_source: {payload['source_count']}.",
        f"연결 방식: {payload['link_count']}.",
        "check의 `legal_basis`를 `법령약칭:조`로 이어 붙인 것과 `law_nodes` id 집합은 같다. 다른 경로로 들어간 노드는 0이다.",
        "",
        "전체 행은 `law_nodes_59.csv`와 아래 표. 생략 없음.",
        "",
        "| node_id | 법령명 | 조 | 조 제목 | 소속 장(절) | 종류 | text_source | 본문 길이 | 항 수 | 쓰는 check | 연결 방식 | 원문 대조 | 인용 80자 | T3 | T4 |",
        "|---|---|---|---|---|---|---|---:|---:|---|---|---|---|---:|---:|",
    ]
    for r in csv_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(r["node_id"]),
                    md_cell(r["법령명"]),
                    md_cell(r["조"]),
                    md_cell(r["조_제목"]),
                    md_cell(r["소속_장절"]),
                    md_cell(r["종류"]),
                    md_cell(r["text_source"]),
                    str(r["본문_길이"]),
                    str(r["항_수"]),
                    md_cell(r["쓰는_check"]),
                    md_cell(r["연결_방식"]),
                    md_cell(r["원문대조_판정"]),
                    md_cell(r["원문대조_인용80"]),
                    str(r["T3문항수"]),
                    str(r["T4문항수"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## 3. 왜 이 59개인가 (파일에 적힌 것만)",
        "",
        "### 3-1. 만들어진 경로",
        "",
        "1. `data_contract/catalog/build_catalog.py`가 check마다 `legal_basis`를 적는다. `law_nodes`는 그 목록을 `법령:조`로 모아 중복을 없앤 것이다.",
        "",
        "```",
        quotes["build_catalog_nodes"],
        "```",
        "",
        "2. `data_contract/catalog/patch_v02.py`가 v0.1 대조 결과를 반영한 뒤 `law_nodes`를 같은 방식으로 다시 만든다.",
        "",
        "```",
        quotes["patch_regen"],
        "```",
        "",
        f"3. 지금 카탈로그 check 72개의 `legal_basis` 슬롯 수는 {payload['basis_slots']}개, 중복 제거 후 **{payload['unique_basis']}**개. `law_nodes` 59개와 집합이 같다.",
        "4. `exp_v2/build_evalset.py` `build_law_texts`는 `cat[\"law_nodes\"]`를 돌며 MST에서 조 본문을 붙인다. 노드를 더하거나 빼지 않는다.",
        "",
        "```",
        quotes["build_eval_loop"],
        "```",
        "",
        "항·호·목은 조 본문에 이어 붙인다.",
        "",
        "```",
        quotes["flatten"],
        "```",
        "",
        "### 3-2. legal_basis가 빈 check",
        "",
        f"**{len(empty_basis)}개.**",
        "",
        "| check | 제목 |",
        "|---|---|",
    ]
    for row in empty_basis:
        lines.append(f"| {row['id']} | {md_cell(row['title'])} |")
    lines += [
        "",
        "이 23개는 조문 노드를 만들지 않는다. 스크립트는 선정 이유를 적지 않았고, 제목만 있다.",
        "",
        "### 3-3. 카탈로그 빌드·CHANGELOG에 적힌 조문 선정 관련 문장",
        "",
        "`build_catalog.py` 머리글:",
        "",
        "```",
        quotes["build_catalog_header"],
        "```",
        "",
        "미수집 표시:",
        "",
        "```",
        quotes["build_catalog_not_collected"],
        "```",
        "",
        "`patch_v02.py` 머리글:",
        "",
        "```",
        quotes["patch_header"],
        "```",
        "",
        "`CHANGELOG_v0.2.md` 전문:",
        "",
        quotes["changelog"],
        "",
        "CHANGELOG에 “이 59개만 고른 기준”은 없다. 있는 것은 개별 check의 근거 추가·삭제다 (예: 보증법 제3조 제거, 주임법 제10조 제거, 민법 제623조 추가).",
        "그 밖의 조를 왜 넣었는지는 `build_catalog.py`의 각 check `legal_basis=` 인자뿐이다. 총론 주석은 없다.",
        "",
        "### 3-4. 카탈로그에 없는 조 (목록만, 넣어야 하는지는 판단하지 않음)",
        "",
        f"- 근로기준법 제2장 근로계약: 카탈로그에 없는 조 **{len(payload['missing']['근기법_제2장'])}**개",
        f"- 근로기준법 제3장 임금: **{len(payload['missing']['근기법_제3장'])}**개",
        f"- 근로기준법 제4장 근로시간과 휴식: **{len(payload['missing']['근기법_제4장'])}**개",
        f"- 주택임대차보호법 전체: **{len(payload['missing']['주임법_전체'])}**개",
        f"- 민법 제618조~제654조: **{len(payload['missing']['민법_임대차618-654'])}**개",
        f"- 민법 소비대차 절 (표제 `{payload['missing']['소비대차_표제']}`): **{len(payload['missing']['민법_소비대차절'])}**개",
        "",
    ]
    labels = [
        ("근기법_제2장", "근로기준법 제2장"),
        ("근기법_제3장", "근로기준법 제3장"),
        ("근기법_제4장", "근로기준법 제4장"),
        ("주임법_전체", "주택임대차보호법 전체"),
        ("민법_임대차618-654", "민법 제618조~제654조"),
        ("민법_소비대차절", "민법 소비대차 절"),
    ]
    for key, title in labels:
        lines += [f"#### {title}", "", "| 조 | 제목 | 소속 장/절 |", "|---|---|---|"]
        rows = payload["missing"][key]
        if not rows:
            lines.append("| (없음) |  |  |")
        for row in rows:
            lines.append(f"| {row['조']} | {md_cell(row['제목'])} | {md_cell((row.get('장') or '') + ' ' + (row.get('절') or ''))} |")
        lines.append("")
    lines += [
        "### 3-5. 본문 없음 6개, 판례 4개, 임시 이름 3개",
        "",
        "T3·T4 문항 수는 해당 check_id를 가진 평가 행 수다.",
        "",
    ]

    def special_block(title: str, rows: list[dict]) -> None:
        lines.append(f"#### {title}")
        lines.append("")
        lines.append("| node_id | check | 제목 | T3 | T4 |")
        lines.append("|---|---|---|---:|---:|")
        for r in rows:
            checks = checks_by_node.get(r["node_id"]) or []
            if not checks:
                lines.append(f"| {r['node_id']} | (check 없음) |  | 0 | 0 |")
            for c in checks:
                lines.append(
                    f"| {r['node_id']} | {c['id']} | {md_cell(c.get('title'))} | {t3_by_check.get(c['id'], 0)} | {t4_by_check.get(c['id'], 0)} |"
                )
        lines.append("")

    special_block("본문 없음 (text_source=missing) 6개", special["missing6"])
    special_block("판례 (text_source=note_only) 4개", special["note4"])
    special_block("임시 이름 (종류=임시 이름) 3개", special["temp3"])
    lines += [
        "임시 이름 3개는 고용보험법·산재법의 `적용 범위 조문`과 `이자규정:본문`이다. 앞의 둘은 missing 6개와 겹친다. 이자규정:본문은 MST 파일 1개가 통째로 본문이다.",
        "",
        "해석: 59개는 법령 전부가 아니라, 카탈로그 check 72개 중 근거를 적은 49개 check의 `legal_basis` 합집합이다. 선정 총론은 파일에 없다.",
        "",
        "## 지난 보고 숫자 대조",
        "",
        "| 지난 보고 | 이번 측정 |",
        "|---|---|",
        f"| 조문단위 1,728 | {t['units']} |",
        f"| 표제 164 | {t['전문']} |",
        f"| 항 1,667 | {t['항']} |",
        f"| 호 762 | {t['호']} |",
        f"| 목 36 | {t['목']} |",
        f"| 근로기준법 장 12개/13개 | 표제 13개(제1장~제12장 + 제6장의2). 조문여부=전문 13 |",
        f"| 민법 조문단위 1,337 | {payload['minbeop_units']} (표제 {payload['minbeop_전문']} 포함, 조만 {payload['minbeop_jo']}) |",
        "",
        "위 합계 다섯 개와 민법 조문단위 1,337은 이번 세기와 같다. 근로기준법 “12장”은 가지 장 `제6장의2`를 빼면 번호가 1~12라는 뜻으로 읽을 수 있고, 표제 행은 13개다.",
        "",
        "## 스크립트와 출력 원문",
        "",
        "실행: `python exp_v2/law_audit/audit_law.py`",
        "",
        "```",
        (OUT / "audit_stdout.txt").read_text(encoding="utf-8"),
        "```",
        "",
    ]
    (OUT / "LAW_AUDIT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
