"""Doi chieu ban C trong firmware/ voi ban Python trong sim/.

Neu hai ban lech nhau thi bo nao se gap du lieu khac luc chay that so voi luc
huan luyen - loi kieu do rat kho tim tren phan cung, nen bat o day.

Chay: python3 tests/test_firmware.py   (can gcc)
"""
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import sim.dock_detector as dd
from sim.lidar import Lidar
from sim.robot import Robot
from sim.world import make_world

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.path.join(ROOT, "firmware")

MAIN_C = r"""
#include <stdio.h>
#include "dock_detect.h"
int main(int argc, char **argv) {
    static float r[4096], ca[4096], sa[4096];
    int n = 0;
    FILE *f = fopen(argv[1], "r");
    while (fscanf(f, "%f %f %f", &r[n], &ca[n], &sa[n]) == 3) n++;
    fclose(f);
    dock_cand_t out[DOCK_MAX_CAND];
    int k = dock_detect(r, ca, sa, n, 0.0f, out);
    for (int i = 0; i < k; ++i)
        printf("%.4f %.4f %.4f\n", out[i].bearing, out[i].dist, out[i].width);
    return 0;
}
"""


def build(tmp):
    src = os.path.join(tmp, "main.c")
    with open(src, "w") as f:
        f.write(MAIN_C)
    exe = os.path.join(tmp, "dd")
    r = subprocess.run(["gcc", "-O2", "-o", exe, src,
                        os.path.join(FW, "dock_detect.c"), "-I", FW, "-lm"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gcc loi:\n" + r.stderr)
    return exe


def main():
    if shutil.which("gcc") is None:
        print("bo qua: may nay khong co gcc")
        return 0
    tmp = tempfile.mkdtemp()
    exe = build(tmp)
    bad = 0
    n_scenes = 25
    for seed in range(n_scenes):
        w = make_world(random.Random(seed), 3)
        d = w.dock
        ld = Lidar()
        ld.reset(np.random.default_rng(seed))
        rb = Robot()
        dist = 0.6 + 0.4 * (seed % 4)
        rb.reset(d.x - dist * math.cos(d.heading),
                 d.y - dist * math.sin(d.heading), d.heading, 1.0)
        if not w.on_table(rb.x, rb.y):
            continue
        ld._scan(rb, w)
        path = os.path.join(tmp, "scan.txt")
        with open(path, "w") as f:
            for i in range(ld.n):
                f.write("%.6f %.6f %.6f\n"
                        % (ld.r[i], ld.cos_base[i], ld.sin_base[i]))
        py = dd.detect(ld.base, ld.r.copy(), ld.cos_base, ld.sin_base, 0.0)
        out = subprocess.run([exe, path], capture_output=True, text=True).stdout
        c = [tuple(float(v) for v in line.split())
             for line in out.splitlines() if line.strip()]
        ok = len(c) == len(py) and all(
            abs(a[0] - b.bearing) < 2e-3 and abs(a[1] - b.dist) < 2e-3 and
            abs(a[2] - b.width) < 2e-3 for a, b in zip(c, py))
        if not ok:
            bad += 1
            print("  FAIL canh %d" % seed)
            print("    python:", [(round(x.bearing, 3), round(x.dist, 3)) for x in py])
            print("    C     :", [(round(x[0], 3), round(x[1], 3)) for x in c])
    shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        print("%d/%d canh lech nhau" % (bad, n_scenes))
        return 1
    print("  ok   dock_detect.c khop dock_detector.py tren %d canh" % n_scenes)
    print("1/1 dat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
