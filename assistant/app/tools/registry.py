"""Registry tool: gom dinh nghia schema + ham thuc thi vao mot cho."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolContext:
    """Moi tra ve cho ham tool: thu muc rieng cua phien dang chat."""

    session_dir: Path
    session_id: str


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], str]
    # Nhan hien thi tren giao dien, cho de doc
    label: str = ""
    icon: str = "*"

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def run(self, name: str, payload: dict[str, Any], ctx: ToolContext) -> tuple[str, bool]:
        """Chay tool, tra ve (ket_qua, co_loi). Khong bao gio nem exception ra ngoai:
        agent loop can mot tool_result cho MOI tool_use, ke ca khi that bai."""
        tool = self.get(name)
        if tool is None:
            return f"Tool '{name}' không tồn tại.", True
        try:
            return tool.handler(payload, ctx), False
        except Exception as exc:  # noqa: BLE001 - loi tool phai quay ve cho model
            return f"{type(exc).__name__}: {exc}", True
