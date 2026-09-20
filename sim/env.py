"""Moi truong huan luyen kieu gym (reset/step) cho xe 2 banh vi sai.

Policy CHI nhin thay du lieu cam bien - dung nhung thu phan cung that co:
LiDAR Camsense (rut thanh 12 quat + ket qua bo do hoc sac), 2 mat do vuc,
1 mat thu hong ngoai 2 kenh, muc pin, va uoc luong odometry cua chinh no.
Phan thuong duoc phep dung thong tin "toan tri" vi no chi ton tai luc huan luyen.
"""
import math
import random

import numpy as np

from . import layout as layout_mod
from .geometry import clamp, wrap_angle
from .lidar import Lidar
from .perception import (MEM_CLIP, OBS_DIM, OBS_NAMES,  # noqa: F401
                         SEC_CLIP, Perception)
from .robot import Robot, RobotSpec
from .sensors import SensorSuite
from .world import IR_CALL, IR_DOCK, Beacon, make_house, make_world

ACT_DIM = 2



class EnvConfig:
    dt = 0.05                 # 20 Hz vong dieu khien
    max_steps = 5000          # 250 giay. Do duoc: mot lan xa het pin mat
                              # ~1000 buoc, nen muon du 3 lan sac hop le thi
                              # tap KHONG the ngan hon ~4000 buoc. De 1600
                              # nhu truoc thi nhiem vu moi la bat kha thi -
                              # xe chi kip cam sac dung mot lan.
    stage = 3
    battery_low = 0.40        # nguong coi la "sap het pin"
    battery_full = 0.97
    call_radius = 0.35
    call_timeout = (900, 2000)   # nha to thi nguoi goi phai doi lau hon
    ir_handshake = 30         # so buoc con nho tin hieu IR de duoc phep sac
    dock_approach = 0.40      # diem doi truoc CUA hoc sac (m)
    world = "house"           # "house" = can nha to co ban ghe; "table" = mat ban
    spawn_at_dock = True      # xe luon bat dau TU TRAM SAC, khong tha lung tung

    # --- Dinh nghia HOAN THANH mot tap ---
    need_calls = 5            # phai toi duoc 5 cai den goi
    need_charges = 3          # va sac day du 3 lan
    # --- Mot lan sac duoc TINH khi ca ba dieu sau dung ---
    charge_below = 0.40       # pin luc cam vao phai duoi muc nay
    charge_far = 2.5          # ... va truoc do da di xa tram it nhat ngan nay
    charge_path = 1.8         # ... va tu luc cat vao trong ban kinh do thi di
                              # THANG ve tram: quang duong di duoc khong duoc
                              # qua 1.8 lan khoang cach luc cat vao. Day la
                              # cach do "di ve mot mach" - chan viec quanh
                              # quan gan tram roi ghe vao nap cho du so lan.
    charge_full = 0.999       # ... VA sac len toi day. Bo di giua chung = khong tinh.
    cover_cell = 0.35         # o luoi do dien tich LiDAR da quet qua (m)
    layout = None             # mat bang tu ve (dict hoac duong dan .json);
                              # None = sinh canh ngau nhien nhu khi huan luyen
    record = False
    record_every = 2
    scan_every = 4
    scan_points = 90          # so diem LiDAR ghi vao khung hinh (0 = du ca vong)

    # He so thuong/phat
    # Roi khoi ban phai dat hon MOI thu kiem duoc trong mot tap cong lai.
    # Truoc day -40: di 2 m ve phia tram da duoc +28, nen lao ve tram roi roi
    # xuong dat van gan nhu hoa von - va xe hoc dung cai do (rot ban 65%,
    # trong do 14/20 lan la dang pin yeu).
    w_fall = -150.0
    # Phai BANG w_fall. Neu chet pin re hon roi ban thi xe se chon cai chet
    # re hon: no dung quay tai cho cho het pin (roi 0%, het pin 85%, moi tap
    # chi di qua 3 o luoi). Hai cai chet deu la chet, gia phai bang nhau.
    w_flat = -150.0
    w_bump = -1.5
    w_cliff = -3.0            # phat lien tuc khi cam bien vuc keu ma van tien
    w_progress = 14.0
    w_arrive = 40.0
    w_dock = 15.0
    w_charge = 150.0
    w_full = 25.0
    w_align = 0.35
    w_speed = 0.6
    w_cover = 1.2             # moi o luoi LiDAR vua nhin thay lan dau
    w_task = 400.0            # thuong khi HOAN THANH ca nhiem vu
    w_task_speed = 300.0      # ... cong them neu xong som
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
        # CHINH module nay cung chay tren laptop khi dieu khien robot that
        # (link/brain_server.py). Mot cho duy nhat dung vector quan sat.
        self.per = Perception(self.cfg.battery_low, self.cfg.ir_handshake,
                              self.spec.v_max, self.spec.wheel_base)
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
        if cfg.layout is None:
            self.world = (make_house(rng, cfg.stage) if cfg.world == "house"
                          else make_world(rng, cfg.stage))
        else:
            lay = cfg.layout
            if isinstance(lay, str):
                lay = layout_mod.load(lay)
            self.world = layout_mod.build_world(lay, rng)

        # Xe SONG O TRAM SAC: moi chuyen di deu bat dau tu trong hoc, dau
        # huong vao trong (no cam dau vao de sac), muon di thi phai lui ra -
        # dung nhu ngoai doi. Tha lung tung giua phong la canh khong bao gio
        # xay ra, ma lai lam xe khong bao gio biet tram cua no o dau.
        dock = self.world.dock
        if cfg.spawn_at_dock and dock is not None:
            x, y = dock.pocket
            th = dock.heading
            # Thuong la vua sac day. Doi khi bi nhac ra giua chung (mat dien,
            # nguoi cam len dat lai) nen con lung chung - giu cho xe van phai
            # tap ve sac chu khong chi tap di long nhong.
            batt = 1.0 if (cfg.stage < 2 or rng.random() < 0.55) \
                else rng.uniform(0.30, 0.85)
        else:
            x, y = self.world.free_spot(rng, self.spec.radius)
            th = rng.uniform(-math.pi, math.pi)
            batt = rng.uniform(0.50, 1.0) if cfg.stage == 2 else (
                rng.uniform(0.30, 1.0) if cfg.stage >= 3 else 1.0)
        self.robot.reset(x, y, th, batt, rng)
        self.sensors.reset()
        self.lidar.reset(self.nprng)
        self.lidar._scan(self.robot, self.world)

        self.per = Perception(cfg.battery_low, cfg.ir_handshake,
                              self.spec.v_max, self.spec.wheel_base)
        self.per.reset(batt)
        self.steps = 0
        self.visited = set()
        self._cover_init()
        self.was_far = False      # da ra khoi ban kinh charge_far chua
        self.far_anchor = 0.0     # khoang cach luc cat vao trong ban kinh do
        self.near_path = 0.0      # quang duong di duoc TU LUC cat vao
        self.sess_ok = False      # lan sac dang do co du tu cach duoc tinh khong
        self.was_charging = False
        self.charge_tries = 0
        self.plug_log = []        # nhat ky tung lan cam vao (de soi luat sac)
        self.task_done = False
        self.call = None
        self.call_expire = 0
        self.call_timer = self._draw_call_delay()
        self.arrivals = 0
        self.charged = 0.0
        self.full_charges = 0
        self.bumps = 0
        self.distance = 0.0
        self.batt_used = 0.0
        self._docked_once = False
        self.rew_parts = {k: 0.0 for k in
                          ("fall", "flat", "bump", "cliff", "progress", "arrive",
                           "charge", "full", "align", "speed", "novel", "spin",
                           "cost")}
        self.frames = []
        # Doc cam bien o DUNG cho nay: read_all rut so ngau nhien (nhieu cam
        # bien vuc va hong ngoai), dat sai cho la ca chuoi ngau nhien lech di
        # va tap chay ra khac han - tim ra loi nay mat mot vong doi chieu.
        self.sensors.read_all(self.robot, self.world, rng)
        return self._obs()

    # ------------------------------------------------------------- do dien tich
    def _cover_init(self):
        c = self.cfg.cover_cell
        self._cgw = int(self.world.width / c) + 2
        self._cgh = int(self.world.height / c) + 2
        self.cover = np.zeros(self._cgw * self._cgh, dtype=bool)
        self.cover_n = 0

    def _cover_update(self):
        """Danh dau nhung o luoi ma vong quet LiDAR vua NHIN THAY.

        Khac han voi "o xe da di qua": xe dung giua phong lon quet mot vong
        la biet ca can phong, con bo vao mot goc kin thi di bao nhieu cung
        khong them duoc gi. Thuong theo cai NHIN THAY moi la thuong dung cho
        viec di kham pha.
        """
        ld = self.lidar
        r = self.robot
        rr = ld.r
        a = ld.base + r.oth
        ca = np.cos(a)
        sa = np.sin(a)
        # Lay may diem doc theo tia chu khong chi lay diem cuoi: khoang khong
        # giua xe va vat can cung la da nhin thay.
        fr = np.array([0.35, 0.65, 0.92], dtype=np.float32)
        xs = r.x + np.outer(fr, rr * ca)
        ys = r.y + np.outer(fr, rr * sa)
        c = self.cfg.cover_cell
        ix = np.clip((xs / c).astype(np.int32) + 1, 0, self._cgw - 1)
        iy = np.clip((ys / c).astype(np.int32) + 1, 0, self._cgh - 1)
        self.cover[(iy * self._cgw + ix).ravel()] = True
        n = int(self.cover.sum())
        moi = n - self.cover_n
        self.cover_n = n
        return moi

    def _draw_call_delay(self):
        # Den goi chi xuat hien tu stage 3. Stage 2 danh rieng cho viec song
        # chung voi may cai hoc va tu di sac - dua ca hai thu vao cung mot
        # buoc thi xe hoc duoc ca hai deu do.
        if self.cfg.stage < 3:
            return 10 ** 9
        return self.rng.randint(40, 250)

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
    @property
    def cands(self):
        return self.per.cands

    @property
    def mem(self):
        return self.per.mem

    @property
    def e_per_m(self):
        return self.per.e_per_m

    def _obs(self):
        """Dong goi cam bien y het luc chay that roi day qua Perception."""
        r = self.robot
        s = self.sensors
        return self.per.update(
            ranges=self.lidar.r, scan_theta=self.lidar.scan_theta,
            scans_new=self.lidar.scans_new, odo=(r.ox, r.oy, r.oth),
            cliff=(s.cliff_front, s.cliff_rear), ir=s.ir,
            battery=r.battery, v=r.v, omega=r.omega,
            bumped=r.bumped, charging=r.charging, on_dock=r.docked(self.world))

    def _memory_polar(self):
        r = self.robot
        return self.per.memory_polar((r.ox, r.oy, r.oth))

    def _return_margin(self, dist):
        return self.per.return_margin(dist)

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

        self.world.step_movers(cfg.dt, rng)
        fallen = r.step(ul, ur, cfg.dt, self.world, rng)
        gained = r.try_charge(self.world, cfg.dt, self.per.ir_ok)

        moved = math.hypot(r.x - px, r.y - py)
        self.distance += moved
        if gained <= 0.0:
            self.batt_used += max(0.0, b0 - r.battery)

        self.call_timer -= 1
        if self.call is None and self.call_timer <= 0 and cfg.stage >= 3:
            self._spawn_call()
        elif self.call is not None:
            self.call_expire -= 1
            if self.call_expire <= 0:
                self._drop_call()

        self.lidar.step(r, self.world, cfg.dt)
        self.sensors.read_all(r, self.world, rng)

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
        # Xat vach khi dang chui vao hoc thi khong phat va khong dem: khe chi
        # ho 5 mm moi ben nen co xat la duong nhien. Phat o day thi xe se hoc
        # cach khong bao gio vao sac. Nhung "dang chui vao" phai tinh chat che
        # (xem World.in_bay_corridor), khong thi thanh ke ho.

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

        # --- theo doi "di xa roi ve mot mach" ---
        dock = self.world.dock
        if dock is not None:
            px, py = dock.pocket
            d_dock = math.hypot(r.x - px, r.y - py)
            if d_dock >= cfg.charge_far:
                # Con o ngoai vong: dat lai moc, quang duong chua tinh
                self.was_far = True
                self.far_anchor = d_dock
                self.near_path = 0.0
            else:
                self.near_path += moved
        if r.charging and not self.was_charging:
            # Chot tu cach NGAY LUC CAM VAO: pin phai duoi nguong, phai da di
            # xa, va tu luc cat vao trong vong thi phai di thang ve.
            self.sess_ok = (b0 < cfg.charge_below and self.was_far and
                            self.near_path <= cfg.charge_path * self.far_anchor)
            self.charge_tries += 1
            self.plug_log.append((b0, self.was_far, self.far_anchor,
                                  self.near_path, self.sess_ok))
        elif not r.charging and self.was_charging:
            self.sess_ok = False            # roi hoc giua chung: mat luot
        self.was_charging = r.charging

        if gained > 0.0:
            g = cfg.w_charge * gained
            rew += g
            P["charge"] += g
            self.charged += gained
            if not self._docked_once:
                rew += cfg.w_dock
                P["charge"] += cfg.w_dock
                self._docked_once = True

        if self.sess_ok and r.charging and r.battery >= cfg.charge_full:
            self.full_charges += 1
            rew += cfg.w_full
            P["full"] += cfg.w_full
            info["full_charge"] = True
            self.sess_ok = False
            self.was_far = False
            self.near_path = 0.0
            self._cover_init()            # sac day xong -> vong tuan tra moi

        if self.lidar.scans_new:
            moi = self._cover_update()
            if moi and goal_after is None and not r.charging:
                nv = cfg.w_cover * moi
                rew += nv
                P["novel"] += nv
                self.visited.add(moi)

        if goal_after is None and not r.charging:
            sp = cfg.w_speed * max(0.0, r.v)
            rew += sp
            P["speed"] += sp

        # Phat quay tai cho ap dung LUC NAO CUNG THE. Truoc day no tat di khi
        # dang co muc tieu, ma pin yeu thi luc nao cung co muc tieu (ve tram)
        # - thanh ra xe duoc quay vong vong mien phi dung luc no can di nhat.
        if not r.charging:
            om_max = 2.0 * self.spec.v_max / self.spec.wheel_base
            sp = cfg.w_spin * abs(r.omega) / om_max
            rew -= sp
            P["spin"] -= sp

        cost = cfg.w_energy * 0.5 * (abs(ul) + abs(ur)) + cfg.w_smooth * 0.5 * (
            abs(ul - self.per.prev_u[0]) + abs(ur - self.per.prev_u[1]))
        rew -= cost
        P["cost"] -= cost

        if (not self.task_done and self.arrivals >= cfg.need_calls
                and self.full_charges >= cfg.need_charges):
            self.task_done = True
            con_lai = 1.0 - self.steps / float(cfg.max_steps)
            bonus = cfg.w_task + cfg.w_task_speed * max(0.0, con_lai)
            rew += bonus
            P["task"] += bonus
            info["task_done"] = True
            done = True               # xong viec thi ve, khong can chay het gio

        self.per.note_action(ul, ur)
        self.steps += 1
        if self.steps >= cfg.max_steps:
            done = True
            info["timeout"] = True

        if cfg.record and (self.steps % cfg.record_every == 0 or done):
            self.frames.append(self._frame())

        obs = self._obs()
        info["arrivals"] = self.arrivals
        info["full_charges"] = self.full_charges
        info["charged"] = self.charged
        info["cover"] = self.cover_n
        info["distance"] = self.distance
        return obs, rew, done, info

    # ------------------------------------------------------------------ ghi hinh
    def _frame(self):
        r = self.robot
        f = {"x": round(r.x, 4), "y": round(r.y, 4), "th": round(r.theta, 4),
             "batt": round(r.battery, 4), "charging": r.charging, "bump": r.bumped,
             "cliff": [self.sensors.cliff_front, self.sensors.cliff_rear],
             "ir": [[round(v, 3) for v in ch] for ch in self.sensors.ir],
             "u": [round(self.per.prev_u[0], 3), round(self.per.prev_u[1], 3)],
             "call": [round(self.call.x, 3), round(self.call.y, 3)] if self.call else None,
             "cand": [[round(c.bearing, 3), round(c.dist, 3), round(c.yaw, 3)]
                      for c in self.cands]}
        if self.world.movers:
            # Nguoi phai ghi TUNG KHUNG, va ghi theo CHAN: chan dang nhac len
            # thi LiDAR khong thay, nen man hinh cung khong duoc ve.
            f["legs"] = [[round(l.x, 3), round(l.y, 3), round(l.r, 3)]
                         for m in self.world.movers for l in m.legs
                         if l.x > -900.0]
        n = len(self.frames)
        if n % self.cfg.scan_every == 0:
            a, rr = self.lidar.base, self.lidar.r
            k = 1 if not self.cfg.scan_points else \
                max(1, self.lidar.n // self.cfg.scan_points)
            off = self.lidar.scan_theta - r.oth
            f["scan"] = [round(float(v), 2) for v in rr[::k]]
            f["scan_off"] = round(off, 3)
        return f

    def episode_record(self):
        return {"world": self.world.as_dict(), "frames": self.frames,
                "dt": self.cfg.dt * self.cfg.record_every,
                "scan_every": self.cfg.scan_every,
                "lidar_n": self.lidar.n,
                "scan_hz": round(self.lidar.scan_hz, 2)}
