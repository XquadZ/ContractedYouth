# -*- coding: utf-8 -*-
"""계약서 RAG 리포트 UI. 127.0.0.1만 연다. 원본은 AES 암호화 DB 저장."""
from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag.auth import (
    assert_owner,
    clear_session_cookie,
    current_user,
    make_token,
    require_admin,
    require_user,
    set_session_cookie,
)
from rag.corpus import convert_law_nodes, load_corpus, propose_tags, write_records, write_tag_proposal
from rag.crypto_store import decrypt_bytes, encrypt_bytes
from rag.db import (
    create_user,
    get_file,
    get_review,
    init_db,
    insert_chat,
    insert_file,
    insert_review,
    list_chats,
    list_files_for_user,
    list_reviews,
    list_users,
    purge_expired_files,
    purge_file_blob,
    verify_user,
    file_ttl_minutes,
    parse_iso,
    utcnow,
)
from rag.domain import score_domain
from rag.extract import ExtractError, extract_bytes, locate_quotes_pdf
from rag.generate import ax_up
from rag.llm_router import chat_answer, is_switching
from rag.paths import SAMPLES, STD_ITEM_RULES
from rag.pii import mask_pii
from rag.pipeline import get_index, run
from rag.settings import get_analyze_model, model_label
from rag.split import split_contract

STATIC = APP / "static"
NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
app = FastAPI(title="계약서 RAG 리포트")
_PUBLIC = {
    "/api/health",
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
}


@app.middleware("http")
async def disable_cache(request, call_next):
    response = await call_next(request)
    response.headers.update(NO_CACHE)
    return response


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class AnalyzeIn(BaseModel):
    text: str
    no_llm: bool = False
    domain: str | None = None
    file_id: int | None = None


class DomainIn(BaseModel):
    text: str


class SignupIn(BaseModel):
    login_id: str
    password: str
    birth_date: str


class LoginIn(BaseModel):
    login_id: str
    password: str


class ChatIn(BaseModel):
    review_id: int
    message: str


class ModelIn(BaseModel):
    analyze_model: str


def _ensure_corpus() -> None:
    records, _skipped = load_corpus()
    if records:
        return
    converted, _skip = convert_law_nodes()
    write_records(converted)
    write_tag_proposal(propose_tags(converted, STD_ITEM_RULES))


def _ttl_loop() -> None:
    while True:
        try:
            purge_expired_files()
        except Exception:
            pass
        threading.Event().wait(60)


@app.on_event("startup")
def startup() -> None:
    init_db()
    purge_expired_files()
    _ensure_corpus()
    t = threading.Thread(target=_ttl_loop, daemon=True)
    t.start()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers=NO_CACHE)


@app.get("/login")
def login_page():
    return FileResponse(STATIC / "login.html", headers=NO_CACHE)


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html", headers=NO_CACHE)


@app.get("/api/health")
def health():
    records, skipped = load_corpus()
    embed_ok = False
    embed_error = None
    try:
        index, _ = get_index()
        embed_ok = index.embed.ok
        embed_error = index.embed.error
    except Exception as exc:
        embed_error = str(exc)[:200]
    return {
        "ax": ax_up(),
        "n_records": len(records),
        "n_skipped": len(skipped),
        "embed_ok": embed_ok,
        "embed_error": embed_error,
        "model": model_label(),
        "analyze_model": get_analyze_model(),
        "model_switching": is_switching(),
        "port": 8082,
        "sec_per_clause": 2.64,
        "file_ttl_minutes": file_ttl_minutes(),
    }


@app.post("/api/auth/signup")
def signup(body: SignupIn, response: Response):
    user, err = create_user(body.login_id, body.password, body.birth_date)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    token = make_token(user)
    set_session_cookie(response, token)
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    user = verify_user(body.login_id, body.password)
    if not user:
        return JSONResponse({"error": "아이디 또는 비밀번호가 올바르지 않아요."}, status_code=401)
    token = make_token(user)
    set_session_cookie(response, token)
    return {"ok": True, "user": user}


@app.post("/api/auth/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        return {"user": None}
    return {"user": user}


@app.post("/api/auth/password-help")
def password_help():
    return {"message": "관리자에게 문의하세요"}


@app.get("/api/reviews")
def reviews_list(request: Request):
    user = require_user(request)
    return {"reviews": list_reviews(user["id"])}


@app.get("/api/reviews/{review_id}")
def reviews_get(review_id: int, request: Request):
    user = require_user(request)
    row = get_review(review_id)
    if not row:
        return JSONResponse({"error": "없음"}, status_code=404)
    assert_owner(user, row["user_id"])
    file_meta = get_file(row["file_id"]) if row.get("file_id") else None
    original_deleted = bool(file_meta and file_meta.get("deleted_at"))
    report = json.loads(row["report_json"] or "{}")
    chats = list_chats(review_id)
    ttl_left = None
    if file_meta and not file_meta.get("deleted_at"):
        try:
            exp = parse_iso(file_meta["expires_at"])
            ttl_left = max(0, int((exp - utcnow()).total_seconds()))
        except Exception:
            ttl_left = None
    return {
        "review": {
            "id": row["id"],
            "domain": row["domain"],
            "model": row["model"],
            "score": row["score"],
            "grade": row["grade"],
            "created_at": row["created_at"],
            "masked_text": row["masked_text"],
            "file_id": row["file_id"],
        },
        "report": report,
        "chats": chats,
        "original_deleted": original_deleted,
        "original_message": "원본은 보안 정책에 따라 삭제됐어요" if original_deleted else None,
        "ttl_seconds_left": ttl_left,
        "ttl_notice": f"업로드 원본은 {file_ttl_minutes()}분 뒤 자동 삭제돼요",
    }


@app.post("/api/chat")
def chat_api(body: ChatIn, request: Request):
    user = require_user(request)
    row = get_review(body.review_id)
    if not row:
        return JSONResponse({"error": "없음"}, status_code=404)
    assert_owner(user, row["user_id"])
    msg_m, _ = mask_pii(body.message or "")
    insert_chat(user_id=user["id"], review_id=body.review_id, role="user", content=msg_m)
    report = json.loads(row["report_json"] or "{}")
    answer = chat_answer(question=msg_m, report=report)
    insert_chat(user_id=user["id"], review_id=body.review_id, role="assistant", content=answer)
    return {"answer": answer}


@app.get("/api/admin/users")
def admin_users(request: Request):
    require_admin(request)
    return {"users": list_users()}


@app.get("/api/admin/users/{user_id}/files")
def admin_user_files(user_id: int, request: Request):
    require_admin(request)
    # 관리자는 파일명·상태만 (내용 없음)
    files = list_files_for_user(user_id)
    out = []
    for f in files:
        out.append(
            {
                "id": f["id"],
                "filename": f["filename"],
                "size": f["size"],
                "created_at": f["created_at"],
                "expires_at": f["expires_at"],
                "deleted_at": f["deleted_at"],
                "deleted_by": f["deleted_by"],
                "status": "deleted" if f.get("deleted_at") else "active",
            }
        )
    return {"files": out}


@app.post("/api/admin/files/{file_id}/delete")
def admin_delete_file(file_id: int, request: Request):
    require_admin(request)
    ok = purge_file_blob(file_id, deleted_by="admin")
    if not ok:
        return JSONResponse({"error": "없음"}, status_code=404)
    return {"ok": True}


@app.post("/api/settings/model")
def set_model(body: ModelIn, request: Request):
    require_user(request)
    m = (body.analyze_model or "").strip().lower()
    if m not in ("ax", "exaone", "gpt"):
        return JSONResponse({"error": "ax|exaone|gpt 만 가능"}, status_code=400)
    import os

    os.environ["ANALYZE_MODEL"] = m
    return {"ok": True, "analyze_model": m, "label": model_label(m), "switching": is_switching()}


@app.get("/api/samples")
def samples(request: Request):
    require_user(request)
    titles = {
        "alba_cafe": "카페 알바 계약서",
        "clean_alba": "표준에 가까운 알바 계약서",
        "demo": "짧은 근로계약 예시",
        "oneroom_lease": "원룸 월세 계약서",
    }
    items = []
    for path in sorted(SAMPLES.glob("*.txt")):
        items.append({"id": path.stem, "title": titles.get(path.stem, path.stem)})
    return {"samples": items}


@app.get("/api/samples/{name}")
def sample_text(name: str, request: Request):
    require_user(request)
    path = (SAMPLES / f"{name}.txt").resolve()
    if path.parent != SAMPLES.resolve() or not path.exists():
        return {"text": ""}
    return {"text": path.read_text(encoding="utf-8")}


@app.post("/api/extract")
async def extract_api(request: Request, file: UploadFile = File(...)):
    user = require_user(request)
    data = await file.read()
    try:
        result = extract_bytes(data, file.filename or "upload.bin")
    except ExtractError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    # 원본 암호화 저장
    nonce, ct = encrypt_bytes(data)
    file_id = insert_file(
        user_id=user["id"],
        filename=file.filename or "upload.bin",
        mime=file.content_type,
        size=len(data),
        enc_blob=ct,
        nonce=nonce,
    )
    pages = result.get("pages") or []
    joined = "\n".join(p.get("text") or "" for p in pages)
    masked, counts = mask_pii(joined)
    # 응답 텍스트는 마스킹본
    for p in pages:
        p["text"], _ = mask_pii(p.get("text") or "")
    domain = score_domain(masked)
    result["domain_guess"] = domain
    result["file_id"] = file_id
    result["masked_counts"] = counts
    result["ttl_minutes"] = file_ttl_minutes()
    result["ttl_notice"] = f"업로드 원본은 {file_ttl_minutes()}분 뒤 자동 삭제돼요"
    return result


@app.post("/api/domain")
def domain_api(body: DomainIn, request: Request):
    require_user(request)
    return score_domain(body.text or "")


@app.post("/api/locate")
async def locate_api(request: Request, file: UploadFile = File(...), quotes: str = Form("[]")):
    require_user(request)
    data = await file.read()
    try:
        qlist = json.loads(quotes or "[]")
        if not isinstance(qlist, list):
            qlist = []
        qlist = [str(x) for x in qlist][:80]
        result = locate_quotes_pdf(data, qlist)
    except ExtractError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=400)
    return result


@app.post("/api/pdf_pages")
async def pdf_pages_api(request: Request, file: UploadFile = File(...), max_pages: int = Form(8)):
    require_user(request)
    import base64
    import fitz

    data = await file.read()
    if not data or data[:5] != b"%PDF-":
        return JSONResponse({"error": "PDF가 아닙니다."}, status_code=400)
    if len(data) > 10 * 1024 * 1024:
        return JSONResponse({"error": "파일은 10MB 이하여야 합니다."}, status_code=400)
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    try:
        n = min(doc.page_count, max(1, min(int(max_pages or 8), 12)))
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            jpg = pix.tobytes("jpeg")
            pages.append(
                {
                    "page": i + 1,
                    "width": pix.width,
                    "height": pix.height,
                    "data_url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii"),
                }
            )
    finally:
        doc.close()
    return {"n": len(pages), "pages": pages}


@app.get("/api/files/{file_id}/status")
def file_status(file_id: int, request: Request):
    user = require_user(request)
    f = get_file(file_id)
    if not f:
        return JSONResponse({"error": "없음"}, status_code=404)
    assert_owner(user, f["user_id"])
    deleted = bool(f.get("deleted_at"))
    ttl_left = None
    if not deleted:
        try:
            ttl_left = max(0, int((parse_iso(f["expires_at"]) - utcnow()).total_seconds()))
        except Exception:
            ttl_left = None
    return {
        "id": f["id"],
        "filename": f["filename"],
        "deleted": deleted,
        "deleted_by": f.get("deleted_by"),
        "message": "원본은 보안 정책에 따라 삭제됐어요" if deleted else None,
        "ttl_seconds_left": ttl_left,
        "ttl_notice": f"업로드 원본은 {file_ttl_minutes()}분 뒤 자동 삭제돼요",
    }


@app.post("/api/split")
def split_api(body: AnalyzeIn, request: Request):
    require_user(request)
    segs = split_contract(body.text or "")
    return {"n": len(segs), "segments": segs}


@app.post("/api/analyze")
def analyze(body: AnalyzeIn, request: Request):
    user = require_user(request)
    text = body.text or ""
    domain = body.domain if body.domain in ("LAB", "LEASE", "LOAN") else None
    mode = get_analyze_model()

    def events():
        q: queue.Queue = queue.Queue()
        report_holder: dict = {}

        def on_event(kind: str, data: dict) -> None:
            if kind == "done":
                report_holder["report"] = data.get("report")
            q.put((kind, data))

        def worker() -> None:
            try:
                run(text, no_llm=body.no_llm, domain=domain, on_event=on_event)
            except Exception as exc:
                q.put(("error", {"message": str(exc)[:400]}))
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()
        yield _sse(
            "meta",
            {
                "model": model_label(mode),
                "analyze_model": mode,
                "no_llm": body.no_llm,
                "domain": domain,
                "demo_notice": "시연 모드: 개인정보를 가린 뒤 외부 AI(OpenAI)로 분석해요"
                if mode == "gpt"
                else None,
            },
        )
        while True:
            item = q.get()
            if item is None:
                break
            kind, data = item
            yield _sse(kind, data)

        # 검토 기록 저장 (마스킹 텍스트만)
        rep = report_holder.get("report") or {}
        masked = rep.get("masked_text") or mask_pii(text)[0]
        rid = insert_review(
            user_id=user["id"],
            file_id=body.file_id,
            domain=rep.get("domain") or domain,
            model=mode,
            masked_text=masked,
            report_json=json.dumps(rep, ensure_ascii=False),
            score=rep.get("score"),
            grade=rep.get("grade"),
        )
        yield _sse("saved", {"review_id": rid, "score": rep.get("score"), "grade": rep.get("grade")})

    return StreamingResponse(events(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8091, reload=False)
