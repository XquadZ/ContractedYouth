# -*- coding: utf-8 -*-
"""WEEK_FINAL-G: API E2E (가입·권한·마스킹·TTL·모델)."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

os.environ.setdefault("ANALYZE_MODEL", "exaone")
os.environ["FILE_TTL_MINUTES"] = "2"

from rag import db as dbmod

dbmod.DB_PATH = APP / "data_local" / "e2e_app.db"
if dbmod.DB_PATH.exists():
    dbmod.DB_PATH.unlink()
dbmod._CONN = None

from fastapi.testclient import TestClient
from rag.db import get_review, purge_expired_files, get_file
from rag.pii import mask_pii
from server import app

OUT = APP / "out" / "week_final_e2e"
OUT.mkdir(parents=True, exist_ok=True)


def cookie(resp):
    raw = resp.headers.get("set-cookie") or ""
    return {"Cookie": raw.split(";", 1)[0]}


def main():
    results = {"pass": [], "fail": [], "unconfirmed": [], "timings": {}}
    demo_dir = APP.parent / "datasets" / "demo_pdfs"
    # TXT 데모 생성 (PDF 6개 부재 → 동일 문서 JSON에서 생성)
    demo_json = demo_dir / "_demo_docs.json"
    docs = json.loads(demo_json.read_text(encoding="utf-8")) if demo_json.exists() else {}
    txt_dir = OUT / "demo_txt"
    txt_dir.mkdir(exist_ok=True)
    for did, meta in docs.items():
        lines = [s[2] for s in meta.get("segs") or []]
        # 마스킹 검증용 PII 삽입
        text = "\n".join(lines).replace("{{근로자_이름}}", "김영수").replace("{{사업주_이름}}", "박민")
        text = text.replace("{{임차인_이름}}", "이서연").replace("{{임대인_이름}}", "최하늘")
        text = text + "\n연락처 010-9876-5432\n"
        (txt_dir / f"{did}.txt").write_text(text, encoding="utf-8")

    with TestClient(app) as c:
        # 1) 만 18 거절 / 만 19 성공
        today = date.today()
        under = date(today.year - 18, today.month, today.day)
        r = c.post(
            "/api/auth/signup",
            json={"login_id": "kid18", "password": "password1", "birth_date": under.isoformat()},
        )
        if r.status_code == 400 and "19" in r.json().get("error", ""):
            results["pass"].append("만18 가입 거절")
        else:
            results["fail"].append(f"만18 가입: {r.status_code} {r.text}")

        adult = date(today.year - 19, today.month, today.day)
        # 생일 미도래 보정: 하루 전으로
        if (today.month, today.day) < (adult.month, adult.day):
            adult = date(today.year - 20, 1, 1)
        else:
            adult = date(today.year - 19, 1, 1)
        r = c.post(
            "/api/auth/signup",
            json={"login_id": "adult19", "password": "password1", "birth_date": adult.isoformat()},
        )
        if r.status_code == 200:
            results["pass"].append("만19+ 가입 성공")
        else:
            results["fail"].append(f"만19 가입: {r.text}")

        # 2) 로그인 → 업로드 → 분석(no_llm 빠르게) → 기록 → 로그아웃 → 재로그인
        login = c.post("/api/auth/login", json={"login_id": "adult19", "password": "password1"})
        h = cookie(login)
        sample = next(txt_dir.glob("WORK-*.txt"), None) or next(txt_dir.glob("*.txt"))
        raw = sample.read_bytes()
        ex = c.post("/api/extract", files={"file": (sample.name, raw, "text/plain")}, headers=h)
        assert ex.status_code == 200, ex.text
        file_id = ex.json()["file_id"]
        masked_pages = "\n".join(p["text"] for p in ex.json()["pages"])
        if "010-9876-5432" in masked_pages or "김영수" in masked_pages:
            # 이름/전화가 그대로면 실패 (김** / ***-****-5432 기대)
            if "김영수" in masked_pages and "김*" not in masked_pages:
                results["fail"].append("추출 응답에 이름 원문")
            if "010-9876-5432" in masked_pages:
                results["fail"].append("추출 응답에 전화 원문")
        else:
            results["pass"].append("추출 응답 마스킹")

        t0 = time.perf_counter()
        # no_llm로 파이프라인·저장 확인 (모델별 시간은 별도)
        an = c.post(
            "/api/analyze",
            headers=h,
            json={"text": masked_pages, "no_llm": True, "domain": "LAB", "file_id": file_id},
        )
        assert an.status_code == 200
        # SSE 소비
        body = an.content.decode("utf-8", "replace")
        review_id = None
        score = None
        for block in body.split("\n\n"):
            if "event: saved" in block or block.startswith("event: saved"):
                for line in block.split("\n"):
                    if line.startswith("data:"):
                        js = json.loads(line[5:])
                        review_id = js.get("review_id")
                        score = js.get("score")
        results["timings"]["analyze_no_llm_sec"] = round(time.perf_counter() - t0, 2)
        if review_id:
            results["pass"].append(f"분석 저장 review_id={review_id} score={score}")
        else:
            results["fail"].append("saved 이벤트 없음")

        # 채팅 저장
        ch = c.post("/api/chat", headers=h, json={"review_id": review_id, "message": "위험이 뭐야?"})
        if ch.status_code == 200:
            results["pass"].append("채팅 저장")
        else:
            results["fail"].append(f"채팅: {ch.text}")

        c.post("/api/auth/logout", headers=h)
        login2 = c.post("/api/auth/login", json={"login_id": "adult19", "password": "password1"})
        h2 = cookie(login2)
        det = c.get(f"/api/reviews/{review_id}", headers=h2)
        if det.status_code == 200 and det.json().get("chats"):
            results["pass"].append("재로그인 후 기록·채팅 유지")
        else:
            results["fail"].append(f"재로그인 기록: {det.status_code}")

        # 3) 다른 사용자 403
        c.post(
            "/api/auth/signup",
            json={"login_id": "other99", "password": "password1", "birth_date": adult.isoformat()},
        )
        ologin = c.post("/api/auth/login", json={"login_id": "other99", "password": "password1"})
        oh = cookie(ologin)
        fr = c.get(f"/api/reviews/{review_id}", headers=oh)
        if fr.status_code == 403:
            results["pass"].append("타인 기록 403")
        else:
            results["fail"].append(f"타인 접근 {fr.status_code}")

        # 4) 관리자 삭제 + TTL
        admin = c.post("/api/auth/login", json={"login_id": "user1", "password": "pwd1"})
        ah = cookie(admin)
        d = c.post(f"/api/admin/files/{file_id}/delete", headers=ah)
        if d.status_code == 200 and get_file(file_id)["deleted_by"] == "admin":
            results["pass"].append("관리자 원본 삭제")
        else:
            results["fail"].append("관리자 삭제 실패")
        # TTL: 새 파일 만료 강제
        login3 = c.post("/api/auth/login", json={"login_id": "adult19", "password": "password1"})
        h3 = cookie(login3)
        ex2 = c.post("/api/extract", files={"file": ("t.txt", b"hello", "text/plain")}, headers=h3)
        fid2 = ex2.json()["file_id"]
        conn = dbmod.get_conn()
        conn.execute("UPDATE files SET expires_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", fid2))
        conn.commit()
        purge_expired_files()
        if get_file(fid2)["deleted_by"] == "auto":
            results["pass"].append("TTL 자동 삭제")
        else:
            results["fail"].append("TTL 실패")
        # 리포트는 남음
        det2 = c.get(f"/api/reviews/{review_id}", headers=h3)
        if det2.status_code == 200 and det2.json().get("report") is not None:
            results["pass"].append("원본 삭제 후에도 리포트 열림")
        else:
            results["fail"].append("리포트 소실")

        # 5) DB masked_text에 원문 전화/이름 없는지
        rev = get_review(review_id)
        mt = rev["masked_text"] or ""
        if "010-9876-5432" in mt or "김영수" in mt:
            results["fail"].append("DB masked_text에 원문 PII")
        else:
            results["pass"].append("DB masked_text 마스킹 확인")

        # 모델 전환 API
        for m in ("ax", "exaone", "gpt"):
            sm = c.post("/api/settings/model", headers=h3, json={"analyze_model": m})
            if sm.status_code != 200:
                results["fail"].append(f"model {m}")
            else:
                results["pass"].append(f"ANALYZE_MODEL={m} 설정")

        # GPT 요청 원문 검사: mask_pii 단위
        sample_txt = sample.read_text(encoding="utf-8")
        masked, counts = mask_pii(sample_txt)
        if "010-9876-5432" in masked:
            results["fail"].append("mask_pii 전화 잔존")
        else:
            results["pass"].append(f"mask_pii ok counts={counts}")

        results["unconfirmed"].append("브라우저 스크린샷(PDF 6개 실파일 없음 → TXT API E2E로 대체)")
        results["unconfirmed"].append("모델별(ax/exaone/gpt) 실LLM 1장 분석 시간: no_llm만 측정, 실측은 시연 시")

    (OUT / "e2e_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
