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

COLOR_PIPE_FILL = "#dfe5ea"
COLOR_PIPE_EDGE = "#9aa6b1"
COLOR_PIPE_LINE = "#c3ccd4"
COLOR_SEAM = "#6f8899"
COLOR_CHUCK = "#8d9aa6"
COLOR_CHUCK_FILL = "#b9c3cc"
COLOR_TRACE = "#d93a1f"
COLOR_TORCH = "#3c4753"
COLOR_TORCH_HOT = "#ff7a1a"
COLOR_FRAME = "#aeb8c2"
COLOR_ROLLER = "#7f8b96"


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
        self.radius = max(profile.pipe.radius, 1.0)
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

    def surface(self, theta_world_deg: float, y: float, scale: float = 1.0) -> Vec3:
        a = math.radians(theta_world_deg)
        r = self.radius * scale
        return (r * math.sin(a), y, r * math.cos(a))

    def material_point(self, x: float, theta: float, scale: float = 1.0) -> Vec3:
        """Điểm gắn trên phôi -> toạ độ thế giới (đã tính tịnh tiến và quay)."""
        return self.surface(theta - self.rotary, x + self.y_head, scale)

    def normal(self, theta_world_deg: float) -> Vec3:
        a = math.radians(theta_world_deg)
        return (math.sin(a), 0.0, math.cos(a))


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
    out.extend(_roller(pose, P))
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
    r = pose.radius * radius_scale
    return [(r * math.sin(math.radians(k)), y, r * math.cos(math.radians(k)))
            for k in range(0, 360, step)]


def _pipe(pose: MachinePose, cam: Camera, P) -> List[Prim]:
    out: List[Prim] = []
    r = pose.radius
    # 1) thân ống tô đặc -> che hết những gì nằm phía sau
    hull = convex_hull([P(p) for p in _ring(pose, 1.0, pose.y_head)
                        + _ring(pose, 1.0, pose.y_tail)])
    if len(hull) >= 3:
        out.append(Prim("fill", hull, COLOR_PIPE_EDGE, 1.4, fill=COLOR_PIPE_FILL))
    # 2) hai vành đầu ống, chỉ nửa hướng về người xem
    for y in (pose.y_head, pose.y_tail):
        out.extend(_visible_runs(
            [(k, P(pose.surface(k, y))) for k in range(0, 365, 5)],
            cam, pose, COLOR_PIPE_EDGE, 1.2))
    # 3) đường sinh - quay theo trục A nên nhìn thấy ống đang xoay
    for k in range(0, 360, 30):
        theta_w = k - pose.rotary
        if not cam.faces_viewer(pose.normal(theta_w)):
            continue
        color, width = (COLOR_SEAM, 2.2) if k == 0 else (COLOR_PIPE_LINE, 1.0)
        out.append(Prim("poly", [P(pose.surface(theta_w, pose.y_head)),
                                 P(pose.surface(theta_w, pose.y_tail))], color, width))
    return out


def _visible_runs(samples, cam: Camera, pose: MachinePose, color: str,
                  width: float) -> List[Prim]:
    """Gom các điểm liền nhau còn nhìn thấy thành từng nét."""
    out: List[Prim] = []
    run: List[Vec2] = []
    for theta_w, pt in samples:
        if cam.faces_viewer(pose.normal(theta_w)):
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
        theta_w = k - pose.rotary
        if not cam.faces_viewer(pose.normal(theta_w)):
            continue
        out.append(Prim("poly", [P(pose.surface(theta_w, y0, 1.55)),
                                 P(pose.surface(theta_w, y0, 0.98))], COLOR_CHUCK, 3.0))
    return out


def _roller(pose: MachinePose, P) -> List[Prim]:
    """Con lăn đỡ đứng yên - mốc để thấy ống trượt qua."""
    out: List[Prim] = []
    r = pose.radius
    y = r * 2.6
    for side in (-1.0, 1.0):
        pts = []
        for k in range(0, 361, 30):
            a = math.radians(k)
            pts.append(P((side * r * 0.75 + r * 0.28 * math.sin(a), y,
                          -r * 0.95 + r * 0.28 * math.cos(a))))
        out.append(Prim("poly", pts, COLOR_ROLLER, 1.6))
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
        theta_w = tp.theta - pose.rotary
        if cam.faces_viewer(pose.normal(theta_w)):
            if not prev_ok:     # vừa vòng ra sau lưng ống rồi quay lại
                flush()
            run.append(P(pose.material_point(tp.x, tp.theta, 1.002)))
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
    tip = r + pose.lift          # Z0 = mũi cắt chạm đỉnh ống
    nozzle = tip + r * 0.32
    body_top = tip + r * 1.5
    out.append(Prim("poly", [P((-r * 1.6, 0.0, body_top)), P((r * 1.6, 0.0, body_top))],
                    COLOR_FRAME, 4.0))
    out.append(Prim("poly", [P((x, 0.0, nozzle)), P((x, 0.0, body_top))], COLOR_TORCH, 7.0))
    w = r * 0.22
    out.append(Prim("fill", [P((x - w, 0.0, nozzle)), P((x + w, 0.0, nozzle)),
                             P((x, 0.0, tip))], COLOR_TORCH, 1.0, fill=COLOR_TORCH))
    if pose.state.torch:
        hit = math.sqrt(max(0.0, r * r - x * x)) if abs(x) < r else -r
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
    for y in (y0, y1):
        for k in range(0, 360, 15):
            pts.append(cam.project(pose.surface(k, y)))
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
