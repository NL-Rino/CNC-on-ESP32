"""Thứ tự cắt kiểu máy laser, và mồi lại ở góc ống hộp."""

import unittest

from pipecut.config import MachineProfile
from pipecut.gcode import build_program
from pipecut.jobs import Job, check_order
from pipecut.planner import plan


def nested_job(optimize):
    """Một cây ống 3 chi tiết, nhập kiểu hay gặp: hết lỗ, rồi rãnh, vạch dấu, cắt đứt."""
    job = Job(name="3 chi tiet", optimize_order=optimize)
    for k in range(3):
        base = 60 + 300 * k
        for th in (0, 90, 180, 270):
            job.add("hole", diameter=12.0, x=base + 30, theta=th)
            job.add("hole", diameter=12.0, x=base + 210, theta=(th + 45) % 360)
    for k in range(3):
        job.add("slot", x=60 + 300 * k + 120, theta=180.0, length=40.0, width_deg=30.0)
    for k in range(3):
        job.add("ring_mark", x=60 + 300 * k + 150)
    for k in range(3):
        job.add("cutoff", x=60 + 300 * k + 260)
    return job


def min_u(c):
    return min(p[0] for p in c.points)


def max_u(c):
    return max(p[0] for p in c.points)


class TestOrder(unittest.TestCase):
    def setUp(self):
        self.p = MachineProfile.load("config/machine_round.json")

    def test_tung_chi_tiet_mot_tu_dau_tu_do_vao(self):
        tp, warns = nested_job(True).build_toolpath(self.p)
        seq = tp.contours
        self.assertEqual(check_order(seq), [])
        self.assertTrue(seq[-1].wrap and seq[-1].kind == "cut")   # kết thúc bằng cắt đứt
        partoffs = [i for i, c in enumerate(seq) if c.wrap and c.kind == "cut"]
        self.assertEqual(len(partoffs), 3)
        # nhát gần đầu tự do (u lớn) cắt trước
        self.assertEqual([min_u(seq[i]) for i in partoffs],
                         sorted([min_u(seq[i]) for i in partoffs], reverse=True))
        # mọi thứ nằm ngoài một nhát cắt đứt đều đã cắt xong trước nó
        for i in partoffs:
            for c in seq[i + 1:]:
                self.assertLessEqual(max_u(c), min_u(seq[i]) + 1e-6, c.name)

    def test_trong_moi_chi_tiet_vach_dau_truoc(self):
        tp, _ = nested_job(True).build_toolpath(self.p)
        group = []
        for c in tp.contours:
            if c.wrap and c.kind == "cut":
                kinds = [x.kind for x in group]
                if "mark" in kinds:
                    self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "mark"))
                group = []
            else:
                group.append(c)

    def test_it_chay_khong_hon_thu_tu_nhap(self):
        def travel(optimize):
            tp, _ = nested_job(optimize).build_toolpath(self.p)
            r = plan(self.p, build_program(self.p, tp).stream_lines())
            return r.by_category["travel"] + r.by_category["lift"]
        self.assertLess(travel(True), 0.75 * travel(False))

    def test_hai_nhat_cat_dut_thi_nhat_ngoai_truoc(self):
        job = Job()
        job.add("cutoff", x=100.0)
        job.add("cutoff", x=250.0)
        tp, _ = job.build_toolpath(self.p)
        self.assertEqual([round(min_u(c)) for c in tp.contours],
                         sorted([round(min_u(c)) for c in tp.contours], reverse=True))

    def test_canh_bao_nhat_cat_dut_nam_ngoai_nhat_da_cat(self):
        """Cắt 100 trước thì khúc chứa nhát 250 đã rơi mất - trước đây không báo."""
        job = Job(optimize_order=False)
        job.add("cutoff", x=100.0)
        job.add("cutoff", x=250.0)
        tp, warns = job.build_toolpath(self.p)
        self.assertTrue(any("đã rơi ra rồi" in w for w in warns), warns)

    def test_goc_quay_tinh_qua_moc_360(self):
        """Lỗ ở 350 độ và lỗ ở 10 độ chỉ cách nhau 20 độ, không phải 340."""
        job = Job()
        for th in (0.0, 180.0, 350.0, 10.0):
            job.add("hole", diameter=10.0, x=100.0, theta=th)
        tp, _ = job.build_toolpath(self.p)
        sec = tp.section
        ths = [sec.contact_at(c.points[0][1]).theta for c in tp.contours]
        turn = abs((ths[0] + 180.0) % 360.0 - 180.0)
        for a, b in zip(ths, ths[1:]):
            turn += abs((b - a + 180.0) % 360.0 - 180.0)
        self.assertLess(turn, 215.0, ths)       # tối ưu là ~200 độ; không để ý mốc 360 thì 350


class TestCornerRestart(unittest.TestCase):
    def _prog(self, path, **process):
        p = MachineProfile.load(path)
        for k, v in process.items():
            setattr(p.process, k, v)
        job = Job()
        job.add("cutoff", x=100.0)
        return p, build_program(p, job.build_toolpath(p)[0])

    @staticmethod
    def _relights(p, lines):
        """(vị trí lúc mồi, dòng G4 ngay sau) cho mỗi lần bật mỏ."""
        pos, out = {}, []
        for i, line in enumerate(lines):
            words = line.split("(")[0].split()
            if words and words[0] in ("M3", "M03", "M4", "M04"):
                out.append((dict(pos), lines[i + 1]))
            for w in words:
                if w[0] in "XYZA" and w[0] in p.letters:
                    pos[w[0]] = float(w[1:])
        return out

    def test_pivot_moi_lai_ngay_tren_mep_dung_do_cao_cat(self):
        p, prog = self._prog("config/machine_default.json")
        self.assertEqual(p.motion.corner_mode, "pivot")
        s = prog.stats
        self.assertEqual(s.edge_starts, s.pierces - 1)
        self.assertEqual(s.edge_starts, 8)                 # 4 góc x 2 lần xoay
        sec = p.pipe.section()
        for pos, _dwell in self._relights(p, prog.stream_lines())[1:]:
            # Độ cao lúc mồi lại = độ cao cắt trên đúng chỗ béc đang đứng
            # (trước đây lấy theo điểm kế tiếp nên cao hơn ~0,4 mm)
            surf = sec.surface_height(pos["A"], pos["X"]) - sec.reference_height
            self.assertAlmostEqual(pos["Z"] - surf, p.process.cut_height, delta=0.01)

    def test_index_bo_qua_cung_goc_nen_phai_duc_that(self):
        p, prog = self._prog("config/machine_box_index.json")
        self.assertEqual(prog.stats.edge_starts, 0)
        sec = p.pipe.section()
        for pos, _dwell in self._relights(p, prog.stream_lines()):
            surf = sec.surface_height(pos["A"], pos["X"]) - sec.reference_height
            self.assertAlmostEqual(pos["Z"] - surf, p.process.pierce_height, delta=0.01)

    def test_cho_moi_lai_rieng(self):
        p, prog = self._prog("config/machine_default.json", restart_delay=0.2)
        relights = self._relights(p, prog.stream_lines())
        self.assertEqual(relights[0][1], f"G4 P{p.process.pierce_delay:g}")   # lần đầu vẫn đục thật
        for _pos, dwell in relights[1:]:
            self.assertEqual(dwell, "G4 P0.2")
        p2, prog2 = self._prog("config/machine_default.json")
        self.assertLess(prog.stats.estimated_time, prog2.stats.estimated_time - 3.0)

    def test_xoay_goc_luc_tat_mo_chay_G0(self):
        p, prog = self._prog("config/machine_default.json")
        lines = prog.stream_lines()
        m5 = next(i for i, l in enumerate(lines) if l.startswith("M5"))
        rotate = [l for l in lines[m5 + 2:m5 + 14] if "A" in l]
        self.assertTrue(rotate)
        self.assertTrue(rotate[0].startswith("G0"), rotate)
        self.assertTrue(all("F" not in l for l in rotate), rotate)

        p.motion.corner_rotate_rate = 1800.0         # người dùng tự đặt tốc độ xoay
        job = Job()
        job.add("cutoff", x=100.0)
        lines = build_program(p, job.build_toolpath(p)[0]).stream_lines()
        m5 = next(i for i, l in enumerate(lines) if l.startswith("M5"))
        rotate = [l for l in lines[m5 + 2:m5 + 14] if "A" in l]
        # G1 là modal: đang cắt bằng G1 nên dòng xoay không lặp chữ G1, chỉ có F
        self.assertTrue(any("F" in l for l in rotate), rotate)
        self.assertTrue(all(not l.startswith("G0") for l in rotate), rotate)


if __name__ == "__main__":
    unittest.main()
