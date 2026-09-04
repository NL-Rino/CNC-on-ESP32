"""Điều khiển thiết bị FluidNC: kết nối, gửi lệnh, chạy chương trình.

Giao thức nạp lệnh: **đếm ký tự (character-counting)**
------------------------------------------------------
Cách ngây thơ là gửi một dòng rồi chờ ``ok``.  Làm vậy máy chạy hết block
này mới nhận block sau, planner không bao giờ có gì để nhìn trước, nên cứ
mỗi đoạn lại tăng tốc rồi phanh - đường cắt gợn sóng, đặc biệt rõ trên các
đoạn ngắn của đường cong.

Cách đúng (Grbl/FluidNC khuyến nghị): luôn giữ cho bộ đệm nhận của máy gần
đầy.  Ta cộng dồn độ dài các dòng đã gửi mà chưa nhận ``ok``; chỉ gửi tiếp
khi tổng đó cộng dòng mới vẫn nhỏ hơn dung lượng bộ đệm.  Nhờ vậy ESP32 luôn
có sẵn 15-20 block phía trước để planner làm mượt vận tốc giữa các đoạn.

Toàn bộ vào/ra chạy trên luồng riêng, giao diện chỉ nhận sự kiện qua callback.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from . import protocol as proto
from .config import MachineProfile
from .protocol import MachineStatus, Response
from .transport import (LoopbackTransport, SerialTransport, TcpTransport,
                        Transport, TransportError, parse_address)

Listener = Callable[..., None]


@dataclass
class JobProgress:
    total: int = 0
    sent: int = 0
    acked: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    errors: List[str] = field(default_factory=list)
    running: bool = False
    paused: bool = False

    @property
    def percent(self) -> float:
        return 100.0 * self.acked / self.total if self.total else 0.0

    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.monotonic()
        return end - self.started_at

    @property
    def eta(self) -> float:
        if self.acked < 3 or not self.running:
            return 0.0
        rate = self.acked / max(self.elapsed, 1e-6)
        return max(0.0, (self.total - self.acked) / max(rate, 1e-6))


@dataclass
class _Pending:
    length: int
    is_job: bool
    line: str


class DeviceController:
    """Kết nối và điều khiển một máy FluidNC."""

    def __init__(self, profile: MachineProfile):
        self.profile = profile
        self.transport: Optional[Transport] = None
        self.status: Optional[MachineStatus] = None
        self._probe_result: Optional[proto.ProbeResult] = None
        self._probe_thread: Optional[threading.Thread] = None
        self._probe_stop = False
        self.progress = JobProgress()
        self.firmware: str = ""

        # callback (giao diện gán vào)
        self.on_line: Optional[Callable[[str, str], None]] = None      # (text, "tx"/"rx")
        self.on_status: Optional[Callable[[MachineStatus], None]] = None
        self.on_progress: Optional[Callable[[JobProgress], None]] = None
        self.on_event: Optional[Callable[[str, str], None]] = None     # (loại, nội dung)

        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._pending: Deque[_Pending] = deque()
        self._pending_bytes = 0
        self._cmd_queue: Deque[str] = deque()
        self._job_lines: List[str] = []
        self._job_index = 0
        self._running = False
        self._threads: List[threading.Thread] = []
        self._rx_partial = ""
        self._last_status_req = 0.0
        self._connected = False

    # ==================================================================
    # Kết nối
    # ==================================================================
    @property
    def is_connected(self) -> bool:
        return self._connected and self.transport is not None and self.transport.is_open

    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None,
                simulator=None) -> None:
        """Mở cổng.  ``port='GIA-LAP'`` hoặc truyền ``simulator`` để chạy mô phỏng."""
        if self.is_connected:
            self.disconnect()
        conn = self.profile.connection
        port = port or conn.port
        baudrate = baudrate or conn.baudrate
        if simulator is not None or (port or "").upper() in ("GIA-LAP", "SIM", "SIMULATOR"):
            if simulator is None:
                from .simulator import FluidNCSimulator
                simulator = FluidNCSimulator(axes="".join(self.profile.letters),
                                             rx_buffer=conn.rx_buffer,
                                             time_scale=max(0.01, conn.simulator_speed))
            self.transport = LoopbackTransport(simulator)
        else:
            if not port:
                raise TransportError("Chưa chọn cổng COM hoặc địa chỉ mạng.")
            address = parse_address(port)
            if address:
                self.transport = TcpTransport(address[0], address[1], conn.timeout)
            else:
                self.transport = SerialTransport(port, baudrate, conn.timeout)
        self.transport.open()
        self._connected = True
        self._reset_buffers()
        self._running = True
        self._threads = [
            threading.Thread(target=self._reader_loop, name="pipecut-rx", daemon=True),
            threading.Thread(target=self._writer_loop, name="pipecut-tx", daemon=True),
            threading.Thread(target=self._poll_loop, name="pipecut-poll", daemon=True),
        ]
        for t in self._threads:
            t.start()
        self._emit_event("connected", f"Đã kết nối {self.transport.description}")

    def disconnect(self) -> None:
        self._running = False
        with self._cond:
            self._cond.notify_all()
        for t in self._threads:
            if t.is_alive() and t is not threading.current_thread():
                t.join(timeout=1.0)
        self._threads = []
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass
        self._connected = False
        self.transport = None
        self._emit_event("disconnected", "Đã ngắt kết nối")

    def _reset_buffers(self) -> None:
        with self._cond:
            self._pending.clear()
            self._pending_bytes = 0
            self._cmd_queue.clear()
            self._job_lines = []
            self._job_index = 0
            self._rx_partial = ""
            self.progress = JobProgress()
            self._cond.notify_all()

    # ==================================================================
    # Gửi lệnh
    # ==================================================================
    def send(self, line: str, front: bool = False) -> None:
        """Xếp một dòng lệnh vào hàng đợi (ưu tiên hơn dòng của chương trình)."""
        text = line.strip()
        if not text:
            return
        with self._cond:
            if front:
                self._cmd_queue.appendleft(text)
            else:
                self._cmd_queue.append(text)
            self._cond.notify_all()

    # ==================================================================
    # Chế độ dò cạnh
    # ==================================================================
    def run_probe(self, routine, on_done=None, on_step=None) -> None:
        """Chạy một quy trình dò cạnh ở luồng nền.

        Quy trình là một generator: nó phát ra từng bước, mình gửi xuống máy,
        **chờ máy chạy xong hẳn**, rồi đưa kết quả dò ngược lại cho nó quyết
        định bước sau.  Phải chờ máy về trạng thái rảnh chứ không chỉ chờ chữ
        'ok': Grbl trả 'ok' ngay khi *nhận* dòng lệnh, chưa chạy xong.
        """
        if not self.is_connected:
            raise RuntimeError("Chưa kết nối máy.")
        if self._probe_thread and self._probe_thread.is_alive():
            raise RuntimeError("Đang có một quy trình dò chạy dở.")
        self._probe_stop = False

        def work() -> None:
            result = None
            try:
                while True:
                    step = routine.send(result)
                    result = None
                    if self._probe_stop:
                        raise RuntimeError("Đã dừng theo yêu cầu.")
                    if step.note and on_step:
                        try:
                            on_step(step.note)
                        except Exception:
                            pass
                    with self._cond:
                        self._probe_result = None
                    for line in step.lines:
                        self.send(line)
                    self._wait_idle()
                    if step.probe:
                        result = self._wait_probe()
            except StopIteration as stop:
                outcome = stop.value
                if outcome is not None and outcome.zero:
                    self._apply_zero(outcome.zero)
                self._emit_event("probe_done", f"Dò xong: {outcome.kind}"
                                 if outcome else "Dò xong")
                if on_done:
                    on_done(outcome, None)
            except Exception as exc:
                self._emit_event("error", f"Dò cạnh dừng: {exc}")
                if on_done:
                    on_done(None, exc)

        self._probe_thread = threading.Thread(target=work, daemon=True)
        self._probe_thread.start()

    def stop_probe(self) -> None:
        """Dừng quy trình dò đang chạy."""
        self._probe_stop = True
        self.send_realtime(proto.RT_FEED_HOLD)

    def _wait_idle(self, timeout: float = 120.0) -> None:
        """Chờ máy chạy hết hàng đợi và về trạng thái rảnh."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._probe_stop:
                raise RuntimeError("Đã dừng theo yêu cầu.")
            state = self.status.state if self.status else ""
            if state in ("Alarm", "Door"):
                raise RuntimeError(f"Máy báo {state} giữa lúc dò.")
            with self._cond:
                idle = (not self._cmd_queue and self._pending_bytes == 0
                        and state == "Idle")
            if idle:
                # Xác nhận lại sau một nhịp hỏi trạng thái: 'Idle' có thể là
                # ảnh chụp cũ, chụp đúng khe hở trước khi máy kịp chạy.
                time.sleep(max(0.06, self.profile.connection.poll_interval))
                with self._cond:
                    still = (not self._cmd_queue and self._pending_bytes == 0)
                if still and self.status and self.status.state == "Idle":
                    return
            time.sleep(0.03)
        raise RuntimeError("Chờ máy quá lâu mà chưa xong bước dò.")

    def _wait_probe(self, timeout: float = 120.0) -> proto.ProbeResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._probe_stop:
                raise RuntimeError("Đã dừng theo yêu cầu.")
            with self._cond:
                if self._probe_result is not None:
                    return self._probe_result
            time.sleep(0.02)
        raise RuntimeError(
            "Không nhận được kết quả dò từ máy. Kiểm tra FluidNC đã khai chân "
            "probe chưa ($Probe/Pin) và cảm biến có nối đúng không."
        )

    def _apply_zero(self, zero: Dict[str, float]) -> None:
        """Đặt gốc chi tiết cho các trục mà quy trình dò yêu cầu."""
        if not zero:
            return
        words = " ".join(f"{letter}{value:g}" for letter, value in zero.items())
        self.send(f"G10 L20 P1 {words}")
        self._emit_event("info", f"Đã đặt gốc chi tiết: {words}")

    def send_realtime(self, byte: bytes) -> None:
        """Gửi byte thời gian thực - không xếp hàng, không chiếm bộ đệm."""
        if not self.is_connected:
            return
        try:
            self.transport.write(byte)  # type: ignore[union-attr]
        except Exception as exc:
            self._emit_event("error", f"Lỗi gửi lệnh thời gian thực: {exc}")

    # --- các lệnh hay dùng -------------------------------------------
    def home(self) -> None:
        self.send("$H", front=True)

    def unlock(self) -> None:
        self.send("$X", front=True)

    def soft_reset(self) -> None:
        self.send_realtime(proto.RT_RESET)
        self._reset_buffers()
        self._emit_event("reset", "Đã reset mềm bộ điều khiển")

    def query_firmware(self) -> None:
        self.send("$I", front=True)

    def jog(self, axes: Dict[str, float], feed: float, relative: bool = True) -> None:
        self.send(proto.jog_command(axes, feed, relative), front=True)

    def cancel_jog(self) -> None:
        self.send_realtime(proto.RT_JOG_CANCEL)

    def set_work_zero(self, letters: Optional[Sequence[str]] = None) -> None:
        """Đặt gốc toạ độ chi tiết tại vị trí hiện tại (G10 L20 P1)."""
        letters = list(letters or self.profile.letters)
        words = " ".join(f"{c}0" for c in letters)
        self.send(f"G10 L20 P1 {words}", front=True)

    def goto_work_zero(self, letters: Optional[Sequence[str]] = None) -> None:
        letters = list(letters or self.profile.letters)
        words = " ".join(f"{c}0" for c in letters)
        self.send(f"G90 G0 {words}", front=True)

    def set_feed_override(self, percent: int) -> None:
        """Điều chỉnh tốc độ chạy về gần ``percent`` bằng các bước 10%/1%."""
        cur = self.status.overrides[0] if self.status else 100
        self.send_realtime(proto.RT_FEED_100)
        cur = 100
        steps10 = int((percent - cur) / 10)
        for _ in range(abs(steps10)):
            self.send_realtime(proto.RT_FEED_PLUS10 if steps10 > 0 else proto.RT_FEED_MINUS10)
        cur += steps10 * 10
        for _ in range(abs(percent - cur)):
            self.send_realtime(proto.RT_FEED_PLUS1 if percent > cur else proto.RT_FEED_MINUS1)

    # ==================================================================
    # Chạy chương trình
    # ==================================================================
    def start_job(self, lines: Sequence[str]) -> None:
        """Bắt đầu nạp một chương trình G-code."""
        if not self.is_connected:
            raise TransportError("Chưa kết nối máy.")
        if self.progress.running:
            raise RuntimeError("Đang có chương trình chạy dở.")
        clean = [l.strip() for l in lines if l and l.strip()]
        with self._cond:
            self._job_lines = clean
            self._job_index = 0
            self.progress = JobProgress(total=len(clean), started_at=time.monotonic(),
                                        running=True)
            self._cond.notify_all()
        self._emit_event("job_start", f"Bắt đầu chạy {len(clean)} dòng lệnh")
        self._notify_progress()

    def pause_job(self) -> None:
        with self._cond:
            self.progress.paused = True
        self.send_realtime(proto.RT_FEED_HOLD)
        self._emit_event("job_pause", "Tạm dừng (feed hold)")
        self._notify_progress()

    def resume_job(self) -> None:
        with self._cond:
            self.progress.paused = False
            self._cond.notify_all()
        self.send_realtime(proto.RT_CYCLE_START)
        self._emit_event("job_resume", "Chạy tiếp")
        self._notify_progress()

    def stop_job(self) -> None:
        """Dừng khẩn: giữ dao, reset mềm, xoá hàng đợi (nguồn cắt tắt theo reset)."""
        self.send_realtime(proto.RT_FEED_HOLD)
        time.sleep(0.05)
        self.send_realtime(proto.RT_RESET)
        with self._cond:
            self._job_lines = []
            self._job_index = 0
            self._cmd_queue.clear()
            self._pending.clear()
            self._pending_bytes = 0
            self.progress.running = False
            self.progress.paused = False
            self.progress.finished_at = time.monotonic()
            self._cond.notify_all()
        self._emit_event("job_stop", "ĐÃ DỪNG chương trình")
        self._notify_progress()

    # ==================================================================
    # Luồng nền
    # ==================================================================
    def _room_for(self, line: str) -> bool:
        limit = max(16, self.profile.connection.rx_buffer - 1)
        return self._pending_bytes + len(line) + 1 <= limit

    def _next_line(self) -> Optional[Tuple[str, bool]]:
        """Chọn dòng kế tiếp: lệnh của người dùng trước, rồi tới chương trình."""
        if self._cmd_queue:
            return (self._cmd_queue[0], False)
        p = self.progress
        if p.running and not p.paused and self._job_index < len(self._job_lines):
            return (self._job_lines[self._job_index], True)
        return None

    def _commit_line(self, is_job: bool) -> None:
        if is_job:
            self._job_index += 1
            self.progress.sent = self._job_index
        else:
            self._cmd_queue.popleft()

    def _writer_loop(self) -> None:
        while self._running:
            line_info = None
            with self._cond:
                line_info = self._next_line()
                if line_info is None:
                    self._cond.wait(0.05)
                    continue
                line, is_job = line_info
                if not self._room_for(line):
                    self._cond.wait(0.05)
                    continue
                self._commit_line(is_job)
                self._pending.append(_Pending(len(line) + 1, is_job, line))
                self._pending_bytes += len(line) + 1
            try:
                self.transport.write((line + "\n").encode("ascii", "replace"))  # type: ignore[union-attr]
            except Exception as exc:
                self._emit_event("error", f"Lỗi gửi dữ liệu: {exc}")
                self._running = False
                break
            if self.on_line:
                try:
                    self.on_line(line, "tx")
                except Exception:
                    pass
            if is_job:
                self._notify_progress()

    def _reader_loop(self) -> None:
        while self._running:
            try:
                data = self.transport.read(512)  # type: ignore[union-attr]
            except Exception as exc:
                self._emit_event("error", f"Lỗi đọc dữ liệu: {exc}")
                self._running = False
                break
            if not data:
                time.sleep(0.005)
                continue
            text = self._rx_partial + data.decode("utf-8", "replace")
            parts = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            self._rx_partial = parts.pop()
            for raw in parts:
                if raw.strip():
                    self._handle_line(raw.strip())

    def _handle_line(self, line: str) -> None:
        resp = proto.parse_response(line, self.profile.letters)
        if resp.kind == "status":
            if resp.status:
                self.status = resp.status
                if self.on_status:
                    try:
                        self.on_status(resp.status)
                    except Exception:
                        pass
            return  # không đổ báo cáo trạng thái ra console cho đỡ nhiễu

        if self.on_line:
            try:
                self.on_line(line, "rx")
            except Exception:
                pass

        if resp.is_ack:
            with self._cond:
                if self._pending:
                    item = self._pending.popleft()
                    self._pending_bytes -= item.length
                    if item.is_job:
                        self.progress.acked += 1
                        if resp.kind == "error":
                            msg = f"Dòng {self.progress.acked}: {resp.message_vi} -> {item.line}"
                            self.progress.errors.append(msg)
                            self._emit_event("error", msg)
                            # lỗi cú pháp giữa chừng: dừng ngay cho an toàn
                            self._job_lines = []
                            self._job_index = 0
                            self.progress.running = False
                            self.progress.finished_at = time.monotonic()
                        elif (self.progress.acked >= self.progress.total
                              and self._job_index >= len(self._job_lines)
                              and self.progress.running):
                            self.progress.running = False
                            self.progress.finished_at = time.monotonic()
                            self._emit_event(
                                "job_done",
                                f"Hoàn tất {self.progress.total} dòng trong "
                                f"{self.progress.elapsed:.1f}s",
                            )
                self._cond.notify_all()
            if self.progress.total:
                self._notify_progress()
            return

        if resp.kind == "alarm":
            self._emit_event("alarm", resp.message_vi)
            with self._cond:
                self._job_lines = []
                self._job_index = 0
                self.progress.running = False
                self.progress.finished_at = time.monotonic()
                self._cond.notify_all()
            self._notify_progress()
        elif resp.kind == "probe":
            result = proto.parse_probe(resp.text, self.profile.letters)
            if result is not None:
                with self._cond:
                    self._probe_result = result
                    self._cond.notify_all()
            self._emit_event("message", resp.text)
        elif resp.kind in ("welcome", "message"):
            if resp.kind == "welcome" or "VER" in resp.text:
                self.firmware = resp.text
            self._adopt_options(resp.text)
            self._emit_event("message", resp.text)

    def _adopt_options(self, text: str) -> None:
        """Dùng cỡ bộ đệm nhận **thật** do máy tự khai trong dòng ``[OPT:...]``.

        Hồ sơ máy chỉ ghi một con số dè dặt (127, an toàn cho cả Grbl gốc).
        FluidNC thường có bộ đệm lớn hơn nhiều; biết số thật thì phần nạp lệnh
        đếm ký tự giữ được bộ đệm gần đầy đúng mức, planner nhìn trước xa hơn.
        Chỉ nới ra, không bao giờ thu nhỏ hơn hồ sơ đã khai.
        """
        opts = proto.parse_options(text)
        if not opts:
            return
        blocks, buffer = opts
        conn = self.profile.connection
        if buffer > conn.rx_buffer:
            old = conn.rx_buffer
            conn.rx_buffer = buffer
            self._emit_event(
                "info",
                f"Máy khai bộ đệm nhận {buffer} byte và {blocks} block planner "
                f"(hồ sơ ghi {old}) - đã dùng theo số máy báo."
            )

    def _poll_loop(self) -> None:
        interval = max(0.05, self.profile.connection.poll_interval)
        while self._running:
            self.send_realtime(proto.RT_STATUS)
            time.sleep(interval)

    # ==================================================================
    def _emit_event(self, kind: str, text: str) -> None:
        if self.on_event:
            try:
                self.on_event(kind, text)
            except Exception:
                pass

    def _notify_progress(self) -> None:
        if self.on_progress:
            try:
                self.on_progress(self.progress)
            except Exception:
                pass

    # ==================================================================
    def wait_idle(self, timeout: float = 60.0) -> bool:
        """Chờ tới khi máy chạy xong (dùng cho kịch bản tự động / kiểm thử)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.progress.running and not self._cmd_queue and not self._pending:
                st = self.status
                if st is None or not st.is_moving:
                    return True
            time.sleep(0.02)
        return False
