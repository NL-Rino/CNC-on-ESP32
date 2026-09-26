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
COLOR_MACHINE = COLOR_MACHINE_EDGE = COLOR_NOZZLE = COLOR_ARC_CORE = ""
COLOR_SPECULAR = COLOR_INSIDE = COLOR_GROUND = COLOR_GHOST = COLOR_HALO = ""
COLOR_GLOW = COLOR_GAP = COLOR_HUD_BG = ""


def _sync_colors(p=None) -> None:
    """Dựng màu cảnh máy từ bảng màu.

    Khung nhìn 3D nền xanh lam ở cả chế độ sáng lẫn tối, nên phôi và máy giữ
    màu kim loại ở cả hai - y như FreeCAD, vật thể không đổi màu theo giao
    diện.  Nếu để chúng chạy theo màu nền thì sang chế độ tối thân ống hoá
    đen thui, nhìn không ra hình khối nữa.
    """
    global COLOR_PIPE_FILL, COLOR_PIPE_EDGE, COLOR_PIPE_LINE, COLOR_SEAM
    global COLOR_CHUCK, COLOR_CHUCK_FILL, COLOR_TRACE, COLOR_TORCH
    global COLOR_TORCH_HOT, COLOR_FRAME
    global COLOR_MACHINE, COLOR_MACHINE_EDGE, COLOR_NOZZLE, COLOR_ARC_CORE
    global COLOR_SPECULAR, COLOR_INSIDE, COLOR_GROUND, COLOR_GHOST, COLOR_HALO
    global COLOR_GLOW, COLOR_GAP, COLOR_HUD_BG
    p = p or _pal.current()
    metal = p.metal_edge
    COLOR_PIPE_FILL = p.metal_fill
    COLOR_PIPE_EDGE = metal
    COLOR_PIPE_LINE = p.mix(metal, p.metal_fill, 0.62)
    COLOR_SEAM = p.accent
    COLOR_CHUCK = p.machine_edge
    COLOR_CHUCK_FILL = p.machine_body
    COLOR_TRACE = p.cut
    COLOR_TORCH = p.tool
    COLOR_TORCH_HOT = p.torch_on
    COLOR_FRAME = p.machine_edge
    COLOR_MACHINE = p.machine_body
    COLOR_MACHINE_EDGE = p.machine_edge
    COLOR_NOZZLE = p.nozzle
    COLOR_ARC_CORE = p.arc_core
    COLOR_SPECULAR = p.specular
    COLOR_INSIDE = p.mix(metal, p.hud_bg, 0.35)          # lòng ống, khuất sáng
    COLOR_GROUND = p.mix(p.view_top, p.view_bottom, 0.5)
    COLOR_GROUND = p.mix(COLOR_GROUND, p.hud_fg, 0.22)     # lưới sàn: nhạt, không rối mắt
    COLOR_GHOST = p.mix(p.cut, p.metal_edge, 0.2)          # đường sắp cắt (nét đứt)
    COLOR_HALO = p.mix(p.cut, p.hud_bg, 0.6)               # viền tối cho vết cắt nổi lên
    COLOR_GLOW = p.mix(p.torch_on, p.view_top, 0.45)
    COLOR_GAP = p.mix(p.hud_fg, p.view_top, 0.25)
    COLOR_HUD_BG = p.hud_bg


_sync_colors()
_pal.on_change(_sync_colors)


@dataclass
class Prim:
    """Một hình nguyên thuỷ trong hệ toạ độ camera (chưa nhân tỉ lệ màn hình)."""

    kind: str                       # poly | fill | dot | text
    points: List[Vec2] = field(default_factory=list)
    color: str = "#000000"
    width: float = 1.0
    fill: Optional[str] = None
    radius: float = 0.0             # cho kind="dot", tính bằng điểm ảnh
    dash: Tuple[int, ...] = ()      # nét đứt (điểm ảnh), rỗng = nét liền
    text: str = ""                  # cho kind="text"


class Camera:
    """Phép chiếu trục đo, xoay được quanh phôi."""

    # Mặc định nhìn từ phía đầu tự do, hơi chếch trên: thấy miệng ống (biết ngay
    # là ống chứ không phải thanh đặc), thấy mặt trên nơi đang cắt, và cột máy
    # nằm phía sau ống nên không che vùng cắt.
    DEFAULT_AZIMUTH = -38.0
    DEFAULT_ELEVATION = 28.0

    def __init__(self, azimuth: float = DEFAULT_AZIMUTH, elevation: float = DEFAULT_ELEVATION):
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

    def depth(self, p: Vec3) -> float:
        """Càng lớn càng gần người xem (hướng nhìn ``dir`` chỉ về phía người xem)."""
        return sum(a * b for a, b in zip(p, self.dir))


# ----------------------------------------------------------------------
# Ánh sáng: một đèn chiếu từ trên - trái - phía người xem
# ----------------------------------------------------------------------
def _rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in (r, g, b))


def _unit(v: Vec3) -> Vec3:
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


class Light:
    """Chiếu sáng kiểu Blinn-Phong đơn giản, gắn theo camera.

    Đèn đi theo góc nhìn nên xoay tới đâu mặt hướng về người xem cũng sáng,
    mặt quay đi thì tối dần - đủ để mắt đọc ra hình khối tròn hay vuông.
    """

    def __init__(self, cam: Camera):
        d, r, u = cam.dir, cam.right, cam.up
        self.L = _unit(tuple(0.55 * d[i] + 0.75 * u[i] - 0.35 * r[i] for i in range(3)))
        self.H = _unit(tuple(self.L[i] + d[i] for i in range(3)))
        self._cache: Dict[Tuple[str, int, int, int], str] = {}

    def shade(self, base: str, n: Vec3, ambient: float = 0.42, diffuse: float = 0.6,
              spec: float = 0.5, shininess: float = 26.0) -> str:
        key = (base, int(n[0] * 64), int(n[1] * 64), int(n[2] * 64))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        ndl = max(0.0, sum(a * b for a, b in zip(n, self.L)))
        ndh = max(0.0, sum(a * b for a, b in zip(n, self.H)))
        k = ambient + diffuse * ndl
        s = spec * ndh ** shininess
        br, bg, bb = _rgb(base)
        wr, wg, wb = _rgb(COLOR_SPECULAR or "#000000")
        out = _hex(br * k + (wr - br * k) * s, bg * k + (wg - bg * k) * s,
                   bb * k + (wb - bb * k) * s)
        self._cache[key] = out
        return out


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
    plan: Sequence[TracePoint] = (),
) -> List[Prim]:
    """Dựng toàn bộ cảnh máy, trả về danh sách hình theo đúng thứ tự vẽ.

    ``trace`` là phần đã cắt tới thời điểm này (vẽ đậm), ``plan`` là toàn bộ
    đường sẽ cắt của chương trình (vẽ mờ nét đứt) - nhìn là biết máy sắp đi đâu.

    Thứ tự vẽ theo chiều sâu (vật xa vẽ trước, vật gần vẽ đè lên): sàn -> cột
    máy nếu nằm sau ống -> ống và mâm cặp (cái nào xa hơn vẽ trước) -> cột máy
    nếu nằm trước ống -> cần mang mỏ -> mỏ cắt và hồ quang.
    """
    pose = MachinePose(profile, state)
    P = cam.project
    light = Light(cam)
    out: List[Prim] = []

    column: List[Prim] = []
    column_front = False
    if show_frame:
        out.extend(_ground(pose, P))
        column, column_front = _column(pose, cam, light, P)
        if not column_front:
            out.extend(column)

    tube = _pipe(pose, cam, light, P)
    if show_trace:
        if plan:
            tube.extend(_trace(pose, cam, P, plan, trace_limit, ghost=True))
        if trace:
            tube.extend(_trace(pose, cam, P, trace, trace_limit))
    chuck = _chuck(pose, cam, light, P)
    # Người xem ở phía mâm cặp (dir.y > 0) thì mâm cặp gần hơn: vẽ sau ống.
    if cam.dir[1] > 0:
        out.extend(tube + chuck)
    else:
        out.extend(chuck + tube)

    if show_frame and column_front:
        out.extend(column)
    if show_frame:
        out.extend(_arm(pose, cam, light, P))
    out.extend(_torch(pose, cam, light, P))
    return out


def _box(cam: Camera, light: Light, P, x0: float, x1: float, y0: float, y1: float,
         z0: float, z1: float, color: str, edge: str) -> List[Prim]:
    """Khối hộp đặc: chỉ vẽ các mặt hướng về người xem (khối lồi, không chồng nhau)."""
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    faces = [
        ((-1, 0, 0), [0, 1, 3, 2]), ((1, 0, 0), [4, 6, 7, 5]),
        ((0, -1, 0), [0, 4, 5, 1]), ((0, 1, 0), [2, 3, 7, 6]),
        ((0, 0, -1), [0, 2, 6, 4]), ((0, 0, 1), [1, 5, 7, 3]),
    ]
    out: List[Prim] = []
    for n, idx in faces:
        if cam.faces_viewer(n):
            col = light.shade(color, n, ambient=0.5, diffuse=0.5, spec=0.25)
            out.append(Prim("fill", [P(c[k]) for k in idx], edge, 1.0, fill=col))
    return out


def _ground(pose: MachinePose, P) -> List[Prim]:
    """Lưới sàn mờ phía dưới và hai ray bệ máy - cho mắt cảm giác chiều sâu."""
    r = pose.radius
    base = -r * 1.9
    y0 = min(pose.y_head, -r * 8.0) - r * 2.0
    y1 = max(pose.y_tail, r * 8.0) + r * 2.0
    step = _nice_step((y1 - y0) / 24.0)
    out: List[Prim] = []
    half = r * 3.2
    k0, k1 = int(math.floor(y0 / step)), int(math.ceil(y1 / step))
    for k in range(k0, k1 + 1):
        y = k * step
        out.append(Prim("poly", [P((-half, y, base)), P((half, y, base))], COLOR_GROUND, 1.0))
    xs = int(half // step)
    for k in range(-xs, xs + 1):
        x = k * step
        out.append(Prim("poly", [P((x, y0, base)), P((x, y1, base))], COLOR_GROUND, 1.0))
    for side in (-1.0, 1.0):                                       # hai ray bệ máy
        out.append(Prim("poly", [P((side * r * 1.7, y0, base)), P((side * r * 1.7, y1, base))],
                        COLOR_MACHINE_EDGE, 2.4))
    return out


def _nice_step(raw: float) -> float:
    """Bước lưới tròn số: 1, 2, 5 x 10^k mm."""
    raw = max(raw, 1e-6)
    e = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if m * e >= raw:
            return m * e
    return 10 * e


def _column(pose: MachinePose, cam: Camera, light: Light, P) -> Tuple[List[Prim], bool]:
    """Cột máy một bên ống (như máy cắt ống thật), mang cần với ra trên ống."""
    r = pose.radius
    base = -r * 1.9
    top = pose.top_height + r * 2.4
    w = r * 0.28
    x = -r * 1.9
    prims = _box(cam, light, P, x - w, x + w, -w, w, base, top, COLOR_MACHINE, COLOR_MACHINE_EDGE)
    front = cam.depth((x, 0.0, 0.0)) > cam.depth((0.0, 0.0, 0.0)) + r * 0.2
    return prims, front


def _arm(pose: MachinePose, cam: Camera, light: Light, P) -> List[Prim]:
    """Cần ngang mang cụm mỏ cắt - trục X chạy dọc cần này."""
    r = pose.radius
    z = pose.top_height + r * 2.4
    h = r * 0.18
    return _box(cam, light, P, -r * 2.2, r * 1.6, -h * 1.4, h * 1.4, z - h, z + h,
                COLOR_MACHINE, COLOR_MACHINE_EDGE)


def _ring(pose: MachinePose, radius_scale: float, y: float, step: int = 6) -> List[Vec3]:
    """Vành tròn (dùng cho mâm cặp) - luôn tròn dù phôi hình gì."""
    r = pose.radius * radius_scale
    return [(r * math.sin(math.radians(k)), y, r * math.cos(math.radians(k)))
            for k in range(0, 360, step)]


def _section_ring(pose: MachinePose, y: float, steps: int = 72) -> List[Vec3]:
    """Đường bao tiết diện phôi tại một mặt cắt ngang."""
    per = pose.section.perimeter
    return [pose.surface(per * i / steps, y) for i in range(steps)]


def _samples(pose: MachinePose, steps: int) -> List[float]:
    """Các vị trí cung để chia dải: đều nhau, cộng thêm đúng các điểm gãy của
    ống hộp để cạnh phẳng/cung góc không bị dải nào vắt ngang qua."""
    per = pose.section.perimeter
    vs = {round(per * i / steps, 9) for i in range(steps)}
    vs.update(round(b, 9) for b in pose.section.breakpoints() if 0.0 <= b < per - 1e-9)
    return sorted(vs)


def _pipe(pose: MachinePose, cam: Camera, light: Light, P) -> List[Prim]:
    """Thân phôi tô sáng tối theo pháp tuyến, miệng ống thấy rõ thành ống."""
    out: List[Prim] = []
    per = pose.section.perimeter
    y0, y1 = pose.y_head, pose.y_tail
    vs = _samples(pose, 96)
    # 1) các dải dọc thân ống hướng về người xem.  Khối lồi nên các dải nhìn
    #    thấy không bao giờ đè lên nhau - khỏi sắp theo chiều sâu.
    for k, va in enumerate(vs):
        vb = vs[k + 1] if k + 1 < len(vs) else vs[0] + per
        n = pose.normal((va + vb) / 2.0)
        if not cam.faces_viewer(n):
            continue
        col = light.shade(COLOR_PIPE_FILL, n, ambient=0.34, diffuse=0.7)
        quad = [P(pose.surface(va, y0)), P(pose.surface(vb, y0)),
                P(pose.surface(vb, y1)), P(pose.surface(va, y1))]
        out.append(Prim("fill", quad, col, 1.0, fill=col))
    # 2) đường bao ngoài cho sắc nét
    hull = convex_hull([P(p) for p in _section_ring(pose, y0) + _section_ring(pose, y1)])
    if len(hull) >= 3:
        out.append(Prim("poly", hull + [hull[0]], COLOR_PIPE_EDGE, 1.2))
    # 3) miệng ống phía đầu tự do: vành khăn + lòng ống tối
    if cam.faces_viewer((0.0, -1.0, 0.0)):
        ring = _section_ring(pose, y0, 96)
        cap = light.shade(COLOR_PIPE_FILL, (0.0, -1.0, 0.0), ambient=0.5)
        out.append(Prim("fill", [P(q) for q in ring], COLOR_PIPE_EDGE, 1.2, fill=cap))
        inner = _inner_ring(pose, y0, 96)
        if inner:
            out.append(Prim("fill", [P(q) for q in inner], COLOR_PIPE_EDGE, 1.0,
                            fill=COLOR_INSIDE))
    # 4) đường sinh mảnh cho thấy ống đang xoay, vạch mốc 0 độ đậm màu nhấn
    for m in range(8):
        v = per * m / 8
        if not cam.faces_viewer(pose.normal(v)):
            continue
        seam = m == 0
        out.append(Prim("poly", [P(pose.surface(v, y0)), P(pose.surface(v, y1))],
                        COLOR_SEAM if seam else COLOR_PIPE_LINE, 2.2 if seam else 1.0))
    return out


def _inner_ring(pose: MachinePose, y: float, steps: int) -> List[Vec3]:
    """Mép trong của thành ống ở mặt đầu: tiết diện co vào đúng chiều dày thành."""
    t = max(0.0, float(pose.profile.pipe.wall_thickness))
    per = pose.section.perimeter
    pts = [pose.section.point_at(per * i / steps) for i in range(steps)]
    a = max(abs(p[0]) for p in pts) or 1.0
    b = max(abs(p[1]) for p in pts) or 1.0
    if t <= 0 or t >= min(a, b):
        return []
    fx, fy = (a - t) / a, (b - t) / b
    out: List[Vec3] = []
    for cx, cy in pts:
        rx, rz = pose._rotate(cx * fx, cy * fy)
        out.append((rx, y, rz))
    return out


def _cylinder_y(cam: Camera, light: Light, P, radius: float, y0: float, y1: float,
                color: str, edge: str, steps: int = 48) -> List[Prim]:
    """Trụ tròn nằm dọc trục ống (mâm cặp), tô sáng tối và mặt trước."""
    out: List[Prim] = []
    for k in range(steps):
        a0, a1 = 2 * math.pi * k / steps, 2 * math.pi * (k + 1) / steps
        am = (a0 + a1) / 2
        n = (math.sin(am), 0.0, math.cos(am))
        if not cam.faces_viewer(n):
            continue
        col = light.shade(color, n, ambient=0.5, diffuse=0.55, spec=0.35)
        q = [P((radius * math.sin(a0), y0, radius * math.cos(a0))),
             P((radius * math.sin(a1), y0, radius * math.cos(a1))),
             P((radius * math.sin(a1), y1, radius * math.cos(a1))),
             P((radius * math.sin(a0), y1, radius * math.cos(a0)))]
        out.append(Prim("fill", q, col, 1.0, fill=col))
    for yy, n in ((y0, (0.0, -1.0, 0.0)), (y1, (0.0, 1.0, 0.0))):
        if cam.faces_viewer(n):
            ring = [P((radius * math.sin(2 * math.pi * k / steps), yy,
                       radius * math.cos(2 * math.pi * k / steps))) for k in range(steps)]
            out.append(Prim("fill", ring, edge, 1.2,
                            fill=light.shade(color, n, ambient=0.55, diffuse=0.5)))
    return out


def _chuck(pose: MachinePose, cam: Camera, light: Light, P) -> List[Prim]:
    """Mâm cặp kẹp đuôi ống - tịnh tiến và quay cùng ống."""
    r = pose.radius
    y0, y1 = pose.y_tail, pose.y_tail + r * 0.9
    out = _cylinder_y(cam, light, P, r * 1.55, y0, y1, COLOR_MACHINE, COLOR_MACHINE_EDGE)
    for k in range(0, 360, 120):        # ba vấu kẹp cho thấy mâm đang quay
        a = math.radians(k - pose.rotary)
        n = (math.sin(a), 0.0, math.cos(a))
        if not cam.faces_viewer(n) and not cam.faces_viewer((0.0, -1.0, 0.0)):
            continue
        out.append(Prim("poly", [P((r * 1.5 * n[0], y0 - 0.5, r * 1.5 * n[2])),
                                 P((r * 1.0 * n[0], y0 - 0.5, r * 1.0 * n[2]))],
                        COLOR_MACHINE_EDGE, 4.0))
    return out


def _trace(pose: MachinePose, cam: Camera, P, trace: Sequence[TracePoint],
           limit: int, ghost: bool = False) -> List[Prim]:
    """Vết cắt trên phôi - chỉ vẽ phần đang hướng về phía người xem.

    Đã cắt: lõi màu cắt trên nền viền tối, nổi hẳn lên mặt kim loại sáng.
    Sắp cắt (``ghost``): nét đứt mờ.
    """
    out: List[Prim] = []
    stride = max(1, len(trace) // max(limit, 1))
    runs: List[List[Vec2]] = []
    run: List[Vec2] = []

    def flush():
        if len(run) >= 2:
            runs.append(list(run))
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
    if ghost:
        return [Prim("poly", r_, COLOR_GHOST, 1.6, dash=(5, 4)) for r_ in runs]
    out.extend(Prim("poly", r_, COLOR_HALO, 5.0) for r_ in runs)
    out.extend(Prim("poly", r_, COLOR_TRACE, 2.4) for r_ in runs)
    return out


def _torch(pose: MachinePose, cam: Camera, light: Light, P) -> List[Prim]:
    """Mỏ cắt: thân trụ kim loại, béc đồng hình côn, hồ quang khi đang cắt.

    Chạy ngang theo X, lên xuống theo Z, đứng yên theo phương dọc ống.
    """
    out: List[Prim] = []
    r = pose.radius
    x = pose.cross
    tip = pose.top_height + pose.lift       # Z0 = mũi cắt chạm bề mặt ở vị trí mốc
    rt = max(4.0, min(16.0, r * 0.26))      # bán kính thân mỏ
    nozzle = tip + rt * 1.6
    body_top = pose.top_height + r * 2.4
    d = cam.dir
    h = _unit((d[0], d[1], 0.0)) if abs(d[0]) + abs(d[1]) > 1e-9 else (1.0, 0.0, 0.0)
    side = cam.right

    def strips(z0: float, z1: float, r0: float, r1: float, color: str, k: int = 10):
        for i in range(k):
            f0 = -math.pi / 2 + math.pi * i / k
            f1 = -math.pi / 2 + math.pi * (i + 1) / k
            fm = (f0 + f1) / 2
            n = tuple(math.cos(fm) * h[j] + math.sin(fm) * side[j] for j in range(3))
            col = light.shade(color, n, ambient=0.45, diffuse=0.6, spec=0.6, shininess=30)

            def pt(f, rr, z):
                return P((x + rr * (math.cos(f) * h[0] + math.sin(f) * side[0]),
                          rr * (math.cos(f) * h[1] + math.sin(f) * side[1]), z))
            out.append(Prim("fill", [pt(f0, r0, z0), pt(f1, r0, z0),
                                     pt(f1, r1, z1), pt(f0, r1, z1)], col, 1.0, fill=col))

    strips(nozzle, body_top, rt, rt, COLOR_PIPE_FILL)          # thân mỏ
    strips(tip, nozzle, rt * 0.32, rt * 0.8, COLOR_NOZZLE)     # béc đồng

    hit = pose.section.surface_height(pose.rotary, x)          # điểm tia thẳng đứng chạm phôi
    if pose.state.torch:
        a, b = P((x, 0.0, tip)), P((x, 0.0, hit))
        out.append(Prim("poly", [a, b], COLOR_GLOW, 11.0))
        out.append(Prim("poly", [a, b], COLOR_TORCH_HOT, 5.0))
        out.append(Prim("poly", [a, b], COLOR_ARC_CORE, 2.0))
        out.append(Prim("dot", [b], COLOR_TORCH_HOT, 1.0, fill=COLOR_TORCH_HOT, radius=7.0))
        out.append(Prim("dot", [b], COLOR_ARC_CORE, 1.0, fill=COLOR_ARC_CORE, radius=3.0))
    else:
        gap = tip - hit
        if 0.05 < gap < r * 4:
            a, b = P((x, 0.0, tip)), P((x, 0.0, hit))
            out.append(Prim("poly", [a, b], COLOR_GAP, 1.2, dash=(3, 3)))
        if 0.5 < gap < r * 4:
            # chữ nằm cạnh mỏ, trên nền tối riêng - đè lên thân ống sáng vẫn đọc được
            out.append(Prim("text", [P((x + rt * 1.3 * side[0], rt * 1.3 * side[1],
                                        (tip + nozzle) / 2))],
                            COLOR_GAP, 1.0, fill=COLOR_HUD_BG, text=f"hở {gap:.1f} mm"))
    return out


# ----------------------------------------------------------------------
def scene_bounds(profile: MachineProfile, cam: Camera,
                 state: Optional[SimState] = None,
                 along_range: Optional[Tuple[float, float]] = None,
                 focus: str = "all",
                 ) -> Tuple[float, float, float, float]:
    """Khung bao của cảnh, dùng để canh tỉ lệ cho vừa khung nhìn.

    * ``focus="work"`` - **vùng cắt**: một khúc ống quanh mỏ cắt, đủ rộng để
      thấy trọn một lỗ hay một nhát cắt đứt.  Mỏ cắt đứng yên theo phương dọc
      (ống trượt qua dưới nó) nên khung này đứng yên suốt chương trình.
    * ``focus="all"`` - **toàn cảnh**: vì phôi trượt qua lại, khung phải bao
      trọn cả hành trình (``along_range`` = khoảng giá trị trục dọc), nếu không
      hình sẽ nhảy ra ngoài mép mỗi khi ống đi xa.
    """
    pose = MachinePose(profile, state or SimState())
    if focus == "work":
        r = pose.radius
        span = max(r * 4.0, 60.0)
        pts = [cam.project((x, y, z))
               for x in (-r * 2.1, r * 1.7) for y in (-span, span)
               for z in (-r * 1.2, pose.top_height + r * 2.6)]
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts), max(p[1] for p in pts))
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
    for x in (-pose.radius * 2.2, pose.radius * 1.75):        # cột và cần mang mỏ cắt
        pts.append(cam.project((x, 0.0, pose.top_height + pose.radius * 2.6)))
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


def axis_triad(profile: MachineProfile, cam: Camera, size: float = 30.0
               ) -> List[Tuple[float, float, str, str]]:
    """Ba trục nhỏ ở góc khung nhìn: (dx, dy điểm ảnh, màu, chữ cái trục máy).

    Giúp biết ngay mình đang nhìn từ phía nào sau khi xoay góc nhìn.
    """
    p = _pal.current()
    rows = [((1.0, 0.0, 0.0), p.axis_x, profile.letter(ROLE_CROSS) or "X"),
            ((0.0, 1.0, 0.0), p.axis_y, profile.letter(ROLE_ALONG) or "Y"),
            ((0.0, 0.0, 1.0), p.axis_z, profile.letter(ROLE_RADIAL) or "Z")]
    # trục nào chĩa vào màn hình thì vẽ trước để trục chĩa ra đè lên
    rows.sort(key=lambda t: cam.depth(t[0]))
    out = []
    for e, color, letter in rows:
        sx, sy = cam.project(e)
        out.append((sx * size, sy * size, color, letter))
    return out
