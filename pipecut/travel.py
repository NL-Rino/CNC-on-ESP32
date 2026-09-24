"""Chạy không giữa hai đường cắt, theo kiểu máy laser cắt ống thật.

Cách cũ: tắt mỏ -> nhấc thẳng lên chiều cao an toàn -> chạy ngang -> hạ thẳng
xuống.  Ba lệnh riêng nên máy **dừng hẳn hai lần** giữa chừng, và luôn nhấc lên
đủ chiều cao an toàn (20 mm) kể cả khi chỉ nhảy sang lỗ bên cạnh trên ống tròn,
nơi mặt ống chỗ nào cũng cao như nhau.

Cách ở đây, giống chế độ "nhảy ếch" (leapfrog) của máy laser:

1. **Chỉ nhấc cao vừa đủ.**  Tính chỗ kim loại cao nhất nằm dưới thân mỏ dọc
   suốt đường đi - kể cả góc ống hộp nhô lên khi xoay qua - rồi cộng khoảng
   hở ``travel_height``.  Ống tròn chạy dọc hay xoay thì mặt ống không đổi nên
   chỉ nhấc vài mm; ống hộp xoay qua góc thì tự nhấc cao hơn.
2. **Vừa nhấc vừa đi, vừa đi vừa hạ** theo một cung trơn: rời điểm cắt theo
   phương thẳng đứng (không kéo lê béc qua xỉ), uốn dần sang ngang, tới nơi thì
   hạ xuống cũng thẳng đứng.  Cung được chia đủ mịn để bộ lập kế hoạch của
   FluidNC chạy qua mà không phải hãm lại.
3. **Kiểm va chạm từng điểm** dọc cung, có tính bề rộng thân mỏ.  Cung nào sát
   phôi hơn mức cho phép thì rút ngắn quãng uốn; tới cùng thì quay về đúng kiểu
   nhấc thẳng - hạ thẳng, kiểu này luôn an toàn vì chỉ chạy ngang ở độ cao đã
   tính qua điểm cao nhất.

Máy có trục vát (đầu cắt nghiêng) thì giữ nguyên cách cũ: đầu nghiêng quét
thân mỏ theo cung, mô hình mỏ thẳng đứng ở đây không bảo đảm được.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .config import (ROLE_BEVEL, ROLE_CROSS, ROLE_RADIAL, ROLE_ROTARY,
                     MachineProfile)

AxisValues = Dict[str, float]


class SurfaceEnvelope:
    """Độ cao kim loại cao nhất dưới một khoảng ngang, ở một góc xoay bất kỳ.

    Ống tròn tính thẳng bằng công thức.  Tiết diện khác thì dựng sẵn bảng
    đường bao trên theo từng nấc góc xoay (tính một lần, dùng lại), và mọi làm
    tròn đều nghiêng về phía **cao hơn** thực tế - sai thì chỉ nhấc thừa chút
    ít, không bao giờ nhấc thiếu.
    """

    def __init__(self, section, step: float = 0.2, dtheta: float = 0.5):
        self.section = section
        self.round = getattr(section, "kind", "") == "round"
        self.R = float(section.max_radius)
        self.ref = float(section.reference_height)
        self.step = step
        self.dtheta = dtheta
        self._span = self.R + 2.0 * step
        self._n = int(math.ceil(2.0 * self._span / step)) + 1
        self._poly = [] if self.round else list(section.outline(720))
        self._cache: Dict[int, List[float]] = {}

    # -- bảng đường bao cho một nấc góc --
    def _grid(self, k: int) -> List[float]:
        key = k % int(round(360.0 / self.dtheta))
        env = self._cache.get(key)
        if env is not None:
            return env
        a = math.radians(key * self.dtheta)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(cx * ca - cy * sa, cx * sa + cy * ca) for cx, cy in self._poly]
        env = [-math.inf] * self._n
        span, step, n = self._span, self.step, self._n
        m = len(pts)
        for i in range(m):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % m]
            # đỉnh đa giác: rải vào cả hai ô lưới kề bên cho chắc
            f = (x0 + span) / step
            for j in (int(math.floor(f)), int(math.ceil(f))):
                if 0 <= j < n and y0 > env[j]:
                    env[j] = y0
            if x1 < x0:
                x0, y0, x1, y1 = x1, y1, x0, y0
            j0 = max(0, int(math.ceil((x0 + span) / step)))
            j1 = min(n - 1, int(math.floor((x1 + span) / step)))
            dx = x1 - x0
            for j in range(j0, j1 + 1):
                x = -span + j * step
                y = y0 if dx < 1e-12 else y0 + (y1 - y0) * (x - x0) / dx
                if y > env[j]:
                    env[j] = y
        self._cache[key] = env
        return env

    def top(self, theta: float, lo: float, hi: float) -> float:
        """Độ cao (tính từ tâm phôi) của kim loại cao nhất có x trong [lo, hi]."""
        if lo > hi:
            lo, hi = hi, lo
        if self.round:
            if lo <= 0.0 <= hi:
                return self.R
            d = min(abs(lo), abs(hi))
            return math.sqrt(self.R * self.R - d * d) if d < self.R else -math.inf
        k0 = int(math.floor(theta / self.dtheta))
        j0 = max(0, int(math.floor((lo + self._span) / self.step)))
        j1 = min(self._n - 1, int(math.ceil((hi + self._span) / self.step)))
        if j1 < j0:
            return -math.inf
        best = -math.inf
        for k in (k0, k0 + 1):          # hai nấc góc kề bên, lấy cái cao hơn
            env = self._grid(k)
            for j in range(j0, j1 + 1):
                if env[j] > best:
                    best = env[j]
        return best


class TravelPlanner:
    """Sinh đường chạy không giữa hai tư thế máy, có kiểm va chạm."""

    def __init__(self, profile: MachineProfile, section=None):
        self.profile = profile
        self.section = section or profile.pipe.section()
        self.env = SurfaceEnvelope(self.section)
        pr, mo = profile.process, profile.motion
        self.clearance = max(0.0, float(getattr(pr, "travel_height", 0.0)))
        self.half_width = max(0.0, float(getattr(mo, "torch_width", 16.0))) / 2.0
        self.ramp = max(0.0, float(getattr(mo, "leapfrog_ramp", 10.0)))
        self.leapfrog = bool(getattr(mo, "leapfrog", True))
        self.steps = max(3, int(getattr(mo, "leapfrog_steps", 10)))
        self.gap_min = max(0.2, min(pr.cut_height, pr.pierce_height))
        self.ax_z = profile.axis(ROLE_RADIAL)
        self.ax_a = profile.axis(ROLE_ROTARY)
        self.ax_x = profile.axis(ROLE_CROSS)
        self.ax_b = profile.axis(ROLE_BEVEL)

    @property
    def enabled(self) -> bool:
        """Có dùng cách chạy không mới hay giữ kiểu nhấc lên chiều cao an toàn."""
        return self.ax_z is not None and self.clearance > 0.0

    # -- đổi qua lại giữa giá trị trục và toạ độ thật --
    @staticmethod
    def _phys(ax, value: float) -> float:
        v = value - ax.offset
        return -v if ax.invert else v

    def _theta(self, vals: AxisValues) -> float:
        return self._phys(self.ax_a, vals[self.ax_a.letter]) if self.ax_a and \
            self.ax_a.letter in vals else 0.0

    def _cross(self, vals: AxisValues) -> float:
        return self._phys(self.ax_x, vals[self.ax_x.letter]) if self.ax_x and \
            self.ax_x.letter in vals else 0.0

    def work_z(self, vals: AxisValues) -> float:
        return self._phys(self.ax_z, vals[self.ax_z.letter])

    def surface_top(self, theta: float, cross: float) -> float:
        """Độ cao (theo gốc Z chi tiết) của kim loại cao nhất dưới thân mỏ."""
        return self.env.top(theta, cross - self.half_width, cross + self.half_width) - self.env.ref

    # -- lấy mẫu dọc đường đi thẳng giữa hai tư thế --
    def _samples(self, t0: float, t1: float, c0: float, c1: float) -> int:
        return int(min(720, max(12, math.ceil(abs(t1 - t0) / 1.0),
                                math.ceil(abs(c1 - c0) / 1.0))))

    def cruise_height(self, p0: AxisValues, p1: AxisValues) -> float:
        """Độ cao phải giữ khi chạy ngang để qua được mọi chỗ cao dưới thân mỏ."""
        t0, t1 = self._theta(p0), self._theta(p1)
        c0, c1 = self._cross(p0), self._cross(p1)
        n = self._samples(t0, t1, c0, c1)
        top = max(self.surface_top(t0 + (t1 - t0) * i / n, c0 + (c1 - c0) * i / n)
                  for i in range(n + 1))
        return top + self.clearance

    # ------------------------------------------------------------------
    def hop(self, p0: AxisValues, p1: AxisValues) -> List[AxisValues]:
        """Danh sách điểm G0 đi từ ``p0`` (vừa cắt xong) tới ``p1`` (điểm mồi).

        Điểm cuối cùng luôn đúng bằng ``p1``.  Trả về rỗng nếu không dùng được
        cách mới (máy không có trục Z, hoặc người dùng tắt).
        """
        if not self.enabled or self.ax_z.letter not in p0 or self.ax_z.letter not in p1:
            return []
        zl = self.ax_z.letter
        z0, z1 = self.work_z(p0), self.work_z(p1)
        H = max(self.cruise_height(p0, p1), z0, z1)
        lateral = [c for c in set(p0) | set(p1) if c != zl]
        d = {c: p1.get(c, p0.get(c, 0.0)) - p0.get(c, p1.get(c, 0.0)) for c in lateral}
        D = math.sqrt(sum(v * v for v in d.values()))

        def at(p: float, z: float) -> AxisValues:
            f = 0.0 if D < 1e-12 else p / D
            out = {c: p0.get(c, p1.get(c, 0.0)) + d[c] * f for c in lateral}
            out[zl] = self.ax_z.apply(z)
            return out

        # Đầu cắt đang nghiêng thì thân mỏ quét theo cung, mô hình mỏ thẳng
        # đứng ở đây không bảo đảm được - để người gọi dùng chiều cao an toàn.
        if self.ax_b is not None and any(
                abs(self._phys(self.ax_b, p.get(self.ax_b.letter, self.ax_b.offset))) > 1e-6
                for p in (p0, p1)):
            return []
        vertical = [at(0.0, H), at(D, H), dict(p1)]
        if D < 1e-9:
            return [dict(p1)]
        if not self.leapfrog or self.ramp <= 0:
            return vertical

        g0 = z0 - self.surface_top(self._theta(p0), self._cross(p0))
        g1 = z1 - self.surface_top(self._theta(p1), self._cross(p1))
        allowed = min(self.gap_min, g0, g1) - 1e-6
        r = self.ramp
        while r >= 0.5:
            path = self._arc_path(D, z0, z1, H, r)
            if self._clear(path, p0, p1, D, allowed):
                pts = [at(p, z) for p, z in path]
                pts[-1] = dict(p1)
                return pts
            r /= 2.0
        return vertical

    def _arc_path(self, D: float, z0: float, z1: float, H: float,
                  r: float) -> List[Tuple[float, float]]:
        """Cung (quãng ngang, độ cao): rời thẳng đứng, uốn sang ngang, hạ thẳng đứng.

        Mỗi đầu là một phần tư elip: ``p = r(1 - cos φ)``, ``z = z0 + (H - z0) sin φ``.
        Ở φ = 0 hướng đi thẳng đứng nên béc không bị kéo lê qua xỉ vừa cắt.
        """
        r = min(r, D / 2.0)
        k = self.steps
        out: List[Tuple[float, float]] = []
        for i in range(1, k + 1):
            phi = 0.5 * math.pi * i / k
            out.append((r * (1.0 - math.cos(phi)), z0 + (H - z0) * math.sin(phi)))
        if D - r > r + 1e-6:
            out.append((D - r, H))
        for i in range(k - 1, -1, -1):
            phi = 0.5 * math.pi * i / k
            out.append((D - r * (1.0 - math.cos(phi)), z1 + (H - z1) * math.sin(phi)))
        return out

    def _clear(self, path: List[Tuple[float, float]], p0: AxisValues, p1: AxisValues,
               D: float, allowed: float) -> bool:
        """Mọi điểm dọc cung (lấy mẫu dày) đều cách kim loại ít nhất ``allowed``."""
        t0, t1 = self._theta(p0), self._theta(p1)
        c0, c1 = self._cross(p0), self._cross(p1)
        z_start = self.work_z(p0)
        prev = (0.0, z_start)
        for p, z in path:
            fa, fb = prev[0] / D, p / D
            n = max(2, self._samples(t0 + (t1 - t0) * fa, t0 + (t1 - t0) * fb,
                                     c0 + (c1 - c0) * fa, c0 + (c1 - c0) * fb))
            for i in range(n + 1):
                w = i / n
                f = fa + (fb - fa) * w
                zz = prev[1] + (z - prev[1]) * w
                if zz - self.surface_top(t0 + (t1 - t0) * f, c0 + (c1 - c0) * f) < allowed:
                    return False
            prev = (p, z)
        return True
