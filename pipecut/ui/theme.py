"""Áp bảng màu lên các widget Tkinter/ttk.

Bảng màu thật nằm ở :mod:`pipecut.palette` (không phụ thuộc Tkinter); tệp này
chỉ dịch nó thành cấu hình ``ttk.Style`` và các tiện ích vẽ.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..palette import (
    DARK,
    LIGHT,
    THEMES,
    Palette,
    current,
    load_preference,
    notify,
    on_change,
    save_preference,
    set_palette,
)

__all__ = ["LIGHT", "DARK", "THEMES", "Palette", "current", "on_change", "notify",
           "set_palette", "load_preference", "save_preference", "apply",
           "paint_gradient"]


# --------------------------------------------------------------------------
# Áp bảng màu lên ttk
# --------------------------------------------------------------------------
def apply(root: tk.Misc, name: str) -> Palette:
    """Đổi toàn bộ giao diện sang một chế độ hiển thị."""
    p = set_palette(name)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")       # 'clam' là theme duy nhất cho đổi màu thoải mái
    except tk.TclError:
        pass

    try:
        root.configure(background=p.bg)
    except tk.TclError:
        pass

    # --- nền và chữ chung ---
    style.configure(".", background=p.bg, foreground=p.fg,
                    fieldbackground=p.field, bordercolor=p.border,
                    lightcolor=p.surface, darkcolor=p.surface_alt,
                    troughcolor=p.surface_alt, focuscolor=p.accent)
    for widget in ("TFrame", "TLabelframe", "TPanedwindow", "TSeparator"):
        style.configure(widget, background=p.bg)
    style.configure("TLabel", background=p.bg, foreground=p.fg)
    style.configure("TLabelframe", bordercolor=p.border, relief="solid",
                    borderwidth=1)
    style.configure("TLabelframe.Label", background=p.bg, foreground=p.accent,
                    font=("TkDefaultFont", 9, "bold"))

    # --- nút ---
    style.configure("TButton", background=p.surface, foreground=p.fg,
                    bordercolor=p.border, focusthickness=1,
                    focuscolor=p.accent, padding=(9, 4), relief="flat")
    style.map("TButton",
              background=[("pressed", p.accent), ("active", p.accent_soft),
                          ("disabled", p.surface_alt)],
              foreground=[("pressed", p.accent_fg),
                          ("disabled", p.fg_faint)],
              bordercolor=[("active", p.accent)])

    # nút nhấn mạnh (Kết nối, Sinh G-code, BẮT ĐẦU CẮT)
    style.configure("Accent.TButton", background=p.accent, foreground=p.accent_fg,
                    bordercolor=p.accent, relief="flat",
                    font=("TkDefaultFont", 9, "bold"))
    style.map("Accent.TButton",
              background=[("pressed", p.accent_hover), ("active", p.accent_hover),
                          ("disabled", p.surface_alt)],
              foreground=[("pressed", p.accent_fg), ("active", p.accent_fg),
                          ("disabled", p.fg_faint)])

    # nút nguy hiểm (DỪNG KHẨN)
    danger_ink = p.ink_on(p.danger)
    style.configure("Danger.TButton", background=p.danger, foreground=danger_ink,
                    bordercolor=p.danger, relief="flat",
                    font=("TkDefaultFont", 9, "bold"))
    style.map("Danger.TButton",
              background=[("pressed", p.danger), ("active", p.danger),
                          ("disabled", p.surface_alt)],
              foreground=[("pressed", danger_ink), ("active", danger_ink),
                          ("disabled", p.fg_faint)])

    # --- ô nhập, hộp chọn ---
    for widget in ("TEntry", "TSpinbox"):
        style.configure(widget, fieldbackground=p.field, foreground=p.fg,
                        bordercolor=p.border, insertcolor=p.fg,
                        arrowcolor=p.fg_dim, padding=3)
        style.map(widget, bordercolor=[("focus", p.accent)],
                  lightcolor=[("focus", p.accent)])
    style.configure("TCombobox", fieldbackground=p.field, foreground=p.fg,
                    background=p.surface, bordercolor=p.border,
                    arrowcolor=p.fg_dim, padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", p.field), ("disabled", p.surface_alt)],
              foreground=[("disabled", p.fg_faint)],
              bordercolor=[("focus", p.accent)],
              arrowcolor=[("active", p.accent)])
    # danh sách xổ xuống của Combobox là widget Tk thuần, phải đặt qua option
    root.option_add("*TCombobox*Listbox.background", p.field)
    root.option_add("*TCombobox*Listbox.foreground", p.fg)
    root.option_add("*TCombobox*Listbox.selectBackground", p.accent)
    root.option_add("*TCombobox*Listbox.selectForeground", p.accent_fg)

    style.configure("TCheckbutton", background=p.bg, foreground=p.fg,
                    indicatorcolor=p.field, focuscolor=p.accent)
    style.map("TCheckbutton",
              indicatorcolor=[("selected", p.accent), ("pressed", p.accent_hover)],
              foreground=[("disabled", p.fg_faint)])
    style.configure("TRadiobutton", background=p.bg, foreground=p.fg,
                    indicatorcolor=p.field)
    style.map("TRadiobutton", indicatorcolor=[("selected", p.accent)])

    # --- thẻ (Notebook) ---
    style.configure("TNotebook", background=p.bg, bordercolor=p.border,
                    tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", background=p.surface_alt, foreground=p.fg_dim,
                    padding=(14, 7), bordercolor=p.border)
    style.map("TNotebook.Tab",
              background=[("selected", p.surface), ("active", p.accent_soft)],
              foreground=[("selected", p.accent), ("active", p.fg)],
              expand=[("selected", (0, 0, 0, 2))])

    # --- bảng danh sách ---
    style.configure("Treeview", background=p.field, fieldbackground=p.field,
                    foreground=p.fg, bordercolor=p.border, rowheight=24)
    style.map("Treeview",
              background=[("selected", p.accent)],
              foreground=[("selected", p.accent_fg)])
    style.configure("Treeview.Heading", background=p.surface_alt,
                    foreground=p.fg_dim, relief="flat",
                    font=("TkDefaultFont", 9, "bold"))
    style.map("Treeview.Heading", background=[("active", p.accent_soft)])

    # --- thanh cuộn, thanh trượt, thanh tiến trình ---
    style.configure("TScrollbar", background=p.surface_alt, troughcolor=p.bg,
                    bordercolor=p.bg, arrowcolor=p.fg_dim, relief="flat")
    style.map("TScrollbar", background=[("active", p.accent_soft)])
    style.configure("TScale", background=p.bg, troughcolor=p.surface_alt)
    style.configure("Horizontal.TProgressbar", background=p.accent,
                    troughcolor=p.surface_alt, bordercolor=p.border,
                    lightcolor=p.accent, darkcolor=p.accent)

    # --- nhãn phụ dùng lại nhiều chỗ ---
    style.configure("Dim.TLabel", background=p.bg, foreground=p.fg_dim)
    style.configure("Faint.TLabel", background=p.bg, foreground=p.fg_faint)
    style.configure("Head.TLabel", background=p.bg, foreground=p.fg,
                    font=("TkDefaultFont", 11, "bold"))
    style.configure("Mono.TLabel", background=p.bg, foreground=p.fg,
                    font=("Consolas", 10))
    style.configure("MonoDim.TLabel", background=p.bg, foreground=p.fg_dim,
                    font=("Consolas", 10))
    style.configure("Status.TLabel", background=p.surface_alt, foreground=p.fg_dim)
    style.configure("Ok.TLabel", background=p.bg, foreground=p.ok)
    style.configure("Warn.TLabel", background=p.bg, foreground=p.warn)
    style.configure("Danger.TLabel", background=p.bg, foreground=p.danger)
    style.configure("Accent.TLabel", background=p.bg, foreground=p.accent)
    style.configure("Hint.TLabel", background=p.bg, foreground=p.fg_faint,
                    font=("TkDefaultFont", 8))
    style.configure("Dro.TLabel", background=p.bg, foreground=p.fg,
                    font=("Consolas", 13))
    style.configure("Card.TFrame", background=p.surface)
    style.configure("Toolbar.TFrame", background=p.surface_alt)
    return p


# --------------------------------------------------------------------------
# Vẽ nền chuyển sắc kiểu khung nhìn FreeCAD
# --------------------------------------------------------------------------
def paint_gradient(canvas: tk.Canvas, width: int, height: int,
                   top: str, bottom: str, steps: int = 40,
                   tag: str = "bg") -> None:
    """Tô nền chuyển sắc dọc.

    Canvas của Tk không có sẵn chuyển sắc, nên vẽ thành nhiều dải ngang.  40
    dải là đủ mượt ở mọi cỡ cửa sổ mà vẫn nhẹ.
    """
    if width <= 0 or height <= 0:
        return
    p = current()
    steps = max(2, steps)
    band = height / steps
    for i in range(steps):
        color = p.mix(top, bottom, i / (steps - 1))
        canvas.create_rectangle(0, i * band - 1, width, (i + 1) * band + 1,
                                fill=color, outline=color, tags=tag)
    canvas.tag_lower(tag)
