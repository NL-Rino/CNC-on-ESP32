"""Hình học 2D trên "mặt trụ trải phẳng".

Ống là một mặt trụ.  Trải mặt trụ ra mặt phẳng là một **phép đẳng cự**
(isometry): độ dài và góc được bảo toàn tuyệt đối.  Nhờ vậy mọi phép xử lý
đường chạy dao - bù bề rộng mạch cắt (kerf), bo góc, vào/ra dao, rời rạc hoá
theo dung sai - đều có thể làm trên mặt phẳng 2D rồi cuốn ngược lại lên ống
mà **không hề có sai số xấp xỉ**.

Hệ toạ độ trải phẳng::

    u = toạ độ dọc trục ống (mm)
    v = độ dài cung theo chu vi (mm) = R * theta(rad)

Module này thuần toán học, không phụ thuộc gì ngoài ``math``.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
EPS = 1e-9


# --------------------------------------------------------------------------
# Vector cơ bản
# --------------------------------------------------------------------------
def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def norm(a: Point) -> float:
    return math.hypot(a[0], a[1])


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a: Point) -> Point:
    n = norm(a)
    if n < EPS:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def left_normal(d: Point) -> Point:
    """Pháp tuyến bên trái của hướng đi ``d`` (quay +90 độ)."""
    return (-d[1], d[0])


def rotate(a: Point, ang_rad: float) -> Point:
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    return (a[0] * c - a[1] * s, a[0] * s + a[1] * c)


# --------------------------------------------------------------------------
# Thao tác trên polyline
# --------------------------------------------------------------------------
def polyline_length(pts: Sequence[Point]) -> float:
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def bbox(pts: Sequence[Point]) -> Tuple[float, float, float, float]:
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return (min(us), min(vs), max(us), max(vs))


def signed_area(pts: Sequence[Point]) -> float:
    """Diện tích có dấu (dương = ngược chiều kim đồng hồ)."""
    if len(pts) < 3:
        return 0.0
    p = list(pts)
    if dist(p[0], p[-1]) > EPS:
        p.append(p[0])
    s = 0.0
    for i in range(len(p) - 1):
        s += cross(p[i], p[i + 1])
    return s / 2.0


def is_closed(pts: Sequence[Point], eps: float = 1e-6) -> bool:
    return len(pts) > 2 and dist(pts[0], pts[-1]) <= eps


def close_loop(pts: Sequence[Point]) -> List[Point]:
    out = list(pts)
    if out and dist(out[0], out[-1]) > EPS:
        out.append(out[0])
    return out


def open_loop(pts: Sequence[Point]) -> List[Point]:
    """Bỏ điểm lặp cuối nếu polyline đang khép kín."""
    out = list(pts)
    while len(out) > 1 and dist(out[0], out[-1]) <= EPS:
        out.pop()
    return out


def dedupe(pts: Sequence[Point], eps: float = 1e-7) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or dist(out[-1], p) > eps:
            out.append(p)
    return out


def reverse(pts: Sequence[Point]) -> List[Point]:
    return list(reversed(pts))


def ensure_ccw(pts: Sequence[Point], ccw: bool = True) -> List[Point]:
    a = signed_area(pts)
    if (a < 0) == ccw:
        return reverse(pts)
    return list(pts)


def translate(pts: Sequence[Point], du: float, dv: float) -> List[Point]:
    return [(p[0] + du, p[1] + dv) for p in pts]


# --------------------------------------------------------------------------
# Rời rạc hoá đường cong theo dung sai dây cung
# --------------------------------------------------------------------------
def adaptive_sample(
    func: Callable[[float], Point],
    t0: float,
    t1: float,
    tolerance: float,
    max_points: int = 6000,
    min_depth: int = 3,
    max_depth: int = 16,
) -> List[Point]:
    """Lấy mẫu đường cong tham số bằng chia đôi thích nghi.

    Tiêu chí dừng: sai số dây cung (khoảng cách từ điểm giữa tới dây) nhỏ hơn
    ``tolerance``.  Vì mặt trụ trải phẳng là đẳng cự, sai số đo trên mặt
    phẳng chính là sai số thật trên bề mặt ống.

    Cách này cho **mật độ điểm tự động**: đoạn cong gắt thì dày, đoạn gần
    thẳng thì thưa - đúng thứ cần để ESP32 không bị nghẽn lệnh mà đường cắt
    vẫn trơn.
    """
    if t1 == t0:
        return [func(t0)]
    result: List[Point] = [func(t0)]
    budget = [max_points]

    def recurse(ta: float, pa: Point, tb: float, pb: Point, depth: int) -> None:
        if budget[0] <= 0:
            return
        tm = 0.5 * (ta + tb)
        pm = func(tm)
        chord = dist(pa, pb)
        if depth >= max_depth:
            deviation = 0.0
        elif chord < EPS:
            deviation = dist(pa, pm)
        else:
            d = normalize(sub(pb, pa))
            deviation = abs(cross(d, sub(pm, pa)))
        if depth < min_depth or (deviation > tolerance and depth < max_depth):
            recurse(ta, pa, tm, pm, depth + 1)
            recurse(tm, pm, tb, pb, depth + 1)
        else:
            result.append(pb)
            budget[0] -= 1

    recurse(t0, result[0], t1, func(t1), 0)
    if dist(result[-1], func(t1)) > EPS:
        result.append(func(t1))
    return dedupe(result)


def resample_max_step(pts: Sequence[Point], max_step: float) -> List[Point]:
    """Chèn thêm điểm để không đoạn nào dài quá ``max_step``.

    Đoạn quá dài làm bộ điều khiển tăng tốc rồi phanh gấp ở mỗi đầu đoạn;
    chia nhỏ giúp planner của FluidNC nhìn xa hơn và giữ tốc độ ổn định.
    """
    if max_step <= 0 or len(pts) < 2:
        return list(pts)
    out: List[Point] = [pts[0]]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = dist(a, b)
        if d > max_step:
            n = int(math.ceil(d / max_step))
            for k in range(1, n):
                t = k / n
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


def rdp(pts: Sequence[Point], tolerance: float) -> List[Point]:
    """Rút gọn Ramer-Douglas-Peucker (bản lặp, không đệ quy sâu).

    Gộp các điểm gần thẳng hàng -> giảm số dòng G-code -> UART và planner của
    ESP32 nhẹ đi rất nhiều mà hình dạng vẫn nằm trong dung sai.
    """
    if tolerance <= 0 or len(pts) < 3:
        return list(pts)
    n = len(pts)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        a, b = pts[i0], pts[i1]
        seg = sub(b, a)
        seg_len = norm(seg)
        best_d = -1.0
        best_i = -1
        if seg_len < EPS:
            for i in range(i0 + 1, i1):
                d = dist(pts[i], a)
                if d > best_d:
                    best_d, best_i = d, i
        else:
            u = mul(seg, 1.0 / seg_len)
            for i in range(i0 + 1, i1):
                w = sub(pts[i], a)
                t = dot(w, u)
                if t < 0:
                    d = norm(w)
                elif t > seg_len:
                    d = dist(pts[i], b)
                else:
                    d = abs(cross(u, w))
                if d > best_d:
                    best_d, best_i = d, i
        if best_d > tolerance and best_i > 0:
            keep[best_i] = True
            stack.append((i0, best_i))
            stack.append((best_i, i1))
    return [pts[i] for i in range(n) if keep[i]]


def enforce_min_segment(pts: Sequence[Point], min_len: float, keep_ends: bool = True) -> List[Point]:
    """Bỏ bớt điểm để không có đoạn nào ngắn hơn ``min_len``.

    Chuỗi đoạn siêu ngắn là nguyên nhân số một gây giật ở máy CNC chạy vi điều
    khiển: mỗi block tiêu tốn thời gian xử lý cố định, planner không kịp nhìn
    trước nên phải giảm tốc liên tục.
    """
    if min_len <= 0 or len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for p in pts[1:-1]:
        if dist(out[-1], p) >= min_len:
            out.append(p)
    last = pts[-1]
    if keep_ends:
        if len(out) > 1 and dist(out[-1], last) < min_len:
            out[-1] = last
        else:
            out.append(last)
    elif dist(out[-1], last) >= min_len:
        out.append(last)
    return out


def turn_angle(prev: Point, cur: Point, nxt: Point) -> float:
    """Góc bẻ hướng tại đỉnh ``cur`` (rad, dương = rẽ trái)."""
    d0 = normalize(sub(cur, prev))
    d1 = normalize(sub(nxt, cur))
    if norm(d0) < EPS or norm(d1) < EPS:
        return 0.0
    return math.atan2(cross(d0, d1), dot(d0, d1))


# --------------------------------------------------------------------------
# Giao điểm, bù đường (offset)
# --------------------------------------------------------------------------
def line_intersection(p1: Point, d1: Point, p2: Point, d2: Point) -> Optional[Point]:
    """Giao của hai đường thẳng (điểm + vector chỉ phương). None nếu song song."""
    den = cross(d1, d2)
    if abs(den) < 1e-12:
        return None
    t = cross(sub(p2, p1), d2) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def segment_intersection(a1: Point, a2: Point, b1: Point, b2: Point) -> Optional[Tuple[Point, float, float]]:
    """Giao của hai đoạn thẳng -> (điểm, t trên A, s trên B) hoặc None."""
    d1 = sub(a2, a1)
    d2 = sub(b2, b1)
    den = cross(d1, d2)
    if abs(den) < 1e-12:
        return None
    diff = sub(b1, a1)
    t = cross(diff, d2) / den
    s = cross(diff, d1) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= s <= 1 + 1e-9:
        return ((a1[0] + d1[0] * t, a1[1] + d1[1] * t), t, s)
    return None


def remove_self_intersections(pts: Sequence[Point], max_passes: int = 8) -> List[Point]:
    """Cắt bỏ các "tai" tự giao sinh ra sau khi bù đường.

    Dùng kiểm tra bao hình chữ nhật trước nên đủ nhanh với vài nghìn điểm.
    """
    work = list(pts)
    for _ in range(max_passes):
        n = len(work)
        if n < 4:
            break
        found = None
        boxes = []
        for i in range(n - 1):
            a, b = work[i], work[i + 1]
            boxes.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
        for i in range(n - 1):
            bi = boxes[i]
            for j in range(i + 2, n - 1):
                bj = boxes[j]
                if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                    continue
                hit = segment_intersection(work[i], work[i + 1], work[j], work[j + 1])
                if hit is None:
                    continue
                pt, t, s = hit
                if i == 0 and j == n - 2 and (t < 1e-6 or s > 1 - 1e-6):
                    continue  # điểm khép kín, không phải tự giao
                found = (i, j, pt)
                break
            if found:
                break
        if not found:
            break
        i, j, pt = found
        work = work[: i + 1] + [pt] + work[j + 1:]
    return dedupe(work)


def offset(pts: Sequence[Point], distance: float, closed: bool = False, clean: bool = True) -> List[Point]:
    """Bù đường sang **bên trái** hướng chạy một khoảng ``distance``.

    ``distance`` âm là bù sang phải.  Dùng để bù nửa bề rộng mạch cắt (kerf):
    tâm tia luôn lệch khỏi đường bao danh nghĩa nửa kerf về phía phần phế
    liệu, nhờ vậy chi tiết ra đúng kích thước.
    """
    if abs(distance) < 1e-9 or len(pts) < 2:
        return list(pts)
    src = open_loop(pts) if closed else list(pts)
    src = dedupe(src)
    n = len(src)
    if n < 2:
        return list(pts)

    segs = []
    m = n if closed else n - 1
    for i in range(m):
        a = src[i]
        b = src[(i + 1) % n]
        d = normalize(sub(b, a))
        if norm(d) < EPS:
            continue
        nn = mul(left_normal(d), distance)
        segs.append((add(a, nn), add(b, nn), d))
    if not segs:
        return list(pts)

    out: List[Point] = []
    if not closed:
        out.append(segs[0][0])
    count = len(segs)
    rng = range(count) if closed else range(count - 1)
    for i in rng:
        a1, b1, d1 = segs[i]
        a2, b2, d2 = segs[(i + 1) % count]
        ip = line_intersection(a1, d1, a2, d2)
        if ip is None or dist(ip, b1) > 50 * abs(distance) + 1e-6:
            out.append(b1)
            out.append(a2)
        else:
            out.append(ip)
    if not closed:
        out.append(segs[-1][1])
    else:
        out = [out[-1]] + out[:-1]
        out = close_loop(out)
    out = dedupe(out)
    if clean and len(out) > 3:
        out = remove_self_intersections(out)
    return out


# --------------------------------------------------------------------------
# Bo góc (fillet)
# --------------------------------------------------------------------------
def round_corners(
    pts: Sequence[Point],
    radius: float,
    closed: bool = False,
    tolerance: float = 0.05,
    min_angle_deg: float = 3.0,
) -> List[Point]:
    """Thay các góc nhọn bằng cung tròn bán kính ``radius``.

    Góc nhọn buộc máy phải dừng hẳn (junction deviation ~ 0).  Bo góc giúp
    bốn trục chuyển hướng liên tục nên đầu cắt không bị "khựng" - đây chính
    là điểm ăn thua về độ mượt của đường cắt.
    """
    if radius <= 0 or len(pts) < 3:
        return list(pts)
    src = open_loop(pts) if closed else list(pts)
    n = len(src)
    if n < 3:
        return list(pts)
    min_ang = math.radians(min_angle_deg)
    out: List[Point] = []
    idx = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(src[0])
    for i in idx:
        prev_p = src[(i - 1) % n]
        cur = src[i]
        nxt = src[(i + 1) % n]
        ang = turn_angle(prev_p, cur, nxt)
        if abs(ang) < min_ang or abs(abs(ang) - math.pi) < 1e-6:
            out.append(cur)
            continue
        d_in = normalize(sub(cur, prev_p))
        d_out = normalize(sub(nxt, cur))
        half = (math.pi - abs(ang)) / 2.0
        if half < 1e-6:
            out.append(cur)
            continue
        trim = radius / math.tan(half)
        avail_in = dist(prev_p, cur) * (0.5 if closed or i > 0 else 1.0)
        avail_out = dist(cur, nxt) * 0.5
        t = min(trim, avail_in * 0.98, avail_out * 0.98)
        if t < 1e-6:
            out.append(cur)
            continue
        r_eff = t * math.tan(half)
        p_start = sub(cur, mul(d_in, t))
        p_end = add(cur, mul(d_out, t))
        sign = 1.0 if ang > 0 else -1.0
        center = add(p_start, mul(left_normal(d_in), sign * r_eff))
        a0 = math.atan2(p_start[1] - center[1], p_start[0] - center[0])
        a1 = math.atan2(p_end[1] - center[1], p_end[0] - center[0])
        sweep = a1 - a0
        while sweep > math.pi:
            sweep -= 2 * math.pi
        while sweep < -math.pi:
            sweep += 2 * math.pi
        steps = max(2, int(math.ceil(abs(sweep) / max(1e-6, 2 * math.acos(max(-1.0, min(1.0, 1 - tolerance / max(r_eff, 1e-6))))))))
        steps = min(steps, 64)
        out.append(p_start)
        for k in range(1, steps):
            a = a0 + sweep * k / steps
            out.append((center[0] + r_eff * math.cos(a), center[1] + r_eff * math.sin(a)))
        out.append(p_end)
    if not closed:
        out.append(src[-1])
    elif out:
        out = close_loop(out)
    return dedupe(out)


# --------------------------------------------------------------------------
# Vào dao / ra dao
# --------------------------------------------------------------------------
def lead_line(anchor: Point, direction: Point, length: float, angle_deg: float) -> List[Point]:
    """Đoạn vào dao thẳng, xoay ``angle_deg`` so với hướng chạy."""
    d = normalize(direction)
    if norm(d) < EPS or length <= 0:
        return []
    lead_dir = rotate(d, math.radians(angle_deg))
    start = sub(anchor, mul(lead_dir, length))
    return [start, anchor]


def lead_arc(anchor: Point, direction: Point, length: float, side: float = 1.0, steps: int = 12) -> List[Point]:
    """Đoạn vào dao dạng cung 1/4 tiếp tuyến - êm hơn vào dao thẳng.

    ``side`` = +1 vào từ bên trái hướng chạy, -1 từ bên phải.
    """
    d = normalize(direction)
    if norm(d) < EPS or length <= 0:
        return []
    r = length
    center = add(anchor, mul(left_normal(d), side * r))
    a_end = math.atan2(anchor[1] - center[1], anchor[0] - center[0])
    sweep = math.pi / 2 * (1.0 if side > 0 else -1.0)
    a_start = a_end - sweep
    pts = []
    for k in range(steps + 1):
        a = a_start + sweep * k / steps
        pts.append((center[0] + r * math.cos(a), center[1] + r * math.sin(a)))
    return pts


def point_at_length(pts: Sequence[Point], s: float) -> Point:
    """Điểm nằm cách điểm đầu một quãng đường ``s`` dọc theo polyline."""
    if not pts:
        raise ValueError("polyline rỗng")
    if s <= 0:
        return pts[0]
    acc = 0.0
    for i in range(len(pts) - 1):
        d = dist(pts[i], pts[i + 1])
        if acc + d >= s:
            t = (s - acc) / d if d > EPS else 0.0
            a, b = pts[i], pts[i + 1]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += d
    return pts[-1]


def trim_to_length(pts: Sequence[Point], s: float) -> List[Point]:
    """Cắt lấy đoạn đầu của polyline có chiều dài ``s``."""
    if s <= 0 or len(pts) < 2:
        return []
    out = [pts[0]]
    acc = 0.0
    for i in range(len(pts) - 1):
        d = dist(pts[i], pts[i + 1])
        if acc + d >= s:
            out.append(point_at_length(pts[i:i + 2], s - acc))
            return out
        acc += d
        out.append(pts[i + 1])
    return out


def rotate_start(pts: Sequence[Point], index: int, closed: bool = True) -> List[Point]:
    """Đổi điểm bắt đầu của một đường khép kín."""
    if not closed or len(pts) < 3:
        return list(pts)
    src = open_loop(pts)
    n = len(src)
    i = index % n
    return close_loop(src[i:] + src[:i])
