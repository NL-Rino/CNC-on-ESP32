"""Kiểm thử bộ diễn giải G-code theo thời gian (dùng cho tab Mô phỏng)."""

import math
import unittest

from pipecut.config import MachineProfile, ROLE_ALONG, ROLE_CROSS, ROLE_ROTARY
from pipecut.gcode import build_program
from pipecut.gsim import Playback
from pipecut.jobs import Job


class TestPlayback(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile()
        self.along = self.p.letter(ROLE_ALONG)
        self.rotary = self.p.letter(ROLE_ROTARY)
        self.cross = self.p.letter(ROLE_CROSS)

    def test_bo_tri_truc_mac_dinh_dung_theo_may(self):
        """Y = ống ra vào, A = xoay, X = ngang, Z = lên xuống."""
        self.assertEqual(self.p.letter(ROLE_ALONG), "Y")
        self.assertEqual(self.p.letter(ROLE_ROTARY), "A")
        self.assertEqual(self.p.letter(ROLE_CROSS), "X")
        self.assertEqual(self.p.letter("radial"), "Z")
        self.assertEqual(self.p.layout, "pipe_moves")

    def test_thoi_gian_doan_cat_dung_bang_quang_duong_chia_toc_do(self):
        pb = Playback(self.p, ["G90", "G21", f"G1 {self.along}120 F600"])
        self.assertAlmostEqual(pb.duration, 120.0 / 600.0 * 60.0, places=6)

    def test_thoi_gian_chay_nhanh_theo_truc_cham_nhat(self):
        ax = self.p.axis(ROLE_ALONG)
        ax.max_rate = 3000.0
        pb = Playback(self.p, ["G90", f"G0 {self.along}150"])
        self.assertAlmostEqual(pb.duration, 150.0 / 3000.0 * 60.0, places=6)

    def test_dung_G4_duoc_tinh_vao_thoi_gian(self):
        pb = Playback(self.p, ["G90", f"G1 {self.along}10 F600", "G4 P1.5"])
        self.assertAlmostEqual(pb.duration, 1.0 + 1.5, places=6)

    def test_noi_suy_vi_tri_theo_thoi_gian(self):
        pb = Playback(self.p, ["G90", f"G1 {self.along}60 F600"])
        half = pb.state_at(pb.duration / 2)
        self.assertAlmostEqual(half.axes[self.along], 30.0, places=3)
        self.assertAlmostEqual(pb.state_at(0.0).axes[self.along], 0.0, places=6)
        self.assertAlmostEqual(pb.state_at(pb.duration).axes[self.along], 60.0, places=6)
        # vượt quá hai đầu thì kẹp lại, không báo lỗi
        self.assertAlmostEqual(pb.state_at(-5.0).axes[self.along], 0.0, places=6)
        self.assertAlmostEqual(pb.state_at(1e6).axes[self.along], 60.0, places=6)

    def test_theo_doi_trang_thai_nguon_cat(self):
        pb = Playback(self.p, ["G90", f"G0 {self.along}10", "M3 S1000",
                               f"G1 {self.along}50 F600", "M5", f"G0 {self.along}0"])
        states = [pb.state_at(m.t0 + m.duration / 2) for m in pb.moves]
        self.assertFalse(states[0].torch)     # trước khi bật
        self.assertTrue(states[1].torch)      # đoạn cắt
        self.assertFalse(states[-1].torch)    # sau khi tắt

    def test_chi_ghi_vet_cat_khi_dang_cat(self):
        pb = Playback(self.p, ["G90", f"G0 {self.along}10", f"G1 {self.along}20 F600",
                               "M3", f"G1 {self.along}60 F600", "M5",
                               f"G0 {self.along}0"])
        self.assertTrue(pb.trace)
        xs = [t.x for t in pb.trace]
        self.assertGreaterEqual(min(xs), 20.0 - 1e-6)   # chỉ đoạn sau khi bật M3
        self.assertLessEqual(max(xs), 60.0 + 1e-6)

    def test_moi_luot_cat_duoc_danh_dau_rieng(self):
        job = Job()
        job.add("hole", diameter=25.0, x=90.0)
        job.add("hole", diameter=25.0, x=90.0, theta=180.0)
        job.add("cutoff", x=200.0)
        tp, _ = job.build_toolpath(self.p)
        pb = Playback(self.p, build_program(self.p, tp).stream_lines())
        starts = [t for t in pb.trace if t.start]
        self.assertEqual(len(starts), 3)   # ba lượt cắt, không nối liền nhau

    def test_vet_cat_khop_voi_duong_chay_dao(self):
        job = Job()
        job.add("hole", diameter=30.0, x=100.0, theta=45.0)
        tp, _ = job.build_toolpath(self.p)
        prog = build_program(self.p, tp)
        pb = Playback(self.p, prog.stream_lines())
        want = prog.passes[0].points
        # vết cắt phải phủ đúng vùng toạ độ của đường chạy dao
        self.assertAlmostEqual(min(t.x for t in pb.trace),
                               min(q.x for q in want), delta=0.5)
        self.assertAlmostEqual(max(t.theta for t in pb.trace),
                               max(q.theta for q in want), delta=1.0)

    def test_mo_cat_lech_ngang_lam_lech_diem_cham(self):
        """Khi trục ngang khác 0, điểm chạm không còn ở vị trí 12 giờ."""
        r = self.p.pipe.radius
        offset = r / 2.0
        pb = Playback(self.p, ["G90", "M3", f"G1 {self.cross}{offset} "
                                            f"{self.along}50 {self.rotary}0 F600"])
        self.assertTrue(pb.trace)
        expected = math.degrees(math.asin(offset / r))
        self.assertAlmostEqual(pb.trace[-1].theta, expected, delta=0.5)

    def test_vet_cat_tang_dan_theo_thoi_gian(self):
        job = Job()
        job.add("cutoff", x=150.0)
        tp, _ = job.build_toolpath(self.p)
        pb = Playback(self.p, build_program(self.p, tp).stream_lines())
        counts = [len(pb.trace_until(pb.duration * f)) for f in (0.0, 0.3, 0.6, 1.0)]
        self.assertEqual(counts[0], 0)
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(counts[-1], len(pb.trace))

    def test_thoi_gian_khop_voi_thong_ke_cua_hau_xu_ly(self):
        job = Job()
        job.add("hole", diameter=25.0, x=80.0)
        job.add("saddle", main_diameter=114.3, x=260.0)
        tp, _ = job.build_toolpath(self.p)
        prog = build_program(self.p, tp)
        pb = Playback(self.p, prog.stream_lines())
        self.assertAlmostEqual(prog.stats.estimated_time, pb.duration, places=6)
        self.assertGreater(pb.cut_time, 0.0)
        self.assertGreater(pb.rapid_time, 0.0)
        self.assertAlmostEqual(pb.cut_time + pb.rapid_time, pb.duration, delta=pb.duration)


if __name__ == "__main__":
    unittest.main()
