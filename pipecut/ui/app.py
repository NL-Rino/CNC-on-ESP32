"""Cửa sổ chính của PipeCut Studio.

Bố cục theo đúng trình tự làm việc thực tế của thợ:

    Máy & Kết nối  ->  Điều khiển tay  ->  Tạo công việc  ->  Xem trước  ->  Chạy

Mọi việc vào/ra cổng COM đều nằm ở luồng nền; luồng giao diện chỉ lấy sự kiện
từ một hàng đợi nên không bao giờ bị "đơ" trong lúc máy đang chạy.
"""

from __future__ import annotations

import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from .. import protocol as proto
from ..config import (
    ROLE_ALONG,
    ROLE_BEVEL,
    ROLE_CROSS,
    ROLE_RADIAL,
    ROLE_ROTARY,
    MachineProfile,
    find_profile,
)
from ..controller import DeviceController, JobProgress
from ..gcode import Program, build_program
from ..gsim import Playback, SimState, TracePoint
from ..jobs import OP_CATALOG, Job, Operation, default_params, ops_for_shape
from ..protocol import MachineStatus
from ..transport import list_ports
from .canvasview import PreviewCanvas
from .machineview import MachineView
from .widgets import PAD, Console, DRO, FieldGrid, ParamForm, StatusBadge

APP_TITLE = "PipeCut Studio - Máy cắt ống 4 trục (ESP32 / FluidNC)"

# Nhãn hiển thị cho từng dạng tiết diện phôi
SHAPE_LABEL = {"round": "Ống tròn", "square": "Ống hộp vuông",
               "rect": "Ống hộp chữ nhật"}
LABEL_SHAPE = {v: k for k, v in SHAPE_LABEL.items()}

# Cách vượt qua góc lượn của ống hộp
CORNER_LABEL = {"follow": "Cắt liền mạch qua góc",
                "pivot": "Xoay 45° đưa góc lên đỉnh rồi cắt",
                "index": "Dừng cắt, xoay 90° bỏ qua góc"}
LABEL_CORNER = {v: k for k, v in CORNER_LABEL.items()}


class MainWindow:
    """Toàn bộ giao diện."""

    def __init__(self, root: tk.Tk, profile_path: Optional[str] = None,
                 job_path: Optional[str] = None):
        self.root = root
        self.profile = MachineProfile.load(profile_path) if profile_path else find_profile()
        self.profile_path = profile_path or ""
        self.job = Job(name="cong-viec-moi")
        self.program: Optional[Program] = None
        self.controller = DeviceController(self.profile)
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self._last_status_draw = 0.0
        # trạng thái tab mô phỏng
        self.playback: Optional[Playback] = None
        self.sim_time = 0.0
        self.sim_playing = False
        self._sim_last_tick = 0.0
        self._sim_updating = False
        self._live_trace: List[TracePoint] = []
        self._live_torch = False
        self._live_pen_up = True
        self._match_index = 0

        root.title(APP_TITLE)
        root.geometry("1280x820")
        root.minsize(1024, 680)
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass

        self._build_layout()
        self._wire_controller()
        if job_path and os.path.exists(job_path):
            self._load_job(job_path)
        else:
            self._seed_demo_job()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(60, self._pump_events)
        self.root.after(40, self._sim_tick)

    # ==================================================================
    # Dựng giao diện
    # ==================================================================
    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=(PAD, PAD, PAD, 0))
        top.pack(side="top", fill="x")
        self.badge = StatusBadge(top)
        self.badge.pack(side="left")
        self.lbl_conn = ttk.Label(top, text="Chưa kết nối", foreground="#5a646e")
        self.lbl_conn.pack(side="left", padx=10)
        self.lbl_pos = ttk.Label(top, text="", font=("Consolas", 10))
        self.lbl_pos.pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side="top", fill="both", expand=True, padx=PAD, pady=PAD)
        self.tab_machine = ttk.Frame(self.nb, padding=PAD)
        self.tab_control = ttk.Frame(self.nb, padding=PAD)
        self.tab_job = ttk.Frame(self.nb, padding=PAD)
        self.tab_preview = ttk.Frame(self.nb, padding=PAD)
        self.tab_sim = ttk.Frame(self.nb, padding=PAD)
        self.tab_run = ttk.Frame(self.nb, padding=PAD)
        self.nb.add(self.tab_machine, text="1. Máy & Kết nối")
        self.nb.add(self.tab_control, text="2. Điều khiển")
        self.nb.add(self.tab_job, text="3. Công việc")
        self.nb.add(self.tab_preview, text="4. Xem trước")
        self.nb.add(self.tab_sim, text="5. Mô phỏng")
        self.nb.add(self.tab_run, text="6. Chạy")

        self._build_machine_tab()
        self._build_control_tab()
        self._build_job_tab()
        self._build_preview_tab()
        self._build_sim_tab()
        self._build_run_tab()

        self.status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(side="bottom", fill="x")

    # ------------------------------------------------------------------
    def _build_machine_tab(self) -> None:
        t = self.tab_machine
        conn = ttk.LabelFrame(t, text="Kết nối", padding=PAD)
        conn.pack(side="top", fill="x")
        ttk.Label(conn, text="Cổng / địa chỉ").grid(row=0, column=0, sticky="w")
        # Không khoá ô này: ngoài cổng COM còn gõ được địa chỉ WiFi/LAN
        # (192.168.1.50, fluidnc.local, hoặc kèm cổng 192.168.1.50:23).
        self.cmb_port = ttk.Combobox(conn, width=26)
        self.cmb_port.grid(row=0, column=1, padx=4)
        ttk.Button(conn, text="Làm mới", command=self.refresh_ports, width=9).grid(row=0, column=2)
        self.btn_scan = ttk.Button(conn, text="Dò trong mạng LAN", width=18,
                                   command=self.scan_lan)
        self.btn_scan.grid(row=0, column=3, padx=(6, 0))
        ttk.Label(conn, text="Baud").grid(row=0, column=4, padx=(14, 2))
        self.cmb_baud = ttk.Combobox(conn, width=9, state="readonly",
                                     values=["115200", "230400", "921600", "57600"])
        self.cmb_baud.set(str(self.profile.connection.baudrate))
        self.cmb_baud.grid(row=0, column=5)
        ttk.Label(conn, text="Tốc độ máy ảo").grid(row=0, column=6, padx=(14, 2))
        self.cmb_simspeed = ttk.Combobox(conn, width=6, state="readonly",
                                         values=["1", "5", "20", "100"])
        self.cmb_simspeed.set(f"{self.profile.connection.simulator_speed:g}")
        self.cmb_simspeed.grid(row=0, column=7)
        self.btn_connect = ttk.Button(conn, text="Kết nối", command=self.toggle_connection, width=12)
        self.btn_connect.grid(row=0, column=8, padx=10)
        self.lbl_fw = ttk.Label(conn, text="", foreground="#5a646e")
        self.lbl_fw.grid(row=1, column=0, columnspan=9, sticky="w", pady=(6, 0))

        body = ttk.Frame(t)
        body.pack(side="top", fill="both", expand=True, pady=(PAD, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        pipe = ttk.LabelFrame(body, text="Phôi", padding=PAD)
        pipe.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        p = self.profile.pipe
        self.f_pipe = FieldGrid(pipe, [
            ("shape", "Hình dạng", SHAPE_LABEL.get(p.shape, SHAPE_LABEL["round"]),
             "choice", list(SHAPE_LABEL.values())),
            ("outer_diameter", "Đường kính ngoài [mm]", p.outer_diameter),
            ("width", "Cạnh ngang [mm]", p.width),
            ("height", "Cạnh dọc [mm]", p.height),
            ("corner_radius", "Bán kính góc lượn [mm]", p.corner_radius),
            ("wall_thickness", "Chiều dày thành [mm]", p.wall_thickness),
            ("length", "Chiều dài phôi [mm]", p.length),
            ("material", "Vật liệu", p.material, "str"),
        ], columns=1)
        self.f_pipe.pack(fill="x")
        self.lbl_pipe = ttk.Label(pipe, text="", foreground="#5a646e", wraplength=250,
                                  justify="left")
        self.lbl_pipe.pack(fill="x", pady=(6, 0))
        ttk.Label(pipe, foreground="#8a949e", wraplength=250, justify="left",
                  font=("TkDefaultFont", 8),
                  text=("Ống tròn dùng ô đường kính; ống hộp dùng hai ô cạnh "
                        "(hộp vuông chỉ cần cạnh ngang). Góc lượn để 0 thì phần "
                        "mềm tự lấy 2 lần chiều dày thành.")).pack(fill="x", pady=(4, 0))

        proc = ttk.LabelFrame(body, text="Tiến trình cắt", padding=PAD)
        proc.grid(row=0, column=1, sticky="nsew", padx=(0, PAD))
        pr = self.profile.process
        self.f_proc = FieldGrid(proc, [
            ("kind", "Kiểu", pr.kind, "choice", ["plasma", "laser", "oxyfuel", "router", "marker"]),
            ("kerf", "Bề rộng mạch cắt [mm]", pr.kerf),
            ("cut_feed", "Tốc độ cắt [mm/ph]", pr.cut_feed),
            ("power", "Công suất S", pr.power),
            ("cut_height", "Cao độ cắt [mm]", pr.cut_height),
            ("pierce_height", "Cao độ mồi [mm]", pr.pierce_height),
            ("pierce_delay", "Thời gian mồi [s]", pr.pierce_delay),
            ("safe_height", "Cao độ an toàn [mm]", pr.safe_height),
            ("lead_in", "Vào dao [mm]", pr.lead_in),
            ("lead_type", "Kiểu vào dao", pr.lead_type, "choice", ["arc", "line", "none"]),
            ("lead_start", "Vị trí điểm mồi [% chu vi]", pr.lead_start),
            ("lead_side", "Phía vào dao", pr.lead_side, "choice",
             ["auto", "inside", "outside", "plus", "minus"]),
            ("lead_angle", "Góc vào dao [độ]", pr.lead_angle),
            ("overcut", "Chạy vượt [mm]", pr.overcut),
        ], columns=1)
        self.f_proc.pack(fill="x")

        mot = ttk.LabelFrame(body, text="Chuyển động & làm mượt", padding=PAD)
        mot.grid(row=0, column=2, sticky="nsew")
        m = self.profile.motion
        self.f_motion = FieldGrid(mot, [
            ("chord_tolerance", "Dung sai dây cung [mm]", m.chord_tolerance),
            ("simplify_tolerance", "Dung sai rút gọn [mm]", m.simplify_tolerance),
            ("min_segment", "Đoạn ngắn nhất [mm]", m.min_segment),
            ("max_segment", "Đoạn dài nhất [mm]", m.max_segment),
            ("max_feed", "Trần tốc độ [mm/ph]", m.max_feed),
            ("max_bevel", "Góc vát tối đa [độ]", m.max_bevel),
            ("bevel_pivot", "Tâm xoay tới mũi cắt [mm]", m.bevel_pivot),
            ("feed_radius_mode", "Bán kính tính tốc độ", m.feed_radius_mode,
             "choice", ["outer", "mid", "inner"]),
            ("uniform_feed", "Tốc độ đều cả đường", m.uniform_feed, "bool"),
            ("corner_mode", "Qua góc ống hộp", CORNER_LABEL.get(m.corner_mode,
                                                                CORNER_LABEL["follow"]),
             "choice", list(CORNER_LABEL.values())),
            ("corner_torch_off", "Tắt mỏ khi xoay góc", m.corner_torch_off, "bool"),
            ("corner_lift", "Nhấc mỏ khi xoay góc [mm]", m.corner_lift),
        ], columns=1)
        self.f_motion.pack(fill="x")

        axes = ttk.LabelFrame(t, text="Trục máy", padding=PAD)
        axes.pack(side="top", fill="x", pady=(PAD, 0))
        cols = ("letter", "role", "max_rate", "max_travel", "invert")
        self.tree_axes = ttk.Treeview(axes, columns=cols, show="headings", height=4)
        for c, w, txt in zip(cols, (60, 110, 130, 130, 80),
                             ("Chữ", "Vai trò", "Tốc độ tối đa", "Hành trình", "Đảo chiều")):
            self.tree_axes.heading(c, text=txt)
            self.tree_axes.column(c, width=w, anchor="center")
        self.tree_axes.pack(side="left", fill="x", expand=True)
        self._refresh_axes_table()
        side = ttk.Frame(axes)
        side.pack(side="left", padx=PAD)
        ttk.Label(side, text="Sửa vai trò trục trong tệp hồ sơ máy (.json)",
                  foreground="#5a646e", wraplength=200).pack(anchor="w")

        bar = ttk.Frame(t)
        bar.pack(side="top", fill="x", pady=(PAD, 0))
        ttk.Button(bar, text="Áp dụng thông số", command=self.apply_profile).pack(side="left")
        ttk.Button(bar, text="Lưu hồ sơ máy...", command=self.save_profile).pack(side="left", padx=6)
        ttk.Button(bar, text="Mở hồ sơ máy...", command=self.open_profile).pack(side="left")
        self.refresh_ports()

    def _refresh_axes_table(self) -> None:
        for iid in self.tree_axes.get_children():
            self.tree_axes.delete(iid)
        role_vi = {ROLE_ALONG: "dọc ống", ROLE_CROSS: "ngang", ROLE_RADIAL: "nâng hạ",
                   ROLE_ROTARY: "xoay mâm cặp", ROLE_BEVEL: "vát mép"}
        for a in self.profile.axes:
            if not a.enabled:
                continue
            unit = "độ/ph" if a.is_angular else "mm/ph"
            travel = "không giới hạn" if a.max_travel <= 0 else f"{a.min_travel:g} .. {a.max_travel:g}"
            self.tree_axes.insert("", "end", values=(
                a.letter, role_vi.get(a.role, a.role), f"{a.max_rate:g} {unit}",
                travel, "có" if a.invert else "không"))

    # ------------------------------------------------------------------
    def _build_control_tab(self) -> None:
        t = self.tab_control
        left = ttk.Frame(t)
        left.pack(side="left", fill="y")
        self.dro = DRO(left, self.profile.letters, padding=PAD)
        self.dro.pack(side="top", fill="x")

        jog = ttk.LabelFrame(left, text="Chạy tay (jog)", padding=PAD)
        jog.pack(side="top", fill="x", pady=PAD)
        ttk.Label(jog, text="Bước [mm]").grid(row=0, column=0, sticky="w")
        self.var_step = tk.StringVar(value="1")
        ttk.Combobox(jog, textvariable=self.var_step, width=7, state="readonly",
                     values=["0.1", "0.5", "1", "5", "10", "50"]).grid(row=0, column=1)
        ttk.Label(jog, text="Bước xoay [độ]").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.var_step_a = tk.StringVar(value="5")
        ttk.Combobox(jog, textvariable=self.var_step_a, width=7, state="readonly",
                     values=["0.5", "1", "5", "15", "45", "90"]).grid(row=0, column=3)
        ttk.Label(jog, text="Tốc độ [mm/ph]").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_jog_feed = tk.StringVar(value="1000")
        ttk.Combobox(jog, textvariable=self.var_jog_feed, width=7, state="readonly",
                     values=["100", "300", "600", "1000", "2000", "3000"]).grid(row=1, column=1,
                                                                                pady=(4, 0))
        pad = ttk.Frame(jog)
        pad.grid(row=2, column=0, columnspan=4, pady=PAD)
        along = self.profile.letter(ROLE_ALONG) or "X"
        cross = self.profile.letter(ROLE_CROSS)
        radial = self.profile.letter(ROLE_RADIAL) or "Z"
        rotary = self.profile.letter(ROLE_ROTARY) or "A"
        bevel = self.profile.letter(ROLE_BEVEL)

        def jb(parent, text, letter, sign, angular=False, r=0, c=0, w=5):
            ttk.Button(parent, text=text, width=w,
                       command=lambda: self.do_jog(letter, sign, angular)).grid(
                row=r, column=c, padx=2, pady=2)

        jb(pad, f"-{along}", along, -1, r=1, c=0)
        ttk.Label(pad, text="dọc ống", width=8, anchor="center").grid(row=1, column=1)
        jb(pad, f"+{along}", along, +1, r=1, c=2)
        jb(pad, f"-{rotary}", rotary, -1, True, r=2, c=0)
        ttk.Label(pad, text="xoay", width=8, anchor="center").grid(row=2, column=1)
        jb(pad, f"+{rotary}", rotary, +1, True, r=2, c=2)
        jb(pad, f"-{radial}", radial, -1, r=3, c=0)
        ttk.Label(pad, text="nâng hạ", width=8, anchor="center").grid(row=3, column=1)
        jb(pad, f"+{radial}", radial, +1, r=3, c=2)
        row = 4
        if cross:
            jb(pad, f"-{cross}", cross, -1, r=row, c=0)
            ttk.Label(pad, text="ngang", width=8, anchor="center").grid(row=row, column=1)
            jb(pad, f"+{cross}", cross, +1, r=row, c=2)
            row += 1
        if bevel:
            jb(pad, f"-{bevel}", bevel, -1, True, r=row, c=0)
            ttk.Label(pad, text="vát", width=8, anchor="center").grid(row=row, column=1)
            jb(pad, f"+{bevel}", bevel, +1, True, r=row, c=2)
        ttk.Button(jog, text="Dừng jog", command=self.controller.cancel_jog).grid(
            row=3, column=0, columnspan=4, sticky="ew")

        ops = ttk.LabelFrame(left, text="Lệnh máy", padding=PAD)
        ops.pack(side="top", fill="x")
        buttons = [
            ("Về gốc ($H)", self.controller.home),
            ("Mở khoá ($X)", self.controller.unlock),
            ("Reset mềm", self.controller.soft_reset),
            ("Đặt gốc chi tiết", lambda: self.controller.set_work_zero()),
            ("Về gốc chi tiết", lambda: self.controller.goto_work_zero()),
            ("Bật nguồn cắt", lambda: self.controller.send(self.profile.process.on_command)),
            ("Tắt nguồn cắt", lambda: self.controller.send(self.profile.process.off_command)),
        ]
        for i, (text, cmd) in enumerate(buttons):
            ttk.Button(ops, text=text, command=cmd, width=20).grid(
                row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")

        right = ttk.Frame(t)
        right.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        ttk.Label(right, text="Nhật ký giao tiếp").pack(anchor="w")
        self.console = Console(right, on_send=self.send_manual)
        self.console.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def _build_job_tab(self) -> None:
        t = self.tab_job
        left = ttk.Frame(t)
        left.pack(side="left", fill="both", expand=True)

        head = ttk.Frame(left)
        head.pack(side="top", fill="x")
        ttk.Label(head, text="Tên công việc").pack(side="left")
        self.var_job_name = tk.StringVar(value=self.job.name)
        ttk.Entry(head, textvariable=self.var_job_name, width=28).pack(side="left", padx=6)
        ttk.Button(head, text="Mở...", command=self.open_job, width=8).pack(side="left")
        ttk.Button(head, text="Lưu...", command=self.save_job, width=8).pack(side="left", padx=4)

        add = ttk.Frame(left)
        add.pack(side="top", fill="x", pady=(PAD, 4))
        ttk.Label(add, text="Thêm nguyên công:").pack(side="left")
        self.var_new_op = tk.StringVar()
        self.cmb_op = ttk.Combobox(add, textvariable=self.var_new_op, state="readonly", width=30)
        self.cmb_op.pack(side="left", padx=6)
        ttk.Button(add, text="Thêm", command=self.add_operation, width=8).pack(side="left")
        self._refresh_op_choices()

        order = ttk.Frame(left)
        order.pack(side="top", fill="x", pady=(0, 4))
        self.var_optimize = tk.BooleanVar(value=self.job.optimize_order)
        ttk.Checkbutton(order, text="Tự sắp xếp thứ tự cắt",
                        variable=self.var_optimize,
                        command=self.on_toggle_order).pack(side="left")
        self.lbl_order = ttk.Label(order, foreground="#5a646e",
                                   text="đang cắt đúng thứ tự trong bảng")
        self.lbl_order.pack(side="left", padx=8)

        cols = ("stt", "loai", "mota")
        self.tree_ops = ttk.Treeview(left, columns=cols, show="headings", height=14)
        for c, w, txt in zip(cols, (40, 150, 320), ("#", "Loại", "Thông số chính")):
            self.tree_ops.heading(c, text=txt)
            self.tree_ops.column(c, width=w, anchor="w")
        self.tree_ops.pack(side="top", fill="both", expand=True)
        self.tree_ops.bind("<<TreeviewSelect>>", lambda _e: self.on_select_operation())

        tools = ttk.Frame(left)
        tools.pack(side="top", fill="x", pady=4)
        for text, cmd in (("Lên", lambda: self.move_operation(-1)),
                          ("Xuống", lambda: self.move_operation(1)),
                          ("Nhân bản", self.duplicate_operation),
                          ("Xoá", self.delete_operation),
                          ("Bật/tắt", self.toggle_operation)):
            ttk.Button(tools, text=text, command=cmd, width=10).pack(side="left", padx=2)

        right = ttk.LabelFrame(t, text="Thông số nguyên công", padding=PAD)
        right.pack(side="left", fill="both", padx=(PAD, 0))
        self.lbl_op_desc = ttk.Label(right, text="", wraplength=330, foreground="#5a646e")
        self.lbl_op_desc.pack(anchor="w", pady=(0, PAD))
        self.form = ParamForm(right, on_change=self.apply_operation_params)
        self.form.pack(fill="x")
        ttk.Button(right, text="Sinh G-code", command=self.generate).pack(
            side="bottom", fill="x", pady=(PAD, 0))

    # ------------------------------------------------------------------
    def _build_preview_tab(self) -> None:
        t = self.tab_preview
        self.preview = PreviewCanvas(t)
        self.preview.pack(side="top", fill="both", expand=True)
        bar = ttk.Frame(t)
        bar.pack(side="bottom", fill="x", pady=(PAD, 0))
        ttk.Button(bar, text="Sinh lại G-code", command=self.generate).pack(side="left")
        ttk.Button(bar, text="Xuất SVG...", command=self.export_svg).pack(side="left", padx=6)
        self.lbl_stats = ttk.Label(bar, text="", foreground="#39424b")
        self.lbl_stats.pack(side="left", padx=14)

    # ------------------------------------------------------------------
    def _build_sim_tab(self) -> None:
        """Mô phỏng máy chạy: ống trượt/quay dưới mỏ cắt, vết cắt hiện dần."""
        t = self.tab_sim
        self.machine_view = MachineView(t)
        self.machine_view.pack(side="top", fill="both", expand=True)

        bar = ttk.Frame(t)
        bar.pack(side="bottom", fill="x", pady=(PAD, 0))
        self.btn_sim_play = ttk.Button(bar, text="▶  Chạy", width=10,
                                       command=self.toggle_sim_play)
        self.btn_sim_play.pack(side="left")
        ttk.Button(bar, text="⏮  Về đầu", width=10,
                   command=self.reset_sim).pack(side="left", padx=4)
        ttk.Label(bar, text="Tốc độ").pack(side="left", padx=(10, 2))
        self.var_sim_speed = tk.StringVar(value="1")
        ttk.Combobox(bar, textvariable=self.var_sim_speed, width=5, state="readonly",
                     values=["0.25", "0.5", "1", "2", "5", "10", "20"]).pack(side="left")
        self.var_sim_live = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Bám theo máy thật", variable=self.var_sim_live).pack(
            side="left", padx=(12, 0))
        ttk.Checkbutton(bar, text="Khung máy",
                        variable=self.machine_view.show_frame,
                        command=self.machine_view.redraw).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(bar, text="Vết cắt",
                        variable=self.machine_view.show_trace,
                        command=self.machine_view.redraw).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Góc nhìn gốc", width=12,
                   command=self.machine_view.reset_view).pack(side="right")
        ttk.Button(bar, text="Xuất ảnh...", width=11,
                   command=self.export_machine_svg).pack(side="right", padx=4)

        line2 = ttk.Frame(t)
        line2.pack(side="bottom", fill="x", pady=(4, 0))
        self.var_sim_pos = tk.DoubleVar(value=0.0)
        self.scale_sim = ttk.Scale(line2, from_=0.0, to=1000.0, orient="horizontal",
                                   variable=self.var_sim_pos, command=self._on_sim_scrub)
        self.scale_sim.pack(side="left", fill="x", expand=True)
        self.lbl_sim_time = ttk.Label(line2, text="0.0 / 0.0 s", width=18,
                                      font=("Consolas", 9))
        self.lbl_sim_time.pack(side="left", padx=8)
        self.lbl_sim_info = ttk.Label(t, text="", foreground="#5a646e")
        self.lbl_sim_info.pack(side="bottom", anchor="w", pady=(4, 0))

    # ---- điều khiển mô phỏng ----
    def toggle_sim_play(self) -> None:
        if not self.playback or self.playback.duration <= 0:
            self.status_var.set("Chưa có chương trình để mô phỏng.")
            return
        self.sim_playing = not self.sim_playing
        if self.sim_playing:
            if self.sim_time >= self.playback.duration - 1e-6:
                self.sim_time = 0.0
            self._sim_last_tick = time.monotonic()
            self.var_sim_live.set(False)   # xem lại thì thôi bám máy thật
        self.btn_sim_play.configure(text="⏸  Dừng" if self.sim_playing else "▶  Chạy")

    def reset_sim(self) -> None:
        self.sim_time = 0.0
        self.sim_playing = False
        self.btn_sim_play.configure(text="▶  Chạy")
        self._refresh_sim_view()

    def _on_sim_scrub(self, _value: str) -> None:
        if self._sim_updating or not self.playback:
            return
        self.sim_playing = False
        self.btn_sim_play.configure(text="▶  Chạy")
        self.var_sim_live.set(False)
        self.sim_time = self.playback.duration * float(self.var_sim_pos.get()) / 1000.0
        self._refresh_sim_view()

    def _sim_tick(self) -> None:
        """Vòng lặp hoạt hình, ~25 khung hình/giây."""
        if self.sim_playing and self.playback:
            now = time.monotonic()
            try:
                speed = float(self.var_sim_speed.get())
            except ValueError:
                speed = 1.0
            self.sim_time += (now - self._sim_last_tick) * speed
            self._sim_last_tick = now
            if self.sim_time >= self.playback.duration:
                self.sim_time = self.playback.duration
                self.sim_playing = False
                self.btn_sim_play.configure(text="▶  Chạy")
            self._refresh_sim_view()
        self.root.after(40, self._sim_tick)

    def _refresh_sim_view(self) -> None:
        if not self.playback:
            return
        state = self.playback.state_at(self.sim_time)
        trace = self.playback.trace_until(self.sim_time)
        self.machine_view.set_state(state, trace)
        self._sim_updating = True
        self.var_sim_pos.set(1000.0 * self.sim_time / max(self.playback.duration, 1e-6))
        self._sim_updating = False
        self.lbl_sim_time.configure(
            text=f"{self.sim_time:6.1f} / {self.playback.duration:.1f} s")
        self.lbl_sim_info.configure(
            text=f"{self.playback.summary()} · dòng {state.line}"
                 + (f" · F{state.feed:.0f}" if state.feed else ""))

    def export_machine_svg(self) -> None:
        """Chụp khung mô phỏng ở thời điểm đang xem thành ảnh SVG."""
        if not self.playback:
            self.status_var.set("Chưa có chương trình để chụp.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".svg", filetypes=[("Ảnh SVG", "*.svg")],
            initialfile=f"{self.job.name}-mo-phong.svg")
        if not path:
            return
        from ..svgview import save_machine_svg
        save_machine_svg(path, self.profile,
                         self.playback.state_at(self.sim_time),
                         self.playback.trace_until(self.sim_time),
                         title=f"{self.job.name} - giây {self.sim_time:.1f}",
                         azimuth=self.machine_view.cam.azimuth,
                         elevation=self.machine_view.cam.elevation,
                         along_range=self.machine_view._along_range())
        self.status_var.set(f"Đã lưu ảnh mô phỏng: {path}")

    # ------------------------------------------------------------------
    def _build_run_tab(self) -> None:
        t = self.tab_run
        bar = ttk.Frame(t)
        bar.pack(side="top", fill="x")
        self.btn_start = ttk.Button(bar, text="BẮT ĐẦU CẮT", command=self.start_job, width=16)
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(bar, text="Tạm dừng", command=self.toggle_pause,
                                    width=12, state="disabled")
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(bar, text="DỪNG", command=self.stop_job,
                                   width=10, state="disabled")
        self.btn_stop.pack(side="left")
        ttk.Button(bar, text="Lưu G-code...", command=self.save_gcode).pack(side="left", padx=(20, 0))
        ttk.Button(bar, text="Mở G-code...", command=self.open_gcode).pack(side="left", padx=6)

        prog = ttk.Frame(t)
        prog.pack(side="top", fill="x", pady=PAD)
        self.pbar = ttk.Progressbar(prog, mode="determinate", maximum=100.0)
        self.pbar.pack(side="top", fill="x")
        self.lbl_progress = ttk.Label(prog, text="Chưa chạy")
        self.lbl_progress.pack(side="top", anchor="w", pady=(4, 0))

        body = ttk.Frame(t)
        body.pack(side="top", fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        gc = ttk.LabelFrame(body, text="Chương trình G-code", padding=4)
        gc.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        self.txt_gcode = tk.Text(gc, wrap="none", font=("Consolas", 9), background="#fbfcfd")
        self.txt_gcode.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(gc, orient="vertical", command=self.txt_gcode.yview)
        sb.pack(side="right", fill="y")
        self.txt_gcode.configure(yscrollcommand=sb.set)
        self.txt_gcode.tag_configure("cur", background="#fff3bf")

        info = ttk.LabelFrame(body, text="Theo dõi", padding=PAD)
        info.grid(row=0, column=1, sticky="nsew")
        self.run_console = Console(info, on_send=self.send_manual)
        self.run_console.pack(fill="both", expand=True)

    # ==================================================================
    # Kết nối và sự kiện
    # ==================================================================
    def _wire_controller(self) -> None:
        c = self.controller
        c.on_line = lambda text, direction: self.events.put(("line", text, direction))
        c.on_status = lambda st: self.events.put(("status", st))
        c.on_progress = lambda pr: self.events.put(("progress", pr))
        c.on_event = lambda kind, text: self.events.put(("event", kind, text))

    def refresh_ports(self) -> None:
        ports = list_ports()
        self.cmb_port["values"] = [f"{p} - {d}" for p, d in ports]
        if ports and not self.cmb_port.get():
            self.cmb_port.current(0)

    def scan_lan(self) -> None:
        """Dò FluidNC trong mạng LAN.

        Quét cả dải /24 nên mất vài giây - chạy ở luồng riêng để giao diện
        không bị treo, xong việc mới đẩy kết quả về luồng chính.
        """
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.btn_scan.configure(text="Đang dò...", state="disabled")
        self.status_var.set("Đang dò tìm máy trong mạng LAN...")

        def work() -> None:
            try:
                from ..transport import discover_lan
                found = discover_lan()
            except Exception as exc:                 # pragma: no cover
                found, err = [], str(exc)
            else:
                err = ""
            self.events.put(("lan", found, err))

        threading.Thread(target=work, daemon=True).start()

    def _on_lan_result(self, found, err: str) -> None:
        self._scanning = False
        self.btn_scan.configure(text="Dò trong mạng LAN", state="normal")
        if err:
            self.status_var.set(f"Dò mạng LAN lỗi: {err}")
            return
        if not found:
            self.status_var.set(
                "Không thấy máy nào trong mạng LAN. Kiểm tra ESP32 đã vào cùng "
                "mạng WiFi và đã bật Telnet trong FluidNC chưa."
            )
            return
        values = list(self.cmb_port["values"]) + [f"{a} - {d}" for a, d in found]
        self.cmb_port["values"] = values
        self.cmb_port.set(f"{found[0][0]} - {found[0][1]}")
        self.status_var.set(f"Thấy {len(found)} máy trong mạng LAN.")

    def toggle_connection(self) -> None:
        if self.controller.is_connected:
            self.controller.disconnect()
            self.btn_connect.configure(text="Kết nối")
            self.badge.set_state(None)
            self.lbl_conn.configure(text="Chưa kết nối")
            return
        raw = self.cmb_port.get()
        port = raw.split(" - ")[0].strip() if raw else ""
        if not port:
            messagebox.showwarning(
                "Chưa chọn cổng",
                "Hãy chọn cổng COM, hoặc gõ địa chỉ WiFi/LAN của máy "
                "(ví dụ 192.168.1.50) trước khi kết nối."
            )
            return
        self.apply_profile(silent=True)
        try:
            self.controller.connect(port=port, baudrate=int(self.cmb_baud.get()))
        except Exception as exc:
            messagebox.showerror("Lỗi kết nối", str(exc))
            return
        from ..transport import parse_address
        how = "qua mạng LAN" if parse_address(port) else "qua cổng COM"
        self.btn_connect.configure(text="Ngắt kết nối")
        self.lbl_conn.configure(text=f"Đã kết nối {port} ({how})")
        self.root.after(400, self.controller.query_firmware)

    def send_manual(self, text: str) -> None:
        if not self.controller.is_connected:
            self.console.log("Chưa kết nối máy.", "err")
            return
        self.controller.send(text)

    def do_jog(self, letter: str, sign: int, angular: bool = False) -> None:
        if not self.controller.is_connected:
            self.status_var.set("Chưa kết nối máy.")
            return
        try:
            step = float(self.var_step_a.get() if angular else self.var_step.get())
            feed = float(self.var_jog_feed.get())
        except ValueError:
            return
        self.controller.jog({letter: sign * step}, feed)

    # ------------------------------------------------------------------
    def _pump_events(self) -> None:
        """Lấy sự kiện từ luồng nền và cập nhật giao diện."""
        try:
            for _ in range(200):
                item = self.events.get_nowait()
                kind = item[0]
                if kind == "line":
                    _, text, direction = item
                    tag = "tx" if direction == "tx" else ("err" if "error" in text.lower()
                                                          or "alarm" in text.lower() else "rx")
                    prefix = ">> " if direction == "tx" else ""
                    if direction == "rx" or not self.controller.progress.running:
                        self.console.log(prefix + text, tag)
                    if direction == "rx" and text.strip().lower() != "ok":
                        self.run_console.log(text, tag)
                elif kind == "lan":
                    self._on_lan_result(item[1], item[2])
                elif kind == "status":
                    self._on_status(item[1])
                elif kind == "progress":
                    self._on_progress(item[1])
                elif kind == "event":
                    _, ekind, text = item
                    tag = "err" if ekind in ("error", "alarm") else "info"
                    self.console.log(f"* {text}", tag)
                    self.run_console.log(f"* {text}", tag)
                    self.status_var.set(text)
                    if ekind in ("job_done", "job_stop", "alarm", "error"):
                        self._set_running_ui(False)
                    if ekind == "alarm":
                        messagebox.showerror("Báo động từ máy", text)
        except queue.Empty:
            pass
        self.root.after(60, self._pump_events)

    def _on_status(self, st: MachineStatus) -> None:
        self.badge.set_state(st.state, st.state_vi)
        pos = st.wpos or st.mpos
        self.dro.update_values(pos, st.mpos)
        self.lbl_pos.configure(
            text="  ".join(f"{k}{v:9.2f}" for k, v in pos.items()) + f"   F{st.feed:.0f}")
        # vẽ vị trí mũi cắt lên khung xem trước
        now = time.monotonic()
        if now - self._last_status_draw > 0.12 and pos:
            self._last_status_draw = now
            along = self.profile.axis(ROLE_ALONG)
            rot = self.profile.axis(ROLE_ROTARY)
            if along and rot and along.letter in pos and rot.letter in pos:
                x = _undo(pos[along.letter], along)
                a = _undo(pos[rot.letter], rot)
                cross_ax = self.profile.axis(ROLE_CROSS)
                xc = (_undo(pos[cross_ax.letter], cross_ax)
                      if cross_ax and cross_ax.letter in pos else 0.0)
                v = self.profile.pipe.section().s_of_contact(a, xc)
                self.preview.set_tool_position(x, v)
                self._mirror_machine(st, pos, x, v)

    def _mirror_machine(self, st: MachineStatus, pos: Dict[str, float],
                        x: float, v: float) -> None:
        """Chiếu trạng thái máy thật lên khung mô phỏng.

        FluidNC báo phụ kiện đang bật trong trường ``A:`` của báo cáo trạng
        thái ('S' = trục chính/nguồn cắt), nhờ đó biết lúc nào đang cắt để vẽ
        tia lửa và ghi vết cắt.
        """
        if not self.var_sim_live.get() or self.sim_playing:
            return
        torch = "S" in (st.accessories or "")
        state = SimState(time=0.0, axes=dict(pos), torch=torch, feed=st.feed)

        # Máy chỉ báo trạng thái 5 lần/giây nên nếu chỉ nối các điểm đó lại thì
        # vết cắt rất thưa.  Vì đã biết trước chương trình đang chạy, ta dóng vị
        # trí máy báo về vào chương trình để lấy đúng phần vết cắt đã hình thành.
        trace = None
        if self.playback and self.playback.moves:
            t = self._match_playback_time(pos)
            if t is not None:
                trace = self.playback.trace_until(t)
                self._sim_updating = True
                self.var_sim_pos.set(1000.0 * t / max(self.playback.duration, 1e-6))
                self._sim_updating = False
                self.lbl_sim_time.configure(
                    text=f"{t:6.1f} / {self.playback.duration:.1f} s")

        if trace is None:
            # không dóng được (tệp G-code lạ): tự tích luỹ từ báo cáo trạng thái
            if torch and not self._live_torch:
                self._live_pen_up = True
            if torch:
                if (not self._live_trace
                        or abs(self._live_trace[-1].x - x) > 0.3
                        or abs(self._live_trace[-1].v - v) > 0.3):
                    self._live_trace.append(TracePoint(0.0, x, v,
                                                       start=self._live_pen_up))
                    self._live_pen_up = False
                    if len(self._live_trace) > 20000:
                        del self._live_trace[:5000]
            trace = self._live_trace
        self._live_torch = torch
        self.machine_view.set_state(state, trace)

    def _match_playback_time(self, pos: Dict[str, float]) -> Optional[float]:
        """Tìm thời điểm trong chương trình khớp nhất với vị trí máy đang báo.

        Ưu tiên tìm quanh vị trí đã khớp lần trước (chương trình chạy tiến dần),
        chỉ quét lại toàn bộ khi không tìm được điểm đủ gần - nhờ vậy đường chạy
        tự cắt nhau cũng không làm mô phỏng nhảy lung tung.
        """
        pb = self.playback
        if not pb or not pb.moves:
            return None
        letters = [c for c in self.profile.letters if c in pos]
        if not letters:
            return None

        def scan(lo: int, hi: int):
            best_t, best_d = None, float("inf")
            for i in range(max(0, lo), min(len(pb.moves), hi)):
                m = pb.moves[i]
                num = den = 0.0
                for c in letters:
                    a0 = m.start.get(c, 0.0)
                    d = m.end.get(c, a0) - a0
                    num += (pos[c] - a0) * d
                    den += d * d
                f = 0.0 if den < 1e-12 else max(0.0, min(1.0, num / den))
                dist = 0.0
                for c in letters:
                    a0 = m.start.get(c, 0.0)
                    p = a0 + (m.end.get(c, a0) - a0) * f
                    dist += (pos[c] - p) ** 2
                if dist < best_d:
                    best_d = dist
                    best_t = m.t0 + m.duration * f
            return best_t, math.sqrt(best_d)

        near = getattr(self, "_match_index", 0)
        t, d = scan(near - 2, near + 40)
        if d > 1.0 or t is None:
            t, d = scan(0, len(pb.moves))
        if t is None:
            return None
        self._match_index = max(0, min(len(pb.moves) - 1,
                                       int(len(pb.moves) * t / max(pb.duration, 1e-6))))
        return t

    def _on_progress(self, pr: JobProgress) -> None:
        self.pbar["value"] = pr.percent
        eta = f" · còn ~{pr.eta:.0f}s" if pr.eta > 1 else ""
        self.lbl_progress.configure(
            text=f"{pr.acked}/{pr.total} dòng ({pr.percent:.1f}%) · "
                 f"đã chạy {pr.elapsed:.0f}s{eta}"
                 + ("  · ĐANG TẠM DỪNG" if pr.paused else ""))
        if pr.total and pr.acked:
            self._highlight_line(pr.acked)
        self._set_running_ui(pr.running)

    def _highlight_line(self, index: int) -> None:
        try:
            self.txt_gcode.tag_remove("cur", "1.0", "end")
            self.txt_gcode.tag_add("cur", f"{index}.0", f"{index}.end")
            self.txt_gcode.see(f"{index}.0")
        except tk.TclError:
            pass

    def _set_running_ui(self, running: bool) -> None:
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_pause.configure(state="normal" if running else "disabled")
        self.btn_stop.configure(state="normal" if running else "disabled")
        if not running:
            self.btn_pause.configure(text="Tạm dừng")

    # ==================================================================
    # Hồ sơ máy
    # ==================================================================
    def apply_profile(self, silent: bool = False) -> None:
        p = self.profile
        label = self.f_pipe.get("shape", SHAPE_LABEL[p.pipe.shape])
        p.pipe.shape = LABEL_SHAPE.get(str(label), p.pipe.shape)
        p.pipe.outer_diameter = self.f_pipe.get("outer_diameter", p.pipe.outer_diameter)
        p.pipe.width = self.f_pipe.get("width", p.pipe.width)
        p.pipe.height = self.f_pipe.get("height", p.pipe.height)
        p.pipe.corner_radius = self.f_pipe.get("corner_radius", p.pipe.corner_radius)
        p.pipe.wall_thickness = self.f_pipe.get("wall_thickness", p.pipe.wall_thickness)
        p.pipe.length = self.f_pipe.get("length", p.pipe.length)
        p.pipe.material = self.f_pipe.get("material", p.pipe.material)
        for key in ("kerf", "cut_feed", "power", "cut_height", "pierce_height",
                    "pierce_delay", "safe_height", "lead_in", "overcut",
                    "lead_start", "lead_angle"):
            setattr(p.process, key, self.f_proc.get(key, getattr(p.process, key)))
        p.process.kind = self.f_proc.get("kind", p.process.kind)
        p.process.lead_type = self.f_proc.get("lead_type", p.process.lead_type)
        p.process.lead_side = self.f_proc.get("lead_side", p.process.lead_side)
        for key in ("chord_tolerance", "simplify_tolerance", "min_segment", "max_segment",
                    "max_feed", "max_bevel", "bevel_pivot"):
            setattr(p.motion, key, self.f_motion.get(key, getattr(p.motion, key)))
        p.motion.feed_radius_mode = self.f_motion.get("feed_radius_mode", p.motion.feed_radius_mode)
        p.motion.uniform_feed = bool(self.f_motion.get("uniform_feed", p.motion.uniform_feed))
        p.motion.corner_mode = LABEL_CORNER.get(
            str(self.f_motion.get("corner_mode", CORNER_LABEL[p.motion.corner_mode])),
            p.motion.corner_mode)
        p.motion.corner_torch_off = bool(
            self.f_motion.get("corner_torch_off", p.motion.corner_torch_off))
        p.motion.corner_lift = self.f_motion.get("corner_lift", p.motion.corner_lift)
        try:
            p.connection.baudrate = int(self.cmb_baud.get())
            p.connection.simulator_speed = max(0.01, float(self.cmb_simspeed.get()))
        except ValueError:
            pass
        warnings = p.validate()
        if warnings and not silent:
            messagebox.showwarning("Cấu hình", "\n".join(warnings))
        if not silent:
            self.status_var.set("Đã áp dụng thông số máy.")
        self._refresh_axes_table()
        if hasattr(self, "cmb_op"):
            self._refresh_op_choices()
        try:
            sec = p.pipe.section()
            note = f"{sec.describe()} · chu vi {sec.perimeter:.1f} mm"
            if not p.pipe.is_round:
                note += (f" · góc lượn R{getattr(sec, 'rc', 0):.1f}"
                         f" · trục ngang cần chạy ±{sec.hx - sec.rc:.0f} mm")
            self.lbl_pipe.configure(text=note)
        except Exception as exc:
            self.lbl_pipe.configure(text=f"Tiết diện không hợp lệ: {exc}")

    def save_profile(self) -> None:
        self.apply_profile(silent=True)
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Hồ sơ máy", "*.json")],
                                            initialfile="machine.json")
        if path:
            self.profile.save(path)
            self.profile_path = path
            self.status_var.set(f"Đã lưu hồ sơ máy: {path}")

    def open_profile(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Hồ sơ máy", "*.json")])
        if not path:
            return
        try:
            self.profile = MachineProfile.load(path)
        except Exception as exc:
            messagebox.showerror("Lỗi", f"Không đọc được hồ sơ máy:\n{exc}")
            return
        self.profile_path = path
        self.controller.profile = self.profile
        messagebox.showinfo("Hồ sơ máy",
                            "Đã nạp hồ sơ máy.  Khởi động lại phần mềm để cập nhật\n"
                            "toàn bộ bảng điều khiển theo cấu hình trục mới.")
        self.status_var.set(f"Đã nạp hồ sơ: {path}")

    # ==================================================================
    # Công việc
    # ==================================================================
    def _seed_demo_job(self) -> None:
        """Công việc mẫu, chọn nguyên công hợp với dạng phôi đang khai báo."""
        if self.profile.pipe.is_round:
            self.job.add("hole", diameter=25.0, x=90.0, theta=0.0)
            self.job.add("saddle", main_diameter=114.3, angle=90.0, x=260.0)
        else:
            self.job.add("slot", x=120.0, theta=0.0, length=60.0,
                         width_deg=45.0, corner=5.0)
            self.job.add("circle", diameter=25.0, x=220.0, theta=90.0)
            self.job.add("cutoff", x=320.0, angle=0.0)
        self._refresh_op_list()
        self.generate()

    def _refresh_op_list(self, select: Optional[int] = None) -> None:
        for iid in self.tree_ops.get_children():
            self.tree_ops.delete(iid)
        for i, op in enumerate(self.job.operations):
            mark = "" if op.enabled else "(tắt) "
            self.tree_ops.insert("", "end", iid=str(i),
                                 values=(i + 1, op.label(), mark + _summary(op)))
        if self.job.operations:
            idx = select if select is not None else 0
            idx = max(0, min(idx, len(self.job.operations) - 1))
            self.tree_ops.selection_set(str(idx))
            self.tree_ops.focus(str(idx))
            self.on_select_operation()

    def _selected_index(self) -> Optional[int]:
        sel = self.tree_ops.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def on_select_operation(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.job.operations):
            return
        op = self.job.operations[idx]
        spec = OP_CATALOG.get(op.type, {})
        self.lbl_op_desc.configure(text=spec.get("desc", ""))
        self.form.build(spec.get("params", []), op.params)
        self._describe_source(op)

    def _describe_source(self, op: Operation) -> None:
        """Với nguyên công nhập tệp: đọc thử và cho biết trong tệp có những gì."""
        if op.type != "pattern":
            return
        path = str(op.get("file", ""))
        if self.job.source_path and path and not os.path.isabs(path):
            path = os.path.join(os.path.dirname(self.job.source_path), path)
        if not path:
            return
        spec = OP_CATALOG.get(op.type, {})
        try:
            from ..importers import describe_file
            text = describe_file(
                path, section=self.profile.pipe.section(),
                tolerance=self.profile.motion.chord_tolerance,
                mesh_axis=str(op.get("mesh_axis", "auto")),
                mesh_roll=float(op.get("mesh_roll", 0.0)),
                mesh_tolerance=float(op.get("mesh_tol", 0.4)),
            )
        except Exception as exc:
            text = f"Lỗi: {exc}"
        self.lbl_op_desc.configure(text=f"{spec.get('desc', '')}\n→ {text}")

    def apply_operation_params(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.job.operations):
            return
        self.job.operations[idx].params.update(self.form.values())
        self.tree_ops.item(str(idx), values=(idx + 1, self.job.operations[idx].label(),
                                             _summary(self.job.operations[idx])))
        self._describe_source(self.job.operations[idx])
        self.generate()

    def _refresh_op_choices(self) -> None:
        """Chỉ hiện những nguyên công dùng được với dạng phôi đang khai báo."""
        keys = ops_for_shape(self.profile.pipe.shape)
        values = [f"{k} - {OP_CATALOG[k]['label']}" for k in keys]
        cur = self.var_new_op.get()
        self.cmb_op["values"] = values
        if cur not in values and values:
            self.cmb_op.current(0)

    def on_toggle_order(self) -> None:
        self.job.optimize_order = bool(self.var_optimize.get())
        self.lbl_order.configure(
            text=("tự xếp: vạch dấu → lỗ/rãnh → cắt đứt (từ ngoài vào)"
                  if self.job.optimize_order else "đang cắt đúng thứ tự trong bảng"))
        self.generate()

    def add_operation(self) -> None:
        key = self.var_new_op.get().split(" - ")[0].strip()
        if key not in OP_CATALOG:
            return
        self.job.add(key)
        self._refresh_op_list(select=len(self.job.operations) - 1)
        self.generate()

    def delete_operation(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self.job.operations.pop(idx)
        self._refresh_op_list(select=max(0, idx - 1))
        self.generate()

    def duplicate_operation(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        src = self.job.operations[idx]
        self.job.operations.insert(idx + 1, Operation(src.type, dict(src.params), src.name, True))
        self._refresh_op_list(select=idx + 1)
        self.generate()

    def toggle_operation(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self.job.operations[idx].enabled = not self.job.operations[idx].enabled
        self._refresh_op_list(select=idx)
        self.generate()

    def move_operation(self, delta: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        j = idx + delta
        if 0 <= j < len(self.job.operations):
            ops = self.job.operations
            ops[idx], ops[j] = ops[j], ops[idx]
            self._refresh_op_list(select=j)
            self.generate()

    def open_job(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Công việc", "*.json")])
        if path:
            self._load_job(path)

    def _load_job(self, path: str) -> None:
        try:
            self.job = Job.load(path)
        except Exception as exc:
            messagebox.showerror("Lỗi", f"Không đọc được tệp công việc:\n{exc}")
            return
        self.var_job_name.set(self.job.name)
        if hasattr(self, "var_optimize"):
            self.var_optimize.set(self.job.optimize_order)
        self._refresh_op_list()
        self.generate()
        self.status_var.set(f"Đã mở công việc: {path}")

    def save_job(self) -> None:
        self.job.name = self.var_job_name.get().strip() or "cong-viec"
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Công việc", "*.json")],
                                            initialfile=f"{self.job.name}.json")
        if path:
            self.job.save(path)
            self.status_var.set(f"Đã lưu công việc: {path}")

    # ==================================================================
    # Sinh chương trình
    # ==================================================================
    def generate(self) -> None:
        self.apply_profile(silent=True)
        self.job.name = self.var_job_name.get().strip() or "cong-viec"
        try:
            toolpath, warns = self.job.build_toolpath(self.profile)
            program = build_program(self.profile, toolpath, self.job.name)
        except Exception as exc:
            self.status_var.set(f"Lỗi sinh G-code: {exc}")
            return
        self.program = program
        self.preview.set_data(self.profile, program.passes)
        try:
            self.playback = Playback(self.profile, program.stream_lines())
        except Exception as exc:
            self.playback = None
            self.console.log(f"! Không dựng được mô phỏng: {exc}", "err")
        self.machine_view.set_profile(self.profile)
        self.machine_view.set_playback(self.playback)
        self.sim_time = 0.0
        self.sim_playing = False
        self.btn_sim_play.configure(text="▶  Chạy")
        self._live_trace = []
        self._refresh_sim_view()
        self.txt_gcode.delete("1.0", "end")
        self.txt_gcode.insert("1.0", "\n".join(program.stream_lines()))
        s = program.stats
        self.lbl_stats.configure(
            text=f"{len(program.passes)} đường · {s.cut_length:.0f} mm cắt · "
                 f"{s.pierces} điểm mồi · {s.lines} dòng · ước tính {s.time_text}")
        order = " → ".join(f"{i}.{ps.name}" for i, ps in enumerate(program.passes, 1))
        self.lbl_order.configure(
            text=("tự xếp: " if self.job.optimize_order else "thứ tự cắt: ") + order[:110])
        for w in warns + s.warnings:
            self.console.log(f"! {w}", "err")
        self.status_var.set("Đã sinh G-code." if not warns else f"Sinh G-code với {len(warns)} cảnh báo.")

    def export_svg(self) -> None:
        if not self.program:
            return
        path = filedialog.asksaveasfilename(defaultextension=".svg",
                                            filetypes=[("Bản vẽ SVG", "*.svg")],
                                            initialfile=f"{self.job.name}.svg")
        if path:
            from ..svgview import save_svg
            save_svg(path, self.profile, self.program.passes, title=self.job.name)
            self.status_var.set(f"Đã xuất bản vẽ: {path}")

    def save_gcode(self) -> None:
        if not self.program:
            self.generate()
        if not self.program:
            return
        path = filedialog.asksaveasfilename(defaultextension=".nc",
                                            filetypes=[("G-code", "*.nc *.gcode *.tap")],
                                            initialfile=f"{self.job.name}.nc")
        if path:
            self.program.save(path)
            self.status_var.set(f"Đã lưu G-code: {path}")

    def open_gcode(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("G-code", "*.nc *.gcode *.tap"),
                                                     ("Tất cả", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        self.txt_gcode.delete("1.0", "end")
        self.txt_gcode.insert("1.0", text)
        self.program = None
        try:
            self.playback = Playback(self.profile, self._gcode_lines())
            self.machine_view.set_profile(self.profile)
            self.machine_view.set_playback(self.playback)
            self.sim_time = 0.0
            self._refresh_sim_view()
        except Exception:
            self.playback = None
        self.status_var.set(f"Đã nạp {path} - mô phỏng được, nhưng không sửa lại biên dạng")

    # ==================================================================
    # Chạy chương trình
    # ==================================================================
    def _gcode_lines(self) -> List[str]:
        from ..gcode import strip_gcode_comment
        raw = self.txt_gcode.get("1.0", "end").splitlines()
        return [l for l in (strip_gcode_comment(x) for x in raw) if l]

    def start_job(self) -> None:
        if not self.controller.is_connected:
            messagebox.showwarning("Chưa kết nối", "Hãy kết nối máy trước khi chạy.")
            return
        lines = self._gcode_lines()
        if not lines:
            messagebox.showwarning("Chưa có chương trình", "Chưa có G-code để chạy.")
            return
        st = self.controller.status
        if st and st.is_alarm:
            if not messagebox.askyesno("Máy đang báo động",
                                       "Máy đang ở trạng thái báo động.\nMở khoá rồi chạy tiếp?"):
                return
            self.controller.unlock()
        est = self.program.stats.time_text if self.program else "?"
        if not messagebox.askyesno(
                "Xác nhận chạy",
                f"Chuẩn bị chạy {len(lines)} dòng lệnh (ước tính {est}).\n\n"
                "Kiểm tra: phôi đã kẹp chắc, gốc toạ độ đã đặt đúng,\n"
                "nguồn cắt và khí đã sẵn sàng.\n\nBắt đầu?"):
            return
        self._live_trace = []
        self._live_pen_up = True
        try:
            self.controller.start_job(lines)
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self._set_running_ui(True)
        self.nb.select(self.tab_run)

    def toggle_pause(self) -> None:
        if self.controller.progress.paused:
            self.controller.resume_job()
            self.btn_pause.configure(text="Tạm dừng")
        else:
            self.controller.pause_job()
            self.btn_pause.configure(text="Chạy tiếp")

    def stop_job(self) -> None:
        if messagebox.askyesno("Dừng", "Dừng khẩn cấp chương trình đang chạy?"):
            self.controller.stop_job()
            self._set_running_ui(False)

    # ==================================================================
    def on_close(self) -> None:
        if self.controller.progress.running:
            if not messagebox.askyesno("Đang chạy", "Chương trình đang chạy. Thoát và dừng máy?"):
                return
            self.controller.stop_job()
        try:
            self.controller.disconnect()
        except Exception:
            pass
        self.root.destroy()


def _undo(value: float, axis) -> float:
    """Đảo ngược phép biến đổi trục để lấy lại toạ độ công nghệ."""
    v = value - axis.offset
    return -v if axis.invert else v


def _summary(op: Operation) -> str:
    """Tóm tắt tham số chính của một nguyên công để hiện trong bảng."""
    p = op.params
    t = op.type
    if t == "cutoff":
        return f"X={p.get('x', 0):g}  góc={p.get('angle', 0):g}°"
    if t == "saddle":
        return (f"ống chính D{p.get('main_diameter', 0):g}  góc={p.get('angle', 90):g}°  "
                f"X={p.get('x', 0):g}")
    if t == "hole":
        return f"D{p.get('diameter', 0):g} tại X={p.get('x', 0):g}, {p.get('theta', 0):g}°"
    if t == "slot":
        return (f"{p.get('length', 0):g}×{p.get('width_deg', 0):g}° tại X={p.get('x', 0):g}, "
                f"{p.get('theta', 0):g}°")
    if t == "circle":
        return f"D{p.get('diameter', 0):g} tại X={p.get('x', 0):g}"
    if t == "helix":
        return f"X {p.get('x_start', 0):g}→{p.get('x_end', 0):g}, {p.get('turns', 0):g} vòng"
    if t == "axial":
        return f"X {p.get('x_start', 0):g}→{p.get('x_end', 0):g} tại {p.get('theta', 0):g}°"
    if t == "ring_mark":
        return f"X={p.get('x', 0):g}"
    if t == "weld_prep":
        return f"X={p.get('x', 0):g}  vát {p.get('angle', 0):g}°"
    if t == "pattern":
        name = os.path.basename(str(p.get("file", "")))
        if not name:
            return "(chưa chọn tệp)"
        scale = float(p.get("scale", 1.0) or 1.0)
        extra = f"  ×{scale:g}" if abs(scale - 1.0) > 1e-9 else ""
        return f"{name}{extra}"
    return ""


def main(profile_path: Optional[str] = None, job_path: Optional[str] = None) -> int:
    root = tk.Tk()
    MainWindow(root, profile_path, job_path)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
