"""Kiểm thử tiết diện phôi và việc cắt ống hộp."""

import math
import re
import unittest

from pipecut import shapes
from pipecut.config import MachineProfile, ROLE_ALONG, ROLE_CROSS, ROLE_ROTARY
from pipecut.gcode import build_program
from pipecut.jobs import Job
from pipecut.section import BoxSection, RoundSection, SectionError, make_section


class TestSectionGeometry(unittest.TestCase):
    def test_chu_vi_ong_tron(self):
        s = RoundSection(60.0)
        self.assertAlmostEqual(s.perimeter, math.pi * 60.0, places=9)

    def test_chu_vi_ong_hop_bang_canh_thang_cong_bon_cung_goc(self):
        s = BoxSection(50.0, 50.0, corner_radius=4.0)
        expect = 4 * (50.0 - 2 * 4.0) + 2 * math.pi * 4.0
        self.assertAlmostEqual(s.perimeter, expect, places=9)

    def test_moi_diem_deu_nam_dung_tren_bien_ong_hop(self):
        s = BoxSection(60.0, 40.0, corner_radius=5.0)
        for i in range(400):
            x, y = s.point_at(s.perimeter * i / 400)
            dx = max(abs(x) - (s.hx - s.rc), 0.0)
            dy = max(abs(y) - (s.hy - s.rc), 0.0)
            if dx > 1e-9 and dy > 1e-9:                    # trên cung góc
                self.assertAlmostEqual(math.hypot(dx, dy), s.rc, places=9)
            else:                                          # trên mặt phẳng
                self.assertTrue(abs(abs(x) - s.hx) < 1e-9 or abs(abs(y) - s.hy) < 1e-9)

    def test_goc_luon_bat_buoc_lon_hon_khong(self):
        s = BoxSection(40.0, 40.0, corner_radius=0.0, wall=2.5)
        self.assertAlmostEqual(s.rc, 5.0)          # tự lấy 2 lần chiều dày
        s2 = BoxSection(40.0, 40.0, corner_radius=100.0)
        self.assertLessEqual(s2.rc, 20.0)          # không vượt nửa cạnh

    def test_tu_the_cat_tren_mat_phang_giu_nguyen_goc_quay(self):
        """Trên một mặt phẳng, trục A đứng yên còn trục X chạy dọc mặt."""
        s = BoxSection(50.0, 50.0, corner_radius=4.0)
        flat_half = s.hx - s.rc
        for t in (0.0, 5.0, 10.0, flat_half):
            c = s.contact_at(t)
            self.assertAlmostEqual(c.theta, 0.0, places=6)     # không xoay
            self.assertAlmostEqual(c.cross, t, places=6)       # X = vị trí trên mặt
            self.assertAlmostEqual(c.height, s.hy, places=6)   # Z không đổi
            self.assertAlmostEqual(s.surface_z(t), 0.0, places=6)

    def test_qua_goc_luon_thi_xoay_va_nhac_truc_z(self):
        s = BoxSection(50.0, 50.0, corner_radius=4.0)
        v_corner = (s.hx - s.rc) + math.pi * s.rc / 4.0        # giữa cung góc
        c = s.contact_at(v_corner)
        self.assertAlmostEqual(c.theta, 45.0, places=6)
        self.assertAlmostEqual(c.cross, 0.0, places=6)         # đỉnh góc nằm giữa
        k = math.hypot(s.hx - s.rc, s.hy - s.rc)
        self.assertAlmostEqual(c.height, k + s.rc, places=6)   # cao hơn mặt phẳng
        self.assertGreater(s.surface_z(v_corner), 5.0)

    def test_ong_tron_khong_dung_toi_truc_ngang(self):
        s = RoundSection(60.0)
        for i in range(50):
            c = s.contact_at(s.perimeter * i / 50)
            self.assertAlmostEqual(c.cross, 0.0, places=9)
            self.assertAlmostEqual(c.height, 30.0, places=9)
            self.assertAlmostEqual(s.surface_z(c.theta), 0.0, places=9)

    def test_dinh_vi_theo_huong_nhin_roi_vao_giua_mat(self):
        """'Lỗ ở 90 độ' phải nằm giữa mặt bên, không phải ở mép."""
        for s in (RoundSection(60.0), BoxSection(50.0, 50.0, corner_radius=4.0),
                  BoxSection(80.0, 40.0, corner_radius=5.0)):
            for theta in (0.0, 90.0, 180.0, 270.0):
                v = s.s_of_theta(theta)
                x, y = s.point_at(v)
                self.assertAlmostEqual(math.degrees(math.atan2(x, y)) % 360.0,
                                       theta % 360.0, delta=0.2)

    def test_ban_do_nguoc_khop_voi_ban_do_xuoi(self):
        for s in (RoundSection(60.0), BoxSection(50.0, 50.0, corner_radius=4.0),
                  BoxSection(80.0, 40.0, corner_radius=8.0)):
            for i in range(200):
                v = s.perimeter * i / 200
                c = s.contact_at(v)
                self.assertAlmostEqual(s.s_of_contact(c.theta, c.cross), v, delta=1e-6)

    def test_lech_ngang_tren_ong_tron_lam_lech_diem_cham(self):
        s = RoundSection(60.0)
        v = s.s_of_contact(0.0, 15.0)
        self.assertAlmostEqual(v, math.radians(30.0) * 30.0, delta=1e-6)

    def test_tao_tiet_dien_theo_ten(self):
        self.assertIsInstance(make_section("round", diameter=50), RoundSection)
        self.assertIsInstance(make_section("square", width=40), BoxSection)
        with self.assertRaises(SectionError):
            make_section("hinh-thang")
        with self.assertRaises(SectionError):
            make_section("square", width=0)


class TestBoxCutting(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile()
        self.p.pipe.shape = "square"
        self.p.pipe.width = 50.0
        self.p.pipe.wall_thickness = 3.0
        self.p.pipe.length = 500.0
        cross = self.p.axis(ROLE_CROSS)
        cross.min_travel, cross.max_travel = -200.0, 200.0
        self.section = self.p.pipe.section()

    def _program(self, *ops):
        job = Job()
        for kind, kw in ops:
            job.add(kind, **kw)
        tp, warns = job.build_toolpath(self.p)
        self.assertEqual(warns, [])
        return build_program(self.p, tp)

    def test_cat_dut_ong_hop_dung_hanh_trinh_bon_truc(self):
        prog = self._program(("cutoff", dict(x=250.0, angle=0.0)))
        b = prog.stats.bounds
        flat = self.section.hx - self.section.rc
        self.assertAlmostEqual(b["X"][0], -flat, delta=0.05)   # chạy hết mặt
        self.assertAlmostEqual(b["X"][1], flat, delta=0.05)
        self.assertAlmostEqual(b["A"][1] - b["A"][0], 360.0, delta=2.0)
        self.assertFalse([w for w in prog.stats.warnings if "hành trình" in w])

    def test_khe_ho_mo_cat_luon_dung_bang_cao_do_cat(self):
        """Bài kiểm tra quan trọng nhất: mỏ cắt không được cắm vào phôi.

        Dựng lại đúng vị trí mũi cắt từ G-code, kể cả **giữa hai điểm** (nơi
        máy nội suy thẳng), rồi đo khe hở tới bề mặt phôi.
        """
        prog = self._program(("cutoff", dict(x=250.0, angle=15.0)))
        sec = self.section
        ref = sec.reference_height
        z_cut = self.p.process.cut_height
        letters = {"X": self.p.letter(ROLE_CROSS), "A": self.p.letter(ROLE_ROTARY)}
        states = []
        cur = {"X": 0.0, "A": 0.0, "Z": 0.0}
        cutting = False
        for line in prog.stream_lines():
            if line.startswith("M3"):
                cutting = True
            elif line.startswith("M5"):
                cutting = False
            for axis in ("X", "Z", "A"):
                m = re.search(axis + r"(-?[\d.]+)", line)
                if m:
                    cur[axis] = float(m.group(1))
            if cutting and line.startswith(("G1", "X", "A", "Z")):
                states.append(dict(cur))

        self.assertGreater(len(states), 20)
        worst = 0.0
        for a, b in zip(states, states[1:]):
            for f in (0.0, 0.25, 0.5, 0.75, 1.0):      # cả điểm giữa hai lệnh
                th = a["A"] + (b["A"] - a["A"]) * f
                xc = a["X"] + (b["X"] - a["X"]) * f
                z = a["Z"] + (b["Z"] - a["Z"]) * f
                if z > z_cut + 1.0:                     # đang nâng lên, bỏ qua
                    continue
                gap = (ref + z) - sec.surface_height(th, xc)
                worst = max(worst, abs(gap - z_cut))
        self.assertLess(worst, 0.15, f"khe hở lệch tới {worst:.3f} mm so với cao độ cắt")

    def test_ong_tron_khong_sinh_lenh_truc_ngang(self):
        self.p.pipe.shape = "round"
        self.p.pipe.outer_diameter = 60.0
        prog = self._program(("cutoff", dict(x=250.0, angle=20.0)))
        xs = prog.stats.bounds.get(self.p.letter(ROLE_CROSS), (0.0, 0.0))
        self.assertAlmostEqual(xs[0], 0.0, places=6)
        self.assertAlmostEqual(xs[1], 0.0, places=6)

    def test_toc_do_be_mat_dung_tren_mat_phang_va_bi_kep_o_goc_luon(self):
        """Trên mặt phẳng phải đúng tốc độ đặt; ở góc lượn thì bị giới hạn
        bởi tốc độ tối đa của trục xoay - đó là giới hạn cơ khí, không phải lỗi.
        """
        from pipecut.kinematics import Kinematics
        from pipecut.pathops import process_contour
        kin = Kinematics(self.p)
        c = shapes.plane_cut(self.section, 250.0, 0.0)
        ps = process_contour(c, self.section, self.p.motion, self.p.process)
        target = self.p.process.cut_feed
        z = self.p.process.cut_height
        on_flat = []
        for a, b in zip(ps.points, ps.points[1:]):
            speed = kin.achievable_surface_speed(a, b, target, z, z)
            self.assertLessEqual(speed, target + 1.0)     # không bao giờ nhanh hơn
            if abs(b.theta - a.theta) < 1e-6:             # đoạn nằm trên mặt phẳng
                on_flat.append(speed)
        self.assertTrue(on_flat)
        for speed in on_flat:
            self.assertAlmostEqual(speed, target, delta=1.0)

    def test_canh_bao_khi_toc_do_bi_tut_o_goc_luon(self):
        prog = self._program(("cutoff", dict(x=250.0, angle=0.0)))
        self.assertTrue(any("tốc độ cắt tụt" in w for w in prog.stats.warnings),
                        prog.stats.warnings)

    def test_che_do_toc_do_deu_giu_toc_do_be_mat_khong_doi(self):
        """Bật 'tốc độ đều' thì cả đường chạy ở một tốc độ bề mặt duy nhất -
        đổi lại chậm hơn, nhưng vết cắt đồng đều từ mặt phẳng sang góc lượn."""
        from pipecut.kinematics import Kinematics
        from pipecut.pathops import process_contour
        kin = Kinematics(self.p)
        c = shapes.plane_cut(self.section, 250.0, 0.0)
        ps = process_contour(c, self.section, self.p.motion, self.p.process)
        z = self.p.process.cut_height
        speeds = [kin.achievable_surface_speed(a, b, self.p.process.cut_feed, z, z)
                  for a, b in zip(ps.points, ps.points[1:])]
        slowest = min(speeds)
        self.assertLess(slowest, self.p.process.cut_feed)     # có chỗ bị kẹp
        uniform = [kin.achievable_surface_speed(a, b, slowest, z, z)
                   for a, b in zip(ps.points, ps.points[1:])]
        for sp in uniform:
            self.assertAlmostEqual(sp, slowest, delta=1.0)    # giờ thì đều tăm tắp
        self.p.motion.uniform_feed = True
        prog = self._program(("cutoff", dict(x=250.0, angle=0.0)))
        self.assertFalse([w for w in prog.stats.warnings if "tốc độ cắt tụt" in w])

    def test_bien_dang_chi_danh_cho_ong_tron_bi_tu_choi(self):
        for kind, kw in (("saddle", dict(main_diameter=114.3)),
                         ("hole", dict(diameter=20.0, x=100.0))):
            job = Job()
            job.add(kind, **kw)
            _tp, warns = job.build_toolpath(self.p)
            self.assertEqual(len(warns), 1)
            self.assertIn("ống tròn", warns[0])

    def test_ranh_va_bien_dang_phang_van_dung_cho_ong_hop(self):
        prog = self._program(("slot", dict(x=150.0, theta=90.0, length=60.0,
                                           width_deg=40.0, corner=5.0)),
                             ("circle", dict(diameter=20.0, x=250.0, theta=0.0)))
        self.assertEqual(prog.stats.pierces, 2)
        self.assertEqual(prog.stats.warnings, [])   # nằm gọn trên mặt phẳng, không tụt tốc

    def test_them_diem_o_canh_ong_hop(self):
        """Phải có đỉnh đúng tại chỗ chuyển mặt phẳng sang góc lượn."""
        from pipecut.pathops import process_contour
        c = shapes.plane_cut(self.section, 250.0, 0.0)
        ps = process_contour(c, self.section, self.p.motion, self.p.process)
        vs = sorted(q.v % self.section.perimeter for q in ps.points)
        for br in self.section.breakpoints():
            if 0 < br < self.section.perimeter:
                self.assertTrue(any(abs(v - br) < 1e-6 for v in vs),
                                f"thiếu đỉnh tại cạnh v={br:.2f}")


if __name__ == "__main__":
    unittest.main()
