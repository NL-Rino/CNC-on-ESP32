"""Moi truong huan luyen kieu gym (reset/step) cho xe 2 banh vi sai.

Policy CHI nhin thay du lieu cam bien (giong het phan cung that).
Phan thuong duoc phep dung thong tin "toan tri" (vi tri that cua beacon) vi
no chi ton tai luc huan luyen.
"""
import math
import random

from .geometry import clamp, wrap_angle
from .robot import Robot, RobotSpec
from .sensors import SensorSuite, SONAR_MAX
from .world import IR_CALL, IR_DOCK, Beacon, make_world

OBS_DIM = 20
ACT_DIM = 2

OBS_NAMES = [
    "sonar_left90", "sonar_left45", "sonar_front", "sonar_right45", "sonar_right90",
    "cliff_front", "cliff_rear",
    "ir_call", "ir_call_seen", "ir_dock", "ir_dock_seen",
    "d_ir_call", "d_ir_dock",
    "battery", "battery_low",
    "vel", "yaw_rate",
    "prev_u_left", "prev_u_right", "bump",
]


class EnvConfig:
    dt = 0.05                 # 20 Hz vong dieu khien
    max_steps = 900           # 45 giay
    stage = 3
    battery_low = 0.40        # nguong bat den tram sac
    p_low_batt = 0.5          # ti le tap bat dau voi pin da yeu san
    call_radius = 0.25        # coi nhu "da toi noi" khi vao ban kinh nay
    call_timeout = (200, 500) # den goi tat sau bao nhieu buoc neu xe khong toi
    record = False

    # He so thuong/phat
    w_fall = -40.0
    w_flat = -25.0            # het pin
    w_bump = -1.2
    w_cliff = -0.8
    w_progress = 14.0
    w_arrive = 40.0
    w_dock = 15.0
    w_charge = 150.0
    w_align = 0.35        # thuong khi da gan tram sac va quay dung huong cam
    dock_approach = 0.30  # diem cho tiep can, cach tram sac bao xa (m)
    dock_pocket = 0.15    # cho xe dung khi sac, cach tram sac bao xa (m)
    w_speed = 0.6
    w_novel = 6.0
    w_spin = 0.25
    w_energy = 0.008
    w_smooth = 0.04

    def __init__(self, **kw):
        for k, v in kw.items():
            if not hasattr(EnvConfig, k):
                raise KeyError("unknown config key: %s" % k)
            setattr(self, k, v)


class CarEnv:
    def __init__(self, cfg: EnvConfig = None, spec: RobotSpec = None):
        self.cfg = cfg or EnvConfig()
        self.spec = spec or RobotSpec()
        self.robot = Robot(self.spec)
        self.sensors = SensorSuite(self.spec)
        self.rng = random.Random(0)
        self.obs_dim = OBS_DIM
        self.act_dim = ACT_DIM
        self.frames = []

    # ------------------------------------------------------------------- reset
    def reset(self, seed=None):
        if seed is not None:
            self.rng = random.Random(seed)
        rng = self.rng
        cfg = self.cfg
        self.world = make_world(rng, cfg.stage)

        x, y = self.world.free_spot(rng, self.spec.radius)
        th = rng.uniform(-math.pi, math.pi)
        if cfg.stage >= 3:
            # Mot nua so tap bat dau voi pin da yeu: neu khong, 45 giay khong
            # du de pin can va xe chang bao gio phai hoc di sac.
            if rng.random() < cfg.p_low_batt:
                batt = rng.uniform(0.18, 0.35)
            else:
                batt = rng.uniform(0.45, 0.95)
        else:
            batt = 1.0
        self.robot.reset(x, y, th, batt)
        self.sensors.reset()

        self.steps = 0
        self.prev_u = [0.0, 0.0]
        self.prev_ir = [0.0, 0.0]
        self.visited = set()
        self.call = None
        self.call_expire = 0
        self.call_timer = self._draw_call_delay()
        self.goal_dist = None
        self.arrivals = 0
        self.charged = 0.0
        self.falls = 0
        self.bumps = 0
        self._docked_once = False
        self.distance = 0.0
        self.rew_parts = {"fall": 0.0, "flat": 0.0, "bump": 0.0, "cliff": 0.0,
                          "progress": 0.0, "arrive": 0.0, "charge": 0.0,
                          "speed": 0.0, "novel": 0.0, "spin": 0.0, "cost": 0.0,
                          "align": 0.0}
        self.frames = []
        if self.world.dock is not None:
            self.world.dock.active = (self.robot.battery < cfg.battery_low)
        self._call_min_dist = 0.6
        self._sense()
        return self._obs()

    def _draw_call_delay(self):
        if self.cfg.stage < 2:
            return 10 ** 9
        return self.rng.randint(20, 240)

    def _spawn_call(self):
        # den goi phai o du xa de xe thuc su phai di tim
        for _ in range(30):
            x, y = self.world.free_spot(self.rng, self.spec.radius + 0.10)
            if math.hypot(x - self.robot.x, y - self.robot.y) > self._call_min_dist:
                break
        self.call = Beacon(x, y, IR_CALL, active=True)
        self.world.beacons.append(self.call)
        self.call_expire = self.rng.randint(*self.cfg.call_timeout)
        self.goal_dist = None

    def _drop_call(self):
        if self.call is not None:
            try:
                self.world.beacons.remove(self.call)
            except ValueError:
                pass
            self.call = None
        self.goal_dist = None
        self.call_timer = self.rng.randint(60, 300)

    # -------------------------------------------------------------------- sense
    def _sense(self):
        self.sensors.read_all(self.robot, self.world, self.rng)

    def _obs(self):
        s = self.sensors
        r = self.robot
        cfg = self.cfg
        om_max = 2.0 * self.spec.v_max / self.spec.wheel_base
        d_call = clamp((s.ir[IR_CALL] - self.prev_ir[IR_CALL]) * 8.0, -1.0, 1.0)
        d_dock = clamp((s.ir[IR_DOCK] - self.prev_ir[IR_DOCK]) * 8.0, -1.0, 1.0)
        obs = [
            s.sonar[0] / SONAR_MAX, s.sonar[1] / SONAR_MAX, s.sonar[2] / SONAR_MAX,
            s.sonar[3] / SONAR_MAX, s.sonar[4] / SONAR_MAX,
            s.cliff_front, s.cliff_rear,
            s.ir[IR_CALL], s.ir_seen[IR_CALL],
            s.ir[IR_DOCK], s.ir_seen[IR_DOCK],
            d_call, d_dock,
            r.battery, 1.0 if r.battery < cfg.battery_low else 0.0,
            clamp(r.v / self.spec.v_max, -1.0, 1.0),
            clamp(r.omega / om_max, -1.0, 1.0),
            self.prev_u[0], self.prev_u[1],
            1.0 if r.bumped else 0.0,
        ]
        self.prev_ir = list(s.ir)
        return obs

    # --------------------------------------------------------------------- goal
    def dock_points(self):
        """Hai diem tren truc tram sac: diem tiep can, va cho dung khi sac.

        Dich KHONG duoc dat dung vao toa do tram sac: tram nam cach mep ban co
        10 cm, keo xe toi tan do la keo no ra mep - cam bien vuc keu, phan xa
        tranh vuc day xe ra, va xe khong bao giờ cam duoc sac.
        """
        d = self.world.dock
        h = self.world.dock_heading
        c, sn = math.cos(h), math.sin(h)
        return (d.x - self.cfg.dock_approach * c, d.y - self.cfg.dock_approach * sn,
                d.x - self.cfg.dock_pocket * c, d.y - self.cfg.dock_pocket * sn)

    def _active_goal(self):
        """Muc tieu hien tai (chi dung cho phan thuong).

        Song sot truoc: den tram sac chi bat khi pin yeu, va luc do no duoc
        uu tien hon ca den goi - dung cua het pin giua duong vi ham di choi.
        """
        d = self.world.dock
        if d is not None and d.active:
            # Cam sac la bai hai buoc: truoc het ra DIEM TIEP CAN nam thang
            # truoc mat tram sac, roi moi dam thang vao. Neu chi thuong theo
            # khoang cach toi tram, xe se lao vao ngang hong va khong cam duoc.
            ax, ay, px, py = self.dock_points()
            if math.hypot(self.robot.x - ax, self.robot.y - ay) > 0.18:
                return ax, ay, "dock_app"
            return px, py, "dock"
        if self.call is not None and self.call.active:
            return self.call.x, self.call.y, "call"
        return None

    # --------------------------------------------------------------------- step
    def step(self, action):
        cfg = self.cfg
        rng = self.rng
        r = self.robot
        ul = clamp(float(action[0]), -1.0, 1.0)
        ur = clamp(float(action[1]), -1.0, 1.0)

        px, py = r.x, r.y
        goal_before = self._active_goal()
        d_before = None
        if goal_before is not None:
            d_before = math.hypot(r.x - goal_before[0], r.y - goal_before[1])

        fallen = r.step(ul, ur, cfg.dt, self.world, rng)
        gained = r.try_charge(self.world, cfg.dt)
        self.distance += math.hypot(r.x - px, r.y - py)

        # --- su kien: den goi xuat hien / tat, den tram sac bat khi pin yeu
        self.call_timer -= 1
        if self.call is None and self.call_timer <= 0 and cfg.stage >= 2:
            self._spawn_call()
        elif self.call is not None:
            self.call_expire -= 1
            if self.call_expire <= 0:      # nguoi goi bo cuoc
                self._drop_call()
        if self.world.dock is not None:
            # den tram sac chi bat khi pin yeu (hoac dang cam sac)
            self.world.dock.active = (r.battery < cfg.battery_low) or r.charging

        self._sense()

        # ------------------------------------------------------------ phan thuong
        rew = 0.0
        done = False
        info = {}

        if fallen:
            rew += cfg.w_fall
            self.rew_parts["fall"] += cfg.w_fall
            done = True
            self.falls += 1
            info["fell"] = True

        if r.battery <= 0.0:
            rew += cfg.w_flat
            self.rew_parts["flat"] += cfg.w_flat
            done = True
            info["flat"] = True

        if r.bumped:
            rew += cfg.w_bump
            self.rew_parts["bump"] += cfg.w_bump
            self.bumps += 1

        # phat khi cam bien vuc keu ma van tien ve phia do
        cf, cr = self.sensors.cliff_front, self.sensors.cliff_rear
        if cf > 0.5 and r.v > 0.02:
            rew += cfg.w_cliff
            self.rew_parts["cliff"] += cfg.w_cliff
        if cr > 0.5 and r.v < -0.02:
            rew += cfg.w_cliff
            self.rew_parts["cliff"] += cfg.w_cliff

        # tien ve muc tieu
        goal_after = self._active_goal()
        if goal_before is not None and goal_after is not None and \
                goal_before[2] == goal_after[2]:
            d_after = math.hypot(r.x - goal_after[0], r.y - goal_after[1])
            dp = cfg.w_progress * (d_before - d_after)
            rew += dp
            self.rew_parts["progress"] += dp

        # toi noi duoc goi
        if self.call is not None and self.call.active:
            dc = math.hypot(r.x - self.call.x, r.y - self.call.y)
            if dc < cfg.call_radius:
                rew += cfg.w_arrive
                self.rew_parts["arrive"] += cfg.w_arrive
                self.arrivals += 1
                info["arrived"] = True
                self._drop_call()

        # da toi gan tram sac: thuong them cho viec quay dung huong cam
        dock = self.world.dock
        if dock is not None and dock.active:
            dd = math.hypot(r.x - dock.x, r.y - dock.y)
            if dd < 0.6:
                err = wrap_angle(r.theta - self.world.dock_heading)
                bonus = cfg.w_align * math.cos(err) * (1.0 - dd / 0.6)
                # vao dung o cam roi thi con phai DUNG LAI moi nap duoc dien
                if dd < 0.22 and abs(err) < 0.9:
                    bonus += cfg.w_align * (1.0 - min(1.0, abs(r.v) / 0.20))
                rew += bonus
                self.rew_parts["align"] += bonus

        # sac pin
        if gained > 0.0:
            rew += cfg.w_charge * gained
            self.rew_parts["charge"] += cfg.w_charge * gained
            self.charged += gained
            if not self._docked_once:
                rew += cfg.w_dock
                self.rew_parts["charge"] += cfg.w_dock
                self._docked_once = True

        # khong co muc tieu -> di long nhong: thuong toc do + kham pha
        if goal_after is None and not r.charging:
            rew += cfg.w_speed * max(0.0, r.v)
            self.rew_parts["speed"] += cfg.w_speed * max(0.0, r.v)
            cell = (int(r.x / 0.30), int(r.y / 0.30))
            if cell not in self.visited:
                self.visited.add(cell)
                rew += cfg.w_novel
                self.rew_parts["novel"] += cfg.w_novel
            om_max = 2.0 * self.spec.v_max / self.spec.wheel_base
            rew -= cfg.w_spin * abs(r.omega) / om_max
            self.rew_parts["spin"] -= cfg.w_spin * abs(r.omega) / om_max

        effort = 0.5 * (abs(ul) + abs(ur))
        cost = cfg.w_energy * effort + cfg.w_smooth * 0.5 * (
            abs(ul - self.prev_u[0]) + abs(ur - self.prev_u[1]))
        rew -= cost
        self.rew_parts["cost"] -= cost

        self.prev_u = [ul, ur]
        self.steps += 1
        if self.steps >= cfg.max_steps:
            done = True
            info["timeout"] = True

        if cfg.record:
            self.frames.append(self._frame())

        obs = self._obs()
        info["arrivals"] = self.arrivals
        info["charged"] = self.charged
        info["distance"] = self.distance
        info["bumps"] = self.bumps
        return obs, rew, done, info

    # ------------------------------------------------------------------ ghi hinh
    def _frame(self):
        f = self.robot.as_dict()
        f["sonar"] = [round(v, 3) for v in self.sensors.sonar]
        f["cliff"] = [self.sensors.cliff_front, self.sensors.cliff_rear]
        f["ir"] = [round(v, 3) for v in self.sensors.ir]
        f["u"] = [round(self.prev_u[0], 3), round(self.prev_u[1], 3)]
        f["call"] = [self.call.x, self.call.y] if self.call else None
        f["dock_on"] = bool(self.world.dock.active) if self.world.dock else False
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}

    def episode_record(self):
        return {"world": self.world.as_dict(), "frames": self.frames,
                "dt": self.cfg.dt}
