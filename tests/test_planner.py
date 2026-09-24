"""Bộ lập kế hoạch chuyển động: phải khớp đúng cách FluidNC/Grbl tăng giảm tốc."""

import math
import unittest

from pipecut.config import MachineProfile
from pipecut.planner import plan, read_blocks


def profile(accel=200.0, rate=20000.0):
    p = MachineProfile()
    for a in p.axes:
        a.accel = accel
        a.max_rate = rate
    return p


def run(p, *lines):
    return plan(p, ["G1 X0 Y0 Z0 A0 F6000"] + list(lines))


class TestTrapezoid(unittest.TestCase):
    """Các trường hợp tính tay được: v = 100 mm/s, a = 200 mm/s²."""

    def setUp(self):
        self.p = profile()

    def test_mot_doan_thang(self):
        # tăng tốc 25 mm (0,5 s) + chạy đều 50 mm (0,5 s) + hãm 25 mm (0,5 s)
        self.assertAlmostEqual(run(self.p, "G1 X100").total, 1.5, places=9)

    def test_doan_ngan_khong_kip_cham_toc_do(self):
        # 20 mm: tam giác vận tốc, đỉnh sqrt(a*L) = 63,2 mm/s
        self.assertAlmostEqual(run(self.p, "G1 X20").total,
                               2 * math.sqrt(20 / 200.0), places=9)

    def test_hai_khuc_thang_hang_khong_dung(self):
        self.assertAlmostEqual(run(self.p, "G1 X50", "G1 X100").total, 1.5, places=9)

    def test_quay_dau_phai_dung_han(self):
        r = run(self.p, "G1 X50", "G1 X0")
        self.assertAlmostEqual(r.total, 2.0, places=9)
        self.assertEqual(r.full_stops, 1)

    def test_goc_vuong_gan_nhu_dung(self):
        r = run(self.p, "G1 X50", "G1 X50 Y50")
        blocks = read_blocks(self.p, ["G1 X0 Y0 Z0 A0 F6000", "G1 X50", "G1 X50 Y50"])
        # junction deviation 0,01 mm: v² = a·δ·s/(1-s), a lấy theo hướng điểm nối
        s = math.sin(math.radians(45.0))
        a_j = 200.0 / s
        want = math.sqrt(a_j * 0.01 * s / (1 - s))
        self.assertAlmostEqual(blocks[1].v_junction, want, places=6)
        self.assertLess(r.total, 2.0)
        self.assertGreater(r.total, 1.95)

    def test_lenh_dong_bo_bat_dung_han(self):
        # M5 giữa hai khúc thẳng hàng: bộ đệm chạy cạn, phải dừng
        self.assertAlmostEqual(run(self.p, "G1 X50", "M5", "G1 X100").total, 2.0, places=9)
        self.assertAlmostEqual(run(self.p, "G1 X50", "G4 P0.5", "G1 X100").total, 2.5, places=9)

    def test_bo_dem_huu_han_lam_cham_chuoi_doan_ngan(self):
        lines = [f"G1 X{0.1 * i:.1f}" for i in range(1, 401)]
        short = run(self.p, *lines).total
        self.p.motion.planner_blocks = 5000
        unlimited = run(self.p, *lines).total
        # như một đoạn liền 40 mm: không đủ dài để chạm 100 mm/s -> tam giác
        self.assertAlmostEqual(unlimited, 2 * math.sqrt(40.0 / 200.0), places=6)
        self.assertGreater(short, unlimited + 0.2)

    def test_toc_do_bi_truc_cham_nhat_kim(self):
        p = profile()
        p.axis_by_letter("A").max_rate = 600.0      # 10 độ/s
        # G1 A90 F6000: trục A chỉ chạy được 10 độ/s -> ~9 s chứ không phải 0,9
        r = run(p, "G1 A90")
        self.assertGreater(r.total, 9.0)


class TestCategories(unittest.TestCase):
    def test_phan_loai_chuyen_dong(self):
        p = profile()
        r = plan(p, ["G0 X0 Y0 Z0 A0", "G0 Z5", "G0 Y50", "G0 Z3", "M3", "G4 P0.5",
                     "G1 Z1 F600", "G1 Y80 F1200", "M5"])
        for cat in ("lift", "travel", "plunge", "cut", "dwell"):
            self.assertGreater(r.by_category[cat], 0.0, cat)
        self.assertAlmostEqual(sum(r.by_category.values()), r.total, places=9)
        self.assertAlmostEqual(sum(r.line_times.values()), r.total, places=9)


if __name__ == "__main__":
    unittest.main()
