# -*- coding: utf-8 -*-
"""암호화 저장·TTL·관리자 삭제 테스트."""
from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

os.environ["FILE_TTL_MINUTES"] = "1"

from rag import db as dbmod

dbmod.DB_PATH = APP / "data_local" / "test_ttl.db"
if dbmod.DB_PATH.exists():
    dbmod.DB_PATH.unlink()
dbmod._CONN = None

from fastapi.testclient import TestClient
from rag.crypto_store import decrypt_bytes, encrypt_bytes
from rag.db import get_file, insert_review, purge_expired_files
from server import app


def _cookie(resp):
    raw = resp.headers.get("set-cookie") or ""
    return {"Cookie": raw.split(";", 1)[0]}


def test_encrypt_roundtrip():
    n, ct = encrypt_bytes(b"hello-contract")
    assert decrypt_bytes(n, ct) == b"hello-contract"
    print("PASS encrypt")


def test_ttl_and_admin_delete_keeps_review():
    with TestClient(app) as c:
        birth = date(date.today().year - 30, 1, 1).isoformat()
        c.post("/api/auth/signup", json={"login_id": "ttluser", "password": "password1", "birth_date": birth})
        login = c.post("/api/auth/login", json={"login_id": "ttluser", "password": "password1"})
        h = _cookie(login)
        uid = login.json()["user"]["id"]
        # upload tiny txt
        files = {"file": ("pii.txt", b"\xef\xbb\xbf\xec\x84\xb1\xeb\xaa\x85 \xea\xb9\x80\xec\x98\x81\xec\x88\x98 010-1234-5678", "text/plain")}
        ex = c.post("/api/extract", files=files, headers=h)
        assert ex.status_code == 200, ex.text
        fid = ex.json()["file_id"]
        f0 = get_file(fid)
        assert f0["enc_blob"] is not None
        rid = insert_review(
            user_id=uid,
            file_id=fid,
            domain="LAB",
            model="ax",
            masked_text="masked",
            report_json='{"score":80,"grade":"안전"}',
            score=80,
            grade="안전",
        )
        # force expire
        conn = dbmod.get_conn()
        conn.execute("UPDATE files SET expires_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", fid))
        conn.commit()
        n = purge_expired_files()
        assert n >= 1
        f1 = get_file(fid)
        assert f1["enc_blob"] is None
        assert f1["deleted_by"] == "auto"
        rev = c.get(f"/api/reviews/{rid}", headers=h)
        assert rev.status_code == 200
        assert rev.json()["original_deleted"] is True
        # admin delete another file
        admin = c.post("/api/auth/login", json={"login_id": "user1", "password": "pwd1"})
        ah = _cookie(admin)
        files2 = {"file": ("a.txt", b"abc", "text/plain")}
        # need user upload then admin delete — re-login as user
        login2 = c.post("/api/auth/login", json={"login_id": "ttluser", "password": "password1"})
        h2 = _cookie(login2)
        ex2 = c.post("/api/extract", files=files2, headers=h2)
        fid2 = ex2.json()["file_id"]
        admin = c.post("/api/auth/login", json={"login_id": "user1", "password": "pwd1"})
        ah = _cookie(admin)
        d = c.post(f"/api/admin/files/{fid2}/delete", headers=ah)
        assert d.status_code == 200
        f2 = get_file(fid2)
        assert f2["deleted_by"] == "admin"
        print("PASS ttl+admin")


if __name__ == "__main__":
    test_encrypt_roundtrip()
    test_ttl_and_admin_delete_keeps_review()
    print("RESULT ok")
