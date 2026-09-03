"""Kiểm thử hình học mặt trụ trải phẳng và các biên dạng cắt ống."""

import math
import unittest

from pipecut import geom2d as g
from pipecut import shapes
from pipecut.section import BoxSection, RoundSection


class TestGeom2D(unittest.TestCase):
    def test_do_dai_va_dien_tich(self):
        sq = g.close_loop([(0, 0), (10, 0), (10, 10), (0, 10)])
        self.assertAlmostEqual(g.polyline_length(sq), 40.0)
        self.assertAlmostEqual(g.signed_area(sq), 100.0)  # dương = ngược kim đồng hồ

    def test_bu_duong_ben_trai_la_phia_trong_voi_duong_nguoc_kim_dong_ho(self):
        sq = g.close_loop([(0, 0), (10, 0), (10, 10), (0, 10)])
        inside = g.offset(sq, 1.0, closed=True)
        self.assertAlmostEqual(min(p[0] for p in inside), 1.0, places=6)
        self.assertAlmostEqual(max(p[0] for p in inside), 9.0, places=6)
        outside = g.offset(sq, -1.0, closed=True)
        self.assertAlmostEqual(min(p[0] for p in outside), -1.0, places=6)

    def test_lay_mau_thich_nghi_dat_dung_sai(self):
        r = 25.0
        pts = g.adaptive_sample(lambda t: (r * math.cos(t), r * math.sin(t)),
                                0, 2 * math.pi, 0.01)
        # chu vi đa giác nội tiếp phải rất sát chu vi thật
        self.assertAlmostEqual(g.polyline_length(pts), 2 * math.pi * r, delta=0.05)
        # mọi điểm phải nằm trên đường tròn
        for p in pts:
            self.assertAlmostEqual(math.hypot(*p), r, places=6)
        # sai số dây cung của mọi đoạn phải nhỏ hơn dung sai
        for a, b in zip(pts, pts[1:]):
            sagitta = r - math.sqrt(max(0.0, r * r - (g.dist(a, b) / 2) ** 2))
            self.assertLessEqual(sagitta, 0.011)

    def test_rut_gon_giu_hinh_dang_trong_dung_sai(self):
        pts = g.adaptive_sample(lambda t: (t, 5 * math.sin(t / 5)), 0, 100, 0.01)
        simple = g.rdp(pts, 0.05)
        self.assertLess(len(simple), len(pts))
        for p in pts:  # mọi điểm gốc vẫn nằm sát đường đã rút gọn
            d = min(_point_seg_dist(p, a, b) for a, b in zip(simple, simple[1:]))
            self.assertLessEqual(d, 0.06)

    def test_gop_doan_ngan(self):
        pts = [(i * 0.05, 0.0) for i in range(100)]
        out = g.enforce_min_segment(pts, 0.5)
        for a, b in zip(out, out[1:]):
            self.assertGreaterEqual(g.dist(a, b), 0.49)
        self.assertEqual(out[-1], pts[-1])  # luôn giữ điểm cuối

    def test_chia_doan_dai(self):
        out = g.resample_max_step([(0, 0), (100, 0)], 8.0)
        self.assertTrue(all(g.dist(a, b) <= 8.0 + 1e-9 for a, b in zip(out, out[1:])))

    def test_bo_goc_lam_ngan_chu_vi_dung_cong_thuc(self):
        sq = g.close_loop([(0, 0), (20, 0), (20, 20), (0, 20)])
        r = 4.0
        out = g.round_corners(sq, r, closed=True, tolerance=0.005)
        expected = 4 * (20 - 2 * r) + 2 * math.pi * r
        self.assertAlmostEqual(g.polyline_length(g.close_loop(out)), expected, delta=0.05)

    def test_cat_bo_tai_tu_giao(self):
        # đường có một "tai" tự cắt
        pts = [(0, 0), (10, 0), (10, 10), (5, -5), (0, 10)]
        out = g.remove_self_intersections(pts)
        self.assertLess(len(out), len(pts) + 2)
        for i in range(len(out) - 1):
            for j in range(i + 2, len(out) - 1):
                hit = g.segment_intersection(out[i], out[i + 1], out[j], out[j + 1])
                if hit and not (i == 0 and j == len(out) - 2):
                    self.assertLess(abs(hit[1]) + abs(1 - hit[2]), 1e-6)


def _point_seg_dist(p, a, b):
    d = g.sub(b, a)
    L = g.norm(d)
    if L < 1e-12:
        return g.dist(p, a)
    t = max(0.0, min(1.0, g.dot(g.sub(p, a), d) / (L * L)))
    return g.dist(p, (a[0] + d[0] * t, a[1] + d[1] * t))


class TestShapes(unittest.TestCase):
    R = 30.0
    SEC = RoundSection(60.0)

    def test_cat_vuong_goc_la_duong_thang_tren_mat_trai(self):
        c = shapes.plane_cut(self.SEC, 100.0, 0.0)
        self.assertTrue(all(abs(p[0] - 100.0) < 1e-9 for p in c.points))
        self.assertAlmostEqual(c.points[-1][1] - c.points[0][1], 2 * math.pi * self.R, places=6)

    def test_cat_vat_cho_bien_do_bang_R_tan_alpha(self):
        for angle in (15.0, 30.0, 45.0, 60.0):
            c = shapes.plane_cut(self.SEC, 0.0, angle)
            amp = max(p[0] for p in c.points)
            self.assertAlmostEqual(amp, self.R * math.tan(math.radians(angle)), delta=0.02)

    def test_mieng_ca_dung_cong_thuc_giao_tuyen(self):
        r, R = 30.0, 50.0
        c = shapes.saddle_cut(RoundSection(2 * r), R, 90.0, x_ref=0.0, reference="axis")
        # kiểm tra từng điểm thoả phương trình mặt trụ ống chính
        for u, v in c.points:
            th = v / r
            y = r * math.sin(th)
            z = -u  # u = -t, với beta = 90 độ thì t chính là toạ độ z
            self.assertAlmostEqual(math.hypot(y, z), R, delta=1e-6)
        depth = max(p[0] for p in c.points) - min(p[0] for p in c.points)
        self.assertAlmostEqual(depth, R - math.sqrt(R * R - r * r), delta=0.01)

    def test_mieng_ca_goc_xien_va_lech_tam(self):
        r, R, beta, e = 20.0, 60.0, 55.0, 8.0
        c = shapes.saddle_cut(RoundSection(2 * r), R, beta, offset=e, x_ref=0.0, reference="axis")
        sb, cb = math.sin(math.radians(beta)), math.cos(math.radians(beta))
        for u, v in c.points:
            th = v / r
            t = -u
            # dựng lại điểm 3D rồi kiểm tra nó nằm trên mặt ống chính
            py = r * math.sin(th) + e
            pz = t * sb + r * math.cos(th) * cb
            self.assertAlmostEqual(math.hypot(py, pz), R, delta=1e-6)

    def test_mieng_ca_bao_loi_khi_khong_kha_thi(self):
        with self.assertRaises(shapes.ShapeError):
            shapes.saddle_cut(RoundSection(80.0), 30.0, 90.0)          # nhánh to hơn ống chính
        with self.assertRaises(shapes.ShapeError):
            shapes.saddle_cut(RoundSection(40.0), 30.0, 90.0, offset=25.0)  # lệch tâm quá lớn

    def test_lo_xuyen_dung_kich_thuoc(self):
        d = 30.0
        c = shapes.pierced_hole(self.SEC, d, 90.0, x_center=50.0)
        us = [p[0] for p in c.points]
        vs = [p[1] for p in c.points]
        self.assertAlmostEqual(max(us) - min(us), d, delta=0.02)   # dài dọc trục = đường kính
        half = math.degrees(math.asin(d / 2 / self.R))
        self.assertAlmostEqual(math.degrees(max(vs) / self.R), half, delta=0.05)
        self.assertAlmostEqual(math.degrees(min(vs) / self.R), -half, delta=0.05)

    def test_lo_xuyen_nam_tren_ca_hai_mat_tru(self):
        R, d, beta = 40.0, 30.0, 60.0
        c = shapes.pierced_hole(RoundSection(2 * R), d, beta, x_center=0.0)
        r = d / 2
        sb, cb = math.sin(math.radians(beta)), math.cos(math.radians(beta))
        for u, v in c.points:
            phi = v / R
            py, pz = R * math.sin(phi), R * math.cos(phi)
            self.assertAlmostEqual(math.hypot(py, pz), R, places=6)  # trên ống chính
            # và cũng nằm trên mặt ống nhánh: khoảng cách tới trục nhánh = r
            px = u
            # trục nhánh: qua gốc, phương (cos b, 0, sin b)
            t = px * cb + pz * sb
            dx, dy, dz = px - t * cb, py, pz - t * sb
            self.assertAlmostEqual(math.sqrt(dx * dx + dy * dy + dz * dz), r, delta=1e-6)

    def test_lo_qua_lon_bi_tu_choi(self):
        with self.assertRaises(shapes.ShapeError):
            shapes.pierced_hole(self.SEC, 2 * self.R + 1.0)

    def test_ranh_dung_chu_vi(self):
        c = shapes.slot(self.SEC, 100.0, 0.0, 40.0, angular_width_deg=60.0, corner_radius=0.0)
        w = math.radians(60.0) * self.R
        self.assertAlmostEqual(g.polyline_length(c.points), 2 * (40.0 + w), delta=0.01)

    def test_xoan_oc_dung_do_dai(self):
        c = shapes.helix(self.SEC, 0.0, 100.0, 2.0)
        expect = math.hypot(100.0, 2 * 2 * math.pi * self.R)
        self.assertAlmostEqual(g.polyline_length(c.points), expect, delta=0.01)


if __name__ == "__main__":
    unittest.main()
