"""Bộ đọc DXF (bản ASCII) bằng thư viện chuẩn, không cần cài thêm gì.

DXF là tệp văn bản gồm từng cặp dòng: **mã nhóm** rồi **giá trị**.  Ta chỉ cần
phần ``ENTITIES`` và một số thực thể hình học thường gặp:

* ``LINE``, ``LWPOLYLINE``, ``POLYLINE``/``VERTEX`` - đoạn thẳng và đa tuyến
  (có xử lý *bulge*: đoạn cong của đa tuyến);
* ``CIRCLE``, ``ARC``, ``ELLIPSE`` - cung tròn và ellipse;
* ``SPLINE`` - đường cong tự do, tính đúng bằng De Boor chứ không nối thô các
  điểm điều khiển;
* ``POINT``, ``TEXT``... - bỏ qua.

Không hỗ trợ DXF nhị phân và khối ``INSERT`` lồng nhau; CAD nào cũng xuất được
DXF ASCII và ``Explode`` khối trước khi lưu.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .common import (
    Curve2D,
    ImportError_,
    Point,
    arc_points,
    bspline_points,
    dedupe,
    ellipse_points,
    join_curves,
)

# Hệ số quy đổi $INSUNITS của DXF sang milimét
_UNIT_MM = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0,
            8: 0.0000254, 9: 0.001, 10: 914.4, 11: 1e-7, 12: 1e-6, 13: 1e-3,
            14: 100.0, 15: 10000.0, 16: 1000000.0}


def _read_pairs(text: str) -> List[Tuple[int, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    pairs: List[Tuple[int, str]] = []
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1]
        i += 2
        if not code:
            continue
        try:
            pairs.append((int(code), value.strip()))
        except ValueError:
            continue
    return pairs


def _bulge_arc(p0: Point, p1: Point, bulge: float, tolerance: float) -> List[Point]:
    """Đoạn cong của LWPOLYLINE, mô tả bằng *bulge* = tang(1/4 góc ôm)."""
    if abs(bulge) < 1e-12:
        return [p0, p1]
    chord = math.dist(p0, p1)
    if chord < 1e-12:
        return [p0, p1]
    theta = 4.0 * math.atan(bulge)          # góc ôm, dấu cho biết chiều
    r = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    d = math.sqrt(max(0.0, r * r - (chord / 2) ** 2))
    ux, uy = (p1[0] - p0[0]) / chord, (p1[1] - p0[1]) / chord
    nx, ny = -uy, ux
    sign = 1.0 if theta > 0 else -1.0
    if abs(theta) > math.pi:
        sign = -sign
    cx, cy = mx - nx * d * sign, my - ny * d * sign
    a0 = math.degrees(math.atan2(p0[1] - cy, p0[0] - cx))
    a1 = math.degrees(math.atan2(p1[1] - cy, p1[0] - cx))
    pts = arc_points(cx, cy, r, a0, a1, tolerance, ccw=theta > 0)
    pts[0], pts[-1] = p0, p1
    return pts


def parse(text: str, tolerance: float = 0.05,
          layers: Optional[Sequence[str]] = None,
          join_tolerance: float = 0.05) -> List[Curve2D]:
    """Đọc nội dung một tệp DXF, trả về danh sách đường cong 2D (đơn vị mm)."""
    pairs = _read_pairs(text)
    if not pairs:
        raise ImportError_("Tệp DXF rỗng hoặc không đúng định dạng văn bản.")

    # tỉ lệ đơn vị từ phần HEADER
    unit_scale = 1.0
    for i, (code, value) in enumerate(pairs):
        if code == 9 and value.upper() == "$INSUNITS" and i + 1 < len(pairs):
            try:
                unit_scale = _UNIT_MM.get(int(pairs[i + 1][1]), 1.0)
            except ValueError:
                pass
            break

    # cắt lấy phần ENTITIES
    start = end = None
    for i, (code, value) in enumerate(pairs):
        if code == 2 and value.upper() == "ENTITIES" and start is None:
            start = i + 1
        elif start is not None and code == 0 and value.upper() == "ENDSEC":
            end = i
            break
    body = pairs[start:end] if start is not None else pairs

    # tách theo từng thực thể
    groups: List[List[Tuple[int, str]]] = []
    for code, value in body:
        if code == 0:
            groups.append([(code, value)])
        elif groups:
            groups[-1].append((code, value))

    wanted = {l.upper() for l in layers} if layers else None
    curves: List[Curve2D] = []
    pending_poly: Optional[Dict] = None

    def num(g: List[Tuple[int, str]], code: int, default: float = 0.0) -> float:
        for c, v in g:
            if c == code:
                try:
                    return float(v)
                except ValueError:
                    return default
        return default

    def all_num(g: List[Tuple[int, str]], code: int) -> List[float]:
        out = []
        for c, v in g:
            if c == code:
                try:
                    out.append(float(v))
                except ValueError:
                    pass
        return out

    def layer_of(g: List[Tuple[int, str]]) -> str:
        for c, v in g:
            if c == 8:
                return v
        return ""

    def add(points: Sequence[Point], closed: bool, kind: str, layer: str) -> None:
        pts = dedupe([(x * unit_scale, y * unit_scale) for x, y in points])
        if len(pts) >= 2:
            curves.append(Curve2D(pts, closed, kind, layer))

    for g in groups:
        kind = g[0][1].upper()
        layer = layer_of(g)
        if wanted is not None and layer.upper() not in wanted and kind != "VERTEX":
            continue

        if kind == "LINE":
            add([(num(g, 10), num(g, 20)), (num(g, 11), num(g, 21))], False, "LINE", layer)

        elif kind == "CIRCLE":
            add(arc_points(num(g, 10), num(g, 20), num(g, 40), 0.0, 360.0,
                           tolerance / max(unit_scale, 1e-9)), True, "CIRCLE", layer)

        elif kind == "ARC":
            add(arc_points(num(g, 10), num(g, 20), num(g, 40),
                           num(g, 50), num(g, 51),
                           tolerance / max(unit_scale, 1e-9)), False, "ARC", layer)

        elif kind == "ELLIPSE":
            add(ellipse_points(num(g, 10), num(g, 20), num(g, 11), num(g, 21),
                               num(g, 40, 1.0), num(g, 41, 0.0),
                               num(g, 42, 2 * math.pi),
                               tolerance / max(unit_scale, 1e-9)),
                abs(num(g, 42, 0.0) - num(g, 41, 0.0) - 2 * math.pi) < 1e-6,
                "ELLIPSE", layer)

        elif kind == "LWPOLYLINE":
            xs, ys = all_num(g, 10), all_num(g, 20)
            closed = int(num(g, 70)) & 1 == 1
            bulges: Dict[int, float] = {}
            idx = -1
            for c, v in g:
                if c == 10:
                    idx += 1
                elif c == 42 and idx >= 0:
                    try:
                        bulges[idx] = float(v)
                    except ValueError:
                        pass
            verts = list(zip(xs, ys))
            pts: List[Point] = []
            span = len(verts) if closed else len(verts) - 1
            for i in range(max(0, span)):
                a, b = verts[i], verts[(i + 1) % len(verts)]
                seg = _bulge_arc(a, b, bulges.get(i, 0.0),
                                 tolerance / max(unit_scale, 1e-9))
                pts.extend(seg if not pts else seg[1:])
            if not pts:
                pts = verts
            add(pts, closed, "LWPOLYLINE", layer)

        elif kind == "POLYLINE":
            pending_poly = {"closed": int(num(g, 70)) & 1 == 1,
                            "layer": layer, "pts": [], "bulges": []}

        elif kind == "VERTEX" and pending_poly is not None:
            pending_poly["pts"].append((num(g, 10), num(g, 20)))
            pending_poly["bulges"].append(num(g, 42))

        elif kind == "SEQEND" and pending_poly is not None:
            verts = pending_poly["pts"]
            closed = pending_poly["closed"]
            pts = []
            span = len(verts) if closed else len(verts) - 1
            for i in range(max(0, span)):
                a, b = verts[i], verts[(i + 1) % len(verts)]
                seg = _bulge_arc(a, b, pending_poly["bulges"][i],
                                 tolerance / max(unit_scale, 1e-9))
                pts.extend(seg if not pts else seg[1:])
            add(pts or verts, closed, "POLYLINE", pending_poly["layer"])
            pending_poly = None

        elif kind == "SPLINE":
            ctrl = list(zip(all_num(g, 10), all_num(g, 20)))
            fit = list(zip(all_num(g, 11), all_num(g, 21)))
            knots = all_num(g, 40)
            degree = int(num(g, 71, 3))
            flags = int(num(g, 70))
            closed = flags & 1 == 1
            if len(ctrl) >= 2:
                add(bspline_points(ctrl, degree, knots, closed=closed), closed,
                    "SPLINE", layer)
            elif len(fit) >= 2:
                add(fit, closed, "SPLINE", layer)

    if not curves:
        raise ImportError_(
            "Không tìm thấy biên dạng nào trong tệp DXF. "
            "Hãy kiểm tra bản vẽ có LINE/ARC/POLYLINE không, và nếu dùng khối "
            "(BLOCK/INSERT) thì hãy Explode trước khi lưu."
        )
    return join_curves(curves, join_tolerance) if join_tolerance > 0 else curves


def load(path: str, **kw) -> List[Curve2D]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse(fh.read(), **kw)
