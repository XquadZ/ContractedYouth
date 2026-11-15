# -*- coding: utf-8 -*-
"""메모리 기반 간단 남용 제한. 프로세스 재시작 시 초기화."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_SIGNUP_IP: dict[str, deque[float]] = defaultdict(deque)
_ANALYZE_USER: dict[int, deque[float]] = defaultdict(deque)

SIGNUP_MAX_PER_HOUR = 5
ANALYZE_MAX_PER_DAY = 20


def _prune(q: deque[float], window_sec: float, now: float) -> None:
    while q and (now - q[0]) > window_sec:
        q.popleft()


def check_signup_ip(ip: str) -> str | None:
    """초과 시 안내 문구, 아니면 None. 통과 시 호출 측에서 record_signup_ip."""
    now = time.time()
    key = (ip or "unknown").strip() or "unknown"
    with _LOCK:
        q = _SIGNUP_IP[key]
        _prune(q, 3600.0, now)
        if len(q) >= SIGNUP_MAX_PER_HOUR:
            return "같은 곳에서 가입 시도가 너무 많아요. 잠시 후 다시 시도해 주세요."
    return None


def record_signup_ip(ip: str) -> None:
    now = time.time()
    key = (ip or "unknown").strip() or "unknown"
    with _LOCK:
        q = _SIGNUP_IP[key]
        _prune(q, 3600.0, now)
        q.append(now)


def check_analyze_user(user_id: int) -> str | None:
    now = time.time()
    uid = int(user_id)
    with _LOCK:
        q = _ANALYZE_USER[uid]
        _prune(q, 86400.0, now)
        if len(q) >= ANALYZE_MAX_PER_DAY:
            return "오늘 분석 횟수를 다 썼어요"
    return None


def record_analyze_user(user_id: int) -> None:
    now = time.time()
    uid = int(user_id)
    with _LOCK:
        q = _ANALYZE_USER[uid]
        _prune(q, 86400.0, now)
        q.append(now)
