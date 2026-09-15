"""Robot gia: chay mo phong nhung noi chuyen y het robot that qua UDP.

    python3 -m link.fake_robot --realtime

Dung de thu toan bo duong di (dong goi -> wifi -> bo nao -> lenh -> banh xe)
khi chua co phan cung. Neu duong nay chay dung o day thi phan con lai chi la
thay ham doc cam bien gia bang ham doc cam bien that.

Lop phan xa an toan o day duoc viet DUNG NHU tren ESP32 se lam, de con thu
duoc no: cam bien vuc keu thi tu lui, mat lenh qua lau thi tu dung.
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from link import protocol as P            # noqa: E402
from sim.env import CarEnv, EnvConfig     # noqa: E402

CMD_TIMEOUT_S = 0.15    # khong co lenh lau hon ngan nay -> dung banh
REFLEX_BACK = 0.6       # ga lui khi cam bien vuc keu


def safety_reflex(cliff_f, cliff_r, v, ul, ur):
    """Phan xa chay TREN ROBOT, khong qua wifi.

    Tu luc cam bien vuc keu den luc tam xe qua mep chi ~290 ms, tru 120 ms
    phanh con 170 ms du dia. Mot cu nghen wifi an het chung do. Nen quyet
    dinh nay phai nam ngay tren ESP32, bat ke bo nao dang nghi gi.
    """
    if cliff_f and (ul + ur) > 0.0:
        return -REFLEX_BACK, -REFLEX_BACK, True
    if cliff_r and (ul + ur) < 0.0:
        return REFLEX_BACK, REFLEX_BACK, True
    return ul, ur, False


class FakeRobot:
    def __init__(self, brain_addr, stage=3, seed=0, port=0):
        self.env = CarEnv(EnvConfig(stage=stage, max_steps=10 ** 9))
        self.obs = self.env.reset(seed)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(CMD_TIMEOUT_S)
        self.brain = brain_addr
        self.seq = 0
        self.t0 = time.time()
        self.u_applied = (0.0, 0.0)   # ga thuc su da vao dong co buoc truoc
        self.n_timeout = 0
        self.n_reflex = 0
        self.rtt = []

    def _ms(self):
        return int((time.time() - self.t0) * 1000.0) & 0xFFFFFFFF

    def send_sensors(self):
        e = self.env
        r = e.robot
        s = e.sensors
        self.seq += 1
        if e.lidar.scans_new:
            self.sock.sendto(P.pack_scan(self.seq, self._ms(),
                                         e.lidar.r.tolist(),
                                         e.lidar.scan_theta, self._ms()),
                             self.brain)
        flags = 0
        if s.cliff_front > 0.5:
            flags |= P.F_CLIFF_F
        if s.cliff_rear > 0.5:
            flags |= P.F_CLIFF_R
        if r.bumped:
            flags |= P.F_BUMP
        if r.charging:
            flags |= P.F_CHARGING
        flags |= getattr(self, "last_flags", 0)
        self.last_flags = 0
        self.sock.sendto(P.pack_state(self.seq, self._ms(),
                                      (r.ox, r.oy, r.oth), r.v, r.omega,
                                      r.battery, s.ir, flags,
                                      self.u_applied), self.brain)

    def wait_cmd(self):
        t = time.time()
        while True:
            try:
                buf, _ = self.sock.recvfrom(256)
            except socket.timeout:
                self.n_timeout += 1
                return 0.0, 0.0          # watchdog: mat lenh thi dung
            p = P.parse(buf)
            if p is None or p[0] != P.T_CMD:
                continue
            c = P.unpack_cmd(p[3])
            if c["ack_seq"] != self.seq:
                continue                 # lenh tra loi cho goi cu, bo di
            self.rtt.append(time.time() - t)
            return c["u"]

    def step(self):
        self.send_sensors()
        ul, ur = self.wait_cmd()
        s = self.env.sensors
        ul, ur, hit = safety_reflex(s.cliff_front > 0.5, s.cliff_rear > 0.5,
                                    self.env.robot.v, ul, ur)
        self.n_reflex += hit
        if hit:
            self.last_flags = P.F_REFLEX
        self.u_applied = (ul, ur)
        self.obs, _, done, info = self.env.step((ul, ur))
        return done, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=P.PORT)
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=0, help="0 = chay mai")
    ap.add_argument("--realtime", action="store_true",
                    help="chay dung 20 Hz nhu ngoai doi")
    a = ap.parse_args()

    rb = FakeRobot((a.brain, a.port), stage=a.stage, seed=a.seed)
    print("robot gia -> bo nao %s:%d" % (a.brain, a.port))
    dt = rb.env.cfg.dt
    n = 0
    t_next = time.time()
    t_rep = time.time()
    while a.steps == 0 or n < a.steps:
        done, info = rb.step()
        n += 1
        if done:
            print("  het tap (%s), bat dau lai" % (
                "roi ban" if info.get("fell") else
                "het pin" if info.get("flat") else "?"))
            rb.obs = rb.env.reset(a.seed + n)
        if a.realtime:
            t_next += dt
            d = t_next - time.time()
            if d > 0:
                time.sleep(d)
            else:
                t_next = time.time()
        if time.time() - t_rep >= 5.0:
            ms = 1000.0 * sum(rb.rtt) / max(1, len(rb.rtt))
            print("  %d buoc | di %.1f m | pin %.0f%% | khu hoi %.1f ms"
                  " | mat lenh %d | phan xa vuc %d"
                  % (n, rb.env.distance, 100 * rb.env.robot.battery, ms,
                     rb.n_timeout, rb.n_reflex))
            rb.rtt = []
            t_rep = time.time()


if __name__ == "__main__":
    main()
