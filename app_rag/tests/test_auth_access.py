# -*- coding: utf-8 -*-
"""회원가입·나이·소유권 403 테스트."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

os.environ["FILE_TTL_MINUTES"] = "2"

from rag import db as dbmod

dbmod.DB_PATH = APP / "data_local" / "test_app.db"
if dbmod.DB_PATH.exists():
    dbmod.DB_PATH.unlink()
dbmod._CONN = None

from fastapi.testclient import TestClient
from server import app  # noqa: E402


def _cookie_header(resp) -> dict:
    raw = resp.headers.get("set-cookie") or ""
    # cy_session=...; HttpOnly; ...
    part = raw.split(";", 1)[0]
    if not part.startswith("cy_session="):
        return {}
    return {"Cookie": part}


def test_under19_rejected():
    with TestClient(app) as client:
        today = date.today()
        birth = date(today.year - 18, today.month, today.day)
        r = client.post(
            "/api/auth/signup",
            json={"login_id": "teen01", "password": "password1", "birth_date": birth.isoformat()},
        )
        assert r.status_code == 400
        assert "19" in r.json()["error"]


def test_signup_login_ok():
    with TestClient(app) as client:
        today = date.today()
        birth = date(today.year - 20, 1, 1)
        r = client.post(
            "/api/auth/signup",
            json={"login_id": "adult01", "password": "password1", "birth_date": birth.isoformat()},
        )
        assert r.status_code == 200, r.text
        r2 = client.post("/api/auth/login", json={"login_id": "adult01", "password": "password1"})
        assert r2.status_code == 200
        me = client.get("/api/auth/me", headers=_cookie_header(r2))
        assert me.json()["user"]["login_id"] == "adult01"


def test_foreign_review_403():
    with TestClient(app) as c1, TestClient(app) as c2:
        today = date.today()
        birth = date(today.year - 25, 5, 5).isoformat()
        assert (
            c1.post(
                "/api/auth/signup",
                json={"login_id": "owner01", "password": "password1", "birth_date": birth},
            ).status_code
            == 200
        )
        assert (
            c2.post(
                "/api/auth/signup",
                json={"login_id": "other01", "password": "password1", "birth_date": birth},
            ).status_code
            == 200
        )
        from rag.db import insert_review

        s1 = c1.post("/api/auth/login", json={"login_id": "owner01", "password": "password1"})
        owner_id = s1.json()["user"]["id"]
        rid = insert_review(
            user_id=owner_id,
            file_id=None,
            domain="LAB",
            model="ax",
            masked_text="masked",
            report_json="{}",
            score=100,
            grade="안전",
        )
        s2 = c2.post("/api/auth/login", json={"login_id": "other01", "password": "password1"})
        r = c2.get(f"/api/reviews/{rid}", headers=_cookie_header(s2))
        assert r.status_code == 403, r.text


def _admin_login_json() -> dict:
    """관리자 로그인 정보. 비밀번호는 환경변수/설정에서 읽고 출력하지 않는다."""
    from rag.db import _admin_password_plain, ensure_admin

    ensure_admin()
    login_id = (os.environ.get("ADMIN_LOGIN_ID") or "user1").strip()
    return {"login_id": login_id, "password": _admin_password_plain()}


def test_admin_seeded():
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json=_admin_login_json())
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"


def test_analyze_requires_login():
    with TestClient(app) as c:
        r = c.post("/api/analyze", json={"text": "테스트", "no_llm": True})
        assert r.status_code == 401


if __name__ == "__main__":
    test_under19_rejected()
    print("PASS under19")
    test_signup_login_ok()
    print("PASS signup")
    test_foreign_review_403()
    print("PASS 403")
    test_admin_seeded()
    print("PASS admin")
    test_analyze_requires_login()
    print("PASS authgate")
    print("RESULT 5/5")
