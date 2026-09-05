"""Kiểm thử chế độ dò cạnh trên phôi ảo đã biết trước vị trí.

Cả bộ này chạy không cần phần cứng: máy ảo có một phôi ảo đặt ở vị trí và góc
xoay do bài kiểm thử tự chọn, nên đo xong là **so ngay được với sự thật**.
"""

import math
import unittest

from pipecut import probing, protocol
from pipecut.config import MachineProfile, ROLE_ALONG, ROLE_CROSS, ROLE_RADIAL
from pipecut.probing import ProbeError, ProbeSpec, extent_range, section_extent
from pipecut.simulator import FluidNCSimulator, VirtualPipe


def _profile(shape: str = "square") -> MachineProfile:
    p = MachineProfile()
    p.pipe.shape = shape
    if shape == "round":
        p.pipe.outer_diameter = 60.0
    else:
        p.pipe.width = p.pipe.height = 50.0
        p.pipe.corner_radius = 6.0
    p.pipe.wall_thickness = 3.0
    p.pipe.length = 1000.0
    return p


def _run(profile, routine, truth, start, spec=None):
    """Chạy một quy trình dò trên máy ảo, trả về (kết quả, số lần dò)."""
    letters = [a.letter for a in profile.axes]
    section = profile.pipe.section()
    # tăng hệ số thời gian để bài kiểm thử không phải chờ theo thời gian thật
    sim = FluidNCSimulator(axes="".join(letters), time_scale=5000.0,
                           workpiece=VirtualPipe(section=section,
                                                 length=profile.pipe.length, **truth))
    sim.take_output(1 << 20)
    sim.target = dict(start)
    sim.pos = dict(start)
    result, probes = None, 0
    while True:
        try:
            step = routine.send(result)
        except StopIteration as stop:
            return stop.value, probes
        result = None
        for line in step.lines:
            sim.feed_input((line + "\n").encode())
            for _ in range(50000):
                sim.tick()
                if not sim.queue and sim.state == "Idle":
                    break
        out = sim.take_output(1 << 20).decode()
        if step.probe:
            probes += 1
            for text in out.splitlines():
                parsed = protocol.parse_probe(text, letters)
                if parsed:
                    result = parsed


class TestProbeParsing(unittest.TestCase):
    def test_doc_dong_prb(self):
        r = protocol.parse_probe("[PRB:10.000,20.000,-5.250:1]", list("XYZ"))
        self.assertTrue(r.touched)
        self.assertAlmostEqual(r.get("Z"), -5.25)

    def test_phan_biet_cham_that_voi_do_hut(self):
        hit = protocol.parse_probe("[PRB:0,0,-5:1]", list("XYZ"))
        miss = protocol.parse_probe("[PRB:0,0,-30:0]", list("XYZ"))
        self.assertTrue(hit.touched)
        self.assertFalse(miss.touched)

    def test_bo_qua_dong_khac(self):
        for line in ("ok", "[MSG:hello]", "<Idle|MPos:0,0,0>", ""):
            self.assertIsNone(protocol.parse_probe(line))


class TestVirtualPipe(unittest.TestCase):
    """Phôi ảo phải cho đúng bề ngang theo góc xoay, nếu không đo ra số sai."""

    def test_be_ngang_doi_theo_goc_xoay(self):
        section = _profile().pipe.section()
        for roll, expect in ((0.0, 50.0), (45.0, 65.74)):
            pipe = VirtualPipe(section=section, length=1000.0, roll_deg=roll)
            lo = hi = None
            x = -40.0
            while x <= 40.0:
                if pipe.surface_z(x, 100.0, 0.0) is not None:
                    lo = x if lo is None else lo
                    hi = x
                x += 0.02
            self.assertAlmostEqual(hi - lo, expect, delta=0.1, msg=f"xoay {roll}")

    def test_ngoai_pham_vi_ong_thi_khong_cham(self):
        section = _profile().pipe.section()
        pipe = VirtualPipe(section=section, length=100.0, y_end=20.0)
        self.assertIsNone(pipe.surface_z(0.0, 10.0, 0.0))    # trước đầu ống
        self.assertIsNone(pipe.surface_z(0.0, 200.0, 0.0))   # quá đuôi ống
        self.assertIsNotNone(pipe.surface_z(0.0, 60.0, 0.0))


class TestSectionExtent(unittest.TestCase):
    def test_hop_vuong_ngua_mat_hep_hon_quay_45_do(self):
        section = _profile().pipe.section()
        self.assertAlmostEqual(section_extent(section, 0.0), 50.0, delta=0.1)
        self.assertGreater(section_extent(section, 45.0), 65.0)
        lo, hi = extent_range(section)
        self.assertAlmostEqual(lo, 50.0, delta=0.1)
        self.assertGreater(hi, 65.0)

    def test_ong_tron_be_ngang_khong_doi(self):
        section = _profile("round").pipe.section()
        lo, hi = extent_range(section)
        self.assertAlmostEqual(lo, 60.0, delta=0.1)
        self.assertAlmostEqual(hi, 60.0, delta=0.1)


class TestRoutines(unittest.TestCase):
    START = {"X": 0.0, "Y": 100.0, "Z": 30.0, "A": 0.0}

    def _truth(self, **kw):
        base = dict(x_centre=0.0, y_end=0.0, roll_deg=0.0, z_axis_centre=-40.0)
        base.update(kw)
        return base

    def test_cham_mat_ra_dung_cao_do_mat_phoi(self):
        p = _profile()
        truth = self._truth()
        out, _ = _run(p, probing.probe_surface(p, ProbeSpec(), start=self.START),
                      truth, self.START)
        expect = truth["z_axis_centre"] + p.pipe.section().reference_height
        self.assertAlmostEqual(out.values["Z"], expect, delta=0.2)

    def test_khong_co_phoi_thi_bao_loi_ro_rang(self):
        p = _profile()
        gen = probing.probe_surface(p, ProbeSpec(), start=self.START)
        with self.assertRaises(ProbeError) as ctx:
            _run(p, gen, self._truth(y_end=500.0), self.START)   # phôi ở xa
        self.assertIn("không chạm", str(ctx.exception))

    def test_tim_tam_ra_dung_duong_tam_va_be_rong(self):
        for centre in (0.0, 7.35, -11.2):
            p = _profile()
            start = dict(self.START, X=centre)
            out, _ = _run(p, probing.find_center(p, ProbeSpec(), start=start),
                          self._truth(x_centre=centre), start)
            xl = p.letter(ROLE_CROSS)
            self.assertAlmostEqual(out.values[f"{xl}_tâm"], centre, delta=0.15,
                                   msg=f"tâm {centre}")
            self.assertAlmostEqual(out.values["bề_rộng"], 50.0, delta=0.2)
            self.assertFalse(out.warnings, out.warnings)

    def test_tim_tam_dung_ca_voi_ong_tron(self):
        p = _profile("round")
        out, _ = _run(p, probing.find_center(p, ProbeSpec(), start=self.START),
                      self._truth(), self.START)
        self.assertAlmostEqual(out.values["bề_rộng"], 60.0, delta=0.2)
        self.assertAlmostEqual(out.values[f"{p.letter(ROLE_CROSS)}_tâm"], 0.0,
                               delta=0.15)

    def test_phoi_xoay_lech_thi_bao_dung_goc_lech(self):
        p = _profile()
        out, _ = _run(p, probing.find_center(p, ProbeSpec(), start=self.START),
                      self._truth(roll_deg=6.2), self.START)
        self.assertTrue(out.warnings)
        self.assertIn("xoay lệch", out.warnings[0])

    def test_tim_dau_ong(self):
        for end in (0.0, 12.4, 55.0):
            p = _profile()
            out, _ = _run(p, probing.find_end(p, ProbeSpec(), start=self.START),
                          self._truth(y_end=end), self.START)
            self.assertAlmostEqual(out.values[p.letter(ROLE_ALONG)], end,
                                   delta=0.15, msg=f"đầu ống {end}")

    def test_can_mat_phang_dung_goc_nghieng(self):
        for roll in (3.0, 6.2, -8.5):
            p = _profile()
            out, _ = _run(p, probing.level_face(p, ProbeSpec(), start=self.START),
                          self._truth(roll_deg=roll), self.START)
            self.assertAlmostEqual(out.values["nghiêng_ban_đầu"], roll, delta=0.2,
                                   msg=f"nghiêng {roll}")
            self.assertAlmostEqual(out.values["đã_xoay"], -roll, delta=0.2)
            self.assertLess(abs(out.values["chênh_còn_lại"]), 0.2)

    def test_ong_tron_khong_can_mat_duoc(self):
        p = _profile("round")
        with self.assertRaises(ProbeError):
            _run(p, probing.level_face(p, ProbeSpec(), start=self.START),
                 self._truth(), self.START)

    def test_do_tron_goi_ra_du_bon_goc(self):
        p = _profile()
        truth = self._truth(x_centre=7.35, y_end=12.4, roll_deg=6.2)
        start = dict(self.START, X=7.0)
        out, probes = _run(p, probing.find_all(p, ProbeSpec(), start=start),
                           truth, start)
        xl, yl, zl = (p.letter(ROLE_CROSS), p.letter(ROLE_ALONG),
                      p.letter(ROLE_RADIAL))
        self.assertAlmostEqual(out.values[f"Tìm tâm.{xl}_tâm"], 7.35, delta=0.15)
        self.assertAlmostEqual(out.values[f"Đầu ống.{yl}"], 12.4, delta=0.15)
        self.assertAlmostEqual(out.values["Cân mặt.nghiêng_ban_đầu"], 6.2, delta=0.2)
        # cân mặt chạy TRƯỚC tìm tâm nên bề rộng đo được là bề rộng thật
        self.assertAlmostEqual(out.values["Tìm tâm.bề_rộng"], 50.0, delta=0.3)
        self.assertFalse(out.warnings, out.warnings)
        self.assertEqual(set(out.zero), {xl, yl, zl, p.letter("rotary")})
        self.assertGreater(probes, 20)

    def test_quang_do_khong_du_thi_canh_bao_chu_khong_im_lang(self):
        p = _profile()
        # đủ để chạm mặt (mặt ở Z=-15, mỏ bắt đầu ở Z=30) nhưng không đủ để
        # dò tới mép rộng nhất (cần khoảng 76 mm)
        spec = ProbeSpec(max_depth=55.0)
        out, _ = _run(p, probing.find_center(p, spec, start=self.START),
                      self._truth(), self.START)
        self.assertTrue(any("Quãng dò" in w for w in out.warnings))


class TestProbeSpec(unittest.TestCase):
    def test_soat_thong_so_vo_ly(self):
        self.assertFalse(ProbeSpec().validate())
        self.assertTrue(ProbeSpec(retract=0.0).validate())
        self.assertTrue(ProbeSpec(latch_feed=999.0, seek_feed=100.0).validate())
        self.assertTrue(ProbeSpec(max_depth=0.0).validate())
        self.assertTrue(ProbeSpec(clearance=1.0, retract=5.0).validate())

    def test_luu_va_nap_lai_trong_ho_so_may(self):
        p = _profile()
        p.probe.max_depth = 77.0
        p.probe.tolerance = 0.05
        again = MachineProfile.from_dict(p.to_dict())
        self.assertAlmostEqual(again.probe.max_depth, 77.0)
        self.assertAlmostEqual(again.probe.tolerance, 0.05)



class TestProbeOffset(unittest.TestCase):
    """Que dò riêng đặt cạnh mỏ: gốc phải quy về mũi cắt, không phải đầu que."""

    START = {"X": 0.0, "Y": 100.0, "Z": 30.0, "A": 0.0}

    def _truth(self, **kw):
        base = dict(x_centre=0.0, y_end=0.0, roll_deg=0.0, z_axis_centre=-40.0)
        base.update(kw)
        return base

    def test_que_do_thap_hon_mo_thi_goc_z_du_ra_dung_bay_nhieu(self):
        p = _profile()
        spec = ProbeSpec(probe_below=12.0)
        out, _ = _run(p, probing.probe_surface(p, spec, start=self.START),
                      self._truth(), self.START)
        # que chạm mặt phôi thì mũi cắt còn ở TRÊN mặt 12 mm
        self.assertAlmostEqual(out.zero[p.letter(ROLE_RADIAL)], 12.0, places=6)

    def test_khong_khai_lech_thi_goc_bang_khong(self):
        p = _profile()
        out, _ = _run(p, probing.probe_surface(p, ProbeSpec(), start=self.START),
                      self._truth(), self.START)
        self.assertAlmostEqual(out.zero[p.letter(ROLE_RADIAL)], 0.0, places=6)

    def test_lech_ngang_va_doc_deu_duoc_bu(self):
        p = _profile()
        spec = ProbeSpec(offset_x=-32.0, offset_y=5.0, probe_below=12.0)
        xl, yl = p.letter(ROLE_CROSS), p.letter(ROLE_ALONG)
        centre, _ = _run(p, probing.find_center(p, spec, start=self.START),
                         self._truth(), self.START)
        self.assertAlmostEqual(centre.zero[xl], 32.0, places=6)
        end, _ = _run(p, probing.find_end(p, spec, start=self.START),
                      self._truth(), self.START)
        self.assertAlmostEqual(end.zero[yl], -5.0, places=6)

    def test_do_duoc_van_dung_du_co_lech(self):
        """Khoảng lệch chỉ đổi gốc đặt ra, không đổi số đo."""
        p = _profile()
        truth = self._truth(x_centre=7.35)
        start = dict(self.START, X=7.35)
        a, _ = _run(p, probing.find_center(p, ProbeSpec(), start=start), truth, start)
        b, _ = _run(p, probing.find_center(
            p, ProbeSpec(offset_x=-32.0, probe_below=12.0), start=start), truth, start)
        xl = p.letter(ROLE_CROSS)
        self.assertAlmostEqual(a.values[f"{xl}_tâm"], b.values[f"{xl}_tâm"], places=6)
        self.assertAlmostEqual(a.values["bề_rộng"], b.values["bề_rộng"], places=6)

    def test_truc_xoay_khong_bi_bu_lech(self):
        """Que dò đặt lệch chỗ nào thì góc xoay vẫn thế - không bù gì cả."""
        p = _profile()
        spec = ProbeSpec(offset_x=-32.0, probe_below=12.0)
        out, _ = _run(p, probing.level_face(p, spec, start=self.START),
                      self._truth(roll_deg=5.0), self.START)
        self.assertAlmostEqual(out.zero[p.letter("rotary")], 0.0, places=6)

    def test_soat_thong_so_lech_vo_ly(self):
        self.assertFalse(ProbeSpec(offset_x=-32.0, probe_below=12.0).validate())
        # khai lệch ngang mà quên khai que thấp hơn mỏ -> mỏ đâm phôi trước
        self.assertTrue(ProbeSpec(offset_x=-32.0).validate())
        self.assertTrue(ProbeSpec(probe_below=-1.0).validate())

    def test_luu_va_nap_lai_khoang_lech(self):
        p = _profile()
        p.probe.offset_x = -32.0
        p.probe.probe_below = 12.0
        again = MachineProfile.from_dict(p.to_dict())
        self.assertAlmostEqual(again.probe.offset_x, -32.0)
        self.assertAlmostEqual(again.probe.probe_below, 12.0)
        self.assertTrue(again.probe.has_offset)

if __name__ == "__main__":
    unittest.main()
