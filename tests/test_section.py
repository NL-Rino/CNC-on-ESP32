"""Kiểm thử tiết diện phôi và việc cắt ống hộp."""

import math
import re
import unittest

from pipecut import shapes
from pipecut.config import MachineProfile, ROLE_ALONG, ROLE_CROSS, ROLE_ROTARY
from pipecut.gcode import build_program
from pipecut.jobs import Job
from pipecut.pathops import process_contour
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


class TestCornerIndexing(unittest.TestCase):
    """Chế độ dừng cắt - xoay 90 độ - cắt tiếp khi qua góc ống hộp."""

    def setUp(self):
        self.p = MachineProfile()
        self.p.pipe.shape = "square"
        self.p.pipe.width = 50.0
        self.p.pipe.wall_thickness = 3.0
        cross = self.p.axis(ROLE_CROSS)
        cross.min_travel, cross.max_travel = -100.0, 100.0
        self.p.motion.corner_mode = "index"
        self.p.motion.corner_torch_off = True
        self.p.motion.corner_lift = 6.0
        self.section = self.p.pipe.section()

    def _cutoff(self):
        job = Job()
        job.add("cutoff", x=250.0, angle=0.0)
        tp, warns = job.build_toolpath(self.p)
        self.assertEqual(warns, [])
        return build_program(self.p, tp)

    def _trace_axes(self, prog):
        """Đọc lại toàn bộ toạ độ trục từ G-code, kèm trạng thái nguồn cắt."""
        cur = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}
        torch = False
        rows = []
        for line in prog.stream_lines():
            if line.startswith("M3") or line.startswith("M4"):
                torch = True
                continue
            if line.startswith("M5"):
                torch = False
                continue
            moved = False
            for axis in ("X", "Y", "Z", "A"):
                m = re.search(axis + r"(-?[\d.]+)", line)
                if m:
                    cur[axis] = float(m.group(1))
                    moved = True
            if moved:
                rows.append((dict(cur), torch))
        return rows

    def test_moi_goc_deu_tat_mo_va_moi_lai(self):
        prog = self._cutoff()
        lines = [l.split(" ")[0] for l in prog.stream_lines()]
        # 1 lần mồi đầu + 4 lần mồi lại sau bốn góc
        self.assertEqual(prog.stats.pierces, 5)
        self.assertEqual(lines.count("M3"), 5)
        self.assertEqual(lines.count("M5"), 6)     # 5 lần cắt + 1 lần ở phần kết

    def test_khi_xoay_goc_mo_cat_bam_dung_goc_do_tren_phoi(self):
        """Suốt lúc mâm quay, mỏ cắt phải giữ nguyên khoảng cách tới tâm cung
        góc - tức là vẫn "đứng" đúng chỗ góc đó trên phôi, chỉ có phôi xoay."""
        prog = self._cutoff()
        sec = self.section
        ref = sec.reference_height
        want = sec.rc + self.p.process.cut_height + self.p.motion.corner_lift
        centers = [(sx * (sec.hx - sec.rc), sy * (sec.hy - sec.rc))
                   for sx in (1, -1) for sy in (1, -1)]
        checked = 0
        for state, torch in self._trace_axes(prog):
            if torch or state["Z"] > 25.0:      # bỏ qua lúc đang cắt và lúc chạy về an toàn
                continue
            a = math.radians(state["A"])
            tip = (state["X"], ref + state["Z"])
            best = min(
                math.hypot(tip[0] - (cx * math.cos(a) - cy * math.sin(a)),
                           tip[1] - (cx * math.sin(a) + cy * math.cos(a)))
                for cx, cy in centers)
            if abs(best - want) < 2.0:          # đang trong pha xoay góc
                checked += 1
                self.assertAlmostEqual(best, want, delta=0.05)
        self.assertGreater(checked, 30, "không tìm thấy pha xoay góc trong G-code")

    def test_ba_truc_cung_chuyen_dong_trong_pha_xoay(self):
        prog = self._cutoff()
        rows = [s for s, torch in self._trace_axes(prog) if not torch]
        moved = {"X": 0, "Z": 0, "A": 0}
        for a, b in zip(rows, rows[1:]):
            for axis in moved:
                if abs(b[axis] - a[axis]) > 1e-6:
                    moved[axis] += 1
        for axis, count in moved.items():
            self.assertGreater(count, 20, f"trục {axis} hầu như không chạy khi xoay góc")

    def test_canh_bao_goc_luon_khong_duoc_cat(self):
        prog = self._cutoff()
        self.assertTrue(any("KHÔNG được cắt" in w for w in prog.stats.warnings))

    def test_khong_canh_bao_tut_toc_do_vi_cham_la_co_y(self):
        prog = self._cutoff()
        self.assertFalse([w for w in prog.stats.warnings if "tốc độ cắt tụt" in w])

    def test_giu_mo_bat_thi_van_cat_lien_mach(self):
        self.p.motion.corner_torch_off = False
        prog = self._cutoff()
        lines = [l.split(" ")[0] for l in prog.stream_lines()]
        self.assertEqual(lines.count("M3"), 1)       # chỉ mồi một lần
        self.assertFalse([w for w in prog.stats.warnings if "KHÔNG được cắt" in w])

    def test_ong_tron_khong_bi_anh_huong(self):
        self.p.pipe.shape = "round"
        self.p.pipe.outer_diameter = 60.0
        prog = self._cutoff()
        lines = [l.split(" ")[0] for l in prog.stream_lines()]
        self.assertEqual(lines.count("M3"), 1)       # ống tròn không có góc để xoay
        self.assertEqual(prog.stats.pierces, 1)

    def test_phan_cat_tren_mat_phang_van_nguyen_ven(self):
        """Bật chế độ xoay góc không được làm hỏng phần cắt trên mặt phẳng."""
        flat = self.section.hx - self.section.rc
        prog = self._cutoff()
        b = prog.stats.bounds
        self.assertAlmostEqual(b["X"][0], -flat, delta=0.05)
        self.assertAlmostEqual(b["X"][1], flat, delta=0.05)
        for state, torch in self._trace_axes(prog):
            if torch and state["Z"] < 5.0:           # đang cắt trên mặt
                gap = (self.section.reference_height + state["Z"]) - \
                    self.section.surface_height(state["A"], state["X"])
                self.assertAlmostEqual(gap, self.p.process.cut_height, delta=0.1)



def _box_profile() -> MachineProfile:
    """Hồ sơ máy ống hộp 50x50 dùng chung cho các bài kiểm thử bên dưới."""
    p = MachineProfile()
    p.pipe.shape = "square"
    p.pipe.width = p.pipe.height = 50.0
    p.pipe.wall_thickness = 3.0
    p.pipe.length = 500.0
    cross = p.axis(ROLE_CROSS)
    cross.min_travel, cross.max_travel = -200.0, 200.0
    return p


class TestSeamContinuity(unittest.TestCase):
    """Góc trục xoay phải liên tục khi đi qua mốc chu vi.

    Đây là chỗ đã từng sai: với ``v`` âm cực nhỏ (vụn dấu phẩy động kiểu
    -9e-16), phần dư bị làm tròn lên đúng bằng chu vi, ``normal_angle`` quy nó
    về 0 độ của vòng sau trong khi bộ đếm vòng vẫn ở vòng trước - góc nhảy trọn
    360 độ và phôi quay hẳn một vòng ngay giữa nhát cắt.
    """

    def _sections(self):
        return [BoxSection(50.0, 50.0, 6.0, 3.0),
                BoxSection(60.0, 40.0, 5.0, 2.0),
                RoundSection(60.0)]

    def test_khong_nhay_360_do_quanh_moc_chu_vi(self):
        for sec in self._sections():
            per = sec.perimeter
            for centre in (0.0, per, -per, 2 * per):
                prev = None
                for k in range(-400, 401):
                    s = centre + k * 1e-9
                    th = sec.contact_at(s).theta
                    if prev is not None:
                        self.assertLess(abs(th - prev), 1.0,
                                        f"{sec.describe()} nhảy tại s={s!r}")
                    prev = th

    def test_vun_dau_phay_dong_am_van_ra_goc_0(self):
        sec = BoxSection(50.0, 50.0, 6.0, 3.0)
        for s in (-8.881784197001252e-16, -1e-15, -1e-12, -1e-9, 0.0, 1e-15):
            self.assertAlmostEqual(sec.contact_at(s).theta, 0.0, places=6,
                                   msg=f"s={s!r}")

    def test_ranh_tren_mat_phang_khong_lam_phoi_quay_vong(self):
        """Rãnh nằm gọn trong một mặt phẳng thì trục xoay phải đứng yên."""
        profile = _box_profile()
        job = Job(name="ranh")
        job.add("slot", x=120.0, theta=0.0, length=60.0, width_deg=45.0, corner=5.0)
        toolpath, _ = job.build_toolpath(profile)
        program = build_program(profile, toolpath, job.name)
        letter = profile.letter(ROLE_ROTARY)
        angles = [float(m.group(1))
                  for line in program.lines
                  for m in [re.search(rf"\b{letter}(-?[\d.]+)", line)] if m]
        self.assertTrue(angles)
        self.assertLess(max(abs(a) for a in angles), 1.0,
                        "trục xoay không được quay khi cắt rãnh trên mặt phẳng")


class TestCornerPivotArcs(unittest.TestCase):
    """Chia cung góc làm nhiều lần xoay thì mặt cắt gần vuông góc hơn."""

    def _worst_tilt(self, arcs: int) -> float:
        profile = _box_profile()
        profile.pipe.corner_radius = 6.0
        profile.motion.corner_mode = "pivot"
        profile.motion.corner_pivot_arcs = arcs
        section = profile.pipe.section()
        job = Job(name="cat"); job.add("cutoff", x=300.0, angle=0.0, bevel_axis=False)
        toolpath, _ = job.build_toolpath(profile)
        ps = process_contour(toolpath.contours[0], section,
                             profile.motion, profile.process)
        worst = 0.0
        for p in ps.points:
            if p.kind != "cut":
                continue
            psi = section.normal_angle(p.v % section.perimeter)
            psi += 360.0 * round((p.theta - psi) / 360.0)
            worst = max(worst, abs(psi - p.theta))
        return worst

    def test_chia_k_lan_thi_lech_toi_da_con_45_chia_k(self):
        for arcs, expect in ((1, 45.0), (2, 22.5), (3, 15.0), (6, 7.5)):
            self.assertAlmostEqual(self._worst_tilt(arcs), expect, delta=1.0,
                                   msg=f"chia {arcs}")

    def test_khe_ho_mo_phoi_giu_nguyen_du_chia_may_lan(self):
        """Chia nhỏ thế nào thì mỏ vẫn phải cách phôi đúng chiều cao cắt."""
        from pipecut.config import ROLE_CROSS, ROLE_RADIAL
        from pipecut.kinematics import Kinematics
        for arcs in (1, 3, 6):
            profile = _box_profile()
            profile.pipe.corner_radius = 6.0
            profile.motion.corner_mode = "pivot"
            profile.motion.corner_pivot_arcs = arcs
            section = profile.pipe.section()
            kin = Kinematics(profile)
            job = Job(name="cat"); job.add("cutoff", x=300.0, angle=0.0, bevel_axis=False)
            toolpath, _ = job.build_toolpath(profile)
            ps = process_contour(toolpath.contours[0], section,
                                 profile.motion, profile.process)
            xl, zl = profile.letter(ROLE_CROSS), profile.letter(ROLE_RADIAL)
            for p in ps.points:
                vals = kin.axis_values(p, profile.process.cut_height)
                gap = (vals.get(zl, 0.0) + section.reference_height
                       - section.surface_height(p.theta, vals.get(xl, 0.0)))
                self.assertAlmostEqual(gap, profile.process.cut_height, places=3,
                                       msg=f"chia {arcs}")

if __name__ == "__main__":
    unittest.main()


class TestJobOrderAndLeads(unittest.TestCase):
    """Thứ tự cắt do người dùng đặt, thư viện lọc theo phôi, và vào dao."""

    def setUp(self):
        self.p = MachineProfile()
        self.p.pipe.shape = "square"
        self.p.pipe.width = 50.0
        self.p.pipe.wall_thickness = 3.0
        cross = self.p.axis(ROLE_CROSS)
        cross.min_travel, cross.max_travel = -100.0, 100.0
        self.section = self.p.pipe.section()

    # ---- thứ tự cắt ----
    def test_mac_dinh_giu_nguyen_thu_tu_nguoi_dung_dat(self):
        job = Job()
        self.assertFalse(job.optimize_order)
        job.add("cutoff", x=320.0)
        job.add("slot", x=120.0, theta=0.0, length=40.0, width_deg=40.0)
        job.add("circle", diameter=20.0, x=200.0, theta=90.0)
        tp, _warns = job.build_toolpath(self.p)
        self.assertEqual([c.meta["shape"] for c in tp.contours],
                         ["plane_cut", "slot", "surface_circle"])

    def test_bat_tu_sap_xep_thi_cat_dut_xuong_cuoi(self):
        job = Job(optimize_order=True)
        job.add("cutoff", x=320.0)
        job.add("slot", x=120.0, theta=0.0, length=40.0, width_deg=40.0)
        job.add("ring_mark", x=60.0)
        tp, _warns = job.build_toolpath(self.p)
        kinds = [c.meta["shape"] for c in tp.contours]
        self.assertEqual(kinds[0], "plane_cut")      # vạch dấu vòng trước
        self.assertEqual(kinds[-1], "plane_cut")     # cắt đứt sau cùng
        self.assertEqual(tp.contours[0].kind, "mark")
        self.assertEqual(tp.contours[-1].kind, "cut")

    def test_canh_bao_khi_nguyen_cong_nam_ngoai_nhat_cat_dut(self):
        job = Job()
        job.add("cutoff", x=200.0)
        job.add("slot", x=300.0, theta=0.0, length=40.0, width_deg=40.0)
        _tp, warns = job.build_toolpath(self.p)
        self.assertTrue(any("đã rơi ra rồi" in w for w in warns), warns)

    def test_khong_canh_bao_khi_thu_tu_hop_ly(self):
        job = Job()
        job.add("slot", x=120.0, theta=0.0, length=40.0, width_deg=40.0)
        job.add("cutoff", x=300.0)
        _tp, warns = job.build_toolpath(self.p)
        self.assertEqual(warns, [])

    # ---- thư viện lọc theo phôi ----
    def test_thu_vien_ong_hop_khong_co_bien_dang_chi_danh_cho_ong_tron(self):
        from pipecut.jobs import ops_for_shape
        for shape in ("square", "rect"):
            ops = ops_for_shape(shape)
            self.assertNotIn("saddle", ops)
            self.assertNotIn("hole", ops)
            self.assertIn("slot", ops)
            self.assertIn("cutoff", ops)
            self.assertIn("circle", ops)
        self.assertIn("saddle", ops_for_shape("round"))
        self.assertIn("hole", ops_for_shape("round"))

    # ---- vào dao ----
    def test_doi_vi_tri_diem_moi_quanh_bien_dang_kin(self):
        from pipecut.pathops import process_contour
        seen = []
        for pct in (0.0, 25.0, 50.0, 75.0):
            self.p.process.lead_start = pct
            c = shapes.slot(self.section, 150.0, 0.0, 60.0,
                            angular_width_deg=50.0, corner_radius=5.0)
            ps = process_contour(c, self.section, self.p.motion, self.p.process)
            seen.append((round(ps.points[0].x, 2), round(ps.points[0].v, 2)))
        self.assertEqual(len(set(seen)), 4)      # bốn vị trí mồi khác nhau

    def test_doi_vi_tri_bat_dau_nhat_cat_quanh_phoi(self):
        from pipecut.pathops import process_contour
        for pct, want_a in ((0.0, 0.0), (25.0, 90.0), (50.0, 180.0)):
            self.p.process.lead_start = pct
            c = shapes.plane_cut(self.section, 250.0, 0.0)
            ps = process_contour(c, self.section, self.p.motion, self.p.process)
            first_cut = ps.points[ps.lead_in_count]
            self.assertAlmostEqual(first_cut.theta, want_a, delta=1.0)

    def test_doi_phia_vao_dao(self):
        from pipecut.pathops import process_contour
        pierce = {}
        for side in ("auto", "outside"):
            self.p.process.lead_side = side
            c = shapes.slot(self.section, 150.0, 0.0, 60.0,
                            angular_width_deg=50.0, corner_radius=5.0)
            ps = process_contour(c, self.section, self.p.motion, self.p.process)
            pierce[side] = (ps.points[0].x, ps.points[0].v)
        self.assertNotEqual(pierce["auto"], pierce["outside"])

    def test_doi_phia_moi_cua_nhat_cat_quanh_phoi(self):
        from pipecut.pathops import process_contour
        got = {}
        for side in ("auto", "minus"):
            self.p.process.lead_side = side
            c = shapes.plane_cut(self.section, 250.0, 0.0)
            ps = process_contour(c, self.section, self.p.motion, self.p.process)
            got[side] = ps.points[0].x - ps.points[ps.lead_in_count].x
        self.assertGreater(got["auto"], 0.0)     # mồi lệch về đầu tự do
        self.assertLess(got["minus"], 0.0)       # mồi lệch về phía mâm cặp


class TestPivotCorner(unittest.TestCase):
    """Chế độ xoay 45 độ đưa góc bo lên đỉnh rồi cắt ở tốc độ chuẩn."""

    def setUp(self):
        self.p = MachineProfile()
        self.p.pipe.shape = "square"
        self.p.pipe.width = 50.0
        self.p.pipe.wall_thickness = 3.0
        cross = self.p.axis(ROLE_CROSS)
        cross.min_travel, cross.max_travel = -100.0, 100.0
        self.p.motion.corner_mode = "pivot"
        self.section = self.p.pipe.section()

    def _pass(self):
        from pipecut.pathops import process_contour
        c = shapes.plane_cut(self.section, 250.0, 0.0)
        return process_contour(c, self.section, self.p.motion, self.p.process)

    def test_cat_ca_cung_goc_o_toc_do_chuan(self):
        from pipecut.kinematics import Kinematics
        kin = Kinematics(self.p)
        ps = self._pass()
        z = self.p.process.cut_height
        target = self.p.process.cut_feed
        speeds = [kin.achievable_surface_speed(a, b, target, z, z)
                  for a, b in zip(ps.points, ps.points[1:])
                  if a.kind == "cut" and b.kind == "cut"]
        self.assertTrue(speeds)
        for sp in speeds:
            self.assertAlmostEqual(sp, target, delta=2.0)

    def test_khi_cat_cung_goc_thi_truc_xoay_dung_yen(self):
        """Đưa góc bo lên đỉnh rồi mới cắt, nên trục A không phải quay tí nào."""
        ps = self._pass()
        arcs = self.section.arc_spans()
        per = self.section.perimeter
        checked = 0
        for a, b in zip(ps.points, ps.points[1:]):
            if a.kind != "cut" or b.kind != "cut":
                continue
            mid = ((a.v + b.v) / 2) % per
            if any(v0 + 1e-6 < mid < v1 - 1e-6 for v0, v1 in arcs):
                checked += 1
                self.assertAlmostEqual(b.theta, a.theta, places=9)
        self.assertGreater(checked, 20)

    def test_hai_lan_xoay_moi_lan_khoang_45_do(self):
        pts = self._pass().points
        sweeps = []
        i = 0
        while i < len(pts):
            if pts[i].kind != "index":
                i += 1
                continue
            j = i
            while j < len(pts) and pts[j].kind == "index":
                j += 1
            before = pts[i - 1].theta if i > 0 else pts[i].theta
            after = pts[j].theta if j < len(pts) else pts[j - 1].theta
            sweeps.append(abs(after - before))
            i = j
        self.assertGreaterEqual(len(sweeps), 8)        # 4 góc x 2 lần xoay
        for sweep in sweeps:
            self.assertAlmostEqual(sweep, 45.0, delta=2.0)

    def test_trong_luc_xoay_mo_cat_dung_yen_tai_mot_diem_tren_phoi(self):
        """Đúng ý: xoay nhưng đầu cắt vẫn ở nguyên chỗ đó trên phôi."""
        ps = self._pass()
        run_v = None
        checked = 0
        for a, b in zip(ps.points, ps.points[1:]):
            if a.kind == "index" and b.kind == "index":
                self.assertAlmostEqual(b.v, a.v, places=9)
                self.assertAlmostEqual(b.x, a.x, places=9)
                checked += 1
        self.assertGreater(checked, 30)

    def test_khe_ho_mo_cat_giu_dung_suot_ca_pha_xoay_va_pha_cat(self):
        from pipecut.jobs import Job
        job = Job()
        job.add("cutoff", x=250.0, angle=0.0)
        tp, _w = job.build_toolpath(self.p)
        prog = build_program(self.p, tp)
        sec = self.section
        ref = sec.reference_height
        zc = self.p.process.cut_height
        cur = {"X": 0.0, "Z": 0.0, "A": 0.0}
        torch = False
        worst, checked = 0.0, 0
        for line in prog.stream_lines():
            if line.startswith(("M3", "M4")):
                torch = True
                continue
            if line.startswith("M5"):
                torch = False
                continue
            for axis in ("X", "Z", "A"):
                m = re.search(axis + r"(-?[\d.]+)", line)
                if m:
                    cur[axis] = float(m.group(1))
            # chỉ soát các lệnh **chạy theo đường cắt** (có dịch X hoặc A) khi
            # nguồn cắt đang bật; lệnh nâng/hạ Z riêng lẻ không phải đường cắt
            if not torch or not re.search(r"[XA]-?[\d.]", line):
                continue
            gap = (ref + cur["Z"]) - sec.surface_height(cur["A"], cur["X"])
            worst = max(worst, abs(gap - zc))
            checked += 1
        self.assertGreater(checked, 50)
        self.assertLess(worst, 0.15, f"khe hở lệch tới {worst:.3f} mm")

    def test_cat_du_chieu_dai_khong_bo_sot_cung_goc(self):
        from pipecut.jobs import Job
        job = Job()
        job.add("cutoff", x=250.0, angle=0.0)
        tp, _w = job.build_toolpath(self.p)
        prog = build_program(self.p, tp)
        want = (self.section.perimeter + self.p.process.lead_in
                + self.p.process.overcut)
        self.assertAlmostEqual(prog.stats.cut_length, want, delta=1.0)
        self.assertFalse([w for w in prog.stats.warnings if "KHÔNG được cắt" in w])

    def test_moi_goc_ton_them_hai_lan_moi(self):
        from pipecut.jobs import Job
        job = Job()
        job.add("cutoff", x=250.0, angle=0.0)
        tp, _w = job.build_toolpath(self.p)
        prog = build_program(self.p, tp)
        self.assertEqual(prog.stats.pierces, 9)     # 1 + 2 lần mỗi góc x 4 góc

    def test_ong_tron_khong_bi_anh_huong(self):
        self.p.pipe.shape = "round"
        self.p.pipe.outer_diameter = 60.0
        self.section = self.p.pipe.section()
        ps = self._pass()
        self.assertTrue(all(q.kind == "cut" for q in ps.points))
        self.assertTrue(all(abs(q.cross) < 1e-9 for q in ps.points))
