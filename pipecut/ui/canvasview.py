"""Khung xem trước đường chạy dao trên Canvas của Tkinter.

Hai chế độ:

* **Trải phẳng** - ngang là chiều dài ống, dọc là chu vi.  Đây là khung nhìn
  để đo đạc: mọi khoảng cách trên hình đúng bằng khoảng cách thật trên bề mặt.
* **Ba chiều** - hình chiếu trục đo, có ẩn nét khuất, để hình dung nhát cắt.

Trong lúc máy chạy, vị trí mũi cắt được vẽ theo thời gian thực từ báo cáo
trạng thái của FluidNC.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Sequence, Tuple

from ..config import MachineProfile
from ..pathops import Pass

COLOR_BG = "#ffffff"
COLOR_CUT = "#e2452a"
COLOR_MARK = "#2b7fd4"
COLOR_LEAD = "#22a06b"
COLOR_RAPID = "#b6bec6"
COLOR_PIPE = "#cfd6dd"
COLOR_GRID = "#eef1f4"
COLOR_TOOL = "#111111"
COLOR_TEXT = "#5a646e"


class _Camera:
    def __init__(self, azimuth_deg: float = 32.0, elevation_deg: float = 22.0):
        az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
        self.dir = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
        d = self.dir
        r = (-d[1], d[0], 0.0)   # tích có hướng của trục Z thế giới với hướng nhìn
        n = math.hypot(r[0], r[1]) or 1.0
        self.right = (r[0] / n, r[1] / n, 0.0)
        rr = self.right
        self.up = (d[1] * rr[2] - d[2] * rr[1],
                   d[2] * rr[0] - d[0] * rr[2],
                   d[0] * rr[1] - d[1] * rr[0])

    def project(self, p: Tuple[float, float, float]) -> Tuple[float, float]:
        return (sum(a * b for a, b in zip(p, self.right)),
                -sum(a * b for a, b in zip(p, self.up)))

    def visible(self, section, v: float) -> bool:
        psi = math.radians(section.normal_angle(v % section.perimeter))
        n = (0.0, math.sin(psi), math.cos(psi))
        return sum(x * y for x, y in zip(n, self.dir)) > -0.02


class PreviewCanvas(ttk.Frame):
    """Khung vẽ có zoom/pan bằng chuột."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.profile: Optional[MachineProfile] = None
        self.section = None
        self.passes: List[Pass] = []
        self.mode = tk.StringVar(value="flat")
        self.show_rapids = tk.BooleanVar(value=True)
        self.cam = _Camera()
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._drag: Optional[Tuple[int, int]] = None
        self._tool: Optional[Tuple[float, float]] = None

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", pady=(0, 4))
        ttk.Radiobutton(bar, text="Trải phẳng", value="flat", variable=self.mode,
                        command=self.refit).pack(side="left")
        ttk.Radiobutton(bar, text="Ba chiều", value="iso", variable=self.mode,
                        command=self.refit).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(bar, text="Chạy không", variable=self.show_rapids,
                        command=self.redraw).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Vừa khung", width=10, command=self.refit).pack(side="right")
        self.info = ttk.Label(bar, text="", foreground=COLOR_TEXT)
        self.info.pack(side="right", padx=10)

        self.canvas = tk.Canvas(self, background=COLOR_BG, highlightthickness=1,
                                highlightbackground="#dde2e7")
        self.canvas.pack(side="top", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        self.canvas.bind("<MouseWheel>", self._on_wheel)          # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.15))   # Linux
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.15))

    # ------------------------------------------------------------------
    def set_data(self, profile: MachineProfile, passes: Sequence[Pass]) -> None:
        self.profile = profile
        self.section = profile.pipe.section()
        self.passes = list(passes)
        self._tool = None
        self.refit()

    def set_tool_position(self, x: float, v: float) -> None:
        """Vị trí mũi cắt, ``v`` là vị trí cung trên bề mặt phôi."""
        self._tool = (x, v)
        self._draw_tool()

    # ------------------------------------------------------------------
    def _world_points(self) -> List[Tuple[float, float]]:
        """Toàn bộ điểm ở toạ độ thế giới của chế độ đang xem."""
        pts: List[Tuple[float, float]] = []
        if not self.profile or not self.section:
            return pts
        sec = self.section
        per = sec.perimeter
        length = max(self.profile.pipe.length, 1.0)
        if self.mode.get() == "flat":
            pts.extend([(0.0, 0.0), (length, per)])
            for ps in self.passes:
                for p in ps.points:
                    pts.append((p.x, p.v % per))
        else:
            for xx in (0.0, length):
                for i in range(36):
                    pts.append(self.cam.project(_surface(sec, xx, per * i / 36)))
            for ps in self.passes:
                for p in ps.points:
                    pts.append(self.cam.project(_surface(sec, p.x, p.v)))
        return pts

    def refit(self) -> None:
        pts = self._world_points()
        w = max(self.canvas.winfo_width(), 50)
        h = max(self.canvas.winfo_height(), 50)
        if not pts:
            self._scale, self._ox, self._oy = 1.0, 20.0, 20.0
            self.redraw()
            return
        x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
        y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
        pad = 28.0
        sx = (w - 2 * pad) / max(x1 - x0, 1e-6)
        sy = (h - 2 * pad) / max(y1 - y0, 1e-6)
        self._scale = max(1e-4, min(sx, sy))
        self._ox = pad - x0 * self._scale + (w - 2 * pad - (x1 - x0) * self._scale) / 2
        self._oy = pad - y0 * self._scale + (h - 2 * pad - (y1 - y0) * self._scale) / 2
        self.redraw()

    def _to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        return (self._ox + wx * self._scale, self._oy + wy * self._scale)

    # ------------------------------------------------------------------
    def _on_press(self, event) -> None:
        self._drag = (event.x, event.y)

    def _on_drag(self, event) -> None:
        if not self._drag:
            return
        dx = event.x - self._drag[0]
        dy = event.y - self._drag[1]
        self._drag = (event.x, event.y)
        self._ox += dx
        self._oy += dy
        self.redraw()

    def _on_wheel(self, event) -> None:
        factor = 1.15 if getattr(event, "delta", 0) > 0 else 1 / 1.15
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, sx: float, sy: float, factor: float) -> None:
        wx = (sx - self._ox) / self._scale
        wy = (sy - self._oy) / self._scale
        self._scale = max(1e-4, min(200.0, self._scale * factor))
        self._ox = sx - wx * self._scale
        self._oy = sy - wy * self._scale
        self.redraw()

    # ------------------------------------------------------------------
    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        if not self.profile:
            c.create_text(20, 20, anchor="nw", text="Chưa có đường chạy dao",
                          fill=COLOR_TEXT)
            return
        if self.mode.get() == "flat":
            self._draw_flat()
        else:
            self._draw_iso()
        self._draw_tool()
        n = sum(len(p.points) for p in self.passes)
        self.info.configure(text=f"{len(self.passes)} đường · {n} điểm · "
                                 f"tỉ lệ {self._scale:.2f} px/mm")

    def _draw_flat(self) -> None:
        c = self.canvas
        pf = self.profile
        sec = self.section
        circ = sec.perimeter
        length = max(pf.pipe.length, 1.0)
        a = self._to_screen(0, 0)
        b = self._to_screen(length, circ)
        c.create_rectangle(a[0], a[1], b[0], b[1], outline=COLOR_PIPE, fill="#fbfcfd")
        for k in range(1, 4):
            vk = sec.s_of_theta(90.0 * k)
            y = self._to_screen(0, vk)[1]
            c.create_line(a[0], y, b[0], y, fill=COLOR_GRID)
            c.create_text(a[0] - 4, y, anchor="e", text=f"{90 * k}°", fill=COLOR_TEXT,
                          font=("TkDefaultFont", 7))
        for br in sec.breakpoints():      # cạnh của ống hộp
            if 0 < br < circ:
                y = self._to_screen(0, br)[1]
                c.create_line(a[0], y, b[0], y, fill=COLOR_PIPE, dash=(3, 3))
        step = _nice_step(length)
        x = 0.0
        while x <= length + 1e-6:
            sx = self._to_screen(x, 0)[0]
            c.create_line(sx, a[1], sx, b[1], fill=COLOR_GRID)
            c.create_text(sx, b[1] + 4, anchor="n", text=f"{x:g}", fill=COLOR_TEXT,
                          font=("TkDefaultFont", 7))
            x += step

        prev_end = None
        for ps in self.passes:
            color = COLOR_MARK if ps.kind == "mark" else COLOR_CUT
            if self.show_rapids.get() and prev_end is not None:
                p0 = self._to_screen(prev_end[0], prev_end[1] % circ)
                p1 = self._to_screen(ps.points[0].x, ps.points[0].v % circ)
                c.create_line(p0[0], p0[1], p1[0], p1[1], fill=COLOR_RAPID, dash=(4, 3))
            seg: List[float] = []
            prev_v = None
            for p in ps.points:
                v = p.v % circ
                if prev_v is not None and abs(v - prev_v) > circ / 2:
                    self._flush(seg, color, 2)   # chỗ vòng qua mốc 0
                    seg = []
                prev_v = v
                sx, sy = self._to_screen(p.x, v)
                seg.extend([sx, sy])
            self._flush(seg, color, 2)
            if ps.lead_in_count:
                lead: List[float] = []
                for p in ps.points[:ps.lead_in_count + 1]:
                    sx, sy = self._to_screen(p.x, p.v % circ)
                    lead.extend([sx, sy])
                self._flush(lead, COLOR_LEAD, 2)
            p0 = ps.points[0]
            s = self._to_screen(p0.x, p0.v % circ)
            c.create_oval(s[0] - 3, s[1] - 3, s[0] + 3, s[1] + 3, fill=COLOR_LEAD, outline="")
            prev_end = (ps.points[-1].x, ps.points[-1].v)

    def _draw_iso(self) -> None:
        c = self.canvas
        pf = self.profile
        sec = self.section
        per = sec.perimeter
        length = max(pf.pipe.length, 1.0)
        marks = sorted(set([per * k / 24 for k in range(24)]
                           + [b for b in sec.breakpoints() if b < per]))
        for v in marks:
            if not self.cam.visible(sec, v):
                continue
            p0 = self._to_screen(*self.cam.project(_surface(sec, 0.0, v)))
            p1 = self._to_screen(*self.cam.project(_surface(sec, length, v)))
            c.create_line(p0[0], p0[1], p1[0], p1[1], fill=COLOR_PIPE)
        for xx in (0.0, length):
            pts: List[float] = []
            for i in range(97):
                s = self._to_screen(*self.cam.project(_surface(sec, xx, per * i / 96)))
                pts.extend(s)
            c.create_line(*pts, fill=COLOR_PIPE)

        prev_end = None
        for ps in self.passes:
            color = COLOR_MARK if ps.kind == "mark" else COLOR_CUT
            seg: List[float] = []
            for p in ps.points:
                if self.cam.visible(sec, p.v):
                    s = self._to_screen(*self.cam.project(_surface(sec, p.x, p.v)))
                    seg.extend(s)
                else:
                    self._flush(seg, color, 2)
                    seg = []
            self._flush(seg, color, 2)
            if self.show_rapids.get() and prev_end is not None:
                p0 = self._to_screen(*self.cam.project(_surface(sec, prev_end[0], prev_end[1])))
                p1 = self._to_screen(*self.cam.project(_surface(sec, ps.points[0].x, ps.points[0].v)))
                c.create_line(p0[0], p0[1], p1[0], p1[1], fill=COLOR_RAPID, dash=(4, 3))
            prev_end = (ps.points[-1].x, ps.points[-1].v)

    def _flush(self, coords: List[float], color: str, width: int) -> None:
        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill=color, width=width,
                                    capstyle="round", joinstyle="round")

    def _draw_tool(self) -> None:
        self.canvas.delete("tool")
        if not self._tool or not self.profile:
            return
        x, v = self._tool
        if not self.section:
            return
        if self.mode.get() == "flat":
            s = self._to_screen(x, v % self.section.perimeter)
        else:
            s = self._to_screen(*self.cam.project(_surface(self.section, x, v)))
        self.canvas.create_oval(s[0] - 5, s[1] - 5, s[0] + 5, s[1] + 5,
                                outline=COLOR_TOOL, width=2, tags="tool")
        self.canvas.create_line(s[0] - 9, s[1], s[0] + 9, s[1], fill=COLOR_TOOL, tags="tool")
        self.canvas.create_line(s[0], s[1] - 9, s[0], s[1] + 9, fill=COLOR_TOOL, tags="tool")


def _surface(section, x: float, v: float) -> Tuple[float, float, float]:
    """Điểm trên bề mặt phôi ở toạ độ trải phẳng (x, v) -> toạ độ 3D."""
    cx, cy = section.point_at(v % section.perimeter)
    return (x, cx, cy)


def _nice_step(span: float) -> float:
    raw = span / 8.0
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if raw <= step:
            return float(step)
    return 1000.0
