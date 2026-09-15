"""Mo hinh dong luc hoc xe: 2 cap banh DC (vi sai) + pin."""
import math

from .geometry import clamp, wrap_angle


class RobotSpec:
    """Thong so vat ly cua xe - doi o day khi dung khung xe that."""
    radius = 0.090          # ban kinh than xe (m)
    wheel_base = 0.150      # khoang cach 2 ben banh (m)
    v_max = 0.60            # toc do banh toi da (m/s) o PWM 100%
    motor_tau = 0.12        # hang so thoi gian dap ung motor (s)
    deadband = 0.06         # PWM duoi muc nay khong du thang ma sat tinh
    slip_noise = 0.02       # nhieu truot banh (ti le)
    cliff_fwd = 0.105       # vi tri cam bien vuc truoc (m, tu tam xe)
    cliff_rear = -0.105     # vi tri cam bien vuc sau
    ir_offset = 0.085       # mat thu hong ngoai o dau xe

    # Pin
    batt_capacity = 1.0
    batt_idle = 0.0016      # tieu hao khi dung yen (don vi/giay)
    batt_drive = 0.0075     # tieu hao them khi chay het ga (don vi/giay)
    charge_rate = 0.060     # toc do sac khi cam dung dock (don vi/giay)


class Robot:
    """Trang thai xe. Dieu khien bang (u_left, u_right) trong [-1, 1]."""

    def __init__(self, spec: RobotSpec = None):
        self.spec = spec or RobotSpec()
        self.reset(0.0, 0.0, 0.0, 1.0)

    def reset(self, x, y, theta, battery=1.0):
        self.x = x
        self.y = y
        self.theta = theta
        self.vl = 0.0          # toc do banh trai thuc te (m/s)
        self.vr = 0.0
        self.v = 0.0           # toc do tien (m/s)
        self.omega = 0.0       # toc do quay (rad/s)
        self.battery = battery
        self.bumped = False
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
        if world.min_obstacle_clearance(nx, ny) < s.radius:
            self.bumped = True
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

        # Roi khoi ban khi tam xe vuot qua mep
        if not world.on_table(self.x, self.y):
            self.fallen = True

        # Pin
        effort = 0.5 * (abs(self.vl) + abs(self.vr)) / s.v_max
        self.battery -= (s.batt_idle + s.batt_drive * effort) * dt
        if self.battery < 0.0:
            self.battery = 0.0
        return self.fallen

    # ------------------------------------------------------------------- tram sac
    def try_charge(self, world, dt):
        """Sac neu dang dung dung vi tri va huong cua tram sac."""
        self.charging = False
        dock = world.dock
        if dock is None:
            return 0.0
        d = math.hypot(self.x - dock.x, self.y - dock.y)
        align = abs(wrap_angle(self.theta - world.dock_heading))
        if d < 0.16 and align < 0.9 and abs(self.v) < 0.12:
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

    def as_dict(self):
        return {"x": self.x, "y": self.y, "th": self.theta,
                "batt": self.battery, "charging": self.charging,
                "bump": self.bumped, "v": self.v, "w": self.omega}
