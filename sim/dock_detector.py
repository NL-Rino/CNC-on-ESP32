"""Do hinh dang tram sac (hop 15 x 15 cm) tu mot vong quet LiDAR.

Day la thuat toan hinh hoc co dien, KHONG phai mang no-ron - viet sao cho
chuyen thang sang C chay tren ESP32 duoc (xem firmware/dock_detect.c).
Mang no-ron chi nhan ket qua: co vat co kich thuoc do o gan khong, huong nao,
cach bao xa.

Cach lam (dung kieu ma firmware hay viet):
  1. Va lai nhung diem mat le loi.
  2. Cat vong quet thanh doan: hai diem ke nhau lech khoang cach qua nguong
     thi coi nhu thuoc hai vat khac nhau.
  3. Doan nao rong 10-25 cm, phang (khong phai tuong dai, khong phai vat tron)
     va gan hon 3 m thi la ung vien.

Hop moi nhu cung 15 x 15 cm va goc cua vat can khac se lot qua duoc - dung vay:
xe phai quay dau lai va hoi bang hong ngoai moi biet do co phai tram sac that
khong. Vi the ung vien duoc xep theo KHOANG CACH chu khong theo diem giong nhau.
"""
import math

import numpy as np

DOCK_W = 0.15           # canh that cua tram sac
WIDTH_MIN = 0.10        # be rong doan chap nhan duoc (m)
WIDTH_MAX = 0.25        # nhin cheo thay 2 mat -> rong toi 0.15*sqrt(2) = 0.21
MAX_DEPTH = 0.085       # goc hop nhin cheo nho ra toi 0.075 m
MIN_PTS = 4             # so diem toi thieu trong doan
MAX_DIST = 3.0          # xa hon thi so diem qua it, khong tin duoc
MIN_DIST = 0.10
GAP_ABS = 0.035         # nguong cat doan (m)
GAP_REL = 0.05          # cong them theo khoang cach
MAX_CAND = 2            # so ung vien gan nhat tra ve cho policy
PATCH_JUMP = 0.06       # va diem mat khi hai ben chenh nhau duoi muc nay


class Candidate:
    __slots__ = ("bearing", "dist", "width", "depth", "npts", "score")

    def __init__(self, bearing, dist, width, depth, npts, score):
        self.bearing = bearing
        self.dist = dist
        self.width = width
        self.depth = depth
        self.npts = npts
        self.score = score

    def __repr__(self):
        return ("<ung vien %.0f do, %.2f m, rong %.2f m, diem %.2f>"
                % (math.degrees(self.bearing), self.dist, self.width, self.score))


def patch_dropouts(ranges):
    """Va lai diem mat le loi. Chi 2% diem mat cung du cat vun mot hop 15 cm
    thanh cac manh qua ngan de nhan ra."""
    r = ranges.copy()
    lo = r[:-2]
    mid = r[1:-1]
    hi = r[2:]
    fix = (mid <= 0.0) & (lo > 0.0) & (hi > 0.0) & (np.abs(lo - hi) < PATCH_JUMP)
    if fix.any():
        r[1:-1] = np.where(fix, 0.5 * (lo + hi), mid)
    return r


def split_segments(r):
    """Cat vong quet thanh doan lien tuc theo buoc nhay khoang cach."""
    n = r.shape[0]
    a = r[:-1]
    b = r[1:]
    cut = (a <= 0.0) | (b <= 0.0) | (np.abs(b - a) > GAP_ABS + GAP_REL * np.minimum(a, b))
    idx = np.flatnonzero(cut)
    m = idx.shape[0]
    starts = np.empty(m + 1, dtype=np.intp)
    ends = np.empty(m + 1, dtype=np.intp)
    starts[0] = 0
    starts[1:] = idx + 1
    ends[:m] = idx + 1
    ends[m] = n
    keep = (ends - starts) >= MIN_PTS
    return starts[keep], ends[keep]


def detect(base, ranges, cos_a, sin_a, bearing_offset=0.0):
    """Tra ve toi da MAX_CAND ung vien, gan nhat truoc.

    base/cos_a/sin_a: goc cua tung diem trong vong quet (co dinh).
    bearing_offset: goc de bu phan xe da quay ke tu luc quet (de-skew).
    """
    r = patch_dropouts(ranges)
    starts, ends = split_segments(r)
    if starts.size == 0:
        return []
    last = ends - 1
    ra = r[starts]
    rb = r[last]
    xa = ra * cos_a[starts]
    ya = ra * sin_a[starts]
    xb = rb * cos_a[last]
    yb = rb * sin_a[last]
    ex = xb - xa
    ey = yb - ya
    width = np.sqrt(ex * ex + ey * ey)
    cx = 0.5 * (xa + xb)
    cy = 0.5 * (ya + yb)
    dist = np.sqrt(cx * cx + cy * cy)
    keep = np.flatnonzero((width >= WIDTH_MIN) & (width <= WIDTH_MAX) &
                          (dist >= MIN_DIST) & (dist <= MAX_DIST))

    out = []
    for k in keep.tolist():
        a = int(starts[k])
        b = int(ends[k])
        wdt = float(width[k])
        exk = float(ex[k])
        eyk = float(ey[k])
        rs = r[a:b]
        dx = rs * cos_a[a:b] - float(xa[k])
        dy = rs * sin_a[a:b] - float(ya[k])
        depth = float(np.abs(dx * eyk - dy * exk).max()) / wdt
        if depth > MAX_DEPTH:
            continue
        npts = b - a
        score = (1.0 - min(1.0, abs(wdt - 0.175) / 0.10)) * \
                (1.0 - 0.4 * min(1.0, depth / MAX_DEPTH))
        if npts < MIN_PTS + 2:
            score *= 0.75
        if score <= 0.05:
            continue
        bear = math.atan2(float(cy[k]), float(cx[k])) + bearing_offset
        if bear > math.pi:
            bear -= 2.0 * math.pi
        elif bear < -math.pi:
            bear += 2.0 * math.pi
        out.append(Candidate(bear, float(dist[k]), wdt, depth, npts, score))

    out.sort(key=lambda c: c.dist)
    return out[:MAX_CAND]


def detect_lidar(lidar, theta_now):
    """Chay bo do tren vong quet moi nhat, da bu phan xe quay tu luc quet."""
    off = lidar.scan_theta - theta_now
    return detect(lidar.base, lidar.r, lidar.cos_base, lidar.sin_base, off)
