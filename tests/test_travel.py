"""Chạy không kiểu nhảy ếch: nhấc vừa đủ, cung trơn, không bao giờ va phôi."""

import glob
import math
import random
import unittest

from pipecut.config import MachineProfile, ROLE_BEVEL
from pipecut.gcode import build_program
from pipecut.jobs import Job
from pipecut.section import make_section
from pipecut.travel import SurfaceEnvelope, TravelPlanner


def exact_top(poly, theta, lo, hi):
    """Điểm kim loại cao nhất có x trong [lo, hi] - tính thẳng trên đa giác, chậm."""
    a = math.radians(theta)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(cx * ca - cy * sa, cx * sa + cy * ca) for cx, cy in poly]
    xs = [lo + (hi - lo) * i / 24 for i in range(25)] + [x for x, _ in pts if lo <= x <= hi]
    best = -math.inf
    for x in xs:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            if min(x0, x1) <= x <= max(x0, x1):
                y = y0 if abs(x1 - x0) < 1e-12 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
                best = max(best, y)
    return best


def moves(profile, lines):
    """Đi qua chương trình: (vị trí trước, vị trí sau, nhanh?, mỏ bật?) cho mỗi lệnh chạy."""
    pos, torch, rapid = {}, False, True
    for raw in lines:
        words = raw.split("(")[0].split()
        if not words:
            continue
        target = dict(pos)
        moved = False
        for w in words:
            k, v = w[0].upper(), w[1:]
            if k == "G" and v in ("0", "00"):
                rapid = True
            elif k == "G" and v in ("1", "01"):
                rapid = False
            elif k == "M" and v in ("3", "4"):
                torch = True
            elif k == "M" and v == "5":
                torch = False
            elif k in "XYZABC" and k in profile.letters:
                target[k] = float(v)
                moved = True
        if moved:
            yield dict(pos), target, rapid, torch
            pos = target


def hops(profile, lines):
    """Từng lần chạy không giữa hai đường cắt: danh sách điểm từ lúc tắt tới lúc mồi."""
    out, cur, started = [], None, False
    for a, b, rapid, torch in moves(profile, lines):
        if torch:
            if cur and len(cur) > 1:
                out.append(cur)
            cur, started = None, True
            continue
        if not started:
            continue                      # lượt chạy đầu tiên: chưa biết mỏ ở đâu
        if cur is None:
            cur = [a]
        cur.append(b)
    return out


class TestEnvelope(unittest.TestCase):
    def test_khong_bao_gio_thap_hon_that(self):
        """Mọi làm tròn đều nghiêng về phía cao hơn: sai thì nhấc thừa, không nhấc thiếu."""
        rnd = random.Random(11)
        for args in (("square", 60, 50, 50, 0, 3), ("rect", 60, 80, 40, 0, 3),
                     ("square", 60, 40, 40, 2, 2), ("round", 60, 50, 50, 0, 3)):
            sec = make_section(*args)
            env = SurfaceEnvelope(sec)
            poly = sec.outline(600)
            for _ in range(60):
                th = rnd.uniform(-400, 400)
                c = rnd.uniform(-40, 40)
                w = rnd.uniform(0.01, 20)
                truth = exact_top(poly, th, c - w / 2, c + w / 2)
                if truth == -math.inf:
                    continue
                got = env.top(th, c - w / 2, c + w / 2)
                self.assertGreaterEqual(got, truth - 1e-3, (args, th, c, w))
                self.assertLess(got - truth, 2.5, (args, th, c, w))


class TestHopShape(unittest.TestCase):
    def _hops(self, profile_path, job):
        p = MachineProfile.load(profile_path)
        prog = build_program(p, job.build_toolpath(p)[0])
        return p, hops(p, prog.stream_lines()), prog

    def _job(self, op="hole"):
        """Ba lỗ: hai lỗ cùng mặt cách nhau 100 mm, lỗ thứ ba phải xoay sang mặt khác.

        ``hole`` chỉ dùng cho ống tròn; ống hộp dùng ``circle`` (lỗ tròn trên mặt).
        """
        job = Job(optimize_order=False)
        job.add(op, diameter=12.0, x=60.0, theta=0.0)
        job.add(op, diameter=12.0, x=160.0, theta=0.0)
        job.add(op, diameter=12.0, x=160.0, theta=90.0 if op == "circle" else 120.0)
        return job

    def test_ong_tron_chi_nhac_vua_du(self):
        """Mặt ống tròn chỗ nào cũng cao như nhau: không nhấc lên 20 mm nữa."""
        p, hs, _ = self._hops("config/machine_round.json", self._job())
        self.assertEqual(len(hs), 2)
        for h in hs:
            top = max(q["Z"] for q in h)
            self.assertAlmostEqual(top, p.process.travel_height, delta=0.05)
            self.assertLess(top, p.process.safe_height)

    def test_roi_diem_cat_theo_phuong_thang_dung(self):
        """Không kéo lê béc qua xỉ vừa cắt: đoạn đầu gần như thẳng đứng."""
        p, hs, _ = self._hops("config/machine_round.json", self._job())
        for h in hs:
            a, b = h[0], h[1]
            dz = b["Z"] - a["Z"]
            lateral = math.sqrt(sum((b[k] - a[k]) ** 2 for k in b if k != "Z" and k in a))
            self.assertGreater(dz, 3.0 * lateral)
            self.assertGreater(dz, 0.0)

    def test_ha_xuong_dung_do_cao_moi(self):
        p, hs, _ = self._hops("config/machine_round.json", self._job())
        for h in hs:
            self.assertAlmostEqual(h[-1]["Z"], p.process.pierce_height, places=3)

    def test_ong_hop_xoay_qua_goc_thi_nhac_cao_hon(self):
        """Góc ống hộp nhô lên khi xoay qua: tự nhấc đủ cao để lướt qua."""
        p, hs, _ = self._hops("config/machine_box.json", self._job("circle"))
        sec = p.pipe.section()
        corner_rise = sec.max_radius - sec.reference_height
        rotating = [h for h in hs if abs(h[-1]["A"] - h[0]["A"]) > 60]
        self.assertTrue(rotating)
        for h in rotating:
            self.assertGreaterEqual(max(q["Z"] for q in h),
                                    corner_rise + p.process.travel_height - 1e-6)

    def test_duong_dau_tien_van_len_cao_an_toan(self):
        p = MachineProfile.load("config/machine_round.json")
        prog = build_program(p, self._job().build_toolpath(p)[0])
        first = next(b for a, b, rapid, torch in moves(p, prog.stream_lines()) if "Z" in b)
        self.assertAlmostEqual(first["Z"], p.process.safe_height, places=3)

    def test_travel_height_0_la_kieu_cu(self):
        p = MachineProfile.load("config/machine_round.json")
        p.process.travel_height = 0.0
        prog = build_program(p, self._job().build_toolpath(p)[0])
        for h in hops(p, prog.stream_lines()):
            self.assertAlmostEqual(max(q["Z"] for q in h), p.process.safe_height, places=3)

    def test_tat_nhay_ech_thi_nhac_thang_ha_thang_o_do_cao_vua_du(self):
        p = MachineProfile.load("config/machine_round.json")
        p.motion.leapfrog = False
        prog = build_program(p, self._job().build_toolpath(p)[0])
        for h in hops(p, prog.stream_lines()):
            self.assertEqual(len(h), 4)          # điểm tắt + lên + ngang + xuống
            self.assertEqual(set(h[1]) - {"Z"}, set(h[1]) - {"Z"})
            self.assertAlmostEqual(h[1]["Z"], p.process.travel_height, places=3)
            self.assertEqual({k: h[1][k] for k in h[1] if k != "Z"},
                             {k: h[0][k] for k in h[0] if k != "Z"})

    def test_dau_cat_dang_nghieng_thi_giu_do_cao_an_toan(self):
        p = MachineProfile.load("config/machine_bevel.json")
        tp = TravelPlanner(p)
        bev = p.axis(ROLE_BEVEL)
        a = {"X": 0.0, "Y": 10.0, "Z": 1.6, "A": 0.0, bev.letter: 20.0}
        b = {"X": 0.0, "Y": 60.0, "Z": 3.8, "A": 0.0, bev.letter: 0.0}
        self.assertEqual(tp.hop(a, b), [])     # người gọi dùng cao độ an toàn


class TestSafetyNet(unittest.TestCase):
    """Cung vòng tự nó đã an toàn trong mọi ca thử; phần kiểm là lưới bảo hiểm.
    Ở đây kiểm riêng lưới đó: bắt được đường đâm vào phôi, và khi không có cung
    nào qua được thì quay về nhấc thẳng - hạ thẳng."""

    def setUp(self):
        self.p = MachineProfile.load("config/machine_box.json")
        self.tp = TravelPlanner(self.p)
        sec = self.tp.section
        ref = sec.reference_height
        ct0, ct1 = sec.contact_at(0.0), sec.contact_at(sec.perimeter / 4)
        cut, pierce = self.p.process.cut_height, self.p.process.pierce_height
        # mặt trên -> mặt bên: phải xoay 90 độ, góc ống nhô lên giữa đường
        self.p0 = {"X": ct0.cross, "Y": 50.0, "A": ct0.theta, "Z": ct0.height - ref + cut}
        self.p1 = {"X": ct1.cross, "Y": 50.0, "A": ct1.theta, "Z": ct1.height - ref + pierce}

    def test_bat_duoc_duong_thap_cat_ngang_qua_goc(self):
        D = math.sqrt(sum((self.p1[k] - self.p0[k]) ** 2 for k in "XYA"))
        low = [(D, self.p0["Z"])]                     # đi ngang sát mặt, không nhấc
        self.assertFalse(self.tp._clear(low, self.p0, self.p1, D, 1.0))
        high = [(0.0, 20.0), (D, 20.0)]
        self.assertTrue(self.tp._clear(high, self.p0, self.p1, D, 1.0))

    def test_khong_cung_nao_qua_duoc_thi_nhac_thang(self):
        self.tp._clear = lambda *a, **k: False
        path = self.tp.hop(self.p0, self.p1)
        self.assertEqual(len(path), 3)
        up, across, down = path
        self.assertEqual({k: up[k] for k in "XYA"}, {k: self.p0[k] for k in "XYA"})
        self.assertEqual({k: across[k] for k in "XYA"}, {k: self.p1[k] for k in "XYA"})
        self.assertAlmostEqual(up["Z"], across["Z"])
        self.assertEqual(down, self.p1)
        sec = self.tp.section
        self.assertGreaterEqual(up["Z"], sec.max_radius - sec.reference_height
                                + self.p.process.travel_height - 1e-6)


class TestNoCollision(unittest.TestCase):
    """Soát ngay trên G-code xuất ra: không điểm nào dọc đường chạy không lại
    gần kim loại hơn lúc mỏ đang cắt ở hai đầu, hay hơn độ cao cắt."""

    def _check(self, profile_path, job_path):
        p = MachineProfile.load(profile_path)
        job = Job.load(job_path)
        prog = build_program(p, job.build_toolpath(p)[0])
        tp = TravelPlanner(p)
        count = 0

        def clear(q):
            return tp.work_z(q) - tp.surface_top(tp._theta(q), tp._cross(q))

        for h in hops(p, prog.stream_lines()):
            floor = min(clear(h[0]), clear(h[-1]), p.process.cut_height) - 1e-6
            for a, b in zip(h, h[1:]):
                for i in range(9):
                    f = i / 8
                    q = {k: a[k] + (b[k] - a[k]) * f for k in b if k in a}
                    self.assertGreaterEqual(clear(q), floor,
                                            f"{profile_path} {job_path}: {q}")
                    count += 1
        return count

    def test_moi_ho_so_moi_cong_viec(self):
        total = 0
        for mf in ("config/machine_round.json", "config/machine_box.json",
                   "config/machine_default.json", "config/machine_box_index.json"):
            for jf in sorted(glob.glob("examples/*.json")):
                total += self._check(mf, jf)
        self.assertGreater(total, 1000)


if __name__ == "__main__":
    unittest.main()
