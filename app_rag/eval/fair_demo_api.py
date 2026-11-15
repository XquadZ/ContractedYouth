# -*- coding: utf-8 -*-
"""8091 재시작 뒤 데모 PDF 1장을 /api/extract로 올린다. 원문 전문은 저장하지 않는다."""
from __future__ import annotations

import json
import mimetypes
import sys
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rag.extract import extract_bytes  # noqa: E402
from rag.pii import mask_pii  # noqa: E402

DEMO = APP.parent / "datasets" / "demo_pdfs"
OUT = APP / "out" / "quant_fair" / "demo_api_check.json"
BASE = "http://127.0.0.1:8091"


def _opener():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _json(opener, url: str, payload: dict) -> tuple[int, dict, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, {}, raw[:300]


def main() -> None:
    pdfs = sorted(DEMO.glob("*.pdf"))
    path = next(p for p in pdfs if "WORK-0002" in p.name)
    local = extract_bytes(path.read_bytes(), path.name)
    original = "\n".join(p.get("text") or "" for p in local.get("pages") or [])
    local_masked, counts = mask_pii(original)
    opener = _opener()
    code, _user, raw = _json(
        opener,
        BASE + "/api/auth/login",
        {"login_id": "user1", "password": "pwd1"},
    )
    if code != 200:
        raise SystemExit(f"login {code} {raw}")
    boundary = "----demo" + uuid.uuid4().hex
    file_bytes = path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/extract",
        data=head + file_bytes + tail,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with opener.open(req, timeout=120) as resp:
        api = json.loads(resp.read().decode("utf-8"))
    api_text = "\n".join(p.get("text") or "" for p in api.get("pages") or [])
    note = {
        "command": "python -u -X utf8 eval/fair_demo_api.py",
        "pdf": path.name,
        "login_status": code,
        "original_star": original.count("*"),
        "local_mask_star": local_masked.count("*"),
        "api_star": api_text.count("*"),
        "api_equals_local_mask": api_text == local_masked,
        "local_counts": counts,
        "api_masked_counts": api.get("masked_counts"),
        "star_delta_api_minus_original": api_text.count("*") - original.count("*"),
    }
    OUT.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(note, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
