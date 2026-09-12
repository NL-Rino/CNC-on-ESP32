"""Agent loop: goi Claude, chay tool, lap lai cho den khi xong.

Toan bo qua trinh duoc phat ra duoi dang event de giao dien ve lai theo thoi gian thuc:
model dang suy nghi gi, goi tool nao, ket qua ra sao.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from .config import settings
from .tools.builtin import build_registry
from .tools.registry import ToolContext

# Gia tham khao (USD / 1 trieu token) de uoc luong chi phi hien tren giao dien.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5-1": (10.0, 50.0),
}

SYSTEM_PROMPT = """\
Bạn là một trợ lý AI cá nhân. Trả lời bằng tiếng Việt tự nhiên, trừ khi người dùng \
dùng ngôn ngữ khác thì theo họ.

Bạn không chỉ biết nói chuyện — bạn có công cụ thật và được khuyến khích dùng chúng:

- run_python: chạy Python thật. Dùng để tính toán, xử lý dữ liệu, tạo file, vẽ biểu đồ. \
Đừng tính nhẩm trong đầu khi có thể chạy code cho chắc.
- read_file / write_file / list_files: workspace riêng của cuộc trò chuyện này. \
Kết quả nào đáng giữ lại thì ghi ra file để người dùng tải về.
- http_request: gọi API công khai.
- web_search / web_fetch: tìm và đọc thông tin mới trên mạng. Bắt buộc dùng khi câu hỏi \
liên quan đến sự kiện gần đây, giá cả, phiên bản phần mềm, hoặc bất kỳ thứ gì có thể đã \
thay đổi sau khi bạn được huấn luyện.
- remember / recall: nhớ thông tin về người dùng giữa các lượt.

Nguyên tắc làm việc:
1. Việc nhiều bước thì cứ làm từng bước bằng tool thật, đừng mô tả suông rồi hỏi \
"bạn có muốn tôi làm không".
2. Trước khi khẳng định một con số hay một sự kiện, kiểm tra bằng tool nếu kiểm tra được.
3. Nếu tool báo lỗi, đọc kỹ lỗi rồi tự sửa, đừng bỏ cuộc ngay lần đầu.
4. Trả lời gọn, đi thẳng vào việc. Có kết quả thì nói kết quả trước, giải thích sau.
5. Không bịa đường dẫn file hay nội dung mà bạn chưa thực sự tạo ra.
"""


def _price(model: str, usage: Any) -> float:
    rate_in, rate_out = PRICING.get(model, (0.0, 0.0))
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    # Token doc tu cache re hon ~10 lan gia input thuong.
    return (tokens_in * rate_in + cached * rate_in * 0.1 + tokens_out * rate_out) / 1_000_000


class Agent:
    def __init__(self) -> None:
        if not settings.api_key:
            raise RuntimeError(
                "Chưa có ANTHROPIC_API_KEY. Tạo file .env từ .env.example rồi điền key vào."
            )
        self.client = anthropic.AsyncAnthropic(api_key=settings.api_key)
        self.registry = build_registry()
        # Bat sau lan dau bi API tu choi tham so beta, de khong thu lai mai.
        self._fallback_unsupported = False

    # ------------------------------------------------------------------ tools
    def tool_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = self.registry.schemas()
        if settings.enable_web:
            specs.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 8})
            specs.append({"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8})
        return specs

    def tool_catalog(self) -> list[dict[str, str]]:
        """Danh sach tool cho giao dien hien thi."""
        items = [
            {"name": t.name, "label": t.label or t.name, "icon": t.icon}
            for t in self.registry.tools.values()
        ]
        if settings.enable_web:
            items.append({"name": "web_search", "label": "Tìm trên web", "icon": "globe"})
            items.append({"name": "web_fetch", "label": "Đọc trang web", "icon": "globe"})
        return items

    def _label(self, name: str) -> str:
        tool = self.registry.get(name)
        if tool:
            return tool.label or name
        return {"web_search": "Tìm trên web", "web_fetch": "Đọc trang web"}.get(name, name)

    async def _execute(self, block: Any, ctx: ToolContext) -> tuple[dict[str, Any], str, bool]:
        """Chay mot tool trong thread rieng (subprocess la blocking)."""
        payload = block.input if isinstance(block.input, dict) else {}
        result, failed = await asyncio.to_thread(self.registry.run, block.name, payload, ctx)
        tool_result = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result or "(không có kết quả)",
        }
        if failed:
            tool_result["is_error"] = True
        return tool_result, result, failed

    # ------------------------------------------------------------------ request
    def _request_kwargs(self, messages: list[Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "max_tokens": settings.max_tokens,
            "system": [
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": messages,
            "tools": self.tool_specs(),
            # Adaptive: model tu quyet dinh suy luan sau bao nhieu.
            # display="summarized" de nguoi dung thay duoc mach suy nghi.
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": settings.effort},
        }
        if settings.refusal_fallback and not self._fallback_unsupported:
            # Neu model tu choi vi chinh sach an toan, API tu chay lai tren model
            # du phong ngay trong cung mot lan goi thay vi tra ve tay trang.
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        return kwargs

    # ------------------------------------------------------------------ loop
    async def run(self, messages: list[Any], session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Chay mot luot tra loi. Yield event de server day xuong trinh duyet.

        `messages` duoc sua tai cho, nen sau khi chay xong caller da co lich su day du.
        """
        ctx = ToolContext(session_dir=settings.session_dir(session_id), session_id=session_id)
        total_cost = 0.0
        tokens_in = tokens_out = 0

        for round_index in range(settings.max_tool_rounds):
            try:
                final = None
                async for event in self._stream_round(messages):
                    if event["type"] == "_final":
                        final = event["message"]
                    else:
                        yield event
            except anthropic.BadRequestError as exc:
                detail = str(exc).lower()
                if not self._fallback_unsupported and ("fallback" in detail or "beta" in detail):
                    # API khong nhan tham so fallback -> bo di va thu lai mot lan.
                    self._fallback_unsupported = True
                    continue
                yield {"type": "error", "message": f"API từ chối request: {exc}"}
                return
            except anthropic.AuthenticationError:
                yield {
                    "type": "error",
                    "message": (
                        "ANTHROPIC_API_KEY không hợp lệ. Kiểm tra lại key trong file .env "
                        "(hoặc trong phần biến môi trường của host)."
                    ),
                }
                return
            except anthropic.RateLimitError:
                yield {"type": "error", "message": "Bị giới hạn tốc độ. Đợi một chút rồi thử lại."}
                return
            except anthropic.APIStatusError as exc:
                yield {"type": "error", "message": f"Lỗi API ({exc.status_code}): {exc}"}
                return
            except anthropic.APIConnectionError:
                yield {"type": "error", "message": "Mất kết nối tới Anthropic. Thử lại nhé."}
                return

            if final is None:
                yield {"type": "error", "message": "Không nhận được phản hồi từ model."}
                return

            tokens_in += getattr(final.usage, "input_tokens", 0) or 0
            tokens_out += getattr(final.usage, "output_tokens", 0) or 0
            total_cost += _price(settings.model, final.usage)

            if final.stop_reason == "refusal":
                reason = getattr(final, "stop_details", None)
                note = getattr(reason, "explanation", None) or "không nêu lý do cụ thể"
                yield {"type": "error", "message": f"Model từ chối yêu cầu này ({note})."}
                return

            messages.append({"role": "assistant", "content": final.content})

            # Tool phia server (web_search) cham qua gioi han vong lap -> gui lai de chay tiep.
            if final.stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if not tool_uses:
                break

            # Chay song song, nhung TAT CA ket qua phai nam trong DUNG MOT user message.
            results = await asyncio.gather(*(self._execute(b, ctx) for b in tool_uses))
            tool_results = []
            for block, (tool_result, raw, failed) in zip(tool_uses, results, strict=True):
                tool_results.append(tool_result)
                yield {
                    "type": "tool_end",
                    "id": block.id,
                    "ok": not failed,
                    "output": raw[:4000],
                }
            messages.append({"role": "user", "content": tool_results})
        else:
            yield {
                "type": "error",
                "message": f"Đã chạy hết {settings.max_tool_rounds} vòng tool mà chưa xong.",
            }

        yield {
            "type": "done",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": round(total_cost, 5),
        }

    async def _stream_round(self, messages: list[Any]) -> AsyncIterator[dict[str, Any]]:
        """Mot lan goi API, dich stream event cua SDK sang event cua ung dung."""
        kwargs = self._request_kwargs(messages)
        streamer = self.client.beta.messages.stream if "betas" in kwargs else self.client.messages.stream

        async with streamer(**kwargs) as stream:
            async for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        yield {
                            "type": "tool_start",
                            "id": block.id,
                            "name": block.name,
                            "label": self._label(block.name),
                        }
                    elif block.type == "server_tool_use":
                        yield {
                            "type": "tool_start",
                            "id": block.id,
                            "name": block.name,
                            "label": self._label(block.name),
                            "server": True,
                        }

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        yield {"type": "thinking", "text": delta.thinking}
                    elif delta.type == "text_delta":
                        yield {"type": "text", "text": delta.text}

                elif etype == "content_block_stop":
                    block = getattr(event, "content_block", None)
                    if block is None:
                        continue
                    if block.type == "tool_use":
                        yield {
                            "type": "tool_input",
                            "id": block.id,
                            "input": json.dumps(block.input, ensure_ascii=False)[:2000],
                        }
                    elif block.type == "server_tool_use":
                        yield {
                            "type": "tool_input",
                            "id": block.id,
                            "input": json.dumps(block.input, ensure_ascii=False)[:2000],
                        }
                        # Tool phia server chay tren ha tang Anthropic: khong co buoc
                        # thuc thi phia minh, nen danh dau xong luon.
                        yield {"type": "tool_end", "id": block.id, "ok": True, "output": ""}

            yield {"type": "_final", "message": await stream.get_final_message()}
