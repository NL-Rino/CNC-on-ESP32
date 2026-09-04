"""Tiết diện phôi: ống tròn, ống hộp vuông, ống hộp chữ nhật.

Vì sao cần lớp này
------------------
Phần mềm làm việc trên **mặt trải phẳng** ``(u, v)``: ``u`` dọc theo phôi,
``v`` là độ dài cung đo dọc theo chu vi tiết diện.  Với ống tròn thì
``v = R·θ`` - quan hệ tuyến tính, nên trước đây chỉ cần một con số bán kính.

Ống hộp thì khác hẳn: khoảng cách từ tâm tới bề mặt thay đổi theo vị trí
(bằng nửa cạnh ở giữa mặt phẳng, lớn hơn ở góc lượn), và **hướng pháp tuyến
của bề mặt cũng thay đổi**.  Muốn mỏ cắt luôn vuông góc với mặt phôi thì:

* trục **A** phải xoay sao cho pháp tuyến tại điểm đang cắt hướng thẳng lên;
* trục **X** đưa mỏ cắt chạy dọc theo bề mặt (khi cắt trên mặt phẳng, A đứng
  yên còn X chạy);
* trục **Z** bù chênh lệch chiều cao bề mặt (góc lượn cao hơn mặt phẳng).

Với ống tròn, phép ánh xạ này tự động rút gọn về đúng cách làm cũ: X = 0,
Z không đổi, A = θ.  Nhờ vậy toàn bộ phần hình học phía trên không phải sửa.

Hệ toạ độ tiết diện: ``(ngang, cao)`` trong hệ gắn với phôi, gốc ở tâm phôi.
Điểm mốc ``s = 0`` nằm ở đỉnh phôi (ngay dưới mỏ cắt khi A = 0), và ``s``
tăng dần theo chiều quay dương.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]

SHAPE_ROUND = "round"
SHAPE_SQUARE = "square"
SHAPE_RECT = "rect"
ALL_SHAPES = (SHAPE_ROUND, SHAPE_SQUARE, SHAPE_RECT)

SHAPE_VI = {
    SHAPE_ROUND: "Ống tròn",
    SHAPE_SQUARE: "Ống hộp vuông",
    SHAPE_RECT: "Ống hộp chữ nhật",
}


class SectionError(ValueError):
    """Kích thước tiết diện không hợp lệ."""


@dataclass
class Contact:
    """Tư thế máy để mỏ cắt chạm vuông góc vào điểm ``s`` trên bề mặt."""

    theta: float     # góc trục A (độ)
    cross: float     # vị trí trục ngang X (mm)
    height: float    # chiều cao điểm chạm so với tâm phôi (mm)


class Section:
    """Giao diện chung cho mọi tiết diện phôi."""

    kind = SHAPE_ROUND

    # ---- các đại lượng cơ bản (lớp con phải cài đặt) ----
    @property
    def perimeter(self) -> float:
        raise NotImplementedError

    def point_at(self, s: float) -> Vec2:
        """Điểm trên biên tiết diện, trong hệ gắn với phôi."""
        raise NotImplementedError

    def normal_angle(self, s: float) -> float:
        """Góc pháp tuyến ngoài tại ``s`` (độ, 0 = hướng lên)."""
        raise NotImplementedError

    def outline(self, steps: int = 96) -> List[Vec2]:
        """Đường bao tiết diện để vẽ."""
        return [self.point_at(self.perimeter * i / steps) for i in range(steps + 1)]

    # ---- suy ra từ các đại lượng trên ----
    def contact_at(self, s: float) -> Contact:
        """Tư thế máy để cắt vuông góc tại vị trí ``s``.

        Xoay phôi đi một góc bằng góc pháp tuyến là pháp tuyến hướng thẳng
        lên; điểm chạm khi đó nằm ở toạ độ ngang ``X`` và chiều cao ``Z``.
        """
        # Gỡ cuộn: đi hết một vòng chu vi là quay đúng 360 độ.
        #
        # Phải rất cẩn thận ngay tại mốc chu vi.  Với ``s`` âm cực nhỏ (kiểu
        # -9e-16 do sai số dấu phẩy động), phần dư ``s - lap*perimeter`` bị làm
        # tròn lên *đúng bằng* chu vi; ``normal_angle`` quy giá trị đó về 0 độ
        # của vòng SAU, trong khi bộ đếm vòng vẫn là vòng TRƯỚC - thành ra góc
        # xoay nhảy trọn 360 độ, phôi quay hẳn một vòng giữa nhát cắt.
        per = self.perimeter
        lap = math.floor(s / per)
        base = s - lap * per
        if base >= per - 1e-9:      # phần dư chạm mốc: nó thuộc vòng sau
            base = 0.0              # đặt hẳn về 0, đừng để lọt xuống số âm
            lap += 1
        elif base < 0.0:            # phòng xa cho phía bên kia
            base = 0.0
        psi = self.normal_angle(base) + 360.0 * lap
        cx, cy = self.point_at(s)
        a = math.radians(psi)
        # quay điểm đi -psi (cùng chiều với cách đo góc pháp tuyến)
        x = cx * math.cos(a) - cy * math.sin(a)
        z = cx * math.sin(a) + cy * math.cos(a)
        return Contact(theta=psi, cross=x, height=z)

    @property
    def reference_height(self) -> float:
        """Chiều cao bề mặt tại điểm mốc - dùng làm gốc Z khi rà dao."""
        return self.contact_at(0.0).height

    def surface_z(self, s: float) -> float:
        """Chênh lệch chiều cao bề mặt so với gốc Z (ống tròn luôn bằng 0)."""
        return self.contact_at(s).height - self.reference_height

    def radius_at(self, s: float) -> float:
        cx, cy = self.point_at(s)
        return math.hypot(cx, cy)

    @property
    def max_radius(self) -> float:
        return max(self.radius_at(self.perimeter * i / 180) for i in range(180))

    def tilt_projection(self, s: float, roll_deg: float = 0.0) -> float:
        """Hình chiếu của điểm lên phương nghiêng - dùng cho nhát cắt vát.

        Mặt phẳng cắt nghiêng góc ``alpha`` cắt phôi theo đường
        ``u(s) = x0 + tan(alpha) · (điểm chiếu lên phương nghiêng)``.
        Với ống tròn, hình chiếu này chính là ``R·cos(θ − roll)``.
        """
        cx, cy = self.point_at(s)
        a = math.radians(roll_deg)
        return cx * math.sin(a) + cy * math.cos(a)

    # ---- tiện dụng ----
    def s_of_theta(self, theta_deg: float) -> float:
        """Vị trí cung của điểm nằm theo **hướng nhìn** ``theta`` từ tâm phôi.

        Nói "lỗ ở 90 độ" nghĩa là lỗ nằm ở hướng 3 giờ - với ống hộp thì đó là
        *giữa mặt bên*, chứ không phải mép mặt.  Vì vậy phải dò theo góc cực
        của điểm, không dò theo góc pháp tuyến (pháp tuyến giữ nguyên suốt cả
        một mặt phẳng nên không định vị được).
        """
        lap = math.floor(theta_deg / 360.0)
        target = theta_deg - 360.0 * lap
        lo, hi = 0.0, self.perimeter
        for _ in range(60):
            mid = (lo + hi) / 2
            cx, cy = self.point_at(mid)
            ang = math.degrees(math.atan2(cx, cy)) % 360.0
            if ang < target or (target == 0.0 and mid < self.perimeter / 2 and ang > 180.0):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2 + lap * self.perimeter

    def s_of_contact(self, theta_deg: float, cross: float = 0.0) -> float:
        """Bài toán ngược: phôi đang quay góc ``theta``, mỏ cắt ở vị trí ngang
        ``cross`` thì **tia cắt thẳng đứng rơi vào đâu** trên bề mặt phôi.

        Khi cắt đúng tư thế (tia vuông góc mặt phôi) thì kết quả trùng với
        điểm vuông góc; khi trục ngang lệch khỏi tư thế chuẩn thì đây mới là
        chỗ vật liệu thật sự bị lấy đi.  Dùng để vẽ vết cắt lên đúng vị trí
        trên phôi khi bám theo máy thật.

        Cách giải: quét biên tiết diện đã quay, tìm đoạn cắt qua đường thẳng
        đứng ``x = cross`` và lấy đoạn nằm **cao nhất** (tia đi từ trên xuống).
        """
        per = self.perimeter
        lap = math.floor(theta_deg / 360.0)
        a = math.radians(theta_deg - 360.0 * lap)
        cos_a, sin_a = math.cos(a), math.sin(a)

        def world(v: float) -> Tuple[float, float]:
            cx, cy = self.point_at(v % per)
            return (cx * cos_a - cy * sin_a, cx * sin_a + cy * cos_a)

        n = 240
        best_v: Optional[float] = None
        best_z = -1e18
        prev_v = 0.0
        prev = world(0.0)
        for i in range(1, n + 1):
            v = per * i / n
            cur = world(v)
            if (prev[0] - cross) * (cur[0] - cross) <= 0 and abs(cur[0] - prev[0]) > 1e-12:
                lo, hi = prev_v, v
                for _ in range(40):     # chia đôi cho chính xác
                    mid = 0.5 * (lo + hi)
                    if (world(lo)[0] - cross) * (world(mid)[0] - cross) <= 0:
                        hi = mid
                    else:
                        lo = mid
                vv = 0.5 * (lo + hi)
                zz = world(vv)[1]
                if zz > best_z:
                    best_z, best_v = zz, vv
            prev_v, prev = v, cur
        if best_v is None:
            best_v = 0.0
        # Suy số vòng từ chính góc pháp tuyến tại điểm vừa tìm được: mặt trên
        # của ống hộp mang cả góc 0 lẫn góc 360 (hai nửa mặt), nên không thể
        # suy số vòng chỉ từ góc quay của máy.
        lap = round((theta_deg - self.normal_angle(best_v)) / 360.0)
        return best_v + lap * per

    def arc_spans(self) -> List[Tuple[float, float]]:
        """Các đoạn cung góc lượn, dạng (v bắt đầu, v kết thúc).

        Đây là những chỗ phôi buộc phải xoay: pháp tuyến quay 90 độ trong một
        đoạn cung rất ngắn.  Ống tròn không có đoạn nào như vậy (quay đều suốt).
        """
        return []

    def corner_arcs(self) -> List[Dict[str, float]]:
        """Mô tả đầy đủ từng cung góc: vị trí, tâm, bán kính, khoảng pháp tuyến."""
        return []

    def rotate_point(self, cx: float, cy: float, theta_deg: float) -> Tuple[float, float]:
        """Quay một điểm của tiết diện theo góc trục A (cùng quy ước contact_at)."""
        a = math.radians(theta_deg)
        return (cx * math.cos(a) - cy * math.sin(a),
                cx * math.sin(a) + cy * math.cos(a))

    def breakpoints(self) -> List[float]:
        """Các vị trí cung mà biên đổi kiểu hình (mặt phẳng <-> góc lượn).

        Tại đó độ cong nhảy bậc, nên đường chạy dao **bắt buộc phải có đỉnh**;
        nếu không, đoạn thẳng nội suy sẽ cắt ngang qua chỗ chuyển tiếp.
        """
        return []

    def signed_distance(self, cx: float, cy: float) -> float:
        """Khoảng cách có dấu từ một điểm tới biên tiết diện.

        Âm là nằm trong lòng phôi, dương là ở ngoài, 0 là đúng trên bề mặt.
        Dùng để nhận ra phần bề mặt của mô hình 3D nào còn nằm trên phôi gốc.
        """
        raise NotImplementedError

    def s_of_point(self, cx: float, cy: float) -> float:
        """Vị trí cung của điểm trên biên nằm theo hướng ``(cx, cy)`` từ tâm."""
        return self.s_of_theta(math.degrees(math.atan2(cx, cy)))

    def surface_height(self, theta_deg: float, cross: float = 0.0) -> float:
        """Chiều cao bề mặt phôi ngay dưới mũi cắt, đo từ tâm phôi.

        Phôi đang quay góc ``theta``, mỏ cắt ở vị trí ngang ``cross``; hàm trả
        về độ cao của điểm mà tia cắt thẳng đứng chạm tới.  Lấy hiệu giữa chiều
        cao mũi cắt và giá trị này là ra **khe hở thật** giữa mỏ và phôi.
        """
        v = self.s_of_contact(theta_deg, cross)
        cx, cy = self.point_at(v % self.perimeter)
        a = math.radians(theta_deg)
        return cx * math.sin(a) + cy * math.cos(a)

    def describe(self) -> str:
        raise NotImplementedError


class RoundSection(Section):
    """Ống tròn - trường hợp đơn giản nhất, mọi thứ đều đều đặn."""

    kind = SHAPE_ROUND

    def __init__(self, diameter: float):
        if diameter <= 0:
            raise SectionError("Đường kính ống phải lớn hơn 0.")
        self.diameter = float(diameter)
        self.radius = self.diameter / 2.0

    @property
    def perimeter(self) -> float:
        return 2 * math.pi * self.radius

    def point_at(self, s: float) -> Vec2:
        a = s / self.radius
        return (self.radius * math.sin(a), self.radius * math.cos(a))

    def normal_angle(self, s: float) -> float:
        return math.degrees(s / self.radius)

    def contact_at(self, s: float) -> Contact:
        # Ống tròn: mỏ cắt luôn ở giữa, chiều cao không đổi - khỏi cần tính vòng
        return Contact(theta=math.degrees(s / self.radius), cross=0.0,
                       height=self.radius)

    def surface_z(self, s: float) -> float:
        return 0.0

    def radius_at(self, s: float) -> float:
        return self.radius

    @property
    def max_radius(self) -> float:
        return self.radius

    def tilt_projection(self, s: float, roll_deg: float = 0.0) -> float:
        return self.radius * math.cos(s / self.radius - math.radians(roll_deg))

    def s_of_theta(self, theta_deg: float) -> float:
        return math.radians(theta_deg) * self.radius

    def s_of_contact(self, theta_deg: float, cross: float = 0.0) -> float:
        # tia thẳng đứng lệch ngang một đoạn e chạm mặt trụ ở góc asin(e/R)
        t = max(-1.0, min(1.0, cross / self.radius))
        return (math.radians(theta_deg) + math.asin(t)) * self.radius

    def signed_distance(self, cx: float, cy: float) -> float:
        return math.hypot(cx, cy) - self.radius

    def describe(self) -> str:
        return f"ống tròn ⌀{self.diameter:g}"


class BoxSection(Section):
    """Ống hộp vuông hoặc chữ nhật, có góc lượn.

    Biên gồm 4 đoạn thẳng và 4 cung góc, đi từ giữa mặt trên theo chiều dương.
    Góc lượn **bắt buộc lớn hơn 0**: nếu góc nhọn tuyệt đối thì tại đó pháp
    tuyến đổi hướng đột ngột 90°, máy sẽ phải xoay tại chỗ - không cắt được.
    Ống hộp thật luôn có góc lượn (thường bằng 1,5-2,5 lần chiều dày thành).
    """

    kind = SHAPE_RECT

    def __init__(self, width: float, height: Optional[float] = None,
                 corner_radius: float = 0.0, wall: float = 2.0):
        height = width if height is None else height
        if width <= 0 or height <= 0:
            raise SectionError("Cạnh ống hộp phải lớn hơn 0.")
        self.width = float(width)
        self.height = float(height)
        self.hx = self.width / 2.0
        self.hy = self.height / 2.0
        rc = corner_radius if corner_radius > 0 else max(0.5, 2.0 * wall)
        limit = min(self.hx, self.hy) * 0.98
        if rc > limit:
            rc = limit
        self.rc = float(rc)
        self.kind = SHAPE_SQUARE if abs(self.width - self.height) < 1e-9 else SHAPE_RECT
        self._build()

    def _build(self) -> None:
        """Dựng bảng các đoạn biên: (kiểu, chiều dài, dữ liệu)."""
        hx, hy, rc = self.hx, self.hy, self.rc
        top = hx - rc      # nửa chiều dài phần thẳng của mặt trên/dưới
        side = hy - rc     # nửa chiều dài phần thẳng của mặt trái/phải
        arc = math.pi * rc / 2.0
        # tâm bốn góc lượn
        k = [(hx - rc, hy - rc), (hx - rc, -(hy - rc)),
             (-(hx - rc), -(hy - rc)), (-(hx - rc), hy - rc)]
        # đi từ giữa mặt trên -> +ngang
        self._segs: List[Tuple[str, float, tuple]] = [
            ("flat", top, ((0.0, hy), (1.0, 0.0), 0.0)),          # nửa mặt trên
            ("arc", arc, (k[0], 0.0)),                            # góc trên-phải
            ("flat", 2 * side, ((hx, hy - rc), (0.0, -1.0), 90.0)),   # mặt phải
            ("arc", arc, (k[1], 90.0)),                           # góc dưới-phải
            ("flat", 2 * top, ((hx - rc, -hy), (-1.0, 0.0), 180.0)),  # mặt dưới
            ("arc", arc, (k[2], 180.0)),                          # góc dưới-trái
            ("flat", 2 * side, ((-hx, -(hy - rc)), (0.0, 1.0), 270.0)),  # mặt trái
            ("arc", arc, (k[3], 270.0)),                          # góc trên-trái
            # Nửa mặt trên còn lại được đánh pháp tuyến 360 độ chứ không phải 0:
            # góc pháp tuyến phải TĂNG ĐƠN ĐIỆU suốt một vòng chu vi thì phép gỡ
            # cuộn mới đúng, nếu không trục A sẽ nhảy nguyên một vòng ngay tại
            # chỗ đường cắt đi qua mốc 0.
            ("flat", top, ((-(hx - rc), hy), (1.0, 0.0), 360.0)),
        ]
        self._perimeter = sum(seg[1] for seg in self._segs)
        acc = 0.0
        self._starts: List[float] = []
        for seg in self._segs:
            self._starts.append(acc)
            acc += seg[1]

    @property
    def perimeter(self) -> float:
        return self._perimeter

    def _locate(self, s: float) -> Tuple[str, float, tuple]:
        s = s % self._perimeter
        for i in range(len(self._segs) - 1, -1, -1):
            if s >= self._starts[i] - 1e-12:
                kind, length, data = self._segs[i]
                return (kind, s - self._starts[i], data)
        kind, length, data = self._segs[0]
        return (kind, s, data)

    def point_at(self, s: float) -> Vec2:
        kind, t, data = self._locate(s)
        if kind == "flat":
            (px, py), (dx, dy), _psi = data
            return (px + dx * t, py + dy * t)
        (cx, cy), psi0 = data
        a = math.radians(psi0) + t / self.rc
        return (cx + self.rc * math.sin(a), cy + self.rc * math.cos(a))

    def normal_angle(self, s: float) -> float:
        kind, t, data = self._locate(s)
        if kind == "flat":
            return data[2]
        (_c, psi0) = data
        return psi0 + math.degrees(t / self.rc)

    def breakpoints(self) -> List[float]:
        return list(self._starts) + [self._perimeter]

    def arc_spans(self) -> List[Tuple[float, float]]:
        return [(self._starts[i], self._starts[i] + seg[1])
                for i, seg in enumerate(self._segs) if seg[0] == "arc"]

    def signed_distance(self, cx: float, cy: float) -> float:
        """Khoảng cách có dấu tới biên hộp bo góc.

        Công thức chuẩn cho hình chữ nhật bo góc: đưa về góc phần tư thứ nhất,
        đo tới hình chữ nhật thu nhỏ (đã trừ bán kính góc) rồi trừ đi bán kính.
        """
        qx = abs(cx) - (self.hx - self.rc)
        qy = abs(cy) - (self.hy - self.rc)
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
        inside = min(max(qx, qy), 0.0)
        return outside + inside - self.rc

    def corner_arcs(self) -> List[Dict[str, float]]:
        out: List[Dict[str, float]] = []
        for i, (kind, length, data) in enumerate(self._segs):
            if kind != "arc":
                continue
            center, psi0 = data
            out.append({
                "v0": self._starts[i],
                "v1": self._starts[i] + length,
                "cx": center[0], "cy": center[1],
                "rc": self.rc,
                "psi0": psi0,
                "psi1": psi0 + math.degrees(length / self.rc),
            })
        return out

    def describe(self) -> str:
        if self.kind == SHAPE_SQUARE:
            return f"ống hộp vuông {self.width:g}×{self.width:g}"
        return f"ống hộp {self.width:g}×{self.height:g}"


def make_section(shape: str, diameter: float = 60.0, width: float = 40.0,
                 height: Optional[float] = None, corner_radius: float = 0.0,
                 wall: float = 2.0) -> Section:
    """Tạo tiết diện theo tên hình dạng."""
    if shape == SHAPE_ROUND:
        return RoundSection(diameter)
    if shape == SHAPE_SQUARE:
        return BoxSection(width, width, corner_radius, wall)
    if shape == SHAPE_RECT:
        return BoxSection(width, height if height else width, corner_radius, wall)
    raise SectionError(f"Hình dạng tiết diện '{shape}' không hợp lệ.")
