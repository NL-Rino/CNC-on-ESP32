"""Bộ đọc SVG bằng thư viện chuẩn (``xml.etree``).

Hỗ trợ ``path`` (đủ các lệnh M L H V C S Q T A Z), ``line``, ``rect``,
``circle``, ``ellipse``, ``polyline``, ``polygon``, kèm thuộc tính
``transform`` (translate / scale / rotate / matrix) lồng qua các nhóm ``g``.

Hai điểm khác biệt của SVG so với bản vẽ cơ khí, đã xử lý sẵn:

* **Trục Y của SVG hướng xuống** - mặc định lật lại cho đúng chiều bản vẽ;
* **Đơn vị là "user unit"**, thường quy ra 96 điểm ảnh trên một inch.  Nếu thẻ
  ``svg`` khai báo ``width``/``height`` kèm đơn vị thật (mm, cm, in) và có
  ``viewBox`` thì tỉ lệ được suy ra chính xác từ đó.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Sequence, Tuple

from .common import (
    Curve2D,
    ImportError_,
    Point,
    arc_points,
    dedupe,
    ellipse_points,
    join_curves,
)

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])")
_UNIT = re.compile(r"([-+0-9.eE]+)\s*([a-z%]*)")
_PX_PER = {"": 1.0, "px": 1.0, "mm": 96.0 / 25.4, "cm": 960.0 / 25.4,
           "in": 96.0, "pt": 96.0 / 72.0, "pc": 16.0}


def _floats(text: str) -> List[float]:
    return [float(m.group()) for m in _NUM.finditer(text or "")]


def _length_px(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = _UNIT.match(text.strip())
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    return value * _PX_PER.get(m.group(2), 1.0)


# --------------------------------------------------------------------------
# Ma trận biến đổi 2D: (a, b, c, d, e, f)
# --------------------------------------------------------------------------
_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(m: Tuple[float, ...], n: Tuple[float, ...]) -> Tuple[float, ...]:
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _rounded_rect(x: float, y: float, w: float, h: float,
                  rx: float, ry: float, tolerance: float) -> List[Tuple[float, float]]:
    """Chữ nhật bo góc của SVG: bốn cạnh thẳng nối bằng bốn cung ellipse."""
    pts: List[Tuple[float, float]] = [(x + rx, y)]
    corners = [
        (x + w - rx, y + ry, 270.0, 360.0),      # trên phải
        (x + w - rx, y + h - ry, 0.0, 90.0),     # dưới phải
        (x + rx, y + h - ry, 90.0, 180.0),       # dưới trái
        (x + rx, y + ry, 180.0, 270.0),          # trên trái
    ]
    for cx, cy, a0, a1 in corners:
        arc = ellipse_points(cx, cy, rx, 0.0, ry / rx,
                             math.radians(a0), math.radians(a1), tolerance)
        pts.append((arc[0][0], arc[0][1]))
        pts.extend(arc[1:])
    pts.append(pts[0])
    return dedupe(pts)


def _apply(m: Tuple[float, ...], p: Point) -> Point:
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def _parse_transform(text: Optional[str]) -> Tuple[float, ...]:
    m = _IDENTITY
    if not text:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        v = _floats(args)
        name = name.lower()
        if name == "translate":
            m = _mul(m, (1, 0, 0, 1, v[0] if v else 0.0, v[1] if len(v) > 1 else 0.0))
        elif name == "scale":
            sx = v[0] if v else 1.0
            sy = v[1] if len(v) > 1 else sx
            m = _mul(m, (sx, 0, 0, sy, 0, 0))
        elif name == "rotate":
            a = math.radians(v[0] if v else 0.0)
            ca, sa = math.cos(a), math.sin(a)
            if len(v) >= 3:
                m = _mul(m, (1, 0, 0, 1, v[1], v[2]))
                m = _mul(m, (ca, sa, -sa, ca, 0, 0))
                m = _mul(m, (1, 0, 0, 1, -v[1], -v[2]))
            else:
                m = _mul(m, (ca, sa, -sa, ca, 0, 0))
        elif name == "matrix" and len(v) >= 6:
            m = _mul(m, tuple(v[:6]))
        elif name == "skewx" and v:
            m = _mul(m, (1, 0, math.tan(math.radians(v[0])), 1, 0, 0))
        elif name == "skewy" and v:
            m = _mul(m, (1, math.tan(math.radians(v[0])), 0, 1, 0, 0))
    return m


# --------------------------------------------------------------------------
# Đường cong Bézier và cung ellipse của lệnh path
# --------------------------------------------------------------------------
def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float) -> List[Point]:
    span = (math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3))
    n = max(4, min(96, int(math.sqrt(span / max(tolerance, 1e-6)) * 2)))
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def _svg_arc(p0: Point, rx: float, ry: float, rot_deg: float, large: int,
             sweep: int, p1: Point, tolerance: float) -> List[Point]:
    """Lệnh ``A`` của SVG - cung ellipse qua hai điểm."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot_deg)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx2, dy2 = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cosp * dx2 + sinp * dy2
    y1 = -sinp * dx2 + cosp * dy2
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp = coef * rx * y1 / ry
    cyp = -coef * ry * x1 / rx
    cx = cosp * cxp - sinp * cyp + (p0[0] + p1[0]) / 2
    cy = sinp * cxp + cosp * cyp + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / n))) if n else 0.0
        return -a if ux * vy - uy * vx < 0 else a

    t0 = angle(1, 0, (x1 - cxp) / rx, (y1 - cyp) / ry)
    dt = angle((x1 - cxp) / rx, (y1 - cyp) / ry, (-x1 - cxp) / rx, (-y1 - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    r_big = max(rx, ry)
    ratio = max(-1.0, min(1.0, 1.0 - tolerance / max(r_big, 1e-6)))
    step = 2 * math.acos(ratio) if r_big > tolerance else math.pi / 6
    n = max(3, int(math.ceil(abs(dt) / max(step, 1e-6))))
    out = []
    for i in range(1, n + 1):
        t = t0 + dt * i / n
        x = rx * math.cos(t)
        y = ry * math.sin(t)
        out.append((cosp * x - sinp * y + cx, sinp * x + cosp * y + cy))
    return out


def _parse_path(d: str, tolerance: float) -> List[Tuple[List[Point], bool]]:
    tokens = [t for t in _CMD.split(d or "") if t.strip()]
    subs: List[Tuple[List[Point], bool]] = []
    cur: List[Point] = []
    pos: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    prev_ctrl: Optional[Point] = None
    prev_cmd = ""
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        if not _CMD.fullmatch(cmd):
            i += 1
            continue
        args = _floats(tokens[i + 1]) if i + 1 < len(tokens) else []
        i += 2
        rel = cmd.islower()
        c = cmd.upper()
        k = 0
        first = True
        while True:
            if c == "Z":
                if cur:
                    cur.append(start)
                    subs.append((cur, True))
                    cur = []
                pos = start
                break
            need = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
                    "Q": 4, "T": 2, "A": 7}[c]
            if k + need > len(args):
                break
            a = args[k:k + need]
            k += need
            if c == "M":
                if cur:
                    subs.append((cur, False))
                p = (a[0], a[1])
                pos = (pos[0] + p[0], pos[1] + p[1]) if rel else p
                start = pos
                cur = [pos]
                c = "L"          # các cặp số tiếp theo của M là lệnh L
            elif c in ("L", "T"):
                p = (a[0], a[1])
                nxt = (pos[0] + p[0], pos[1] + p[1]) if rel else p
                if c == "T":
                    ctrl = pos if prev_ctrl is None else (2 * pos[0] - prev_ctrl[0],
                                                          2 * pos[1] - prev_ctrl[1])
                    cur.extend(_bezier(pos, ctrl, ctrl, nxt, tolerance))
                    prev_ctrl = ctrl
                else:
                    cur.append(nxt)
                    prev_ctrl = None
                pos = nxt
            elif c == "H":
                nxt = (pos[0] + a[0], pos[1]) if rel else (a[0], pos[1])
                cur.append(nxt)
                pos, prev_ctrl = nxt, None
            elif c == "V":
                nxt = (pos[0], pos[1] + a[0]) if rel else (pos[0], a[0])
                cur.append(nxt)
                pos, prev_ctrl = nxt, None
            elif c in ("C", "S"):
                if c == "C":
                    c1 = (pos[0] + a[0], pos[1] + a[1]) if rel else (a[0], a[1])
                    c2 = (pos[0] + a[2], pos[1] + a[3]) if rel else (a[2], a[3])
                    nxt = (pos[0] + a[4], pos[1] + a[5]) if rel else (a[4], a[5])
                else:
                    c1 = pos if prev_ctrl is None else (2 * pos[0] - prev_ctrl[0],
                                                        2 * pos[1] - prev_ctrl[1])
                    c2 = (pos[0] + a[0], pos[1] + a[1]) if rel else (a[0], a[1])
                    nxt = (pos[0] + a[2], pos[1] + a[3]) if rel else (a[2], a[3])
                cur.extend(_bezier(pos, c1, c2, nxt, tolerance))
                pos, prev_ctrl = nxt, c2
            elif c == "Q":
                q = (pos[0] + a[0], pos[1] + a[1]) if rel else (a[0], a[1])
                nxt = (pos[0] + a[2], pos[1] + a[3]) if rel else (a[2], a[3])
                c1 = (pos[0] + 2 / 3 * (q[0] - pos[0]), pos[1] + 2 / 3 * (q[1] - pos[1]))
                c2 = (nxt[0] + 2 / 3 * (q[0] - nxt[0]), nxt[1] + 2 / 3 * (q[1] - nxt[1]))
                cur.extend(_bezier(pos, c1, c2, nxt, tolerance))
                pos, prev_ctrl = nxt, q
            elif c == "A":
                nxt = (pos[0] + a[5], pos[1] + a[6]) if rel else (a[5], a[6])
                cur.extend(_svg_arc(pos, a[0], a[1], a[2], int(a[3]), int(a[4]),
                                    nxt, tolerance))
                pos, prev_ctrl = nxt, None
            first = False
            if k >= len(args):
                break
        prev_cmd = c
    if cur:
        subs.append((cur, False))
    return subs


# --------------------------------------------------------------------------
def parse(text: str, tolerance: float = 0.05, scale: Optional[float] = None,
          flip_y: bool = True, join_tolerance: float = 0.05) -> List[Curve2D]:
    """Đọc nội dung một tệp SVG, trả về danh sách đường cong (đơn vị mm)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ImportError_(f"Tệp SVG hỏng: {exc}") from exc

    # tỉ lệ: ưu tiên width/height thật kèm viewBox
    px_to_mm = 25.4 / 96.0
    if scale is None:
        vb = _floats(root.get("viewBox") or "")
        w_px = _length_px(root.get("width"))
        if len(vb) == 4 and w_px and vb[2] > 0:
            w_mm = w_px * 25.4 / 96.0
            px_to_mm = w_mm / vb[2]
    else:
        px_to_mm = scale

    curves: List[Curve2D] = []

    def tag_of(el) -> str:
        return el.tag.split("}")[-1].lower()

    def walk(el, matrix) -> None:
        m = _mul(matrix, _parse_transform(el.get("transform")))
        name = tag_of(el)
        subs: List[Tuple[List[Point], bool]] = []
        if name == "path":
            subs = _parse_path(el.get("d") or "", tolerance / max(px_to_mm, 1e-9))
        elif name == "line":
            subs = [([(float(el.get("x1", 0)), float(el.get("y1", 0))),
                      (float(el.get("x2", 0)), float(el.get("y2", 0)))], False)]
        elif name in ("polyline", "polygon"):
            v = _floats(el.get("points") or "")
            pts = list(zip(v[0::2], v[1::2]))
            if pts:
                subs = [(pts + ([pts[0]] if name == "polygon" else []),
                         name == "polygon")]
        elif name == "rect":
            x = float(el.get("x", 0)); y = float(el.get("y", 0))
            w = float(el.get("width", 0)); h = float(el.get("height", 0))
            if w > 0 and h > 0:
                # rx/ry là bo góc; theo chuẩn SVG, thiếu một cái thì lấy cái kia
                rx = el.get("rx"); ry = el.get("ry")
                rx = float(rx) if rx not in (None, "auto") else (
                    float(ry) if ry not in (None, "auto") else 0.0)
                ry = float(ry) if ry not in (None, "auto") else rx
                rx = max(0.0, min(rx, w / 2)); ry = max(0.0, min(ry, h / 2))
                if rx > 0 and ry > 0:
                    subs = [(_rounded_rect(x, y, w, h, rx, ry,
                                           tolerance / max(px_to_mm, 1e-9)), True)]
                else:
                    subs = [([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], True)]
        elif name == "circle":
            r = float(el.get("r", 0))
            if r > 0:
                subs = [(arc_points(float(el.get("cx", 0)), float(el.get("cy", 0)), r,
                                    0, 360, tolerance / max(px_to_mm, 1e-9)), True)]
        elif name == "ellipse":
            rx = float(el.get("rx", 0)); ry = float(el.get("ry", 0))
            if rx > 0 and ry > 0:
                subs = [(ellipse_points(float(el.get("cx", 0)), float(el.get("cy", 0)),
                                        rx, 0.0, ry / rx, 0.0, 2 * math.pi,
                                        tolerance / max(px_to_mm, 1e-9)), True)]
        for pts, closed in subs:
            out = [_apply(m, p) for p in pts]
            out = [(x * px_to_mm, (-y if flip_y else y) * px_to_mm) for x, y in out]
            out = dedupe(out)
            if len(out) >= 2:
                curves.append(Curve2D(out, closed, name, el.get("id", "")))
        for child in el:
            walk(child, m)

    walk(root, _IDENTITY)
    if not curves:
        raise ImportError_("Không tìm thấy hình nào trong tệp SVG "
                           "(chỉ đọc path, line, rect, circle, ellipse, polyline, polygon).")
    return join_curves(curves, join_tolerance) if join_tolerance > 0 else curves


def load(path: str, **kw) -> List[Curve2D]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse(fh.read(), **kw)
