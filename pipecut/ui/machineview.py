"""Khung mô phỏng máy ba chiều trên Canvas của Tkinter.

Phần hình học nằm ở `pipecut/machinescene.py` (không phụ thuộc Tkinter); module
này chỉ lo hiển thị: đổi toạ độ camera sang điểm ảnh, vẽ, và xử lý chuột.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Sequence, Tuple

from ..config import MachineProfile
from ..gsim import Playback, SimState, TracePoint
from ..machinescene import (
    Camera,
    Prim,
    axis_readout,
    axis_triad,
    build_scene,
    scene_bounds,
)

from . import theme

COLOR_BG = COLOR_TEXT = COLOR_EDGE = COLOR_DIM = ""


def _sync_colors(p=None) -> None:
    global COLOR_BG, COLOR_TEXT, COLOR_EDGE, COLOR_DIM
    p = p or theme.current()
    COLOR_BG = p.view_flat
    COLOR_TEXT = p.fg
    COLOR_EDGE = p.border
    COLOR_DIM = p.fg_dim


_sync_colors()
theme.on_change(_sync_colors)


class MachineView(ttk.Frame):
    """Canvas mô phỏng máy, cập nhật theo trạng thái bốn trục."""

    TRACE_DRAW_LIMIT = 900     # số điểm vết cắt vẽ tối đa mỗi khung hình

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.profile: Optional[MachineProfile] = None
        self.playback: Optional[Playback] = None
        self.cam = Camera()
        self.state = SimState()
        self._trace: List[TracePoint] = []
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._drag: Optional[Tuple[int, int, str]] = None
        # "work" = nhìn cận vùng cắt quanh mỏ (mặc định), "all" = toàn cảnh
        self.focus = "work"
        self.show_frame = tk.BooleanVar(value=True)
        self.show_trace = tk.BooleanVar(value=True)

        self.canvas = tk.Canvas(self, background=COLOR_BG, highlightthickness=1,
                                highlightbackground=COLOR_EDGE)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.refit())
        self.canvas.bind("<ButtonPress-1>", lambda e: self._press(e, "orbit"))
        self.canvas.bind("<ButtonPress-3>", lambda e: self._press(e, "pan"))
        self.canvas.bind("<Shift-ButtonPress-1>", lambda e: self._press(e, "pan"))
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<B3-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: self._release())
        self.canvas.bind("<ButtonRelease-3>", lambda _e: self._release())
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom(1.12, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self._zoom(1 / 1.12, e.x, e.y))
        self.canvas.bind("<Double-Button-1>", lambda _e: self.toggle_focus())

    # ==================================================================
    def set_profile(self, profile: MachineProfile) -> None:
        self.profile = profile
        self.refit()

    def set_playback(self, playback: Optional[Playback]) -> None:
        self.playback = playback
        self._trace = []
        self.refit()

    def set_state(self, state: SimState,
                  trace: Optional[Sequence[TracePoint]] = None) -> None:
        self.state = state
        if trace is not None:
            self._trace = list(trace)
        self.redraw()

    def reset_view(self) -> None:
        self.cam = Camera()
        self.refit()

    def set_focus(self, focus: str) -> None:
        self.focus = "all" if focus == "all" else "work"
        self.refit()

    def toggle_focus(self) -> str:
        """Chuyển qua lại giữa nhìn cận vùng cắt và toàn cảnh (nháy đúp chuột)."""
        self.set_focus("all" if self.focus == "work" else "work")
        if self.on_focus_change:
            self.on_focus_change(self.focus)
        return self.focus

    on_focus_change = None

    # ==================================================================
    def _press(self, event, mode: str) -> None:
        self._drag = (event.x, event.y, mode)

    def _release(self) -> None:
        self._drag = None

    def _motion(self, event) -> None:
        if not self._drag:
            return
        x0, y0, mode = self._drag
        dx, dy = event.x - x0, event.y - y0
        self._drag = (event.x, event.y, mode)
        if mode == "orbit":
            self.cam.orbit(-dx * 0.5, dy * 0.5)
        else:
            self._ox += dx
            self._oy += dy
        self.redraw()

    def _wheel(self, event) -> None:
        self._zoom(1.12 if getattr(event, "delta", 0) > 0 else 1 / 1.12, event.x, event.y)

    def _zoom(self, factor: float, cx: Optional[float] = None,
              cy: Optional[float] = None) -> None:
        """Phóng to/thu nhỏ **quanh con trỏ chuột** - chỗ đang chỉ vào đứng yên."""
        if cx is None:
            cx, cy = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        new = max(0.02, min(200.0, self._scale * factor))
        f = new / self._scale
        self._ox = cx - (cx - self._ox) * f
        self._oy = cy - (cy - self._oy) * f
        self._scale = new
        self.redraw()

    # ==================================================================
    def refit(self) -> None:
        if not self.profile:
            return
        w = max(self.canvas.winfo_width(), 50)
        h = max(self.canvas.winfo_height(), 50)
        x0, y0, x1, y1 = scene_bounds(self.profile, self.cam, self.state,
                                      self._along_range(), focus=self.focus)
        pad = 34.0
        self._scale = max(0.02, min((w - 2 * pad) / max(x1 - x0, 1e-6),
                                    (h - 2 * pad) / max(y1 - y0, 1e-6)))
        self._ox = w / 2 - (x0 + x1) / 2 * self._scale
        self._oy = h / 2 - (y0 + y1) / 2 * self._scale
        self.redraw()

    def _along_range(self) -> Optional[Tuple[float, float]]:
        """Khoảng trượt của ống trong chương trình - để khung nhìn đứng yên."""
        if not self.playback or not self.profile:
            return None
        from ..config import ROLE_ALONG
        letter = self.profile.letter(ROLE_ALONG)
        return self.playback.axis_range(letter) if letter else None

    def _px(self, p: Tuple[float, float]) -> Tuple[float, float]:
        return (self._ox + p[0] * self._scale, self._oy + p[1] * self._scale)

    # ==================================================================
    def apply_theme(self) -> None:
        """Đổi màu khung nhìn khi người dùng chuyển chế độ hiển thị."""
        _sync_colors()
        self.canvas.configure(background=COLOR_BG, highlightbackground=COLOR_EDGE)
        self.redraw()

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        # Nền chuyển sắc dọc như khung nhìn 3D của FreeCAD: đậm ở trên, nhạt
        # dần xuống dưới, giúp nhìn ra chiều sâu mà không cần đổ bóng.
        pal = theme.current()
        theme.paint_gradient(c, c.winfo_width(), c.winfo_height(),
                             pal.view_top, pal.view_bottom)
        if not self.profile:
            c.create_text(16, 16, anchor="nw", fill=COLOR_TEXT,
                          text="Chưa có chương trình để mô phỏng")
            return
        plan = self.playback.trace if (self.playback and self.show_trace.get()) else ()
        for prim in build_scene(self.profile, self.state, self._trace, self.cam,
                                show_frame=self.show_frame.get(),
                                show_trace=self.show_trace.get(),
                                trace_limit=self.TRACE_DRAW_LIMIT,
                                plan=plan):
            self._draw(prim)
        self._draw_labels()

    def _draw(self, prim: Prim) -> None:
        pts = [v for p in prim.points for v in self._px(p)]
        if prim.kind == "fill" and len(pts) >= 6:
            self.canvas.create_polygon(pts, fill=prim.fill or "", outline=prim.color,
                                       width=prim.width)
        elif prim.kind == "dot" and len(pts) >= 2:
            r = prim.radius
            self.canvas.create_oval(pts[0] - r, pts[1] - r, pts[0] + r, pts[1] + r,
                                    fill=prim.fill or prim.color, outline="")
        elif prim.kind == "text" and len(pts) >= 2:
            t = self.canvas.create_text(pts[0], pts[1], anchor="w", fill=prim.color,
                                        font=("TkDefaultFont", 9, "bold"), text=prim.text)
            if prim.fill:
                b = self.canvas.bbox(t)
                if b:
                    bg = self.canvas.create_rectangle(b[0] - 4, b[1] - 2, b[2] + 4, b[3] + 2,
                                                      fill=prim.fill, outline="")
                    self.canvas.tag_lower(bg, t)
        elif len(pts) >= 4:
            self.canvas.create_line(pts, fill=prim.color, width=prim.width,
                                    capstyle="round", joinstyle="round",
                                    dash=prim.dash or None)

    def _draw_labels(self) -> None:
        """Bảng số toạ độ, ghi chú và ba trục - chữ sáng trên nền tối cho dễ đọc.

        Khung nhìn 3D luôn nền xanh (cả chế độ sáng lẫn tối), nên chữ ở đây
        không dùng màu chữ của giao diện mà dùng bộ màu riêng của khung nhìn.
        """
        c = self.canvas
        pf = self.profile
        pal = theme.current()
        items = []
        y = 14
        for row in axis_readout(pf, self.state):
            items.append(c.create_text(16, y, anchor="nw", fill=pal.hud_fg,
                                       font=("Consolas", 11), text=row))
            y += 18
        items.append(c.create_text(16, y + 4, anchor="nw", fill=pal.hud_fg,
                                   font=("TkDefaultFont", 9),
                                   text=f"{pf.pipe.size_text} × dài {pf.pipe.length:g} mm"))
        y += 22
        if self.state.torch:
            items.append(c.create_text(16, y + 2, anchor="nw", fill=pal.torch_on,
                                       font=("TkDefaultFont", 10, "bold"),
                                       text="● NGUỒN CẮT ĐANG BẬT"))
        box = c.bbox(*items)
        if box:
            panel = c.create_rectangle(box[0] - 8, box[1] - 6, box[2] + 10, box[3] + 7,
                                       fill=pal.hud_bg, outline=pal.machine_edge)
            c.tag_lower(panel, items[0])
        # ba trục nhỏ ở góc dưới trái
        h = max(self.canvas.winfo_height(), 100)
        ox, oy = 46, h - 46
        c.create_oval(ox - 34, oy - 34, ox + 34, oy + 34, fill=pal.hud_bg, outline="")
        for dx, dy, color, letter in axis_triad(pf, self.cam, 24.0):
            c.create_line(ox, oy, ox + dx, oy + dy, fill=color, width=3, capstyle="round")
            c.create_text(ox + dx * 1.3, oy + dy * 1.3, fill=color,
                          font=("TkDefaultFont", 9, "bold"), text=letter)
        w = max(self.canvas.winfo_width(), 100)
        hint = ("kéo trái: xoay · kéo phải: dịch · lăn chuột: phóng to · nháy đúp: "
                + ("toàn cảnh" if self.focus == "work" else "vùng cắt"))
        t = c.create_text(w - 14, 14, anchor="ne", fill=pal.hud_fg,
                          font=("TkDefaultFont", 8), text=hint)
        b = c.bbox(t)
        if b:
            bg = c.create_rectangle(b[0] - 6, b[1] - 3, b[2] + 6, b[3] + 3,
                                    fill=pal.hud_bg, outline="")
            c.tag_lower(bg, t)
