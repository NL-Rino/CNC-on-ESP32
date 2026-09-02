"""Xử lý đường chạy dao trước khi sinh G-code.

Chuỗi xử lý cho từng biên dạng::

    Contour (u,v)  ->  bù kerf  ->  vào/ra dao  ->  rút gọn + đều đoạn
                   ->  tính góc trục vát  ->  danh sách CutPoint (x, theta, bevel)

Tất cả đều thực hiện trên mặt phẳng trải nên khoảng cách đo được chính là
khoảng cách thật trên bề mặt ống.

Một hệ quả quan trọng: vì ``v`` biến thiên **liên tục**, góc quay
``theta = v/R`` cũng liên tục - không bao giờ có cú nhảy +-180 độ giữa hai
điểm.  Trục A vì thế quay đều một mạch, đó là điều kiện tiên quyết để đường
cắt mượt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import geom2d as g
from .config import MotionSpec, ProcessSpec
from .toolpath import (
    BEVEL_CONSTANT,
    BEVEL_FOLLOW,
    BEVEL_NONE,
    Contour,
    CutPoint,
    Point,
    v_to_theta,
)


@dataclass
class Pass:
    """Một lượt chạy dao hoàn chỉnh (đã có vào dao, cắt, ra dao)."""

    points: List[CutPoint] = field(default_factory=list)
    name: str = ""
    kind: str = "cut"
    lead_in_count: int = 0    # số điểm đầu thuộc đoạn vào dao
    lead_out_count: int = 0   # số điểm cuối thuộc đoạn ra dao
    meta: Dict[str, object] = field(default_factory=dict)

    @property
    def pierce(self) -> CutPoint:
        return self.points[0]

    def __len__(self) -> int:
        return len(self.points)


# --------------------------------------------------------------------------
# Hỗ trợ đường quấn quanh chu vi
# --------------------------------------------------------------------------
def _period(radius: float) -> float:
    return 2 * math.pi * radius


def periodic_extend(pts: Sequence[Point], radius: float, margin: float) -> Tuple[List[Point], int, int]:
    """Nối thêm bản sao tuần hoàn ở hai đầu đường quấn.

    Nhờ vậy các phép bù/bo góc ở gần điểm nối vòng vẫn đúng như ở giữa đường.
    Trả về (điểm mở rộng, số điểm thêm ở đầu, số điểm thêm ở cuối).
    """
    P = _period(radius)
    if margin <= 0 or len(pts) < 2:
        return list(pts), 0, 0
    v0, v1 = pts[0][1], pts[-1][1]
    head: List[Point] = []
    for u, v in reversed(pts[:-1]):
        vv = v - P
        if vv < v0 - margin:
            break
        head.insert(0, (u, vv))
    tail: List[Point] = []
    for u, v in pts[1:]:
        vv = v + P
        tail.append((u, vv))
        if vv > v1 + margin:
            break
    return head + list(pts) + tail, len(head), len(tail)


def _trim_v_range(pts: Sequence[Point], v_lo: float, v_hi: float) -> List[Point]:
    """Giữ lại phần polyline nằm trong khoảng ``v`` cho trước (có nội suy biên)."""
    out: List[Point] = []
    for i, p in enumerate(pts):
        inside = v_lo - 1e-9 <= p[1] <= v_hi + 1e-9
        if inside:
            out.append(p)
        if i + 1 < len(pts):
            a, b = p, pts[i + 1]
            for bound in (v_lo, v_hi):
                if (a[1] - bound) * (b[1] - bound) < 0:
                    t = (bound - a[1]) / (b[1] - a[1])
                    out.append((a[0] + (b[0] - a[0]) * t, bound))
    out.sort(key=lambda q: q[1]) if False else None
    return g.dedupe(out)


# --------------------------------------------------------------------------
# Bù bề rộng mạch cắt
# --------------------------------------------------------------------------
def apply_kerf(contour: Contour, radius: float, kerf: float, side: str = "auto") -> List[Point]:
    """Dịch đường chạy dao đi nửa bề rộng mạch cắt về phía phần phế liệu."""
    pts = list(contour.points)
    if kerf <= 0 or side == "none" or contour.kind == "mark":
        return pts
    half = kerf / 2.0

    if contour.closed:
        # Lỗ / rãnh: phế liệu nằm bên trong -> tâm tia đi vào trong nửa kerf
        pts = g.close_loop(g.ensure_ccw(pts, ccw=True))
        d = half if side in ("auto", "inside", "left") else -half
        return g.offset(pts, d, closed=True)

    if contour.wrap:
        # Cắt quanh ống: phế liệu ở phía đầu tự do (u lớn) -> lệch về +u.
        # Bù vuông góc với đường cắt (đúng hơn là chỉ dịch theo u).
        margin = 10.0 * half + 5.0
        ext, nh, nt = periodic_extend(pts, radius, margin)
        # hướng chạy chủ yếu theo +v => pháp tuyến trái là -u => cần dấu âm
        sign = -1.0 if side in ("auto", "right") else 1.0
        off = g.offset(ext, sign * half, closed=False)
        v_lo, v_hi = pts[0][1], pts[-1][1]
        trimmed = _trim_v_range(off, v_lo, v_hi)
        return trimmed if len(trimmed) >= 2 else off

    if side in ("left", "right"):
        return g.offset(pts, half if side == "left" else -half, closed=False)
    return pts


# --------------------------------------------------------------------------
# Chạy vượt (thuộc đường cắt) và vào/ra dao (không thuộc đường cắt)
# --------------------------------------------------------------------------
def apply_overcut(contour: Contour, pts: Sequence[Point], radius: float, overcut: float) -> List[Point]:
    """Chạy vượt qua điểm khép kín để mạch cắt đứt hẳn.

    Phần chạy vượt là *phần nối dài của chính đường cắt* nên phải được thêm
    trước khi tính góc trục vát, để trục vát chạy tiếp liền mạch.
    """
    pts = list(pts)
    if overcut <= 0 or len(pts) < 2 or contour.kind == "mark":
        return pts
    if contour.closed:
        pts = g.close_loop(pts)
        extra = g.trim_to_length(pts, overcut)
        if len(extra) > 1:
            pts = pts + extra[1:]
        return pts
    if contour.wrap:
        ext, nh, nt = periodic_extend(pts, radius, overcut + 1.0)
        if nt > 0:
            after = ext[len(pts) + nh - 1:]
            extra = g.trim_to_length(after, overcut)
            if len(extra) > 1:
                pts = pts + extra[1:]
    return pts


def _lead_steps(length: float, min_segment: float) -> int:
    step = max(0.4, min_segment if min_segment > 0 else 0.5)
    return max(3, min(24, int(math.ceil(length / step))))


def build_leads(
    contour: Contour,
    pts: Sequence[Point],
    process: ProcessSpec,
    motion: MotionSpec,
) -> Tuple[List[Point], List[Point]]:
    """Sinh đoạn vào dao và ra dao (chưa nối vào đường cắt).

    Điểm mồi luôn nằm trong phần phế liệu: bên trong lỗ với biên dạng kín,
    hoặc phía đầu tự do của ống với nhát cắt quanh ống.  Nhờ vậy vết mồi
    (rất xấu và rộng) không rơi vào chi tiết thành phẩm.
    """
    if len(pts) < 2 or contour.kind == "mark" or process.lead_type == "none":
        return [], []
    lin, lout = max(0.0, process.lead_in), max(0.0, process.lead_out)
    ltype = process.lead_type
    lead_in: List[Point] = []
    lead_out: List[Point] = []

    if contour.closed:
        if lin > 0:
            d = g.sub(pts[1], pts[0])
            if ltype == "arc":
                arc = g.lead_arc(pts[0], d, lin, side=1.0, steps=_lead_steps(lin * 1.6, motion.min_segment))
            else:
                arc = g.lead_line(pts[0], d, lin, process.lead_angle)
            lead_in = arc[:-1] if len(arc) > 1 else []
        if lout > 0:
            d = g.sub(pts[-1], pts[-2])
            if ltype == "arc":
                arc = g.lead_arc(pts[-1], g.mul(d, -1.0), lout, side=-1.0,
                                 steps=_lead_steps(lout * 1.6, motion.min_segment))
                arc = list(reversed(arc))
            else:
                arc = list(reversed(g.lead_line(pts[-1], g.mul(d, -1.0), lout, -process.lead_angle)))
            lead_out = arc[1:] if len(arc) > 1 else []
        return lead_in, lead_out

    if contour.wrap:
        # mồi lệch về phía đầu tự do rồi tiến ngang vào đường cắt
        if lin > 0:
            start = pts[0]
            lead_in = [(start[0] + lin, start[1])]
        return lead_in, []

    # đường hở: kéo dài theo tiếp tuyến hai đầu
    if lin > 0:
        d = g.normalize(g.sub(pts[1], pts[0]))
        lead_in = [g.sub(pts[0], g.mul(d, lin))]
    if lout > 0:
        d = g.normalize(g.sub(pts[-1], pts[-2]))
        lead_out = [g.add(pts[-1], g.mul(d, lout))]
    return lead_in, lead_out


# --------------------------------------------------------------------------
# Điều tiết mật độ điểm
# --------------------------------------------------------------------------
def condition(pts: Sequence[Point], motion: MotionSpec) -> List[Point]:
    """Rút gọn - gộp đoạn ngắn - chia đoạn dài, theo thứ tự đó.

    Ba bước này quyết định "cảm giác" của máy:

    1. *Rút gọn* bỏ điểm thừa trên đoạn gần thẳng -> ít block, UART nhẹ.
    2. *Gộp đoạn ngắn* tránh chuỗi block li ti làm planner của ESP32 hụt hơi.
    3. *Chia đoạn dài* để planner luôn có nhiều block nhìn trước, không phanh
       gấp ở cuối mỗi đoạn dài.
    """
    out = g.dedupe(pts, 1e-7)
    if motion.simplify_tolerance > 0:
        out = g.rdp(out, motion.simplify_tolerance)
    if motion.min_segment > 0:
        out = g.enforce_min_segment(out, motion.min_segment)
    if motion.max_segment > 0:
        out = g.resample_max_step(out, motion.max_segment)
    if motion.max_points_per_contour and len(out) > motion.max_points_per_contour:
        # nới dung sai dần cho tới khi đạt hạn mức
        tol = max(motion.simplify_tolerance, 1e-4)
        for _ in range(12):
            tol *= 1.6
            out = g.rdp(out, tol)
            if len(out) <= motion.max_points_per_contour:
                break
    return out


# --------------------------------------------------------------------------
# Trục vát
# --------------------------------------------------------------------------
def compute_bevels(
    pts: Sequence[Point],
    mode: str,
    value: float,
    motion: MotionSpec,
    closed: bool = False,
    window: float = 1.5,
) -> List[float]:
    """Tính góc nghiêng đầu cắt cho từng điểm.

    Chế độ ``follow``: giữ mặt cắt vuông góc với đường cắt trải phẳng, tức là
    trục vát bám đúng **độ dốc dọc trục** của đường cắt::

        tan(gamma) = du / dv

    Với nhát cắt vát phẳng, công thức này trả về đúng góc mặt phẳng ở sườn ống
    và 0 độ ở hai điểm cực - giống hệt cách thợ đặt mỏ cắt.  Với miệng cá, nó
    cho góc bám theo thành ống chính.

    Hướng chạy dao không ảnh hưởng tới kết quả (chuẩn hoá theo dấu của dv),
    và giá trị được làm trơn bằng trung bình trượt để trục vát không bị rung.
    """
    n = len(pts)
    if n == 0:
        return []
    if mode == BEVEL_CONSTANT:
        return [_clamp(value, motion)] * n
    if mode != BEVEL_FOLLOW:
        return [0.0] * n

    # độ dài luỹ kế để lấy lân cận theo khoảng cách thật
    s = [0.0] * n
    for i in range(1, n):
        s[i] = s[i - 1] + g.dist(pts[i - 1], pts[i])
    total = s[-1]

    def neighbour(i: int, direction: int) -> int:
        target = s[i] + direction * window
        j = i
        while 0 <= j + direction < n and ((direction > 0 and s[j] < target) or (direction < 0 and s[j] > target)):
            j += direction
        return max(0, min(n - 1, j))

    raw: List[float] = []
    for i in range(n):
        a = neighbour(i, -1)
        b = neighbour(i, +1)
        if a == b:
            a, b = max(0, i - 1), min(n - 1, i + 1)
        du = pts[b][0] - pts[a][0]
        dv = pts[b][1] - pts[a][1]
        if abs(dv) < 1e-9 and abs(du) < 1e-9:
            raw.append(raw[-1] if raw else 0.0)
            continue
        if dv < 0:
            du, dv = -du, -dv
        ang = math.degrees(math.atan2(du, dv))
        if motion.bevel_invert:
            ang = -ang
        raw.append(_clamp(ang, motion))

    return _smooth(raw, pts, window, closed=closed)


def _clamp(a: float, motion: MotionSpec) -> float:
    lim = abs(motion.max_bevel)
    return max(-lim, min(lim, a))


def _smooth(
    values: Sequence[float],
    pts: Sequence[Point],
    window: float,
    closed: bool = False,
    passes: int = 2,
) -> List[float]:
    """Làm trơn dãy góc vát theo **khoảng cách cung**, không theo chỉ số điểm.

    Nếu các điểm nằm thưa hơn cửa sổ làm trơn thì đạo hàm đã đủ ổn định rồi,
    lúc đó không làm trơn nữa - nếu cứ làm trơn theo chỉ số sẽ bào mòn đỉnh
    góc vát (ví dụ miệng cá 18.4 độ bị kéo xuống còn 17 độ).
    """
    out = list(values)
    n = len(out)
    if n < 3 or window <= 0:
        return out
    gap_prev = [0.0] * n
    gap_next = [0.0] * n
    for i in range(n):
        ia = (i - 1) % n if closed else max(0, i - 1)
        ib = (i + 1) % n if closed else min(n - 1, i + 1)
        gap_prev[i] = g.dist(pts[i], pts[ia])
        gap_next[i] = g.dist(pts[i], pts[ib])
    for _ in range(passes):
        prev = list(out)
        for i in range(n):
            ia = (i - 1) % n if closed else max(0, i - 1)
            ib = (i + 1) % n if closed else min(n - 1, i + 1)
            wa = 0.25 * max(0.0, 1.0 - gap_prev[i] / window)
            wb = 0.25 * max(0.0, 1.0 - gap_next[i] / window)
            out[i] = wa * prev[ia] + wb * prev[ib] + (1.0 - wa - wb) * prev[i]
    return out


# --------------------------------------------------------------------------
# Toàn bộ chuỗi xử lý
# --------------------------------------------------------------------------
def process_contour(
    contour: Contour,
    radius: float,
    motion: MotionSpec,
    process: ProcessSpec,
    kerf_override: Optional[float] = None,
) -> Pass:
    """Biến một ``Contour`` thô thành ``Pass`` sẵn sàng xuất G-code.

    Thứ tự các bước rất quan trọng: góc trục vát được tính **sau** khi đường
    cắt đã ở hình dạng cuối cùng nhưng **trước** khi gắn đoạn vào/ra dao -
    đoạn vào dao chạy thuần theo trục nên nếu tính chung sẽ kéo trục vát lệch
    đi ngay tại điểm mồi.
    """
    if len(contour.points) < 2:
        raise ValueError(f"Biên dạng '{contour.name}' có ít hơn 2 điểm.")
    kerf = process.kerf if kerf_override is None else kerf_override
    side = contour.kerf_side if contour.kerf_side != "auto" else process.kerf_side

    # 1) bù bề rộng mạch cắt
    pts = apply_kerf(contour, radius, kerf, side)
    if contour.closed:
        pts = g.close_loop(pts)
    # 2) bo góc nhọn nếu có yêu cầu
    if motion.corner_radius > 0 and contour.meta.get("shape") in ("slot", "flat_pattern"):
        pts = g.round_corners(pts, motion.corner_radius, closed=contour.closed,
                              tolerance=motion.chord_tolerance)
    # 3) chạy vượt (là phần nối dài của đường cắt)
    pts = apply_overcut(contour, pts, radius, process.overcut)
    # 4) điều tiết mật độ điểm
    pts = condition(pts, motion)
    if len(pts) < 2:
        raise ValueError(f"Biên dạng '{contour.name}' rỗng sau khi xử lý.")

    # 5) góc trục vát trên đúng phần cắt
    bevels = compute_bevels(
        pts, contour.bevel_mode, contour.bevel_value, motion,
        closed=contour.closed or contour.wrap,
    )

    # 6) gắn vào/ra dao, giữ nguyên góc vát của điểm cắt kề bên
    lead_in, lead_out = build_leads(contour, pts, process, motion)
    if lead_in:
        lead_in = g.enforce_min_segment(lead_in + [pts[0]], motion.min_segment)[:-1]
    if lead_out:
        lead_out = g.enforce_min_segment([pts[-1]] + lead_out, motion.min_segment)[1:]
    all_pts = list(lead_in) + list(pts) + list(lead_out)
    all_bevels = ([bevels[0]] * len(lead_in)) + bevels + ([bevels[-1]] * len(lead_out))

    cut_points = [
        CutPoint(x=u, theta=v_to_theta(v, radius), bevel=all_bevels[i])
        for i, (u, v) in enumerate(all_pts)
    ]
    return Pass(
        points=cut_points,
        name=contour.name,
        kind=contour.kind,
        lead_in_count=len(lead_in),
        lead_out_count=len(lead_out),
        meta=dict(contour.meta),
    )
