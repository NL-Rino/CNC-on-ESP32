"""Ve khung hinh ASCII cho terminal - xem nhanh xe dang lam gi."""
import math
import sys

GLYPH_DIR = ">^<v"


def ascii_frame(env, cols=62):
    w, h = env.world.width, env.world.height
    rows = max(8, int(cols * h / w / 2.1))
    grid = [[" "] * cols for _ in range(rows)]

    def cell(x, y):
        cx = min(cols - 1, max(0, int(x / w * cols)))
        cy = min(rows - 1, max(0, int((h - y) / h * rows)))
        return cy, cx

    for ob in env.world.obstacles:
        x0, y0, x1, y1 = ob.x0, ob.y0, ob.x1, ob.y1
        r0, c0 = cell(x0, y1)
        r1, c1 = cell(x1, y0)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if 0 <= r < rows and 0 <= c < cols:
                    grid[r][c] = "#"

    for bay in env.world.bays:
        r, c = cell(*bay.mouth)
        grid[r][c] = "C" if bay.tag == "dock" else "c"    # C = that, c = moi nhu
    if env.world.dock is not None:
        r, c = cell(*env.world.dock.pocket)
        grid[r][c] = "o"                                  # cho dung sac
    if env.call is not None:
        r, c = cell(env.call.x, env.call.y)
        grid[r][c] = "!"

    rb = env.robot
    r, c = cell(rb.x, rb.y)
    idx = int(((rb.theta + math.pi / 4) % (2 * math.pi)) / (math.pi / 2)) % 4
    grid[r][c] = GLYPH_DIR[idx]

    top = "+" + "-" * cols + "+"
    body = "\n".join("|" + "".join(row) + "|" for row in grid)
    s = env.sensors
    bar = int(rb.battery * 10)
    sec = env.lidar.sector_ranges(rb.oth)
    n = len(sec)
    fwd = min(sec[(n // 2 - 1) % n], sec[n // 2 % n])
    cand = ", ".join("%.0f do/%.1fm/truc %.0f do"
                     % (math.degrees(c.bearing), c.dist, math.degrees(c.yaw))
                     for c in env.cands[:2]) or "khong"
    hud = ("t=%5.1fs  pin[%s%s] %3.0f%%  truoc=%4.2fm  vuc=%d%d"
           "  ir_goi=%.2f ir_sac=%.2f%s\nhoc sac thay duoc: %s"
           % (env.steps * env.cfg.dt, "#" * bar, "." * (10 - bar), rb.battery * 100,
              fwd, int(s.cliff_front), int(s.cliff_rear), s.ir[0], s.ir[1],
              "  [DANG SAC]" if rb.charging else "", cand))
    return top + "\n" + body + "\n" + top + "\n" + hud


def print_frame(env, clear=True):
    if clear:
        sys.stdout.write("\033[H\033[J")
    sys.stdout.write(ascii_frame(env) + "\n")
    sys.stdout.flush()
