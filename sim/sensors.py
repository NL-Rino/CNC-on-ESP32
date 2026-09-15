"""Mo hinh cam bien: 5 sieu am, 2 cam bien vuc, 1 mat thu hong ngoai, do pin.

Moi cam bien co nhieu + do tre + loi that (sieu am doi khi mat echo) de
policy hoc duoc khong tin tuyet doi vao mot lan doc.
"""
import math

from .geometry import wrap_angle

# Goc lap 5 cam bien sieu am so voi dau xe (rad)
SONAR_ANGLES = (-math.pi / 2, -math.pi / 4, 0.0, math.pi / 4, math.pi / 2)
SONAR_MAX = 2.00           # tam do toi da (m)
SONAR_MIN = 0.03           # vung mu
SONAR_CONE = 0.13          # nua goc chum tia (rad) ~ 7.5 do
SONAR_NOISE = 0.012        # sai so (m)
SONAR_DROP = 0.02          # xac suat mat echo moi lan do

CLIFF_TRIG = 0.045         # nguong cao do (m) de bao "co vuc"
CLIFF_NOISE = 0.003
TABLE_DROP = 0.40          # do cao tu mat ban xuong san (m)

IR_FOV = 0.80              # nua goc thu hong ngoai (rad) ~ 46 do
IR_RANGE = 3.0             # tam thu hieu qua (m)
IR_NOISE = 0.03


class SensorSuite:
    def __init__(self, spec):
        self.spec = spec
        self.n_sonar = len(SONAR_ANGLES)
        self.reset()

    def reset(self):
        self.sonar = [SONAR_MAX] * self.n_sonar
        self.cliff_front = 0.0
        self.cliff_rear = 0.0
        self.ir = [0.0, 0.0]        # cuong do 2 kenh
        self.ir_seen = [0.0, 0.0]   # co con nhin thay khong (0/1)

    # ------------------------------------------------------------------- sieu am
    def read_sonar(self, robot, world, rng):
        out = self.sonar
        for i, a in enumerate(SONAR_ANGLES):
            ang = robot.theta + a
            ox, oy = robot.sensor_point(self.spec.radius * 0.9 * math.cos(a),
                                        self.spec.radius * 0.9 * math.sin(a))
            # chum tia: lay gia tri nho nhat trong 3 tia
            d = world.raycast(ox, oy, ang, SONAR_MAX)
            d1 = world.raycast(ox, oy, ang - SONAR_CONE, SONAR_MAX)
            if d1 < d:
                d = d1
            d2 = world.raycast(ox, oy, ang + SONAR_CONE, SONAR_MAX)
            if d2 < d:
                d = d2
            if d < SONAR_MAX:
                d += rng.gauss(0.0, SONAR_NOISE)
                if rng.random() < SONAR_DROP:
                    d = SONAR_MAX      # mat echo -> bao "trong"
            if d < SONAR_MIN:
                d = SONAR_MIN
            elif d > SONAR_MAX:
                d = SONAR_MAX
            out[i] = d
        return out

    # -------------------------------------------------------------- cam bien vuc
    def read_cliff(self, robot, world, rng):
        """Hai cam bien chieu xuong o dau va duoi xe.

        Tra ve (front, rear) = 1.0 khi phat hien khong con mat ban ben duoi.
        """
        res = []
        for off in (self.spec.cliff_fwd, self.spec.cliff_rear):
            px, py = robot.sensor_point(off)
            h = 0.0 if world.on_table(px, py) else TABLE_DROP
            h += rng.gauss(0.0, CLIFF_NOISE)
            res.append(1.0 if h > CLIFF_TRIG else 0.0)
        self.cliff_front, self.cliff_rear = res
        return res

    # ---------------------------------------------------------------- hong ngoai
    def read_ir(self, robot, world, rng):
        """Mat thu o dau xe: moi kenh tra ve cuong do 0..1.

        Cuong do giam theo goc lech va binh phuong khoang cach, bi vat can chan.
        Chi co MOT mat thu -> muon biet huong thi xe phai xoay va so sanh.
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
            off = abs(wrap_angle(math.atan2(dy, dx) - robot.theta))
            if off > IR_FOV:
                continue
            if not world.line_of_sight(rx, ry, b.x, b.y):
                continue
            lobe = math.cos(off * math.pi / (2.0 * IR_FOV)) ** 2
            atten = 1.0 / (1.0 + (d / 0.9) ** 2)
            s = b.power * lobe * atten
            s += rng.gauss(0.0, IR_NOISE)
            if s < 0.0:
                s = 0.0
            elif s > 1.0:
                s = 1.0
            ch = b.channel
            if s > vals[ch]:
                vals[ch] = s
            if s > 0.05:
                seen[ch] = 1.0
        self.ir = vals
        self.ir_seen = seen
        return vals, seen

    def read_all(self, robot, world, rng):
        self.read_sonar(robot, world, rng)
        self.read_cliff(robot, world, rng)
        self.read_ir(robot, world, rng)
        return self

    def as_dict(self):
        return {"sonar": list(self.sonar),
                "cliff": [self.cliff_front, self.cliff_rear],
                "ir": list(self.ir)}
