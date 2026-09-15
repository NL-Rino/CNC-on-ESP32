"""The gioi mo phong: mat ban co mep vuc, vat can, den hong ngoai, tram sac.

Tram sac la mot HOC hinh chu U de xe chui han vao trong:
  - kich thuoc ngoai 40 x 40 cm, long trong 31 x 31 cm, vach day 4.5 cm
  - den hong ngoai gan GIUA THANH TRONG (vach day), chieu thang ra cua
Xe TRON duong kinh 30 cm nen chui vao chi con du moi ben 5 mm.

Vi la chu U nen LiDAR doc duoc ca HUONG cua hoc chu khong chi vi tri: hai
mep cua tao thanh mot day cung, long hoc lom vao phia sau day cung do. Do la
thu ma hop dac 15 cm truoc day khong cho duoc, va cung la thu giup xe canh
duoc truc truoc khi chui vao.

Tren ban con vai cai hoc y het nhung KHONG phat hong ngoai (moi nhu), nen xe
buoc phai hoi hong ngoai moi biet cai nao la tram sac that.
"""
import math
import random

import numpy as np

from .geometry import ray_aabb, ray_circle

IR_CALL = 0     # nguoi dung "goi" xe toi
IR_DOCK = 1     # den bao cua tram sac

BAY_OUT = 0.40          # canh ngoai cua hoc (m)
BAY_IN = 0.31           # long trong (m) - xe 30 cm chui vua khit
BAY_WALL = 0.5 * (BAY_OUT - BAY_IN)     # be day vach = 4.5 cm
DOCK_IR_CONE = 0.70     # nua goc chum hong ngoai cua den (rad) ~ 40 do
                        # hai vach ben con bop chum nay lai con ~24 do o cua

# Doan LOE o mieng hoc. Rat quan trong, khong phai trang tri:
# hoc thang tap 31 cm voi xe 30 cm doi hoi xe vao dung +-5 mm ngang va +-1 do
# goc. LiDAR o cu ly cam cho truc chinh xac ~2 do, tuc la KHONG DU. Vat hai
# goc trong o mieng cho loe ra 37 cm roi thu dan ve 31 cm thi cua so bat
# rong +-3.5 cm, va hai vach tu day xe vao giua. Moi de sac that deu lam vay.
# Dat BAY_FLARE = 0.0 de quay lai hoc thang tap nhu ban ve goc.
BAY_FLARE = 0.08        # doan loe dai bao nhieu tinh tu mieng (m)
BAY_FLARE_STEPS = 3     # xap xi mat vat bang may bac (de giu raycast AABB)


class Obstacle:
    """Vat can tren ban. kind = 'circle' | 'box'."""

    __slots__ = ("kind", "x", "y", "r", "x0", "y0", "x1", "y1", "tag")

    def __init__(self, kind, tag="", **kw):
        self.kind = kind
        self.tag = tag
        if kind == "circle":
            self.x = kw["x"]
            self.y = kw["y"]
            self.r = kw["r"]
            self.x0 = self.x - self.r
            self.y0 = self.y - self.r
            self.x1 = self.x + self.r
            self.y1 = self.y + self.r
        else:
            self.x0, self.y0, self.x1, self.y1 = kw["x0"], kw["y0"], kw["x1"], kw["y1"]
            self.x = 0.5 * (self.x0 + self.x1)
            self.y = 0.5 * (self.y0 + self.y1)
            self.r = 0.5 * math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    def ray(self, ox, oy, dx, dy, max_t):
        if self.kind == "circle":
            return ray_circle(ox, oy, dx, dy, self.x, self.y, self.r, max_t)
        return ray_aabb(ox, oy, dx, dy, self.x0, self.y0, self.x1, self.y1, max_t)

    def dist_to_point(self, px, py):
        """Khoang cach tu tam xe toi be mat vat can (am neu dang chong lan)."""
        if self.kind == "circle":
            return math.hypot(px - self.x, py - self.y) - self.r
        dx = max(self.x0 - px, 0.0, px - self.x1)
        dy = max(self.y0 - py, 0.0, py - self.y1)
        if dx == 0.0 and dy == 0.0:
            return -min(px - self.x0, self.x1 - px, py - self.y0, self.y1 - py)
        return math.hypot(dx, dy)

    def corners(self):
        return ((self.x0, self.y0), (self.x1, self.y0),
                (self.x1, self.y1), (self.x0, self.y1))

    def as_dict(self):
        if self.kind == "circle":
            return {"kind": "circle", "x": self.x, "y": self.y, "r": self.r,
                    "tag": self.tag}
        return {"kind": "box", "x0": self.x0, "y0": self.y0, "x1": self.x1,
                "y1": self.y1, "tag": self.tag}


class Beacon:
    """Den hong ngoai. dir_ang=None nghia la phat deu moi huong."""

    __slots__ = ("x", "y", "channel", "active", "power", "dir_ang", "cone")

    def __init__(self, x, y, channel, active=True, power=1.0,
                 dir_ang=None, cone=math.pi):
        self.x = x
        self.y = y
        self.channel = channel
        self.active = active
        self.power = power
        self.dir_ang = dir_ang      # huong truc phat
        self.cone = cone            # nua goc phat

    def as_dict(self):
        return {"x": self.x, "y": self.y, "ch": self.channel,
                "active": bool(self.active), "power": self.power,
                "dir": self.dir_ang, "cone": self.cone}


class Bay:
    """Hoc chu U de xe chui vao: vach day + hai vach ben.

    He toa do rieng: u doc theo `heading` (huong XE phai quay khi chui vao),
    v la be ngang. Cua hoc o u = -0.20, thanh trong o u = +0.155.
    """

    def __init__(self, x, y, heading, tag="dock"):
        self.x = x                  # tam hoc (cung la cho xe dung khi sac)
        self.y = y
        self.heading = heading
        self.tag = tag
        hu = 0.5 * BAY_OUT          # 0.200
        hi = 0.5 * BAY_IN           # 0.155
        self.half_out = hu
        self.half_in = hi
        self.depth = hu + hi        # long hoc sau bao nhieu tinh tu cua
        self.walls = [self._box(hi, hu, -hu, hu, tag)]     # vach day
        u0 = -hu + BAY_FLARE
        for sgn in (1.0, -1.0):
            self.walls.append(self._box(u0, hu, *sorted((sgn * hi, sgn * hu)),
                                        tag=tag))
            for i in range(BAY_FLARE_STEPS):
                if BAY_FLARE <= 0.0:
                    break
                ua = -hu + BAY_FLARE * i / BAY_FLARE_STEPS
                ub = -hu + BAY_FLARE * (i + 1) / BAY_FLARE_STEPS
                vi = hi + (hu - hi) * (BAY_FLARE_STEPS - 1 - i) / BAY_FLARE_STEPS
                self.walls.append(self._box(ua, ub,
                                            *sorted((sgn * vi, sgn * hu)),
                                            tag=tag))
        self.mouth_half = hi + (hu - hi) * (BAY_FLARE_STEPS - 1) / BAY_FLARE_STEPS \
            if BAY_FLARE > 0.0 else hi

    def _box(self, u0, u1, v0, v1, tag=""):
        c, s = math.cos(self.heading), math.sin(self.heading)
        xs = []
        ys = []
        for u, v in ((u0, v0), (u0, v1), (u1, v0), (u1, v1)):
            xs.append(self.x + u * c - v * s)
            ys.append(self.y + u * s + v * c)
        return Obstacle("box", tag=tag, x0=min(xs), y0=min(ys),
                        x1=max(xs), y1=max(ys))

    def local_to_world(self, u, v=0.0):
        c, s = math.cos(self.heading), math.sin(self.heading)
        return (self.x + u * c - v * s, self.y + u * s + v * c)

    @property
    def pocket(self):
        """Cho xe dung khi da chui han vao - chinh la tam hoc."""
        return (self.x, self.y)

    @property
    def mouth(self):
        return self.local_to_world(-self.half_out)

    def approach(self, d=0.35):
        """Diem doi truoc cua hoc, cach cua d met."""
        return self.local_to_world(-(self.half_out + d))

    def to_local(self, x, y, theta):
        """(doc truc, ngang truc, lech goc) cua xe so voi hoc."""
        c, s = math.cos(self.heading), math.sin(self.heading)
        dx = x - self.x
        dy = y - self.y
        return (dx * c + dy * s, -dx * s + dy * c,
                (theta - self.heading + math.pi) % (2.0 * math.pi) - math.pi)

    def clearance(self, x, y):
        """Khoang cach tu tam xe toi vach gan nhat cua hoc nay."""
        best = 1e9
        for w in self.walls:
            d = w.dist_to_point(x, y)
            if d < best:
                best = d
        return best

    def as_dict(self):
        return {"x": self.x, "y": self.y, "heading": self.heading,
                "out": BAY_OUT, "inner": BAY_IN, "tag": self.tag,
                "pocket": list(self.pocket), "mouth": list(self.mouth)}


class Dock(Bay):
    """Hoc that: co them den hong ngoai giua thanh trong, chieu ra cua."""

    def __init__(self, x, y, heading):
        Bay.__init__(self, x, y, heading, tag="dock")
        bx, by = self.local_to_world(self.half_in - 0.005)
        self.beacon = Beacon(bx, by, IR_DOCK, active=True,
                             dir_ang=heading + math.pi, cone=DOCK_IR_CONE)

    @property
    def active(self):
        return self.beacon.active

    @active.setter
    def active(self, v):
        self.beacon.active = bool(v)

    def as_dict(self):
        d = Bay.as_dict(self)
        d["active"] = bool(self.beacon.active)
        return d


class World:
    """Mat ban hinh chu nhat [0,W] x [0,H]. Ra khoi bien = roi khoi ban."""

    def __init__(self, width=3.2, height=2.4):
        self.width = width
        self.height = height
        self.obstacles = []     # tat ca (dung cho LiDAR / duong ngam)
        self.solid = []         # vat can tinh va cham kieu hinh tron
        self.bays = []          # hoc chu U - va cham tinh kieu hinh vuong
        self.beacons = []
        self.dock = None
        self._arrays_dirty = True

    def add_obstacle(self, ob):
        self.obstacles.append(ob)
        self.solid.append(ob)
        self._arrays_dirty = True

    def add_bay(self, bay):
        self.bays.append(bay)
        self.obstacles.extend(bay.walls)
        self.solid.extend(bay.walls)
        self._arrays_dirty = True

    # ---------------------------------------------------------------- dung mang
    def bake(self):
        """Gom vat can thanh mang numpy de ban ca vong LiDAR trong mot luot."""
        cir = [o for o in self.obstacles if o.kind == "circle"]
        box = [o for o in self.obstacles if o.kind == "box"]
        f32 = np.float32
        self._cxy = np.array([[o.x for o in cir], [o.y for o in cir]], dtype=f32)
        self._cr2 = np.array([o.r * o.r for o in cir], dtype=f32)
        self._b0 = np.array([[o.x0 for o in box], [o.y0 for o in box]], dtype=f32)
        self._b1 = np.array([[o.x1 for o in box], [o.y1 for o in box]], dtype=f32)
        self._arrays_dirty = False

    def raycast_batch(self, ox, oy, angles, max_range):
        """Ban ca vong tia cung luc. angles: ndarray goc tuyet doi (rad).

        Mang duoc bo tri [so_vat_can, so_tia] chu khong phai nguoc lai: rut gon
        theo truc 0 nhanh hon ~12 lan vi du lieu nam lien nhau trong bo nho.
        """
        if self._arrays_dirty:
            self.bake()
        dx = np.cos(angles, dtype=np.float32)
        dy = np.sin(angles, dtype=np.float32)
        out = np.full(angles.shape[0], max_range, dtype=np.float32)

        if self._cr2.size:
            vx = ox - self._cxy[0]
            vy = oy - self._cxy[1]
            b = np.outer(vx, dx)
            b += np.outer(vy, dy)
            c = (vx * vx + vy * vy - self._cr2)[:, None]
            disc = b * b - c
            sq = np.sqrt(np.maximum(disc, 0.0))
            t0 = -b - sq
            t1 = -b + sq
            t = np.where(t0 > 0.0, t0, t1)
            t = np.where((disc > 0.0) & (t > 0.0), t, max_range)
            np.minimum(out, t.min(axis=0), out=out)

        if self._b0.size:
            idx = 1.0 / np.where(dx == 0.0, 1e-9, dx)
            idy = 1.0 / np.where(dy == 0.0, 1e-9, dy)
            tx1 = np.outer(self._b0[0] - ox, idx)
            tx2 = np.outer(self._b1[0] - ox, idx)
            ty1 = np.outer(self._b0[1] - oy, idy)
            ty2 = np.outer(self._b1[1] - oy, idy)
            lo = np.maximum(np.minimum(tx1, tx2), np.minimum(ty1, ty2))
            hi = np.minimum(np.maximum(tx1, tx2), np.maximum(ty1, ty2))
            t = np.where(lo > 0.0, lo, hi)
            ok = (hi >= np.maximum(lo, 0.0)) & (t > 0.0)
            np.minimum(out, np.where(ok, t, max_range).min(axis=0), out=out)

        return out

    # ---------------------------------------------------------------- truy van
    def on_table(self, x, y, margin=0.0):
        return (margin <= x <= self.width - margin and
                margin <= y <= self.height - margin)

    def edge_distance(self, x, y):
        return min(x, y, self.width - x, self.height - y)

    def raycast(self, ox, oy, ang, max_range):
        dx = math.cos(ang)
        dy = math.sin(ang)
        best = max_range
        for ob in self.obstacles:
            t = ob.ray(ox, oy, dx, dy, best)
            if t is not None and t < best:
                best = t
        return best

    def line_of_sight(self, x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return True
        dx /= L
        dy /= L
        for ob in self.obstacles:
            t = ob.ray(x0, y0, dx, dy, L)
            if t is not None and t < L - 1e-3:
                return False
        return True

    def min_obstacle_clearance(self, x, y):
        best = 1e9
        for ob in self.solid:
            d = ob.dist_to_point(x, y)
            if d < best:
                best = d
        return best

    def bay_clearance(self, x, y):
        """Khoang cach toi vach hoc gan nhat (bo qua vat can thuong)."""
        best = 1e9
        for bay in self.bays:
            d = bay.clearance(x, y)
            if d < best:
                best = d
        return best

    def wedge(self, x, y, theta, radius):
        """Vach loe day xe ve giua truc - mo phong doan vat goc o mieng hoc.

        Than xe TRON nen cai nem chi phai lam mot viec: day xe sang ngang cho
        dung truc. Khong co buoc nay thi doan loe chi de nhin - xe cham vach
        la dung yen tai cho chu khong duoc nan lai.
        """
        for bay in self.bays:
            u, v, dth = bay.to_local(x, y, theta)
            # CHI nan khi xe that su dang ti vao mat vat o mieng hoc va dang
            # huong vao trong. Thieu ba dieu kien nay thi cai nem thanh nam
            # cham: xe huc vao SUON hoc cung bi keo ve truc (tuc la di xuyen
            # qua vach), va lo dam vao hoc moi nhu thi bi hut han vao trong.
            # Cai nem CHI ton tai o doan vat. Qua khoi doan do, hai vach song
            # song voi truc: chung chan duoc xe di ngang chu khong day duoc xe
            # sang ben. Dat BAY_FLARE = 0 thi khong con cho nao nan xe ca -
            # va do dung la cai hoc thang tuot doi +-5 mm.
            if BAY_FLARE <= 0.0:
                continue
            if u < -bay.half_out - radius or u > -bay.half_out + BAY_FLARE:
                continue
            # Lech qua ngan nay thi mui xe dam thang vao MAT TRUOC cua vach
            # chu khong ti vao mat vat - khong co gi nan no ca. Day chinh la
            # gioi han hinh hoc: o mat cua, long ho `mouth_half`, xe ban kinh
            # `radius`, nen tam xe phai nam trong khoang do tru di ban kinh.
            if abs(v) > bay.mouth_half - radius + 0.005 or abs(dth) > 0.55:
                continue
            for dv in (0.004, 0.010, 0.018, 0.028, 0.040):
                nv = v - math.copysign(min(dv, abs(v)), v) if v else v
                nx, ny = bay.local_to_world(u, nv)
                if self.min_obstacle_clearance(nx, ny) >= radius:
                    return nx, ny
        return None

    def free_spot(self, rng, radius, margin=0.12, tries=200):
        for _ in range(tries):
            x = rng.uniform(margin + radius, self.width - margin - radius)
            y = rng.uniform(margin + radius, self.height - margin - radius)
            if self.min_obstacle_clearance(x, y) > radius + 0.10:
                return x, y
        return self.width * 0.5, self.height * 0.5

    def as_dict(self):
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": [o.as_dict() for o in self.obstacles],
            "bays": [b.as_dict() for b in self.bays],
            "beacons": [b.as_dict() for b in self.beacons],
            "dock": self.dock.as_dict() if self.dock else None,
        }


# --------------------------------------------------------------------- scenario
def make_world(rng: random.Random, stage: int = 3) -> World:
    """Sinh ngau nhien mot canh.

    stage 0: ban trong
    stage 1: them vat can
    stage 2: them tram sac that + hoc moi nhu cung kieu
    """
    w = rng.uniform(2.8, 3.8)
    h = rng.uniform(2.2, 3.0)
    world = World(w, h)

    if stage >= 1:
        n = rng.randint(1, 4) if stage == 1 else rng.randint(2, 5)
        for _ in range(n):
            if rng.random() < 0.5:
                r = rng.uniform(0.07, 0.20)
                world.add_obstacle(Obstacle(
                    "circle", x=rng.uniform(0.4, w - 0.4),
                    y=rng.uniform(0.4, h - 0.4), r=r))
            else:
                bw = rng.uniform(0.20, 0.50)
                bh = rng.uniform(0.20, 0.50)
                x = rng.uniform(0.3, w - 0.3 - bw)
                y = rng.uniform(0.3, h - 0.3 - bh)
                world.add_obstacle(Obstacle(
                    "box", x0=x, y0=y, x1=x + bw, y1=y + bh))

    if stage >= 2:
        # Hoc luon quay lung ra mep ban (nguoi that cung ke sat tuong nhu vay),
        # nen huong cua no la 1 trong 4 huong chinh.
        pad = 0.5 * BAY_OUT + 0.02
        side = rng.randrange(4)
        if side == 0:
            dx, dy, head = rng.uniform(0.7, w - 0.7), pad, -math.pi / 2
        elif side == 1:
            dx, dy, head = rng.uniform(0.7, w - 0.7), h - pad, math.pi / 2
        elif side == 2:
            dx, dy, head = pad, rng.uniform(0.7, h - 0.7), math.pi
        else:
            dx, dy, head = w - pad, rng.uniform(0.7, h - 0.7), 0.0
        dock = Dock(dx, dy, head)
        ax, ay = dock.approach(0.45)
        world.solid = [o for o in world.solid
                       if o.dist_to_point(dx, dy) > 0.55
                       and o.dist_to_point(ax, ay) > 0.40]
        world.obstacles = list(world.solid)
        world.dock = dock
        world.add_bay(dock)
        world.beacons.append(dock.beacon)

        # Hoc moi nhu: tren LiDAR giong het tram sac nhung khong phat hong ngoai.
        # Khong co no thi xe chi can thay hinh la lao vao, khoi hoi hong ngoai.
        # stage 2 mot cai moi nhu, stage 3 thi hai - vao hoc moi nhu roi phai
        # biet lui ra la ky nang kho, cho hoc dan.
        for _ in range(1 if stage == 2 else rng.randint(1, 2)):
            for _ in range(40):
                mx = rng.uniform(0.6, w - 0.6)
                my = rng.uniform(0.6, h - 0.6)
                mh = rng.randrange(4) * math.pi / 2
                if (math.hypot(mx - dx, my - dy) > 1.0 and
                        world.min_obstacle_clearance(mx, my) > 0.45):
                    world.add_bay(Bay(mx, my, mh, tag="decoy"))
                    break

    world.bake()
    return world
