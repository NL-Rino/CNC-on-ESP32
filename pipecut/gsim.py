"""Diễn giải G-code thành chuyển động theo thời gian để mô phỏng.

Khác với `simulator.py` (giả lập *thiết bị* FluidNC để kiểm thử giao thức),
module này chỉ quan tâm tới **hình học và thời gian**: đọc chương trình rồi
trả lời câu hỏi "tại giây thứ t, bốn trục đang ở đâu, nguồn cắt bật hay tắt".

Nhờ vậy tab Mô phỏng có thể chạy, tạm dừng, tua tới lui và đổi tốc độ mà
không cần kết nối máy.

Mô hình thời gian là *tam giác vận tốc phẳng* (chạy đều theo F, không mô hình
hoá gia tốc), nên thời gian hiển thị là cận dưới - máy thật luôn lâu hơn một
chút vì phải tăng/giảm tốc.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import MachineProfile, ROLE_ALONG, ROLE_CROSS, ROLE_RADIAL, ROLE_ROTARY
from .gcode import strip_gcode_comment

AxisValues = Dict[str, float]


@dataclass
class SimMove:
    """Một đoạn chuyển động đã biết thời điểm bắt đầu và thời lượng."""

    t0: float
    duration: float
    start: AxisValues
    end: AxisValues
    rapid: bool = False
    torch: bool = False       # nguồn cắt có đang bật trong đoạn này không
    dwell: bool = False
    line: int = 0             # số thứ tự dòng trong chương trình (đếm từ 1)
    feed: float = 0.0

    @property
    def t1(self) -> float:
        return self.t0 + self.duration


@dataclass
class SimState:
    """Trạng thái máy tại một thời điểm."""

    time: float = 0.0
    axes: AxisValues = field(default_factory=dict)
    torch: bool = False
    line: int = 0
    feed: float = 0.0
    rapid: bool = False


@dataclass
class TracePoint:
    """Một điểm vết cắt, ghi theo **toạ độ trên phôi** nên nằm yên khi phôi
    trượt và xoay.

    ``v`` là vị trí tính theo chu vi tiết diện (mm) - dùng được cho cả ống tròn
    lẫn ống hộp, khác với góc quay của máy.
    """

    time: float
    x: float          # mm dọc theo phôi, tính từ gốc chi tiết
    v: float          # mm theo chu vi tiết diện
    start: bool = False   # True = mở đầu một lượt cắt mới (nhấc dao trước đó)


class Playback:
    """Chương trình G-code đã được "trải" ra theo trục thời gian."""

    def __init__(self, profile: MachineProfile, lines: Sequence[str],
                 trace_step: float = 0.6):
        self.profile = profile
        self.moves: List[SimMove] = []
        self.trace: List[TracePoint] = []
        self._starts: List[float] = []
        self.duration = 0.0
        self.warnings: List[str] = []
        self._build(lines, trace_step)

    # ------------------------------------------------------------------
    def _build(self, lines: Sequence[str], trace_step: float) -> None:
        pf = self.profile
        letters = set(pf.letters)
        pos: AxisValues = {c: 0.0 for c in pf.letters}
        feed = 0.0
        rapid_mode = True
        absolute = True
        torch = False
        t = 0.0
        cutting = False          # lượt cắt trước có liền mạch với đoạn này không
        section = pf.pipe.section()
        along = pf.letter(ROLE_ALONG)
        rotary = pf.letter(ROLE_ROTARY)
        cross = pf.letter(ROLE_CROSS)

        for index, raw in enumerate(lines, start=1):
            text = strip_gcode_comment(raw)
            if not text:
                continue
            words = _parse_words(text)
            if not words:
                continue
            dwell_time = 0.0
            saw_dwell = False
            target = dict(pos)
            moved = False
            for letter, value in words:
                if letter == "G":
                    code = int(round(value * 10))
                    if code == 0:
                        rapid_mode = True
                    elif code == 10:
                        rapid_mode = False
                    elif code == 40:
                        saw_dwell = True
                    elif code == 900:
                        absolute = True
                    elif code == 910:
                        absolute = False
                elif letter == "M":
                    code = int(round(value))
                    if code in (3, 4):
                        torch = True
                    elif code in (5, 2, 30):
                        torch = False
                elif letter == "F":
                    feed = max(1.0, value)
                elif letter == "P" and saw_dwell:
                    dwell_time = max(0.0, value)
                elif letter in letters:
                    target[letter] = value if absolute else pos.get(letter, 0.0) + value
                    moved = True

            if saw_dwell and dwell_time > 0:
                self.moves.append(SimMove(t, dwell_time, dict(pos), dict(pos),
                                          rapid=False, torch=torch, dwell=True,
                                          line=index))
                t += dwell_time
                continue
            if not moved:
                continue

            dist = math.sqrt(sum((target[c] - pos.get(c, 0.0)) ** 2 for c in letters))
            if dist < 1e-9:
                continue
            duration = (self._rapid_time(pos, target) if rapid_mode
                        else dist / max(feed, 1.0) * 60.0)
            move = SimMove(t, duration, dict(pos), dict(target), rapid=rapid_mode,
                           torch=torch, line=index, feed=feed)
            self.moves.append(move)

            # ghi vết cắt (chỉ khi nguồn cắt bật và đang chạy cắt)
            is_cut = torch and not rapid_mode and along and rotary
            if is_cut:
                self._add_trace(move, along, rotary, cross, section, trace_step,
                                new_run=not cutting)
            cutting = bool(is_cut)
            t += duration
            pos = target

        self.duration = t
        self._starts = [m.t0 for m in self.moves]

    # ------------------------------------------------------------------
    def _rapid_time(self, a: AxisValues, b: AxisValues) -> float:
        """G0 chạy phối hợp, trục nào chậm nhất quyết định thời gian."""
        worst = 0.0
        for letter, value in b.items():
            d = abs(value - a.get(letter, 0.0))
            if d < 1e-12:
                continue
            ax = self.profile.axis_by_letter(letter)
            rate = ax.max_rate if ax and ax.max_rate > 0 else 3000.0
            worst = max(worst, d / rate * 60.0)
        return max(worst, 1e-4)

    def _add_trace(self, move: SimMove, along: str, rotary: str,
                   cross: Optional[str], section, step: float,
                   new_run: bool = False) -> None:
        """Lấy mẫu vết cắt theo toạ độ trên phôi.

        Tiết diện lo phần đổi ngược: biết góc quay và vị trí trục ngang thì suy
        ra mũi cắt đang chạm vào đâu trên chu vi - đúng cho cả ống tròn lẫn ống
        hộp (với ống hộp, cả một mặt phẳng có chung góc quay nên bắt buộc phải
        dùng thêm trục ngang).
        """
        n = max(1, int(math.ceil(_axis_dist(move.start, move.end, (along, rotary)) / step)))
        n = min(n, 400)
        for k in range(0 if new_run else 1, n + 1):
            f = k / n
            x = _lerp(move.start.get(along, 0.0), move.end.get(along, 0.0), f)
            a = _lerp(move.start.get(rotary, 0.0), move.end.get(rotary, 0.0), f)
            xc = 0.0
            if cross:
                xc = _lerp(move.start.get(cross, 0.0), move.end.get(cross, 0.0), f)
            v = section.s_of_contact(a, xc)
            self.trace.append(TracePoint(move.t0 + move.duration * f, x, v,
                                         start=(new_run and k == 0)))

    # ------------------------------------------------------------------
    def state_at(self, t: float) -> SimState:
        """Trạng thái máy tại giây thứ ``t`` (nội suy tuyến tính trong đoạn)."""
        if not self.moves:
            return SimState(time=0.0, axes={c: 0.0 for c in self.profile.letters})
        t = max(0.0, min(t, self.duration))
        i = max(0, bisect_right(self._starts, t) - 1)
        m = self.moves[i]
        f = 0.0 if m.duration <= 1e-9 else max(0.0, min(1.0, (t - m.t0) / m.duration))
        axes = {c: _lerp(m.start.get(c, 0.0), m.end.get(c, 0.0), f) for c in m.end}
        return SimState(time=t, axes=axes, torch=m.torch, line=m.line,
                        feed=0.0 if m.rapid or m.dwell else m.feed, rapid=m.rapid)

    def trace_until(self, t: float) -> List[TracePoint]:
        """Phần vết cắt đã hình thành tính tới thời điểm ``t``."""
        if not self.trace:
            return []
        lo, hi = 0, len(self.trace)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.trace[mid].time <= t:
                lo = mid + 1
            else:
                hi = mid
        return self.trace[:lo]

    def axis_range(self, letter: str) -> Tuple[float, float]:
        """Khoảng giá trị mà một trục đi qua trong cả chương trình."""
        vals: List[float] = []
        for m in self.moves:
            for d in (m.start, m.end):
                v = d.get(letter)
                if v is not None:
                    vals.append(v)
        return (min(vals), max(vals)) if vals else (0.0, 0.0)

    @property
    def cut_time(self) -> float:
        return sum(m.duration for m in self.moves if m.torch and not m.rapid)

    @property
    def rapid_time(self) -> float:
        return sum(m.duration for m in self.moves if m.rapid)

    def summary(self) -> str:
        return (f"{len(self.moves)} đoạn · tổng {_hms(self.duration)} "
                f"(cắt {_hms(self.cut_time)}, chạy không {_hms(self.rapid_time)})")


# ----------------------------------------------------------------------
def _parse_words(line: str) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    s = line.upper()
    i = 0
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


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _axis_dist(a: AxisValues, b: AxisValues, letters: Sequence[str]) -> float:
    return math.sqrt(sum((b.get(c, 0.0) - a.get(c, 0.0)) ** 2 for c in letters))


def _hms(seconds: float) -> str:
    s = int(round(seconds))
    if s >= 3600:
        return f"{s // 3600}h{s % 3600 // 60:02d}m"
    return f"{s // 60}m{s % 60:02d}s"
