"""Cam bien khong phai LiDAR: 2 mat do vuc chieu xuong va 1 mat thu hong ngoai.

LiDAR quet ngang nen KHONG thay mep ban (tia di thang ra ngoai khong co gi doi
ve) - y het ngoai doi. Chi hai mat chieu xuong cuu duoc xe.
"""
import math

from .geometry import wrap_angle
from .world import IR_CALL, IR_DOCK  # noqa: F401

CLIFF_TRIG = 0.045         # nguong cao do (m) de bao "co vuc"
CLIFF_NOISE = 0.003
TABLE_DROP = 0.40          # do cao tu mat ban xuong san (m)

IR_FOV = 0.80              # nua goc thu cua mat xe (rad) ~ 46 do
IR_RANGE = 3.0             # tam thu hieu qua (m)
IR_NOISE = 0.03
IR_SEEN = 0.05             # nguong coi la "co tin hieu"


class SensorSuite:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.cliff_front = 0.0
        self.cliff_rear = 0.0
        self.ir = [0.0, 0.0]
        self.ir_seen = [0.0, 0.0]

    def read_cliff(self, robot, world, rng):
        """Hai mat chieu xuong o dau va duoi xe. 1.0 = duoi do khong con ban."""
        res = []
        for off in (self.spec.cliff_fwd, self.spec.cliff_rear):
            px, py = robot.sensor_point(off)
            h = 0.0 if world.on_table(px, py) else TABLE_DROP
            h += rng.gauss(0.0, CLIFF_NOISE)
            res.append(1.0 if h > CLIFF_TRIG else 0.0)
        self.cliff_front, self.cliff_rear = res
        return res

    def read_ir(self, robot, world, rng):
        """Mat thu o dau xe. Moi kenh tra ve cuong do 0..1.

        Tram sac phat co huong (chi toa ra phia truoc mat no), nen xe chi bat
        duoc tin hieu khi dung o phia truoc tram VA dang quay dau ve phia do.
        """
        rx, ry = robot.sensor_point(self.spec.ir_offset)
        vals = [0.0, 0.0]
        seen = [0.0, 0.0]
        for b in world.beacons:
            if not b.active:
                continue
            dx = b.x - rx
            dy = b.y - ry
            d = math.hypot(dx, dy)
            if d > IR_RANGE:
                continue
            ang = math.atan2(dy, dx)
            off = abs(wrap_angle(ang - robot.theta))
            if off > IR_FOV:
                continue
            if b.dir_ang is not None:
                # goc nhin tu den ra xe co nam trong chum phat khong
                if abs(wrap_angle(ang + math.pi - b.dir_ang)) > b.cone:
                    continue
            # KHONG bo qua vach hoc o day: chinh hai vach ben cua hoc bop
            # chum hong ngoai lai con +-24 do o cua. Nho vay xe phai doi dien
            # cai hoc moi bat duoc tin hieu - dung nhu tram sac that.
            if not world.line_of_sight(rx, ry, b.x, b.y):
                continue
            lobe = math.cos(off * math.pi / (2.0 * IR_FOV)) ** 2
            atten = 1.0 / (1.0 + (d / 0.9) ** 2)
            s = b.power * lobe * atten + rng.gauss(0.0, IR_NOISE)
            s = 0.0 if s < 0.0 else (1.0 if s > 1.0 else s)
            ch = b.channel
            if s > vals[ch]:
                vals[ch] = s
            if s > IR_SEEN:
                seen[ch] = 1.0
        self.ir = vals
        self.ir_seen = seen
        return vals, seen

    def read_all(self, robot, world, rng):
        self.read_cliff(robot, world, rng)
        self.read_ir(robot, world, rng)
        return self

    def as_dict(self):
        return {"cliff": [self.cliff_front, self.cliff_rear], "ir": list(self.ir)}
