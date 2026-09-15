"""Dung vector quan sat tu du lieu cam bien THO.

Module nay la cho DUY NHAT bien tin hieu cam bien thanh 46 so ma bo nao an.
Ca mo phong (sim/env.py) lan robot that (link/brain_server.py) deu goi vao
day - neu hai ben tu dung lay vector rieng thi chi can mot ben lech mot chi
so la bo nao chay tren ban se hanh xu khac han luc huan luyen, ma kieu loi
do gan nhu khong the tim ra tren phan cung.

Dau vao chi gom nhung thu phan cung that co:
  - mot vong quet LiDAR (mang khoang cach, 0 = khong co tia ve) + goc xe luc quet
  - 2 bit cam bien vuc
  - 2 kenh cuong do hong ngoai
  - muc pin
  - odometry cua chinh xe (x, y, goc) - co troi, va DUNG cai troi do
  - van toc, toc do quay, co va cham
Khong co toa do that, khong co ban do.
"""
import math

import numpy as np

from .dock_detector import MAX_CAND, detect
from .geometry import clamp, wrap_angle
from .lidar import RMAX, SECTORS

SEC_CLIP = 3.0          # tam nhin dua vao mang no-ron (m) - xa hon coi la "trong"
MEM_CLIP = 3.0
E_PER_M_0 = 0.045       # uoc luong ban dau: pin hao moi met

OBS_DIM = SECTORS + 2 + 6 * MAX_CAND + 6 + 6 + 3 + 5

OBS_NAMES = (
    ["lidar_sector_%02d" % i for i in range(SECTORS)] +
    ["cliff_front", "cliff_rear"] +
    sum([["cand%d_seen" % i, "cand%d_sin" % i, "cand%d_cos" % i,
          "cand%d_dist" % i, "cand%d_yawsin" % i, "cand%d_yawcos" % i]
         for i in range(MAX_CAND)], []) +
    ["ir_call", "ir_call_seen", "ir_dock", "ir_dock_seen", "d_ir_call", "d_ir_dock"] +
    ["mem_known", "mem_sin", "mem_cos", "mem_dist", "mem_headsin", "mem_headcos"] +
    ["battery", "battery_low", "return_margin"] +
    ["vel", "yaw_rate", "prev_u_left", "prev_u_right", "bump"]
)
assert len(OBS_NAMES) == OBS_DIM


class Perception:
    """Trang thai suy dien cua xe: tri nho tram sac, kinh nghiem hao pin, IR.

    Doi tuong nay CO TRI NHO giua cac buoc, nen phai reset() moi chuyen di.
    """

    def __init__(self, battery_low=0.40, ir_handshake=30, v_max=0.50,
                 wheel_base=0.240):
        self.battery_low = battery_low
        self.ir_handshake = ir_handshake      # so buoc con nho tin hieu IR
        self.v_max = v_max
        self.om_max = 2.0 * v_max / wheel_base
        self._n = 0
        self.reset()

    def reset(self, battery=1.0):
        self.steps = 0
        self.cands = []
        self.mem = None                # (x, y, goc truc) trong he odometry
        self.mem_age = 0
        self.ir_hand = -10 ** 9        # buoc cuoi cung con thay IR tram sac
        self.prev_ir = [0.0, 0.0]
        self.prev_u = [0.0, 0.0]
        self.odo_prev = None
        self.batt_prev = battery
        self.trip_dist = 0.0
        self.trip_batt = 0.0
        self.e_per_m = E_PER_M_0

    # ------------------------------------------------------------------ LiDAR
    def _prepare(self, n):
        """Bang goc/cos/sin cho vong quet - tinh mot lan, dung mai."""
        if n != self._n:
            self._n = n
            self.base = np.linspace(-math.pi, math.pi, n,
                                    endpoint=False).astype(np.float32)
            self.cos_base = np.cos(self.base)
            self.sin_base = np.sin(self.base)
            self.sectors = np.zeros(SECTORS, dtype=np.float32)

    def _sector_ranges(self, ranges, shift):
        rr = np.roll(np.where(ranges <= 0.0, RMAX, ranges), shift)
        return rr.reshape(SECTORS, -1).min(axis=1)

    # ------------------------------------------------------------------- tri nho
    def _remember_dock(self, odo):
        """Hong ngoai xac nhan: ghi lai tram theo he odometry cua chinh xe.

        Mat thu nam o dau xe nen co tin hieu nghia la tram dang o phia truoc.
        Lay ung vien LiDAR gan nhat trong quat truoc mat lam vi tri, va lay
        luon goc truc cua no - hoc chi chui vao duoc tu mot phia.
        """
        ox, oy, oth = odo
        best = None
        for c in self.cands:
            if abs(c.bearing) < 0.45 and (best is None or c.dist < best.dist):
                best = c
        if best is not None:
            a = oth + best.bearing
            self.mem = (ox + best.dist * math.cos(a),
                        oy + best.dist * math.sin(a),
                        wrap_angle(oth + best.yaw))
            self.mem_age = 0

    def memory_polar(self, odo):
        """Khoang cach, goc, huong truc cua tram theo tri nho (he odometry)."""
        if self.mem is None:
            return MEM_CLIP, 0.0, 0.0
        ox, oy, oth = odo
        dx = self.mem[0] - ox
        dy = self.mem[1] - oy
        return (math.hypot(dx, dy), wrap_angle(math.atan2(dy, dx) - oth),
                wrap_angle(self.mem[2] - oth))

    def return_margin(self, dist):
        """Pin con du de ve tram khong? Day la phan "kinh nghiem" cua xe.

        e_per_m la muc hao pin moi met do CHINH XE do duoc tu dau chuyen di,
        qua odometry chu khong qua toa do that.
        """
        if self.mem is None:
            need = 0.35        # chua biet tram o dau -> phai chua du de di tim
        else:
            # 2.0 chu khong phai 1.0: duong ve khong thang, con phai vong ra
            # truoc cua hoc. 0.12 la phan danh cho viec do dam va canh truc.
            need = self.e_per_m * dist * 2.0 + 0.12
        return clamp(self.batt_prev - need, -1.0, 1.0)

    @property
    def ir_ok(self):
        """Con nho bat tay hong ngoai du gan day de duoc phep nap dien khong."""
        return (self.steps - self.ir_hand) <= self.ir_handshake

    # -------------------------------------------------------------------- buoc
    def update(self, ranges, scan_theta, scans_new, odo, cliff, ir,
               battery, v, omega, bumped, charging):
        """Tra ve list OBS_DIM so. Goi dung mot lan moi buoc dieu khien."""
        ox, oy, oth = odo
        self._prepare(len(ranges))

        # Bu phan xe da quay ke tu luc quet. Vong quet mat ~143 ms trong khi
        # vong dieu khien chay 50 ms, nen du lieu luon cu hon thuc te.
        d = (scan_theta - oth) % (2.0 * math.pi)
        shift = int(round(d / (2.0 * math.pi) * self._n)) % self._n
        sec = self._sector_ranges(ranges, shift)

        if scans_new:
            self.cands = detect(self.base, ranges, self.cos_base,
                                self.sin_base, scan_theta - oth)

        ir_call, ir_dock = float(ir[0]), float(ir[1])
        seen_call = 1.0 if ir_call > 0.05 else 0.0
        seen_dock = 1.0 if ir_dock > 0.05 else 0.0
        if seen_dock > 0.5:
            self.ir_hand = self.steps
            self._remember_dock(odo)
        if charging:
            self.mem = (ox, oy, oth)
            self.mem_age = 0

        # Kinh nghiem hao pin: do bang odometry, vi xe khong biet toa do that
        if self.odo_prev is not None:
            moved = math.hypot(ox - self.odo_prev[0], oy - self.odo_prev[1])
            self.trip_dist += moved
            if not charging:
                self.trip_batt += max(0.0, self.batt_prev - battery)
            if self.trip_dist > 0.5:
                e = self.trip_batt / self.trip_dist
                self.e_per_m = 0.9 * self.e_per_m + 0.1 * e
        self.odo_prev = (ox, oy)
        self.batt_prev = battery

        np.minimum(sec, SEC_CLIP, out=sec)
        obs = (sec * (1.0 / SEC_CLIP)).tolist()
        obs.append(float(cliff[0]))
        obs.append(float(cliff[1]))

        for i in range(MAX_CAND):
            if i < len(self.cands):
                c = self.cands[i]
                obs += [1.0, math.sin(c.bearing), math.cos(c.bearing),
                        min(c.dist, SEC_CLIP) / SEC_CLIP,
                        math.sin(c.yaw), math.cos(c.yaw)]
            else:
                obs += [0.0, 0.0, 0.0, 1.0, 0.0, 1.0]

        obs += [ir_call, seen_call, ir_dock, seen_dock,
                clamp((ir_call - self.prev_ir[0]) * 8.0, -1.0, 1.0),
                clamp((ir_dock - self.prev_ir[1]) * 8.0, -1.0, 1.0)]
        self.prev_ir = [ir_call, ir_dock]

        md, mb, mh = self.memory_polar(odo)
        if self.mem is None:
            obs += [0.0, 0.0, 0.0, 1.0, 0.0, 1.0]
        else:
            obs += [1.0, math.sin(mb), math.cos(mb),
                    min(md, MEM_CLIP) / MEM_CLIP, math.sin(mh), math.cos(mh)]

        obs += [battery,
                1.0 if battery < self.battery_low else 0.0,
                self.return_margin(md)]
        obs += [clamp(v / self.v_max, -1.0, 1.0),
                clamp(omega / self.om_max, -1.0, 1.0),
                self.prev_u[0], self.prev_u[1],
                1.0 if bumped else 0.0]

        self.mem_age += 1
        self.steps += 1
        return obs

    def note_action(self, ul, ur):
        """Ghi lenh vua gui xuong - buoc sau bo nao can biet no da lam gi."""
        self.prev_u = [float(ul), float(ur)]
