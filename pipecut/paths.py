"""Hai loại thư mục của phần mềm: chỗ để tài nguyên đi kèm, và chỗ người dùng ghi.

Chạy từ mã nguồn thì tài nguyên (``config/``, ``examples/``, ``firmware/``,
``docs/``) nằm ở gốc kho mã.  Chạy từ bản đóng gói ``.exe`` thì chúng nằm cạnh
tệp ``.exe`` - thường là ``C:\\Program Files\\PipeCut Studio``, nơi **không ghi
được**.  Nên mọi thứ người dùng lưu (hồ sơ máy, công việc, G-code) phải mặc định
vào thư mục của người dùng, không phải thư mục đang đứng.
"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """Đang chạy từ bản đóng gói (PyInstaller) chứ không phải từ mã nguồn."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> str:
    """Thư mục chứa ``config/``, ``examples/``, ``firmware/``, ``docs/`` đi kèm."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource(*parts: str) -> str:
    return os.path.join(resource_dir(), *parts)


def user_dir(create: bool = False) -> str:
    """``~/.pipecut`` - chỗ phần mềm tự đọc lại hồ sơ máy mỗi lần mở."""
    path = os.path.join(os.path.expanduser("~"), ".pipecut")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def user_profile_path() -> str:
    """Hồ sơ máy của người dùng.  Lưu vào đây thì lần sau mở là có sẵn."""
    return os.path.join(user_dir(), "machine.json")


def documents_dir(create: bool = False) -> str:
    """Chỗ mặc định để lưu công việc và G-code: ``Documents/PipeCut``."""
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    path = os.path.join(docs, "PipeCut") if os.path.isdir(docs) else user_dir()
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def writable(path: str) -> bool:
    """Thư mục này có ghi được không (Program Files thì thường là không)."""
    return os.path.isdir(path) and os.access(path, os.W_OK)
