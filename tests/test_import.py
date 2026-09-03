"""Kiểm thử các bộ nhập biên dạng: DXF, SVG, G-code phẳng và mô hình 3D."""

import math
import os
import struct
import tempfile
import unittest

from pipecut import importers, jobs
from pipecut.config import MachineProfile
from pipecut.importers import common, dxf, gcode2d, mesh, svg
from pipecut.section import BoxSection, RoundSection


def _tmp(name: str, data, binary: bool = False) -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="pipecut-"), name)
    with open(path, "wb" if binary else "w",
              **({} if binary else {"encoding": "utf-8"})) as fh:
        fh.write(data)
    return path


# --------------------------------------------------------------------------
class TestCommon(unittest.TestCase):
    def test_cung_tron_dung_do_dai(self):
        pts = common.arc_points(0, 0, 10, 0, 90, tolerance=0.001)
        length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        self.assertAlmostEqual(length, math.pi * 10 / 2, places=2)

    def test_bspline_qua_dung_hai_dau(self):
        ctrl = [(0, 0), (10, 20), (30, -10), (40, 0)]
        pts = common.bspline_points(ctrl, degree=3, samples=120)
        self.assertAlmostEqual(math.dist(pts[0], ctrl[0]), 0.0, places=6)
        self.assertAlmostEqual(math.dist(pts[-1], ctrl[-1]), 0.0, places=6)

    def test_noi_cac_doan_roi_thanh_vong_kin(self):
        segs = [common.Curve2D([(0, 0), (10, 0)]), common.Curve2D([(10, 10), (0, 10)]),
                common.Curve2D([(10, 0), (10, 10)]), common.Curve2D([(0, 10), (0, 0)])]
        joined = common.join_curves(segs, tolerance=0.01)
        self.assertEqual(len(joined), 1)
        self.assertTrue(joined[0].closed)
        self.assertAlmostEqual(joined[0].length, 40.0, places=6)


# --------------------------------------------------------------------------
DXF_RECT = """0
SECTION
2
HEADER
9
$INSUNITS
70
4
0
ENDSEC
0
SECTION
2
ENTITIES
0
LINE
8
CUT
10
0.0
20
0.0
11
60.0
21
0.0
0
LINE
8
CUT
10
60.0
20
0.0
11
60.0
21
40.0
0
LINE
8
CUT
10
60.0
20
40.0
11
0.0
21
40.0
0
LINE
8
CUT
10
0.0
20
40.0
11
0.0
21
0.0
0
CIRCLE
8
LO
10
30.0
20
20.0
40
8.0
0
ENDSEC
0
EOF
"""


class TestDxf(unittest.TestCase):
    def setUp(self):
        self.path = _tmp("a.dxf", DXF_RECT)

    def test_noi_bon_doan_thanh_hinh_chu_nhat_kin(self):
        curves = dxf.load(self.path)
        rect = [c for c in curves if c.layer == "CUT"]
        self.assertEqual(len(rect), 1)
        self.assertTrue(rect[0].closed)
        self.assertAlmostEqual(rect[0].length, 200.0, places=6)

    def test_duong_tron_dung_chu_vi(self):
        circle = [c for c in dxf.load(self.path, tolerance=0.001) if c.layer == "LO"][0]
        self.assertTrue(circle.closed)
        self.assertAlmostEqual(circle.length, 2 * math.pi * 8.0, places=1)

    def test_loc_theo_lop(self):
        self.assertEqual(len(dxf.load(self.path, layers=["LO"])), 1)

    def test_lwpolyline_co_bulge_thanh_cung_tron(self):
        # nửa đường tròn bán kính 10: bulge = 1 (nửa vòng)
        text = ("0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n8\n0\n90\n2\n70\n0\n"
                "10\n0.0\n20\n0.0\n42\n1.0\n10\n20.0\n20\n0.0\n0\nENDSEC\n0\nEOF\n")
        c = dxf.parse(text, tolerance=0.001)[0]
        self.assertAlmostEqual(c.length, math.pi * 10.0, places=1)


# --------------------------------------------------------------------------
class TestSvg(unittest.TestCase):
    def test_doi_don_vi_tu_width_va_viewbox(self):
        text = ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" '
                'viewBox="0 0 100 50"><rect x="10" y="10" width="40" height="20"/></svg>')
        c = svg.parse(text)[0]
        self.assertTrue(c.closed)
        self.assertAlmostEqual(c.length, 120.0, places=6)

    def test_duong_tron_va_bien_doi_long_nhau(self):
        text = ('<svg xmlns="http://www.w3.org/2000/svg" width="200mm" '
                'viewBox="0 0 200 200"><g transform="translate(10,10) scale(2)">'
                '<circle cx="0" cy="0" r="5"/></g></svg>')
        c = svg.parse(text, tolerance=0.001)[0]
        self.assertAlmostEqual(c.length, 2 * math.pi * 10.0, places=1)

    def test_chu_nhat_bo_goc(self):
        base = ('<svg xmlns="http://www.w3.org/2000/svg" width="150mm" '
                'viewBox="0 0 150 60"><rect x="5" y="5" width="140" height="50"%s/></svg>')
        vuong = svg.parse(base % "")[0]
        self.assertAlmostEqual(vuong.length, 2 * (140 + 50), places=6)
        tron = svg.parse(base % ' rx="10" ry="10"', tolerance=0.005)[0]
        self.assertAlmostEqual(tron.length, 2 * (120 + 30) + 2 * math.pi * 10, places=1)
        # thiếu ry thì lấy theo rx
        chi_rx = svg.parse(base % ' rx="10"', tolerance=0.005)[0]
        self.assertAlmostEqual(chi_rx.length, tron.length, places=6)
        # rx lớn quá bị kẹp lại còn nửa cạnh -> thành hình ellipse
        kep = svg.parse(base % ' rx="500" ry="500"', tolerance=0.005)[0]
        a, b = 70.0, 25.0
        chu_vi = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
        self.assertAlmostEqual(kep.length, chu_vi, places=1)

    def test_duong_path_co_cung_ellipse(self):
        text = ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" '
                'viewBox="0 0 100 100"><path d="M0,0 A10,10 0 0 1 20,0"/></svg>')
        c = svg.parse(text, tolerance=0.001)[0]
        self.assertAlmostEqual(c.length, math.pi * 10.0, places=1)


# --------------------------------------------------------------------------
class TestGcode2d(unittest.TestCase):
    def test_chay_nhanh_tach_bien_dang(self):
        prog = ("G21 G90\nG0 X0 Y0\nG1 X10 Y0\nG0 X50 Y0\nG1 X60 Y0\n")
        curves = gcode2d.parse(prog)
        self.assertEqual(len(curves), 2)
        self.assertAlmostEqual(curves[0].length, 10.0, places=6)

    def test_cung_kieu_ij_va_kieu_r_cho_cung_ket_qua(self):
        a = gcode2d.parse("G21 G90\nG0 X50 Y30\nG3 X40 Y40 I-10 J0\n", tolerance=0.001)
        b = gcode2d.parse("G21 G90\nG0 X50 Y30\nG3 X40 Y40 R10\n", tolerance=0.001)
        self.assertAlmostEqual(a[0].length, b[0].length, places=6)
        self.assertAlmostEqual(a[0].length, math.pi * 10 / 2, places=2)

    def test_r_am_cho_cung_lon(self):
        c = gcode2d.parse("G21 G90\nG0 X50 Y30\nG3 X40 Y40 R-10\n", tolerance=0.001)
        self.assertAlmostEqual(c[0].length, 2 * math.pi * 10 * 0.75, places=1)

    def test_g2_di_vong_lon_khi_tam_o_phia_kia(self):
        # G2 (cùng chiều kim đồng hồ) quanh tâm (40,30) là cung 270 độ
        c = gcode2d.parse("G21 G90\nG0 X50 Y30\nG2 X40 Y40 I-10 J0\n", tolerance=0.001)
        self.assertAlmostEqual(c[0].length, 2 * math.pi * 10 * 0.75, places=1)

    def test_inch_va_toa_do_tuong_doi(self):
        c = gcode2d.parse("G20 G91\nG1 X1 Y0\nG1 X0 Y1\n")
        self.assertAlmostEqual(c[0].length, 2 * 25.4, places=6)
        self.assertAlmostEqual(c[0].points[-1][1], 25.4, places=6)

    def test_bo_qua_ghi_chu(self):
        c = gcode2d.parse("(mo dau)\nG21 G90 ; chu thich\nG1 X10 Y0\n")
        self.assertAlmostEqual(c[0].length, 10.0, places=6)

    def test_tep_khong_co_duong_cat_thi_bao_loi(self):
        with self.assertRaises(common.ImportError_):
            gcode2d.parse("G21 G90\nM3\nM5\n")

    def test_vong_tron_kin_duoc_danh_dau_khep_kin(self):
        c = gcode2d.parse("G21 G90\nG0 X10 Y0\nG3 X10 Y0 I-10 J0\n", tolerance=0.001)
        self.assertTrue(c[0].closed)
        self.assertAlmostEqual(c[0].length, 2 * math.pi * 10, places=1)


# --------------------------------------------------------------------------
def _stl(tris) -> str:
    data = bytearray(b"\0" * 80 + struct.pack("<I", len(tris)))
    for t in tris:
        data += struct.pack("<12f", 0, 0, 0, *t[0], *t[1], *t[2]) + b"\0\0"
    return _tmp("m.stl", bytes(data), binary=True)


def _tube(section, cut, length: float = 120.0, n: int = 180, m: int = 30, axis: int = 2):
    """Lưới mặt ngoài một đoạn phôi bị cắt theo hàm ``cut(v)``."""
    per = section.perimeter
    tris = []

    def pt(u, v):
        x, y = section.point_at(v % per)
        return (x, y, u) if axis == 2 else (u, x, y)

    for i in range(n):
        v0, v1 = per * i / n, per * (i + 1) / n
        for j in range(m):
            a = pt(cut(v0) * j / m, v0)
            b = pt(cut(v1) * j / m, v1)
            c = pt(cut(v1) * (j + 1) / m, v1)
            d = pt(cut(v0) * (j + 1) / m, v0)
            tris.append((a, b, c))
            tris.append((a, c, d))
    return tris


class TestMesh(unittest.TestCase):
    def setUp(self):
        self.section = BoxSection(50.0, 50.0, 5.0, 3.0)
        self.per = self.section.perimeter
        self.cut = lambda v: 100.0 + 20.0 * math.sin(2 * math.pi * v / self.per)
        self.tris = _tube(self.section, self.cut)

    def test_lay_dung_duong_cat_so_voi_ly_thuyet(self):
        curves = mesh.extract_cut_curves(self.tris, self.section, surface_tolerance=0.2)
        top = max(curves, key=lambda c: max(p[0] for p in c.points))
        err = max(abs(u - self.cut(v % self.per)) for u, v in top.points)
        self.assertLess(err, 1e-6)

    def test_duong_cat_chay_tron_vong_duoc_danh_dau_quan_vong(self):
        curves = mesh.extract_cut_curves(self.tris, self.section, surface_tolerance=0.2)
        self.assertTrue(all(c.wrap and c.closed for c in curves))
        top = max(curves, key=lambda c: max(p[0] for p in c.points))
        span = top.points[-1][1] - top.points[0][1]
        self.assertAlmostEqual(abs(span), self.per, places=3)

    def test_lo_tren_than_ong_la_vong_kin_khong_quan_vong(self):
        section = RoundSection(60.0)
        per = section.perimeter
        hole = (45.0, per * 0.25, 10.0)

        def keep(u, v):
            dv = (v - hole[1] + per / 2) % per - per / 2
            return math.hypot(u - hole[0], dv) >= hole[2]

        tris = []
        n, m, length = 240, 60, 90.0
        for i in range(n):
            v0, v1 = per * i / n, per * (i + 1) / n
            for j in range(m):
                if not keep(length * (j + 0.5) / m, (v0 + v1) / 2):
                    continue
                pts = [(length * j / m, v0), (length * j / m, v1),
                       (length * (j + 1) / m, v1), (length * (j + 1) / m, v0)]
                xyz = []
                for u, v in pts:
                    x, y = section.point_at(v % per)
                    xyz.append((x, y, u))
                tris.append((xyz[0], xyz[1], xyz[2]))
                tris.append((xyz[0], xyz[2], xyz[3]))
        curves = mesh.extract_cut_curves(tris, section, surface_tolerance=0.2)
        holes = [c for c in curves if not c.wrap]
        self.assertEqual(len(holes), 1)
        self.assertTrue(holes[0].closed)
        us = [p[0] for p in holes[0].points]
        self.assertAlmostEqual((min(us) + max(us)) / 2, hole[0], delta=1.0)

    def test_doc_duoc_stl_nhi_phan_ascii_va_obj_cho_ket_qua_nhu_nhau(self):
        binary = mesh.load_triangles(_stl(self.tris))
        lines = ["solid t"]
        for t in self.tris:
            lines.append(" facet normal 0 0 0\n  outer loop")
            lines += ["   vertex %.6f %.6f %.6f" % v for v in t]
            lines.append("  endloop\n endfacet")
        lines.append("endsolid t")
        ascii_tris = mesh.load_triangles(_tmp("m.stl", "\n".join(lines)))
        self.assertEqual(len(binary), len(self.tris))
        self.assertEqual(len(ascii_tris), len(self.tris))
        a = mesh.extract_cut_curves(binary, self.section, surface_tolerance=0.2)
        b = mesh.extract_cut_curves(ascii_tris, self.section, surface_tolerance=0.2)
        self.assertAlmostEqual(a[0].length, b[0].length, places=3)

    def test_stl_co_byte_thua_o_cuoi_van_doc_duoc(self):
        path = _stl(self.tris[:10])
        with open(path, "ab") as fh:
            fh.write(b"rac rac rac")
        self.assertEqual(len(mesh.load_triangles(path)), 10)

    def test_tu_do_duoc_truc_phoi(self):
        self.assertEqual(mesh.detect_axis(self.tris), "z")
        along_x = _tube(self.section, self.cut, axis=0)
        self.assertEqual(mesh.detect_axis(along_x), "x")
        curves = mesh.extract_cut_curves(along_x, self.section, surface_tolerance=0.2)
        self.assertAlmostEqual(curves[0].length,
                               mesh.extract_cut_curves(self.tris, self.section,
                                                       surface_tolerance=0.2)[0].length,
                               places=3)

    def test_bu_duoc_goc_xoay_quanh_truc(self):
        a = math.radians(30)
        rolled = [tuple((v[0] * math.cos(a) - v[1] * math.sin(a),
                         v[0] * math.sin(a) + v[1] * math.cos(a), v[2]) for v in t)
                  for t in self.tris]
        curves = mesh.extract_cut_curves(rolled, self.section, roll_deg=30,
                                         surface_tolerance=0.2)
        self.assertAlmostEqual(curves[0].length, 210.6, delta=0.5)
        with self.assertRaises(common.ImportError_):
            mesh.extract_cut_curves(rolled, self.section, surface_tolerance=0.2)

    def test_bao_khi_tiet_dien_khai_bao_khong_khop_mo_hinh(self):
        notes = []
        mesh.extract_cut_curves(self.tris, BoxSection(50.0, 50.0, 0.0, 3.0),
                                surface_tolerance=0.2, notes=notes)
        self.assertTrue(notes, "phải cảnh báo khi khai sai bán kính bo góc")
        self.assertTrue(any("chu vi" in n for n in notes))

    def test_phoi_khai_qua_nho_thi_bao_loi(self):
        with self.assertRaises(common.ImportError_):
            mesh.extract_cut_curves(self.tris, BoxSection(40.0, 40.0, 5.0, 3.0),
                                    surface_tolerance=0.2)


# --------------------------------------------------------------------------
class TestDispatch(unittest.TestCase):
    def test_nhan_dien_dinh_dang_theo_duoi_tep(self):
        self.assertEqual(importers.detect_format("a.DXF"), "dxf")
        self.assertEqual(importers.detect_format("a.svg"), "svg")
        self.assertEqual(importers.detect_format("a.tap"), "gcode")
        self.assertEqual(importers.detect_format("a.obj"), "mesh")
        self.assertEqual(importers.detect_format("a.csv"), "points")

    def test_step_bao_loi_kem_huong_dan_xuat_stl(self):
        with self.assertRaises(common.ImportError_) as ctx:
            importers.detect_format("chi_tiet.step")
        self.assertIn("STL", str(ctx.exception))

    def test_doc_mo_hinh_3d_ma_thieu_tiet_dien_thi_bao_loi(self):
        path = _stl(_tube(BoxSection(50.0, 50.0, 5.0, 3.0), lambda v: 100.0))
        with self.assertRaises(common.ImportError_):
            importers.load_curves(path)

    def test_danh_sach_diem_csv_va_json(self):
        csv = importers.load_curves(_tmp("p.csv", "# u,v\n0,0\n50,0\n50,40\n"))
        self.assertAlmostEqual(csv[0].length, 90.0, places=6)
        js = importers.load_curves(_tmp("p.json", '{"points": [[0,0],[60,0]]}'))
        self.assertAlmostEqual(js[0].length, 60.0, places=6)

    def test_mo_ta_tep_cho_giao_dien(self):
        text = importers.describe_file(_tmp("a.dxf", DXF_RECT))
        self.assertIn("DXF", text)
        self.assertIn("đường", text)


# --------------------------------------------------------------------------
class TestJobIntegration(unittest.TestCase):
    def setUp(self):
        self.profile = MachineProfile.load(
            os.path.join(os.path.dirname(__file__), "..", "config", "machine_default.json"))

    def test_mot_tep_nhieu_duong_thanh_nhieu_bien_dang(self):
        job = jobs.Job(name="nhap")
        job.add("pattern", file=_tmp("a.dxf", DXF_RECT), x_offset=100.0)
        toolpath, warns = job.build_toolpath(self.profile)
        self.assertEqual(len(toolpath.contours), 2)
        self.assertEqual(warns, [])

    def test_ti_le_xoay_va_lat_deu_co_tac_dung(self):
        path = _tmp("a.dxf", DXF_RECT)
        job = jobs.Job(name="nhap")
        job.add("pattern", file=path, x_offset=100.0, scale=2.0)
        big = job.build_toolpath(self.profile)[0].contours[0]
        job2 = jobs.Job(name="nhap")
        job2.add("pattern", file=path, x_offset=100.0)
        small = job2.build_toolpath(self.profile)[0].contours[0]
        self.assertAlmostEqual(big.length, small.length * 2.0, places=3)

        job3 = jobs.Job(name="nhap")
        job3.add("pattern", file=path, x_offset=100.0, rotate=90.0)
        rot = job3.build_toolpath(self.profile)[0].contours[0]
        self.assertAlmostEqual(rot.length, small.length, places=3)
        # xoay 90 độ thì khổ dọc ống và khổ chu vi đổi chỗ cho nhau
        du = lambda c: max(p[0] for p in c.points) - min(p[0] for p in c.points)
        dv = lambda c: max(p[1] for p in c.points) - min(p[1] for p in c.points)
        self.assertAlmostEqual(du(rot), dv(small), places=3)

    def test_tep_khong_doc_duoc_thanh_canh_bao_chu_khong_lam_do_chuong_trinh(self):
        job = jobs.Job(name="nhap")
        job.add("pattern", file="/khong/co/that.dxf")
        toolpath, warns = job.build_toolpath(self.profile)
        self.assertEqual(toolpath.contours, [])
        self.assertEqual(len(warns), 1)

    def test_bien_dang_nhap_vao_sinh_duoc_gcode_bon_truc(self):
        from pipecut.gcode import build_program
        job = jobs.Job(name="nhap")
        job.add("pattern", file=_tmp("a.dxf", DXF_RECT), x_offset=150.0)
        toolpath, _ = job.build_toolpath(self.profile)
        program = build_program(self.profile, toolpath, job.name)
        self.assertGreater(program.stats.lines, 50)
        self.assertTrue(any(line.startswith("G1") or " A" in line
                            for line in program.lines))

    def test_khu_hoi_gcode_phang_ve_dung_bien_dang_ban_dau(self):
        """Xuất biên dạng ra G-code phẳng rồi nạp lại phải ra đúng hình cũ."""
        section = BoxSection(50.0, 50.0, 5.0, 3.0)
        from pipecut import shapes
        original = shapes.slot(section, 150.0, 0.0, 60.0, angular_width_deg=90.0,
                               corner_radius=5.0, tolerance=0.01)
        lines = ["G21 G90", "G0 X%.4f Y%.4f" % original.points[0]]
        lines += ["G1 X%.4f Y%.4f" % p for p in original.points[1:]]
        curves = gcode2d.parse("\n".join(lines), tolerance=0.01)
        self.assertEqual(len(curves), 1)
        # sai lệch còn lại chỉ do làm tròn 4 chữ số khi ghi G-code
        self.assertAlmostEqual(curves[0].length, original.length, places=3)
        for a, b in zip(curves[0].points, original.points):
            self.assertAlmostEqual(a[0], b[0], places=4)
            self.assertAlmostEqual(a[1], b[1], places=4)


if __name__ == "__main__":
    unittest.main()
