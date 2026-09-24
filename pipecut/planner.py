"""Ước lượng thời gian chạy **đúng như FluidNC lập kế hoạch chuyển động**.

Mô hình trong :mod:`pipecut.gsim` coi máy chạy đều theo F, không tăng giảm tốc.
Đủ để vẽ mô phỏng, nhưng nó *không thấy* đúng cái làm máy thật chậm: mỗi lần
dừng hẳn rồi khởi động lại.  Nhấc Z, chạy ngang, hạ Z thành ba lệnh riêng thì
máy phải dừng hẳn ở hai chỗ; mỗi góc gấp trên đường cắt cũng phải hãm lại.
Tối ưu chuyển động mà không đo được mấy cái đó thì chỉ là đoán.

Module này chạy lại đúng thuật toán lập kế hoạch của Grbl/FluidNC:

* **Tốc độ danh định** của mỗi khối: F (hoặc tốc độ chạy nhanh với G0), nhưng
  không trục nào được vượt ``max_rate`` của nó.
* **Gia tốc** của khối: trục nào yếu nhất theo đúng hướng đi quyết định.
* **Tốc độ qua điểm nối** giữa hai khối theo công thức *junction deviation*:
  góc càng gấp thì càng phải chậm, quay ngược đầu thì phải dừng hẳn.
* **Nhìn trước có hạn**: bộ đệm chỉ chứa ``planner_blocks`` khối, khối cuối
  trong bộ đệm luôn phải dừng được - nên chuỗi đoạn quá ngắn tự làm máy chậm.
* **Lệnh đồng bộ** (M3/M5, G4, G10...) bắt bộ đệm chạy cạn: dừng hẳn.

Mỗi khối được xếp vào một loại chuyển động (cắt, chạy không, nhấc/hạ, ...)
để biết thời gian đang tiêu vào đâu.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import MachineProfile, ROLE_RADIAL
from .gcode import strip_gcode_comment

CATEGORIES: Tuple[str, ...] = ("cut", "travel", "lift", "plunge", "index", "dwell")
CATEGORY_LABELS: Dict[str, str] = {
    "cut": "cắt",
    "travel": "chạy không",
    "lift": "nhấc/hạ mỏ",
    "plunge": "hạ mỏ chậm",
    "index": "xoay/đi chậm không cắt",
    "dwell": "chờ (mồi, tắt)",
}

# Lệnh làm bộ đệm chạy cạn rồi mới làm tiếp (Grbl: protocol_buffer_synchronize)
_SYNC_M = {3, 4, 5, 7, 8, 9, 62, 63, 64, 65}
_SYNC_G = {4, 10, 28, 30, 92, 53}


@dataclass
class Block:
    """Một đoạn chuyển động thẳng trong không gian trục (mm và độ như nhau)."""

    line: int
    length: float
    unit: Dict[str, float]       # véc-tơ đơn vị hướng đi
    v_nom: float                 # mm/s
    accel: float                 # mm/s^2
    category: str
    sync_before: bool = False    # có lệnh đồng bộ ngay trước khối này
    v_junction: float = 0.0      # tốc độ tối đa được phép ở điểm vào (mm/s)
    v_entry: float = 0.0
    v_exit: float = 0.0
    time: float = 0.0


@dataclass
class PlanResult:
    """Kết quả lập kế hoạch cho cả chương trình."""

    total: float = 0.0
    by_category: Dict[str, float] = field(default_factory=lambda: {c: 0.0 for c in CATEGORIES})
    distance: Dict[str, float] = field(default_factory=lambda: {c: 0.0 for c in CATEGORIES})
    blocks: int = 0
    syncs: int = 0               # số lần bộ đệm bị bắt chạy cạn
    full_stops: int = 0          # số điểm nối phải dừng hẳn (không tính đồng bộ)
    nominal: float = 0.0         # thời gian nếu chạy đều theo F, không tăng giảm tốc
    line_times: Dict[int, float] = field(default_factory=dict)   # số dòng -> giây

    @property
    def accel_overhead(self) -> float:
        """Thời gian mất thêm vì phải tăng/giảm tốc so với chạy đều."""
        return max(0.0, self.total - self.nominal - self.by_category.get("dwell", 0.0))

    def share(self, category: str) -> float:
        return self.by_category.get(category, 0.0) / self.total if self.total > 0 else 0.0

    def summary(self) -> str:
        parts = [f"{CATEGORY_LABELS[c]} {self.by_category[c]:.1f}s"
                 for c in CATEGORIES if self.by_category[c] > 0.05]
        return (f"tổng {self.total:.1f}s ({', '.join(parts)}); "
                f"{self.full_stops} lần dừng hẳn giữa chừng, {self.syncs} lần đồng bộ")


# ----------------------------------------------------------------------
# Đọc chương trình thành các khối
# ----------------------------------------------------------------------
def _words(text: str) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    s = text.upper()
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if "A" <= ch <= "Z":
            j = i + 1
            while j < n and (s[j].isdigit() or s[j] in "+-."):
                j += 1
            try:
                out.append((ch, float(s[i + 1:j])))
            except ValueError:
                pass
            i = j
        else:
            i += 1
    return out


def _limit_by_axes(limits: Dict[str, float], unit: Dict[str, float]) -> float:
    """Giống ``limit_value_by_axis_maximum`` của Grbl."""
    best = float("inf")
    for letter, u in unit.items():
        if abs(u) > 1e-12:
            lim = limits.get(letter, 0.0)
            if lim > 0:
                best = min(best, lim / abs(u))
    return best if best < float("inf") else 0.0


def read_blocks(profile: MachineProfile, lines: Sequence[str]) -> List[Block]:
    letters = [c for c in profile.letters]
    rates = {}      # mm/s
    accels = {}     # mm/s^2
    for c in letters:
        ax = profile.axis_by_letter(c)
        rates[c] = (ax.max_rate if ax and ax.max_rate > 0 else 3000.0) / 60.0
        accels[c] = ax.accel if ax and ax.accel > 0 else 200.0
    radial = (profile.letter(ROLE_RADIAL) or "Z").upper()

    # Lúc bắt đầu, mỏ đứng ở gốc chi tiết - đúng chỗ vừa "đặt gốc tại đây".
    # Cùng giả định với mô phỏng (gsim) và bộ sắp thứ tự cắt (jobs).
    pos = {c: 0.0 for c in letters}
    rapid, absolute, torch = True, True, False
    feed = 0.0
    sync_pending = True    # đầu chương trình: máy đứng yên
    blocks: List[Block] = []

    for index, raw in enumerate(lines, start=1):
        text = strip_gcode_comment(raw)
        if not text:
            continue
        words = _words(text)
        target = dict(pos)
        moved = False
        dwell = None
        is_dwell = False
        for letter, value in words:
            if letter == "G":
                code = int(round(value * 10))
                if code == 0:
                    rapid = True
                elif code == 10:
                    rapid = False
                elif code == 900:
                    absolute = True
                elif code == 910:
                    absolute = False
                elif code == 40:
                    is_dwell = True
                if code % 10 == 0 and code // 10 in _SYNC_G:
                    sync_pending = True
            elif letter == "M":
                code = int(round(value))
                if code in (3, 4):
                    torch = True
                elif code in (5, 2, 30):
                    torch = False
                if code in _SYNC_M:
                    sync_pending = True
            elif letter == "F":
                feed = max(1.0, value)
            elif letter == "P" and is_dwell:
                dwell = max(0.0, value)
            elif letter in pos:
                target[letter] = value if absolute else pos[letter] + value
                moved = True

        if is_dwell:
            if dwell:
                blocks.append(Block(index, 0.0, {}, 0.0, 1.0, "dwell",
                                    sync_before=True, time=dwell))
            sync_pending = True
            continue
        if not moved:
            continue
        delta = {c: target[c] - pos[c] for c in letters if abs(target[c] - pos[c]) > 1e-9}
        length = math.sqrt(sum(d * d for d in delta.values()))
        if length < 1e-9:
            pos = target
            continue
        unit = {c: d / length for c, d in delta.items()}
        rapid_rate = _limit_by_axes(rates, unit)
        v_nom = rapid_rate if rapid else min(feed / 60.0, rapid_rate)
        only_z = set(delta) == {radial}
        if rapid:
            category = "lift" if only_z else "travel"
        elif only_z:
            category = "plunge"      # hạ từ độ cao mồi xuống độ cao cắt
        elif torch:
            category = "cut"
        else:
            category = "index"
        blocks.append(Block(index, length, unit, max(v_nom, 1e-6),
                            max(_limit_by_axes(accels, unit), 1e-6), category,
                            sync_before=sync_pending))
        sync_pending = False
        pos = target
    _junctions(blocks, profile, accels)
    return blocks


def _junctions(blocks: List[Block], profile: MachineProfile, accels: Dict[str, float]) -> None:
    """Tốc độ tối đa tại điểm vào mỗi khối - công thức junction deviation."""
    jd = max(1e-6, float(getattr(profile.motion, "junction_deviation", 0.01)))
    prev: Optional[Block] = None
    for b in blocks:
        if b.category == "dwell":
            prev = None
            continue
        if prev is None or b.sync_before:
            b.v_junction = 0.0
        else:
            letters = set(b.unit) | set(prev.unit)
            cos_t = -sum(prev.unit.get(c, 0.0) * b.unit.get(c, 0.0) for c in letters)
            if cos_t > 0.999999:            # quay ngược đầu: phải dừng hẳn
                v2 = 0.0
            elif cos_t < -0.999999:         # thẳng hàng: không giới hạn
                v2 = float("inf")
            else:
                ju = {c: b.unit.get(c, 0.0) - prev.unit.get(c, 0.0) for c in letters}
                n = math.sqrt(sum(v * v for v in ju.values()))
                ju = {c: v / n for c, v in ju.items()} if n > 1e-12 else ju
                a_j = _limit_by_axes(accels, ju) or b.accel
                s = math.sqrt(0.5 * (1.0 - cos_t))
                v2 = a_j * jd * s / (1.0 - s)
            b.v_junction = math.sqrt(min(v2, b.v_nom ** 2, prev.v_nom ** 2))
        prev = b


def _trapezoid(length: float, v0: float, v1: float, vc: float, a: float) -> float:
    if length <= 0:
        return 0.0
    d_acc = max(0.0, (vc * vc - v0 * v0) / (2 * a))
    d_dec = max(0.0, (vc * vc - v1 * v1) / (2 * a))
    if d_acc + d_dec <= length:
        return (vc - v0) / a + (vc - v1) / a + (length - d_acc - d_dec) / vc
    vp = math.sqrt(max(0.0, (2 * a * length + v0 * v0 + v1 * v1) / 2.0))
    vp = max(vp, v0, v1)
    return max(0.0, (vp - v0) / a + (vp - v1) / a)


def plan(profile: MachineProfile, lines: Sequence[str]) -> PlanResult:
    """Lập kế hoạch cả chương trình, trả về thời gian và phân loại."""
    blocks = read_blocks(profile, lines)
    res = PlanResult()
    depth = max(2, int(getattr(profile.motion, "planner_blocks", 32)) - 1)

    # Chia thành các đoạn liền mạch giữa hai lần đồng bộ.
    runs: List[List[Block]] = []
    cur: List[Block] = []
    for b in blocks:
        if b.category == "dwell":
            if cur:
                runs.append(cur)
                cur = []
            res.by_category["dwell"] += b.time
            res.total += b.time
            res.line_times[b.line] = res.line_times.get(b.line, 0.0) + b.time
            continue
        if b.sync_before and cur:
            runs.append(cur)
            cur = []
        cur.append(b)
    if cur:
        runs.append(cur)
    res.syncs = len(runs)

    for run in runs:
        n = len(run)
        # quãng hãm có được trong phần còn lại của bộ đệm sau mỗi khối
        room = [0.0] * n
        pref = [0.0] * (n + 1)
        for i, b in enumerate(run):
            pref[i + 1] = pref[i] + 2.0 * b.accel * b.length
        for i in range(n):
            j = min(n, i + depth)
            room[i] = pref[j] - pref[i + 1]
        # lượt ngược: phải hãm kịp trước mọi giới hạn phía trước
        v_next = 0.0
        exits = [0.0] * n
        for i in range(n - 1, -1, -1):
            b = run[i]
            exits[i] = min(v_next, math.sqrt(max(0.0, room[i])))
            v_next = min(b.v_junction,
                         math.sqrt(exits[i] ** 2 + 2.0 * b.accel * b.length))
        # lượt xuôi: không tăng tốc nhanh hơn gia tốc cho phép
        v_in = 0.0
        for i, b in enumerate(run):
            b.v_entry = min(v_in, b.v_junction) if i else 0.0
            b.v_exit = min(exits[i], math.sqrt(b.v_entry ** 2 + 2.0 * b.accel * b.length), b.v_nom)
            b.time = _trapezoid(b.length, b.v_entry, b.v_exit, b.v_nom, b.accel)
            v_in = b.v_exit
            res.by_category[b.category] += b.time
            res.line_times[b.line] = res.line_times.get(b.line, 0.0) + b.time
            res.distance[b.category] += b.length
            res.total += b.time
            res.nominal += b.length / b.v_nom
            res.blocks += 1
            if i and b.v_entry < 0.05 * min(b.v_nom, run[i - 1].v_nom):
                res.full_stops += 1
    return res
