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


LEG_R = 0.045           # ban kinh cang chan o tam quet LiDAR (~20 cm tren san)
STRIDE = 0.62           # do dai mot buoc chan (m)
HIP_W = 0.09            # hai chan cach nhau bao nhieu theo be ngang
STANCE = 0.58           # ti le chu ky ma mot chan CHAM DAT (con lai la nhac len)
FAR_AWAY = -1000.0      # cho de chan dang nhac len - ngoai tam moi phep tinh


class Walker:
    """Nguoi di lai, nhin tu LiDAR: HAI CHAM nho hien ra roi bien mat.

    Day la chi tiet quan trong nhat ve nguoi trong mo phong nay. LiDAR quet
    ngang o ~20 cm tren san, nen no KHONG thay ca nguoi - no thay hai cai
    cang chan. Ma chan thi:

      - chan dang cham dat thi DUNG YEN tai cho trong khi than nguoi di qua
      - chan dang nhac len thi BIEN MAT khoi tam quet
      - buoc tiep theo no HIEN RA o mot cho khac, phia truoc

    Nen tren man hinh LiDAR, mot nguoi dang di la mot cham nam yen roi tat,
    rot mot cai o cho khac, tat, lai o cho khac. Khong he giong mot khoi
    truot muot ma ban se ve neu chi ngoi tuong tuong.
    """

    __slots__ = ("legs", "x", "y", "vx", "vy", "speed", "phase",
                 "planted", "turn_t", "pause_t")

    def __init__(self, x, y, speed, heading, r=LEG_R):
        self.x = x
        self.y = y
        self.speed = speed
        self.vx = speed * math.cos(heading)
        self.vy = speed * math.sin(heading)
        self.phase = 0.0
        self.legs = [Obstacle("circle", tag="leg", x=x, y=y, r=r),
                     Obstacle("circle", tag="leg", x=x, y=y, r=r)]
        self.planted = [(x, y), (x, y)]
        self.turn_t = 0.0
        self.pause_t = 0.0
        self._replant(0)
        self._replant(1)

    def obstacles(self):
        return self.legs

    def _replant(self, i):
        """Dat ban chan moi: phia truoc than mot nua buoc, lech sang mot ben."""
        h = math.atan2(self.vy, self.vx)
        side = 1.0 if i == 0 else -1.0
        fx, fy = math.cos(h), math.sin(h)
        self.planted[i] = (self.x + 0.5 * STRIDE * fx - side * HIP_W * fy,
                           self.y + 0.5 * STRIDE * fy + side * HIP_W * fx)

    def _leg_down(self, i):
        """Chan i co dang cham dat khong. Hai chan lech pha nhau nua chu ky."""
        ph = (self.phase + 0.5 * i) % 1.0
        return ph < STANCE

    def step(self, world, dt, rng):
        moving = self.pause_t <= 0.0
        if not moving:
            self.pause_t -= dt
        else:
            nx = self.x + self.vx * dt
            ny = self.y + self.vy * dt
            if self._chan(world, nx, ny):
                a = rng.uniform(0.0, 2.0 * math.pi)
                self.vx = self.speed * math.cos(a)
                self.vy = self.speed * math.sin(a)
            else:
                self.x, self.y = nx, ny
                # Nhip chan theo quang duong di duoc, khong theo thoi gian:
                # di cham thi buoc thua, dung han thi khong buoc nao.
                old = self.phase
                self.phase = (self.phase + self.speed * dt / STRIDE) % 1.0
                for i in (0, 1):
                    ph_old = (old + 0.5 * i) % 1.0
                    ph_new = (self.phase + 0.5 * i) % 1.0
                    # vua tu nhac-len chuyen sang cham-dat -> dat ban chan moi
                    if ph_old >= STANCE > ph_new or (ph_new < ph_old and ph_new < STANCE):
                        self._replant(i)
            self.turn_t -= dt
            if self.turn_t <= 0.0:
                self.turn_t = rng.uniform(1.5, 5.0)
                if rng.random() < 0.2:
                    self.pause_t = rng.uniform(0.6, 2.5)
                else:
                    a = math.atan2(self.vy, self.vx) + rng.gauss(0.0, 0.7)
                    self.vx = self.speed * math.cos(a)
                    self.vy = self.speed * math.sin(a)

        # Dua vi tri thuc te cho tung chan. Chan dang nhac len thi day han ra
        # ngoai the gioi: khong tia LiDAR nao cham toi, va cung khong chan xe.
        for i, leg in enumerate(self.legs):
            if self._leg_down(i) or not moving:
                px, py = self.planted[i]
            else:
                px = py = FAR_AWAY
            leg.x, leg.y = px, py
            leg.x0, leg.y0 = px - leg.r, py - leg.r
            leg.x1, leg.y1 = px + leg.r, py + leg.r

    def _chan(self, world, nx, ny):
        """Co vat gi chan khong. Dung luoi khong gian: duyet het 96 vat can
        moi buoc cho moi nguoi la 531 nghin phep tinh mot tap."""
        return (not world.inside(nx, ny, 0.22)
                or world.static_clearance(nx, ny) < 0.22)

    def as_dict(self):
        return {"x": self.x, "y": self.y, "speed": self.speed, "walker": True,
                "legs": [[l.x, l.y, l.r] for l in self.legs]}


# Ten cu, giu lai cho mat bang da ve truoc day van doc duoc
def Mover(x, y, r, speed, heading, rng=None):        # noqa: N802
    return Walker(x, y, speed, heading, max(0.03, min(r, 0.09)))


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

    def __init__(self, width=3.2, height=2.4, boundary="cliff"):
        self.width = width
        self.height = height
        # "cliff" = mat ban, ra khoi bien la ROI. "wall" = phong kin, ra khoi
        # bien la dam tuong. Nha nguoi ta thi la "wall"; giu ca hai vi cam
        # bien vuc van con dung cho cau thang.
        self.boundary = boundary
        self.obstacles = []     # tat ca (dung cho LiDAR / duong ngam)
        self.solid = []         # vat can va cham
        self.bays = []          # hoc chu U
        self.movers = []        # nguoi di lai (moi nguoi = 2 cai chan)
        self.holes = []         # cau thang / khoang thong tang: roi xuong la hong.
                                # LiDAR quet ngang KHONG thay duoc - y het mep ban.
        self.beacons = []
        self.dock = None
        self._arrays_dirty = True

    def add_obstacle(self, ob):
        self.obstacles.append(ob)
        self.solid.append(ob)
        self._arrays_dirty = True

    def add_boundary_walls(self, thick=0.12):
        """Dung 4 buc tuong that quanh phong.

        Khong co buoc nay thi bien chi ton tai trong ham va cham: xe dam vao
        thi dung, nhung LIDAR KHONG THAY GI - tuong hien ra nhu khong gian
        trong. Bo nao se doc canh nha nhu mot bai bat kha thi.
        """
        w, h, t = self.width, self.height, thick
        for x0, y0, x1, y1 in ((-t, -t, w + t, 0.0), (-t, h, w + t, h + t),
                               (-t, 0.0, 0.0, h), (w, 0.0, w + t, h)):
            self.add_obstacle(Obstacle("box", tag="wall", x0=x0, y0=y0,
                                       x1=x1, y1=y1))

    def add_mover(self, mv):
        self.movers.append(mv)
        for ob in mv.obstacles():
            self.obstacles.append(ob)
            self.solid.append(ob)
        self._arrays_dirty = True

    def mover_obstacles(self):
        return [ob for mv in self.movers for ob in mv.obstacles()]

    def step_movers(self, dt, rng):
        """Cho vat di chuyen roi cap nhat THANG vao mang da nuong.

        Nuong lai ca the gioi moi buoc thi qua ton; vat di chuyen deu la hinh
        tron va duoc xep dau danh sach, nen chi can ghi de vai o toa do.
        """
        if not self.movers:
            return
        for mv in self.movers:
            mv.step(self, dt, rng)
        if not self._arrays_dirty:
            for i, ob in enumerate(self.mover_obstacles()):
                self._cxy[0, i] = ob.x
                self._cxy[1, i] = ob.y
                self._fast_cir[i] = (ob.x, ob.y, ob.r)

    def inside(self, x, y, margin=0.0):
        return (margin <= x <= self.width - margin and
                margin <= y <= self.height - margin)

    def add_bay(self, bay):
        self.bays.append(bay)
        self.obstacles.extend(bay.walls)
        self.solid.extend(bay.walls)
        self._arrays_dirty = True

    # ---------------------------------------------------------------- dung mang
    def bake(self):
        """Gom vat can thanh mang numpy de ban ca vong LiDAR trong mot luot."""
        # Vat di chuyen phai dung DAU danh sach tron: step_movers ghi de
        # truc tiep vao _cxy[:, :len(movers)] theo dung thu tu nay.
        movers = self.mover_obstacles()
        cir = movers + [o for o in self.obstacles
                        if o.kind == "circle" and o.tag != "leg"]
        box = [o for o in self.obstacles if o.kind == "box"]
        f32 = np.float32
        self._cxy = np.array([[o.x for o in cir], [o.y for o in cir]], dtype=f32)
        self._cr = np.array([o.r for o in cir], dtype=f32)
        self._cr2 = self._cr * self._cr
        self._b0 = np.array([[o.x0 for o in box], [o.y0 for o in box]], dtype=f32)
        self._b1 = np.array([[o.x1 for o in box], [o.y1 for o in box]], dtype=f32)

        # Rieng cho va cham: chi vat can RAN, va de dang mang phang de tinh
        # mot phat. Vong lap Python qua 30 vat can, ba lan moi buoc, tung
        # chiem 1/3 toan bo thoi gian mo phong.
        scir = self.mover_obstacles()
        self._n_mover = len(scir)
        scir += [o for o in self.solid if o.kind == "circle" and o.tag != "leg"]
        self._fast_cir = [(o.x, o.y, o.r) for o in scir]
        self._fast_box = [(o.x0, o.y0, o.x1, o.y1)
                          for o in self.solid if o.kind == "box"]
        self._build_grid()
        self._arrays_dirty = False

    # ------------------------------------------------------- luoi khong gian
    def _build_grid(self, cell=0.6, reach=0.40):
        """Xep vat can TINH vao o luoi.

        Mot can nha co gan 100 vat can (hon nua la chan ban ghe). Duyet het
        chung moi lan hoi va cham la 13 us; xe chi quan tam thu trong vong
        30 cm, tuc gan nhu luc nao cung chi vai cai. Xep san vao o luoi thi
        chi con ~3 us. Nguoi di lai KHONG vao luoi - ho doi cho lien tuc nen
        kiem rieng, ma cung chi co vai cai chan.
        """
        self._cell = cell
        self._gw = max(1, int(self.width / cell) + 3)
        self._gh = max(1, int(self.height / cell) + 3)
        self._grid = [[] for _ in range(self._gw * self._gh)]
        for i, (cx, cy, r) in enumerate(self._fast_cir):
            if i < self._n_mover:
                continue
            self._add_grid(cx - r - reach, cy - r - reach,
                           cx + r + reach, cy + r + reach, ("c", cx, cy, r))
        for b in self._fast_box:
            self._add_grid(b[0] - reach, b[1] - reach, b[2] + reach,
                           b[3] + reach, ("b",) + b)

    def _cell_ix(self, x, y):
        i = int(x / self._cell) + 1
        j = int(y / self._cell) + 1
        i = 0 if i < 0 else (self._gw - 1 if i >= self._gw else i)
        j = 0 if j < 0 else (self._gh - 1 if j >= self._gh else j)
        return j * self._gw + i

    def _add_grid(self, x0, y0, x1, y1, item):
        i0 = max(0, min(self._gw - 1, int(x0 / self._cell) + 1))
        i1 = max(0, min(self._gw - 1, int(x1 / self._cell) + 1))
        j0 = max(0, min(self._gh - 1, int(y0 / self._cell) + 1))
        j1 = max(0, min(self._gh - 1, int(y1 / self._cell) + 1))
        for j in range(j0, j1 + 1):
            row = j * self._gw
            for i in range(i0, i1 + 1):
                self._grid[row + i].append(item)

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

        # Loai truoc nhung vat can nam ngoai tam do. Trong can nha 12 m, dung
        # o mot goc thi gan nua so do dac xa hon 8 m - tinh chung cho moi tia
        # la phi. Loc tren mang ~100 phan tu re hon nhieu so voi mang
        # (100 x 460) sinh ra sau do.
        if self._cr2.size:
            vx = ox - self._cxy[0]
            vy = oy - self._cxy[1]
            gan = (vx * vx + vy * vy) <= (max_range + self._cr) ** 2
            if not gan.all():
                vx = vx[gan]
                vy = vy[gan]
                cr2 = self._cr2[gan]
            else:
                cr2 = self._cr2
            if vx.size == 0:
                vx = None             # loai het roi: bo qua nhanh hinh tron
        if self._cr2.size and vx is not None:
            b = np.outer(vx, dx)
            b += np.outer(vy, dy)
            c = (vx * vx + vy * vy - cr2)[:, None]
            disc = b * b - c
            sq = np.sqrt(np.maximum(disc, 0.0))
            t0 = -b - sq
            t1 = -b + sq
            t = np.where(t0 > 0.0, t0, t1)
            t = np.where((disc > 0.0) & (t > 0.0), t, max_range)
            np.minimum(out, t.min(axis=0), out=out)

        if self._b0.size:
            bx0, by0 = self._b0
            bx1, by1 = self._b1
            ex = np.maximum(np.maximum(bx0 - ox, 0.0), ox - bx1)
            ey = np.maximum(np.maximum(by0 - oy, 0.0), oy - by1)
            gan = (ex * ex + ey * ey) <= max_range * max_range
            if not gan.all():
                bx0, by0, bx1, by1 = bx0[gan], by0[gan], bx1[gan], by1[gan]
            nb = bx0.size
            if nb == 0:
                return out
            # Ban goc viet thang bang bieu thuc numpy sinh ra 16 mang tam moi
            # vong quet, moi mang ~17 nghin phan tu. Viet lai bang out= de
            # dung lai dung 4 cai. Ket qua giong het tung bit - cung mot phep
            # tinh, chi khac cho chua.
            nr = angles.shape[0]
            if getattr(self, "_rc_n", -1) != nb * nr:
                self._rc_n = nb * nr
                self._rc = [np.empty((nb, nr), dtype=np.float32)
                            for _ in range(5)]
            elif self._rc[0].shape != (nb, nr):
                self._rc = [b.reshape(nb, nr) for b in self._rc]
            a, b, lo, hi, tmp = self._rc
            idx = 1.0 / np.where(dx == 0.0, 1e-9, dx)
            idy = 1.0 / np.where(dy == 0.0, 1e-9, dy)
            np.multiply((bx0 - ox)[:, None], idx[None, :], out=a)
            np.multiply((bx1 - ox)[:, None], idx[None, :], out=b)
            np.minimum(a, b, out=lo)
            np.maximum(a, b, out=hi)
            np.multiply((by0 - oy)[:, None], idy[None, :], out=a)
            np.multiply((by1 - oy)[:, None], idy[None, :], out=b)
            # Lay min TRUOC vao tmp, roi moi de max len a: nguoc lai thi a da
            # bi ghi de mat gia tri goc truoc khi tinh max.
            np.minimum(a, b, out=tmp)
            np.maximum(a, b, out=a)
            np.maximum(lo, tmp, out=lo)
            np.minimum(hi, a, out=hi)
            # tmp = khoang cach VAO hop: lay `lo` neu duong, khong thi `hi`
            np.copyto(tmp, hi)
            np.copyto(tmp, lo, where=lo > 0.0)
            np.maximum(lo, 0.0, out=lo)
            # Khong cham thi dat thanh max_range de phep min() bo qua
            np.copyto(tmp, max_range, where=(hi < lo) | (tmp <= 0.0))
            np.minimum(out, tmp.min(axis=0), out=out)

        return out

    # ---------------------------------------------------------------- truy van
    def on_table(self, x, y, margin=0.0):
        """True = van con cho dung (khong roi)."""
        for x0, y0, x1, y1 in self.holes:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return False
        if self.boundary == "wall":
            return True
        return self.inside(x, y, margin)

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

    def clearance_full(self, x, y):
        """Duyet HET vat can - dung duoc o moi cu ly, nhung cham.

        Dung luc dung canh (dat ban ghe cach nhau bao xa), khong dung trong
        vong dieu khien. Khong can nuong mang truoc nen goi lien tuc luc dang
        them vat can cung khong sao.
        """
        best = 1e9
        for ob in self.solid:
            d = ob.dist_to_point(x, y)
            if d < best:
                best = d
        return best

    def static_clearance(self, x, y):
        """Nhu min_obstacle_clearance nhung BO QUA nguoi di lai.

        Dung cho chinh nguoi di lai - khong thi ho tu dam vao chan minh.
        """
        if self._arrays_dirty:
            self.bake()
        return self._grid_clearance(x, y)

    def min_obstacle_clearance(self, x, y):
        """Khoang cach toi vat can gan nhat - CHI DUNG trong vong 40 cm.

        Xa hon thi tra ve mot so >= 0.40 nhung khong nhat thiet dung, vi luoi
        khong gian chi xep vat can vao o trong tam do. Vong dieu khien chi hoi
        "co cham khong" (< 15 cm) nen khong sao; muon do that thi dung
        clearance_full().

        Goi ~2.4 lan moi buoc, moi lan duyet het vat can - tung chiem 1/3
        thoi gian mo phong. Da thu chuyen sang numpy: CHAM HON gap doi, vi
        voi vai chuc vat can thi chi phi goi numpy lon hon chinh phep tinh.
        Nen giu vong lap Python nhung duyet tren TUPLE da rut san, va bo
        builtin max() (no ton hon mot lenh re nhanh).
        """
        if self._arrays_dirty:
            self.bake()
        best = 1e9
        for cx, cy, r in self._fast_cir[:self._n_mover]:
            dx = x - cx
            dy = y - cy
            d = (dx * dx + dy * dy) ** 0.5 - r
            if d < best:
                best = d
        b = self._grid_clearance(x, y)
        return b if b < best else best

    def _grid_clearance(self, x, y):
        best = 1e9
        for it in self._grid[self._cell_ix(x, y)]:
            if it[0] == "c":
                _, cx, cy, r = it
                dx = x - cx
                dy = y - cy
                d = (dx * dx + dy * dy) ** 0.5 - r
                if d < best:
                    best = d
                continue
            _, x0, y0, x1, y1 = it
            dx = x0 - x
            if dx < 0.0:
                dx = x - x1
                if dx < 0.0:
                    dx = 0.0
            dy = y0 - y
            if dy < 0.0:
                dy = y - y1
                if dy < 0.0:
                    dy = 0.0
            if dx == 0.0 and dy == 0.0:
                d = -min(x - x0, x1 - x, y - y0, y1 - y)
            elif dy == 0.0:
                d = dx
            elif dx == 0.0:
                d = dy
            else:
                d = (dx * dx + dy * dy) ** 0.5
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

    def in_bay_corridor(self, x, y, theta, radius):
        """Xe co dang nam trong LOI VAO cua mot cai hoc khong?

        Phan biet "dang chui vao hoc" voi "dang huc vao suon hoc". Xat vach
        khi chui vao la chuyen binh thuong va khong bi phat; nhung neu mien
        phat cho ca viec ti vao suon thi do la mot ke ho - xe hoc duoc rang
        cu day vao hoc la va cham mien phi, va no nam ly o do 41% so buoc.
        """
        for bay in self.bays:
            u, v, dth = bay.to_local(x, y, theta)
            if -bay.half_out - radius <= u <= bay.half_in and \
                    abs(v) <= bay.half_in + 0.02 and abs(dth) < 0.9:
                return True
        return False

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
            if self.clearance_full(x, y) > radius + 0.10 and \
                    self.on_table(x, y):
                return x, y
        return self.width * 0.5, self.height * 0.5

    def as_dict(self):
        return {
            "width": self.width,
            "height": self.height,
            "boundary": self.boundary,
            "holes": [list(h) for h in self.holes],
            "movers": [m.as_dict() for m in self.movers],
            "obstacles": [o.as_dict() for o in self.obstacles],
            "bays": [b.as_dict() for b in self.bays],
            "beacons": [b.as_dict() for b in self.beacons],
            "dock": self.dock.as_dict() if self.dock else None,
        }


# ------------------------------------------------------------------- noi that
def _legs(world, cx, cy, w, h, ang, r, tag):
    """Bon chan o bon goc mot hinh chu nhat.

    O tam quet LiDAR (~20 cm tren san), cai ban khong phai mot khoi chu nhat
    - no la BON CHAM nho cach nhau ca met, va o cu ly 3 m moi cham chi chiem
    dung mot tia. Ve cai ban thanh hinh hop dac la lam bai de di rat nhieu so
    voi doi that.
    """
    c, s_ = math.cos(ang), math.sin(ang)
    for du, dv in ((0.5, 0.5), (0.5, -0.5), (-0.5, 0.5), (-0.5, -0.5)):
        u, v = du * w, dv * h
        world.add_obstacle(Obstacle("circle", tag=tag,
                                    x=cx + u * c - v * s_,
                                    y=cy + u * s_ + v * c, r=r))


def _dat_duoc(world, x, y, ban_kinh):
    return (world.inside(x, y, ban_kinh + 0.05) and
            world.clearance_full(x, y) > ban_kinh + 0.55)


def make_house(rng: random.Random, stage: int = 3) -> World:
    """Mot can nha THAT: to so voi con xe, chia phong, co ban ghe.

    stage 0  nha trong, khong do dac
    stage 1  them tuong ngan, ban ghe, tu ke
    stage 2  them tram sac + hoc moi nhu + cau thang
    stage 3  them nguoi di lai + den goi
    """
    w = rng.uniform(8.0, 12.0)
    h = rng.uniform(6.0, 9.0)
    world = World(w, h, boundary="wall")
    world.add_boundary_walls()

    if stage >= 1:
        # Tuong ngan phong, moi buc chua mot cua di rong ~0.95 m
        for _ in range(rng.randint(1, 3)):
            doc = rng.random() < 0.55
            if doc:
                x = rng.uniform(0.28 * w, 0.72 * w)
                cua = rng.uniform(1.0, h - 1.9)
                world.add_obstacle(Obstacle("box", tag="wall", x0=x - 0.06,
                                            y0=0.0, x1=x + 0.06, y1=cua))
                world.add_obstacle(Obstacle("box", tag="wall", x0=x - 0.06,
                                            y0=cua + 0.95, x1=x + 0.06, y1=h))
            else:
                y = rng.uniform(0.28 * h, 0.72 * h)
                cua = rng.uniform(1.0, w - 1.9)
                world.add_obstacle(Obstacle("box", tag="wall", x0=0.0,
                                            y0=y - 0.06, x1=cua, y1=y + 0.06))
                world.add_obstacle(Obstacle("box", tag="wall", x0=cua + 0.95,
                                            y0=y - 0.06, x1=w, y1=y + 0.06))

        # Ban an + ghe quanh no
        for _ in range(rng.randint(1, 3)):
            for _ in range(25):
                cx = rng.uniform(1.3, w - 1.3)
                cy = rng.uniform(1.3, h - 1.3)
                if not _dat_duoc(world, cx, cy, 0.9):
                    continue
                bw, bh = rng.uniform(1.0, 1.7), rng.uniform(0.7, 1.0)
                ang = rng.uniform(0.0, math.pi)
                _legs(world, cx, cy, bw, bh, ang, rng.uniform(0.028, 0.040), "ban")
                for k in range(rng.randint(2, 4)):
                    a = ang + k * math.pi / 2 + rng.gauss(0.0, 0.25)
                    d = 0.5 * max(bw, bh) + rng.uniform(0.32, 0.5)
                    gx, gy = cx + d * math.cos(a), cy + d * math.sin(a)
                    if world.inside(gx, gy, 0.35):
                        _legs(world, gx, gy, 0.40, 0.40,
                              rng.uniform(0, math.pi), 0.022, "ghe")
                break

        # Do khoi: sofa, tu, ke sach
        for _ in range(rng.randint(2, 5)):
            for _ in range(25):
                bw, bh = rng.uniform(0.45, 2.0), rng.uniform(0.40, 0.75)
                if rng.random() < 0.5:
                    bw, bh = bh, bw
                x0 = rng.uniform(0.15, w - 0.15 - bw)
                y0 = rng.uniform(0.15, h - 0.15 - bh)
                if world.clearance_full(x0 + bw / 2, y0 + bh / 2) > 0.75:
                    world.add_obstacle(Obstacle("box", tag="do", x0=x0, y0=y0,
                                                x1=x0 + bw, y1=y0 + bh))
                    break

    if stage >= 2:
        # Cau thang: LiDAR khong thay duoc, chi hai mat do vuc cuu duoc xe
        if rng.random() < 0.6:
            for _ in range(25):
                sw, sh = rng.uniform(0.9, 1.6), rng.uniform(0.9, 1.6)
                x0 = rng.uniform(0.3, w - 0.3 - sw)
                y0 = rng.uniform(0.3, h - 0.3 - sh)
                if world.clearance_full(x0 + sw / 2, y0 + sh / 2) > 1.0:
                    world.holes.append((x0, y0, x0 + sw, y0 + sh))
                    break

        # Tram sac ke sat mot buc tuong ngoai, lui vao 25 cm
        pad = 0.5 * BAY_OUT + 0.25
        for _ in range(40):
            side = rng.randrange(4)
            if side == 0:
                dx, dy, head = rng.uniform(1.0, w - 1.0), pad, -math.pi / 2
            elif side == 1:
                dx, dy, head = rng.uniform(1.0, w - 1.0), h - pad, math.pi / 2
            elif side == 2:
                dx, dy, head = pad, rng.uniform(1.0, h - 1.0), math.pi
            else:
                dx, dy, head = w - pad, rng.uniform(1.0, h - 1.0), 0.0
            if world.clearance_full(dx, dy) > 0.75 and \
                    world.on_table(dx, dy):
                break
        dock = Dock(dx, dy, head)
        ax, ay = dock.approach(0.5)
        world.solid = [o for o in world.solid
                       if o.dist_to_point(dx, dy) > 0.5
                       and o.dist_to_point(ax, ay) > 0.4]
        world.obstacles = [o for o in world.obstacles
                           if o in world.solid or o.tag == "leg"]
        world.dock = dock
        world.add_bay(dock)
        world.beacons.append(dock.beacon)

        for _ in range(rng.randint(1, 2)):
            for _ in range(40):
                mx = rng.uniform(0.6, w - 0.6)
                my = rng.uniform(0.6, h - 0.6)
                if (math.hypot(mx - dx, my - dy) > 2.0 and
                        world.clearance_full(mx, my) > 0.5 and
                        world.on_table(mx, my)):
                    world.add_bay(Bay(mx, my, rng.randrange(4) * math.pi / 2,
                                      tag="decoy"))
                    break

    if stage >= 3:
        for _ in range(rng.randint(1, 3)):
            for _ in range(30):
                mx = rng.uniform(0.8, w - 0.8)
                my = rng.uniform(0.8, h - 0.8)
                if (world.clearance_full(mx, my) > 0.6 and
                        world.on_table(mx, my)):
                    world.add_mover(Walker(mx, my, rng.uniform(0.5, 1.1),
                                           rng.uniform(-math.pi, math.pi)))
                    break

    world.bake()
    return world


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
        # Hoc quay lung ve phia mep ban (nguoi that cung ke sat tuong nhu
        # vay) nen huong cua no la 1 trong 4 huong chinh. Nhung KHONG dat sat
        # mep: de lui vao 25 cm. Sat mep thi luc cam sac mui xe chi cach vuc
        # 7 cm, va quan trong hon - LiDAR khong thay duoc mep ban, xe phai
        # doan mep bang "quat nay trong tron". Dat mot khoi 40 cm ngay tai
        # mep la pha hong dung cai manh moi do.
        pad = 0.5 * BAY_OUT + 0.25
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

        # Nguoi di ngang qua. Chi co tu stage 3: xe phai biet ne vat TINH da
        # roi moi hoc duoc rang cho trong luc nay mot giay nua co the khong
        # con trong. Dua vao som qua thi hai bai lan vao nhau.
        if stage >= 3:
            for _ in range(rng.randint(1, 2)):
                for _ in range(20):
                    mx = rng.uniform(0.5, w - 0.5)
                    my = rng.uniform(0.5, h - 0.5)
                    if (math.hypot(mx - dx, my - dy) > 0.9 and
                            world.clearance_full(mx, my) > 0.35):
                        world.add_mover(Mover(mx, my, rng.uniform(0.12, 0.22),
                                              rng.uniform(0.35, 0.9),
                                              rng.uniform(-math.pi, math.pi)))
                        break

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
                        world.clearance_full(mx, my) > 0.45):
                    world.add_bay(Bay(mx, my, mh, tag="decoy"))
                    break

    world.bake()
    return world
