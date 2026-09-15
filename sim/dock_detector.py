"""Do cai HOC chu U (ngoai 40 cm, long trong 31 cm) tu mot vong quet LiDAR.

Day la thuat toan hinh hoc co dien, KHONG phai mang no-ron - viet sao cho
chuyen thang sang C chay tren ESP32 duoc (xem firmware/dock_detect.c).

Y tuong: nhin tu phia truoc, cai hoc tao ra mot "hom" trong vong quet -
    gan (mep vach trai) -> nhay RA XA (long hoc) -> gan lai (mep vach phai)
Hai diem gan hai ben la hai mep cua; noi chung lai duoc mot DAY CUNG. Nhung
diem o giua deu nam PHIA SAU day cung do, sau khoang 35 cm (den thanh trong).

Cach lam:
  1. Va lai nhung diem mat le loi.
  2. Cat vong quet thanh doan lien tuc. Nguong cat phai LON hon do sau long
     hoc (35.5 cm), neu khong chinh cai hoc se bi cat doi.
  3. Voi moi doan: noi hai dau lai thanh day cung, roi do xem nhung diem o
     giua lom ra SAU day cung bao nhieu.
  4. Giu doan nao rong 26-48 cm va lom sau 14-60 cm.

Luu y tu thuc nghiem: tia LiDAR quet qua cua hoc KHONG nhay mot phat tu mep
vao thanh trong. No truot doc mat trong cua vach ben nen khoang cach len dan
thanh bac thang (0.82 -> 0.89 -> 1.07 -> 1.16 m o cu ly 0.8 m). Vi vay cach
"tim mep roi ghep cap" khong an - phai lay ca doan roi do do lom.

Vi day la chu U chu khong phai hop dac, ket qua cho ra ca HUONG TRUC cua hoc
(`yaw`) - goc ma xe phai quay ve de chui vao thang. Hop dac truoc day khong
cho duoc thong tin nay, ma khong co no thi khong the canh vao khe rong hon
than xe 1 cm.

Hoc moi nhu tren ban giong het hoc that o day - dung vay: xe phai quay ve
doi dien roi hoi hong ngoai moi biet cai nao that. Nen ung vien duoc xep theo
KHOANG CACH chu khong theo diem giong nhau.
"""
import math

import numpy as np

BAY_OUT = 0.40          # canh ngoai that cua hoc
BAY_DEPTH = 0.355       # long hoc sau bao nhieu tinh tu mat cua
WIDTH_MIN = 0.26        # nhin cheo thi cua hep lai (40 cm * cos 50 do = 26 cm)
WIDTH_MAX = 0.52        # nhin hoi cheo thi thay them mat ngoai vach ben
DEPTH_MIN = 0.14        # long hoc phai lom vao it nhat ngan nay
DEPTH_MAX = 0.60        # sau hon nua thi khong phai hoc
BULGE_MAX = 0.05        # diem loi RA TRUOC day cung qua muc nay = dau hieu vat dac
BULGE_FRAC = 0.12       # nhung cho phep vai diem nhu vay: hai dau day cung
                        # cung co nhieu +-2 cm nen day cung bi nghieng theo
MIN_PTS = 6             # so diem toi thieu trong doan
WIDTH_PRE = 0.95        # nguong loc so bo truoc khi co day cung
SHRINK_ITERS = 6        # so lan co day cung toi da
BACK_BAND = 0.08        # be day lop diem coi la thuoc thanh trong (m)
BACK_MIN_PTS = 5        # it hon thi khong du de khop duong thang
MIN_DIST = 0.12
MAX_DIST = 3.0
GAP_ABS = 0.45          # nguong cat doan (m) - phai > BAY_DEPTH
GAP_REL = 0.20          # cong them theo khoang cach
MAX_CAND = 2            # so ung vien gan nhat tra ve cho policy
PATCH_JUMP = 0.06       # va diem mat khi hai ben chenh nhau duoi muc nay


class Candidate:
    __slots__ = ("bearing", "dist", "width", "depth", "yaw", "npts", "score")

    def __init__(self, bearing, dist, width, depth, yaw, npts, score):
        self.bearing = bearing      # huong toi cua hoc (rad, 0 = truoc mat xe)
        self.dist = dist            # khoang cach toi cua hoc (m)
        self.width = width          # be rong cua do duoc (m)
        self.depth = depth          # long hoc lom vao bao sau (m)
        self.yaw = yaw              # huong TRUC hoc: xe phai quay ve goc nay
        self.npts = npts
        self.score = score

    def __repr__(self):
        return ("<hoc %.0f do, %.2f m, rong %.2f, sau %.2f, truc %.0f do, %.2f>"
                % (math.degrees(self.bearing), self.dist, self.width,
                   self.depth, math.degrees(self.yaw), self.score))


def patch_dropouts(ranges):
    """Va lai diem mat le loi. Mot diem mat giua long hoc se bi doc nham
    thanh mep neu khong va."""
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
    px = r * cos_a
    py = r * sin_a
    last = ends - 1
    xa = px[starts]
    ya = py[starts]
    xb = px[last]
    yb = py[last]
    ex = xb - xa
    ey = yb - ya
    width = np.sqrt(ex * ex + ey * ey)
    cx = 0.5 * (xa + xb)
    cy = 0.5 * (ya + yb)
    dist = np.sqrt(cx * cx + cy * cy)
    keep = np.flatnonzero((width >= WIDTH_MIN) & (width <= WIDTH_PRE) &
                          (dist >= MIN_DIST) & (dist <= MAX_DIST))

    out = []
    for k in keep.tolist():
        a = int(starts[k])
        b = int(ends[k])

        # Co day cung vao cho het loi.
        # Nhin cheo, cai hoc in bong thanh chu L: mat NGOAI cua vach ben nam
        # loi han ra truoc day cung noi hai dau doan. Cu cat dan dau nao gan
        # cho loi nhat, day cung se tu lui ve dung hai mep cua hoc.
        ok = False
        for _ in range(SHRINK_ITERS):
            x0 = float(px[a])
            y0 = float(py[a])
            ex = float(px[b - 1]) - x0
            ey = float(py[b - 1]) - y0
            wdt = math.hypot(ex, ey)
            if wdt < WIDTH_MIN or b - a < MIN_PTS:
                break
            mx = 0.5 * (x0 + float(px[b - 1]))
            my = 0.5 * (y0 + float(py[b - 1]))
            nx = -ey / wdt
            ny = ex / wdt
            if nx * mx + ny * my < 0.0:
                nx = -nx
                ny = -ny
            dep = (px[a:b] - x0) * nx + (py[a:b] - y0) * ny
            j = int(dep.argmin())
            if float(dep[j]) >= -BULGE_MAX:
                ok = True
                break
            if j * 2 < b - a:
                a += j
            else:
                b = a + j + 1
        if not ok or wdt < WIDTH_MIN or wdt > WIDTH_MAX:
            continue

        dmax = float(dep.max())
        if dmax < DEPTH_MIN or dmax > DEPTH_MAX:
            continue
        dist_k = math.hypot(mx, my)
        if dist_k < MIN_DIST or dist_k > MAX_DIST:
            continue

        # Truc cua hoc lay tu MAT THANH TRONG chu khong tu day cung.
        # Day cung chi co hai diem dau, moi diem nhieu +-2 cm, nen o cu ly
        # 0.4 m no cho sai so truc toi 40 do - khong the canh vao khe ho
        # 5 mm bang con so do. Thanh trong thi phang va co hang chuc diem:
        # khop mot duong thang qua chung on dinh hon han.
        sub = dep > dmax - BACK_BAND
        nback = int(sub.sum())
        if nback >= BACK_MIN_PTS:
            bx = px[a:b][sub]
            by = py[a:b][sub]
            ux = bx - bx.mean()
            uy = by - by.mean()
            sxx = float((ux * ux).sum())
            syy = float((uy * uy).sum())
            sxy = float((ux * uy).sum())
            ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)   # huong mat thanh
            fx = -math.sin(ang)                            # phap tuyen
            fy = math.cos(ang)
            if fx * mx + fy * my < 0.0:                    # cho chi ra xa xe
                fx = -fx
                fy = -fy
            nx, ny = fx, fy

        bear = math.atan2(my, mx) + bearing_offset
        yaw = math.atan2(ny, nx) + bearing_offset
        if bear > math.pi:
            bear -= 2.0 * math.pi
        elif bear < -math.pi:
            bear += 2.0 * math.pi
        if yaw > math.pi:
            yaw -= 2.0 * math.pi
        elif yaw < -math.pi:
            yaw += 2.0 * math.pi

        ws = 1.0 - min(1.0, abs(wdt - BAY_OUT) / 0.16)
        ds = 1.0 - min(1.0, abs(dmax - BAY_DEPTH) / 0.24)
        score = ws * ds
        if score <= 0.05:
            continue
        out.append(Candidate(bear, dist_k, wdt, dmax, yaw, b - a, score))

    out.sort(key=lambda c: c.dist)
    return out[:MAX_CAND]


def detect_lidar(lidar, theta_now):
    """Chay bo do tren vong quet moi nhat, da bu phan xe quay tu luc quet."""
    off = lidar.scan_theta - theta_now
    return detect(lidar.base, lidar.r, lidar.cos_base, lidar.sin_base, off)
