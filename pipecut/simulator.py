"""Bộ giả lập FluidNC.

Mô phỏng đủ sát để kiểm thử toàn bộ đường đi của phần mềm: bộ đệm nhận
(character-counting), hàng đợi planner, chuyển động theo thời gian thực,
báo cáo trạng thái, jog, tạm dừng, báo động.

Không mô phỏng gia tốc - thời gian mỗi block tính theo ``L/F`` - nên thời
gian chạy giả lập chỉ mang tính tham khảo.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

WELCOME = "\r\nGrbl 1.1f ['$' for help]\r\n"


@dataclass
class Block:
    target: Dict[str, float]
    feed: float
    duration: float
    is_dwell: bool = False


class FluidNCSimulator:
    """Thiết bị FluidNC ảo, dùng chung giao diện với cổng COM."""

    def __init__(self, axes: str = "XYZA", rx_buffer: int = 127,
                 planner_size: int = 16, time_scale: float = 1.0):
        self.letters = list(axes.upper())
        self.rx_buffer = rx_buffer
        self.planner_size = planner_size
        self.time_scale = max(1e-3, time_scale)
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.pos: Dict[str, float] = {c: 0.0 for c in self.letters}
        self.target: Dict[str, float] = dict(self.pos)
        self.wco: Dict[str, float] = {c: 0.0 for c in self.letters}
        self.queue: Deque[Block] = deque()
        self._in = bytearray()
        self._out = bytearray(WELCOME.encode())
        self.state = "Idle"
        self.feed = 1500.0
        self.spindle_on = False
        self.spindle_speed = 0.0
        self.absolute = True
        self.block_start: Optional[float] = None
        self.block_from: Dict[str, float] = dict(self.pos)
        self.now = time.monotonic()
        self.alarm: Optional[int] = None
        self.lines_done = 0
        self.overrides = (100, 100, 100)

    # ------------------------------------------------------------------
    # Cổng vào / ra
    # ------------------------------------------------------------------
    def feed_input(self, data: bytes) -> None:
        for byte in data:
            b = bytes([byte])
            if byte >= 0x80 or b in (b"?", b"~", b"!", b"\x18"):
                self._realtime(b)
                continue
            if b in (b"\n", b"\r"):
                line = self._in.decode("utf-8", "replace").strip()
                self._in.clear()
                if line:
                    self._execute(line)
                else:
                    self._emit("ok")
                continue
            self._in.append(byte)

    def take_output(self, size: int = 1024) -> bytes:
        chunk = bytes(self._out[:size])
        del self._out[:len(chunk)]
        return chunk

    def _emit(self, text: str) -> None:
        self._out.extend((text + "\r\n").encode())

    # ------------------------------------------------------------------
    # Lệnh thời gian thực
    # ------------------------------------------------------------------
    def _realtime(self, b: bytes) -> None:
        if b == b"?":
            self.tick()
            self._emit(self.status_report())
        elif b == b"!":
            if self.state == "Run":
                self.state = "Hold"
        elif b == b"~":
            if self.state == "Hold":
                self.state = "Run" if self.queue or self.block_start else "Idle"
                self.block_start = self.now if self.queue else None
        elif b == b"\x18":
            was_alarm = self.alarm
            self.reset()
            if was_alarm:
                self.alarm = was_alarm
                self.state = "Alarm"
        elif b == b"\x85":
            self.queue.clear()
            self.block_start = None
            self.state = "Idle"

    # ------------------------------------------------------------------
    # Thông dịch G-code (mức đủ dùng để kiểm thử)
    # ------------------------------------------------------------------
    def _execute(self, line: str) -> None:
        s = line.strip()
        if s.startswith("$"):
            self._dollar(s)
            return
        if self.state == "Alarm":
            self._emit("error:9")
            return
        words = self._parse_words(s)
        if not words:
            self._emit("ok")
            return
        motion = None
        dwell = 0.0
        for letter, value in words:
            if letter == "G":
                iv = int(round(value * 10))
                if iv == 0:
                    motion = "G0"
                elif iv == 10:
                    motion = "G1"
                elif iv == 40:
                    dwell = -1.0
                elif iv == 900:
                    self.absolute = True
                elif iv == 910:
                    self.absolute = False
            elif letter == "M":
                iv = int(round(value))
                if iv in (3, 4):
                    self.spindle_on = True
                elif iv == 5:
                    self.spindle_on = False
                elif iv in (2, 30):
                    self.spindle_on = False
            elif letter == "F":
                self.feed = max(1.0, value)
            elif letter == "S":
                self.spindle_speed = value
            elif letter == "P" and dwell < 0:
                dwell = value

        if dwell > 0:
            self.queue.append(Block(dict(self.target), 0.0, dwell, is_dwell=True))
            self._start_if_idle()
            self._emit("ok")
            return

        axis_words = {l: v for l, v in words if l in self.letters}
        if axis_words:
            new_target = dict(self.target)
            for letter, value in axis_words.items():
                new_target[letter] = value if self.absolute else new_target[letter] + value
            dist = math.sqrt(sum((new_target[c] - self.target[c]) ** 2 for c in self.letters))
            rate = self.feed if motion != "G0" else max(self.feed, 3000.0)
            duration = (dist / max(rate, 1.0)) * 60.0
            self.queue.append(Block(new_target, rate, duration))
            self.target = new_target
            self._start_if_idle()
        self.lines_done += 1
        # Giống Grbl: chỉ trả 'ok' khi hàng đợi planner còn chỗ
        if len(self.queue) > self.planner_size:
            self._pending_ok = getattr(self, "_pending_ok", 0) + 1
        else:
            self._emit("ok")

    def _dollar(self, s: str) -> None:
        low = s.lower()
        if low == "$$":
            self._emit("$0=10"); self._emit("$1=25"); self._emit("$100=80.000")
            self._emit("ok")
        elif low == "$i":
            self._emit("[VER:1.1f FluidNC v3.7.x (gia lap)]")
            self._emit("[OPT:VL,16,128]")
            self._emit("ok")
        elif low == "$x":
            self.alarm = None
            self.state = "Idle"
            self._emit("[MSG:Caution: Unlocked]")
            self._emit("ok")
        elif low == "$h":
            for c in self.letters:
                self.pos[c] = 0.0
            self.target = dict(self.pos)
            self.queue.clear()
            self.alarm = None
            self.state = "Idle"
            self._emit("ok")
        elif low.startswith("$j="):
            body = s[3:]
            words = self._parse_words(body)
            rel = "G91" in body.upper()
            feed = self.feed
            new_target = dict(self.target)
            for letter, value in words:
                if letter in self.letters:
                    new_target[letter] = new_target[letter] + value if rel else value
                elif letter == "F":
                    feed = max(1.0, value)
            dist = math.sqrt(sum((new_target[c] - self.target[c]) ** 2 for c in self.letters))
            self.queue.append(Block(new_target, feed, (dist / max(feed, 1.0)) * 60.0))
            self.target = new_target
            self._start_if_idle(jog=True)
            self._emit("ok")
        elif low == "$g":
            self._emit("[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]")
            self._emit("ok")
        else:
            self._emit("ok")

    @staticmethod
    def _parse_words(line: str) -> List[Tuple[str, float]]:
        out: List[Tuple[str, float]] = []
        i = 0
        s = line.upper()
        # bỏ chú thích
        while "(" in s and ")" in s:
            a, b = s.index("("), s.index(")")
            if a < b:
                s = s[:a] + s[b + 1:]
            else:
                break
        if ";" in s:
            s = s[:s.index(";")]
        while i < len(s):
            ch = s[i]
            if ch.isalpha():
                j = i + 1
                num = ""
                while j < len(s) and (s[j].isdigit() or s[j] in "+-."):
                    num += s[j]
                    j += 1
                try:
                    out.append((ch, float(num)))
                except ValueError:
                    pass
                i = j
            else:
                i += 1
        return out

    def _start_if_idle(self, jog: bool = False) -> None:
        if self.state in ("Idle", "Run", "Jog"):
            if self.block_start is None:
                self.block_start = self.now
                self.block_from = dict(self.pos)
            self.state = "Jog" if jog else "Run"

    # ------------------------------------------------------------------
    # Tiến trình chuyển động theo thời gian thực
    # ------------------------------------------------------------------
    def tick(self, now: Optional[float] = None) -> None:
        self.now = now if now is not None else time.monotonic()
        if self.state == "Hold" or self.block_start is None:
            return
        guard = 0
        while self.queue and guard < 10000:
            guard += 1
            block = self.queue[0]
            dur = max(1e-4, block.duration / self.time_scale)
            elapsed = self.now - self.block_start
            if elapsed >= dur:
                self.pos = dict(block.target)
                self.block_from = dict(self.pos)
                self.block_start += dur
                self.queue.popleft()
                pending = getattr(self, "_pending_ok", 0)
                if pending > 0:
                    self._emit("ok")
                    self._pending_ok = pending - 1
                continue
            t = elapsed / dur
            if not block.is_dwell:
                for c in self.letters:
                    a = self.block_from.get(c, 0.0)
                    b = block.target.get(c, a)
                    self.pos[c] = a + (b - a) * t
            return
        if not self.queue:
            self.block_start = None
            if self.state in ("Run", "Jog"):
                self.state = "Idle"

    # ------------------------------------------------------------------
    def status_report(self) -> str:
        mpos = ",".join(f"{self.pos[c]:.3f}" for c in self.letters)
        wco = ",".join(f"{self.wco[c]:.3f}" for c in self.letters)
        state = self.state
        if self.alarm:
            state = "Alarm"
        planner_free = max(0, self.planner_size - len(self.queue))
        rx_free = self.rx_buffer
        cur_feed = self.queue[0].feed if self.queue else 0.0
        # FluidNC chỉ gửi trường 'A:' khi có phụ kiện đang bật; 'S' = trục
        # chính / nguồn cắt.  Giao diện dựa vào đây để biết lúc nào đang cắt.
        acc = "|A:S" if self.spindle_on else ""
        return (f"<{state}|MPos:{mpos}|FS:{cur_feed:.0f},{self.spindle_speed:.0f}"
                f"|WCO:{wco}|Bf:{planner_free},{rx_free}"
                f"|Ov:{self.overrides[0]},{self.overrides[1]},{self.overrides[2]}{acc}>")

    # ------------------------------------------------------------------
    def raise_alarm(self, code: int = 1) -> None:
        """Giả lập sự cố (chạm công tắc hành trình...) để thử phần xử lý lỗi."""
        self.alarm = code
        self.state = "Alarm"
        self.queue.clear()
        self.block_start = None
        self._emit(f"ALARM:{code}")


# --------------------------------------------------------------------------
# Máy ảo chạy trên mạng
# --------------------------------------------------------------------------
class FluidNCServer:
    """Cho máy ảo lắng nghe trên một cổng TCP như FluidNC thật.

    Dùng để thử đường truyền LAN mà không cần bo mạch: mở máy chủ này rồi trỏ
    phần mềm tới ``127.0.0.1:<cổng>``.  Cũng là cách kiểm thử toàn bộ đường đi
    qua socket thật thay vì giả lập trong bộ nhớ.
    """

    def __init__(self, simulator: "FluidNCSimulator", host: str = "127.0.0.1",
                 port: int = 0):
        self.sim = simulator
        self.host = host
        self.port = port
        self._sock = None
        self._thread = None
        self._running = False

    def start(self) -> int:
        """Bắt đầu lắng nghe, trả về cổng thực tế đang dùng."""
        import socket
        import threading

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _serve(self) -> None:
        import socket

        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                return
            conn.settimeout(0.02)
            self.sim.reset()
            try:
                while self._running:
                    try:
                        data = conn.recv(4096)
                        if not data:
                            break
                        self.sim.feed_input(data)
                    except (socket.timeout, TimeoutError):
                        pass
                    except OSError:
                        break
                    self.sim.tick()
                    out = self.sim.take_output(4096)
                    if out:
                        try:
                            conn.sendall(out)
                        except OSError:
                            break
                    time.sleep(0.002)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
