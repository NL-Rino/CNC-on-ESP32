"""Lớp truyền dẫn: cổng COM thật hoặc thiết bị giả lập.

Tách riêng để toàn bộ phần điều khiển có thể chạy và kiểm thử mà không cần
phần cứng - chỉ việc đổi ``SerialTransport`` thành ``LoopbackTransport``.
"""

from __future__ import annotations

import time
from typing import List, Optional, Protocol, Tuple


class TransportError(RuntimeError):
    pass


class Transport:
    """Giao diện tối thiểu mà bộ điều khiển cần."""

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> int:
        raise NotImplementedError

    def read(self, size: int = 1024) -> bytes:
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        raise NotImplementedError

    @property
    def description(self) -> str:
        return "transport"


class SerialTransport(Transport):
    """Cổng COM thật qua ``pyserial``.

    ``pyserial`` chỉ được nạp khi thực sự mở cổng, nhờ vậy phần sinh G-code và
    mô phỏng vẫn dùng được trên máy chưa cài thư viện này.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise TransportError(
                "Chưa cài pyserial.  Chạy:  pip install pyserial"
            ) from exc
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=2.0,
            )
        except Exception as exc:
            raise TransportError(f"Không mở được cổng {self.port}: {exc}") from exc
        # ESP32 khởi động lại khi cổng được mở (DTR/RTS) - chờ nó boot xong
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def write(self, data: bytes) -> int:
        if self._ser is None:
            raise TransportError("Cổng chưa mở.")
        try:
            return self._ser.write(data) or 0
        except Exception as exc:
            raise TransportError(f"Lỗi ghi cổng COM: {exc}") from exc

    def read(self, size: int = 1024) -> bytes:
        if self._ser is None:
            return b""
        try:
            waiting = getattr(self._ser, "in_waiting", 0)
            n = max(1, min(size, waiting or 1))
            return self._ser.read(n)
        except Exception as exc:
            raise TransportError(f"Lỗi đọc cổng COM: {exc}") from exc

    @property
    def is_open(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", False)

    @property
    def description(self) -> str:
        return f"{self.port} @ {self.baudrate}"


class LoopbackTransport(Transport):
    """Nối thẳng vào một thiết bị giả lập chạy trong cùng tiến trình."""

    def __init__(self, device):
        self.device = device
        self._open = False

    def open(self) -> None:
        self.device.reset()
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> int:
        if not self._open:
            raise TransportError("Cổng giả lập chưa mở.")
        self.device.feed_input(data)
        return len(data)

    def read(self, size: int = 1024) -> bytes:
        if not self._open:
            return b""
        self.device.tick()
        return self.device.take_output(size)

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def description(self) -> str:
        return "GIA-LAP"


def list_ports() -> List[Tuple[str, str]]:
    """Liệt kê cổng COM khả dụng -> [(tên cổng, mô tả)].

    Luôn kèm mục ``GIA-LAP`` để dùng thử phần mềm khi chưa có máy.
    """
    ports: List[Tuple[str, str]] = []
    try:
        from serial.tools import list_ports as lp  # type: ignore

        for p in lp.comports():
            desc = p.description or ""
            hint = ""
            hw = (p.hwid or "").upper()
            # các chip USB-UART hay gặp trên board ESP32
            if "CP210" in desc.upper() or "10C4" in hw:
                hint = " [CP2102 - ESP32]"
            elif "CH340" in desc.upper() or "1A86" in hw:
                hint = " [CH340 - ESP32]"
            elif "FT232" in desc.upper() or "0403" in hw:
                hint = " [FTDI]"
            ports.append((p.device, f"{desc}{hint}"))
    except ImportError:
        pass
    except Exception:
        pass
    ports.append(("GIA-LAP", "Thiết bị giả lập (không cần phần cứng)"))
    return ports
