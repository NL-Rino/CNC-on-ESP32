"""Xuất bản vẽ xem trước dạng SVG.

Hai khung nhìn bổ trợ cho nhau:

* **Trải phẳng** - đúng như tấm tôn khai triển, dễ đo kích thước thật.
* **Không gian 3D** - ống nhìn nghiêng, có ẩn nét khuất, để hình dung nhát cắt.

Xuất SVG nên mở được bằng trình duyệt, dán vào tài liệu, hoặc in ra để
đối chiếu - không cần cài thư viện đồ hoạ nào.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .config import MachineProfile
from .pathops import Pass
from .toolpath import CutPoint

Vec3 = Tuple[float, float, float]

from . import palette as _pal

COLOR_CUT = COLOR_MARK = COLOR_LEAD = COLOR_RAPID = ""
COLOR_PIPE = COLOR_GRID = COLOR_TEXT = COLOR_BG = COLOR_FILL = COLOR_VIEW = ""


def _sync_colors(p=None) -> None:
    """Bản vẽ xuất ra dùng đúng bảng màu đang xem trên giao diện."""
    global COLOR_CUT, COLOR_MARK, COLOR_LEAD, COLOR_RAPID
    global COLOR_PIPE, COLOR_GRID, COLOR_TEXT, COLOR_BG, COLOR_FILL, COLOR_VIEW
    p = p or _pal.current()
    COLOR_CUT = p.cut
    COLOR_MARK = p.mark
    COLOR_LEAD = p.lead
    COLOR_RAPID = p.rapid
    COLOR_PIPE = p.pipe_line
    COLOR_GRID = p.grid
    COLOR_TEXT = p.fg
    COLOR_BG = p.view_flat
    COLOR_FILL = p.pipe_fill
    COLOR_VIEW = p.view_bottom


_sync_colors()
_pal.on_change(_sync_colors)


class _Camera:
    """Phép chiếu trục đo đơn giản, có kiểm tra mặt khuất."""

    def __init__(self, azimuth_deg: float = 32.0, elevation_deg: float = 22.0):
        az = math.radians(azimuth_deg)
        el = math.radians(elevation_deg)
        self.dir = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
        d = self.dir
        up_w = (0.0, 0.0, 1.0)
        r = (up_w[1] * d[2] - up_w[2] * d[1],
             up_w[2] * d[0] - up_w[0] * d[2],
             up_w[0] * d[1] - up_w[1] * d[0])
        n = math.sqrt(sum(c * c for c in r)) or 1.0
        self.right = (r[0] / n, r[1] / n, r[2] / n)
        rr = self.right
        self.up = (d[1] * rr[2] - d[2] * rr[1],
                   d[2] * rr[0] - d[0] * rr[2],
                   d[0] * rr[1] - d[1] * rr[0])

    def project(self, p: Vec3) -> Tuple[float, float]:
        x = sum(a * b for a, b in zip(p, self.right))
        y = sum(a * b for a, b in zip(p, self.up))
        return (x, -y)

    def visible(self, normal: Vec3) -> bool:
        return sum(a * b for a, b in zip(normal, self.dir)) > -0.02


def _surface(section, x: float, v: float) -> Vec3:
    """Điểm bề mặt ở toạ độ trải phẳng (x, v) -> toạ độ 3D."""
    cx, cy = section.point_at(v % section.perimeter)
    return (x, cx, cy)


def _normal(section, v: float) -> Vec3:
    psi = math.radians(section.normal_angle(v % section.perimeter))
    return (0.0, math.sin(psi), math.cos(psi))


def _poly(points: Sequence[Tuple[float, float]], color: str, width: float = 1.4,
          dash: str = "", opacity: float = 1.0) -> str:
    if len(points) < 2:
        return ""
    d = " ".join(f"{'M' if i == 0 else 'L'}{p[0]:.2f},{p[1]:.2f}"
                 for i, p in enumerate(points))
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"{dash_attr}/>')


def render_svg(
    profile: MachineProfile,
    passes: Sequence[Pass],
    title: str = "",
    width: int = 1100,
    show_flat: bool = True,
    show_3d: bool = True,
    show_rapids: bool = True,
) -> str:
    """Dựng chuỗi SVG cho danh sách lượt chạy dao."""
    section = profile.pipe.section()
    circ = section.perimeter
    pipe_len = profile.pipe.length

    xs = [p.x for ps in passes for p in ps.points] or [0.0, pipe_len]
    x_min = min(min(xs), 0.0)
    x_max = max(max(xs), pipe_len * 0.2)
    span = max(x_max - x_min, 1.0)

    margin = 46.0
    scale = (width - 2 * margin) / span
    flat_h = circ * scale
    layout = _iso_layout(passes, section, x_min, x_max, width, margin, scale)
    iso_h = (layout[3] - layout[2]) * layout[0] + 30 if show_3d else 0.0
    total_h = margin * 2 + (flat_h + 60 if show_flat else 0) + (iso_h + 40 if show_3d else 0)

    out: List[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {width:.0f} {total_h:.0f}">'
    )
    out.append(f'<rect width="100%" height="100%" fill="{COLOR_BG}"/>')
    out.append(
        f'<text x="{margin}" y="26" font-family="sans-serif" font-size="15" '
        f'fill="{COLOR_TEXT}">{_esc(title or "PipeCut Studio")}</text>'
    )
    out.append(
        f'<text x="{margin}" y="44" font-family="sans-serif" font-size="11" '
        f'fill="{COLOR_TEXT}">Ống D{profile.pipe.outer_diameter:.0f} x '
        f'{profile.pipe.wall_thickness:.1f} mm - chu vi {circ:.1f} mm - '
        f'{len(passes)} đường cắt</text>'
    )

    y = margin + 30
    if show_flat:
        out.extend(_render_flat(passes, section, x_min, scale, margin, y, span, circ, show_rapids))
        y += flat_h + 60
    if show_3d:
        out.extend(_render_iso(passes, section, x_min, x_max, margin, y, layout, show_rapids))
    out.append(_legend(width, total_h - 14))
    out.append("</svg>")
    return "\n".join(out)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _render_flat(passes, section, x_min, scale, margin, y0, span, circ, show_rapids) -> List[str]:
    out: List[str] = []
    out.append(f'<text x="{margin}" y="{y0 - 10:.1f}" font-family="sans-serif" '
               f'font-size="12" fill="{COLOR_TEXT}">Trải phẳng (ngang: dọc ống, dọc: chu vi)</text>')
    out.append(f'<rect x="{margin:.1f}" y="{y0:.1f}" width="{span * scale:.1f}" '
               f'height="{circ * scale:.1f}" fill="{COLOR_FILL}" stroke="{COLOR_PIPE}"/>')
    # lưới 90 độ
    for k in range(1, 4):
        yy = y0 + section.s_of_theta(90.0 * k) * scale
        out.append(f'<line x1="{margin:.1f}" y1="{yy:.1f}" x2="{margin + span * scale:.1f}" '
                   f'y2="{yy:.1f}" stroke="{COLOR_GRID}" stroke-width="1"/>')
        out.append(f'<text x="{margin - 6:.1f}" y="{yy + 3:.1f}" text-anchor="end" '
                   f'font-family="sans-serif" font-size="9" fill="{COLOR_TEXT}">{90 * k}°</text>')

    def to_xy(p: CutPoint) -> Tuple[float, float]:
        return (margin + (p.x - x_min) * scale, y0 + (p.v % circ) * scale)

    prev_end: Optional[CutPoint] = None
    for ps in passes:
        if show_rapids and prev_end is not None:
            out.append(_poly([to_xy(prev_end), to_xy(ps.points[0])], COLOR_RAPID, 1.0, "4,3", 0.8))
        color = COLOR_MARK if ps.kind == "mark" else COLOR_CUT
        segments: List[Tuple[str, List[Tuple[float, float]]]] = [(ps.points[0].kind, [])]
        prev_v = None
        for p in ps.points:
            v = p.v % circ
            if (prev_v is not None and abs(v - prev_v) > circ / 2) or \
                    p.kind != segments[-1][0]:
                segments.append((p.kind, []))
            prev_v = v
            segments[-1][1].append(to_xy(p))
        for kind, seg in segments:
            if kind == "cut":
                out.append(_poly(seg, color, 1.6))
            else:   # pha xoay góc: không cắt nên vẽ nét đứt
                out.append(_poly(seg, COLOR_RAPID, 1.2, "4,3", 0.9))
        # đoạn vào dao
        if ps.lead_in_count:
            out.append(_poly([to_xy(p) for p in ps.points[:ps.lead_in_count + 1]], COLOR_LEAD, 1.6))
        p0 = to_xy(ps.points[0])
        out.append(f'<circle cx="{p0[0]:.1f}" cy="{p0[1]:.1f}" r="2.6" fill="{COLOR_LEAD}"/>')
        prev_end = ps.points[-1]
    return out


def _iso_layout(passes, section, x_min, x_max, width, margin, scale):
    """Tính tỉ lệ và khung bao của hình chiếu trục đo trước khi vẽ.

    Phải biết trước chiều cao thật của hình 3D thì mới đặt được chiều cao
    trang SVG, nếu không hình sẽ tràn ra ngoài khung nhìn.
    """
    cam = _Camera()
    pts: List[Tuple[float, float]] = []
    per = section.perimeter
    for ps in passes:
        for p in ps.points:
            pts.append(cam.project(_surface(section, p.x, p.v)))
    for xx in (x_min, x_max):
        for i in range(61):
            pts.append(cam.project(_surface(section, xx, per * i / 60)))
    if not pts:
        return (scale, 0.0, 0.0, 0.0)
    bx0 = min(p[0] for p in pts); bx1 = max(p[0] for p in pts)
    by0 = min(p[1] for p in pts); by1 = max(p[1] for p in pts)
    s = min((width - 2 * margin) / max(bx1 - bx0, 1e-6), scale)
    return (s, bx0, by0, by1)


def _render_iso(passes, section, x_min, x_max, margin, y0, layout, show_rapids) -> List[str]:
    out: List[str] = []
    cam = _Camera()
    out.append(f'<text x="{margin}" y="{y0 - 6:.1f}" font-family="sans-serif" '
               f'font-size="12" fill="{COLOR_TEXT}">Hình chiếu trục đo (nét khuất được ẩn)</text>')
    s, bx0, by0, by1 = layout
    if s <= 0:
        return out
    ox = margin - bx0 * s
    oy = y0 + 10 - by0 * s

    def tr(p: Tuple[float, float]) -> Tuple[float, float]:
        return (ox + p[0] * s, oy + p[1] * s)

    # thân phôi: đường sinh + hai vành đầu
    per = section.perimeter
    marks = sorted(set([per * k / 24 for k in range(24)]
                       + [b for b in section.breakpoints() if b < per]))
    for v in marks:
        if not cam.visible(_normal(section, v)):
            continue
        a = tr(cam.project(_surface(section, x_min, v)))
        b = tr(cam.project(_surface(section, x_max, v)))
        out.append(_poly([a, b], COLOR_PIPE, 0.6, "", 0.55))
    for xx in (x_min, x_max):
        ring = [tr(cam.project(_surface(section, xx, per * i / 96)))
                for i in range(97)]
        out.append(_poly(ring, COLOR_PIPE, 1.0, "", 0.9))

    prev_end: Optional[CutPoint] = None
    for ps in passes:
        color = COLOR_MARK if ps.kind == "mark" else COLOR_CUT
        seg: List[Tuple[float, float]] = []
        seg_kind = ps.points[0].kind

        def flush_iso():
            if len(seg) > 1:
                if seg_kind == "cut":
                    out.append(_poly(seg, color, 1.8))
                else:
                    out.append(_poly(seg, COLOR_RAPID, 1.2, "4,3", 0.9))
            seg.clear()

        for p in ps.points:
            if p.kind != seg_kind:
                flush_iso()
                seg_kind = p.kind
            if cam.visible(_normal(section, p.v)):
                seg.append(tr(cam.project(_surface(section, p.x, p.v))))
            else:
                flush_iso()
        flush_iso()
        if show_rapids and prev_end is not None:
            a = tr(cam.project(_surface(section, prev_end.x, prev_end.v)))
            b = tr(cam.project(_surface(section, ps.points[0].x, ps.points[0].v)))
            out.append(_poly([a, b], COLOR_RAPID, 1.0, "4,3", 0.7))
        prev_end = ps.points[-1]
    return out


def _legend(width: float, y: float) -> str:
    items = [(COLOR_CUT, "đường cắt"), (COLOR_LEAD, "vào dao / điểm mồi"),
             (COLOR_MARK, "vạch dấu"), (COLOR_RAPID, "chạy không")]
    parts = []
    x = 46.0
    for color, label in items:
        parts.append(f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x + 18:.0f}" y2="{y:.0f}" '
                     f'stroke="{color}" stroke-width="2.4"/>')
        parts.append(f'<text x="{x + 23:.0f}" y="{y + 4:.0f}" font-family="sans-serif" '
                     f'font-size="10" fill="{COLOR_TEXT}">{label}</text>')
        x += 32 + len(label) * 5.6
    return "".join(parts)


def save_svg(path: str, profile: MachineProfile, passes: Sequence[Pass],
             title: str = "", **kw) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_svg(profile, passes, title=title, **kw))


# --------------------------------------------------------------------------
# Ảnh chụp khung mô phỏng máy
# --------------------------------------------------------------------------
def render_machine_svg(
    profile: MachineProfile,
    state,
    trace=(),
    title: str = "",
    width: int = 1000,
    height: int = 560,
    azimuth: Optional[float] = None,
    elevation: Optional[float] = None,
    show_frame: bool = True,
    along_range=None,
    focus: str = "work",
    plan=(),
) -> str:
    """Chụp lại khung mô phỏng máy tại một thời điểm thành ảnh SVG.

    Dùng đúng bộ dựng cảnh của tab Mô phỏng nên hình ảnh giống hệt những gì
    thấy trên giao diện - tiện để in kèm phiếu công nghệ hoặc gửi cho khách.
    """
    from .machinescene import Camera, axis_readout, axis_triad, build_scene, scene_bounds

    cam = Camera(Camera.DEFAULT_AZIMUTH if azimuth is None else azimuth,
                 Camera.DEFAULT_ELEVATION if elevation is None else elevation)
    prims = build_scene(profile, state, list(trace), cam, show_frame=show_frame,
                        plan=list(plan))
    x0, y0, x1, y1 = scene_bounds(profile, cam, state, along_range, focus=focus)
    pad = 40.0
    scale = min((width - 2 * pad) / max(x1 - x0, 1e-6),
                (height - 2 * pad) / max(y1 - y0, 1e-6))
    ox = width / 2 - (x0 + x1) / 2 * scale
    oy = height / 2 - (y0 + y1) / 2 * scale

    def px(p):
        return (ox + p[0] * scale, oy + p[1] * scale)

    # Nền chuyển sắc dọc giống hệt khung nhìn trên màn hình, để ảnh xuất ra
    # nhìn liền mạch với những gì người dùng vừa xem.
    pal = _pal.current()
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">',
           '<defs><linearGradient id="nen" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0%" stop-color="{pal.view_top}"/>'
           f'<stop offset="100%" stop-color="{pal.view_bottom}"/>'
           '</linearGradient></defs>',
           '<rect width="100%" height="100%" fill="url(#nen)"/>']
    for prim in prims:
        pts = [px(p) for p in prim.points]
        if prim.kind == "fill" and len(pts) >= 3:
            d = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
            out.append(f'<polygon points="{d}" fill="{prim.fill or "none"}" '
                       f'stroke="{prim.color}" stroke-width="{prim.width}" '
                       f'stroke-linejoin="round"/>')
        elif prim.kind == "dot" and pts:
            out.append(f'<circle cx="{pts[0][0]:.2f}" cy="{pts[0][1]:.2f}" '
                       f'r="{prim.radius}" fill="{prim.fill or prim.color}"/>')
        elif prim.kind == "text" and pts:
            if prim.fill:
                tw = len(prim.text) * 7.2 + 8
                out.append(f'<rect x="{pts[0][0] - 4:.1f}" y="{pts[0][1] - 9:.1f}" '
                           f'width="{tw:.0f}" height="18" rx="3" fill="{prim.fill}"/>')
            out.append(f'<text x="{pts[0][0]:.1f}" y="{pts[0][1] + 4:.1f}" '
                       f'font-family="sans-serif" font-size="12" font-weight="bold" '
                       f'fill="{prim.color}">{_esc(prim.text)}</text>')
        elif len(pts) >= 2:
            out.append(_poly(pts, prim.color, prim.width,
                             dash=",".join(str(v) for v in prim.dash)))
    # Bảng số: chữ sáng trên nền tối - khung nhìn luôn nền xanh ở cả hai chế độ
    pal = _pal.current()
    rows = axis_readout(profile, state)
    extra = [f"{profile.pipe.size_text} × dài {profile.pipe.length:g} mm"]
    if getattr(state, "torch", False):
        extra.append("● NGUỒN CẮT ĐANG BẬT")
    box_w = max(len(r) for r in rows + extra) * 7.9 + 24
    box_h = 18 * len(rows) + 22 * len(extra) + 16
    out.append(f'<rect x="8" y="8" width="{box_w:.0f}" height="{box_h:.0f}" rx="4" '
               f'fill="{pal.hud_bg}" stroke="{pal.machine_edge}"/>')
    y = 28.0
    for row in rows:
        out.append(f'<text x="18" y="{y:.0f}" font-family="Consolas, DejaVu Sans Mono, Courier New, monospace" font-size="13" '
                   f'fill="{pal.hud_fg}" xml:space="preserve">{_esc(row)}</text>')
        y += 18
    for k, line in enumerate(extra):
        color = pal.torch_on if k == 1 else pal.hud_fg
        weight = ' font-weight="bold"' if k == 1 else ""
        out.append(f'<text x="18" y="{y + 6:.0f}" font-family="sans-serif" font-size="12" '
                   f'fill="{color}"{weight}>{_esc(line)}</text>')
        y += 22
    ox, oy = 46, height - 46
    out.append(f'<circle cx="{ox}" cy="{oy}" r="34" fill="{pal.hud_bg}"/>')
    for dx, dy, color, letter in axis_triad(profile, cam, 24.0):
        out.append(f'<line x1="{ox}" y1="{oy}" x2="{ox + dx:.1f}" y2="{oy + dy:.1f}" '
                   f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>')
        out.append(f'<text x="{ox + dx * 1.3:.1f}" y="{oy + dy * 1.3 + 4:.1f}" '
                   f'text-anchor="middle" font-family="sans-serif" font-size="12" '
                   f'font-weight="bold" fill="{color}">{letter}</text>')
    if title:
        tw = len(title) * 7.4 + 20
        out.append(f'<rect x="{width - tw - 8:.0f}" y="8" width="{tw:.0f}" height="24" '
                   f'rx="4" fill="{pal.hud_bg}"/>')
        out.append(f'<text x="{width - 18}" y="25" text-anchor="end" '
                   f'font-family="sans-serif" font-size="13" fill="{pal.hud_fg}">'
                   f'{_esc(title)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def save_machine_svg(path: str, profile: MachineProfile, state, trace=(),
                     title: str = "", **kw) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_machine_svg(profile, state, trace, title=title, **kw))
