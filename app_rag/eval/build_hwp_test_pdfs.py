# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS: test 15장을 표준 양식(HWP/HWPX) 복사본에 넣어 HWP·PDF 생성.
모델/GPU 사용 안 함. 한글(win32com) 자동화만 사용.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from splitutil import SPLIT_FILE_V2, clean_twin_path, load_split_ids  # noqa: E402
from recall_dev import load_jsonl  # noqa: E402
from rag.paths import GOLD, OUT  # noqa: E402
from dev_eval import is_meta  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs"
LAB_FORM = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
LEASE_FORMS = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts"
SEED = 42

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
GIVEN = ["민수", "서연", "지훈", "하은", "도윤", "수아", "예준", "지아", "현우", "소율", "유진", "시우"]


def norm_codes(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(v)]


def load_domain_docs(domain: str) -> dict[str, dict]:
    ids = set(load_split_ids("test", domain, SPLIT_FILE_V2))
    rows = load_jsonl(GOLD[domain]["contract"])
    twin = clean_twin_path(domain)
    if twin.exists():
        rows = rows + load_jsonl(twin)
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.get("doc_id") in ids:
            by[r["doc_id"]].append(r)
    out = {}
    for did, segs in by.items():
        segs = sorted(
            segs,
            key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
        )
        labs = {s.get("label") for s in segs}
        codes = sorted({c for s in segs if s.get("label") == "toxic" for c in norm_codes(s.get("toxic_code"))})
        meta = next((s for s in segs if is_meta(s)), None)
        src = None
        for s in segs:
            if s.get("source_hwpx"):
                src = s.get("source_hwpx")
                break
        out[did] = {
            "segs": segs,
            "labs": labs,
            "codes": codes,
            "meta": meta,
            "source_hwpx": src,
            "is_toxic": "toxic" in labs,
            "is_clean": ("toxic" not in labs) and ("check" not in labs),
        }
    return out


def lab_dev_codes() -> set[str]:
    ids = load_split_ids("dev", "LAB", SPLIT_FILE_V2)
    rows = load_jsonl(GOLD["LAB"]["contract"])
    out: set[str] = set()
    for r in rows:
        if r.get("doc_id") in ids and r.get("label") == "toxic":
            out.update(norm_codes(r.get("toxic_code")))
    return out


def select_docs() -> dict:
    rng = random.Random(SEED)
    lab_dev = lab_dev_codes()
    selected = {"seed": SEED, "domains": {}}
    for dom in ("LAB", "LEASE", "LOAN"):
        docs = load_domain_docs(dom)
        toxic = [d for d, v in docs.items() if v["is_toxic"]]
        clean = [d for d, v in docs.items() if v["is_clean"]]
        rng.shuffle(toxic)
        rng.shuffle(clean)
        if dom == "LAB":
            toxic_sorted = sorted(
                toxic,
                key=lambda d: (0 if any(c not in lab_dev for c in docs[d]["codes"]) else 1, d),
            )
        else:
            toxic_sorted = list(toxic)
        picked: list[str] = []
        used: set[str] = set()
        for d in toxic_sorted:
            codes = set(docs[d]["codes"])
            if codes & used:
                continue
            picked.append(d)
            used |= codes
            if len(picked) >= 3:
                break
        if len(picked) < 3:
            for d in toxic_sorted:
                if d not in picked:
                    picked.append(d)
                if len(picked) >= 3:
                    break
        if dom == "LAB" and not any(any(c not in lab_dev for c in docs[d]["codes"]) for d in picked):
            for d in toxic_sorted:
                if any(c not in lab_dev for c in docs[d]["codes"]):
                    picked[-1] = d
                    break
        cleans = clean[:2]
        items = []
        for d in picked[:3]:
            items.append({"doc_id": d, "kind": "toxic", "codes": docs[d]["codes"], "reason": "toxic_code 겹침 최소 + seed42"})
        for d in cleans:
            items.append({"doc_id": d, "kind": "clean", "codes": [], "reason": "toxic0 check0, seed42 shuffle 상위"})
        if dom == "LAB":
            for it in items:
                if it["kind"] == "toxic":
                    it["dev_absent_codes"] = [c for c in it["codes"] if c not in lab_dev]
        selected["domains"][dom] = {"items": items, "docs": {d: docs[d] for d in [x["doc_id"] for x in items]}}
    return selected


class FakePool:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.phone_i = 0
        self.used_names: set[str] = set()

    def name(self) -> str:
        for _ in range(100):
            n = self.rng.choice(SURNAMES) + self.rng.choice(GIVEN)
            if n not in self.used_names:
                self.used_names.add(n)
                return n
        n = f"김테스트{len(self.used_names)}"
        self.used_names.add(n)
        return n

    def phone(self) -> str:
        # 010-0000-0000 부터
        n = self.phone_i
        self.phone_i += 1
        return f"010-{n // 10000:04d}-{n % 10000:04d}"

    def address(self, gu: str | None = None) -> str:
        gus = ["강남구", "서초구", "마포구", "관악구", "송파구", "영등포구", "성동구", "노원구"]
        roads = ["테헤란로", "올림픽로", "월드컵북로", "봉천로", "도산대로", "국회대로"]
        g = gu or self.rng.choice(gus)
        return f"서울특별시 {g} {self.rng.choice(roads)} {self.rng.randint(10, 99)}"


def fill_placeholders(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    # leftover placeholders → generic
    def _sub(m):
        key = m.group(1)
        if key not in mapping:
            # leave marker replaced by deterministic fake
            return mapping.setdefault(key, f"미정_{key}")
        return mapping[key]

    out = re.sub(r"\{\{([^{}]+)\}\}", _sub, out)
    return out


def build_fake_map(domain: str, doc_id: str, pool: FakePool, segs: list[dict]) -> dict[str, str]:
    blob = "\n".join(s.get("text") or "" for s in segs)
    keys = sorted(set(re.findall(r"\{\{([^{}]+)\}\}", blob)))
    m: dict[str, str] = {}
    # prioritize role names
    role_name_keys = [k for k in keys if any(x in k for x in ("이름", "성명", "대표"))]
    for k in role_name_keys:
        m[k] = pool.name()
    for k in keys:
        if k in m:
            continue
        if any(x in k for x in ("전화", "연락", "휴대폰", "핸드폰")):
            m[k] = pool.phone()
        elif any(x in k for x in ("주소", "소재", "사업장_이름", "임차주택")):
            m[k] = pool.address() if "주소" in k or "소재" in k else f"{pool.name()}점"
        elif "이름" in k or "성명" in k:
            m[k] = pool.name()
        elif "서명" in k:
            m[k] = "(서명)"
        else:
            m[k] = f"테스트{k}"
    # domain defaults
    if domain == "LAB":
        m.setdefault("사업주_이름", pool.name())
        m.setdefault("근로자_이름", pool.name())
        m.setdefault("사업장_이름", f"{pool.name()}사업장")
        m.setdefault("근로자_연락처", pool.phone())
        m.setdefault("근로자_주소", pool.address())
    if domain == "LEASE":
        m.setdefault("임대인_이름", pool.name())
        m.setdefault("임차인_이름", pool.name())
        m.setdefault("임대인_연락처", pool.phone())
        m.setdefault("임차인_연락처", pool.phone())
        m.setdefault("임대인_주소", pool.address())
        m.setdefault("임차인_주소", pool.address())
        m.setdefault("임차주택_주소", pool.address())
    if domain == "LOAN":
        m.setdefault("채권자_이름", pool.name())
        m.setdefault("채무자_이름", pool.name())
        m.setdefault("보증인_이름", pool.name())
        m.setdefault("채권자_전화", pool.phone())
        m.setdefault("채무자_전화", pool.phone())
        m.setdefault("채권자_주소", pool.address())
        m.setdefault("채무자_주소", pool.address())
    m["_doc_id"] = doc_id
    return m


class Hwp:
    def __init__(self):
        import win32com.client

        self.hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
        self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        try:
            self.hwp.SetMessageBoxMode(0x00010000)
        except Exception:
            pass

    def open(self, path: Path) -> None:
        ok = self.hwp.Open(str(path))
        if not ok:
            raise RuntimeError(f"Open failed: {path}")

    def clear_new(self) -> None:
        self.hwp.Clear(1)

    def move_doc_end(self) -> None:
        try:
            self.hwp.Run("MoveDocEnd")
        except Exception:
            pass

    def escape_table(self) -> None:
        """문서 끝이 표/셀 안이면 정답조항이 잘리므로 표 밖으로 이동 후 새 쪽."""
        self.move_doc_end()
        for cmd in ("MoveOutOfTable", "BreakTable", "Cancel"):
            try:
                self.hwp.Run(cmd)
            except Exception:
                pass
        # 양식 표/다단 레이아웃과 섞이면 PDF 추출 순서가 깨지므로 새 쪽에 기입
        for cmd in ("InsertPageBreak", "BreakPage"):
            try:
                self.hwp.Run(cmd)
                break
            except Exception:
                continue
        self.move_doc_end()

    def insert_text(self, text: str) -> None:
        # InsertText action; use real newlines
        act = self.hwp.CreateAction("InsertText")
        pset = act.CreateSet()
        pset.SetItem("Text", text)
        act.Execute(pset)

    def insert_lines(self, lines: list[str]) -> None:
        self.escape_table()
        # 한 번에 넣으면 일부 양식에서 유실되므로 줄 단위
        for i, line in enumerate(lines):
            self.move_doc_end()
            self.insert_text(line)
            self.insert_text("\r\n")

    def replace_all(self, old: str, new: str) -> None:
        if not old or old == new:
            return
        try:
            self.hwp.HAction.GetDefault("AllReplace", self.hwp.HParameterSet.HFindReplace.HSet)
            fr = self.hwp.HParameterSet.HFindReplace
            fr.FindString = old
            fr.ReplaceString = new
            fr.IgnoreFindString = 0
            fr.IgnoreReplaceString = 0
            fr.Direction = 0
            fr.MatchCase = 0
            fr.AllWordForms = 0
            fr.SeveralWords = 0
            fr.UseWildCards = 0
            fr.WholeWordOnly = 0
            fr.AutoSpell = 0
            fr.ReplaceMode = 1
            fr.IgnoreMessage = 1
            fr.FindType = 1
            self.hwp.HAction.Execute("AllReplace", fr.HSet)
        except Exception:
            # fallback: get text / set not available — ignore
            pass

    def save_as(self, path: Path, fmt: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        if fmt:
            self.hwp.SaveAs(str(path), fmt)
        else:
            self.hwp.SaveAs(str(path))
        # SaveAs can be async-ish; wait for file
        for _ in range(50):
            if path.exists() and path.stat().st_size > 0:
                return
            time.sleep(0.1)
        raise RuntimeError(f"SaveAs no file: {path}")

    def quit(self) -> None:
        try:
            self.hwp.Quit()
        except Exception:
            pass


def lab_form_kind(meta_text: str) -> str:
    t = meta_text or ""
    if "단시간" in t:
        return "단시간근로자"
    if "연소" in t:
        return "연소근로자"
    if "건설" in t:
        return "건설일용"
    if "기간" in t and "정함" in t:
        return "기간의 정함이 있는"
    return "표준(기간의 정함 없음)"


def wrap_line(text: str, width: int = 70) -> str:
    """문장 내용은 유지하고 공백 기준으로만 줄바꿈(한글 PDF 단 넘김 완화)."""
    if len(text) <= width:
        return text
    parts: list[str] = []
    buf = ""
    for tok in re.split(r"(\s+)", text):
        if not tok:
            continue
        if buf and len(buf) + len(tok) > width and not tok.isspace():
            parts.append(buf.rstrip())
            buf = tok.lstrip() if tok.isspace() else tok
        else:
            buf += tok
    if buf:
        parts.append(buf.rstrip())
    return "\r\n".join(p for p in parts if p)


def append_gold_block(h: Hwp, filled_segs: list[dict], place_note: str) -> list[dict]:
    """특약/본문에 정답 문장을 순서대로 삽입. 위치 기록 반환."""
    h.escape_table()
    chunks = ["\r\n\r\n【특약사항·정답조항】\r\n"]
    placements = []
    for i, seg in enumerate(filled_segs, 1):
        label = seg.get("label") or ""
        sid = seg.get("segment_id")
        text = seg.get("text_filled") or ""
        # 긴 한 줄이 PDF 단/표에 쪼개지지 않도록 공백 기준 줄바꿈(문장 글자는 동일)
        chunks.append(f"{i}. {wrap_line(text)}\r\n")
        placements.append(
            {
                "segment_id": sid,
                "label": label,
                "std_item": seg.get("std_item"),
                "place": f"{place_note} #{i}",
                "order": seg.get("order"),
            }
        )
    # 한 번에 넣어 MoveDocEnd가 양식 표로 되돌아가지 않게 함
    h.insert_text("".join(chunks))
    return placements


def known_form_pii_replacements(fake: dict[str, str]) -> list[tuple[str, str]]:
    """양식에 흔한 실명·연락처 샘플 → 가짜 값. 알려진 샘플만."""
    pairs = []
    # LEASE sample names seen in MONTHLY forms
    samples = ["박서영", "이서준", "김민수", "최지현", "정도윤", "한소희", "윤서준", "강예은"]
    # assign sequential fakes
    for i, name in enumerate(samples):
        pairs.append((name, fake.get("_extra_names", [fake.get("임대인_이름", "김민수")])[0] if False else None))
    return []  # filled per-doc below


def build_one(h: Hwp, domain: str, kind: str, doc_id: str, doc: dict, pool: FakePool) -> dict:
    segs = doc["segs"]
    fake = build_fake_map(domain, doc_id, pool, segs)
    # materialize filled texts
    filled = []
    for s in segs:
        row = dict(s)
        row["text_filled"] = fill_placeholders(s.get("text") or "", fake)
        filled.append(row)

    out_stem = f"{domain}_{kind}_{doc_id}"
    out_hwp = OUT_DIR / f"{out_stem}.hwp"
    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    form_used = None
    form_kept: list[str] = []
    placements: list[dict] = []

    if domain == "LAB":
        form_used = str(LAB_FORM.relative_to(WORK)).replace("\\", "/")
        # copy form
        tmp = OUT_DIR / f"_tmp_{out_stem}.hwp"
        shutil.copy2(LAB_FORM, tmp)
        h.open(tmp)
        meta_txt = (doc["meta"] or {}).get("text") or ""
        kind_form = lab_form_kind(meta_txt)
        # replace blank-ish party markers with fakes where possible
        h.replace_all("(이하 “사업주”라 함)", f"{fake['사업주_이름']}(이하 “사업주”라 함)")
        h.replace_all('(이하 "사업주"라 함)', f"{fake['사업주_이름']}(이하 \"사업주\"라 함)")
        h.replace_all("(이하 “근로자”라 함)", f"{fake['근로자_이름']}(이하 “근로자”라 함)")
        h.replace_all('(이하 "근로자"라 함)', f"{fake['근로자_이름']}(이하 \"근로자\"라 함)")
        # append exact gold texts
        placements = append_gold_block(h, filled, f"특약(양식={kind_form})")
        form_kept.append("표준근로계약서(7종) 양식 본문 유지 — 항목 칸·안내문은 정답 매핑 없이 남김")
        h.save_as(out_hwp)
        h.save_as(out_pdf, "PDF")
        try:
            tmp.unlink()
        except Exception:
            pass

    elif domain == "LEASE":
        src_rel = doc.get("source_hwpx") or ""
        src = WORK / "datasets" / "property" / src_rel.replace("/", "\\") if src_rel else None
        if not src or not src.exists():
            # fallback by type from meta
            meta = ((doc["meta"] or {}).get("text") or "")
            pref = "JEONSE" if "전세" in meta else "MONTHLY"
            cands = sorted(LEASE_FORMS.glob(f"{pref}_*.hwpx"))
            src = cands[0] if cands else sorted(LEASE_FORMS.glob("*.hwpx"))[0]
            src_rel = str(src.relative_to(WORK / "datasets" / "property")).replace("\\", "/")
        form_used = src_rel if src_rel.startswith("source_hwpx") else f"source_hwpx_originals/contracts/{src.name}"
        # ensure path under originals
        if "source_hwpx_originals" not in str(src):
            # map contracts/ X to originals if possible
            alt = LEASE_FORMS / src.name
            if alt.exists():
                src = alt
                form_used = f"source_hwpx_originals/contracts/{src.name}"
        tmp = OUT_DIR / f"_tmp_{out_stem}.hwpx"
        shutil.copy2(src, tmp)
        h.open(tmp)
        # replace likely real names found in form extract later; do common replacements now
        # Use fake lessor/lessee
        # Will also run generic replacements after save via second pass if needed
        # Append gold
        placements = append_gold_block(h, filled, "특약(임대 양식)")
        form_kept.append("주택임대차 표준/원본 HWPX 본문 유지 — 원 조항·안내문은 정답 없음으로 남김")
        # replace some visible sample names with fakes (common in these forms)
        for old, new in [
            ("박서영", fake.get("임대인_이름", "김민수")),
            ("이서준", fake.get("임차인_이름", "이서연")),
        ]:
            h.replace_all(old, new)
        h.save_as(out_hwp)
        h.save_as(out_pdf, "PDF")
        try:
            tmp.unlink()
        except Exception:
            pass

    else:  # LOAN new doc
        form_used = "(new) 금전차용계약서(차용증)"
        h.clear_new()
        lines = [
            "금전차용계약서(차용증)",
            "",
            "【당사자】",
            f"채권자 성명: {fake['채권자_이름']}  주소: {fake['채권자_주소']}  연락처: {fake['채권자_전화']}",
            f"채무자 성명: {fake['채무자_이름']}  주소: {fake['채무자_주소']}  연락처: {fake['채무자_전화']}",
            "",
            "【조항】",
        ]
        h.insert_lines(lines)
        placements = []
        for i, seg in enumerate(filled, 1):
            text = seg.get("text_filled") or ""
            h.insert_text(f"제{i}조 {text}\r\n")
            placements.append(
                {
                    "segment_id": seg.get("segment_id"),
                    "label": seg.get("label"),
                    "std_item": seg.get("std_item"),
                    "place": f"제{i}조",
                    "order": seg.get("order"),
                }
            )
        h.insert_text("\r\n【서명】\r\n채권자 (서명) ________  채무자 (서명) ________\r\n")
        form_kept = []
        h.save_as(out_hwp)
        h.save_as(out_pdf, "PDF")

    return {
        "doc_id": doc_id,
        "domain": domain,
        "kind": kind,
        "form": form_used,
        "hwp": str(out_hwp.relative_to(WORK)).replace("\\", "/"),
        "pdf": str(out_pdf.relative_to(WORK)).replace("\\", "/"),
        "fake_values": {k: v for k, v in fake.items() if not k.startswith("_")},
        "segments": placements,
        "form_sentences_kept": form_kept,
        "toxic_codes": doc.get("codes") or [],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selected = select_docs()
    # write selection first
    sel_path = OUT_DIR / "selection.json"
    sel_lite = {
        "seed": SEED,
        "lab_dev_codes_note": "LAB toxic 중 1장 이상에 dev 없는 toxic_code 포함",
        "domains": {
            dom: selected["domains"][dom]["items"] for dom in ("LAB", "LEASE", "LOAN")
        },
    }
    sel_path.write_text(json.dumps(sel_lite, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", sel_path)

    pool = FakePool(SEED)
    h = Hwp()
    manifest = {"seed": SEED, "command": "python eval/build_hwp_test_pdfs.py", "docs": []}
    try:
        for dom in ("LAB", "LEASE", "LOAN"):
            block = selected["domains"][dom]
            for it in block["items"]:
                did = it["doc_id"]
                kind = it["kind"]
                print(f"BUILD {dom} {kind} {did}", flush=True)
                entry = build_one(h, dom, kind, did, block["docs"][did], pool)
                entry["select_reason"] = it.get("reason")
                if "dev_absent_codes" in it:
                    entry["dev_absent_codes"] = it["dev_absent_codes"]
                manifest["docs"].append(entry)
                print("  ->", entry["hwp"], entry["pdf"], flush=True)
    finally:
        h.quit()

    man_path = OUT_DIR / "manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", man_path, "n=", len(manifest["docs"]))


if __name__ == "__main__":
    main()
