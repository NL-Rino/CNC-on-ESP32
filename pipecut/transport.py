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


class TcpTransport(Transport):
    """Nối tới FluidNC **qua mạng LAN** bằng cổng telnet (mặc định 23).

    FluidNC mở sẵn một máy chủ telnet nói đúng giao thức Grbl như cổng COM,
    nên toàn bộ phần điều khiển phía trên không phải sửa gì: chỉ đổi đường
    truyền.  Ưu điểm là không cần dây USB, đặt máy tính ở đâu trong xưởng cũng
    điều khiển được; nhược điểm là mạng WiFi chập chờn thì lệnh tới trễ, nên
    khi cắt nên dùng WiFi ổn định hoặc cắm dây mạng cho bo.

    Một số máy chủ telnet gửi kèm chuỗi thương lượng IAC (0xFF); phần đọc ở
    đây lọc bỏ chúng để không lẫn vào dữ liệu G-code.
    """

    DEFAULT_PORT = 23

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 0.1):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self._sock = None

    def open(self) -> None:
        import socket

        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=5.0)
        except OSError as exc:
            raise TransportError(
                f"Không kết nối được tới {self.host}:{self.port} - {exc}. "
                f"Kiểm tra bo đã lên WiFi chưa và máy tính có cùng mạng không."
            ) from exc
        self._sock.settimeout(self.timeout)
        try:
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def write(self, data: bytes) -> int:
        if self._sock is None:
            raise TransportError("Chưa kết nối mạng.")
        try:
            self._sock.sendall(data)
            return len(data)
        except OSError as exc:
            raise TransportError(f"Lỗi gửi qua mạng: {exc}") from exc

    def read(self, size: int = 1024) -> bytes:
        if self._sock is None:
            return b""
        import socket

        try:
            data = self._sock.recv(size)
        except (socket.timeout, TimeoutError):
            return b""
        except BlockingIOError:
            return b""
        except OSError as exc:
            raise TransportError(f"Lỗi đọc từ mạng: {exc}") from exc
        if not data:
            raise TransportError("Bo mạch đã đóng kết nối.")
        return _strip_telnet(data)

    @property
    def is_open(self) -> bool:
        return self._sock is not None

    @property
    def description(self) -> str:
        return f"{self.host}:{self.port} (LAN)"


def _strip_telnet(data: bytes) -> bytes:
    """Bỏ các chuỗi thương lượng telnet (IAC) nếu máy chủ có gửi."""
    if b"\xff" not in data:
        return data
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0xFF and i + 1 < len(data):
            nxt = data[i + 1]
            if nxt == 0xFF:          # 0xFF 0xFF = một byte 0xFF thật
                out.append(0xFF)
                i += 2
                continue
            i += 3 if nxt in (0xFB, 0xFC, 0xFD, 0xFE) else 2
            continue
        out.append(b)
        i += 1
    return bytes(out)


def parse_address(text: str) -> Optional[Tuple[str, int]]:
    """Nhận diện một địa chỉ mạng: ``192.168.1.50``, ``fluidnc.local:23``...

    Trả về ``None`` nếu chuỗi trông giống tên cổng COM chứ không phải địa chỉ.
    """
    s = (text or "").strip()
    if not s or s.upper() in ("GIA-LAP", "SIM", "SIMULATOR"):
        return None
    if s.upper().startswith("COM") or s.startswith("/dev/"):
        return None
    host, _, port = s.partition(":")
    if not host:
        return None
    looks_ip = host.replace(".", "").isdigit() and host.count(".") == 3
    looks_host = ("." in host and not host[0].isdigit()) or host.endswith(".local")
    if not (looks_ip or looks_host):
        return None
    try:
        port_num = int(port) if port else TcpTransport.DEFAULT_PORT
    except ValueError:
        return None
    return (host, port_num)


def discover_lan(port: int = TcpTransport.DEFAULT_PORT, timeout: float = 0.35,
                 workers: int = 64) -> List[Tuple[str, str]]:
    """Dò tìm bo FluidNC trong mạng LAN bằng cách thử mở cổng telnet.

    Quét dải /24 quanh địa chỉ của chính máy tính.  Không dùng mDNS để khỏi
    phụ thuộc thư viện ngoài; đổi lại chỉ tìm được trong cùng dải mạng con.
    """
    import socket
    from concurrent.futures import ThreadPoolExecutor

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
        probe.close()
    except OSError:
        return []
    parts = local_ip.split(".")
    if len(parts) != 4:
        return []
    prefix = ".".join(parts[:3])

    def probe_host(n: int) -> Optional[Tuple[str, str]]:
        ip = f"{prefix}.{n}"
        try:
            with socket.create_connection((ip, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                try:
                    banner = sock.recv(120).decode("utf-8", "replace").strip()
                except OSError:
                    banner = ""
            return (ip, banner.splitlines()[0] if banner else "")
        except OSError:
            return None

    found: List[Tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(probe_host, range(1, 255)):
            if res:
                found.append(res)
    return found


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
            up = desc.upper()
            # ESP32-S3 (và S2/C3...) có USB nối thẳng vào chip, không qua chip
            # cầu USB-UART nào, nên hiện ra dưới mã nhà sản xuất của Espressif.
            # Bo S3-DevKitC-1 có HAI cổng USB-C: cổng "USB" là loại này, cổng
            # "UART" mới đi qua CP2102/CH340.  Cắm sai cổng là không thấy máy.
            if "303A" in hw:
                if "1001" in hw:
                    hint = " [ESP32-S3 USB gắn trong - cổng USB]"
                elif "1002" in hw:
                    hint = " [ESP32-S3 USB-OTG]"
                else:
                    hint = " [Espressif USB gắn trong]"
            # các chip USB-UART hay gặp trên board ESP32
            elif "CP210" in up or "10C4" in hw:
                hint = " [CP2102 - ESP32]"
            elif "CH340" in up or "1A86" in hw:
                hint = " [CH340 - ESP32]"
            elif "FT232" in up or "0403" in hw:
                hint = " [FTDI]"
            ports.append((p.device, f"{desc}{hint}"))
    except ImportError:
        pass
    except Exception:
        pass
    ports.append(("GIA-LAP", "Thiết bị giả lập (không cần phần cứng)"))
    return ports


def list_ports_and_lan(scan: bool = False) -> List[Tuple[str, str]]:
    """Cổng COM + (tuỳ chọn) các bo FluidNC dò được trong mạng LAN."""
    ports = list_ports()
    if scan:
        for ip, banner in discover_lan():
            note = f" - {banner[:40]}" if banner else ""
            ports.insert(0, (ip, f"FluidNC qua mạng LAN{note}"))
    return ports
