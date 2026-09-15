"""Moi truong huan luyen kieu gym (reset/step) cho xe 2 banh vi sai.

Policy CHI nhin thay du lieu cam bien - dung nhung thu phan cung that co:
LiDAR Camsense (rut thanh 12 quat + ket qua bo do hoc sac), 2 mat do vuc,
1 mat thu hong ngoai 2 kenh, muc pin, va uoc luong odometry cua chinh no.
Phan thuong duoc phep dung thong tin "toan tri" vi no chi ton tai luc huan luyen.
"""
import math
import random

import numpy as np

from .dock_detector import MAX_CAND, detect_lidar
from .geometry import clamp, wrap_angle
from .lidar import RMAX, SECTORS, Lidar
from .robot import Robot, RobotSpec
from .sensors import SensorSuite
from .world import IR_CALL, IR_DOCK, Beacon, make_world

SEC_CLIP = 3.0          # tam nhin dua vao mang no-ron (m) - xa hon coi la "trong"
MEM_CLIP = 3.0

OBS_DIM = SECTORS + 2 + 6 * MAX_CAND + 6 + 6 + 3 + 5
ACT_DIM = 2

OBS_NAMES = (
    ["lidar_sector_%02d" % i for i in range(SECTORS)] +
    ["cliff_front", "cliff_rear"] +
    sum([["cand%d_seen" % i, "cand%d_sin" % i, "cand%d_cos" % i,
          "cand%d_dist" % i, "cand%d_yawsin" % i, "cand%d_yawcos" % i]
         for i in range(MAX_CAND)], []) +
    ["ir_call", "ir_call_seen", "ir_dock", "ir_dock_seen", "d_ir_call", "d_ir_dock"] +
    ["mem_known", "mem_sin", "mem_cos", "mem_dist",
     "mem_headsin", "mem_headcos"] +
    ["battery", "battery_low", "return_margin"] +
    ["vel", "yaw_rate", "prev_u_left", "prev_u_right", "bump"]
)
assert len(OBS_NAMES) == OBS_DIM


class EnvConfig:
    dt = 0.05                 # 20 Hz vong dieu khien
    max_steps = 1600          # 80 giay - du de phai sac lai it nhat mot lan
    stage = 3
    battery_low = 0.40        # nguong coi la "sap het pin"
    battery_full = 0.97
    call_radius = 0.25
    call_timeout = (200, 500)
    ir_handshake = 30         # so buoc con nho tin hieu IR de duoc phep sac
    dock_approach = 0.40      # diem doi truoc CUA hoc sac (m)
    record = False
    record_every = 2
    scan_every = 4

    # He so thuong/phat
    w_fall = -40.0
    w_flat = -60.0
    w_bump = -1.5
    w_cliff = -0.8
    w_progress = 14.0
    w_arrive = 40.0
    w_dock = 15.0
    w_charge = 150.0
    w_full = 25.0
    w_align = 0.35
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
        self.lidar = Lidar()
        self.rng = random.Random(0)
        self.nprng = np.random.default_rng(0)
        self.obs_dim = OBS_DIM
        self.act_dim = ACT_DIM
        self.frames = []

    # ------------------------------------------------------------------- reset
    def reset(self, seed=None):
        if seed is not None:
            self.rng = random.Random(seed)
            self.nprng = np.random.default_rng(seed)
        rng = self.rng
        cfg = self.cfg
        self.world = make_world(rng, cfg.stage)

        x, y = self.world.free_spot(rng, self.spec.radius)
        th = rng.uniform(-math.pi, math.pi)
        batt = rng.uniform(0.30, 1.0) if cfg.stage >= 2 else 1.0
        self.robot.reset(x, y, th, batt, rng)
        self.sensors.reset()
        self.lidar.reset(self.nprng)
        self.lidar._scan(self.robot, self.world)

        self.steps = 0
        self.prev_u = [0.0, 0.0]
        self.prev_ir = [0.0, 0.0]
        self.visited = set()
        self.call = None
        self.call_expire = 0
        self.call_timer = self._draw_call_delay()
        self.cands = []
        self.ir_hand = -999            # buoc cuoi cung con thay IR tram sac
        self.mem = None                # (x, y) tram sac trong he odometry
        self.mem_age = 0
        self.arrivals = 0
        self.charged = 0.0
        self.full_charges = 0
        self.bumps = 0
        self.distance = 0.0
        self.batt_used = 0.0
        self.e_per_m = 0.045           # uoc luong ban dau: pin hao moi met
        self._docked_once = False
        self.rew_parts = {k: 0.0 for k in
                          ("fall", "flat", "bump", "cliff", "progress", "arrive",
                           "charge", "full", "align", "speed", "novel", "spin",
                           "cost")}
        self.frames = []
        self._sense()
        return self._obs()

    def _draw_call_delay(self):
        # Den goi chi xuat hien tu stage 3. Stage 2 danh rieng cho viec song
        # chung voi may cai hoc va tu di sac - dua ca hai thu vao cung mot
        # buoc thi xe hoc duoc ca hai deu do.
        if self.cfg.stage < 3:
            return 10 ** 9
        return self.rng.randint(40, 400)

    def _spawn_call(self):
        for _ in range(30):
            x, y = self.world.free_spot(self.rng, self.spec.radius + 0.10)
            if math.hypot(x - self.robot.x, y - self.robot.y) > 0.7:
                break
        self.call = Beacon(x, y, IR_CALL, active=True)
        self.world.beacons.append(self.call)
        self.call_expire = self.rng.randint(*self.cfg.call_timeout)

    def _drop_call(self):
        if self.call is not None:
            try:
                self.world.beacons.remove(self.call)
            except ValueError:
                pass
            self.call = None
        self.call_expire = 0
        self.call_timer = self.rng.randint(80, 400)

    # -------------------------------------------------------------------- sense
    def _sense(self):
        r = self.robot
        self.sensors.read_all(r, self.world, self.rng)
        if self.lidar.scans_new:
            self.cands = detect_lidar(self.lidar, r.theta)
        if self.sensors.ir_seen[IR_DOCK] > 0.5:
            self.ir_hand = self.steps
            self._update_memory()
        if r.charging:
            self.mem = (r.ox, r.oy, r.oth)
            self.mem_age = 0

    def _update_memory(self):
        """Hong ngoai xac nhan: ghi lai vi tri tram theo he odometry cua xe.

        Mat thu nam o dau xe nen tin hieu IR co nghia la tram dang o phia truoc.
        Neu LiDAR cung thay mot ung vien o phia truoc thi lay khoang cach cua no,
        khong thi uoc luong tam thoi bang cuong do tin hieu.
        """
        r = self.robot
        best = None
        for c in self.cands:
            if abs(c.bearing) < 0.45 and (best is None or c.dist < best.dist):
                best = c
        if best is not None:
            a = r.oth + best.bearing
            self.mem = (r.ox + best.dist * math.cos(a),
                        r.oy + best.dist * math.sin(a),
                        wrap_angle(r.oth + best.yaw))
            self.mem_age = 0

    def _obs(self):
        s = self.sensors
        r = self.robot
        cfg = self.cfg
        om_max = 2.0 * self.spec.v_max / self.spec.wheel_base

        # .tolist() nhanh hon list(...) nhieu lan: khong sinh 16 doi tuong
        # numpy scalar roi moi chuyen ve float.
        sec = self.lidar.sector_ranges(r.theta)
        obs = np.minimum(sec, SEC_CLIP, out=sec).__imul__(1.0 / SEC_CLIP).tolist()
        obs.append(s.cliff_front)
        obs.append(s.cliff_rear)

        for i in range(MAX_CAND):
            if i < len(self.cands):
                c = self.cands[i]
                obs += [1.0, math.sin(c.bearing), math.cos(c.bearing),
                        min(c.dist, SEC_CLIP) / SEC_CLIP,
                        math.sin(c.yaw), math.cos(c.yaw)]
            else:
                obs += [0.0, 0.0, 0.0, 1.0, 0.0, 1.0]

        d_call = clamp((s.ir[IR_CALL] - self.prev_ir[IR_CALL]) * 8.0, -1.0, 1.0)
        d_dock = clamp((s.ir[IR_DOCK] - self.prev_ir[IR_DOCK]) * 8.0, -1.0, 1.0)
        obs += [s.ir[IR_CALL], s.ir_seen[IR_CALL],
                s.ir[IR_DOCK], s.ir_seen[IR_DOCK], d_call, d_dock]
        self.prev_ir = list(s.ir)

        md, mb, mh = self._memory_polar()
        if self.mem is None:
            obs += [0.0, 0.0, 0.0, 1.0, 0.0, 1.0]
        else:
            obs += [1.0, math.sin(mb), math.cos(mb), min(md, MEM_CLIP) / MEM_CLIP,
                    math.sin(mh), math.cos(mh)]

        obs += [r.battery,
                1.0 if r.battery < cfg.battery_low else 0.0,
                self._return_margin(md)]
        obs += [clamp(r.v / self.spec.v_max, -1.0, 1.0),
                clamp(r.omega / om_max, -1.0, 1.0),
                self.prev_u[0], self.prev_u[1],
                1.0 if r.bumped else 0.0]
        return obs

    def _memory_polar(self):
        """Khoang cach, goc, va HUONG TRUC cua tram sac theo tri nho.

        Phai nho ca huong truc: hoc chi chui vao duoc tu mot phia, biet no nam
        dau ma khong biet no quay ve dau thi ve toi noi van phai do lai tu dau.
        """
        if self.mem is None:
            return MEM_CLIP, 0.0, 0.0
        r = self.robot
        dx = self.mem[0] - r.ox
        dy = self.mem[1] - r.oy
        return (math.hypot(dx, dy), wrap_angle(math.atan2(dy, dx) - r.oth),
                wrap_angle(self.mem[2] - r.oth))

    def _return_margin(self, dist):
        """Pin con du de ve tram khong? Day la phan "kinh nghiem" cua xe.

        e_per_m la muc hao pin moi met do CHINH XE do duoc tu dau tap - chay
        cang nang, ma sat cang nhieu thi con so nay cang lon.
        """
        if self.mem is None:
            need = 0.35        # chua biet tram o dau -> phai chua du de di tim
        else:
            # 2.0 chu khong phai 1.0: duong ve khong thang, con phai vong ra
            # truoc cua hoc. 0.12 la phan danh cho viec do dam va canh truc.
            need = self.e_per_m * dist * 2.0 + 0.12
        return clamp(self.robot.battery - need, -1.0, 1.0)

    # --------------------------------------------------------------------- goal
    def dock_points(self):
        """(diem doi truoc cua, diem dung sac)."""
        d = self.world.dock
        ax, ay = d.approach(self.cfg.dock_approach)
        px, py = d.pocket
        return ax, ay, px, py

    def _active_goal(self):
        """Muc tieu dung cho phan thuong. Pin yeu thi ve sac truoc da."""
        r = self.robot
        d = self.world.dock
        if d is not None and (r.battery < self.cfg.battery_low or r.charging):
            ax, ay, px, py = self.dock_points()
            if math.hypot(r.x - ax, r.y - ay) > 0.20:
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
        b0 = r.battery
        goal_before = self._active_goal()
        d_before = None
        if goal_before is not None:
            d_before = math.hypot(r.x - goal_before[0], r.y - goal_before[1])

        fallen = r.step(ul, ur, cfg.dt, self.world, rng)
        ir_ok = (self.steps - self.ir_hand) <= cfg.ir_handshake
        gained = r.try_charge(self.world, cfg.dt, ir_ok)

        moved = math.hypot(r.x - px, r.y - py)
        self.distance += moved
        if gained <= 0.0:
            self.batt_used += max(0.0, b0 - r.battery)
        if self.distance > 0.5:
            self.e_per_m = 0.9 * self.e_per_m + 0.1 * (self.batt_used / self.distance)

        self.call_timer -= 1
        if self.call is None and self.call_timer <= 0 and cfg.stage >= 3:
            self._spawn_call()
        elif self.call is not None:
            self.call_expire -= 1
            if self.call_expire <= 0:
                self._drop_call()

        self.lidar.step(r, self.world, cfg.dt)
        self.mem_age += 1
        self._sense()

        # ------------------------------------------------------------ phan thuong
        rew = 0.0
        done = False
        info = {}
        P = self.rew_parts

        if fallen:
            rew += cfg.w_fall
            P["fall"] += cfg.w_fall
            done = True
            info["fell"] = True
        if r.battery <= 0.0:
            rew += cfg.w_flat
            P["flat"] += cfg.w_flat
            done = True
            info["flat"] = True
        if r.bumped and not r.bump_bay:
            rew += cfg.w_bump
            P["bump"] += cfg.w_bump
            self.bumps += 1
        elif r.bump_bay:
            # Xat vach hoc khi chui vao la chuyen binh thuong - khe chi ho
            # 5 mm moi ben. Phat o day thi xe se hoc cach khong bao gio vao sac.
            self.bumps += 1

        cf, cr = self.sensors.cliff_front, self.sensors.cliff_rear
        if cf > 0.5 and r.v > 0.02:
            rew += cfg.w_cliff
            P["cliff"] += cfg.w_cliff
        if cr > 0.5 and r.v < -0.02:
            rew += cfg.w_cliff
            P["cliff"] += cfg.w_cliff

        goal_after = self._active_goal()
        if goal_before is not None and goal_after is not None and \
                goal_before[2] == goal_after[2]:
            d_after = math.hypot(r.x - goal_after[0], r.y - goal_after[1])
            dp = cfg.w_progress * (d_before - d_after)
            rew += dp
            P["progress"] += dp

        if self.call is not None and self.call.active:
            dc = math.hypot(r.x - self.call.x, r.y - self.call.y)
            if dc < cfg.call_radius:
                rew += cfg.w_arrive
                P["arrive"] += cfg.w_arrive
                self.arrivals += 1
                info["arrived"] = True
                self._drop_call()

        dock = self.world.dock
        if dock is not None and r.battery < cfg.battery_low:
            _, _, pkx, pky = self.dock_points()
            dd = math.hypot(r.x - pkx, r.y - pky)
            if dd < 0.7:
                err = wrap_angle(r.theta - dock.heading)
                bonus = cfg.w_align * math.cos(err) * (1.0 - dd / 0.7)
                if dd < 0.20 and abs(err) < 0.5:
                    bonus += cfg.w_align * (1.0 - min(1.0, abs(r.v) / 0.20))
                rew += bonus
                P["align"] += bonus

        if gained > 0.0:
            g = cfg.w_charge * gained
            rew += g
            P["charge"] += g
            self.charged += gained
            if not self._docked_once:
                rew += cfg.w_dock
                P["charge"] += cfg.w_dock
                self._docked_once = True
            if b0 < cfg.battery_full <= r.battery:
                rew += cfg.w_full
                P["full"] += cfg.w_full
                self.full_charges += 1
                self.visited.clear()      # sac day xong -> vong tuan tra moi
                info["full_charge"] = True

        if goal_after is None and not r.charging:
            sp = cfg.w_speed * max(0.0, r.v)
            rew += sp
            P["speed"] += sp
            cell = (int(r.x / 0.30), int(r.y / 0.30))
            if cell not in self.visited:
                self.visited.add(cell)
                rew += cfg.w_novel
                P["novel"] += cfg.w_novel
            om_max = 2.0 * self.spec.v_max / self.spec.wheel_base
            sp = cfg.w_spin * abs(r.omega) / om_max
            rew -= sp
            P["spin"] -= sp

        cost = cfg.w_energy * 0.5 * (abs(ul) + abs(ur)) + cfg.w_smooth * 0.5 * (
            abs(ul - self.prev_u[0]) + abs(ur - self.prev_u[1]))
        rew -= cost
        P["cost"] -= cost

        self.prev_u = [ul, ur]
        self.steps += 1
        if self.steps >= cfg.max_steps:
            done = True
            info["timeout"] = True

        if cfg.record and (self.steps % cfg.record_every == 0 or done):
            self.frames.append(self._frame())

        obs = self._obs()
        info["arrivals"] = self.arrivals
        info["charged"] = self.charged
        info["distance"] = self.distance
        return obs, rew, done, info

    # ------------------------------------------------------------------ ghi hinh
    def _frame(self):
        r = self.robot
        f = {"x": round(r.x, 4), "y": round(r.y, 4), "th": round(r.theta, 4),
             "batt": round(r.battery, 4), "charging": r.charging, "bump": r.bumped,
             "cliff": [self.sensors.cliff_front, self.sensors.cliff_rear],
             "ir": [round(v, 3) for v in self.sensors.ir],
             "u": [round(self.prev_u[0], 3), round(self.prev_u[1], 3)],
             "call": [round(self.call.x, 3), round(self.call.y, 3)] if self.call else None,
             "cand": [[round(c.bearing, 3), round(c.dist, 3), round(c.yaw, 3)]
                      for c in self.cands]}
        n = len(self.frames)
        if n % self.cfg.scan_every == 0:
            a, rr = self.lidar.base, self.lidar.r
            k = max(1, self.lidar.n // 90)
            off = self.lidar.scan_theta - r.theta
            f["scan"] = [round(float(v), 2) for v in rr[::k]]
            f["scan_off"] = round(off, 3)
        return f

    def episode_record(self):
        return {"world": self.world.as_dict(), "frames": self.frames,
                "dt": self.cfg.dt * self.cfg.record_every,
                "scan_every": self.cfg.scan_every,
                "lidar_n": self.lidar.n,
                "scan_hz": round(self.lidar.scan_hz, 2)}
