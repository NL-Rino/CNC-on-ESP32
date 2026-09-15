"""The gioi mo phong: mat ban co mep vuc, vat can, den hong ngoai, tram sac.

Tram sac la mot HOP 15x15 cm that su nam tren ban, vi bay gio xe nhin bang
LiDAR - no phai *thay hinh dang* cua tram roi moi dung hong ngoai xac nhan.
Tren ban con co vai hop 15x15 cm khac khong phat hong ngoai (moi nhu) de xe
khong the chi dua vao hinh dang.
"""
import math
import random

import numpy as np

from .geometry import ray_aabb, ray_circle

IR_CALL = 0     # nguoi dung "goi" xe toi
IR_DOCK = 1     # den bao cua tram sac

DOCK_SIZE = 0.15        # canh hop tram sac (m) - dung 15 x 15 cm
DOCK_IR_CONE = 0.95     # nua goc phat hong ngoai cua tram (rad) ~ 54 do
DOCK_POCKET = 0.20      # cho xe dung sac, tinh tu TAM hop ra phia truoc (m)


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


class Dock:
    """Tram sac: hop 15x15 cm + den hong ngoai phat ra phia truoc mat."""

    def __init__(self, x, y, heading):
        self.x = x                 # tam hop
        self.y = y
        self.heading = heading     # huong XE phai quay khi cam sac (chia vao hop)
        h = DOCK_SIZE * 0.5
        self.box = Obstacle("box", tag="dock", x0=x - h, y0=y - h,
                            x1=x + h, y1=y + h)
        # den phat nguoc lai huong xe vao, tu mat truoc cua hop
        fx = x - (h + 0.005) * math.cos(heading)
        fy = y - (h + 0.005) * math.sin(heading)
        self.beacon = Beacon(fx, fy, IR_DOCK, active=True,
                             dir_ang=heading + math.pi, cone=DOCK_IR_CONE)

    @property
    def pocket(self):
        """Cho xe dung khi sac: cach tam hop DOCK_POCKET ve phia truoc mat."""
        return (self.x - DOCK_POCKET * math.cos(self.heading),
                self.y - DOCK_POCKET * math.sin(self.heading))

    def approach(self, d=0.55):
        return (self.x - d * math.cos(self.heading),
                self.y - d * math.sin(self.heading))

    @property
    def active(self):
        return self.beacon.active

    @active.setter
    def active(self, v):
        self.beacon.active = bool(v)

    def as_dict(self):
        return {"x": self.x, "y": self.y, "heading": self.heading,
                "size": DOCK_SIZE, "pocket": list(self.pocket),
                "active": bool(self.beacon.active)}


class World:
    """Mat ban hinh chu nhat [0,W] x [0,H]. Ra khoi bien = roi khoi ban."""

    def __init__(self, width=2.4, height=1.8):
        self.width = width
        self.height = height
        self.obstacles = []
        self.beacons = []
        self.dock = None
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

    def line_of_sight(self, x0, y0, x1, y1, skip_tag=None):
        dx = x1 - x0
        dy = y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return True
        dx /= L
        dy /= L
        for ob in self.obstacles:
            if skip_tag is not None and ob.tag == skip_tag:
                continue
            t = ob.ray(x0, y0, dx, dy, L)
            if t is not None and t < L - 1e-3:
                return False
        return True

    def min_obstacle_clearance(self, x, y):
        best = 1e9
        for ob in self.obstacles:
            d = ob.dist_to_point(x, y)
            if d < best:
                best = d
        return best

    def free_spot(self, rng, radius, margin=0.12, tries=200):
        for _ in range(tries):
            x = rng.uniform(margin, self.width - margin)
            y = rng.uniform(margin, self.height - margin)
            if self.min_obstacle_clearance(x, y) > radius + 0.05:
                return x, y
        return self.width * 0.5, self.height * 0.5

    def as_dict(self):
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": [o.as_dict() for o in self.obstacles],
            "beacons": [b.as_dict() for b in self.beacons],
            "dock": self.dock.as_dict() if self.dock else None,
        }


# --------------------------------------------------------------------- scenario
def make_world(rng: random.Random, stage: int = 3) -> World:
    """Sinh ngau nhien mot canh.

    stage 0: ban trong
    stage 1: them vat can
    stage 2: them tram sac that + hop moi nhu cung kich thuoc
    """
    w = rng.uniform(2.0, 3.2)
    h = rng.uniform(1.6, 2.6)
    world = World(w, h)

    if stage >= 1:
        n = rng.randint(1, 4) if stage == 1 else rng.randint(2, 5)
        for _ in range(n):
            if rng.random() < 0.5:
                r = rng.uniform(0.06, 0.18)
                world.obstacles.append(Obstacle(
                    "circle", x=rng.uniform(0.3, w - 0.3),
                    y=rng.uniform(0.3, h - 0.3), r=r))
            else:
                bw = rng.uniform(0.20, 0.50)
                bh = rng.uniform(0.20, 0.50)
                x = rng.uniform(0.25, w - 0.25 - bw)
                y = rng.uniform(0.25, h - 0.25 - bh)
                world.obstacles.append(Obstacle(
                    "box", x0=x, y0=y, x1=x + bw, y1=y + bh))

    if stage >= 2:
        pad = DOCK_SIZE * 0.5 + 0.015     # hop nam tron ven tren ban
        side = rng.randrange(4)
        if side == 0:
            dx, dy, head = rng.uniform(0.45, w - 0.45), pad, -math.pi / 2
        elif side == 1:
            dx, dy, head = rng.uniform(0.45, w - 0.45), h - pad, math.pi / 2
        elif side == 2:
            dx, dy, head = pad, rng.uniform(0.45, h - 0.45), math.pi
        else:
            dx, dy, head = w - pad, rng.uniform(0.45, h - 0.45), 0.0
        dock = Dock(dx, dy, head)
        # don quang duong vao tram
        px, py = dock.pocket
        world.obstacles = [o for o in world.obstacles
                           if o.dist_to_point(dx, dy) > 0.45
                           and o.dist_to_point(px, py) > 0.30]
        world.dock = dock
        world.obstacles.append(dock.box)
        world.beacons.append(dock.beacon)

        # hop moi nhu: nhin giong het tram sac tren LiDAR nhung khong phat IR
        for _ in range(rng.randint(1, 2)):
            for _ in range(30):
                mx = rng.uniform(0.35, w - 0.35)
                my = rng.uniform(0.35, h - 0.35)
                if (math.hypot(mx - dx, my - dy) > 0.8 and
                        world.min_obstacle_clearance(mx, my) > 0.35):
                    hs = DOCK_SIZE * 0.5
                    world.obstacles.append(Obstacle(
                        "box", tag="decoy", x0=mx - hs, y0=my - hs,
                        x1=mx + hs, y1=my + hs))
                    break

    world.bake()
    return world
