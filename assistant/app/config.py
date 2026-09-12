"""Cau hinh doc tu bien moi truong (hoac file .env)."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv la tuy chon, tren host thi dung env that
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


class Settings:
    """Gom toan bo tham so chinh o mot cho."""

    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.app_password = os.getenv("APP_PASSWORD", "").strip()

        self.model = os.getenv("MODEL", "claude-opus-5").strip()
        self.effort = os.getenv("EFFORT", "high").strip()
        self.max_tokens = _int("MAX_TOKENS", 32000)
        self.max_tool_rounds = _int("MAX_TOOL_ROUNDS", 25)
        self.max_history = _int("MAX_HISTORY", 40)

        self.enable_python = _bool("ENABLE_PYTHON", True)
        self.enable_files = _bool("ENABLE_FILES", True)
        self.enable_http = _bool("ENABLE_HTTP", True)
        self.enable_web = _bool("ENABLE_WEB", True)
        self.enable_shell = _bool("ENABLE_SHELL", False)

        self.exec_timeout = _int("EXEC_TIMEOUT", 30)
        self.exec_memory_mb = _int("EXEC_MEMORY_MB", 512)

        # Moi phien chat co thu muc rieng ben trong workspace goc.
        self.workspace = Path(os.getenv("WORKSPACE", "./workspace")).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Fallback phia server: neu Opus 5 tu choi vi ly do an toan, API tu
        # chay lai request tren model du phong trong cung mot lan goi.
        self.refusal_fallback = _bool("REFUSAL_FALLBACK", True)

    @property
    def auth_required(self) -> bool:
        return bool(self.app_password)

    def session_dir(self, session_id: str) -> Path:
        """Thu muc lam viec rieng cua mot phien, khong cho thoat ra ngoai."""
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
        path = self.workspace / (safe or "default")
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
