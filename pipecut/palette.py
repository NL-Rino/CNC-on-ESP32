"""Bảng màu dùng chung cho toàn bộ phần mềm.

Mọi màu sắc trong giao diện đều lấy từ **một chỗ duy nhất** ở đây, nên đổi
tông màu hay thêm chế độ mới chỉ phải sửa một tệp - các lớp vẽ (bản xem trước,
khung mô phỏng máy, bảng điều khiển) đều hỏi bảng màu đang dùng chứ không tự
chọn màu.

Tông màu lấy theo **FreeCAD**: khung nhìn nền chuyển sắc xanh lam đặc trưng,
khung điều khiển màu xám trung tính, điểm nhấn xanh dương, và các màu báo
trạng thái đủ đậm để đọc được trên cả nền sáng lẫn nền tối.

Tệp này **không nạp Tkinter**, nên phần sinh G-code, xuất bản vẽ SVG và các
bài kiểm thử đều dùng được mà không cần môi trường đồ hoạ.  Phần áp bảng màu
lên widget nằm ở ``pipecut.ui.theme``.

Mọi cặp màu chữ/nền trong hai bảng đều đã soát theo tiêu chuẩn tương phản
WCAG AA (4.5:1 cho chữ, 3:1 cho nét vẽ) - xem ``tests/test_theme.py``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Palette:
    """Toàn bộ màu của một chế độ hiển thị."""

    name: str
    label: str
    dark: bool

    # --- nền và khung ---
    bg: str              # nền cửa sổ
    surface: str         # nền khung nổi (LabelFrame, thẻ)
    surface_alt: str     # nền phụ: sọc xen kẽ, thanh công cụ
    field: str           # nền ô nhập liệu
    border: str
    border_soft: str

    # --- chữ ---
    fg: str
    fg_dim: str          # chữ phụ, ghi chú
    fg_faint: str        # chữ mờ nhất, gợi ý

    # --- điểm nhấn ---
    accent: str
    accent_fg: str       # chữ nằm trên nền accent
    accent_soft: str     # nền nhạt cùng tông accent
    accent_hover: str

    # --- màu báo trạng thái (chữ, nền) ---
    ok: str
    ok_soft: str
    warn: str
    warn_soft: str
    danger: str
    danger_soft: str

    # --- khung nhìn ---
    view_top: str        # đỉnh nền chuyển sắc (kiểu FreeCAD)
    view_bottom: str     # đáy nền chuyển sắc
    view_flat: str       # nền phẳng cho bản vẽ trải phẳng
    grid: str
    grid_major: str

    # --- đường chạy dao ---
    cut: str
    mark: str
    lead: str
    rapid: str
    tool: str
    tool_ring: str
    pipe_line: str
    pipe_fill: str
    metal_fill: str      # thân phôi trong khung nhìn 3D
    metal_edge: str      # cạnh phôi trong khung nhìn 3D
    torch_on: str

    # --- bảng điều khiển dạng dòng lệnh ---
    console_bg: str
    console_fg: str
    console_tx: str
    console_rx: str
    console_err: str
    console_ok: str
    console_info: str
    highlight: str       # nền dòng G-code đang chạy

    def hex_to_rgb(self, color: str) -> Tuple[int, int, int]:
        c = color.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))

    def mix(self, a: str, b: str, t: float) -> str:
        """Trộn hai màu theo tỉ lệ ``t`` (0 = toàn a, 1 = toàn b)."""
        ra, ga, ba = self.hex_to_rgb(a)
        rb, gb, bb = self.hex_to_rgb(b)
        t = max(0.0, min(1.0, t))
        return "#%02x%02x%02x" % (round(ra + (rb - ra) * t),
                                  round(ga + (gb - ga) * t),
                                  round(ba + (bb - ba) * t))

    def ink_on(self, background: str) -> str:
        """Chọn chữ đen hay trắng cho vừa nền, theo độ sáng cảm nhận được.

        Cùng một màu "nguy hiểm" nhưng ở chế độ sáng thì đậm (cần chữ trắng),
        ở chế độ tối lại nhạt (cần chữ đen) - để hàm này quyết định thì khỏi
        phải nhớ.
        """
        def channel(v: float) -> float:
            v /= 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        r, g, b = self.hex_to_rgb(background)
        lum = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
        # tương phản với trắng so với tương phản với đen
        return "#101418" if (1.05 / (lum + 0.05)) < ((lum + 0.05) / 0.05) else "#ffffff"

    def fade(self, color: str, t: float) -> str:
        """Làm nhạt một màu về phía nền - dùng cho nét phụ, lưới, bóng."""
        return self.mix(color, self.view_flat, t)


# --------------------------------------------------------------------------
# Hai chế độ hiển thị
# --------------------------------------------------------------------------
LIGHT = Palette(
    name="light", label="Sáng", dark=False,
    bg="#e8ecf1", surface="#f3f6f9", surface_alt="#dfe5ec",
    field="#ffffff", border="#b8c2ce", border_soft="#ccd4dd",
    fg="#1d242c", fg_dim="#55616e", fg_faint="#5e6a76",
    accent="#1f6cba", accent_fg="#ffffff", accent_soft="#dbeafb",
    accent_hover="#17579b",
    ok="#1f7a3d", ok_soft="#e0f4e6",
    warn="#9a6b00", warn_soft="#fdf1dd",
    danger="#b3261e", danger_soft="#fce9e7",
    # nền chuyển sắc xanh lam đặc trưng của khung nhìn FreeCAD
    view_top="#5b8fc4", view_bottom="#cadcee", view_flat="#fdfefe",
    grid="#e6ebf0", grid_major="#ccd6e0",
    cut="#d93f21", mark="#2d7dd2", lead="#12925c", rapid="#828e9a",
    tool="#20272e", tool_ring="#ff8c1a",
    pipe_line="#7d8b99", pipe_fill="#eef2f6",
    metal_fill="#eaeff4", metal_edge="#374048", torch_on="#ff7a1a",
    console_bg="#141a21", console_fg="#c8d2dc",
    console_tx="#7fc8ff", console_rx="#aab6c2", console_err="#ff8a7a",
    console_ok="#7fdc9b", console_info="#f2c66d", highlight="#fff2c2",
)

DARK = Palette(
    name="dark", label="Tối", dark=True,
    bg="#2b3036", surface="#343a41", surface_alt="#22262b",
    field="#1e2227", border="#4a525b", border_soft="#3b424a",
    fg="#e2e8ee", fg_dim="#a3aeba", fg_faint="#98a4b0",
    accent="#4a9eeb", accent_fg="#0d1319", accent_soft="#20364b",
    accent_hover="#6bb2f2",
    ok="#4fc47c", ok_soft="#1b3326",
    warn="#e0a53a", warn_soft="#3a2e17",
    danger="#f0705e", danger_soft="#3d211e",
    # cùng dải xanh lam nhưng tối hẳn, giữ đúng cảm giác FreeCAD Dark
    view_top="#1d344a", view_bottom="#33526f", view_flat="#20262c",
    grid="#2d343b", grid_major="#3b444d",
    cut="#ff6b4a", mark="#58b0ff", lead="#35c98b", rapid="#6f7b87",
    tool="#f0f4f8", tool_ring="#ffa33d",
    pipe_line="#8f9daa", pipe_fill="#2a3138",
    metal_fill="#c6d0da", metal_edge="#39424b", torch_on="#ff9433",
    console_bg="#171c21", console_fg="#c4cdd6",
    console_tx="#7fc8ff", console_rx="#9aa6b2", console_err="#ff8a7a",
    console_ok="#7fdc9b", console_info="#f2c66d", highlight="#4a4326",
)

THEMES: Dict[str, Palette] = {p.name: p for p in (LIGHT, DARK)}


# --------------------------------------------------------------------------
# Ghi nhớ lựa chọn của người dùng
# --------------------------------------------------------------------------
def _settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, ".pipecut", "giao-dien.json")


def load_preference(default: str = "light") -> str:
    """Đọc chế độ hiển thị đã chọn lần trước."""
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            name = str(json.load(fh).get("theme", default))
    except Exception:
        return default
    return name if name in THEMES else default


def save_preference(name: str) -> None:
    """Ghi nhớ chế độ hiển thị; hỏng thì bỏ qua, không làm phiền người dùng."""
    try:
        path = _settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"theme": name}, fh)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Bảng màu đang dùng - các lớp vẽ hỏi qua đây
# --------------------------------------------------------------------------
_current: Palette = LIGHT
_listeners: List[Callable[[Palette], None]] = []


def current() -> Palette:
    return _current


def on_change(callback: Callable[[Palette], None]) -> None:
    """Đăng ký một hàm được gọi lại mỗi khi đổi chế độ hiển thị."""
    if callback not in _listeners:
        _listeners.append(callback)


def set_palette(name: str) -> Palette:
    global _current
    _current = THEMES.get(name, LIGHT)
    return _current


def notify() -> None:
    for cb in list(_listeners):
        try:
            cb(_current)
        except Exception:
            pass


