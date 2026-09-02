"""Thư viện biên dạng cắt trên ống (sinh đường cong ở mặt phẳng trải).

Quy ước chung
-------------
* Phôi ống nằm dọc trục X, quay quanh chính nó bằng trục A.
* ``u`` = toạ độ dọc ống (mm), tăng dần về phía đầu tự do.
* ``v`` = độ dài cung (mm) = R * theta; theta = 0 ở vị trí 12 giờ (ngay dưới mỏ cắt).
* Mọi hàm trả về ``Contour`` với dung sai rời rạc hoá do người gọi truyền vào.

Toán học của các biên dạng giao tuyến ống được suy ra trực tiếp từ phương
trình mặt trụ nên chính xác tuyệt đối (không dùng bảng tra hay xấp xỉ).
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

from . import geom2d as g
from .toolpath import BEVEL_CONSTANT, BEVEL_FOLLOW, BEVEL_NONE, Contour, Point


class ShapeError(ValueError):
    """Tham số biên dạng không hợp lệ về mặt hình học."""


def _sample_closed(func: Callable[[float], Point], tol: float, max_points: int) -> List[Point]:
    pts = g.adaptive_sample(func, 0.0, 2 * math.pi, tol, max_points=max_points)
    return g.close_loop(g.dedupe(pts))


# --------------------------------------------------------------------------
# 1. Cắt đứt / cắt vát góc (mặt phẳng cắt)
# --------------------------------------------------------------------------
def plane_cut(
    radius: float,
    x: float,
    angle_deg: float = 0.0,
    roll_deg: float = 0.0,
    tolerance: float = 0.05,
    bevel: bool = True,
    name: str = "cat-dut",
    max_points: int = 4000,
) -> Contour:
    """Cắt đứt ống bằng một mặt phẳng nghiêng ``angle_deg`` so với mặt cắt vuông.

    Giao của mặt phẳng với mặt trụ là một ellipse; trải phẳng ra nó thành
    hình sin thuần tuý::

        u(theta) = x + R * tan(alpha) * cos(theta - roll)

    ``angle_deg`` = 0 cho nhát cắt vuông góc, 30-45 độ cho ống nối co/cút.
    ``roll_deg`` xoay hướng vát quanh ống.
    """
    if radius <= 0:
        raise ShapeError("Bán kính ống phải > 0.")
    if abs(angle_deg) >= 89.0:
        raise ShapeError("Góc cắt vát phải nhỏ hơn 89 độ.")
    amp = radius * math.tan(math.radians(angle_deg))
    roll = math.radians(roll_deg)

    def f(t: float) -> Point:
        return (x + amp * math.cos(t - roll), radius * t)

    pts = g.adaptive_sample(f, 0.0, 2 * math.pi, tolerance, max_points=max_points)
    return Contour(
        points=pts,
        closed=False,
        wrap=True,
        name=name,
        bevel_mode=BEVEL_FOLLOW if (bevel and abs(angle_deg) > 1e-6) else BEVEL_NONE,
        meta={"shape": "plane_cut", "angle": angle_deg, "x": x},
    )


# --------------------------------------------------------------------------
# 2. Miệng cá / yên ngựa (ống nhánh cắt để ôm vào ống chính)
# --------------------------------------------------------------------------
def saddle_cut(
    radius: float,
    main_radius: float,
    angle_deg: float = 90.0,
    offset: float = 0.0,
    x_ref: float = 0.0,
    reference: str = "heel",
    roll_deg: float = 0.0,
    tolerance: float = 0.05,
    bevel: bool = True,
    name: str = "mieng-ca",
    max_points: int = 6000,
) -> Contour:
    """Cắt "miệng cá" (fishmouth/cope) trên ống nhánh để ôm vào ống chính.

    Ống nhánh bán kính ``r`` (chính là phôi đang gá), ống chính bán kính ``R``,
    hai trục cắt nhau một góc ``beta`` và lệch tâm ``e``.  Điểm trên mặt ống
    nhánh ở góc ``theta`` và cách trục ống chính một đoạn ``t`` dọc theo trục
    nhánh::

        P = (t*cos b - r*cos th*sin b,  r*sin th + e,  t*sin b + r*cos th*cos b)

    Thay vào phương trình ống chính ``P_y^2 + P_z^2 = R^2`` rồi giải ra ``t``::

        t(th) = [ sqrt(R^2 - (r*sin th + e)^2) - r*cos th*cos b ] / sin b

    Toạ độ dọc ống nhánh: ``u = x_axis - t`` (t càng lớn càng ăn sâu vào phôi).

    ``reference``:
      * ``heel``  - ``x_ref`` là vị trí điểm còn dài nhất (gót yên ngựa);
      * ``toe``   - ``x_ref`` là vị trí điểm ăn sâu nhất (đáy miệng cá);
      * ``axis``  - ``x_ref`` là giao điểm hai đường tâm ống.
    """
    r = radius
    R = main_radius
    if r <= 0 or R <= 0:
        raise ShapeError("Bán kính ống phải > 0.")
    if r > R + 1e-9:
        raise ShapeError(
            f"Ống nhánh (D={2*r:.1f}) lớn hơn ống chính (D={2*R:.1f}) - không tạo được miệng cá."
        )
    beta = math.radians(angle_deg)
    if abs(math.sin(beta)) < 1e-6:
        raise ShapeError("Góc giữa hai ống phải khác 0 và 180 độ.")
    if abs(offset) + r > R:
        raise ShapeError(
            f"Lệch tâm {offset:.1f} mm quá lớn: ống nhánh vượt ra ngoài ống chính."
        )
    sb, cb = math.sin(beta), math.cos(beta)
    roll = math.radians(roll_deg)

    def t_of(th: float) -> float:
        y = r * math.sin(th) + offset
        disc = R * R - y * y
        if disc < 0:
            raise ShapeError("Biên dạng miệng cá không tồn tại với bộ tham số này.")
        return (math.sqrt(disc) - r * math.cos(th) * cb) / sb

    def f(t: float) -> Point:
        return (-t_of(t - roll), r * t)

    pts = g.adaptive_sample(f, 0.0, 2 * math.pi, tolerance, max_points=max_points)
    us = [p[0] for p in pts]
    if reference == "heel":
        shift = x_ref - max(us)
    elif reference == "toe":
        shift = x_ref - min(us)
    else:  # axis
        shift = x_ref
    pts = [(u + shift, v) for (u, v) in pts]
    depth = max(us) - min(us)
    return Contour(
        points=pts,
        closed=False,
        wrap=True,
        name=name,
        bevel_mode=BEVEL_FOLLOW if bevel else BEVEL_NONE,
        meta={
            "shape": "saddle",
            "main_radius": R,
            "angle": angle_deg,
            "offset": offset,
            "depth": depth,
        },
    )


# --------------------------------------------------------------------------
# 3. Lỗ tròn xuyên thành ống (giao tuyến ống nhánh với ống chính - phía ống chính)
# --------------------------------------------------------------------------
def pierced_hole(
    radius: float,
    hole_diameter: float,
    angle_deg: float = 90.0,
    offset: float = 0.0,
    x_center: float = 0.0,
    theta_center_deg: float = 0.0,
    tolerance: float = 0.05,
    name: str = "lo",
    max_points: int = 4000,
) -> Contour:
    """Lỗ do một ống/mũi khoan đường kính ``d`` xuyên qua thành ống.

    Đây là *vế còn lại* của bài toán giao tuyến: đường cắt nằm trên **ống
    chính** (chính là phôi).  Rút gọn hệ phương trình cho kết quả rất gọn::

        P_y = r*sin th + e
        P_z = sqrt(R^2 - P_y^2)
        P_x = (P_z*cos b - r*cos th) / sin b
        phi = asin(P_y / R)          (góc quay quanh ống)

    Với ``b = 90`` độ và ``e = 0`` ta được lỗ tròn khoan hướng tâm; với ``b``
    khác 90 độ là lỗ xiên (đầu nối chữ Y).
    """
    R = radius
    r = hole_diameter / 2.0
    if R <= 0 or r <= 0:
        raise ShapeError("Đường kính ống và lỗ phải > 0.")
    if r + abs(offset) >= R:
        raise ShapeError(
            f"Lỗ D={hole_diameter:.1f} (lệch {offset:.1f}) không nằm gọn trên ống D={2*R:.1f}."
        )
    beta = math.radians(angle_deg)
    if abs(math.sin(beta)) < 1e-6:
        raise ShapeError("Góc khoan phải khác 0 và 180 độ.")
    sb, cb = math.sin(beta), math.cos(beta)
    v_center = math.radians(theta_center_deg) * R

    def f(t: float) -> Point:
        py = r * math.sin(t) + offset
        pz = math.sqrt(max(0.0, R * R - py * py))
        px = (pz * cb - r * math.cos(t)) / sb
        phi = math.atan2(py, pz)
        return (x_center + px, v_center + R * phi)

    pts = _sample_closed(f, tolerance, max_points)
    return Contour(
        points=pts,
        closed=True,
        wrap=False,
        name=name,
        kerf_side="auto",
        meta={"shape": "hole", "diameter": hole_diameter, "angle": angle_deg},
    )


# --------------------------------------------------------------------------
# 4. Rãnh / cửa sổ chữ nhật (trải phẳng)
# --------------------------------------------------------------------------
def slot(
    radius: float,
    x_center: float,
    theta_center_deg: float,
    axial_length: float,
    arc_width: Optional[float] = None,
    angular_width_deg: Optional[float] = None,
    corner_radius: float = 0.0,
    tolerance: float = 0.05,
    name: str = "ranh",
) -> Contour:
    """Cửa sổ/rãnh chữ nhật bo góc, đo theo **kích thước thật trên bề mặt**.

    Cho đúng một trong hai: ``arc_width`` (bề rộng cung, mm) hoặc
    ``angular_width_deg`` (bề rộng theo góc quay).
    """
    if axial_length <= 0:
        raise ShapeError("Chiều dài rãnh phải > 0.")
    if arc_width is None and angular_width_deg is None:
        raise ShapeError("Cần bề rộng rãnh (arc_width hoặc angular_width_deg).")
    if arc_width is None:
        arc_width = math.radians(angular_width_deg or 0.0) * radius
    if arc_width <= 0:
        raise ShapeError("Bề rộng rãnh phải > 0.")
    if arc_width > 2 * math.pi * radius:
        raise ShapeError("Bề rộng rãnh vượt quá chu vi ống.")
    hu = axial_length / 2.0
    hv = arc_width / 2.0
    cu = x_center
    cv = math.radians(theta_center_deg) * radius
    rect = [
        (cu - hu, cv - hv),
        (cu + hu, cv - hv),
        (cu + hu, cv + hv),
        (cu - hu, cv + hv),
    ]
    rect = g.close_loop(rect)
    rmax = min(hu, hv) * 0.999
    r_c = min(corner_radius, rmax) if corner_radius > 0 else 0.0
    if r_c > 0:
        rect = g.round_corners(rect, r_c, closed=True, tolerance=tolerance)
    return Contour(
        points=rect,
        closed=True,
        wrap=False,
        name=name,
        meta={"shape": "slot", "axial_length": axial_length, "arc_width": arc_width},
    )


# --------------------------------------------------------------------------
# 5. Đường tròn "trắc địa" trên bề mặt (vạch dấu / lỗ đo theo bề mặt)
# --------------------------------------------------------------------------
def surface_circle(
    radius: float,
    x_center: float,
    theta_center_deg: float,
    diameter: float,
    tolerance: float = 0.05,
    name: str = "tron-be-mat",
) -> Contour:
    """Đường tròn đo trên bề mặt ống (khác lỗ khoan: đây là hình tròn khi trải phẳng)."""
    if diameter <= 0:
        raise ShapeError("Đường kính phải > 0.")
    if diameter > 2 * math.pi * radius:
        raise ShapeError("Đường tròn lớn hơn chu vi ống.")
    r = diameter / 2.0
    cu = x_center
    cv = math.radians(theta_center_deg) * radius

    def f(t: float) -> Point:
        return (cu + r * math.cos(t), cv + r * math.sin(t))

    return Contour(
        points=_sample_closed(f, tolerance, 3000),
        closed=True,
        wrap=False,
        name=name,
        meta={"shape": "surface_circle", "diameter": diameter},
    )


# --------------------------------------------------------------------------
# 6. Đường xoắn ốc / cắt lò xo
# --------------------------------------------------------------------------
def helix(
    radius: float,
    x_start: float,
    x_end: float,
    turns: float,
    theta_start_deg: float = 0.0,
    tolerance: float = 0.05,
    name: str = "xoan-oc",
) -> Contour:
    """Đường xoắn ốc quanh ống - cắt lò xo, ống mềm, rãnh xoắn.

    Trải phẳng ra là một đường thẳng, nên chỉ cần hai điểm; ta vẫn chia nhỏ
    để planner có nhiều block nhìn trước và giữ tốc độ ổn định.
    """
    if abs(turns) < 1e-9:
        raise ShapeError("Số vòng xoắn phải khác 0.")
    v0 = math.radians(theta_start_deg) * radius
    v1 = v0 + turns * 2 * math.pi * radius
    pts = [(x_start, v0), (x_end, v1)]
    pts = g.resample_max_step(pts, max(2.0, radius / 4.0))
    return Contour(
        points=pts,
        closed=False,
        wrap=False,
        name=name,
        meta={"shape": "helix", "turns": turns},
    )


# --------------------------------------------------------------------------
# 7. Đường thẳng dọc ống / vạch dấu
# --------------------------------------------------------------------------
def axial_line(
    radius: float,
    x_start: float,
    x_end: float,
    theta_deg: float = 0.0,
    kind: str = "cut",
    name: str = "duong-doc",
) -> Contour:
    """Đường cắt/vạch chạy dọc thân ống ở một góc quay cố định."""
    v = math.radians(theta_deg) * radius
    return Contour(
        points=[(x_start, v), (x_end, v)],
        closed=False,
        wrap=False,
        name=name,
        kind=kind,
        meta={"shape": "axial_line"},
    )


def ring_mark(
    radius: float,
    x: float,
    tolerance: float = 0.05,
    name: str = "vach-vong",
) -> Contour:
    """Vạch dấu tròn quanh ống."""
    c = plane_cut(radius, x, 0.0, tolerance=tolerance, bevel=False, name=name)
    c.kind = "mark"
    c.bevel_mode = BEVEL_NONE
    return c


# --------------------------------------------------------------------------
# 8. Biên dạng tự do (nhập từ DXF/CSV/SVG đã trải phẳng)
# --------------------------------------------------------------------------
def flat_pattern(
    radius: float,
    points: Sequence[Point],
    closed: bool = False,
    x_offset: float = 0.0,
    theta_offset_deg: float = 0.0,
    scale: float = 1.0,
    tolerance: float = 0.05,
    corner_radius: float = 0.0,
    name: str = "bien-dang",
) -> Contour:
    """Cuốn một biên dạng phẳng bất kỳ lên mặt ống.

    ``points`` là toạ độ (u, v) tính bằng mm trên tấm trải phẳng: u dọc ống,
    v theo chu vi.  Đây là cửa ngõ để nạp DXF/SVG/CSV vào máy.
    """
    if len(points) < 2:
        raise ShapeError("Biên dạng cần ít nhất 2 điểm.")
    v_off = math.radians(theta_offset_deg) * radius
    pts = [(p[0] * scale + x_offset, p[1] * scale + v_off) for p in points]
    pts = g.dedupe(pts)
    if closed:
        pts = g.close_loop(pts)
    if corner_radius > 0:
        pts = g.round_corners(pts, corner_radius, closed=closed, tolerance=tolerance)
    return Contour(
        points=pts,
        closed=closed,
        wrap=False,
        name=name,
        meta={"shape": "flat_pattern"},
    )


# --------------------------------------------------------------------------
# 9. Vát mép hàn ở đầu ống (hai đường: mặt trong và mặt ngoài)
# --------------------------------------------------------------------------
def weld_prep(
    radius: float,
    x: float,
    bevel_angle_deg: float = 37.5,
    tolerance: float = 0.05,
    name: str = "vat-mep-han",
) -> Contour:
    """Cắt vuông đầu ống nhưng giữ trục vát ở góc cố định để tạo mép hàn V."""
    c = plane_cut(radius, x, 0.0, tolerance=tolerance, bevel=False, name=name)
    c.bevel_mode = BEVEL_CONSTANT
    c.bevel_value = bevel_angle_deg
    c.meta["shape"] = "weld_prep"
    return c
