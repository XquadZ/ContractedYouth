# -*- coding: utf-8 -*-
"""PyJWT httpOnly 쿠키 인증."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request, Response

COOKIE_NAME = "cy_session"
JWT_HOURS = 12


def _secret() -> str:
    # 서버 전용. 없으면 임시 생성(재시작 시 세션 무효).
    s = os.environ.get("JWT_SECRET") or ""
    if s:
        return s
    # 파일 기반 고정(로컬 시연)
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "data_local" / "jwt.secret"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(os.urandom(32).hex(), encoding="ascii")
    return p.read_text(encoding="ascii").strip()


def make_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "login_id": user["login_id"],
        "role": user.get("role") or "user",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_HOURS)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_HOURS * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_token(token)
        return {
            "id": int(payload["sub"]),
            "login_id": payload.get("login_id"),
            "role": payload.get("role") or "user",
        }
    except Exception:
        return None


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요해요.")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있어요.")
    return user


def assert_owner(user: dict, owner_id: int | None) -> None:
    if owner_id is None or int(user["id"]) != int(owner_id):
        raise HTTPException(status_code=403, detail="권한이 없어요.")
