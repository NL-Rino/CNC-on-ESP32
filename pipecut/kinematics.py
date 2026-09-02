"""Động học máy cắt ống 4 trục và bài toán tốc độ tổng hợp.

Vấn đề cốt lõi
--------------
FluidNC (giống Grbl) hiểu ``F`` là tốc độ trên **quãng đường tổng hợp trong
không gian các trục**, trong đó trục xoay được tính bằng *độ* y hệt như *mm*.
Vì thế nếu ta cứ ghi ``F1600`` cho mọi đoạn thì:

* đoạn chỉ có trục A quay: 1600 độ/phút -> với ống phi 60 là 1600*pi*30/180
  = 838 mm/phút trên bề mặt (quá chậm);
* đoạn chỉ có trục X chạy: đúng 1600 mm/phút;
* đoạn phối hợp X + A: tốc độ bề mặt nhảy loạn xạ giữa hai giá trị trên.

Hậu quả là vết cắt lúc cháy lúc non, gờ xỉ không đều - đúng hiện tượng "cắt
không mượt" mà máy cắt ống tự chế hay gặp.

Cách xử lý
----------
Với mỗi đoạn, tính hai quãng đường:

* ``L_real`` - quãng đường **thật của mũi cắt trên bề mặt ống**
  ``= sqrt(dx^2 + (R*d_theta)^2 + dz^2 + (pivot*d_bevel)^2)``
* ``L_mach`` - quãng đường trong không gian trục mà FluidNC dùng để chia F
  ``= sqrt(dX^2 + dY^2 + dZ^2 + dA^2 + dB^2)``  (A, B tính bằng độ)

rồi ghi ``F = v_cắt * L_mach / L_real``.

Nhờ vậy **tốc độ mũi cắt trên bề mặt ống luôn không đổi** dù bốn trục phối
hợp theo tỉ lệ nào.  Sau đó F còn được kẹp lại theo tốc độ tối đa của từng
trục để không trục nào bị ép chạy quá khả năng (chính là lúc máy mất bước).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import (
    ROLE_ALONG,
    ROLE_BEVEL,
    ROLE_CROSS,
    ROLE_RADIAL,
    ROLE_ROTARY,
    MachineProfile,
)
from .toolpath import CutPoint

AxisValues = Dict[str, float]


@dataclass
class Move:
    """Một lệnh dịch chuyển đã quy về toạ độ trục của máy."""

    kind: str                      # rapid | cut | plunge | lead
    target: AxisValues = field(default_factory=dict)
    feed: Optional[float] = None   # None = chạy nhanh G0
    comment: str = ""
    surface_length: float = 0.0    # quãng đường thật trên bề mặt (mm)
    machine_length: float = 0.0    # quãng đường tổng hợp trong không gian trục


class Kinematics:
    """Chuyển đổi giữa toạ độ công nghệ (x, theta, bevel, z) và toạ độ trục."""

    def __init__(self, profile: MachineProfile):
        self.profile = profile
        self.motion = profile.motion
        self.radius = profile.pipe.radius
        self.feed_radius = profile.pipe.feed_radius(profile.motion.feed_radius_mode)
        self.ax_along = profile.axis(ROLE_ALONG)
        self.ax_rotary = profile.axis(ROLE_ROTARY)
        self.ax_radial = profile.axis(ROLE_RADIAL)
        self.ax_bevel = profile.axis(ROLE_BEVEL)
        self.ax_cross = profile.axis(ROLE_CROSS)

    # ------------------------------------------------------------------
    # Toạ độ
    # ------------------------------------------------------------------
    def axis_values(self, cp: CutPoint, z: Optional[float] = None) -> AxisValues:
        """Đổi một điểm cắt thành từ điển {chữ cái trục: giá trị}.

        Có bù sai lệch do trục vát: khi đầu cắt nghiêng một góc ``gamma`` quanh
        tâm quay cách mũi cắt ``bevel_pivot`` mm, mũi cắt bị đẩy đi
        ``pivot*sin(gamma)`` theo phương dọc và nhấc lên ``pivot*(1-cos gamma)``.
        Ta cộng ngược lại để mũi cắt vẫn nằm đúng điểm lập trình.
        """
        vals: AxisValues = {}
        x = cp.x
        zz = z
        gamma = math.radians(cp.bevel) if self.ax_bevel else 0.0
        pivot = self.motion.bevel_pivot
        if self.ax_bevel and abs(pivot) > 1e-9 and abs(gamma) > 1e-12:
            x += pivot * math.sin(gamma)
            if zz is not None:
                zz -= pivot * (1.0 - math.cos(gamma))
        if self.ax_along:
            vals[self.ax_along.letter] = self.ax_along.apply(x)
        if self.ax_rotary:
            vals[self.ax_rotary.letter] = self.ax_rotary.apply(cp.theta)
        if self.ax_radial and zz is not None:
            vals[self.ax_radial.letter] = self.ax_radial.apply(zz)
        if self.ax_bevel:
            vals[self.ax_bevel.letter] = self.ax_bevel.apply(cp.bevel)
        if self.ax_cross and abs(cp.cross) > 1e-12:
            vals[self.ax_cross.letter] = self.ax_cross.apply(cp.cross)
        return vals

    # ------------------------------------------------------------------
    # Quãng đường
    # ------------------------------------------------------------------
    def surface_distance(self, a: CutPoint, b: CutPoint,
                         za: Optional[float] = None, zb: Optional[float] = None) -> float:
        """Quãng đường thật mũi cắt đi trên bề mặt ống giữa hai điểm."""
        dx = b.x - a.x
        dv = math.radians(b.theta - a.theta) * self.feed_radius
        dz = 0.0 if (za is None or zb is None) else (zb - za)
        db = 0.0
        if self.ax_bevel and abs(self.motion.bevel_pivot) > 1e-9:
            db = math.radians(b.bevel - a.bevel) * self.motion.bevel_pivot
        return math.sqrt(dx * dx + dv * dv + dz * dz + db * db)

    def machine_distance(self, va: AxisValues, vb: AxisValues) -> float:
        """Quãng đường tổng hợp mà FluidNC dùng để phân bổ F."""
        s = 0.0
        for letter, value in vb.items():
            d = value - va.get(letter, value)
            s += d * d
        return math.sqrt(s)

    # ------------------------------------------------------------------
    # Tốc độ
    # ------------------------------------------------------------------
    def clamp_by_axis_rates(self, feed: float, va: AxisValues, vb: AxisValues,
                            machine_len: float) -> float:
        """Giảm F nếu có trục nào bị ép chạy vượt tốc độ tối đa của nó."""
        if machine_len <= 1e-12:
            return feed
        limit = feed
        for letter, value in vb.items():
            d = abs(value - va.get(letter, value))
            if d < 1e-12:
                continue
            ax = self.profile.axis_by_letter(letter)
            if not ax or ax.max_rate <= 0:
                continue
            rate = ax.max_rate
            if ax.role == ROLE_BEVEL and self.motion.bevel_max_rate > 0:
                rate = min(rate, self.motion.bevel_max_rate)
            limit = min(limit, rate * machine_len / d)
        return limit

    def feed_for(
        self,
        a: CutPoint,
        b: CutPoint,
        target_surface_feed: float,
        za: Optional[float] = None,
        zb: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """Trả về (F ghi vào G-code, quãng đường bề mặt, quãng đường trục).

        Đây chính là chỗ bốn trục được "hoà" lại thành một tốc độ cắt duy nhất.
        """
        va = self.axis_values(a, za)
        vb = self.axis_values(b, zb)
        l_real = self.surface_distance(a, b, za, zb)
        l_mach = self.machine_distance(va, vb)
        if l_mach <= 1e-12:
            return (target_surface_feed, l_real, 0.0)
        if l_real <= 1e-9:
            # Chỉ có trục vát/trục phụ chuyển động: chạy ở tốc độ trục cho phép.
            feed = self.motion.max_feed
        else:
            feed = target_surface_feed * (l_mach / l_real)
        feed = self.clamp_by_axis_rates(feed, va, vb, l_mach)
        feed = max(self.motion.min_feed, min(self.motion.max_feed, feed))
        return (feed, l_real, l_mach)

    # ------------------------------------------------------------------
    # Trục xoay
    # ------------------------------------------------------------------
    def shortest_rotary(self, current: float, target: float) -> float:
        """Chọn phương án quay ngắn nhất khi **chạy không** (không cắt).

        Khi đang cắt thì tuyệt đối không dùng hàm này: đường cắt phải quay
        liên tục theo đúng góc luỹ kế, nếu "tối ưu" giữa chừng thì mạch cắt
        sẽ bị lệch cả vòng.
        """
        if not self.motion.rotary_shortest_path:
            return target
        delta = target - current
        k = round(delta / 360.0)
        return target - 360.0 * k

    def unwrap_series(self, thetas: Sequence[float]) -> List[float]:
        """Bảo đảm dãy góc liên tục (không nhảy +-360)."""
        if not thetas:
            return []
        out = [thetas[0]]
        for t in thetas[1:]:
            prev = out[-1]
            k = round((t - prev) / 360.0)
            out.append(t - 360.0 * k)
        return out

    # ------------------------------------------------------------------
    # Kiểm tra giới hạn hành trình
    # ------------------------------------------------------------------
    def check_limits(self, values: AxisValues) -> List[str]:
        msgs: List[str] = []
        for letter, v in values.items():
            ax = self.profile.axis_by_letter(letter)
            if not ax or ax.max_travel <= 0:
                continue  # 0 = không giới hạn (trục xoay)
            lo, hi = min(ax.min_travel, ax.max_travel), max(ax.min_travel, ax.max_travel)
            if v < lo - 1e-6 or v > hi + 1e-6:
                msgs.append(
                    f"Trục {letter} = {v:.2f} vượt hành trình [{lo:.1f}, {hi:.1f}]"
                )
        return msgs
