"""Cấu trúc dữ liệu đường chạy dao.

``Contour`` giữ đường cắt ở dạng **toạ độ trải phẳng** (u, v):

* ``u`` - dọc trục ống (mm), sẽ thành trục X của máy.
* ``v`` - độ dài cung theo chu vi (mm), sẽ thành trục A (độ) khi chia cho R.

Giữ nguyên dạng trải phẳng cho tới bước cuối cùng giúp mọi phép xử lý hình
học (bù kerf, bo góc, rút gọn, vào/ra dao) đều đúng theo khoảng cách thật
trên bề mặt ống.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import geom2d as g

Point = Tuple[float, float]

# Chế độ điều khiển trục vát
BEVEL_NONE = "none"
BEVEL_FOLLOW = "follow"      # nghiêng theo độ dốc đường cắt (mặt cắt phẳng)
BEVEL_CONSTANT = "constant"  # góc vát cố định (vát mép hàn)


@dataclass
class Contour:
    """Một đường cắt/vạch dấu trên mặt ống, toạ độ trải phẳng."""

    points: List[Point] = field(default_factory=list)
    closed: bool = False        # khép kín trong mặt phẳng trải (lỗ, rãnh)
    wrap: bool = False          # quấn trọn vòng chu vi (cắt đứt, cắt vát, miệng cá)
    name: str = "contour"
    kind: str = "cut"           # cut | mark
    bevel_mode: str = BEVEL_NONE
    bevel_value: float = 0.0    # dùng cho BEVEL_CONSTANT (độ)
    kerf_side: str = "auto"     # auto | none | left | right
    meta: Dict[str, object] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return g.polyline_length(self.points)

    def bounds(self) -> Tuple[float, float, float, float]:
        return g.bbox(self.points)

    def copy_with(self, points: Sequence[Point]) -> "Contour":
        return Contour(
            points=list(points),
            closed=self.closed,
            wrap=self.wrap,
            name=self.name,
            kind=self.kind,
            bevel_mode=self.bevel_mode,
            bevel_value=self.bevel_value,
            kerf_side=self.kerf_side,
            meta=dict(self.meta),
        )


@dataclass
class CutPoint:
    """Điểm đã cuốn lên ống, sẵn sàng đưa vào động học máy."""

    x: float             # mm dọc trục ống
    theta: float         # ĐỘ, đã "gỡ cuộn" (có thể vượt 360 hoặc âm)
    bevel: float = 0.0   # ĐỘ
    cross: float = 0.0   # mm (trục ngang, thường = 0)


@dataclass
class PathSegment:
    """Một đoạn đường chạy dao đã có tốc độ, dùng để sinh G-code."""

    points: List[CutPoint]
    kind: str = "cut"          # cut | mark | lead_in | lead_out
    name: str = ""
    feed: float = 0.0          # tốc độ cắt thực trên bề mặt (mm/phút)


@dataclass
class Toolpath:
    """Tập hợp các đường cắt của một công việc."""

    contours: List[Contour] = field(default_factory=list)
    radius: float = 30.0
    name: str = "job"
    meta: Dict[str, object] = field(default_factory=dict)

    def add(self, contour: Contour) -> "Toolpath":
        self.contours.append(contour)
        return self

    @property
    def total_length(self) -> float:
        return sum(c.length for c in self.contours)

    def bounds(self) -> Tuple[float, float, float, float]:
        if not self.contours:
            return (0.0, 0.0, 0.0, 0.0)
        boxes = [c.bounds() for c in self.contours]
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )


# --------------------------------------------------------------------------
# Cuốn từ mặt phẳng trải lên ống
# --------------------------------------------------------------------------
def v_to_theta(v: float, radius: float) -> float:
    """Đổi độ dài cung (mm) sang góc quay (độ)."""
    return math.degrees(v / radius) if radius > 1e-9 else 0.0


def theta_to_v(theta_deg: float, radius: float) -> float:
    return math.radians(theta_deg) * radius


def surface_point(x: float, theta_deg: float, radius: float) -> Tuple[float, float, float]:
    """Toạ độ 3D thật của một điểm trên mặt ống (dùng để vẽ và kiểm tra)."""
    a = math.radians(theta_deg)
    return (x, radius * math.sin(a), radius * math.cos(a))
