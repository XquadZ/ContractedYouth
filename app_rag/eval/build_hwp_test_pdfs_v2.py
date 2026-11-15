# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS_FIX A장: test 15장을 실제 양식처럼 v2로 다시 만든다.
1차 datasets/test_hwp_pdfs 는 유지. 출력은 datasets/test_hwp_pdfs_v2.
모델/GPU/판정 없음. rag/ 코드 수정 없음.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from recall_dev import load_jsonl  # noqa: E402
from rag.paths import GOLD  # noqa: E402
from splitutil import clean_twin_path  # noqa: E402
from dev_eval import is_meta  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs_v2"
SEL_V1 = WORK / "datasets" / "test_hwp_pdfs" / "selection.json"
LAB_FORM = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
LEASE_FORMS = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts"
SEED = 42

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신"]
GIVEN = ["민수", "서연", "지훈", "하은", "도윤", "수아", "예준", "지아", "현우", "소율", "유진", "시우"]
SHOPS = ["카페 봄날", "한빛베이커리", "달빛서점", "푸른세탁소", "소망분식", "코너문구", "햇살미용실", "느티나무식당"]
HOUSE_TYPES = ["아파트", "다세대주택", "오피스텔", "연립주택", "단독주택"]
HOUSE_PARTS = ["3층 302호 전부", "2층 201호 전부", "101호 전부", "5층 502호 전부", "4층 401호 전부"]

# 7종 HWP 쪽 범위 (1-based, 프로브로 확인)
LAB_PAGE_RANGES = {
    "표준(기간의 정함 없음)": (1, 2),
    "연소근로자": (3, 4),
    "건설일용": (5, 5),
    "단시간근로자": (6, 7),
    "외국인근로자": (8, 11),
}

LAB_STD_FIND = {
    "LAB-01": ["1. 근로개시일", "1. 근로계약기간"],
    "LAB-02": ["2. 근 무 장 소", "2. 근무장소", "2. 근 무장소"],
    "LAB-03": ["3. 업무의 내용", "3. 업무의 내용(직종)"],
    "LAB-04": ["4. 소정근로시간", "근로일 및 근로일별 근로시간"],
    "LAB-05": ["7. 임금", "6. 임 금", "5. 임 금", "임금"],
    "LAB-06": ["수습기간", "수습"],
    "LAB-07": ["연차유급휴가", "8. 연차", "연차"],
    "LAB-08": ["사회보험", "9. 사회보험"],
    "LAB-09": ["근로계약서 교부", "교부"],
    "LAB-10": ["기타"],
    "LAB-11": ["기타"],
    "LAB-12": ["기타"],
}


class FakePool:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.phone_i = 0
        self.used_names: set[str] = set()
        self.shop_i = 0

    def name(self) -> str:
        for _ in range(200):
            n = self.rng.choice(SURNAMES) + self.rng.choice(GIVEN)
            if n not in self.used_names:
                self.used_names.add(n)
                return n
        n = f"김민{len(self.used_names)}"
        self.used_names.add(n)
        return n

    def phone(self) -> str:
        n = self.phone_i
        self.phone_i += 1
        return f"010-0000-{n:04d}"

    def address(self) -> str:
        gus = ["강남구", "서초구", "마포구", "관악구", "송파구", "영등포구", "성동구", "노원구"]
        roads = ["테헤란로", "올림픽로", "월드컵북로", "봉천로", "도산대로", "국회대로"]
        return f"서울특별시 {self.rng.choice(gus)} {self.rng.choice(roads)} {self.rng.randint(10, 99)}"

    def shop(self) -> str:
        s = SHOPS[self.shop_i % len(SHOPS)]
        self.shop_i += 1
        return s

    def house_type(self) -> str:
        return self.rng.choice(HOUSE_TYPES)

    def house_part(self) -> str:
        return self.rng.choice(HOUSE_PARTS)


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
        if not self.hwp.Open(str(path)):
            raise RuntimeError(f"Open failed: {path}")

    def clear_new(self) -> None:
        self.hwp.Clear(1)

    def run(self, cmd: str) -> None:
        try:
            self.hwp.Run(cmd)
        except Exception:
            pass

    def move_doc_end(self) -> None:
        self.run("MoveDocEnd")

    def escape_table(self) -> None:
        self.move_doc_end()
        for cmd in ("MoveOutOfTable", "BreakTable", "Cancel"):
            self.run(cmd)
        self.move_doc_end()

    def insert_text(self, text: str) -> None:
        act = self.hwp.CreateAction("InsertText")
        pset = act.CreateSet()
        pset.SetItem("Text", text)
        act.Execute(pset)

    def find(self, s: str, from_begin: bool = True) -> bool:
        self.run("Cancel")
        if from_begin:
            self.run("MoveDocBegin")
        self.hwp.HAction.GetDefault("ForwardFind", self.hwp.HParameterSet.HFindReplace.HSet)
        fr = self.hwp.HParameterSet.HFindReplace
        fr.FindString = s
        fr.IgnoreMessage = 1
        fr.Direction = 1
        fr.FindType = 1
        try:
            return bool(self.hwp.HAction.Execute("ForwardFind", fr.HSet))
        except Exception:
            return False

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
            pass

    def save_as(self, path: Path, fmt: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        if fmt:
            self.hwp.SaveAs(str(path), fmt)
        else:
            self.hwp.SaveAs(str(path))
        for _ in range(80):
            if path.exists() and path.stat().st_size > 0:
                return
            time.sleep(0.1)
        raise RuntimeError(f"SaveAs no file: {path}")

    def quit(self) -> None:
        try:
            self.hwp.Quit()
        except Exception:
            pass

    def page_count(self) -> int:
        try:
            return int(self.hwp.PageCount)
        except Exception:
            return 0

    def keep_pages(self, start: int, end: int) -> None:
        """1-based inclusive page keep."""
        while self.page_count() > end:
            self.run("MoveDocEnd")
            self.run("DeletePage")
        for _ in range(max(0, start - 1)):
            self.run("MoveDocBegin")
            self.run("DeletePage")

    def create_table(self, rows: int, cols: int) -> bool:
        try:
            self.hwp.HAction.GetDefault("TableCreate", self.hwp.HParameterSet.HTableCreation.HSet)
            tc = self.hwp.HParameterSet.HTableCreation
            tc.Rows = rows
            tc.Cols = cols
            tc.WidthType = 2
            tc.HeightType = 0
            return bool(self.hwp.HAction.Execute("TableCreate", tc.HSet))
        except Exception:
            return False

    def table_right(self) -> None:
        self.run("TableRightCell")

    def table_down(self) -> None:
        self.run("TableLowerCell")


def fill_placeholders(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)

    def _sub(m):
        key = m.group(1)
        if key not in mapping:
            # never use the word 테스트
            if "유형" in key or "주택" in key:
                mapping[key] = "아파트"
            elif "부분" in key:
                mapping[key] = "3층 302호 전부"
            elif "이름" in key or "성명" in key:
                mapping[key] = "김민수"
            elif "전화" in key or "연락" in key:
                mapping[key] = "010-0000-0099"
            elif "주소" in key:
                mapping[key] = "서울특별시 강남구 테헤란로 10"
            else:
                mapping[key] = "해당없음"
        return mapping[key]

    return re.sub(r"\{\{([^{}]+)\}\}", _sub, out)


def build_fake_map(domain: str, pool: FakePool, segs: list[dict]) -> dict[str, str]:
    blob = "\n".join(s.get("text") or "" for s in segs)
    keys = sorted(set(re.findall(r"\{\{([^{}]+)\}\}", blob)))
    m: dict[str, str] = {}
    for k in keys:
        if any(x in k for x in ("전화", "연락", "휴대폰", "핸드폰")):
            m[k] = pool.phone()
        elif any(x in k for x in ("주소", "소재")):
            m[k] = pool.address()
        elif "주택_유형" in k or k.endswith("유형"):
            m[k] = pool.house_type()
        elif "임차할부분" in k or "임차할_부분" in k:
            m[k] = pool.house_part()
        elif "사업장" in k:
            m[k] = pool.shop()
        elif "서명" in k:
            m[k] = "(서명)"
        elif any(x in k for x in ("이름", "성명", "대표")):
            m[k] = pool.name()
        else:
            m[k] = pool.shop() if "장" in k else pool.name()
    if domain == "LAB":
        m.setdefault("사업주_이름", pool.name())
        m.setdefault("근로자_이름", pool.name())
        m.setdefault("사업장_이름", pool.shop())
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
        m.setdefault("주택_유형", pool.house_type())
        m.setdefault("임차할부분", pool.house_part())
    if domain == "LOAN":
        m.setdefault("채권자_이름", pool.name())
        m.setdefault("채무자_이름", pool.name())
        m.setdefault("보증인_이름", pool.name())
        m.setdefault("채권자_전화", pool.phone())
        m.setdefault("채무자_전화", pool.phone())
        m.setdefault("채권자_주소", pool.address())
        m.setdefault("채무자_주소", pool.address())
        m.setdefault("보증인_서명", "(서명)")
        m.setdefault("채권자_서명", "(서명)")
        m.setdefault("채무자_서명", "(서명)")
    return m


def load_docs_from_selection() -> tuple[dict, dict[str, list[dict]]]:
    sel = json.loads(SEL_V1.read_text(encoding="utf-8"))
    by_dom: dict[str, list[dict]] = {}
    for dom in ("LAB", "LEASE", "LOAN"):
        rows = load_jsonl(GOLD[dom]["contract"])
        twin = clean_twin_path(dom)
        if twin.exists():
            rows = rows + load_jsonl(twin)
        want = {it["doc_id"] for it in sel["domains"][dom]}
        segs_by: dict[str, list] = {}
        for r in rows:
            if r.get("doc_id") in want:
                segs_by.setdefault(r["doc_id"], []).append(r)
        items = []
        for it in sel["domains"][dom]:
            did = it["doc_id"]
            segs = sorted(
                segs_by.get(did, []),
                key=lambda s: (s.get("order") if s.get("order") is not None else 0, s.get("segment_id") or ""),
            )
            items.append({"item": it, "segs": segs})
        by_dom[dom] = items
    return sel, by_dom


def lab_form_kind(meta_text: str) -> str:
    t = meta_text or ""
    if "단시간" in t:
        return "단시간근로자"
    if "연소" in t:
        return "연소근로자"
    if "건설" in t:
        return "건설일용"
    if "외국인" in t:
        return "외국인근로자"
    if "기간" in t and "정함" in t and "있는" in t:
        return "표준(기간의 정함 없음)"  # 7종에 '있는' 단독 구간이 없으면 표준 사용
    return "표준(기간의 정함 없음)"


def insert_after_find(h: Hwp, needles: list[str], text: str) -> str | None:
    for n in needles:
        if h.find(n, from_begin=True):
            h.run("MoveLineEnd")
            h.insert_text("\r\n" + text)
            return n
    return None


def build_lab(h: Hwp, doc_id: str, kind: str, segs: list[dict], pool: FakePool) -> dict:
    fake = build_fake_map("LAB", pool, segs)
    meta = next((s for s in segs if is_meta(s)), {})
    form_kind = lab_form_kind((meta.get("text") or ""))
    start, end = LAB_PAGE_RANGES[form_kind]
    tmp = OUT_DIR / f"_tmp_LAB_{doc_id}.hwp"
    shutil.copy2(LAB_FORM, tmp)
    h.open(tmp)
    h.keep_pages(start, end)

    # 당사자 채우기
    emp = fake["사업주_이름"]
    wrk = fake["근로자_이름"]
    h.replace_all("(이하 “사업주”라 함)", f"{emp}(이하 “사업주”라 함)")
    h.replace_all('(이하 "사업주"라 함)', f'{emp}(이하 "사업주"라 함)')
    h.replace_all("(이하 “근로자”라 함)", f"{wrk}(이하 “근로자”라 함)")
    h.replace_all('(이하 "근로자"라 함)', f'{wrk}(이하 "근로자"라 함)')

    placements = []
    golds = [s for s in segs if not is_meta(s)]
    # std별 묶되, 문서에 한 번씩만 삽입
    leftover: list[dict] = []
    for s in golds:
        filled = fill_placeholders(s.get("text") or "", fake)
        std = s.get("std_item") or "LAB-12"
        needles = LAB_STD_FIND.get(std, ["기타"])
        place = insert_after_find(h, needles, filled)
        if not place:
            leftover.append({"seg": s, "text": filled})
            place_name = "기타(미매칭)"
        else:
            place_name = place
        placements.append(
            {
                "segment_id": s.get("segment_id"),
                "label": s.get("label"),
                "std_item": std,
                "place": place_name,
            }
        )
    if leftover:
        # 기타 칸에 순서대로
        if not h.find("기타", from_begin=True):
            h.escape_table()
            h.insert_text("\r\n기타\r\n")
        else:
            h.run("MoveLineEnd")
        for item in leftover:
            h.insert_text("\r\n" + item["text"])
            # update place
            for p in placements:
                if p["segment_id"] == item["seg"].get("segment_id"):
                    p["place"] = "기타"

    out_stem = f"LAB_{kind}_{doc_id}"
    out_hwp = OUT_DIR / f"{out_stem}.hwp"
    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    h.save_as(out_hwp)
    h.save_as(out_pdf, "PDF")
    try:
        tmp.unlink()
    except Exception:
        pass
    return {
        "doc_id": doc_id,
        "domain": "LAB",
        "kind": kind,
        "form": str(LAB_FORM.relative_to(WORK)).replace("\\", "/"),
        "form_kind": form_kind,
        "form_pages_kept": [start, end],
        "hwp": str(out_hwp.relative_to(WORK)).replace("\\", "/"),
        "pdf": str(out_pdf.relative_to(WORK)).replace("\\", "/"),
        "fake_values": fake,
        "segments": placements,
    }


def lease_source(segs: list[dict], meta_text: str) -> Path:
    src_rel = None
    for s in segs:
        if s.get("source_hwpx"):
            src_rel = s.get("source_hwpx")
            break
    if src_rel:
        p = WORK / "datasets" / "property" / src_rel.replace("/", "\\")
        if p.exists():
            return p
        alt = LEASE_FORMS / Path(src_rel).name
        if alt.exists():
            return alt
    pref = "JEONSE" if "전세" in (meta_text or "") else "MONTHLY"
    if "민간" in (meta_text or ""):
        cands = sorted(LEASE_FORMS.glob("PRIVATE_*.hwpx"))
        if cands:
            return cands[0]
    cands = sorted(LEASE_FORMS.glob(f"{pref}_*.hwpx"))
    return cands[0] if cands else sorted(LEASE_FORMS.glob("*.hwpx"))[0]


# 양식 본문 계약별 문장 앞머리 — 비워 정답과 중복 방지(별지·법령 안내는 유지)
LEASE_BODY_SNIPS = [
    "위 부동산의 임대차에 관하여 임대인과 임차인은 합의하에",
    "임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는",
    "임대인과 임차인은 임차주택의 수리가 필요한 시설물",
    "임차인은 임대인의 동의 없이 임차주택의 구조",
    "임차인이 임대인에게 중도금",
    "당사자 일방이 채무를 이행하지 아니하는 때에는",
    "임차인은 본인의 과실 없이 임차주택의 일부가 멸실",
    "임차인은 임대차기간이 끝나기 6개월 전부터",
    "임대인과 임차인은 본 임대차계약과 관련한 분쟁이 발생하는",
    "중개보수는 거래 가액의",
    "개업공인중개사는 중개대상물 확인․설명서를",
    "매년 차임 조정안을 통보",
    "물가상승 등을 고려하여 매년",
]


def build_lease(h: Hwp, doc_id: str, kind: str, segs: list[dict], pool: FakePool) -> dict:
    """양식 복사본 유지(쪽수), 본문 계약별 문장은 비우고 정답 조각만 특약에 한 번씩."""
    fake = build_fake_map("LEASE", pool, segs)
    meta = next((s for s in segs if is_meta(s)), {})
    src = lease_source(segs, meta.get("text") or "")
    tmp = OUT_DIR / f"_tmp_LEASE_{doc_id}.hwpx"
    shutil.copy2(src, tmp)
    h.open(tmp)

    h.replace_all("박서영", fake["임대인_이름"])
    h.replace_all("이서준", fake["임차인_이름"])
    h.replace_all("박영숙", fake["임대인_이름"])

    for sn in LEASE_BODY_SNIPS:
        h.replace_all(sn, "")

    golds = [s for s in segs if not is_meta(s)]
    filled_golds = [(s, fill_placeholders(s.get("text") or "", fake)) for s in golds]

    # 양식에 이미 같은 문장이 있으면 지운 뒤, 아래에서 한 번만 넣는다
    for _, text in filled_golds:
        if len(re.sub(r"\s+", "", text)) >= 20:
            h.replace_all(text, "")

    placements = []
    block = ["\r\n"]
    seen_norm: set[str] = set()
    for s, text in filled_golds:
        std = s.get("std_item") or ""
        place = "특약사항"
        if std == "LEASE-01":
            place = "특약사항(목적물)"
        elif std == "LEASE-02":
            place = "특약사항(보증금·차임)"
        key = re.sub(r"\s+", "", text)
        # 서로 다른 조각이 같은 글자이면 문서에는 한 번만 기입
        if key and key not in seen_norm:
            seen_norm.add(key)
            block.append(text + "\r\n")
        placements.append(
            {
                "segment_id": s.get("segment_id"),
                "label": s.get("label"),
                "std_item": std,
                "place": place,
            }
        )

    # 표/다단에 끼지 않도록 새 쪽에 특약 기입
    h.escape_table()
    for cmd in ("InsertPageBreak", "BreakPage"):
        try:
            h.hwp.Run(cmd)
            break
        except Exception:
            continue
    h.insert_text("특약사항\r\n" + "".join(block))

    h.replace_all("테스트주택_유형", fake["주택_유형"])
    h.replace_all("테스트임차할부분", fake["임차할부분"])

    out_stem = f"LEASE_{kind}_{doc_id}"
    out_hwp = OUT_DIR / f"{out_stem}.hwp"
    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    h.save_as(out_hwp)
    h.save_as(out_pdf, "PDF")
    try:
        tmp.unlink()
    except Exception:
        pass
    form_rel = str(src.relative_to(WORK / "datasets" / "property")).replace("\\", "/")
    return {
        "doc_id": doc_id,
        "domain": "LEASE",
        "kind": kind,
        "form": form_rel,
        "hwp": str(out_hwp.relative_to(WORK)).replace("\\", "/"),
        "pdf": str(out_pdf.relative_to(WORK)).replace("\\", "/"),
        "fake_values": fake,
        "segments": placements,
    }


def build_loan(h: Hwp, doc_id: str, kind: str, segs: list[dict], pool: FakePool) -> dict:
    fake = build_fake_map("LOAN", pool, segs)
    h.clear_new()
    # 제목
    h.insert_text("금전차용계약서\r\n\r\n")
    # 당사자 표
    h.create_table(3, 4)
    cells = [
        "구분",
        "성명",
        "주소",
        "연락처",
        "채권자",
        fake["채권자_이름"],
        fake["채권자_주소"],
        fake["채권자_전화"],
        "채무자",
        fake["채무자_이름"],
        fake["채무자_주소"],
        fake["채무자_전화"],
    ]
    for i, c in enumerate(cells):
        h.insert_text(c)
        if i < len(cells) - 1:
            h.table_right()
    h.escape_table()
    h.insert_text("\r\n\r\n")

    placements = []
    golds = [s for s in segs if not is_meta(s)]
    for s in golds:
        text = fill_placeholders(s.get("text") or "", fake)
        # 조 번호가 이미 있으면 그대로
        h.insert_text(text + "\r\n")
        placements.append(
            {
                "segment_id": s.get("segment_id"),
                "label": s.get("label"),
                "std_item": s.get("std_item"),
                "place": "조항본문",
            }
        )

    # 서명 표
    h.insert_text("\r\n")
    h.create_table(3, 3)
    sig_cells = [
        "당사자",
        "성명",
        "서명",
        "채권자",
        fake["채권자_이름"],
        "(서명)",
        "채무자",
        fake["채무자_이름"],
        "(서명)",
    ]
    for i, c in enumerate(sig_cells):
        h.insert_text(c)
        if i < len(sig_cells) - 1:
            h.table_right()
    h.escape_table()

    # 계약일(meta에서 숫자만 참고 — meta 문장 그대로 넣지 않음)
    meta_sig = next((s for s in segs if is_meta(s) and "계약일" in (s.get("text") or "")), None)
    if meta_sig:
        m = re.search(r"계약일:\s*([0-9\-년월일\s]+)", meta_sig.get("text") or "")
        if m:
            h.insert_text(f"\r\n계약일: {m.group(1).strip()}\r\n")

    out_stem = f"LOAN_{kind}_{doc_id}"
    out_hwp = OUT_DIR / f"{out_stem}.hwp"
    out_pdf = OUT_DIR / f"{out_stem}.pdf"
    h.save_as(out_hwp)
    h.save_as(out_pdf, "PDF")
    return {
        "doc_id": doc_id,
        "domain": "LOAN",
        "kind": kind,
        "form": "(new) 금전차용계약서",
        "hwp": str(out_hwp.relative_to(WORK)).replace("\\", "/"),
        "pdf": str(out_pdf.relative_to(WORK)).replace("\\", "/"),
        "fake_values": fake,
        "segments": placements,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sel, by_dom = load_docs_from_selection()
    (OUT_DIR / "selection.json").write_text(json.dumps(sel, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT_DIR / "selection.json")

    pool = FakePool(SEED)
    h = Hwp()
    manifest = {"seed": SEED, "command": "python eval/build_hwp_test_pdfs_v2.py", "docs": []}
    try:
        for dom in ("LAB", "LEASE", "LOAN"):
            for block in by_dom[dom]:
                it = block["item"]
                did = it["doc_id"]
                kind = it["kind"]
                segs = block["segs"]
                print(f"BUILD {dom} {kind} {did}", flush=True)
                if dom == "LAB":
                    entry = build_lab(h, did, kind, segs, pool)
                elif dom == "LEASE":
                    entry = build_lease(h, did, kind, segs, pool)
                else:
                    entry = build_loan(h, did, kind, segs, pool)
                entry["select_reason"] = it.get("reason")
                if it.get("dev_absent_codes"):
                    entry["dev_absent_codes"] = it["dev_absent_codes"]
                entry["toxic_codes"] = it.get("codes") or []
                manifest["docs"].append(entry)
                print(" ->", entry["pdf"], flush=True)
    finally:
        h.quit()

    man = OUT_DIR / "manifest.json"
    man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", man, "n=", len(manifest["docs"]))


if __name__ == "__main__":
    main()
