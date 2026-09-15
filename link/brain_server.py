"""Bo nao chay tren laptop, dieu khien robot qua wifi.

    python3 -m link.brain_server --policy brains/car_bay_v1.npz

Robot giu nhip: cu moi goi STATE gui len (20 Hz) thi may tinh tra ve mot goi
CMD ngay. Khong can dong bo dong ho, khong can may tinh biet gio cua robot.

Cai gi KHONG nam o day: lop phan xa an toan. No phai nam tren ESP32, vi
khoang tu luc cam bien vuc keu den luc xe roi khoi ban chi ~290 ms, tru 120 ms
phanh con 170 ms - mot cu nghen wifi la het. Xem firmware/robot_link.ino.
"""
import argparse
import os
import socket
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from link import protocol as P            # noqa: E402
from sim.perception import Perception     # noqa: E402
from sim.robot import RobotSpec           # noqa: E402
from train.policy import GRUPolicy        # noqa: E402

SCAN_STALE_S = 0.6      # vong quet cu hon ngan nay thi khong dam lai nua
LINK_GAP_S = 1.0        # mat lien lac lau hon ngan nay -> quen het, lam lai


class Brain:
    """Bo nao + trang thai suy dien. Tach rieng de test goi thang duoc."""

    def __init__(self, policy_path, spec=None, battery_low=0.40,
                 ir_handshake=30):
        self.pol, self.meta = GRUPolicy.load(policy_path)
        spec = spec or RobotSpec()
        self.per = Perception(battery_low, ir_handshake,
                              spec.v_max, spec.wheel_base)
        self.reset()

    def reset(self, battery=1.0):
        self.pol.reset()
        self.per.reset(battery)
        self.scan = None            # (ranges m, goc luc quet)
        self.scan_t = 0.0
        self.scan_fresh = False
        self.last_obs = None
        self.n_steps = 0

    def on_scan(self, pkt, now):
        self.scan = (np.array(pkt["mm"], dtype=np.float32) * 0.001,
                     float(pkt["scan_theta"]))
        self.scan_t = now
        self.scan_fresh = True

    def act(self, st, now):
        """st = ket qua unpack_state. Tra ve (ga_trai, ga_phai, ly_do)."""
        if self.scan is None:
            return 0.0, 0.0, "chua co vong quet nao"
        if now - self.scan_t > SCAN_STALE_S:
            return 0.0, 0.0, "vong quet cu %.2f s" % (now - self.scan_t)

        ranges, scan_theta = self.scan
        # Lay ga THUC SU da chay chu khong phai ga minh vua yeu cau: phan xa
        # an toan tren robot va watchdog deu co the da doi no.
        self.per.prev_u = [float(st["u_applied"][0]), float(st["u_applied"][1])]
        obs = self.per.update(
            ranges=ranges, scan_theta=scan_theta, scans_new=self.scan_fresh,
            odo=st["odo"], cliff=st["cliff"], ir=st["ir"],
            battery=st["battery"], v=st["v"], omega=st["omega"],
            bumped=st["bumped"], charging=st["charging"])
        self.scan_fresh = False

        self.last_obs = obs
        ul, ur = self.pol.act(obs)
        if not (np.isfinite(ul) and np.isfinite(ur)):
            return 0.0, 0.0, "bo nao tra ve NaN"
        ul = max(-1.0, min(1.0, float(ul)))
        ur = max(-1.0, min(1.0, float(ur)))
        self.n_steps += 1
        return ul, ur, ""


def serve(policy_path=None, host="0.0.0.0", port=P.PORT, verbose=True,
          brain=None, stop=None):
    """`brain` va `stop` de test goi vao duoc; chay that thi khong can."""
    brain = brain or Brain(policy_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(0.5)
    if verbose:
        print("bo nao %d tham so (gen %s) dang nghe %s:%d"
              % (brain.pol.n_params, brain.meta.get("gen", "?"), host, port))

    seq = 0
    last_state = 0.0
    if stop is None:
        stop = lambda: False        # noqa: E731
    lat = []
    t_report = time.time()
    n_state = n_scan = n_lost = 0
    while not stop():
        try:
            buf, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        now = time.time()
        p = P.parse(buf)
        if p is None:
            continue
        kind, rseq, t_ms, body = p

        if kind == P.T_SCAN:
            pkt = P.unpack_scan(body)
            if pkt is not None:
                brain.on_scan(pkt, now)
                n_scan += 1
            continue
        if kind != P.T_STATE:
            continue

        if last_state and now - last_state > LINK_GAP_S:
            # Mat lien lac lau: tri nho GRU va tri nho vi tri tram deu da cu.
            # Giu lai con te hon vut di - xe se hanh dong theo mot the gioi
            # khong con ton tai.
            n_lost += 1
            st0 = P.unpack_state(body)
            brain.reset(st0["battery"])
            if verbose:
                print("  mat lien lac %.1f s -> quen va lam lai"
                      % (now - last_state))
        last_state = now
        n_state += 1

        st = P.unpack_state(body)
        ul, ur, why = brain.act(st, now)
        if why and verbose and n_state % 20 == 1:
            print("  dung yen:", why)
        seq += 1
        sock.sendto(P.pack_cmd(seq, int(now * 1000) & 0xFFFFFFFF,
                               ul, ur, rseq), addr)
        lat.append(time.time() - now)

        if verbose and now - t_report >= 5.0:
            ms = 1000.0 * sum(lat) / max(1, len(lat))
            print("  %5.1f Hz STATE | %4.1f Hz SCAN | nao xu ly %.2f ms"
                  " | mat lien lac %d lan | pin %.0f%%"
                  % (n_state / (now - t_report), n_scan / (now - t_report),
                     ms, n_lost, 100 * st["battery"]))
            n_state = n_scan = 0
            lat = []
            t_report = now
    sock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="brains/car_bay_v1.npz")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=P.PORT)
    a = ap.parse_args()
    try:
        serve(a.policy, a.host, a.port)
    except KeyboardInterrupt:
        print("\ndung.")


if __name__ == "__main__":
    main()
