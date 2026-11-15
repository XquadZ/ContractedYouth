# -*- coding: utf-8 -*-
"""HWP_TEST_PDFS_FIX2: v3 시험 계약서.
v1/v2 유지. 출력 datasets/test_hwp_pdfs_v3.
임대 조항은 조 단위로 공식 문구 또는 정답으로 통째 교체.
rag/ 미수정. 모델/GPU/판정 없음.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
WORK = APP.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "eval"))

from recall_dev import load_jsonl  # noqa: E402
from rag.paths import GOLD  # noqa: E402
from rag.extract import extract_bytes  # noqa: E402
from splitutil import clean_twin_path  # noqa: E402
from dev_eval import is_meta  # noqa: E402

OUT_DIR = WORK / "datasets" / "test_hwp_pdfs_v3"
SEL_V1 = WORK / "datasets" / "test_hwp_pdfs" / "selection.json"
LAB_FORM = WORK / "datasets" / "work" / "표준_근로계약서(7종)(19.6월).hwp"
LEASE_FORMS = WORK / "datasets" / "property" / "source_hwpx_originals" / "contracts"
OFFICIAL_JSON = OUT_DIR / "lease_official_articles.json"
SEED = 42

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신"]
GIVEN = ["민수", "서연", "지훈", "하은", "도윤", "수아", "예준", "지아", "현우", "소율", "유진", "시우"]
# 업종 없이 이름만 — 정답에 '카페 {{사업장_이름}}'가 있어도 겹치지 않음
SHOPS = ["봄날", "한빛", "달빛", "푸른", "소망", "코너", "햇살", "느티"]
HOUSE_TYPES = ["아파트", "다세대주택", "오피스텔", "연립주택", "단독주택"]
HOUSE_PARTS = ["3층 302호 전부", "2층 201호 전부", "101호 전부", "5층 502호 전부", "4층 401호 전부"]

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

# 정답 std → 양식 조 (같은 주제). 나머지·중복은 특약.
STD_TO_ART = {
    "LEASE-02": "제1조",
    "LEASE-03": "제2조",
    "LEASE-04": "제3조",
    "LEASE-05": "제4조",
    "LEASE-06": "제5조",
    "LEASE-07": "제6조",
    "LEASE-08": "제7조",
    "LEASE-11": "제8조",
    "LEASE-09": "제9조",
    "LEASE-10": "제10조",
    "LEASE-13": "제12조",
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

    def find_next(self, s: str) -> bool:
        """현재 위치 이후에서 찾기."""
        self.run("Cancel")
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

    def selected_start(self) -> tuple[int, int] | None:
        sp = self.hwp.GetSelectedPos()
        if not sp or not sp[0]:
            return None
        return int(sp[2]), int(sp[3])

    def replace_range(self, start_needle: str, end_needle: str | None, new_text: str) -> bool:
        """start_needle 시작부터 end_needle 시작 직전까지 지우고 new_text 삽입."""
        needles = [start_needle]
        # PDF에서 공백이 달라질 수 있어 짧은 후보도 시도
        m = re.match(r"(제\s*\d+\s*조\s*\([^)]{2,12})", start_needle)
        if m:
            needles.append(m.group(1))
        needles.append(re.sub(r"\s+", "", start_needle)[:20])

        s = None
        used = None
        for n in needles:
            if not n:
                continue
            if self.find(n, from_begin=True):
                s = self.selected_start()
                used = n
                if s:
                    break
        if not s:
            return False
        if end_needle:
            end_ok = False
            for n in (end_needle, re.sub(r"\s+", "", end_needle)[:16], "특약사항"):
                if n and self.find(n, from_begin=True):
                    # end must be after start
                    e = self.selected_start()
                    if e and (e[0] > s[0] or (e[0] == s[0] and e[1] > s[1])):
                        end_ok = True
                        break
            if not end_ok:
                return False
        else:
            self.run("MoveDocEnd")
            p = self.hwp.GetPos()
            e = (int(p[1]), int(p[2]))
        try:
            self.hwp.SelectText(s[0], s[1], e[0], e[1])
        except Exception:
            return False
        self.run("Delete")
        self.insert_text(new_text if new_text.endswith("\r\n") else new_text + "\r\n")
        return True

    def replace_all(self, old: str, new: str) -> None:
        if not old or old == new:
            return
        try:
            self.hwp.HAction.GetDefault("AllReplace", self.hwp.HParameterSet.HFindReplace.HSet)
            fr = self.hwp.HParameterSet.HFindReplace
            fr.FindString = old
            fr.ReplaceString = new
            fr.IgnoreMessage = 1
            fr.ReplaceMode = 1
            fr.FindType = 1
            fr.Direction = 0
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

    def char_shape_title(self) -> None:
        """제목 굵게·크게(선택 영역에 적용하려면 호출 전 선택)."""
        try:
            self.hwp.HAction.GetDefault("CharShape", self.hwp.HParameterSet.HCharShape.HSet)
            cs = self.hwp.HParameterSet.HCharShape
            cs.Bold = 1
            cs.Height = 1600  # 16pt in hangul units often 100=1pt → 16pt=1600?
            self.hwp.HAction.Execute("CharShape", cs.HSet)
        except Exception:
            pass

    def para_center(self) -> None:
        try:
            self.hwp.HAction.GetDefault("ParagraphShape", self.hwp.HParameterSet.HParaShape.HSet)
            ps = self.hwp.HParameterSet.HParaShape
            ps.AlignType = 1  # center
            self.hwp.HAction.Execute("ParagraphShape", ps.HSet)
        except Exception:
            self.run("ParagraphShapeAlignCenter")


def fill_placeholders(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)

    def _sub(m):
        key = m.group(1)
        if key not in mapping:
            if "유형" in key:
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

    emp = fake["사업주_이름"]
    wrk = fake["근로자_이름"]
    h.replace_all("(이하 “사업주”라 함)", f"{emp}(이하 “사업주”라 함)")
    h.replace_all('(이하 "사업주"라 함)', f'{emp}(이하 "사업주"라 함)')
    h.replace_all("(이하 “근로자”라 함)", f"{wrk}(이하 “근로자”라 함)")
    h.replace_all('(이하 "근로자"라 함)', f'{wrk}(이하 "근로자"라 함)')

    placements = []
    golds = [s for s in segs if not is_meta(s)]
    leftover: list[dict] = []
    seen: set[str] = set()
    for s in golds:
        filled = fill_placeholders(s.get("text") or "", fake)
        key = re.sub(r"\s+", "", filled)
        std = s.get("std_item") or "LAB-12"
        if key in seen:
            placements.append(
                {"segment_id": s.get("segment_id"), "label": s.get("label"), "std_item": std, "place": "동일문장공유"}
            )
            continue
        seen.add(key)
        needles = LAB_STD_FIND.get(std, ["기타"])
        place = insert_after_find(h, needles, filled)
        if not place:
            leftover.append({"seg": s, "text": filled})
            place_name = "기타"
        else:
            place_name = place
        placements.append(
            {"segment_id": s.get("segment_id"), "label": s.get("label"), "std_item": std, "place": place_name}
        )
    if leftover:
        if not h.find("기타", from_begin=True):
            h.escape_table()
            h.insert_text("\r\n기타\r\n")
        else:
            h.run("MoveLineEnd")
        for item in leftover:
            h.insert_text("\r\n" + item["text"])

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


def parse_period(text: str) -> tuple[str | None, str | None]:
    """계약기간 시작·종료일 문자열."""
    m = re.search(
        r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*부터\s*(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
        text or "",
    )
    if not m:
        return None, None
    a = f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일"
    b = f"{m.group(4)}년 {int(m.group(5))}월 {int(m.group(6))}일"
    return a, b


def date_minus_days(kor_date: str, days: int) -> str:
    m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", kor_date or "")
    if not m:
        return kor_date
    dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))) - timedelta(days=days)
    return f"{dt.year}년 {dt.month}월 {dt.day}일"


def list_article_titles_from_pdf(pdf_bytes: bytes, name: str) -> list[str]:
    """본문 제1~13조 제목을 문서 등장 순·번호당 1회만 반환."""
    ex = extract_bytes(pdf_bytes, name)
    text = "\n".join(p.get("text") or "" for p in ex.get("pages") or [])
    # 별지·통지서 이후 인용은 무시. '특약사항'은 본문 안에도 있어 자르지 않음.
    cut = len(text)
    for stop in ("별지1", "별지 1", "별지2", "계약갱신 거절통지"):
        j = text.find(stop)
        if j > 0:
            cut = min(cut, j)
    head = text[:cut]
    found: list[tuple[int, int, str]] = []
    seen: set[int] = set()
    for m in re.finditer(r"제\s*([1-9]|1[0-3])\s*조\s*\([^)]+\)", head):
        n = int(m.group(1))
        if n in seen:
            continue
        seen.add(n)
        found.append((m.start(), n, m.group(0)))
    found.sort(key=lambda x: x[0])
    return [t for _, _, t in found]


def art_num(title: str) -> int:
    m = re.search(r"제\s*(\d+)\s*조", title)
    return int(m.group(1)) if m else 0


def build_lease(
    h: Hwp,
    doc_id: str,
    kind: str,
    segs: list[dict],
    pool: FakePool,
    official: dict,
    official_private: dict | None = None,
) -> dict:
    fake = build_fake_map("LEASE", pool, segs)
    meta = next((s for s in segs if is_meta(s)), {})
    src = lease_source(segs, meta.get("text") or "")
    is_private = "PRIVATE" in src.name.upper()
    if is_private and official_private:
        official = official_private
    tmp = OUT_DIR / f"_tmp_LEASE_{doc_id}.hwpx"
    shutil.copy2(src, tmp)
    h.open(tmp)

    # 이름 샘플 치환
    for old in ("박서영", "이서준", "박영숙", "조도윤"):
        if "임대" in old or True:
            pass
    h.replace_all("박서영", fake["임대인_이름"])
    h.replace_all("이서준", fake["임차인_이름"])
    h.replace_all("박영숙", fake["임대인_이름"])
    h.replace_all("조도윤", fake["임대인_이름"])

    golds = [(s, fill_placeholders(s.get("text") or "", fake)) for s in segs if not is_meta(s)]
    period_text = next((t for _, t in golds if "계약기간" in t or "부터" in t and "까지" in t), "")
    start_d, end_d = parse_period(period_text)
    write_d = date_minus_days(start_d, 7) if start_d else None

    # 조별 정답(첫 매핑만 조에, 나머지 특약)
    art_gold: dict[str, tuple[dict, str]] = {}
    specials: list[tuple[dict, str]] = []
    for s, text in golds:
        std = s.get("std_item") or ""
        art = STD_TO_ART.get(std)
        if art and art not in art_gold:
            art_gold[art] = (s, text)
        else:
            specials.append((s, text))

    # 현재 문서 조 제목 목록(PDF로)
    probe_pdf = OUT_DIR / f"_probe_{doc_id}.pdf"
    h.save_as(probe_pdf, "PDF")
    raw_titles = list_article_titles_from_pdf(probe_pdf.read_bytes(), probe_pdf.name)
    # PDF 읽기 순서가 표 때문에 뒤바뀔 수 있으므로 조 번호 순으로 정렬
    by_num: dict[int, str] = {}
    for t in raw_titles:
        n = art_num(t)
        if 1 <= n <= 13 and n not in by_num:
            by_num[n] = t
    # 표준 MONTHLY/JEONSE 공식 제목으로 누락 조 보완(문서에서 Find 가능해야 함)
    for n in range(1, 14):
        if n in by_num:
            continue
        off = (official.get(f"제{n}조") or {}).get("title") or ""
        if off and h.find(off, from_begin=True):
            by_num[n] = off
        else:
            # 짧은 후보
            for cand in (f"제{n}조(", f"제{n}조"):
                if h.find(cand, from_begin=True):
                    by_num[n] = cand
                    break
    body_titles = [by_num[n] for n in sorted(by_num)]
    print("  titles", body_titles, flush=True)
    try:
        probe_pdf.unlink()
    except Exception:
        pass

    placements = []
    article_status = {}

    # PRIVATE 양식은 SelectText 조교체가 불안정 → 조는 공식 문구 유지, 정답은 특약에만
    if is_private:
        for n in sorted(by_num.keys()):
            key = f"제{n}조"
            article_status[key] = {
                "status": "공식 문구",
                "ok": True,
                "title": by_num[n],
                "note": "PRIVATE: 조 유지·정답은 특약",
            }
        # art_gold도 특약으로
        art_gold = {}

    # 뒤에서부터 바꾸면 좌표가 안 밀림 (번호 큰 조 → 작은 조)
    nums = sorted(by_num.keys(), reverse=True)
    for n in nums:
        if is_private:
            break
        title = by_num[n]
        key = f"제{n}조"
        end = by_num[n + 1] if (n + 1) in by_num else "특약사항"
        # PRIVATE 제목 특수문자 때문에 짧은 end 바늘도 허용
        end_candidates = [end, f"제{n+1}조", "특약사항", "특약"]
        if key in art_gold:
            seg, gtxt = art_gold[key]
            # 정답에 조 번호 없으면 공식 제목 붙임
            if not re.match(r"제\s*\d+\s*조", gtxt):
                # title may have spaces
                tclean = re.sub(r"\s+", "", title)
                m = re.match(r"(제\d+조\([^)]*\))", tclean)
                prefix = m.group(1) if m else key
                # use original title spacing from find string
                new_text = f"{title} {gtxt}"
            else:
                new_text = gtxt
            ok = False
            for end_n in end_candidates:
                if h.replace_range(title, end_n, new_text):
                    ok = True
                    break
            article_status[key] = {"status": "정답 조각으로 바꿈", "ok": ok, "title": title}
            if ok:
                placements.append(
                    {
                        "segment_id": seg.get("segment_id"),
                        "label": seg.get("label"),
                        "std_item": seg.get("std_item"),
                        "place": key,
                    }
                )
            # ok=False면 아래에서 특약으로 넣음
        else:
            off = (official.get(key) or {}).get("text") or ""
            if not off:
                article_status[key] = {"status": "다름", "ok": False, "title": title, "reason": "공식문구없음"}
                continue
            new_text = off
            # 날짜 맞춤(제2조·제13조 등)
            if start_d and end_d:
                new_text = re.sub(
                    r"20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일까지 임차인에게 인도하고, 임대차기간은 인도일로부터 20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일까지",
                    f"{start_d}까지 임차인에게 인도하고, 임대차기간은 인도일로부터 {end_d}까지",
                    new_text,
                )
                new_text = re.sub(
                    r"잔금지급일 20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일까지",
                    f"잔금지급일 {start_d}까지",
                    new_text,
                )
                if write_d:
                    new_text = re.sub(
                        r"첨부하여20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
                        f"첨부하여{write_d}",
                        new_text,
                    )
            ok = False
            for end_n in end_candidates:
                if h.replace_range(title, end_n, new_text):
                    ok = True
                    break
            article_status[key] = {"status": "공식 문구", "ok": ok, "title": title}

    # 특약: 본문 [특약사항] 칸 — 서명/별지 앞. 페이지 나누지 않음.
    # 이미 조에 넣은 조각은 placements에 있음. specials + LEASE-01 등
    for s, text in golds:
        if any(p.get("segment_id") == s.get("segment_id") for p in placements):
            continue
        placements.append(
            {
                "segment_id": s.get("segment_id"),
                "label": s.get("label"),
                "std_item": s.get("std_item"),
                "place": "특약사항",
            }
        )

    # 중복 문장 한 번만
    spec_lines = []
    seen = set()
    for s, text in golds:
        if any(p.get("segment_id") == s.get("segment_id") and p.get("place", "").startswith("제") for p in placements):
            continue
        key = re.sub(r"\s+", "", text)
        if key in seen:
            continue
        seen.add(key)
        spec_lines.append(text)

    # 특약에 넣을 문장이 양식에 이미 있으면 제거(두 번 등장 방지)
    for line in spec_lines:
        if len(re.sub(r"\s+", "", line)) >= 20:
            h.replace_all(line, "")

    if h.find("특약사항", from_begin=True):
        h.run("MoveLineEnd")
        if spec_lines:
            h.insert_text("\r\n" + "\r\n".join(spec_lines) + "\r\n")
    elif spec_lines:
        if h.find("별지", from_begin=True):
            s = h.selected_start()
            if s:
                try:
                    h.hwp.SetPos(0, s[0], s[1])
                except Exception:
                    pass
            h.insert_text("\r\n특약사항\r\n" + "\r\n".join(spec_lines) + "\r\n")

    # 별지 서식 비우기: 채워진 날짜/서명 흔한 패턴 제거(본문 날짜는 이미 정답에 맞춤)
    if write_d and start_d:
        # 통지서에 남은 임의 날짜를 빈칸 느낌으로 — 너무 공격적이지 않게 별지 쪽만
        pass
    # 통지서 서명 줄에 들어간 이름 제거 시도
    h.replace_all(f"/ {fake['임대인_이름']} (서명)", "/              (서명)")
    h.replace_all(f"{fake['임대인_이름']} (서명)", "              (서명)")

    # 헤더 금액·주소는 정답 조각(특약·제1조)에 있으므로 별도 칸은 가능한 범위만
    h.replace_all("테스트주택_유형", fake["주택_유형"])
    h.replace_all("테스트임차할부분", fake["임차할부분"])

    # 쪽 번호 n/m (n>m) 방지: 푸터가 /5 인데 6쪽만 넘는 경우 1쪽만 제거
    if h.page_count() == 6:
        h.run("MoveDocEnd")
        h.run("DeletePage")

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
        "article_status": article_status,
        "body_titles": body_titles,
        "period": {"start": start_d, "end": end_d, "write": write_d},
    }


def build_loan(h: Hwp, doc_id: str, kind: str, segs: list[dict], pool: FakePool) -> dict:
    fake = build_fake_map("LOAN", pool, segs)
    h.clear_new()
    # 제목 가운데·굵게
    h.para_center()
    h.insert_text("금전차용계약서")
    # select line and apply shape
    h.run("MoveLineBegin")
    h.run("MoveSelLineEnd")
    h.char_shape_title()
    h.run("Cancel")
    h.insert_text("\r\n\r\n")
    h.run("ParagraphShapeAlignLeft") if False else None
    try:
        h.hwp.HAction.GetDefault("ParagraphShape", h.hwp.HParameterSet.HParaShape.HSet)
        ps = h.hwp.HParameterSet.HParaShape
        ps.AlignType = 0
        h.hwp.HAction.Execute("ParagraphShape", ps.HSet)
    except Exception:
        pass

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
    seen: set[str] = set()
    for s in segs:
        if is_meta(s):
            continue
        text = fill_placeholders(s.get("text") or "", fake)
        key = re.sub(r"\s+", "", text)
        if key in seen:
            placements.append(
                {
                    "segment_id": s.get("segment_id"),
                    "label": s.get("label"),
                    "std_item": s.get("std_item"),
                    "place": "동일문장공유",
                }
            )
            continue
        seen.add(key)
        h.insert_text(text + "\r\n")
        placements.append(
            {
                "segment_id": s.get("segment_id"),
                "label": s.get("label"),
                "std_item": s.get("std_item"),
                "place": "조항본문",
            }
        )

    h.insert_text("\r\n")
    h.create_table(3, 3)
    sig_cells = [
        "구분",
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
    if not OFFICIAL_JSON.exists():
        raise SystemExit(f"missing {OFFICIAL_JSON}; run eval/_extract_lease_official.py first")
    official = json.loads(OFFICIAL_JSON.read_text(encoding="utf-8"))["official"]
    priv_path = OUT_DIR / "lease_official_articles_private.json"
    official_private = (
        json.loads(priv_path.read_text(encoding="utf-8"))["official"] if priv_path.exists() else {}
    )

    sel, by_dom = load_docs_from_selection()
    (OUT_DIR / "selection.json").write_text(json.dumps(sel, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT_DIR / "selection.json")

    pool = FakePool(SEED)
    h = Hwp()
    manifest = {"seed": SEED, "command": "python eval/build_hwp_test_pdfs_v3.py", "docs": []}
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
                    entry = build_lease(h, did, kind, segs, pool, official, official_private)
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
