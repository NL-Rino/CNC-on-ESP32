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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from link import protocol as P  # noqa: E402

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
        printf("%.4f %.4f %.4f %.4f\n", out[i].bearing, out[i].dist,
               out[i].width, out[i].yaw);
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


LINK_C = r"""
#include <stdio.h>
#include <string.h>
#include "link_pack.h"
int main(void) {
    static uint8_t buf[4096];
    link_state_t st;
    st.x = 1.25f; st.y = -2.5f; st.th = 0.75f;
    st.v = 0.3125f; st.w = -0.125f; st.battery = 0.625f;
    st.ir_call = 0.25f; st.ir_dock = 0.875f;
    st.u_applied_l = -0.5f; st.u_applied_r = 0.75f;
    st.flags = LINK_F_CLIFF_R | LINK_F_REFLEX;
    int n = link_pack_state(buf, 1234u, 5678u, &st);
    printf("STATE %d ", n);
    for (int i = 0; i < n; ++i) printf("%02x", buf[i]);
    printf("\n");

    float scan[5] = {0.0f, 0.123f, 3.4567f, 8.0f, 70.0f};
    n = link_pack_scan(buf, 7u, 8u, scan, 5, 0.5f, 9u);
    printf("SCAN %d ", n);
    for (int i = 0; i < n; ++i) printf("%02x", buf[i]);
    printf("\n");

    // doc goi CMD do Python gui qua stdin (hex)
    char hex[1024];
    if (scanf("%1023s", hex) == 1) {
        int len = (int)strlen(hex) / 2;
        for (int i = 0; i < len; ++i) {
            unsigned v; sscanf(hex + 2 * i, "%2x", &v); buf[i] = (uint8_t)v;
        }
        float ul = 0, ur = 0; uint32_t ack = 0; uint8_t fl = 0;
        int ok = link_parse_cmd(buf, len, 0, &ul, &ur, &ack, &fl);
        printf("CMD %d %.6f %.6f %u %u\n", ok, ul, ur, ack, fl);
        ok = link_parse_cmd(buf, len, 99999u, &ul, &ur, &ack, &fl);
        printf("CMDSEQ %d\n", ok);      // seq khong khop -> phai la 0
    }
    return 0;
}
"""


def check_link(tmp):
    """Doi chieu tung byte goi tin giua link_pack.c va link/protocol.py."""
    src = os.path.join(tmp, "linkmain.c")
    with open(src, "w") as f:
        f.write(LINK_C)
    exe = os.path.join(tmp, "lk")
    r = subprocess.run(["gcc", "-O2", "-o", exe, src,
                        os.path.join(FW, "link_pack.c"), "-I", FW],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gcc loi:\n" + r.stderr)

    cmd_py = P.pack_cmd(4242, 11, -0.25, 0.5, 4242, 1)
    out = subprocess.run([exe], input=cmd_py.hex() + "\n",
                         capture_output=True, text=True).stdout
    lines = dict()
    for line in out.splitlines():
        k, _, rest = line.partition(" ")
        lines[k] = rest

    bad = 0
    n, _, hx = lines["STATE"].partition(" ")
    c_state = bytes.fromhex(hx)
    py_state = P.pack_state(1234, 5678, (1.25, -2.5, 0.75), 0.3125, -0.125,
                            0.625, (0.25, 0.875),
                            P.F_CLIFF_R | P.F_REFLEX, (-0.5, 0.75))
    if c_state != py_state:
        bad += 1
        print("  FAIL goi STATE lech:")
        print("    C     :", c_state.hex())
        print("    Python:", py_state.hex())
    else:
        print("  ok   goi STATE trung tung byte (%s byte)" % n)

    n, _, hx = lines["SCAN"].partition(" ")
    c_scan = bytes.fromhex(hx)
    py_scan = P.pack_scan(7, 8, [0.0, 0.123, 3.4567, 8.0, 70.0], 0.5, 9)
    if c_scan != py_scan:
        bad += 1
        print("  FAIL goi SCAN lech:")
        print("    C     :", c_scan.hex())
        print("    Python:", py_scan.hex())
    else:
        print("  ok   goi SCAN trung tung byte (%s byte, co ca cat nguong 65.535 m)" % n)

    ok, ul, ur, ack, fl = lines["CMD"].split()
    if not (ok == "1" and abs(float(ul) + 0.25) < 1e-6 and
            abs(float(ur) - 0.5) < 1e-6 and ack == "4242" and fl == "1"):
        bad += 1
        print("  FAIL C doc goi CMD cua Python sai:", lines["CMD"])
    else:
        print("  ok   C doc dung goi CMD do Python dong")
    if lines["CMDSEQ"].strip() != "0":
        bad += 1
        print("  FAIL C nhan ca lenh tra loi cho goi cu (phai bo di)")
    else:
        print("  ok   C bo lenh tra loi cho goi cam bien cu")
    return bad


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
        dist = 0.5 + 0.35 * (seed % 4)
        off = (-0.3, 0.0, 0.3)[seed % 3]
        mx, my = d.mouth
        a = d.heading + math.pi + off
        rb.reset(mx + dist * math.cos(a), my + dist * math.sin(a),
                 math.atan2(my - (my + dist * math.sin(a)),
                            mx - (mx + dist * math.cos(a))), 1.0)
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
        # `yaw` khop long hon: no den tu khop duong thang, ma Python cong
        # don float32 theo cap con C cong don double tuan tu.
        ok = len(c) == len(py) and all(
            abs(a[0] - b.bearing) < 2e-3 and abs(a[1] - b.dist) < 2e-3 and
            abs(a[2] - b.width) < 2e-3 and abs(a[3] - b.yaw) < 1e-2
            for a, b in zip(c, py))
        if not ok:
            bad += 1
            print("  FAIL canh %d" % seed)
            print("    python:", [(round(x.bearing, 3), round(x.dist, 3)) for x in py])
            print("    C     :", [(round(x[0], 3), round(x[1], 3)) for x in c])
    if bad:
        shutil.rmtree(tmp, ignore_errors=True)
        print("%d/%d canh lech nhau" % (bad, n_scenes))
        return 1
    print("  ok   dock_detect.c khop dock_detector.py tren %d canh" % n_scenes)
    bad += check_link(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        return 1
    print("5/5 dat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
