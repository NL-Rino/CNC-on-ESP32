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

# BA mat thu dat quanh dau xe. Mot mat thi chi biet "co thay hay khong" chu
# khong biet den o dau - xe khong con cach nao ngoai di thang roi hy vong.
# Do duoc: voi mot mat, trong can nha 10 m xe nhin thay den goi 0,8% so buoc
# va toi noi 0,2/5 lan. Ba mat thi so sanh cuong do giua chung la ra huong,
# dung cach robot hut bui that tim de sac.
# Thu tu la TRAI, GIUA, PHAI - goc duong la ben trai (nguoc chieu kim dong
# ho), dung quy uoc cua ca mo phong. Dat nguoc lai la xe lai ngay ra XA den:
# loi do da lam xe san den 400 buoc lien ma khong bao gio toi.
IR_MAT = (1.15, 0.0, -1.15)   # goc dat tung mat so voi dau xe (rad, ~66 do)
IR_FOV = 1.15              # nua goc thu cua MOI mat
IR_RANGE = 6.0             # tam thu hieu qua (m). Trong can nha 10 m thi 3 m
                           # la qua ngan - den goi tat truoc khi xe kip tim ra.
IR_NOISE = 0.03
IR_SEEN = 0.05             # nguong coi la "co tin hieu"


class SensorSuite:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.cliff_front = 0.0
        self.cliff_rear = 0.0
        self.ir = [[0.0] * len(IR_MAT), [0.0] * len(IR_MAT)]
        self.ir_max = [0.0, 0.0]
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
        vals = [[0.0] * len(IR_MAT), [0.0] * len(IR_MAT)]
        for b in world.beacons:
            if not b.active:
                continue
            dx = b.x - rx
            dy = b.y - ry
            d = math.hypot(dx, dy)
            if d > IR_RANGE:
                continue
            ang = math.atan2(dy, dx)
            if b.dir_ang is not None:
                # goc nhin tu den ra xe co nam trong chum phat khong
                if abs(wrap_angle(ang + math.pi - b.dir_ang)) > b.cone:
                    continue
            # KHONG bo qua vach hoc o day: chinh hai vach ben cua hoc bop
            # chum hong ngoai lai con +-24 do o cua. Nho vay xe phai doi dien
            # cai hoc moi bat duoc tin hieu - dung nhu tram sac that.
            if not world.line_of_sight(rx, ry, b.x, b.y):
                continue
            # Mau so 2.5 chu khong phai 0.9: voi 0.9 thi o 4 m cuong do chi
            # con 0.048, duoi ca nguong "co thay" 0.05 - tuc la khai bao tam
            # 6 m nhung thuc te chi 3,5 m, va xe di ngang cach den 3 m van
            # khong thay gi. Do duoc: 0-0,5%% so buoc la thay den goi.
            atten = 1.0 / (1.0 + (d / 2.5) ** 2)
            ch = b.channel
            for k, mat in enumerate(IR_MAT):
                off = abs(wrap_angle(ang - robot.theta - mat))
                if off > IR_FOV:
                    continue
                lobe = math.cos(off * math.pi / (2.0 * IR_FOV)) ** 2
                v = b.power * lobe * atten + rng.gauss(0.0, IR_NOISE)
                v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                if v > vals[ch][k]:
                    vals[ch][k] = v
        self.ir = vals
        self.ir_max = [max(v) for v in vals]
        self.ir_seen = [1.0 if m > IR_SEEN else 0.0 for m in self.ir_max]
        return vals, self.ir_seen

    def read_all(self, robot, world, rng):
        self.read_cliff(robot, world, rng)
        self.read_ir(robot, world, rng)
        return self

    def as_dict(self):
        return {"cliff": [self.cliff_front, self.cliff_rear],
                "ir": [list(v) for v in self.ir]}
