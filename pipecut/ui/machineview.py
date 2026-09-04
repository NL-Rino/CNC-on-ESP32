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
    COLOR_TORCH_HOT,
    Camera,
    Prim,
    axis_readout,
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
        self.canvas.bind("<Button-4>", lambda e: self._zoom(1.12))
        self.canvas.bind("<Button-5>", lambda e: self._zoom(1 / 1.12))

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
        self._zoom(1.12 if getattr(event, "delta", 0) > 0 else 1 / 1.12)

    def _zoom(self, factor: float) -> None:
        self._scale = max(0.05, min(40.0, self._scale * factor))
        self.redraw()

    # ==================================================================
    def refit(self) -> None:
        if not self.profile:
            return
        w = max(self.canvas.winfo_width(), 50)
        h = max(self.canvas.winfo_height(), 50)
        x0, y0, x1, y1 = scene_bounds(self.profile, self.cam, self.state,
                                      self._along_range())
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
        for prim in build_scene(self.profile, self.state, self._trace, self.cam,
                                show_frame=self.show_frame.get(),
                                show_trace=self.show_trace.get(),
                                trace_limit=self.TRACE_DRAW_LIMIT):
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
        elif len(pts) >= 4:
            self.canvas.create_line(pts, fill=prim.color, width=prim.width,
                                    capstyle="round", joinstyle="round")

    def _draw_labels(self) -> None:
        c = self.canvas
        pf = self.profile
        y = 12
        for row in axis_readout(pf, self.state):
            c.create_text(12, y, anchor="nw", fill=COLOR_TEXT,
                          font=("Consolas", 10), text=row)
            y += 16
        c.create_text(12, y + 4, anchor="nw", fill=COLOR_TEXT, font=("TkDefaultFont", 9),
                      text=f"{pf.pipe.size_text} × dài {pf.pipe.length:g} mm")
        if self.state.torch:
            c.create_text(12, y + 20, anchor="nw", fill=COLOR_TORCH_HOT,
                          font=("TkDefaultFont", 9, "bold"), text="● NGUỒN CẮT ĐANG BẬT")
        w = max(self.canvas.winfo_width(), 100)
        c.create_text(w - 10, 12, anchor="ne", fill=COLOR_DIM, font=("TkDefaultFont", 8),
                      text="kéo trái: xoay góc nhìn · kéo phải: dịch · lăn chuột: phóng to")
