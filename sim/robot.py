"""Mo hinh dong luc hoc xe: 2 cap banh DC (vi sai) + pin."""
import math

from .geometry import clamp, wrap_angle


class RobotSpec:
    """Thong so vat ly cua xe - doi o day khi dung khung xe that.

    Than xe TRON duong kinh 30 cm. Tron thi de hon vuong nhieu khi chui vao
    hoc sac: chi can dung truc trong pham vi 5 mm, KHONG co rang buoc goc
    quay. Xe vuong cung kich thuoc nghieng 2 do la da can khe 31.0 cm.
    """
    radius = 0.150          # ban kinh than xe (m)
    wheel_base = 0.240      # khoang cach 2 ben banh (m)
    v_max = 0.50            # toc do banh toi da (m/s) o PWM 100%
    motor_tau = 0.12        # hang so thoi gian dap ung motor (s)
    deadband = 0.06         # PWM duoi muc nay khong du thang ma sat tinh
    slip_noise = 0.02       # nhieu truot banh (ti le)
    cliff_fwd = 0.145       # vi tri cam bien vuc truoc (m, tu tam xe)
    cliff_rear = -0.145     # vi tri cam bien vuc sau
    ir_offset = 0.140       # mat thu hong ngoai o dau xe

    # Odometry (dung de nho vi tri tram sac giua cac chuyen di)
    odo_scale_err = 0.025   # sai so ti le duong kinh banh moi ben
    # 0.0015 rad/s = 0.086 do/s: con quay MPU6050/ICM ĐÃ HIỆU CHUẨN (do do
    # lech luc dung yen roi tru di). Chua hieu chuan thi khoang 0.57 do/s,
    # tuc sau 150 giay lech 86 do - do duoc trong mo phong: tri nho vi tri
    # tram sai toi 2,7 m, xe khong con tim duoc duong ve. Voi nha to va
    # chuyen di 5 phut thi hieu chuan con quay la BAT BUOC, khong phai tuy chon.
    odo_gyro_bias = 0.0015  # troi goc (rad/s)

    # Pin
    batt_capacity = 1.0
    batt_idle = 0.0020      # tieu hao khi dung yen (don vi/giay)
    batt_drive = 0.0170     # tieu hao them khi chay het ga (don vi/giay)
    charge_rate = 0.100     # toc do sac khi cam dung dock (don vi/giay)


class Robot:
    """Trang thai xe. Dieu khien bang (u_left, u_right) trong [-1, 1]."""

    def __init__(self, spec: RobotSpec = None):
        self.spec = spec or RobotSpec()
        self.reset(0.0, 0.0, 0.0, 1.0)

    def reset(self, x, y, theta, battery=1.0, rng=None):
        self.x = x
        self.y = y
        self.theta = theta
        # Odometry bat dau trung voi that, roi troi dan - dung nhu ngoai doi
        self.ox = x
        self.oy = y
        self.oth = theta
        if rng is not None:
            self.sl = 1.0 + rng.gauss(0.0, self.spec.odo_scale_err)
            self.sr = 1.0 + rng.gauss(0.0, self.spec.odo_scale_err)
            self.gbias = rng.gauss(0.0, self.spec.odo_gyro_bias)
        else:
            self.sl = self.sr = 1.0
            self.gbias = 0.0
        self.vl = 0.0          # toc do banh trai thuc te (m/s)
        self.vr = 0.0
        self.v = 0.0           # toc do tien (m/s)
        self.omega = 0.0       # toc do quay (rad/s)
        self.battery = battery
        self.bumped = False
        self.bump_bay = False      # cham vach hoc (co xat khi chui vao la thuong)
        self.on_dock = False       # tiep diem sac dang cham (co dien hay khong
                                   # la chuyen khac - do la viec cua bat tay IR)
        self.fallen = False
        self.charging = False

    # ------------------------------------------------------------------ dong hoc
    def _motor(self, u, v_now, dt, rng):
        u = clamp(u, -1.0, 1.0)
        if abs(u) < self.spec.deadband:
            u = 0.0
        target = u * self.spec.v_max
        k = dt / (self.spec.motor_tau + dt)
        v = v_now + (target - v_now) * k
        if self.spec.slip_noise > 0.0:
            v += rng.gauss(0.0, self.spec.slip_noise) * self.spec.v_max * dt / 0.05
        return v

    def step(self, u_left, u_right, dt, world, rng):
        """Cap nhat mot buoc. Tra ve True neu xe roi khoi ban."""
        s = self.spec
        self.vl = self._motor(u_left, self.vl, dt, rng)
        self.vr = self._motor(u_right, self.vr, dt, rng)
        self.v = 0.5 * (self.vl + self.vr)
        self.omega = (self.vr - self.vl) / s.wheel_base

        nx = self.x + self.v * math.cos(self.theta) * dt
        ny = self.y + self.v * math.sin(self.theta) * dt
        ntheta = wrap_angle(self.theta + self.omega * dt)

        # Va cham voi vat can: truot doc / chan lai
        self.bumped = False
        self.bump_bay = False
        if world.boundary == "wall" and not world.inside(nx, ny, s.radius):
            # Phong kin: bien la TUONG, dam vao thi dung chu khong roi
            self.bumped = True
            nx = min(max(nx, s.radius), world.width - s.radius)
            ny = min(max(ny, s.radius), world.height - s.radius)
            self.vl *= 0.3
            self.vr *= 0.3
        if world.min_obstacle_clearance(nx, ny) < s.radius:
            self.bumped = True
            # Cham vach hoc thi khac cham vat can: khe chui vao chi ho 5 mm
            # moi ben nen xat nhe hai ben la chuyen binh thuong, dung phat.
            # Thu phep re nhat truoc: in_bay_corridor chi la vai phep nhan,
            # con bay_clearance phai duyet 9 vach x moi cai hoc.
            self.bump_bay = (world.in_bay_corridor(nx, ny, ntheta, s.radius)
                             and world.bay_clearance(nx, ny) < s.radius)
            # Mat vat cheo o mieng hoc nan xe ve giua truoc da
            wd = world.wedge(nx, ny, ntheta, s.radius) if self.bump_bay else None
            if wd is not None:
                self.x, self.y, self.theta = wd[0], wd[1], ntheta
                self.vl *= 0.85
                self.vr *= 0.85
                self._odo(dt)
                if not world.on_table(self.x, self.y):
                    self.fallen = True
                self._drain(dt)
                return self.fallen
            # thu truot theo tung truc de xe khong bi dinh cung
            if world.min_obstacle_clearance(nx, self.y) >= s.radius:
                ny = self.y
            elif world.min_obstacle_clearance(self.x, ny) >= s.radius:
                nx = self.x
            else:
                nx, ny = self.x, self.y
            self.vl *= 0.3
            self.vr *= 0.3

        self.x, self.y, self.theta = nx, ny, ntheta
        self._odo(dt)
        if not world.on_table(self.x, self.y):
            self.fallen = True
        self._drain(dt)
        return self.fallen

    def _odo(self, dt):
        """Odometry: xe chi biet minh di duoc bao nhieu qua banh xe, ma banh
        thi truot va hai ben khong bang nhau -> uoc luong troi dan."""
        s = self.spec
        vlo = self.vl * self.sl
        vro = self.vr * self.sr
        vo = 0.5 * (vlo + vro)
        wo = (vro - vlo) / s.wheel_base + self.gbias
        self.ox += vo * math.cos(self.oth) * dt
        self.oy += vo * math.sin(self.oth) * dt
        self.oth = wrap_angle(self.oth + wo * dt)

    def _drain(self, dt):
        s = self.spec
        effort = 0.5 * (abs(self.vl) + abs(self.vr)) / s.v_max
        self.battery -= (s.batt_idle + s.batt_drive * effort) * dt
        if self.battery < 0.0:
            self.battery = 0.0

    # ------------------------------------------------------------------- tram sac
    def docked(self, world):
        """Tiep diem sac co dang cham khong.

        Day la tin hieu PHAN CUNG THAT (dien ap tren tiep diem), khong phai
        suy luan. Nho vay xe vua bat nguon trong hoc la biet ngay tram cua no
        o dau, khong can nhin thay gi. Khac voi try_charge: tiep diem cham
        khong co nghia la co dien - con phai bat tay hong ngoai da.
        """
        d = world.dock
        if d is None:
            return False
        px, py = d.pocket
        return (math.hypot(self.x - px, self.y - py) < 0.10 and
                abs(wrap_angle(self.theta - d.heading)) < 0.30)

    def try_charge(self, world, dt, ir_ok=True):
        """Sac neu dang dung dung o cam, dung huong, va da bat tay hong ngoai.

        `ir_ok`: vua nhan duoc tin hieu hong ngoai cua tram trong vai buoc gan
        day. Tram sac that cung lam vay - khong co bat tay thi khong dong dien.
        """
        self.charging = False
        dock = world.dock
        self.on_dock = self.docked(world)
        if dock is None or not ir_ok:
            return 0.0
        px, py = dock.pocket
        d = math.hypot(self.x - px, self.y - py)
        align = abs(wrap_angle(self.theta - dock.heading))
        # Da chui han vao trong hoc: khe chi ho 5 mm moi ben nen toi day
        # goc quay gan nhu chac chan da dung, chi con phai vao du sau.
        if d < 0.10 and align < 0.30 and abs(self.v) < 0.10:
            before = self.battery
            self.battery = min(self.spec.batt_capacity,
                               self.battery + self.spec.charge_rate * dt)
            self.charging = True
            return self.battery - before
        return 0.0

    def sensor_point(self, offset_fwd, offset_side=0.0):
        c = math.cos(self.theta)
        s = math.sin(self.theta)
        return (self.x + offset_fwd * c - offset_side * s,
                self.y + offset_fwd * s + offset_side * c)

    def odo_pose(self):
        return self.ox, self.oy, self.oth

    def as_dict(self):
        return {"x": self.x, "y": self.y, "th": self.theta,
                "batt": self.battery, "charging": self.charging,
                "bump": self.bumped, "v": self.v, "w": self.omega}

