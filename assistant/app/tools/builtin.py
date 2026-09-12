"""Cac tool ma agent duoc phep goi."""
from __future__ import annotations

import json
import shlex
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..config import settings
from . import sandbox
from .registry import Registry, Tool, ToolContext

MAX_READ = 200_000
MEMORY_FILE = "_memory.json"


def _resolve(ctx: ToolContext, rel: str) -> Path:
    """Ep moi duong dan nam trong thu muc phien. Chan ../.. va symlink tro ra ngoai."""
    root = ctx.session_dir.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Đường dẫn '{rel}' nằm ngoài workspace - không được phép.")
    return target


# --------------------------------------------------------------------------- files
def _list_files(payload: dict[str, Any], ctx: ToolContext) -> str:
    base = _resolve(ctx, payload.get("path", "."))
    if not base.exists():
        return f"Không có '{payload.get('path', '.')}'."
    if base.is_file():
        return f"{base.name} ({base.stat().st_size} bytes)"

    rows: list[str] = []
    for item in sorted(base.rglob("*"))[:500]:
        if item.name.startswith("_run.py"):
            continue
        rel = item.relative_to(ctx.session_dir)
        rows.append(f"{rel}/" if item.is_dir() else f"{rel}  ({item.stat().st_size} bytes)")
    return "\n".join(rows) or "(thư mục rỗng)"


def _read_file(payload: dict[str, Any], ctx: ToolContext) -> str:
    target = _resolve(ctx, payload["path"])
    if not target.is_file():
        return f"Không có file '{payload['path']}'."
    data = target.read_text(encoding="utf-8", errors="replace")
    if len(data) > MAX_READ:
        return data[:MAX_READ] + f"\n\n... [còn {len(data) - MAX_READ} ký tự nữa]"
    return data or "(file rỗng)"


def _write_file(payload: dict[str, Any], ctx: ToolContext) -> str:
    target = _resolve(ctx, payload["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    content = payload.get("content", "")
    target.write_text(content, encoding="utf-8")
    return f"Đã ghi {len(content)} ký tự vào '{payload['path']}'."


# --------------------------------------------------------------------------- exec
def _run_python(payload: dict[str, Any], ctx: ToolContext) -> str:
    return sandbox.run_python(payload["code"], ctx.session_dir)


def _run_shell(payload: dict[str, Any], ctx: ToolContext) -> str:
    command = payload["command"]
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"Lệnh không hợp lệ: {exc}"
    if not argv:
        return "Lệnh rỗng."
    return sandbox.run_command(argv, ctx.session_dir)


# --------------------------------------------------------------------------- http
def _http_request(payload: dict[str, Any], ctx: ToolContext) -> str:
    url = payload["url"]
    if not url.startswith(("http://", "https://")):
        return "URL phải bắt đầu bằng http:// hoặc https://."

    method = payload.get("method", "GET").upper()
    body = payload.get("body")
    headers = payload.get("headers") or {}
    headers.setdefault("User-Agent", "tro-ly-ai/1.0")

    req = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=body.encode("utf-8") if body else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310 - da chan scheme o tren
            raw = resp.read(MAX_READ).decode("utf-8", errors="replace")
            return f"HTTP {resp.status}\n\n{raw}"
    except urllib.error.HTTPError as exc:
        detail = exc.read(5000).decode("utf-8", errors="replace")
        return f"HTTP {exc.code}\n\n{detail}"
    except urllib.error.URLError as exc:
        return f"Không kết nối được: {exc.reason}"


# --------------------------------------------------------------------------- memory
def _memory_path(ctx: ToolContext) -> Path:
    return ctx.session_dir / MEMORY_FILE


def _load_memory(ctx: ToolContext) -> dict[str, str]:
    path = _memory_path(ctx)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _remember(payload: dict[str, Any], ctx: ToolContext) -> str:
    store = _load_memory(ctx)
    key, value = payload["key"], payload.get("value", "")
    if value:
        store[key] = value
        action = f"Đã nhớ: {key}"
    else:
        store.pop(key, None)
        action = f"Đã xoá ghi nhớ: {key}"
    _memory_path(ctx).write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return action


def _recall(payload: dict[str, Any], ctx: ToolContext) -> str:
    store = _load_memory(ctx)
    key = payload.get("key")
    if key:
        return store.get(key, f"(không có ghi nhớ nào tên '{key}')")
    if not store:
        return "(chưa nhớ gì cả)"
    return "\n".join(f"- {k}: {v}" for k, v in store.items())


# --------------------------------------------------------------------------- build
def build_registry() -> Registry:
    reg = Registry()

    if settings.enable_files:
        reg.add(Tool(
            name="list_files", label="Liệt kê file", icon="folder",
            description=(
                "Liet ke file/thu muc trong workspace rieng cua phien chat. "
                "Dung de xem minh da tao ra nhung gi."
            ),
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Duong dan tuong doi, mac dinh '.'"}},
            },
            handler=_list_files,
        ))
        reg.add(Tool(
            name="read_file", label="Đọc file", icon="file",
            description="Doc noi dung mot file text trong workspace.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Duong dan tuong doi toi file."}},
                "required": ["path"],
            },
            handler=_read_file,
        ))
        reg.add(Tool(
            name="write_file", label="Ghi file", icon="save",
            description=(
                "Tao moi hoac ghi de mot file text trong workspace. "
                "Dung de luu ket qua, script, bao cao cho nguoi dung tai ve."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Duong dan tuong doi toi file."},
                    "content": {"type": "string", "description": "Toan bo noi dung file."},
                },
                "required": ["path", "content"],
            },
            handler=_write_file,
        ))

    if settings.enable_python:
        reg.add(Tool(
            name="run_python", label="Chạy Python", icon="python",
            description=(
                "Chay mot doan Python trong workspace va tra ve stdout/stderr. "
                "Dung cho tinh toan, xu ly du lieu, doc/ghi file, tao bieu do. "
                f"Gioi han {settings.exec_timeout}s va {settings.exec_memory_mb}MB RAM. "
                "Moi lan chay la mot tien trinh moi nen bien khong duoc giu lai - "
                "muon luu trang thai thi ghi ra file. In ket qua bang print()."
            ),
            input_schema={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Ma Python can chay."}},
                "required": ["code"],
            },
            handler=_run_python,
        ))

    if settings.enable_shell:
        reg.add(Tool(
            name="run_shell", label="Chạy lệnh", icon="terminal",
            description=(
                "Chay mot lenh shell trong workspace (khong qua shell interpreter, "
                "khong ho tro pipe hay dau &&). Chi dung khi that su can."
            ),
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Lenh can chay, vi du: ls -la"}},
                "required": ["command"],
            },
            handler=_run_shell,
        ))

    if settings.enable_http:
        reg.add(Tool(
            name="http_request", label="Gọi API", icon="globe",
            description=(
                "Goi mot HTTP request toi API bat ky va tra ve noi dung phan hoi. "
                "Dung cho API cong khai (thoi tiet, gia coin, REST API...). "
                "De doc bai bao/trang web thi dung web_fetch se sach hon."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL day du."},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "headers": {"type": "object", "description": "Header dang key-value."},
                    "body": {"type": "string", "description": "Body dang chuoi, thuong la JSON."},
                },
                "required": ["url"],
            },
            handler=_http_request,
        ))

    reg.add(Tool(
        name="remember", label="Ghi nhớ", icon="brain",
        description=(
            "Luu mot thong tin ve nguoi dung de nho sang cac luot sau "
            "(ten, so thich, du an dang lam...). De 'value' rong de xoa."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Ten muc ghi nho, vi du 'ten'."},
                "value": {"type": "string", "description": "Noi dung can nho. Rong = xoa."},
            },
            "required": ["key"],
        },
        handler=_remember,
    ))
    reg.add(Tool(
        name="recall", label="Nhớ lại", icon="brain",
        description="Doc lai nhung gi da ghi nho. Bo trong 'key' de xem tat ca.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string", "description": "Ten muc can xem, bo trong = xem het."}},
        },
        handler=_recall,
    ))

    return reg
