# -*- coding: utf-8 -*-
"""SQLite app.db — users/files/reviews/chat_messages."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rag.paths import APP as _APP_FALLBACK

APP = Path(__file__).resolve().parents[1]
DATA_LOCAL = APP / "data_local"
DB_PATH = DATA_LOCAL / "app.db"

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login_id TEXT NOT NULL UNIQUE,
  pw_hash TEXT NOT NULL,
  birth_date TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  created_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  mime TEXT,
  size INTEGER NOT NULL,
  enc_blob BLOB,
  nonce BLOB,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  deleted_at TEXT,
  deleted_by TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  file_id INTEGER,
  domain TEXT,
  model TEXT,
  masked_text TEXT,
  report_json TEXT,
  score INTEGER,
  grade TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(file_id) REFERENCES files(id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  review_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(review_id) REFERENCES reviews(id)
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    d = dt or utcnow()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def age_years(birth: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def get_conn() -> sqlite3.Connection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            DATA_LOCAL.mkdir(parents=True, exist_ok=True)
            _CONN = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            _CONN.row_factory = sqlite3.Row
            _CONN.executescript(SCHEMA)
            _CONN.commit()
        return _CONN


def init_db() -> None:
    get_conn()
    ensure_admin()


def ensure_admin() -> None:
    """시연용 관리자 user1/pwd1 — 8자 규칙 예외(의도적 약한 비밀번호)."""
    import bcrypt

    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE login_id=?", ("user1",)).fetchone()
    if row:
        return
    # DEMO ADMIN ONLY: pwd1 is intentionally short for demo; do not use in production.
    pw_hash = bcrypt.hashpw(b"pwd1", bcrypt.gensalt()).decode("ascii")
    conn.execute(
        "INSERT INTO users(login_id, pw_hash, birth_date, role, created_at) VALUES (?,?,?,?,?)",
        ("user1", pw_hash, "1990-01-01", "admin", iso()),
    )
    conn.commit()


def create_user(login_id: str, password: str, birth_date: str) -> tuple[dict | None, str | None]:
    import bcrypt
    import re

    if not re.fullmatch(r"[A-Za-z0-9]{4,20}", login_id or ""):
        return None, "아이디는 영문·숫자 4~20자여야 해요."
    if login_id == "user1":
        # admin reserved; normal signup still enforces 8+ except the seeded admin
        pass
    if len(password or "") < 8 and login_id != "user1":
        return None, "비밀번호는 8자 이상이어야 해요."
    try:
        y, m, d = [int(x) for x in birth_date.split("-")]
        bd = date(y, m, d)
    except Exception:
        return None, "생년월일 형식이 올바르지 않아요."
    if age_years(bd) < 19:
        return None, "만 19세 이상만 가입할 수 있어요."
    conn = get_conn()
    if conn.execute("SELECT id FROM users WHERE login_id=?", (login_id,)).fetchone():
        return None, "이미 사용 중인 아이디예요."
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    cur = conn.execute(
        "INSERT INTO users(login_id, pw_hash, birth_date, role, created_at) VALUES (?,?,?,?,?)",
        (login_id, pw_hash, bd.isoformat(), "user", iso()),
    )
    conn.commit()
    return {"id": cur.lastrowid, "login_id": login_id, "role": "user"}, None


def verify_user(login_id: str, password: str) -> dict | None:
    import bcrypt

    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE login_id=? AND deleted_at IS NULL", (login_id,)
    ).fetchone()
    if not row:
        return None
    if not bcrypt.checkpw(password.encode("utf-8"), row["pw_hash"].encode("ascii")):
        return None
    return {"id": row["id"], "login_id": row["login_id"], "role": row["role"]}


def get_user(user_id: int) -> dict | None:
    row = get_conn().execute(
        "SELECT id, login_id, role, birth_date, created_at FROM users WHERE id=? AND deleted_at IS NULL",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, login_id, role, birth_date, created_at FROM users WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def file_ttl_minutes() -> int:
    try:
        return max(1, int(os.environ.get("FILE_TTL_MINUTES", "1440")))
    except Exception:
        return 1440


def insert_file(*, user_id: int, filename: str, mime: str | None, size: int, enc_blob: bytes, nonce: bytes) -> int:
    now = utcnow()
    exp = now + timedelta(minutes=file_ttl_minutes())
    cur = get_conn().execute(
        "INSERT INTO files(user_id, filename, mime, size, enc_blob, nonce, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, filename, mime, size, enc_blob, nonce, iso(now), iso(exp)),
    )
    get_conn().commit()
    return int(cur.lastrowid)


def get_file(file_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    return dict(row) if row else None


def list_files_for_user(user_id: int) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, user_id, filename, mime, size, created_at, expires_at, deleted_at, deleted_by "
        "FROM files WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def purge_file_blob(file_id: int, *, deleted_by: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT id, deleted_at FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE files SET enc_blob=NULL, nonce=NULL, deleted_at=?, deleted_by=? WHERE id=?",
        (iso(), deleted_by, file_id),
    )
    conn.commit()
    return True


def purge_expired_files() -> int:
    conn = get_conn()
    now = iso()
    rows = conn.execute(
        "SELECT id FROM files WHERE deleted_at IS NULL AND expires_at <= ?", (now,)
    ).fetchall()
    n = 0
    for r in rows:
        purge_file_blob(int(r["id"]), deleted_by="auto")
        n += 1
    return n


def insert_review(
    *,
    user_id: int,
    file_id: int | None,
    domain: str | None,
    model: str | None,
    masked_text: str,
    report_json: str,
    score: int | None,
    grade: str | None,
) -> int:
    cur = get_conn().execute(
        "INSERT INTO reviews(user_id, file_id, domain, model, masked_text, report_json, score, grade, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, file_id, domain, model, masked_text, report_json, score, grade, iso()),
    )
    get_conn().commit()
    return int(cur.lastrowid)


def get_review(review_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    return dict(row) if row else None


def list_reviews(user_id: int) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, user_id, file_id, domain, model, score, grade, created_at FROM reviews "
        "WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_chat(*, user_id: int, review_id: int, role: str, content: str) -> int:
    cur = get_conn().execute(
        "INSERT INTO chat_messages(user_id, review_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_id, review_id, role, content, iso()),
    )
    get_conn().commit()
    return int(cur.lastrowid)


def list_chats(review_id: int) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, user_id, review_id, role, content, created_at FROM chat_messages "
        "WHERE review_id=? ORDER BY id",
        (review_id,),
    ).fetchall()
    return [dict(r) for r in rows]
