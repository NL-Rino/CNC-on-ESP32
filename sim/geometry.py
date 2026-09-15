"""Hinh hoc co ban cho mo phong: raycast, va cham, goc.

Tat ca don vi SI: met, radian, giay.
"""
import math

TWO_PI = 2.0 * math.pi


def wrap_angle(a: float) -> float:
    """Dua goc ve khoang [-pi, pi)."""
    a = (a + math.pi) % TWO_PI
    if a < 0.0:
        a += TWO_PI
    return a - math.pi


def clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def ray_circle(ox, oy, dx, dy, cx, cy, r, max_t):
    """Khoang cach tu goc tia den duong tron, hoac None."""
    fx = ox - cx
    fy = oy - cy
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - r * r
    if c > 0.0 and b > 0.0:
        return None
    disc = b * b - c
    if disc < 0.0:
        return None
    sq = math.sqrt(disc)
    t = -b - sq
    if t < 0.0:
        t = -b + sq
    if t < 0.0 or t > max_t:
        return None
    return t


def ray_aabb(ox, oy, dx, dy, x0, y0, x1, y1, max_t):
    """Khoang cach tu goc tia den hop chu nhat (slab method), hoac None."""
    tmin = 0.0
    tmax = max_t
    for o, d, lo, hi in ((ox, dx, x0, x1), (oy, dy, y0, y1)):
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
            continue
        inv = 1.0 / d
        t1 = (lo - o) * inv
        t2 = (hi - o) * inv
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > tmin:
            tmin = t1
        if t2 < tmax:
            tmax = t2
        if tmin > tmax:
            return None
    return tmin


def point_segment_dist(px, py, x0, y0, x1, y1):
    vx = x1 - x0
    vy = y1 - y0
    wx = px - x0
    wy = py - y0
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        return math.hypot(wx, wy)
    t = clamp((wx * vx + wy * vy) / L2, 0.0, 1.0)
    return math.hypot(px - (x0 + t * vx), py - (y0 + t * vy))
