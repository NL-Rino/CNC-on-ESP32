"""Kiểm thử bảng màu: tương phản đọc được và không sót màu cứng trong mã."""

import os
import re
import unittest

from pipecut import machinescene, palette, svgview

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _luminance(color: str) -> float:
    def channel(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = palette.LIGHT.hex_to_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class TestPaletteValues(unittest.TestCase):
    def test_moi_ma_mau_dung_dinh_dang(self):
        for name, pal in palette.THEMES.items():
            for field in pal.__dataclass_fields__:
                value = getattr(pal, field)
                if field in ("name", "label") or not isinstance(value, str):
                    continue
                self.assertRegex(value, r"^#[0-9a-fA-F]{6}$",
                                 f"{name}.{field} = {value!r}")

    def test_hai_bang_mau_co_du_moi_truong(self):
        self.assertEqual(set(palette.LIGHT.__dataclass_fields__),
                         set(palette.DARK.__dataclass_fields__))
        self.assertFalse(palette.LIGHT.dark)
        self.assertTrue(palette.DARK.dark)

    def test_tron_mau(self):
        p = palette.LIGHT
        self.assertEqual(p.mix("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(p.mix("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(p.mix("#000000", "#ffffff", 0.5), "#808080")
        # tỉ lệ ngoài khoảng bị kẹp lại chứ không cho ra màu vô nghĩa
        self.assertEqual(p.mix("#000000", "#ffffff", -3.0), "#000000")
        self.assertEqual(p.mix("#000000", "#ffffff", 9.0), "#ffffff")


class TestContrast(unittest.TestCase):
    """Mọi cặp chữ/nền phải đọc được theo tiêu chuẩn WCAG AA."""

    TEXT_PAIRS = [("fg", "bg"), ("fg", "surface"), ("fg", "field"),
                  ("fg_dim", "bg"), ("fg_faint", "bg"),
                  ("console_fg", "console_bg")]
    MARK_PAIRS = [("accent", "bg"), ("accent_hover", "bg"),
                  ("ok", "ok_soft"), ("warn", "warn_soft"),
                  ("danger", "danger_soft"),
                  ("cut", "view_flat"), ("mark", "view_flat"),
                  ("lead", "view_flat"), ("rapid", "view_flat"),
                  ("console_err", "console_bg"), ("console_ok", "console_bg"),
                  ("console_info", "console_bg"), ("console_tx", "console_bg")]

    def test_chu_du_tuong_phan(self):
        for name, pal in palette.THEMES.items():
            for a, b in self.TEXT_PAIRS:
                r = contrast(getattr(pal, a), getattr(pal, b))
                self.assertGreaterEqual(r, 4.5, f"{name}: {a} trên {b} chỉ {r:.2f}:1")

    def test_net_ve_du_tuong_phan(self):
        for name, pal in palette.THEMES.items():
            for a, b in self.MARK_PAIRS:
                r = contrast(getattr(pal, a), getattr(pal, b))
                self.assertGreaterEqual(r, 3.0, f"{name}: {a} trên {b} chỉ {r:.2f}:1")

    def test_chu_tren_nut_nhan_manh_doc_duoc(self):
        for name, pal in palette.THEMES.items():
            for bg in (pal.accent, pal.danger):
                r = contrast(pal.ink_on(bg), bg)
                self.assertGreaterEqual(r, 4.5, f"{name}: chữ trên {bg} chỉ {r:.2f}:1")

    def test_phoi_noi_bat_tren_nen_khung_nhin(self):
        """Thân phôi phải nhìn ra được trên nền chuyển sắc ở cả hai chế độ.

        Hình khối đọc được nhờ **hoặc** thân sáng hơn hẳn nền, **hoặc** đường
        viền đậm hơn hẳn nền - chỉ cần một trong hai là đủ.  Ở chế độ sáng thì
        đường viền gánh việc đó, ở chế độ tối thì thân phôi.
        """
        for name, pal in palette.THEMES.items():
            for background in (pal.view_top, pal.view_bottom):
                best = max(contrast(pal.metal_fill, background),
                           contrast(pal.metal_edge, background))
                self.assertGreaterEqual(
                    best, 3.0, f"{name}: phôi chìm vào nền {background} ({best:.2f}:1)")


class TestThemeSwitching(unittest.TestCase):
    def setUp(self):
        palette.set_palette("light")
        palette.notify()

    tearDown = setUp

    def test_doi_bang_mau_thi_cac_lop_ve_tu_doi_theo(self):
        palette.set_palette("dark")
        palette.notify()
        self.assertEqual(svgview.COLOR_CUT, palette.DARK.cut)
        self.assertEqual(machinescene.COLOR_PIPE_FILL, palette.DARK.metal_fill)
        palette.set_palette("light")
        palette.notify()
        self.assertEqual(svgview.COLOR_CUT, palette.LIGHT.cut)
        self.assertEqual(machinescene.COLOR_PIPE_FILL, palette.LIGHT.metal_fill)

    def test_ten_la_thi_quay_ve_bang_mau_sang(self):
        self.assertIs(palette.set_palette("khong-co-that"), palette.LIGHT)

    def test_nap_palette_khong_keo_theo_tkinter(self):
        """Phần sinh G-code và xuất SVG phải chạy được trên máy không đồ hoạ."""
        import subprocess
        import sys
        code = ("import sys; import pipecut.palette, pipecut.svgview, "
                "pipecut.machinescene; "
                "sys.exit(1 if 'tkinter' in sys.modules else 0)")
        self.assertEqual(subprocess.call([sys.executable, "-c", code], cwd=REPO), 0)


class TestNoHardcodedColours(unittest.TestCase):
    """Màu phải lấy từ bảng màu, không rải rác trong mã."""

    FILES = ["pipecut/svgview.py", "pipecut/machinescene.py",
             "pipecut/ui/app.py", "pipecut/ui/canvasview.py",
             "pipecut/ui/machineview.py", "pipecut/ui/widgets.py"]
    HEX = re.compile(r"#[0-9a-fA-F]{6}")

    def test_khong_con_ma_mau_cung_ngoai_bang_mau(self):
        for rel in self.FILES:
            with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
                text = fh.read()
            found = {m for m in self.HEX.findall(text)}
            # màu mặc định của kiểu dữ liệu Prim là ngoại lệ duy nhất
            found.discard("#000000")
            self.assertFalse(found, f"{rel} còn màu cứng: {sorted(found)}")


if __name__ == "__main__":
    unittest.main()
