"""Dựng "cảnh" mô phỏng máy dưới dạng các hình nguyên thuỷ, không phụ thuộc Tkinter.

Tách phần **tính toán hình học** ra khỏi phần **vẽ** để hai nơi dùng chung một
nguồn duy nhất:

* `ui/machineview.py` vẽ lên Canvas của Tkinter (xem trực tiếp, có hoạt hình);
* `svgview.py` xuất ra SVG (chụp lại một khoảnh khắc để in, gửi, lưu hồ sơ).

Toạ độ thế giới: ``(ngang, dọc ống, cao)`` — khớp với bố trí máy thật, trong đó
ống tịnh tiến theo phương dọc và quay quanh trục của nó, còn mỏ cắt chạy ngang
và lên xuống.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import (
    MachineProfile,
    ROLE_ALONG,
    ROLE_BEVEL,
    ROLE_CROSS,
    ROLE_RADIAL,
    ROLE_ROTARY,
)
from .gsim import SimState, TracePoint

Vec3 = Tuple[float, float, float]
Vec2 = Tuple[float, float]

from . import palette as _pal

# Màu cảnh máy lấy từ bảng màu đang dùng; đổi chế độ sáng/tối là tự đổi theo.
COLOR_PIPE_FILL = COLOR_PIPE_EDGE = COLOR_PIPE_LINE = COLOR_SEAM = ""
COLOR_CHUCK = COLOR_CHUCK_FILL = COLOR_TRACE = COLOR_TORCH = ""
COLOR_TORCH_HOT = COLOR_FRAME = ""


def _sync_colors(p=None) -> None:
    """Dựng màu cảnh máy từ bảng màu.

    Thân ống, mâm cặp và khung máy đều là sắc độ của một màu trung tính duy
    nhất, pha dần về phía nền - nhờ vậy chuyển sang chế độ tối là cả cảnh tự
    tối theo mà vẫn giữ đúng thứ tự đậm nhạt giữa các bộ phận.
    """
    global COLOR_PIPE_FILL, COLOR_PIPE_EDGE, COLOR_PIPE_LINE, COLOR_SEAM
    global COLOR_CHUCK, COLOR_CHUCK_FILL, COLOR_TRACE, COLOR_TORCH
    global COLOR_TORCH_HOT, COLOR_FRAME
    p = p or _pal.current()
    # Khung nhìn 3D nền xanh lam ở cả chế độ sáng lẫn tối, nên phôi và máy giữ
    # màu kim loại ở cả hai - y như FreeCAD, vật thể không đổi màu theo giao
    # diện.  Nếu để chúng chạy theo màu nền thì sang chế độ tối thân ống hoá
    # đen thui, nhìn không ra hình khối nữa.
    metal = p.metal_edge
    COLOR_PIPE_FILL = p.metal_fill
    COLOR_PIPE_EDGE = metal
    COLOR_PIPE_LINE = p.mix(metal, p.metal_fill, 0.55)
    COLOR_SEAM = p.mix(metal, p.accent, 0.45)
    COLOR_CHUCK = p.mix(metal, p.metal_fill, 0.15)
    COLOR_CHUCK_FILL = p.mix(metal, p.metal_fill, 0.55)
    COLOR_TRACE = p.cut
    COLOR_TORCH = p.tool
    COLOR_TORCH_HOT = p.torch_on
    COLOR_FRAME = p.mix(metal, p.view_bottom, 0.45)


_sync_colors()
_pal.on_change(_sync_colors)


@dataclass
class Prim:
    """Một hình nguyên thuỷ trong hệ toạ độ camera (chưa nhân tỉ lệ màn hình)."""

    kind: str                       # poly | fill | dot
    points: List[Vec2] = field(default_factory=list)
    color: str = "#000000"
    width: float = 1.0
    fill: Optional[str] = None
    radius: float = 0.0             # cho kind="dot", tính bằng điểm ảnh


class Camera:
    """Phép chiếu trục đo, xoay được quanh phôi."""

    def __init__(self, azimuth: float = 38.0, elevation: float = 24.0):
        self.azimuth = azimuth
        self.elevation = elevation
        self._update()

    def _update(self) -> None:
        az = math.radians(self.azimuth)
        el = math.radians(max(-85.0, min(85.0, self.elevation)))
        self.dir = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
        d = self.dir
        r = (-d[1], d[0], 0.0)      # tích có hướng của trục "lên" với hướng nhìn
        n = math.hypot(r[0], r[1]) or 1.0
        self.right = (r[0] / n, r[1] / n, 0.0)
        rr = self.right
        self.up = (d[1] * rr[2] - d[2] * rr[1],
                   d[2] * rr[0] - d[0] * rr[2],
                   d[0] * rr[1] - d[1] * rr[0])

    def orbit(self, d_az: float, d_el: float) -> None:
        self.azimuth = (self.azimuth + d_az) % 360.0
        self.elevation = max(-85.0, min(85.0, self.elevation + d_el))
        self._update()

    def project(self, p: Vec3) -> Vec2:
        return (sum(a * b for a, b in zip(p, self.right)),
                -sum(a * b for a, b in zip(p, self.up)))

    def faces_viewer(self, normal: Vec3) -> bool:
        return sum(a * b for a, b in zip(normal, self.dir)) > 0.0


def convex_hull(points: Sequence[Vec2]) -> List[Vec2]:
    """Bao lồi 2D (monotone chain).

    Mặt trụ là khối lồi, nên bao lồi của hai vành đầu ống **chính là** đường bao
    thật của thân ống - tô đặc nó là có ngay hiệu ứng che khuất đúng.
    """
    pts = sorted(set(points))
    if len(pts) < 3:
        return list(pts)

    def half(seq):
        out: List[Vec2] = []
        for p in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) <= 0:
                    out.pop()
                else:
                    break
            out.append(p)
        return out

    return half(pts)[:-1] + half(list(reversed(pts)))[:-1]


# ----------------------------------------------------------------------
class MachinePose:
    """Tư thế máy tại một thời điểm, suy từ giá trị bốn trục."""

    def __init__(self, profile: MachineProfile, state: SimState):
        self.profile = profile
        self.state = state
        self.section = profile.pipe.section()
        self.radius = max(profile.pipe.radius, 1.0)   # bán kính bao ngoài
        self.length = max(profile.pipe.length, 10.0)
        self.along = self.axis(ROLE_ALONG)
        self.rotary = self.axis(ROLE_ROTARY)
        self.cross = self.axis(ROLE_CROSS)
        self.lift = self.axis(ROLE_RADIAL)
        if profile.layout == "torch_moves":
            self.y_head, self.y_tail = 0.0, self.length   # ống đứng yên
        else:
            self.y_head = -self.along                     # ống tịnh tiến
            self.y_tail = self.length - self.along

    def axis(self, role: str) -> float:
        ax = self.profile.axis(role)
        if ax is None:
            return 0.0
        v = self.state.axes.get(ax.letter)
        if v is None:
            return 0.0
        v -= ax.offset
        return -v if ax.invert else v

    def _rotate(self, cx: float, cy: float) -> Tuple[float, float]:
        """Quay một điểm của tiết diện theo góc trục A hiện tại."""
        a = math.radians(self.rotary)
        return (cx * math.cos(a) - cy * math.sin(a),
                cx * math.sin(a) + cy * math.cos(a))

    def surface(self, v: float, y: float, scale: float = 1.0) -> Vec3:
        """Điểm trên bề mặt phôi (vị trí cung ``v``) -> toạ độ thế giới."""
        cx, cy = self.section.point_at(v % self.section.perimeter)
        rx, rz = self._rotate(cx * scale, cy * scale)
        return (rx, y, rz)

    def material_point(self, x: float, v: float, scale: float = 1.0) -> Vec3:
        """Điểm gắn trên phôi -> toạ độ thế giới (đã tính tịnh tiến và quay)."""
        return self.surface(v, x + self.y_head, scale)

    def normal(self, v: float) -> Vec3:
        """Pháp tuyến ngoài tại vị trí ``v``, trong hệ thế giới."""
        psi = math.radians(self.section.normal_angle(v % self.section.perimeter)
                           - self.rotary)
        return (math.sin(psi), 0.0, math.cos(psi))

    @property
    def top_height(self) -> float:
        """Chiều cao bề mặt tại điểm mốc - chính là gốc Z khi rà dao."""
        return self.section.reference_height


# ----------------------------------------------------------------------
def build_scene(
    profile: MachineProfile,
    state: SimState,
    trace: Sequence[TracePoint],
    cam: Camera,
    show_frame: bool = True,
    show_trace: bool = True,
    trace_limit: int = 900,
) -> List[Prim]:
    """Dựng toàn bộ cảnh máy, trả về danh sách hình theo đúng thứ tự vẽ."""
    pose = MachinePose(profile, state)
    P = cam.project
    out: List[Prim] = []

    if show_frame:
        out.extend(_frame(pose, P))
    out.extend(_pipe(pose, cam, P))
    out.extend(_chuck(pose, cam, P))
    if show_trace and trace:
        out.extend(_trace(pose, cam, P, trace, trace_limit))
    out.extend(_torch(pose, P))
    return out


def _frame(pose: MachinePose, P) -> List[Prim]:
    """Bệ máy và cột mang mỏ cắt - làm mốc để thấy ống đang trượt."""
    r, length = pose.radius, pose.length
    base = -r * 1.9
    span = max(length, 200.0)
    y0 = min(pose.y_head, -span * 0.1)
    y1 = max(pose.y_tail, span * 1.05)
    out: List[Prim] = []
    for side in (-1.0, 1.0):
        out.append(Prim("poly", [P((side * r * 1.7, y0, base)),
                                 P((side * r * 1.7, y1, base))], COLOR_FRAME, 2.0))
    for k in range(7):
        y = y0 + (y1 - y0) * k / 6
        out.append(Prim("poly", [P((-r * 1.7, y, base)), P((r * 1.7, y, base))],
                        COLOR_FRAME, 1.0))
    top = r * 3.0
    for x in (-r * 1.7, r * 1.7):
        out.append(Prim("poly", [P((x, 0.0, base)), P((x, 0.0, top))], COLOR_FRAME, 2.0))
    out.append(Prim("poly", [P((-r * 1.7, 0.0, top)), P((r * 1.7, 0.0, top))],
                    COLOR_FRAME, 3.0))
    return out


def _ring(pose: MachinePose, radius_scale: float, y: float, step: int = 6) -> List[Vec3]:
    """Vành tròn (dùng cho mâm cặp) - luôn tròn dù phôi hình gì."""
    r = pose.radius * radius_scale
    return [(r * math.sin(math.radians(k)), y, r * math.cos(math.radians(k)))
            for k in range(0, 360, step)]


def _section_ring(pose: MachinePose, y: float, steps: int = 72) -> List[Vec3]:
    """Đường bao tiết diện phôi tại một mặt cắt ngang."""
    per = pose.section.perimeter
    return [pose.surface(per * i / steps, y) for i in range(steps)]


def _pipe(pose: MachinePose, cam: Camera, P) -> List[Prim]:
    out: List[Prim] = []
    r = pose.radius
    # 1) thân phôi tô đặc -> che hết những gì nằm phía sau
    hull = convex_hull([P(p) for p in _section_ring(pose, pose.y_head)
                        + _section_ring(pose, pose.y_tail)])
    if len(hull) >= 3:
        out.append(Prim("fill", hull, COLOR_PIPE_EDGE, 1.4, fill=COLOR_PIPE_FILL))
    # 2) hai vành đầu phôi, chỉ nửa hướng về người xem
    per = pose.section.perimeter
    steps = 96
    for y in (pose.y_head, pose.y_tail):
        out.extend(_visible_runs(
            [(per * i / steps, P(pose.surface(per * i / steps, y)))
             for i in range(steps + 1)],
            cam, pose, COLOR_PIPE_EDGE, 1.2))
    # 3) đường sinh - quay theo trục A nên nhìn thấy phôi đang xoay.
    #    Với ống hộp, thêm hẳn đường sinh ở các cạnh để thấy rõ hình hộp.
    marks = [per * k / 12 for k in range(12)]
    edges = [b for b in pose.section.breakpoints() if b < per - 1e-9]
    for v in sorted(set(marks + edges)):
        if not cam.faces_viewer(pose.normal(v)):
            continue
        is_edge = any(abs(v - b) < 1e-6 for b in edges)
        if abs(v) < 1e-9:
            color, width = COLOR_SEAM, 2.2          # vạch mốc 0 độ
        elif is_edge:
            color, width = COLOR_PIPE_EDGE, 1.4     # cạnh ống hộp
        else:
            color, width = COLOR_PIPE_LINE, 1.0
        out.append(Prim("poly", [P(pose.surface(v, pose.y_head)),
                                 P(pose.surface(v, pose.y_tail))], color, width))
    return out


def _visible_runs(samples, cam: Camera, pose: MachinePose, color: str,
                  width: float) -> List[Prim]:
    """Gom các điểm liền nhau còn nhìn thấy thành từng nét."""
    out: List[Prim] = []
    run: List[Vec2] = []
    for v, pt in samples:
        if cam.faces_viewer(pose.normal(v)):
            run.append(pt)
        elif len(run) >= 2:
            out.append(Prim("poly", run, color, width))
            run = []
        else:
            run = []
    if len(run) >= 2:
        out.append(Prim("poly", run, color, width))
    return out


def _chuck(pose: MachinePose, cam: Camera, P) -> List[Prim]:
    """Mâm cặp kẹp đuôi ống - tịnh tiến và quay cùng ống."""
    out: List[Prim] = []
    r = pose.radius
    y0, y1 = pose.y_tail, pose.y_tail + r * 0.9
    hull = convex_hull([P(p) for p in _ring(pose, 1.55, y0, 10)
                        + _ring(pose, 1.55, y1, 10)])
    if len(hull) >= 3:
        out.append(Prim("fill", hull, COLOR_CHUCK, 1.4, fill=COLOR_CHUCK_FILL))
    for k in range(0, 360, 120):        # ba vấu kẹp cho thấy mâm đang quay
        a = math.radians(k - pose.rotary)
        n = (math.sin(a), 0.0, math.cos(a))
        if not cam.faces_viewer(n):
            continue
        rc = pose.radius
        out.append(Prim("poly", [P((rc * 1.55 * n[0], y0, rc * 1.55 * n[2])),
                                 P((rc * 0.98 * n[0], y0, rc * 0.98 * n[2]))],
                        COLOR_CHUCK, 3.0))
    return out


def _trace(pose: MachinePose, cam: Camera, P, trace: Sequence[TracePoint],
           limit: int) -> List[Prim]:
    """Vết cắt đã hình thành - chỉ vẽ phần đang hướng về phía người xem."""
    out: List[Prim] = []
    stride = max(1, len(trace) // max(limit, 1))
    run: List[Vec2] = []

    def flush():
        if len(run) >= 2:
            out.append(Prim("poly", list(run), COLOR_TRACE, 2.4))
        run.clear()

    prev_ok = False
    for i in range(0, len(trace), stride):
        tp = trace[i]
        if tp.start:            # nhấc dao: không nối sang lượt cắt kế tiếp
            flush()
            prev_ok = False
        if cam.faces_viewer(pose.normal(tp.v)):
            if not prev_ok:     # vừa vòng ra sau lưng phôi rồi quay lại
                flush()
            run.append(P(pose.material_point(tp.x, tp.v, 1.004)))
            prev_ok = True
        else:
            flush()
            prev_ok = False
    flush()
    return out


def _torch(pose: MachinePose, P) -> List[Prim]:
    """Mỏ cắt: chạy ngang theo X, lên xuống theo Z, đứng yên theo phương dọc."""
    out: List[Prim] = []
    r = pose.radius
    x = pose.cross
    tip = pose.top_height + pose.lift   # Z0 = mũi cắt chạm bề mặt ở vị trí mốc
    nozzle = tip + r * 0.32
    body_top = tip + r * 1.5
    out.append(Prim("poly", [P((-r * 1.6, 0.0, body_top)), P((r * 1.6, 0.0, body_top))],
                    COLOR_FRAME, 4.0))
    out.append(Prim("poly", [P((x, 0.0, nozzle)), P((x, 0.0, body_top))], COLOR_TORCH, 7.0))
    w = r * 0.22
    out.append(Prim("fill", [P((x - w, 0.0, nozzle)), P((x + w, 0.0, nozzle)),
                             P((x, 0.0, tip))], COLOR_TORCH, 1.0, fill=COLOR_TORCH))
    if pose.state.torch:
        # điểm chạm thật của tia cắt ở đúng tư thế hiện tại
        hit = pose.section.surface_height(pose.rotary, x)
        out.append(Prim("poly", [P((x, 0.0, tip)), P((x, 0.0, hit))], COLOR_TORCH_HOT, 3.0))
        out.append(Prim("dot", [P((x, 0.0, hit))], COLOR_TORCH_HOT, 1.0,
                        fill=COLOR_TORCH_HOT, radius=4.0))
    return out


# ----------------------------------------------------------------------
def scene_bounds(profile: MachineProfile, cam: Camera,
                 state: Optional[SimState] = None,
                 along_range: Optional[Tuple[float, float]] = None
                 ) -> Tuple[float, float, float, float]:
    """Khung bao của cảnh, dùng để canh tỉ lệ cho vừa khung nhìn.

    Vì phôi **trượt qua lại** trong lúc chạy, khung nhìn phải bao trọn cả hành
    trình của nó (``along_range`` = khoảng giá trị trục dọc trong chương trình),
    nếu không hình sẽ nhảy ra ngoài mép mỗi khi ống đi xa.
    """
    pose = MachinePose(profile, state or SimState())
    if along_range and profile.layout != "torch_moves":
        lo, hi = min(along_range), max(along_range)
        y0, y1 = -hi, pose.length - lo
    else:
        y0, y1 = pose.y_head, pose.y_tail
    pad = max(pose.length * 0.06, pose.radius * 2.0)
    y0 -= pad
    y1 += pad
    pts: List[Vec2] = []
    per = pose.section.perimeter
    for y in (y0, y1):
        for i in range(24):
            pts.append(cam.project(pose.surface(per * i / 24, y)))
        for x in (-pose.radius * 1.75, pose.radius * 1.75):   # bệ máy
            pts.append(cam.project((x, y, -pose.radius * 1.95)))
    for x in (-pose.radius * 1.75, pose.radius * 1.75):       # cột mang mỏ cắt
        pts.append(cam.project((x, 0.0, pose.radius * 3.1)))
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def axis_readout(profile: MachineProfile, state: SimState) -> List[str]:
    """Các dòng hiển thị giá trị trục kèm tên gọi dễ hiểu."""
    labels = [(ROLE_CROSS, "ngang"), (ROLE_ALONG, "ống ra vào"),
              (ROLE_RADIAL, "lên xuống"), (ROLE_ROTARY, "xoay"), (ROLE_BEVEL, "vát")]
    rows: List[str] = []
    for role, text in labels:
        ax = profile.axis(role)
        if ax is None:
            continue
        unit = "°" if ax.is_angular else " mm"
        rows.append(f"{ax.letter}  {state.axes.get(ax.letter, 0.0):9.2f}{unit}   {text}")
    return rows
