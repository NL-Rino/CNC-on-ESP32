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
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import geom2d as g
from .config import MotionSpec, ProcessSpec
from .section import Section
from .toolpath import (
    BEVEL_CONSTANT,
    BEVEL_FOLLOW,
    BEVEL_NONE,
    Contour,
    CutPoint,
    Point,
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
def periodic_extend(pts: Sequence[Point], section: Section, margin: float) -> Tuple[List[Point], int, int]:
    """Nối thêm bản sao tuần hoàn ở hai đầu đường quấn.

    Nhờ vậy các phép bù/bo góc ở gần điểm nối vòng vẫn đúng như ở giữa đường.
    Trả về (điểm mở rộng, số điểm thêm ở đầu, số điểm thêm ở cuối).
    """
    P = section.perimeter
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
def apply_kerf(contour: Contour, section: Section, kerf: float, side: str = "auto") -> List[Point]:
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
        ext, nh, nt = periodic_extend(pts, section, margin)
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
def apply_overcut(contour: Contour, pts: Sequence[Point], section: Section, overcut: float) -> List[Point]:
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
        ext, nh, nt = periodic_extend(pts, section, overcut + 1.0)
        if nt > 0:
            after = ext[len(pts) + nh - 1:]
            extra = g.trim_to_length(after, overcut)
            if len(extra) > 1:
                pts = pts + extra[1:]
    return pts


def apply_lead_start(
    contour: Contour,
    pts: Sequence[Point],
    section: Section,
    percent: float,
) -> List[Point]:
    """Dời **điểm bắt đầu** của biên dạng đi ``percent`` % chu vi.

    Điểm bắt đầu chính là nơi mồi và nơi đoạn vào dao bám vào.  Vết mồi rất
    xấu và rộng, nên thợ luôn muốn tự chọn nó rơi vào chỗ nào - ví dụ vào giữa
    một cạnh thay vì đúng góc bo, hoặc vào mặt khuất.
    """
    frac = (percent % 100.0) / 100.0
    if frac <= 1e-9 or len(pts) < 3:
        return list(pts)

    if contour.closed:
        loop = g.close_loop(list(pts))
        total = g.polyline_length(loop)
        target = total * frac
        acc, idx = 0.0, 0
        for i in range(len(loop) - 1):
            step = g.dist(loop[i], loop[i + 1])
            if acc + step >= target:
                idx = i if (target - acc) < step / 2 else i + 1
                break
            acc += step
        return g.rotate_start(loop, idx, closed=True)

    if contour.wrap:
        per = section.perimeter
        shift = per * frac
        ext, nh, _nt = periodic_extend(pts, section, shift + 5.0)
        v0 = pts[0][1] + shift
        rolled = _trim_v_range(ext, v0, v0 + per)
        return rolled if len(rolled) >= 2 else list(pts)

    return list(pts)


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
        # phía vào dao: mặc định vào từ trong lòng biên dạng (chỗ phế liệu)
        side = -1.0 if process.lead_side == "outside" else 1.0
        if lin > 0:
            d = g.sub(pts[1], pts[0])
            if ltype == "arc":
                arc = g.lead_arc(pts[0], d, lin, side=side,
                                 steps=_lead_steps(lin * 1.6, motion.min_segment))
            else:
                arc = g.lead_line(pts[0], d, lin, process.lead_angle * side)
            lead_in = arc[:-1] if len(arc) > 1 else []
        if lout > 0:
            d = g.sub(pts[-1], pts[-2])
            if ltype == "arc":
                arc = g.lead_arc(pts[-1], g.mul(d, -1.0), lout, side=-side,
                                 steps=_lead_steps(lout * 1.6, motion.min_segment))
                arc = list(reversed(arc))
            else:
                arc = list(reversed(g.lead_line(pts[-1], g.mul(d, -1.0), lout,
                                                -process.lead_angle * side)))
            lead_out = arc[1:] if len(arc) > 1 else []
        return lead_in, lead_out

    if contour.wrap:
        # mồi lệch dọc trục rồi tiến ngang vào đường cắt; mặc định lệch về phía
        # đầu tự do (u lớn) vì đó là phần phế liệu
        if lin > 0:
            sign = -1.0 if process.lead_side == "minus" else 1.0
            start = pts[0]
            lead_in = [(start[0] + lin * sign, start[1])]
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
# Bám sát tiết diện không tròn
# --------------------------------------------------------------------------
def insert_breakpoints(pts: Sequence[Point], section: Section) -> List[Point]:
    """Chèn đỉnh tại mọi chỗ tiết diện chuyển giữa mặt phẳng và góc lượn.

    Với ống hộp, đúng những chỗ này là nơi trục ngang X đạt cực trị và độ cong
    nhảy bậc.  Thiếu đỉnh ở đây thì đoạn nội suy sẽ "cắt vát" qua chỗ chuyển
    tiếp, làm sai biên dạng ngay tại cạnh ống.
    """
    breaks = section.breakpoints()
    if not breaks or len(pts) < 2:
        return list(pts)
    per = section.perimeter
    out: List[Point] = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        v0, v1 = a[1], b[1]
        if abs(v1 - v0) > 1e-9:
            lo, hi = (v0, v1) if v1 > v0 else (v1, v0)
            k0 = math.floor(lo / per)
            k1 = math.floor(hi / per) + 1
            hits: List[float] = []
            for k in range(int(k0), int(k1) + 1):
                for br in breaks:
                    vv = br + k * per
                    if lo + 1e-9 < vv < hi - 1e-9:
                        hits.append(vv)
            hits.sort(reverse=v1 < v0)
            for vv in hits:
                t = (vv - v0) / (v1 - v0)
                out.append((a[0] + (b[0] - a[0]) * t, vv))
        out.append(b)
    return g.dedupe(out)


def refine_for_section(
    pts: Sequence[Point],
    section: Section,
    tolerance: float,
    max_points: int = 8000,
) -> List[Point]:
    """Chia nhỏ thêm ở những nơi đường chạy dao **cong trong không gian trục**.

    Trên mặt phẳng trải, một nhát cắt vuông góc quanh ống hộp là đường thẳng -
    nhưng trong không gian bốn trục nó không hề thẳng: qua góc lượn, trục A
    xoay 90°, trục X chạy từ mép này sang mép kia và trục Z nhô lên rồi hạ
    xuống.  Nội suy thẳng giữa hai đầu sẽ cho mỏ cắt cắm vào phôi.

    Hàm này đo sai lệch giữa **đường đi thật của mũi cắt** và dây cung nối hai
    điểm, rồi chia đôi cho tới khi sai lệch nhỏ hơn dung sai.  Với ống tròn và
    với các đoạn nằm trên mặt phẳng, sai lệch bằng 0 nên không thêm điểm nào -
    số dòng G-code không hề tăng vô ích.
    """
    if len(pts) < 2 or tolerance <= 0:
        return list(pts)
    if not section.breakpoints():
        return list(pts)          # ống tròn: nội suy trục đã chính xác tuyệt đối

    def tip(v: float) -> Tuple[float, float]:
        ct = section.contact_at(v)
        return (ct.cross, ct.height)

    budget = [max_points - len(pts)]
    out: List[Point] = [pts[0]]

    def recurse(a: Point, b: Point, depth: int) -> None:
        if budget[0] <= 0 or depth > 12:
            out.append(b)
            return
        vm = 0.5 * (a[1] + b[1])
        um = 0.5 * (a[0] + b[0])
        ta, tb, tm = tip(a[1]), tip(b[1]), tip(vm)
        dx = tm[0] - 0.5 * (ta[0] + tb[0])
        dz = tm[1] - 0.5 * (ta[1] + tb[1])
        if math.hypot(dx, dz) <= tolerance:
            out.append(b)
            return
        mid = (um, vm)
        budget[0] -= 1
        recurse(a, mid, depth + 1)
        recurse(mid, b, depth + 1)

    for a, b in zip(pts, pts[1:]):
        recurse(a, b, 0)
    return g.dedupe(out)


def _arc_index(arcs, v: float, per: float) -> Optional[int]:
    vm = v % per
    for i, a in enumerate(arcs):
        if a["v0"] + 1e-9 < vm < a["v1"] - 1e-9:
            return i
    return None


def _psi_near(section: Section, v: float, reference: float) -> float:
    """Góc pháp tuyến tại ``v``, lấy đại diện **gần** ``reference`` nhất.

    Góc pháp tuyến chỉ xác định sai khác bội số của 360 độ.  Chọn đại diện gần
    góc quay hiện tại là cách an toàn duy nhất: dò theo phép chia dư sẽ nhảy
    bậc ngay tại mốc chu vi và làm phôi quay thừa trọn một vòng.
    """
    raw = section.normal_angle(v % section.perimeter)
    return raw + 360.0 * round((reference - raw) / 360.0)


def _corner_pose(section: Section, arc, v: float, a_deg: float) -> Tuple[float, float]:
    """Vị trí trục ngang và chiều cao bề mặt khi phôi quay ``a_deg`` mà tia cắt
    thẳng đứng rơi đúng vào điểm vật liệu ``v`` trên cung góc.

    Điểm nằm trên cung tâm K bán kính rc, nên sau khi quay thì nó vẫn cách tâm
    K (đã quay) đúng rc, lệch khỏi phương thẳng đứng một góc bằng chênh lệch
    giữa pháp tuyến tại đó và góc quay hiện tại.
    """
    psi = _psi_near(section, v, a_deg)
    delta = math.radians(psi - a_deg)
    kwx, kwz = section.rotate_point(arc["cx"], arc["cy"], a_deg)
    return (kwx + arc["rc"] * math.sin(delta),
            kwz + arc["rc"] * math.cos(delta))


def _pivot_corner(
    hold_in: CutPoint,
    run: List[CutPoint],
    hold_out: CutPoint,
    arc,
    section: Section,
    motion: MotionSpec,
    process: ProcessSpec,
) -> List[CutPoint]:
    """Vượt góc lượn bằng cách **xoay đưa góc lên đỉnh rồi cắt**.

    Trình tự đúng như thợ làm bằng tay: cắt hết mặt phẳng ở tốc độ chuẩn ->
    dừng, xoay đưa phần cung sắp cắt lên đỉnh (mỏ vẫn đứng đúng điểm vừa cắt
    xong trên phôi, trục ngang và trục Z phối hợp bám theo) -> cắt phần cung
    đó ở **tốc độ chuẩn** với trục A đứng yên -> lặp lại cho tới hết cung ->
    xoay nốt về mặt phẳng kế tiếp -> cắt tiếp.

    Vì sao giữ được tốc độ chuẩn: khi cung đã nằm ở đỉnh, cắt hết nó chỉ cần
    trục ngang chạy, trục A không phải quay tí nào.  So với cắt liền mạch
    (trục A phải quay 90 độ trong khoảng 9 mm cung, tức ~15 000 độ/phút) thì
    đây là trời với vực.

    **Chia cung làm mấy lần xoay** (``motion.corner_pivot_arcs``) quyết định độ
    vuông góc của mặt cắt.  Cả cung 90 độ mà chỉ xoay một lần thì ở hai đầu
    cung mỏ nghiêng tới 45 độ so với pháp tuyến; chia làm ``k`` lần thì độ
    nghiêng lớn nhất chỉ còn ``45/k`` độ, đổi lại thêm ``k-1`` lần dừng xoay.
    """
    ref = section.reference_height
    zc = process.cut_height
    steps = max(2, int(motion.corner_pivot_steps))
    groups = max(1, int(getattr(motion, "corner_pivot_arcs", 1)))

    def make(v: float, x: float, a_deg: float, kind: str) -> CutPoint:
        cross, surf = _corner_pose(section, arc, v, a_deg)
        return CutPoint(x=x, v=v, theta=a_deg, cross=cross,
                        surface_z=surf - ref, bevel=0.0, kind=kind,
                        z_axis=surf - ref + zc)

    # Chia cung thành k phần **bằng nhau theo góc** (không phải theo số điểm:
    # các điểm không rải đều theo góc nên chia theo chỉ số sẽ ra góc lệch).
    psi0, psi1 = float(arc["psi0"]), float(arc["psi1"])
    width = (psi1 - psi0) / groups
    parts: List[List[CutPoint]] = [[] for _ in range(groups)]
    targets = [psi0 + (m + 0.5) * width for m in range(groups)]
    for q in run:
        psi = section.normal_angle(q.v % section.perimeter)
        # đưa về đúng nhánh [psi0, psi1] rồi mới xếp nhóm
        psi += 360.0 * round(((psi0 + psi1) / 2.0 - psi) / 360.0)
        m = int((psi - psi0) / width) if width else 0
        parts[max(0, min(groups - 1, m))].append(q)

    out: List[CutPoint] = []
    a_prev = hold_in.theta
    v_prev, x_prev = hold_in.v, hold_in.x
    for part, target in zip(parts, targets):
        if not part:
            continue
        a_target = target + 360.0 * round((a_prev - target) / 360.0)
        for k in range(1, steps + 1):
            a = a_prev + (a_target - a_prev) * k / steps
            out.append(make(v_prev, x_prev, a, "index"))
        for q in part:
            out.append(make(q.v, q.x, a_target, "cut"))
        a_prev = a_target
        v_prev, x_prev = part[-1].v, part[-1].x

    # xoay nốt về mặt phẳng kế tiếp, mỏ bám điểm vừa cắt xong
    out.append(make(hold_out.v, hold_out.x, a_prev, "cut"))
    a_end = _psi_near(section, hold_out.v, a_prev)
    for k in range(1, steps):
        a = a_prev + (a_end - a_prev) * k / steps
        out.append(make(hold_out.v, hold_out.x, a, "index"))
    return out


def apply_corner_strategy(
    points: List[CutPoint],
    section: Section,
    motion: MotionSpec,
    process: ProcessSpec,
) -> List[CutPoint]:
    """Xử lý các cung góc lượn theo chế độ đã chọn.

    * ``follow`` - giữ nguyên, cắt liền mạch (tốc độ bị trục xoay kéo tụt);
    * ``index``  - dừng cắt, nhấc mỏ, xoay hết 90 độ rồi mồi lại cắt tiếp
      (cung góc **không** được cắt nếu tắt mỏ);
    * ``pivot``  - xoay 45 độ đưa cung góc lên đỉnh rồi cắt hết cung ở tốc độ
      chuẩn, xong xoay nốt 45 độ (cắt đủ cả cung, giữ được tốc độ).
    """
    arcs = section.corner_arcs()
    if not arcs or motion.corner_mode not in ("index", "pivot") or not points:
        return points
    per = section.perimeter
    lift = motion.corner_lift if motion.corner_torch_off else 0.0
    out: List[CutPoint] = []
    i, n = 0, len(points)
    while i < n:
        p = points[i]
        idx = _arc_index(arcs, p.v, per) if p.kind == "cut" else None
        if idx is None:
            out.append(p)
            i += 1
            continue
        j = i
        while j < n and _arc_index(arcs, points[j].v, per) == idx:
            j += 1
        run = points[i:j]
        if motion.corner_mode == "index":
            for q in run:
                out.append(CutPoint(x=q.x, v=q.v, theta=q.theta, cross=q.cross,
                                    surface_z=q.surface_z, bevel=q.bevel,
                                    kind="index",
                                    z_axis=(process.cut_height + q.surface_z + lift)
                                    if lift else None))
        else:
            hold_in = out[-1] if out else run[0]
            hold_out = points[j] if j < n else run[-1]
            out.extend(_pivot_corner(hold_in, run, hold_out, arcs[idx],
                                     section, motion, process))
        i = j
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
# Những thông số đường dẫn mồi mà từng nguyên công được phép ghi đè riêng.
LEAD_OVERRIDES = ("lead_in", "lead_out", "lead_type", "lead_angle",
                  "lead_start", "lead_side", "overcut")


def apply_lead_overrides(process: ProcessSpec, meta: Dict[str, Any]) -> ProcessSpec:
    """Áp thông số đường dẫn mồi riêng của một nguyên công lên tiến trình chung.

    Mỗi nhát cắt có chỗ vào dao hợp lý khác nhau: lỗ thì vào từ trong lòng, cắt
    đứt thì vào từ phía phế liệu, rãnh dài thì nên vào ở đầu nào tuỳ chỗ kẹp.
    Vì vậy ngoài thiết lập chung ở hồ sơ máy, từng nguyên công còn ghi đè được.
    Ô nào để trống (hoặc ghi ``theo mặc định``) thì vẫn dùng số của tiến trình.
    """
    over = meta.get("lead") if meta else None
    if not over:
        return process
    changed = {k: v for k, v in over.items() if k in LEAD_OVERRIDES and v is not None}
    if not changed:
        return process
    return replace(process, **changed)


def process_contour(
    contour: Contour,
    section: Section,
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
    # Từng nguyên công được ghi đè riêng chỗ vào dao (xem apply_lead_overrides)
    process = apply_lead_overrides(process, contour.meta)
    kerf = process.kerf if kerf_override is None else kerf_override
    side = contour.kerf_side if contour.kerf_side != "auto" else process.kerf_side

    # 1) bù bề rộng mạch cắt
    pts = apply_kerf(contour, section, kerf, side)
    if contour.closed:
        pts = g.close_loop(pts)
    # 2) bo góc nhọn nếu có yêu cầu
    if motion.corner_radius > 0 and contour.meta.get("shape") in ("slot", "flat_pattern"):
        pts = g.round_corners(pts, motion.corner_radius, closed=contour.closed,
                              tolerance=motion.chord_tolerance)
    # 3) dời điểm mồi theo ý người dùng, rồi chạy vượt
    pts = apply_lead_start(contour, pts, section, process.lead_start)
    pts = apply_overcut(contour, pts, section, process.overcut)
    # 4) điều tiết mật độ điểm
    pts = condition(pts, motion)
    # 4b) với tiết diện không tròn: chèn đỉnh ở chỗ đổi hình rồi bám sát
    #     đường đi thật trong không gian trục
    pts = insert_breakpoints(pts, section)
    pts = refine_for_section(pts, section, motion.chord_tolerance,
                             motion.max_points_per_contour or 8000)
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

    # Ánh xạ sang tư thế máy: tiết diện quyết định góc quay, vị trí trục ngang
    # và chênh cao bề mặt tại từng điểm.
    ref = section.reference_height
    cut_points: List[CutPoint] = []
    for i, (u, v) in enumerate(all_pts):
        ct = section.contact_at(v)
        cut_points.append(CutPoint(x=u, v=v, theta=ct.theta, cross=ct.cross,
                                   surface_z=ct.height - ref,
                                   bevel=all_bevels[i]))
    if contour.kind != "mark":
        cut_points = apply_corner_strategy(cut_points, section, motion, process)
    meta = dict(contour.meta)
    meta["wrap"] = contour.wrap
    meta["closed"] = contour.closed
    return Pass(
        points=cut_points,
        name=contour.name,
        kind=contour.kind,
        lead_in_count=len(lead_in),
        lead_out_count=len(lead_out),
        meta=meta,
    )
