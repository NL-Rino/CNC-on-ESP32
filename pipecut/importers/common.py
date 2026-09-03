"""Kiểu dữ liệu và tiện ích dùng chung cho các bộ nhập biên dạng.

Mọi bộ nhập (DXF, SVG, G-code phẳng, lưới 3D) đều quy về cùng một thứ: danh
sách **đường cong 2D** trên mặt phẳng.  Sau đó lớp trên cuốn chúng lên mặt phôi
và đưa vào đúng dây chuyền xử lý đã có (bù kerf, vào/ra dao, xoay góc ống hộp,
bù tốc độ bốn trục) - nhờ vậy biên dạng nhập từ đâu cũng được xử lý y như biên
dạng do phần mềm tự sinh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


class ImportError_(ValueError):
    """Tệp không đọc được hoặc không chứa biên dạng dùng được."""


@dataclass
class Curve2D:
    """Một đường cong phẳng đã được rời rạc hoá."""

    points: List[Point] = field(default_factory=list)
    closed: bool = False
    name: str = ""
    layer: str = ""
    rapid: bool = False        # True = đoạn chạy không (chỉ dùng khi nhập G-code)
    wrap: bool = False         # True = đường khép kín bằng cách vòng quanh phôi

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.points, self.points[1:]))

    def bounds(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------
# Rời rạc hoá cung tròn / ellipse / đường B-spline
# --------------------------------------------------------------------------
def arc_points(cx: float, cy: float, r: float, a0_deg: float, a1_deg: float,
               tolerance: float = 0.05, ccw: bool = True) -> List[Point]:
    """Cung tròn -> chuỗi điểm, số điểm tự chọn theo dung sai dây cung."""
    if r <= 0:
        return [(cx, cy)]
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    sweep = a1 - a0
    if ccw:
        while sweep <= 0:
            sweep += 2 * math.pi
    else:
        while sweep >= 0:
            sweep -= 2 * math.pi
    ratio = max(-1.0, min(1.0, 1.0 - tolerance / r))
    step = 2 * math.acos(ratio) if r > tolerance else math.pi / 4
    n = max(2, int(math.ceil(abs(sweep) / max(step, 1e-6))))
    return [(cx + r * math.cos(a0 + sweep * i / n),
             cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def ellipse_points(cx: float, cy: float, mx: float, my: float, ratio: float,
                   t0: float, t1: float, tolerance: float = 0.05) -> List[Point]:
    """Cung ellipse theo cách DXF mô tả: tâm + vector bán trục lớn + tỉ lệ."""
    major = math.hypot(mx, my)
    minor = major * ratio
    if major <= 0:
        return [(cx, cy)]
    rot = math.atan2(my, mx)
    sweep = t1 - t0
    while sweep <= 0:
        sweep += 2 * math.pi
    ratio_c = max(-1.0, min(1.0, 1.0 - tolerance / major))
    step = 2 * math.acos(ratio_c) if major > tolerance else math.pi / 4
    n = max(4, int(math.ceil(abs(sweep) / max(step, 1e-6))))
    out: List[Point] = []
    for i in range(n + 1):
        t = t0 + sweep * i / n
        x = major * math.cos(t)
        y = minor * math.sin(t)
        out.append((cx + x * math.cos(rot) - y * math.sin(rot),
                    cy + x * math.sin(rot) + y * math.cos(rot)))
    return out


def bspline_points(control: Sequence[Point], degree: int,
                   knots: Optional[Sequence[float]] = None,
                   samples: int = 0, closed: bool = False) -> List[Point]:
    """Đường B-spline -> chuỗi điểm, tính bằng thuật toán De Boor.

    CAD thường xuất đường cong tự do thành SPLINE; nếu chỉ nối các điểm điều
    khiển lại thì hình sẽ méo, nên phải tính đúng.
    """
    pts = list(control)
    n = len(pts)
    if n == 0:
        return []
    degree = max(1, min(degree, n - 1))
    if not knots or len(knots) != n + degree + 1:
        # nút kẹp đều: đường đi qua điểm đầu và điểm cuối
        knots = ([0.0] * (degree + 1)
                 + [i / (n - degree) for i in range(1, n - degree)]
                 + [1.0] * (degree + 1))
    knots = list(knots)
    lo, hi = knots[degree], knots[n]
    if hi <= lo:
        return pts
    if samples <= 0:
        samples = max(24, 8 * n)

    def de_boor(u: float) -> Point:
        k = degree
        while k < n and knots[k + 1] <= u:
            k += 1
        k = min(max(k, degree), n - 1)
        d = [pts[j + k - degree] for j in range(degree + 1)]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + k - degree
                den = knots[i + degree + 1 - r] - knots[i]
                a = 0.0 if den == 0 else (u - knots[i]) / den
                d[j] = ((1 - a) * d[j - 1][0] + a * d[j][0],
                        (1 - a) * d[j - 1][1] + a * d[j][1])
        return d[degree]

    out = [de_boor(lo + (hi - lo) * i / samples) for i in range(samples + 1)]
    if closed and out:
        out.append(out[0])
    return out


# --------------------------------------------------------------------------
# Ghép các đoạn rời thành đường liền
# --------------------------------------------------------------------------
def join_curves(curves: Sequence[Curve2D], tolerance: float = 0.05) -> List[Curve2D]:
    """Nối các đoạn có đầu mút trùng nhau thành đường liền mạch.

    Bản vẽ CAD hay lưu một biên dạng thành hàng chục đoạn LINE/ARC rời rạc,
    thứ tự lộn xộn.  Không ghép lại thì mỗi đoạn thành một lần mồi riêng - vừa
    xấu vừa lâu.  Ghép xong, đường nào có đầu trùng cuối thì đánh dấu khép kín.
    """
    open_list = [Curve2D(list(c.points), c.closed, c.name, c.layer, c.rapid)
                 for c in curves if len(c.points) >= 2]
    result: List[Curve2D] = []
    while open_list:
        cur = open_list.pop(0)
        if cur.closed:
            result.append(cur)
            continue
        changed = True
        while changed:
            changed = False
            for i, other in enumerate(open_list):
                if other.closed:
                    continue
                for rev_cur in (False, True):
                    for rev_oth in (False, True):
                        a = list(reversed(cur.points)) if rev_cur else cur.points
                        b = list(reversed(other.points)) if rev_oth else other.points
                        if math.dist(a[-1], b[0]) <= tolerance:
                            cur.points = a + b[1:]
                            open_list.pop(i)
                            changed = True
                            break
                    if changed:
                        break
                if changed:
                    break
        if len(cur.points) > 2 and math.dist(cur.points[0], cur.points[-1]) <= tolerance:
            cur.points[-1] = cur.points[0]
            cur.closed = True
        result.append(cur)
    return result


def dedupe(points: Sequence[Point], tolerance: float = 1e-7) -> List[Point]:
    out: List[Point] = []
    for p in points:
        if not out or math.dist(out[-1], p) > tolerance:
            out.append(p)
    return out


def transform(curves: Sequence[Curve2D], scale: float = 1.0,
              dx: float = 0.0, dy: float = 0.0,
              rotate_deg: float = 0.0, mirror_y: bool = False) -> List[Curve2D]:
    """Đổi tỉ lệ, xoay, lật và dịch toàn bộ biên dạng."""
    a = math.radians(rotate_deg)
    ca, sa = math.cos(a), math.sin(a)
    out: List[Curve2D] = []
    for c in curves:
        pts: List[Point] = []
        for x, y in c.points:
            x *= scale
            y *= scale * (-1.0 if mirror_y else 1.0)
            pts.append((x * ca - y * sa + dx, x * sa + y * ca + dy))
        out.append(Curve2D(pts, c.closed, c.name, c.layer, c.rapid))
    return out


def summary(curves: Sequence[Curve2D]) -> str:
    if not curves:
        return "không có biên dạng nào"
    total = sum(c.length for c in curves)
    closed = sum(1 for c in curves if c.closed)
    xs = [p[0] for c in curves for p in c.points]
    ys = [p[1] for c in curves for p in c.points]
    return (f"{len(curves)} đường ({closed} khép kín) · tổng {total:.1f} mm · "
            f"khổ {max(xs) - min(xs):.1f} × {max(ys) - min(ys):.1f} mm")
