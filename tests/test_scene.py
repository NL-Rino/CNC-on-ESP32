"""Khung nhìn 3D: đọc được hình khối, nhìn cận vùng cắt, thấy đường sắp cắt."""

import unittest

from pipecut import machinescene as ms
from pipecut.config import MachineProfile
from pipecut.gcode import build_program
from pipecut.gsim import Playback, SimState
from pipecut.jobs import Job


def _playback(profile_path="config/machine_round.json", job="examples/vi_du_ong_T.json"):
    p = MachineProfile.load(profile_path)
    prog = build_program(p, Job.load(job).build_toolpath(p)[0])
    return p, Playback(p, prog.stream_lines())


class TestScene(unittest.TestCase):
    def setUp(self):
        self.p, self.pb = _playback()
        self.cam = ms.Camera()

    def _scene(self, t, **kw):
        return ms.build_scene(self.p, self.pb.state_at(t), self.pb.trace_until(t),
                              self.cam, **kw)

    def test_than_ong_co_sang_toi(self):
        """Một màu phẳng thì không đọc ra khối tròn: phải có nhiều sắc độ."""
        prims = self._scene(self.pb.duration / 2)
        shades = {q.fill for q in prims if q.kind == "fill"}
        self.assertGreater(len(shades), 15)

    def test_mieng_ong_thay_thanh_ong(self):
        """Góc nhìn mặc định từ đầu tự do: thấy lòng ống tối bên trong vành."""
        self.assertLess(self.cam.dir[1], 0.0)
        prims = self._scene(0.0)
        self.assertTrue(any(q.kind == "fill" and q.fill == ms.COLOR_INSIDE for q in prims))

    def test_vung_cat_nho_hon_han_toan_canh(self):
        st = self.pb.state_at(0.0)
        wx0, wy0, wx1, wy1 = ms.scene_bounds(self.p, self.cam, st, focus="work")
        ax0, ay0, ax1, ay1 = ms.scene_bounds(self.p, self.cam, st, focus="all")
        self.assertLess((wx1 - wx0), 0.5 * (ax1 - ax0))
        # mũi mỏ cắt nằm trong khung vùng cắt
        tip = self.cam.project((0.0, 0.0, self.p.pipe.section().reference_height))
        self.assertTrue(wx0 <= tip[0] <= wx1 and wy0 <= tip[1] <= wy1)

    def test_duong_sap_cat_net_dut_da_cat_net_dam(self):
        t = self.pb.duration * 0.3
        prims = self._scene(t, plan=self.pb.trace)
        ghost = [q for q in prims if q.color == ms.COLOR_GHOST]
        done = [q for q in prims if q.color == ms.COLOR_TRACE]
        self.assertTrue(ghost and all(q.dash for q in ghost))
        self.assertTrue(done and not any(q.dash for q in done))
        # vết đã cắt có viền tối bên dưới cho nổi trên kim loại sáng
        self.assertTrue(any(q.color == ms.COLOR_HALO for q in prims))

    def test_mo_tat_thi_ghi_khoang_ho(self):
        t = next(m.t0 + m.duration * 0.5 for m in self.pb.moves
                 if not m.torch and m.rapid and m.t0 > self.pb.duration * 0.3)
        labels = [q for q in self._scene(t) if q.kind == "text"]
        self.assertTrue(labels)
        self.assertTrue(labels[0].text.startswith("hở "))
        self.assertTrue(labels[0].fill)            # có nền riêng, đè lên ống vẫn đọc được

    def test_mo_bat_thi_co_ho_quang(self):
        t = next(m.t0 + m.duration * 0.5 for m in self.pb.moves if m.torch and not m.rapid)
        prims = self._scene(t)
        self.assertTrue(any(q.color == ms.COLOR_ARC_CORE for q in prims))

    def test_ong_hop_mat_phang_mot_mau_goc_bo_chuyen_sac(self):
        p, pb = _playback("config/machine_box.json", "examples/vi_du_ong_hop.json")
        prims = ms.build_scene(p, SimState(axes={}), [], self.cam, show_frame=False)
        fills = [q.fill for q in prims if q.kind == "fill"]
        # mặt phẳng: nhiều dải cùng một màu; góc bo: các màu chuyển dần
        counts = {c: fills.count(c) for c in set(fills)}
        self.assertGreaterEqual(max(counts.values()), 8)
        self.assertGreater(len(counts), 6)

    def test_ba_truc_o_goc(self):
        rows = ms.axis_triad(self.p, self.cam, 24.0)
        self.assertEqual(sorted(r[3] for r in rows), ["X", "Y", "Z"])
        z = next(r for r in rows if r[3] == "Z")
        self.assertLess(z[1], 0.0)                   # trục Z chĩa lên trên màn hình

    def test_anh_svg_giong_khung_nhin(self):
        import xml.dom.minidom
        from pipecut.svgview import render_machine_svg
        t = self.pb.duration * 0.3
        svg = render_machine_svg(self.p, self.pb.state_at(t), self.pb.trace_until(t),
                                 title="thử", plan=self.pb.trace)
        xml.dom.minidom.parseString(svg.encode("utf-8"))
        self.assertIn("stroke-dasharray", svg)       # có đường sắp cắt
        from pipecut import palette
        self.assertIn(palette.current().hud_bg, svg)  # bảng số nền tối, chữ sáng


if __name__ == "__main__":
    unittest.main()
