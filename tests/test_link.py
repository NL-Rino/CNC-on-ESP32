"""Thu toan bo duong di: robot -> UDP -> bo nao tren laptop -> lenh -> banh xe.

Chay: python3 tests/test_link.py

Cai dang gia nhat o day la phep doi chieu QUAN SAT: vector 46 so ma bo nao
dung tren laptop phai khop voi vector ma mo phong tu tinh lay. Neu khong khop
thi bo nao se hanh xu khac han luc huan luyen, ma kieu loi do gan nhu khong
the tim ra khi da ra phan cung.
"""
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from link import protocol as P            # noqa: E402
from link.brain_server import Brain, serve  # noqa: E402
from link.fake_robot import FakeRobot, safety_reflex  # noqa: E402
from sim.perception import OBS_NAMES      # noqa: E402

BRAIN = "brains/nha_v0.npz"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Link:
    """Dung mot cap bo nao + robot gia noi voi nhau qua UDP that."""

    def __init__(self, stage=3, seed=1):
        self.port = _free_port()
        self.brain = Brain(os.path.join(ROOT, BRAIN))
        self.stopping = False
        self.th = threading.Thread(
            target=serve, kwargs=dict(host="127.0.0.1", port=self.port,
                                      verbose=False, brain=self.brain,
                                      stop=lambda: self.stopping),
            daemon=True)
        self.th.start()
        time.sleep(0.2)
        self.rb = FakeRobot(("127.0.0.1", self.port), stage=stage, seed=seed)

    def close(self):
        self.stopping = True
        self.th.join(timeout=2.0)


def test_bao_duoc_tiep_diem_sac_qua_duong_truyen():
    """Xe vua bat nguon trong hoc phai bao duoc dieu do len, khong thi bo nao
    tren laptop mat luon manh moi de nhat ve cho tram sac."""
    ir0 = [[0, 0, 0], [0, 0, 0]]
    st = P.pack_state(1, 1, (0.0, 0.0, 0.0), 0, 0, 1.0, ir0,
                      P.F_ON_DOCK | P.F_CHARGING)
    d = P.unpack_state(P.parse(st)[3])
    assert d["on_dock"] and d["charging"]
    st = P.pack_state(1, 1, (0.0, 0.0, 0.0), 0, 0, 1.0, ir0, P.F_ON_DOCK)
    d = P.unpack_state(P.parse(st)[3])
    assert d["on_dock"] and not d["charging"], \
        "cham tiep diem ma chua co dien van phai bao duoc"


def test_goi_tin_dong_goi_va_mo_ra_khop_nhau():
    st = P.pack_state(5, 99, (1.5, -2.5, 0.75), 0.31, -0.12, 0.66,
                      [[0.1, 0.2, 0.3], [0.9, 0.8, 0.7]],
                      P.F_CLIFF_R | P.F_CHARGING)
    kind, seq, t, body = P.parse(st)
    d = P.unpack_state(body)
    assert kind == P.T_STATE and seq == 5 and t == 99
    assert abs(d["odo"][0] - 1.5) < 1e-6 and abs(d["odo"][2] - 0.75) < 1e-6
    assert d["cliff"] == (0.0, 1.0) and d["charging"] and not d["bumped"]

    rr = [0.0, 0.123, 3.4567, 8.0]
    kind, _, _, body = P.parse(P.pack_scan(1, 2, rr, 0.5, 3))
    sc = P.unpack_scan(body)
    assert sc["n"] == 4
    got = [v * 0.001 for v in sc["mm"]]
    for a, b in zip(rr, got):
        assert abs(a - b) <= 0.0006, (a, b)     # sai so lam tron 1 mm

    assert P.parse(b"") is None
    assert P.parse(b"XX" + bytes(20)) is None   # sai magic
    assert P.parse(b"CB\x63" + bytes(20)) is None   # sai phien ban


def test_quan_sat_tren_laptop_khop_voi_mo_phong():
    lk = Link(stage=3, seed=4)
    try:
        worst = 0.0
        worst_name = ""
        n = 0
        for _ in range(220):
            truoc = list(lk.rb.obs)          # quan sat mo phong TRUOC buoc nay
            lk.rb.step()
            tren_nao = lk.brain.last_obs
            if tren_nao is None:
                continue
            if n < 3:
                # Ba buoc dau bo qua: mo phong da chay mot lan update luc
                # reset, con bo nao tren laptop thi chua - hai ben lech pha
                # dung o cho tinh do THAY DOI cuong do hong ngoai.
                n += 1
                continue
            d = np.abs(np.array(truoc) - np.array(tren_nao))
            i = int(d.argmax())
            if d[i] > worst:
                worst, worst_name = float(d[i]), OBS_NAMES[i]
            n += 1
        assert n > 150, "chi doi chieu duoc %d buoc" % n
        # Mo phong cung lam tron ve milimet nhu Camsense that, nen hai ben
        # phai khop gan nhu tuyet doi - chi con sai so lam tron float32.
        assert worst < 1e-4, "lech %.5f o truong %s" % (worst, worst_name)
        print("     doi chieu %d buoc, lech lon nhat %.2e (%s)"
              % (n, worst, worst_name or "-"))
    finally:
        lk.close()


def test_robot_chay_that_va_do_tre_duong_truyen():
    lk = Link(stage=3, seed=7)
    try:
        for _ in range(240):
            lk.rb.step()
        # Do DUONG TRUYEN, khong do chat luong bo nao: xe xuat phat tu trong
        # hoc sac va bo nao dang nuoi do con chua biet lui ra, nen quang
        # duong di duoc khong noi len dieu gi ve duong truyen ca.
        assert lk.rb.n_timeout <= 3, "mat lenh %d lan" % lk.rb.n_timeout
        assert lk.brain.n_steps > 150, \
            "bo nao chi xu ly duoc %d buoc" % lk.brain.n_steps
        assert lk.brain.last_obs is not None and \
            len(lk.brain.last_obs) == len(OBS_NAMES), "quan sat khong toi noi"
        ms = 1000.0 * sum(lk.rb.rtt) / max(1, len(lk.rb.rtt))
        assert ms < 20.0, "khu hoi %.1f ms" % ms
        print("     di %.1f m, khu hoi %.2f ms qua loopback" % (lk.rb.env.distance, ms))
    finally:
        lk.close()


def test_mat_lien_lac_thi_robot_tu_dung():
    """Bo nao im lang -> banh phai dung, khong duoc chay tiep theo lenh cu."""
    lk = Link(stage=3, seed=9)
    try:
        for _ in range(40):
            lk.rb.step()
        lk.stopping = True                  # cat bo nao giua chung
        lk.th.join(timeout=2.0)
        t0 = time.time()
        for _ in range(6):
            lk.rb.step()
        assert lk.rb.n_timeout >= 5, "khong phat hien mat lenh"
        v = abs(lk.rb.env.robot.v)
        assert v < 0.12, "mat lien lac roi ma van chay %.2f m/s" % v
        print("     cat song %.1f s -> %d lan mat lenh, toc do con %.3f m/s"
              % (time.time() - t0, lk.rb.n_timeout, v))
    finally:
        lk.close()


def test_phan_xa_vuc_khong_di_qua_wifi():
    """Phan xa phai chay tren robot: chi con ~170 ms du dia sau khi tru
    quang duong phanh, mot cu nghen wifi la het."""
    ul, ur, hit = safety_reflex(True, False, 0.4, 0.8, 0.8)
    assert hit and ul < 0 and ur < 0, "cam bien vuc truoc keu ma van tien"
    ul, ur, hit = safety_reflex(False, True, -0.3, -0.7, -0.7)
    assert hit and ul > 0 and ur > 0, "cam bien vuc sau keu ma van lui"
    ul, ur, hit = safety_reflex(False, False, 0.3, 0.5, 0.4)
    assert not hit and (ul, ur) == (0.5, 0.4), "khong co vuc ma van can thiep"
    ul, ur, hit = safety_reflex(True, False, 0.0, -0.5, -0.5)
    assert not hit, "dang lui khoi vuc thi dung chan"


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for f in fns:
        try:
            f()
            print("  ok   %s" % f.__name__)
        except Exception as e:                        # noqa: BLE001
            bad += 1
            print("  LOI  %s: %r" % (f.__name__, e))
    print("%d/%d dat" % (len(fns) - bad, len(fns)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
