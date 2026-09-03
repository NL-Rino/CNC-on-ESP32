"""Bộ đọc **G-code phẳng hai trục** để cuốn lên mặt phôi.

Ý tưởng: ông cứ dùng CAM quen tay (Fusion, SheetCam, LibreCAD, Inkscape...)
vẽ biên dạng **trên mặt phẳng** rồi xuất G-code 2 trục như cắt tôn tấm.  Phần
mềm này đọc lại, coi ``X`` là chiều dọc phôi và ``Y`` là chiều theo chu vi,
cuốn biên dạng lên ống rồi **áp toàn bộ xử lý bốn trục đã có**: bù bề rộng
mạch cắt, vào/ra dao, xoay góc ống hộp, bù tốc độ tổng hợp.

Nhờ vậy không cần CAM nào biết về máy cắt ống - chỉ cần nó vẽ được hình phẳng.

Đọc được: ``G0/G1`` (thẳng), ``G2/G3`` (cung, cả kiểu I/J lẫn kiểu R),
``G90/G91`` (tuyệt đối/tương đối), ``G20/G21`` (inch/mm).  Các đoạn chạy nhanh
``G0`` được dùng làm ranh giới tách biên dạng, và không bị coi là đường cắt.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence, Tuple

from .common import Curve2D, ImportError_, Point, dedupe

_WORD = re.compile(r"([A-Za-z])\s*([-+]?[0-9]*\.?[0-9]+)")


def _strip_comment(line: str) -> str:
    out, depth = [], 0
    for ch in line:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            if ch == ";":
                break
            out.append(ch)
    return "".join(out)


def _arc(p0: Point, p1: Point, centre: Point, ccw: bool,
         tolerance: float) -> List[Point]:
    """Cung tròn giữa hai điểm quanh một tâm -> chuỗi điểm theo dung sai."""
    cx, cy = centre
    r = math.dist(p0, centre)
    if r <= 1e-9:
        return [p1]
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    sweep = a1 - a0
    if ccw:
        while sweep <= 1e-12:
            sweep += 2 * math.pi
    else:
        while sweep >= -1e-12:
            sweep -= 2 * math.pi
    ratio = max(-1.0, min(1.0, 1.0 - tolerance / r))
    step = 2 * math.acos(ratio) if r > tolerance else math.pi / 6
    n = max(2, int(math.ceil(abs(sweep) / max(step, 1e-6))))
    return [(cx + r * math.cos(a0 + sweep * i / n),
             cy + r * math.sin(a0 + sweep * i / n)) for i in range(1, n + 1)]


def parse(text: str, tolerance: float = 0.05,
          keep_rapids: bool = False) -> List[Curve2D]:
    """Đọc G-code phẳng, trả về từng đường cắt (đoạn chạy nhanh dùng để tách)."""
    curves: List[Curve2D] = []
    cur: List[Point] = []
    pos: Point = (0.0, 0.0)
    absolute = True
    unit = 1.0
    motion = 0
    seen_motion = False

    def flush() -> None:
        nonlocal cur
        pts = dedupe(cur)
        if len(pts) >= 2:
            closed = math.dist(pts[0], pts[-1]) <= max(tolerance, 1e-6)
            curves.append(Curve2D(pts, closed, "gcode"))
        cur = []

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        words = [(w.group(1).upper(), float(w.group(2)))
                 for w in _WORD.finditer(line)]
        if not words:
            continue
        target = {"X": None, "Y": None, "I": None, "J": None, "R": None}
        moved = False
        for letter, value in words:
            if letter == "G":
                g = int(round(value))
                if g in (0, 1, 2, 3):
                    motion = g
                    seen_motion = True
                elif g == 90:
                    absolute = True
                elif g == 91:
                    absolute = False
                elif g == 20:
                    unit = 25.4
                elif g == 21:
                    unit = 1.0
            elif letter in target:
                target[letter] = value * unit
                if letter in ("X", "Y"):
                    moved = True
        if not moved or not seen_motion:
            continue

        nx = pos[0] if target["X"] is None else (
            target["X"] if absolute else pos[0] + target["X"])
        ny = pos[1] if target["Y"] is None else (
            target["Y"] if absolute else pos[1] + target["Y"])
        nxt = (nx, ny)

        if motion == 0:                      # chạy nhanh -> ngắt biên dạng
            flush()
            if keep_rapids:
                curves.append(Curve2D([pos, nxt], False, "rapid", rapid=True))
            pos = nxt
            continue

        if not cur:
            cur = [pos]
        if motion == 1:
            cur.append(nxt)
        else:
            ccw = motion == 3
            if target["I"] is not None or target["J"] is not None:
                centre = (pos[0] + (target["I"] or 0.0),
                          pos[1] + (target["J"] or 0.0))
            elif target["R"] is not None:
                r = target["R"]
                mx, my = (pos[0] + nx) / 2, (pos[1] + ny) / 2
                d = math.dist(pos, nxt) / 2
                h = math.sqrt(max(0.0, r * r - d * d))
                if d > 0:
                    ux, uy = (nx - pos[0]) / (2 * d), (ny - pos[1]) / (2 * d)
                else:
                    ux, uy = 0.0, 0.0
                sign = 1.0 if (r > 0) == ccw else -1.0
                centre = (mx - uy * h * sign, my + ux * h * sign)
            else:
                cur.append(nxt)
                pos = nxt
                continue
            cur.extend(_arc(pos, nxt, centre, ccw, tolerance))
        pos = nxt
    flush()

    if not curves:
        raise ImportError_(
            "Không tìm thấy đường cắt nào trong tệp G-code. "
            "Tệp cần có các lệnh G1/G2/G3 với toạ độ X, Y."
        )
    return curves


def load(path: str, **kw) -> List[Curve2D]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse(fh.read(), **kw)
