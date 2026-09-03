"""Bộ đọc mô hình 3D (STL nhị phân/ASCII và OBJ) để lấy đường cắt trên phôi.

Cách làm
--------
Mô hình đưa vào là **chi tiết đã hoàn thiện**: một đoạn ống/hộp đã bị cắt.  Bề
mặt của nó gồm hai phần:

1. phần vẫn nằm **trên mặt phôi gốc** (mặt trụ hoặc mặt hộp);
2. phần **mặt cắt mới** do dao tạo ra.

Đường cắt chính là **ranh giới giữa hai phần đó**.  Thuật toán:

* tính khoảng cách có dấu từ mỗi đỉnh tới mặt phôi;
* tam giác nào có cả ba đỉnh nằm sát mặt phôi thì đánh dấu "còn nguyên";
* cạnh nào chỉ thuộc **một** tam giác "còn nguyên" chính là cạnh biên;
* nối các cạnh biên lại thành vòng, rồi đổi từng đỉnh sang toạ độ trải phẳng
  ``(u, v)`` để đưa vào đúng dây chuyền xử lý như mọi biên dạng khác.

Cách này chịu được lưới thô hay mịn, và không cần thư viện hình học nào.

**STEP/IGES không đọc được** - đó là định dạng B-rep, muốn đọc phải kèm cả một
nhân hình học (OpenCASCADE) rất nặng.  Mọi phần mềm CAD đều xuất được STL, nên
hãy xuất STL với sai số lưới nhỏ (0,01-0,05 mm) rồi nạp vào đây.
"""

from __future__ import annotations

import math
import struct
from typing import Dict, List, Optional, Sequence, Tuple

from .common import Curve2D, ImportError_, Point, dedupe

Vec3 = Tuple[float, float, float]
Tri = Tuple[Vec3, Vec3, Vec3]

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


# --------------------------------------------------------------------------
# Đọc tệp
# --------------------------------------------------------------------------
def load_triangles(path: str) -> List[Tri]:
    """Đọc tam giác từ tệp STL (nhị phân hoặc ASCII) hoặc OBJ."""
    low = path.lower()
    if low.endswith(".obj"):
        return _read_obj(path)
    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw:
        raise ImportError_("Tệp mô hình rỗng.")
    # STL nhị phân: 84 byte đầu + 50 byte mỗi tam giác.  Một số phần mềm ghi
    # thêm vài byte thừa ở cuối, nên chỉ cần đủ chỗ chứa là đọc.
    if len(raw) >= 84:
        count = struct.unpack_from("<I", raw, 80)[0]
        if count > 0 and 84 + count * 50 <= len(raw):
            return _read_stl_binary(raw, count)
    text = raw.decode("utf-8", "replace")
    if "facet" in text or text.lstrip().lower().startswith("solid"):
        return _read_stl_ascii(text)
    raise ImportError_(
        "Không nhận ra định dạng mô hình. Hỗ trợ STL (nhị phân/ASCII) và OBJ. "
        "Nếu đang có STEP/IGES, hãy xuất lại sang STL từ phần mềm CAD."
    )


def _read_stl_binary(raw: bytes, count: int) -> List[Tri]:
    tris: List[Tri] = []
    off = 84
    for _ in range(count):
        vals = struct.unpack_from("<12f", raw, off)
        tris.append(((vals[3], vals[4], vals[5]),
                     (vals[6], vals[7], vals[8]),
                     (vals[9], vals[10], vals[11])))
        off += 50
    return tris


def _read_stl_ascii(text: str) -> List[Tri]:
    tris: List[Tri] = []
    verts: List[Vec3] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].lower() == "vertex":
            try:
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                continue
            if len(verts) == 3:
                tris.append((verts[0], verts[1], verts[2]))
                verts = []
        elif parts and parts[0].lower() == "endfacet":
            verts = []
    if not tris:
        raise ImportError_("Tệp STL ASCII không chứa tam giác nào.")
    return tris


def _read_obj(path: str) -> List[Tri]:
    verts: List[Vec3] = []
    tris: List[Tri] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v" and len(parts) >= 4:
                try:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    pass
            elif parts[0] == "f" and len(parts) >= 4:
                idx = []
                for token in parts[1:]:
                    try:
                        i = int(token.split("/")[0])
                    except ValueError:
                        continue
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):     # quạt tam giác
                    try:
                        tris.append((verts[idx[0]], verts[idx[k]], verts[idx[k + 1]]))
                    except IndexError:
                        pass
    if not tris:
        raise ImportError_("Tệp OBJ không chứa mặt nào.")
    return tris


# --------------------------------------------------------------------------
# Đặt phôi vào mô hình
# --------------------------------------------------------------------------
def detect_axis(tris: Sequence[Tri]) -> str:
    """Đoán trục của phôi: chiều dài nhất của khối bao."""
    lo = [min(v[i] for t in tris for v in t) for i in range(3)]
    hi = [max(v[i] for t in tris for v in t) for i in range(3)]
    span = [hi[i] - lo[i] for i in range(3)]
    return "xyz"[span.index(max(span))]


def measure(tris: Sequence[Tri], axis: str = "auto") -> Dict[str, float]:
    """Đo mô hình: trục phôi, chiều dài, tâm và bán kính bao của tiết diện."""
    axis = detect_axis(tris) if axis == "auto" else axis.lower()
    ai = AXIS_INDEX[axis]
    others = [i for i in range(3) if i != ai]
    along = [v[ai] for t in tris for v in t]
    c0 = [v[others[0]] for t in tris for v in t]
    c1 = [v[others[1]] for t in tris for v in t]
    cx = (min(c0) + max(c0)) / 2
    cy = (min(c1) + max(c1)) / 2
    radius = max(math.hypot(a - cx, b - cy) for a, b in zip(c0, c1))
    return {"axis": axis, "length": max(along) - min(along),
            "along_min": min(along), "along_max": max(along),
            "center_x": cx, "center_y": cy, "radius": radius,
            "width": max(c0) - min(c0), "height": max(c1) - min(c1),
            "triangles": float(len(tris))}


# --------------------------------------------------------------------------
# Lấy đường cắt
# --------------------------------------------------------------------------
def _key(p: Point, grid: float) -> Tuple[int, int]:
    return (int(round(p[0] / grid)), int(round(p[1] / grid)))


def extract_cut_curves(
    tris: Sequence[Tri],
    section,
    axis: str = "auto",
    center: Optional[Tuple[float, float]] = None,
    roll_deg: float = 0.0,
    surface_tolerance: float = 0.4,
    weld: float = 0.05,
    notes: Optional[List[str]] = None,
) -> List[Curve2D]:
    """Tìm các đường cắt trên bề mặt phôi, trả về toạ độ trải phẳng (u, v).

    ``notes`` nếu được truyền vào sẽ nhận thêm các cảnh báo về mức độ khớp giữa
    mô hình và tiết diện phôi đã khai báo.
    """
    if not tris:
        raise ImportError_("Mô hình không có tam giác nào.")
    info = measure(tris, axis)
    ai = AXIS_INDEX[info["axis"]]
    others = [i for i in range(3) if i != ai]
    cx, cy = center if center is not None else (info["center_x"], info["center_y"])
    roll = math.radians(roll_deg)
    ca, sa = math.cos(roll), math.sin(roll)

    def local(v: Vec3) -> Tuple[float, float, float]:
        a = v[ai]
        p = v[others[0]] - cx
        q = v[others[1]] - cy
        return (a, p * ca + q * sa, -p * sa + q * ca)

    # 1) tam giác nào còn nằm trên mặt phôi gốc
    on_surface: List[Tuple[Tuple[float, float, float], ...]] = []
    outside = 0
    for t in tris:
        pts = [local(v) for v in t]
        dists = [section.signed_distance(p[1], p[2]) for p in pts]
        if all(abs(d) <= surface_tolerance for d in dists):
            on_surface.append(tuple(pts))
        elif min(dists) > surface_tolerance:
            outside += 1
    if not on_surface:
        raise ImportError_(
            "Không thấy phần bề mặt nào của mô hình nằm trên mặt phôi đã khai báo. "
            "Kiểm tra lại kích thước phôi, trục và tâm - hoặc tăng dung sai bề mặt."
        )

    _check_fit(on_surface, section, len(tris), outside, notes)

    # 2) cạnh chỉ thuộc một tam giác "còn nguyên" là cạnh biên
    edges: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], int] = {}
    coords: Dict[Tuple[int, int, int], Tuple[float, float, float]] = {}

    def vkey(p: Tuple[float, float, float]) -> Tuple[int, int, int]:
        k = (int(round(p[0] / weld)), int(round(p[1] / weld)), int(round(p[2] / weld)))
        coords.setdefault(k, p)
        return k

    for tri in on_surface:
        ks = [vkey(p) for p in tri]
        for i in range(3):
            a, b = ks[i], ks[(i + 1) % 3]
            edges[(a, b) if a <= b else (b, a)] = edges.get(
                (a, b) if a <= b else (b, a), 0) + 1
    boundary = [e for e, n in edges.items() if n == 1]
    if not boundary:
        raise ImportError_(
            "Bề mặt phôi trong mô hình không có đường biên nào - "
            "có vẻ mô hình chưa bị cắt gì."
        )

    # 3) nối cạnh biên thành vòng
    adj: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
    for a, b in boundary:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    used = set()
    chains: List[List[Tuple[int, int, int]]] = []
    for start in list(adj):
        if start in used and len(adj[start]) <= 2:
            continue
        for first in adj[start]:
            edge = (start, first) if start <= first else (first, start)
            if edge in used:
                continue
            chain = [start, first]
            used.add(edge)
            cur, prev = first, start
            while True:
                nxts = [n for n in adj.get(cur, [])
                        if n != prev and ((cur, n) if cur <= n else (n, cur)) not in used]
                if not nxts:
                    break
                nxt = nxts[0]
                used.add((cur, nxt) if cur <= nxt else (nxt, cur))
                chain.append(nxt)
                prev, cur = cur, nxt
                if cur == start:
                    break
            if len(chain) >= 3:
                chains.append(chain)

    # 4) đổi sang toạ độ trải phẳng
    curves: List[Curve2D] = []
    for chain in chains:
        pts: List[Point] = []
        for k in chain:
            a, p, q = coords[k]
            pts.append((a, section.s_of_point(p, q)))
        pts = _unwrap_v(dedupe(pts), section.perimeter)
        if len(pts) >= 3:
            # Đường cắt khép kín theo hai kiểu: tự gặp lại chính nó (lỗ, rãnh),
            # hoặc chạy hết một vòng quanh phôi (cắt đứt, vát đầu ống) - kiểu
            # sau có điểm đầu và điểm cuối lệch nhau đúng một chu vi.
            du = abs(pts[-1][0] - pts[0][0])
            dv = pts[-1][1] - pts[0][1]
            laps = round(dv / section.perimeter)
            wrap = laps != 0 and du <= weld and \
                abs(dv - laps * section.perimeter) <= weld
            closed = wrap or math.dist(pts[0], pts[-1]) <= weld
            curves.append(Curve2D(pts, closed, "mesh", wrap=wrap))
    if not curves:
        raise ImportError_("Tìm được đường biên nhưng không dựng được đường cắt.")
    curves.sort(key=lambda c: -c.length)
    return curves


def _check_fit(on_surface, section, total: int, outside: int,
               notes: Optional[List[str]]) -> None:
    """Soát xem tiết diện khai báo có thật sự khớp với mô hình không.

    Khai báo sai kích thước, sai bán kính bo góc hay sai đơn vị thì thuật toán
    vẫn chạy và vẫn ra đường cong - nhưng là đường sai.  Hai dấu hiệu bắt được
    gần hết các nhầm lẫn đó:

    * có phần vật liệu nằm **hẳn ra ngoài** mặt phôi khai báo -> phôi khai nhỏ quá;
    * có **dải chu vi** không chỗ nào bám được mặt phôi -> sai hình dạng tiết diện
      (hay gặp nhất: quên khai bán kính bo góc của ống hộp).
    """
    if notes is None:
        return
    if outside > max(4, total * 0.01):
        notes.append(
            f"{outside}/{total} mảnh lưới nằm hẳn ngoài mặt phôi đã khai báo - "
            "nhiều khả năng phôi khai nhỏ hơn thực tế (hoặc mô hình đang tính "
            "theo inch)."
        )
    bins = 180
    seen = [False] * bins
    per = section.perimeter
    for tri in on_surface:
        for _, p, q in tri:
            seen[int(section.s_of_point(p, q) % per / per * bins) % bins] = True
    gaps = bins - sum(seen)
    if gaps > bins * 0.05:
        notes.append(
            f"{gaps * 100 // bins}% chu vi tiết diện không có mảnh lưới nào bám vào - "
            "tiết diện khai báo có vẻ không đúng hình dạng mô hình (hay gặp nhất "
            "là quên khai bán kính bo góc ống hộp). Đường cắt lấy ra có thể bị "
            "đứt đoạn."
        )


def _unwrap_v(points: Sequence[Point], perimeter: float) -> List[Point]:
    """Gỡ cuộn toạ độ chu vi để đường cắt không nhảy một vòng ở mốc 0."""
    if not points:
        return []
    out = [points[0]]
    for u, v in points[1:]:
        prev = out[-1][1]
        k = round((v - prev) / perimeter)
        out.append((u, v - k * perimeter))
    return out


def load(path: str, section, **kw) -> List[Curve2D]:
    return extract_cut_curves(load_triangles(path), section, **kw)
