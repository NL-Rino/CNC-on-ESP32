"""Web server: mot trang chat + endpoint SSE day event cua agent xuong trinh duyet."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import Agent
from .config import settings

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
SESSION_TTL = 6 * 60 * 60  # phien im lang qua 6 tieng thi don di

app = FastAPI(title="Tro ly AI", docs_url=None, redoc_url=None)

_agent: Agent | None = None
_sessions: dict[str, dict[str, Any]] = {}
_tokens: set[str] = set()
_locks: dict[str, asyncio.Lock] = {}


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def _prune() -> None:
    now = time.time()
    for sid in [s for s, d in _sessions.items() if now - d["seen"] > SESSION_TTL]:
        _sessions.pop(sid, None)
        _locks.pop(sid, None)


def require_auth(request: Request) -> None:
    """Khong dat APP_PASSWORD thi mo cua tu do - hop ly khi chay o localhost."""
    if not settings.auth_required:
        return
    header = request.headers.get("authorization", "")
    token = header[7:] if header.startswith("Bearer ") else request.cookies.get("token", "")
    if token not in _tokens:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")


@app.post("/api/login")
async def login(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.auth_required:
        return {"token": "", "required": False}
    # so sanh hang so de khong lo mat khau qua thoi gian phan hoi
    if not secrets.compare_digest(str(payload.get("password", "")), settings.app_password):
        raise HTTPException(status_code=401, detail="Sai mật khẩu")
    token = secrets.token_urlsafe(32)
    _tokens.add(token)
    return {"token": token, "required": True}


@app.get("/api/config")
async def config() -> dict[str, Any]:
    agent = get_agent()
    return {
        "auth_required": settings.auth_required,
        "model": settings.model,
        "effort": settings.effort,
        "tools": agent.tool_catalog(),
    }


@app.post("/api/reset", dependencies=[Depends(require_auth)])
async def reset(payload: dict[str, Any]) -> dict[str, str]:
    sid = str(payload.get("session_id", ""))
    _sessions.pop(sid, None)
    _locks.pop(sid, None)
    return {"status": "ok"}


@app.get("/api/files", dependencies=[Depends(require_auth)])
async def list_files(session_id: str) -> dict[str, Any]:
    """Liet ke file agent da tao, de nguoi dung tai ve."""
    base = settings.session_dir(session_id)
    files = [
        {"name": str(p.relative_to(base)), "size": p.stat().st_size}
        for p in sorted(base.rglob("*"))
        if p.is_file() and p.name not in {"_run.py", "_memory.json"}
    ]
    return {"files": files}


@app.get("/api/file", dependencies=[Depends(require_auth)])
async def get_file(session_id: str, name: str) -> FileResponse:
    base = settings.session_dir(session_id).resolve()
    target = (base / name).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Không có file này")
    return FileResponse(target, filename=target.name)


@app.post("/api/chat", dependencies=[Depends(require_auth)])
async def chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="Tin nhắn rỗng")

    session_id = str(payload.get("session_id") or uuid.uuid4().hex)
    _prune()
    session = _sessions.setdefault(session_id, {"messages": [], "seen": time.time()})
    session["seen"] = time.time()
    lock = _locks.setdefault(session_id, asyncio.Lock())

    agent = get_agent()

    async def stream() -> Any:
        if lock.locked():
            yield _sse({"type": "error", "message": "Phiên này đang xử lý một câu hỏi khác."})
            return

        async with lock:
            history: list[Any] = session["messages"]
            history.append({"role": "user", "content": message})
            # Cat bot lich su cu de khong phinh context vo han.
            if len(history) > settings.max_history:
                del history[: len(history) - settings.max_history]
                # Lich su phai bat dau bang luot cua nguoi dung.
                while history and history[0].get("role") != "user":
                    history.pop(0)

            yield _sse({"type": "start", "session_id": session_id})
            try:
                async for event in agent.run(history, session_id):
                    yield _sse(event)
            except Exception as exc:  # noqa: BLE001 - loi bat ngo van phai bao ra UI
                yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # tat buffering cua nginx tren mot so host
        },
    )


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
