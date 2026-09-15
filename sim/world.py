"""The gioi mo phong: mat ban co mep vuc, vat can, den hong ngoai, tram sac."""
import math
import random

from .geometry import ray_aabb, ray_circle, point_segment_dist

# Hai kenh hong ngoai (khac tan so tren phan cung that, vi du 38kHz / 56kHz)
IR_CALL = 0     # nguoi dung "goi" xe toi
IR_DOCK = 1     # den bao cua tram sac


class Obstacle:
    """Vat can tren ban. kind = 'circle' | 'box'."""

    __slots__ = ("kind", "x", "y", "r", "x0", "y0", "x1", "y1")

    def __init__(self, kind, **kw):
        self.kind = kind
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
            # ben trong hop: khoang cach am toi canh gan nhat
            return -min(px - self.x0, self.x1 - px, py - self.y0, self.y1 - py)
        return math.hypot(dx, dy)

    def as_dict(self):
        if self.kind == "circle":
            return {"kind": "circle", "x": self.x, "y": self.y, "r": self.r}
        return {"kind": "box", "x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


class Beacon:
    """Den hong ngoai phat tin hieu tren mot kenh."""

    __slots__ = ("x", "y", "channel", "active", "power")

    def __init__(self, x, y, channel, active=True, power=1.0):
        self.x = x
        self.y = y
        self.channel = channel
        self.active = active
        self.power = power

    def as_dict(self):
        return {"x": self.x, "y": self.y, "ch": self.channel,
                "active": bool(self.active), "power": self.power}


class World:
    """Mat ban hinh chu nhat [0,W] x [0,H]. Ra khoi bien = roi khoi ban."""

    def __init__(self, width=2.4, height=1.8):
        self.width = width
        self.height = height
        self.obstacles = []
        self.beacons = []
        self.dock = None          # Beacon kenh IR_DOCK (tram sac)
        self.dock_heading = 0.0   # huong xe phai quay khi cam sac

    # ---------------------------------------------------------------- truy van
    def on_table(self, x, y, margin=0.0):
        return (margin <= x <= self.width - margin and
                margin <= y <= self.height - margin)

    def edge_distance(self, x, y):
        """Khoang cach ngan nhat toi mep ban (am neu da ra ngoai)."""
        return min(x, y, self.width - x, self.height - y)

    def raycast(self, ox, oy, ang, max_range):
        """Ban tia tim vat can gan nhat. Mep ban KHONG phan xa sieu am."""
        dx = math.cos(ang)
        dy = math.sin(ang)
        best = max_range
        for ob in self.obstacles:
            t = ob.ray(ox, oy, dx, dy, best)
            if t is not None and t < best:
                best = t
        return best

    def line_of_sight(self, x0, y0, x1, y1):
        """True neu doan thang khong bi vat can chan (cho tia hong ngoai)."""
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
        for ob in self.obstacles:
            d = ob.dist_to_point(x, y)
            if d < best:
                best = d
        return best

    def free_spot(self, rng, radius, margin=0.12, tries=200):
        """Tim vi tri trong tren ban, cach vat can it nhat `radius`."""
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
            "dock_heading": self.dock_heading,
        }


# --------------------------------------------------------------------- scenario
def make_world(rng: random.Random, stage: int = 3) -> World:
    """Sinh ngau nhien mot canh: kich thuoc ban, vat can, tram sac.

    stage 0: ban trong, chi hoc khong roi khoi mep
    stage 1: them vat can
    stage 2+: them tram sac / den goi
    """
    w = rng.uniform(1.8, 3.0)
    h = rng.uniform(1.4, 2.4)
    world = World(w, h)

    if stage >= 1:
        n = rng.randint(1, 4) if stage == 1 else rng.randint(2, 6)
        for _ in range(n):
            if rng.random() < 0.5:
                r = rng.uniform(0.05, 0.16)
                x = rng.uniform(0.25, w - 0.25)
                y = rng.uniform(0.25, h - 0.25)
                world.obstacles.append(Obstacle("circle", x=x, y=y, r=r))
            else:
                bw = rng.uniform(0.10, 0.45)
                bh = rng.uniform(0.10, 0.45)
                x = rng.uniform(0.2, w - 0.2 - bw)
                y = rng.uniform(0.2, h - 0.2 - bh)
                world.obstacles.append(
                    Obstacle("box", x0=x, y0=y, x1=x + bw, y1=y + bh))

    if stage >= 2:
        # Tram sac dat sat mep ban, quay mat vao trong
        side = rng.randrange(4)
        pad = 0.10
        if side == 0:
            dx, dy, head = rng.uniform(0.3, w - 0.3), pad, math.pi / 2
        elif side == 1:
            dx, dy, head = rng.uniform(0.3, w - 0.3), h - pad, -math.pi / 2
        elif side == 2:
            dx, dy, head = pad, rng.uniform(0.3, h - 0.3), 0.0
        else:
            dx, dy, head = w - pad, rng.uniform(0.3, h - 0.3), math.pi
        # don sach vat can quanh tram sac
        world.obstacles = [o for o in world.obstacles
                           if o.dist_to_point(dx, dy) > 0.30]
        dock = Beacon(dx, dy, IR_DOCK, active=True)
        world.dock = dock
        world.dock_heading = head
        world.beacons.append(dock)

    return world
