"""Kiểm thử động học, xử lý đường chạy dao và sinh G-code."""

import math
import re
import unittest

from pipecut import shapes
from pipecut.section import BoxSection, RoundSection
from pipecut.config import (AxisSpec, MachineProfile, ROLE_ALONG, ROLE_BEVEL,
                            ROLE_CROSS, ROLE_ROTARY)
from pipecut.gcode import build_program, fmt, strip_gcode_comment
from pipecut.jobs import Job
from pipecut.kinematics import Kinematics
from pipecut.pathops import compute_bevels, process_contour
from pipecut.toolpath import BEVEL_FOLLOW, CutPoint, Toolpath


class TestFeedCompensation(unittest.TestCase):
    """Yêu cầu cốt lõi: tốc độ mũi cắt trên bề mặt phải không đổi."""

    def setUp(self):
        self.p = MachineProfile()
        self.p.pipe.outer_diameter = 60.0
        self.kin = Kinematics(self.p)

    def cp(self, x: float, theta: float) -> CutPoint:
        """Điểm cắt trên ống tròn: toạ độ cung suy từ góc quay."""
        r = self.p.pipe.outer_diameter / 2.0
        return CutPoint(x=x, v=math.radians(theta) * r, theta=theta)

    def _surface_speed(self, a, b, target):
        feed, l_real, l_mach = self.kin.feed_for(a, b, target)
        minutes = l_mach / feed
        return l_real / minutes

    def test_toc_do_be_mat_khong_doi_moi_ti_le_phoi_hop_truc(self):
        target = 1600.0
        cases = [
            (self.cp(0, 0), self.cp(10, 0)),        # chỉ trục dọc
            (self.cp(0, 0), self.cp(0, 45)),        # chỉ trục xoay
            (self.cp(0, 0), self.cp(10, 45)),       # phối hợp
            (self.cp(0, 0), self.cp(1, 120)),       # xoay là chính
            (self.cp(0, 0), self.cp(50, 2)),        # dọc là chính
        ]
        for a, b in cases:
            self.assertAlmostEqual(self._surface_speed(a, b, target), target, delta=0.5)

    def test_toc_do_be_mat_khong_doi_tren_toan_bo_duong_mieng_ca(self):
        c = shapes.saddle_cut(RoundSection(60.0), 50.0, 90.0, x_ref=200.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        target = self.p.process.cut_feed
        for a, b in zip(ps.points, ps.points[1:]):
            speed = self._surface_speed(a, b, target)
            self.assertAlmostEqual(speed, target, delta=1.0)

    def test_khong_bu_thi_toc_do_sai_lech_lon(self):
        """Chứng minh vì sao phải bù: dùng F cố định thì tốc độ lệch hàng loạt."""
        R = self.p.pipe.radius
        a, b = self.cp(0, 0), self.cp(0, 45)
        l_real = math.radians(45) * R          # 23.6 mm trên bề mặt
        l_mach = 45.0                          # nhưng FluidNC thấy 45 "mm"
        naive_speed = 1600.0 * l_real / l_mach  # tốc độ bề mặt thực nếu ghi F1600
        self.assertLess(naive_speed, 900.0)     # chậm hơn 44% so với yêu cầu
        self.assertAlmostEqual(self._surface_speed(a, b, 1600.0), 1600.0, delta=0.5)

    def test_kep_theo_toc_do_toi_da_cua_tung_truc(self):
        self.p.axis(ROLE_ROTARY).max_rate = 600.0   # trục xoay rất chậm
        kin = Kinematics(self.p)
        feed, l_real, l_mach = kin.feed_for(self.cp(0, 0), self.cp(0, 90), 3000.0)
        self.assertLessEqual(feed, 600.0 + 1e-6)

    def test_khong_vuot_tran_va_san_toc_do(self):
        self.p.motion.max_feed = 2000.0
        kin = Kinematics(self.p)
        feed, _, _ = kin.feed_for(self.cp(0, 0), self.cp(0, 180), 5000.0)
        self.assertLessEqual(feed, 2000.0)

    def test_quay_duong_ngan_nhat_chi_dung_khi_chay_khong(self):
        kin = Kinematics(self.p)
        self.assertAlmostEqual(kin.shortest_rotary(350.0, 10.0), 370.0)
        self.assertAlmostEqual(kin.shortest_rotary(-5.0, 350.0), -10.0)
        self.assertAlmostEqual(kin.shortest_rotary(0.0, 90.0), 90.0)

    def test_go_cuon_day_goc(self):
        kin = Kinematics(self.p)
        out = kin.unwrap_series([350.0, 10.0, 30.0, 350.0])
        for a, b in zip(out, out[1:]):
            self.assertLess(abs(b - a), 180.0)


class TestBevel(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile()
        cross = self.p.axis(ROLE_CROSS)
        cross.role = ROLE_BEVEL          # dùng trục ngang làm trục vát để kiểm thử
        cross.max_rate = 1800.0
        cross.max_travel = 0.0
        self.bevel_letter = cross.letter
        self.p.motion.max_bevel = 60.0

    def test_cat_vat_cho_goc_truc_vat_dung_bang_goc_mat_phang(self):
        for angle in (20.0, 30.0, 45.0):
            c = shapes.plane_cut(RoundSection(60.0), 0.0, angle)
            ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
            peak = max(abs(q.bevel) for q in ps.points)
            self.assertAlmostEqual(peak, angle, delta=1.0)

    def test_mieng_ca_cho_goc_truc_vat_theo_do_doc_duong_cat(self):
        r, R = 30.0, 50.0
        c = shapes.saddle_cut(RoundSection(2 * r), R, 90.0, x_ref=200.0)
        ps = process_contour(c, RoundSection(2 * r), self.p.motion, self.p.process)
        # đỉnh lý thuyết: max của atan(r sin th cos th / sqrt(R^2 - r^2 sin^2 th))
        best = max(math.degrees(math.atan(r * math.sin(t) * math.cos(t) /
                                          math.sqrt(R * R - (r * math.sin(t)) ** 2)))
                   for t in [i * math.pi / 2000 for i in range(2001)])
        peak = max(abs(q.bevel) for q in ps.points)
        self.assertAlmostEqual(peak, best, delta=1.0)

    def test_goc_vat_bi_kep_theo_gioi_han(self):
        self.p.motion.max_bevel = 15.0
        c = shapes.plane_cut(RoundSection(60.0), 0.0, 50.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        self.assertLessEqual(max(abs(q.bevel) for q in ps.points), 15.0 + 1e-9)

    def test_doan_vao_dao_khong_lam_lech_goc_vat(self):
        c = shapes.saddle_cut(RoundSection(60.0), 50.0, 90.0, x_ref=200.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        self.assertGreater(ps.lead_in_count, 0)
        # điểm vào dao phải mang đúng góc vát của điểm cắt đầu tiên
        first_cut = ps.points[ps.lead_in_count]
        for q in ps.points[:ps.lead_in_count]:
            self.assertAlmostEqual(q.bevel, first_cut.bevel, places=6)

    def test_bu_toa_do_khi_dau_cat_nghieng(self):
        self.p.motion.bevel_pivot = 50.0
        kin = Kinematics(self.p)
        vals = kin.axis_values(CutPoint(x=100.0, v=0.0, theta=0.0, bevel=30.0), z=2.0)
        along = self.p.letter(ROLE_ALONG)
        self.assertAlmostEqual(vals[along], 100.0 + 50.0 * math.sin(math.radians(30)), places=6)
        self.assertAlmostEqual(vals["Z"], 2.0 - 50.0 * (1 - math.cos(math.radians(30))), places=6)


class TestPathOps(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile()

    def test_bu_kerf_thu_nho_lo_dung_nua_be_rong(self):
        R, d = 30.0, 30.0
        self.p.process.kerf = 2.0
        c = shapes.pierced_hole(RoundSection(2 * R), d, 90.0, x_center=50.0)
        ps = process_contour(c, RoundSection(2 * R), self.p.motion, self.p.process)
        cut = ps.points[ps.lead_in_count:len(ps.points) - ps.lead_out_count]
        span = max(q.x for q in cut) - min(q.x for q in cut)
        self.assertAlmostEqual(span, d - self.p.process.kerf, delta=0.15)

    def test_bu_kerf_cat_dut_lech_ve_phia_phe_lieu(self):
        self.p.process.kerf = 2.0
        c = shapes.plane_cut(RoundSection(60.0), 100.0, 0.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        cut = ps.points[ps.lead_in_count:]
        for q in cut:
            self.assertAlmostEqual(q.x, 101.0, delta=0.02)  # dịch +kerf/2 về đầu tự do

    def test_dieu_tiet_mat_do_diem(self):
        c = shapes.pierced_hole(RoundSection(60.0), 40.0, 90.0, x_center=100.0)
        self.p.motion.min_segment = 1.0
        self.p.motion.max_segment = 4.0
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        pts = [(q.x, q.v) for q in ps.points]
        for a, b in zip(pts, pts[1:]):
            d = math.dist(a, b)
            self.assertLessEqual(d, 4.0 + 1e-6)

    def test_goc_quay_lien_tuc_khong_nhay_360(self):
        c = shapes.plane_cut(RoundSection(60.0), 100.0, 40.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        for a, b in zip(ps.points, ps.points[1:]):
            self.assertLess(abs(b.theta - a.theta), 30.0)

    def test_chay_vuot_lam_duong_cat_dai_hon_chu_vi(self):
        self.p.process.overcut = 3.0
        c = shapes.plane_cut(RoundSection(60.0), 100.0, 0.0)
        ps = process_contour(c, self.p.pipe.section(), self.p.motion, self.p.process)
        sweep = max(q.theta for q in ps.points) - min(q.theta for q in ps.points)
        self.assertGreater(sweep, 360.0)
        self.assertAlmostEqual(sweep, 360.0 + math.degrees(3.0 / 30.0), delta=0.5)


class TestGcode(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile()
        job = Job(name="kiem-thu")
        job.add("hole", diameter=25.0, x=80.0)
        job.add("cutoff", x=200.0, angle=30.0)
        self.tp, _ = job.build_toolpath(self.p)
        self.prog = build_program(self.p, self.tp, "kiem-thu")

    def test_dinh_dang_so_gon(self):
        self.assertEqual(fmt(3.140000), "3.14")
        self.assertEqual(fmt(-0.0001), "0")
        self.assertEqual(fmt(100.0), "100")

    def test_bo_chu_thich(self):
        self.assertEqual(strip_gcode_comment("G1 X10 (di chuyen) Y5 ; ghi chu"), "G1 X10 Y5")

    def test_cau_truc_chuong_trinh(self):
        text = self.prog.text()
        self.assertIn("G21", text)
        self.assertIn("G90", text)
        self.assertTrue(text.rstrip().endswith("M30"))
        # mỗi lần bật nguồn cắt phải có đúng một lần tắt tương ứng
        lines = [l.split(" ")[0] for l in self.prog.stream_lines()]
        self.assertEqual(lines.count("M3"), 2)
        self.assertEqual(lines.count("M5"), 3)  # 2 lần cắt + 1 lần ở phần kết

    def test_moi_luon_o_cao_do_moi_roi_moi_ha_xuong_cao_do_cat(self):
        lines = self.prog.stream_lines()
        i = next(i for i, l in enumerate(lines) if l.startswith("M3"))
        before = " ".join(lines[max(0, i - 3):i])
        self.assertIn(f"Z{fmt(self.p.process.pierce_height)}", before)
        after = " ".join(lines[i:i + 4])
        self.assertIn(f"Z{fmt(self.p.process.cut_height)}", after)

    def test_xuat_modal_khong_lap_lai_tu_lenh(self):
        along = self.p.letter(ROLE_ALONG)
        rotary = self.p.letter(ROLE_ROTARY)
        lines = [l for l in self.prog.stream_lines()
                 if l.startswith(("G1", along, rotary))]
        # G1 chỉ xuất hiện ở đầu mỗi chuỗi cắt, không lặp lại từng dòng
        self.assertGreater(sum(1 for l in lines if not l.startswith("G1")), len(lines) * 0.9)
        # F chỉ ghi lại khi tốc độ đổi quá ngưỡng, không phải mọi dòng
        self.assertLess(sum(1 for l in lines if "F" in l), len(lines) * 0.8)

    def test_thong_ke_hop_ly(self):
        s = self.prog.stats
        self.assertEqual(s.pierces, 2)
        self.assertGreater(s.cut_length, 100.0)
        self.assertGreater(s.estimated_time, 1.0)
        self.assertIn(self.p.letter(ROLE_ALONG), s.bounds)

    def test_canh_bao_khi_vuot_hanh_trinh(self):
        p = MachineProfile()
        p.axis(ROLE_ALONG).max_travel = 100.0
        job = Job()
        job.add("cutoff", x=500.0)
        tp, _ = job.build_toolpath(p)
        prog = build_program(p, tp)
        self.assertTrue(any("vượt hành trình" in w for w in prog.stats.warnings))

    def test_bien_dang_hong_khong_lam_chet_ca_chuong_trinh(self):
        p = MachineProfile()
        job = Job()
        job.add("saddle", main_diameter=10.0)   # ống chính nhỏ hơn ống nhánh -> lỗi
        job.add("cutoff", x=150.0)
        tp, warns = job.build_toolpath(p)
        self.assertEqual(len(warns), 1)
        prog = build_program(p, tp)
        self.assertGreater(prog.stats.pierces, 0)   # nguyên công còn lại vẫn chạy


if __name__ == "__main__":
    unittest.main()
