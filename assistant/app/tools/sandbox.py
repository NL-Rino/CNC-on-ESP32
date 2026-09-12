"""Chay code/lenh trong tien trinh con co gioi han."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from ..config import settings

MAX_OUTPUT = 20_000  # cat bot output khong lo truoc khi day vao context


def _limits() -> object | None:
    """Gioi han CPU + RAM cho tien trinh con (chi co tren Unix)."""
    try:
        import resource
    except ImportError:  # Windows
        return None

    cpu = max(1, settings.exec_timeout)
    mem = settings.exec_memory_mb * 1024 * 1024

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        if mem > 0:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))

    return apply


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    half = MAX_OUTPUT // 2
    cut = len(text) - MAX_OUTPUT
    return f"{text[:half]}\n\n... [cắt bớt {cut} ký tự ở giữa] ...\n\n{text[-half:]}"


def _format(proc: subprocess.CompletedProcess[str]) -> str:
    parts: list[str] = []
    if proc.stdout.strip():
        parts.append(f"[stdout]\n{proc.stdout.rstrip()}")
    if proc.stderr.strip():
        parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
    if proc.returncode != 0:
        parts.append(f"[exit code] {proc.returncode}")
    if not parts:
        return "(chạy xong, không có output)"
    return _clip("\n\n".join(parts))


def run_command(argv: list[str], cwd: Path, stdin: str | None = None) -> str:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # khong de code sinh ra doc duoc key
    env.pop("APP_PASSWORD", None)
    env["HOME"] = str(cwd)
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=settings.exec_timeout,
            preexec_fn=_limits(),  # noqa: PLW1509 - co y: ap rlimit trong child
        )
    except subprocess.TimeoutExpired:
        return f"[timeout] Quá {settings.exec_timeout}s nên bị dừng. Hãy chia nhỏ việc ra."
    except FileNotFoundError:
        return f"[lỗi] Không tìm thấy lệnh: {argv[0]}"
    return _format(proc)


def run_python(code: str, cwd: Path) -> str:
    """Ghi code ra file roi chay bang interpreter hien tai."""
    script = cwd / "_run.py"
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    return run_command([sys.executable, str(script)], cwd)
