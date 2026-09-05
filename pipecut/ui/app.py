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
from . import theme
from .canvasview import PreviewCanvas
from .machineview import MachineView
from .widgets import PAD, Console, DRO, FieldGrid, ParamForm, ScrollColumn, StatusBadge

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
        self.theme_name = theme.load_preference()
        theme.apply(root, self.theme_name)

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
        # Huy hiệu bên trái đã báo trạng thái rồi, nhãn này nói chi tiết hơn
        # (cổng nào, kiểu kết nối gì) chứ không lặp lại chữ y hệt.
        self.lbl_conn = ttk.Label(top, text="Chọn cổng ở thẻ 1 rồi bấm Kết nối",
                                  style="Dim.TLabel")
        self.lbl_conn.pack(side="left", padx=10)
        self.lbl_pos = ttk.Label(top, text="", style="Mono.TLabel")
        self.lbl_pos.pack(side="right", padx=(0, 12))
        self.btn_theme = ttk.Button(top, width=12, command=self.toggle_theme)
        self.btn_theme.pack(side="right")
        self._update_theme_button()

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
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel",
                  relief="flat", anchor="w", padding=(8, 4)).pack(side="bottom", fill="x")

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
        self.btn_connect = ttk.Button(conn, text="Kết nối", command=self.toggle_connection,
                                      width=12, style="Accent.TButton")
        self.btn_connect.grid(row=0, column=8, padx=10)
        self.lbl_fw = ttk.Label(conn, text="", style="Dim.TLabel")
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
        self.lbl_pipe = ttk.Label(pipe, text="", style="Dim.TLabel", wraplength=250,
                                  justify="left")
        self.lbl_pipe.pack(fill="x", pady=(6, 0))
        ttk.Label(pipe, style="Hint.TLabel", wraplength=250, justify="left",
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
            ("corner_pivot_arcs", "Chia cung góc mấy lần xoay",
             float(m.corner_pivot_arcs)),
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
                  style="Dim.TLabel", wraplength=200).pack(anchor="w")

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
        # Cột trái dài hơn màn hình máy tính xách tay, nên cho cuộn được.
        self.control_column = ScrollColumn(t)
        self.control_column.pack(side="left", fill="y")
        left = self.control_column.inner
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
        # Lệnh làm máy chạy hoặc mồi lửa được tô màu để không bấm nhầm.
        buttons = [
            ("Về gốc ($H)", self.controller.home, "Accent.TButton"),
            ("Mở khoá ($X)", self.controller.unlock, ""),
            ("Reset mềm", self.controller.soft_reset, ""),
            ("Đặt gốc chi tiết", lambda: self.controller.set_work_zero(), ""),
            ("Về gốc chi tiết", lambda: self.controller.goto_work_zero(), "Accent.TButton"),
            ("Bật nguồn cắt", lambda: self.controller.send(self.profile.process.on_command),
             "Danger.TButton"),
            ("Tắt nguồn cắt", lambda: self.controller.send(self.profile.process.off_command), ""),
        ]
        for i, (text, cmd, style) in enumerate(buttons):
            ttk.Button(ops, text=text, command=cmd, width=20,
                       style=style or "TButton").grid(
                row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")

        probe = ttk.LabelFrame(left, text="Dò cạnh (tự tìm phôi, đặt gốc)", padding=PAD)
        probe.pack(side="top", fill="x", pady=(PAD, 0))
        probe.columnconfigure(0, weight=1)
        ttk.Label(probe, style="Hint.TLabel", wraplength=300, justify="left",
                  text="Đường phụ, cần cảm biến chạm. Căn tâm mâm cặp bên phải là "
                       "đủ cho gốc X và Z; cái này để máy tự tìm mép khi cần. Rà mỏ "
                       "vào khoảng giữa mặt trên phôi rồi bấm.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        from ..probing import ROUTINES
        self._probe_keys = list(ROUTINES)
        self.cmb_probe = ttk.Combobox(probe, state="readonly", width=30,
                                      values=[ROUTINES[k][0] for k in self._probe_keys])
        self.cmb_probe.current(len(self._probe_keys) - 1)
        self.cmb_probe.grid(row=1, column=0, sticky="ew")
        self.btn_probe = ttk.Button(probe, text="Bắt đầu dò", width=12,
                                    style="Accent.TButton", command=self.start_probe)
        self.btn_probe.grid(row=1, column=1, padx=(4, 0))
        sp0 = self.profile.probe
        ttk.Button(probe, text="Thông số dò...", command=self.show_probe_options).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        # Mười hai ô thông số nằm trong hộp thoại riêng: cột này đã chật, mà
        # khai xong rồi thì hầu như không đụng lại nữa.
        self._probe_dlg = tk.Toplevel(self.root)
        self._probe_dlg.title("Thông số dò cạnh")
        self._probe_dlg.withdraw()
        self._probe_dlg.protocol("WM_DELETE_WINDOW", self._probe_dlg.withdraw)
        self._probe_dlg.resizable(False, False)
        box = ttk.Frame(self._probe_dlg, padding=PAD)
        box.pack(fill="both", expand=True)
        self.f_probe = FieldGrid(box, [
            ("probe_below", "Đầu dò thấp hơn mỏ [mm]", sp0.probe_below),
            ("max_depth", "Quãng dò tối đa [mm]", sp0.max_depth),
            ("offset_x", "Đầu dò lệch ngang [mm]", sp0.offset_x),
            ("offset_y", "Đầu dò lệch dọc [mm]", sp0.offset_y),
            ("ohmic", "Dò bằng chính mỏ cắt", sp0.ohmic, "bool"),
            ("ohmic_output", "Ngõ ra rơ-le dây dò", float(sp0.ohmic_output)),
            ("seek_feed", "Tốc độ dò [mm/ph]", sp0.seek_feed),
            ("latch_feed", "Tốc độ dò lại [mm/ph]", sp0.latch_feed),
            ("swivel", "Có đầu đảo", sp0.swivel, "bool"),
            ("swivel_z", "Cao độ xoay đảo [mm]", sp0.swivel_z),
            ("swivel_torch", "Góc đảo: mỏ cắt [độ]", sp0.swivel_torch),
            ("swivel_probe", "Góc đảo: đầu dò [độ]", sp0.swivel_probe),
        ], columns=2)
        self.f_probe.pack(fill="x")
        ttk.Label(box, style="Hint.TLabel", wraplength=420, justify="left",
                  text="Dò bằng chính mỏ cắt: kẹp dây vào béc, mọi số lệch để 0. "
                       "Ngõ ra rơ-le = -1 nếu đấu chết không có rơ-le tách dây. "
                       "Dùng đầu dò riêng trên đầu đảo thì bật ô 'Có đầu đảo' và "
                       "khai đầu dò thấp hơn mỏ bao nhiêu.").pack(anchor="w", pady=(8, 6))
        ttk.Button(box, text="Đóng", command=self._probe_dlg.withdraw).pack(anchor="e")

        self.lbl_probe = ttk.Label(probe, style="Dim.TLabel", wraplength=300,
                                   justify="left", text="")
        self.lbl_probe.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        right = ttk.Frame(t)
        right.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self._build_clamp_frame(right)
        ttk.Label(right, text="Nhật ký giao tiếp").pack(anchor="w", pady=(PAD, 0))
        self.console = Console(right, on_send=self.send_manual)
        self.console.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Căn tâm mâm cặp: chạm bốn mặt ống, một lần, dùng mãi
    # ------------------------------------------------------------------
    def _build_clamp_frame(self, parent) -> None:
        from ..clamp import TOUCH_LABELS, TOUCH_ORDER, Touch
        cal = self.profile.clamp
        self._touches = {k: Touch(dict(v.pos)) for k, v in cal.touches.items()}

        f = ttk.LabelFrame(parent, text="Căn tâm mâm cặp (căn một lần, dùng mãi)",
                           padding=PAD)
        f.pack(side="top", fill="x")
        f.columnconfigure(2, weight=1)
        ttk.Label(f, style="Hint.TLabel", wraplength=560, justify="left",
                  text="Mâm cặp tự định tâm nên tâm nó là hằng số cơ khí của máy, "
                       "không phải của phôi. Chạm mỏ vào bốn mặt ống một lần là "
                       "xong: sau này thay ống cỡ khác chỉ việc khai lại kích "
                       "thước, phần mềm tự tính gốc X và gốc Z mới, khỏi căn "
                       "lại.").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        self._touch_rows: Dict[str, ttk.Label] = {}
        for i, key in enumerate(TOUCH_ORDER):
            r = i + 1
            ttk.Label(f, text=f"{i + 1}. {TOUCH_LABELS[key]}").grid(
                row=r, column=0, sticky="w", pady=1)
            ttk.Button(f, text="Ghi", width=6,
                       command=lambda k=key: self.clamp_record(k)).grid(
                row=r, column=1, sticky="w", padx=6)
            lbl = ttk.Label(f, style="Dim.TLabel", text="chưa ghi")
            lbl.grid(row=r, column=2, columnspan=2, sticky="w")
            self._touch_rows[key] = lbl

        r = len(TOUCH_ORDER) + 1
        self.lbl_clamp_hint = ttk.Label(f, style="Hint.TLabel", wraplength=560,
                                        justify="left", text="")
        self.lbl_clamp_hint.grid(row=r, column=0, columnspan=4, sticky="w", pady=(4, 4))

        bar = ttk.Frame(f)
        bar.grid(row=r + 1, column=0, columnspan=4, sticky="ew")
        ttk.Button(bar, text="Tính tâm", style="Accent.TButton",
                   command=self.clamp_solve).pack(side="left")
        ttk.Button(bar, text="Xoá số đo", command=self.clamp_clear).pack(side="left", padx=4)
        self.var_auto_limits = tk.BooleanVar(value=cal.auto_limits)
        ttk.Checkbutton(bar, text="Tự siết hành trình theo cỡ ống",
                        variable=self.var_auto_limits,
                        command=self.clamp_sync).pack(side="left", padx=(12, 4))
        ttk.Label(bar, text="chừa thêm").pack(side="left")
        self.var_clamp_margin = tk.StringVar(value=f"{cal.margin:g}")
        ttk.Entry(bar, textvariable=self.var_clamp_margin, width=5).pack(side="left", padx=3)
        ttk.Label(bar, text="mm").pack(side="left")

        self.lbl_clamp = ttk.Label(f, style="Dim.TLabel", wraplength=560,
                                   justify="left", text=cal.summary())
        self.lbl_clamp.grid(row=r + 2, column=0, columnspan=4, sticky="w", pady=(6, 4))

        zbar = ttk.Frame(f)
        zbar.grid(row=r + 3, column=0, columnspan=4, sticky="ew")
        ttk.Button(zbar, text="Đặt gốc X-Z từ tâm kẹp", style="Accent.TButton",
                   command=self.clamp_apply_zero).pack(side="left")
        along = self.profile.letter(ROLE_ALONG) or "Y"
        rotary = self.profile.letter(ROLE_ROTARY) or "A"
        ttk.Button(zbar, text=f"Đặt gốc {along} tại đây",
                   command=lambda: self.zero_here(ROLE_ALONG)).pack(side="left", padx=4)
        ttk.Button(zbar, text=f"Đặt gốc {rotary} tại đây",
                   command=lambda: self.zero_here(ROLE_ROTARY)).pack(side="left")
        ttk.Label(f, style="Hint.TLabel", wraplength=560, justify="left",
                  text=f"Gốc X và Z suy thẳng từ tâm kẹp nên mỏ đang đứng đâu cũng "
                       f"bấm được. Còn gốc {along} (chỗ nào trên ống) thì rà tay tới "
                       f"đúng chỗ muốn cắt rồi bấm - chỉ đâu cắt đó.").grid(
            row=r + 4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self._refresh_clamp_rows()

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
        self.lbl_order = ttk.Label(order, style="Dim.TLabel",
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
        self.lbl_op_desc = ttk.Label(right, text="", wraplength=330, style="Dim.TLabel")
        self.lbl_op_desc.pack(anchor="w", pady=(0, PAD))
        self.form = ParamForm(right, on_change=self.apply_operation_params)
        self.form.pack(fill="x")
        ttk.Button(right, text="Sinh G-code", command=self.generate,
                   style="Accent.TButton").pack(side="bottom", fill="x", pady=(PAD, 0))

    # ------------------------------------------------------------------
    def _build_preview_tab(self) -> None:
        t = self.tab_preview
        self.preview = PreviewCanvas(t)
        self.preview.pack(side="top", fill="both", expand=True)
        bar = ttk.Frame(t)
        bar.pack(side="bottom", fill="x", pady=(PAD, 0))
        ttk.Button(bar, text="Sinh lại G-code", command=self.generate,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(bar, text="Xuất SVG...", command=self.export_svg).pack(side="left", padx=6)
        self.lbl_stats = ttk.Label(bar, text="", style="Head.TLabel")
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
        self.lbl_sim_info = ttk.Label(t, text="", style="Dim.TLabel")
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
        self.btn_start = ttk.Button(bar, text="BẮT ĐẦU CẮT", command=self.start_job,
                                    width=16, style="Accent.TButton")
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(bar, text="Tạm dừng", command=self.toggle_pause,
                                    width=12, state="disabled")
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(bar, text="DỪNG", command=self.stop_job, style="Danger.TButton",
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
        _p = theme.current()
        self.txt_gcode = tk.Text(gc, wrap="none", font=("Consolas", 9),
                                 background=_p.field, foreground=_p.fg,
                                 insertbackground=_p.fg, relief="flat",
                                 highlightthickness=1, highlightbackground=_p.border)
        self.txt_gcode.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(gc, orient="vertical", command=self.txt_gcode.yview)
        sb.pack(side="right", fill="y")
        self.txt_gcode.configure(yscrollcommand=sb.set)
        self.txt_gcode.tag_configure("cur", background=_p.highlight)

        info = ttk.LabelFrame(body, text="Theo dõi", padding=PAD)
        info.grid(row=0, column=1, sticky="nsew")
        self.run_console = Console(info, on_send=self.send_manual)
        self.run_console.pack(fill="both", expand=True)

    # ==================================================================
    # Căn tâm mâm cặp
    # ==================================================================
    def _clamp_letters(self) -> Dict[str, str]:
        return {"cross": self.profile.letter(ROLE_CROSS) or "X",
                "radial": self.profile.letter(ROLE_RADIAL) or "Z",
                "rotary": self.profile.letter(ROLE_ROTARY) or "A"}

    def clamp_record(self, key: str) -> None:
        """Ghi lại toạ độ **máy** ngay lúc mỏ đang chạm."""
        from ..clamp import Touch
        st = self.controller.status
        mpos = dict(st.mpos) if st and st.mpos else {}
        if not mpos:
            messagebox.showwarning(
                "Chưa có toạ độ máy",
                "Chưa đọc được toạ độ máy. Nối máy (hoặc bật máy ảo) và chờ dòng "
                "trạng thái hiện số rồi hãy ghi.\n\nPhải dùng toạ độ máy chứ không "
                "phải toạ độ chi tiết: gốc chi tiết còn thay đổi, tâm mâm cặp thì "
                "không.")
            return
        self._touches[key] = Touch({k.upper(): float(v) for k, v in mpos.items()})
        self._refresh_clamp_rows()

    def clamp_clear(self) -> None:
        self._touches = {}
        self._refresh_clamp_rows()
        self.status_var.set("Đã xoá số đo căn tâm (hồ sơ căn cũ vẫn còn).")

    def _refresh_clamp_rows(self) -> None:
        from ..clamp import TOUCH_HINTS, TOUCH_ORDER
        lt = self._clamp_letters()
        for key in TOUCH_ORDER:
            t = self._touches.get(key)
            if t is None:
                self._touch_rows[key].configure(text="chưa ghi", style="Dim.TLabel")
            else:
                self._touch_rows[key].configure(
                    text="  ".join(f"{c}{t.get(c):.3f}" for c in
                                   (lt["cross"], lt["radial"], lt["rotary"])),
                    style="Ok.TLabel")
        nxt = next((k for k in TOUCH_ORDER if k not in self._touches), None)
        self.lbl_clamp_hint.configure(
            text=TOUCH_HINTS[nxt] if nxt else "Đủ bốn lần chạm - bấm Tính tâm.")

    def clamp_sync(self) -> None:
        """Đưa hai ô tuỳ chọn vào hồ sơ căn (giới hạn tính lại ngay lập tức)."""
        cal = self.profile.clamp
        cal.auto_limits = bool(self.var_auto_limits.get())
        try:
            cal.margin = max(0.0, float(str(self.var_clamp_margin.get()).replace(",", ".")))
        except ValueError:
            pass

    def clamp_solve(self) -> None:
        from ..clamp import ClampError, limit_report, solve
        self.apply_profile(silent=True)
        self.clamp_sync()
        try:
            cal, warns = solve(self._touches, self.profile.pipe,
                               letters=self._clamp_letters(),
                               margin=self.profile.clamp.margin)
        except ClampError as exc:
            messagebox.showwarning("Chưa căn được", str(exc))
            return
        cal.auto_limits = self.profile.clamp.auto_limits
        self.profile.clamp = cal
        self.controller.profile = self.profile
        lines = [cal.summary(),
                 f"Bề rộng đo được {cal.span_x:.2f} mm, lệch tâm {cal.runout:+.2f} mm."]
        lines += limit_report(self.profile)
        self.lbl_clamp.configure(text="  ·  ".join(lines[:2]) + "\n" + " | ".join(lines[2:]))
        self.status_var.set("Đã căn tâm mâm cặp. Nhớ Lưu hồ sơ máy để dùng lần sau.")
        body = "\n".join(lines)
        if warns:
            messagebox.showwarning("Căn xong, có điều cần xem lại",
                                   body + "\n\n" + "\n\n".join("• " + w for w in warns))
        else:
            messagebox.showinfo(
                "Đã căn tâm mâm cặp",
                body + "\n\nLưu hồ sơ máy (thẻ Máy → Lưu hồ sơ máy) thì lần sau "
                       "mở phần mềm là có sẵn, không phải căn lại.")

    def clamp_apply_zero(self) -> None:
        """Đặt gốc X-Z thẳng từ tâm mâm cặp - không cần rà mỏ vào đâu cả."""
        from ..clamp import ClampError, work_origin, zero_commands
        self.apply_profile(silent=True)
        self.clamp_sync()
        try:
            org = work_origin(self.profile.clamp, self.profile.pipe)
            lines = zero_commands(self.profile)
        except ClampError as exc:
            messagebox.showwarning("Chưa căn tâm", str(exc))
            return
        if not self.controller.is_connected:
            messagebox.showwarning("Chưa nối máy", "Nối máy trước rồi hãy đặt gốc.")
            return
        lt = self._clamp_letters()
        if not messagebox.askokcancel(
                "Đặt gốc từ tâm mâm cặp",
                f"Ống đang khai: {self.profile.pipe.size_text}\n\n"
                f"Gốc {lt['cross']} đặt tại toạ độ máy {org['X']:.3f} (đường tâm ống)\n"
                f"Gốc {lt['radial']} đặt tại toạ độ máy {org['Z']:.3f} (mặt trên phôi)\n\n"
                f"Máy không di chuyển, chỉ đổi gốc toạ độ.\n"
                f"Gốc dọc ống và gốc xoay giữ nguyên."):
            return
        for line in lines:
            self.controller.send(line, front=True)
        self.status_var.set(f"Đã đặt gốc {lt['cross']}-{lt['radial']} từ tâm mâm cặp.")

    def show_probe_options(self) -> None:
        dlg = self._probe_dlg
        dlg.configure(background=theme.current().bg)
        dlg.transient(self.root)
        dlg.deiconify()
        dlg.lift()

    def zero_here(self, role: str) -> None:
        """Đặt gốc của **một** trục tại chỗ mỏ đang đứng - chỉ đâu cắt đó."""
        letter = self.profile.letter(role)
        if not letter:
            return
        if not self.controller.is_connected:
            messagebox.showwarning("Chưa nối máy", "Nối máy trước rồi hãy đặt gốc.")
            return
        self.controller.send(f"G10 L20 P1 {letter}0", front=True)
        self.status_var.set(f"Đã đặt gốc {letter} tại vị trí hiện tại.")

    # ==================================================================
    # Dò cạnh
    # ==================================================================
    def start_probe(self) -> None:
        """Chạy quy trình dò cạnh đang chọn."""
        if not self.controller.is_connected:
            messagebox.showwarning("Chưa kết nối", "Hãy kết nối máy trước khi dò.")
            return
        from ..probing import ROUTINES, ProbeError
        key = self._probe_keys[max(0, self.cmb_probe.current())]
        label, factory = ROUTINES[key]
        self.apply_profile(silent=True)
        sp = self.profile.probe
        for name in ("probe_below", "offset_x", "offset_y", "max_depth",
                     "swivel_z", "swivel_torch", "swivel_probe",
                     "seek_feed", "latch_feed"):
            setattr(sp, name, self.f_probe.get(name, getattr(sp, name)))
        sp.swivel = bool(self.f_probe.get("swivel", sp.swivel))
        sp.ohmic = bool(self.f_probe.get("ohmic", sp.ohmic))
        sp.ohmic_output = int(self.f_probe.get("ohmic_output", sp.ohmic_output))
        warns = self.profile.probe.validate()
        if warns:
            messagebox.showerror("Thông số dò không hợp lệ", "\n".join(warns))
            return
        # Điểm xuất phát là **chỗ mỏ đang đứng thật**, không phải gốc 0.
        status = self.controller.status
        start = dict(status.wpos or status.mpos) if status else {}
        if not start:
            messagebox.showwarning(
                "Chưa biết vị trí mỏ",
                "Chưa nhận được toạ độ từ máy. Chờ vài giây rồi thử lại.")
            return
        checks = [f"{label}", "", "Máy sẽ hạ xuống dò phôi. Hãy chắc chắn:",
                  "  • nguồn cắt ĐANG TẮT",
                  "  • cảm biến chạm nối đúng và thử được"]
        if sp.ohmic:
            checks.append("  • dây dò đã kẹp vào đầu mỏ — mỏ CHÍNH LÀ đầu dò")
            if sp.ohmic_output >= 0:
                checks.append(f"  • rơ-le dây dò ở ngõ ra {sp.ohmic_output} "
                              f"(phần mềm tự đóng/ngắt)")
        if sp.swivel:
            checks.append(f"  • máy sẽ NÂNG LÊN {sp.swivel_z:g} mm rồi xoay đầu "
                          f"đảo sang đầu dò ({sp.swivel_probe:g}°), xong tự trả "
                          f"về mỏ cắt ({sp.swivel_torch:g}°)")
        if sp.has_offset:
            checks.append("  • ĐẦU DÒ (không phải mũi cắt) đang ở khoảng giữa "
                          "mặt trên phôi")
            checks.append(f"  • đầu dò thấp hơn mũi cắt {sp.probe_below:g} mm")
        else:
            checks.append("  • mũi cắt đang ở khoảng giữa mặt trên phôi")
        checks += ["", "Vị trí hiện tại: "
                   + ", ".join(f"{k}{v:.1f}" for k, v in start.items())]
        if not messagebox.askokcancel("Bắt đầu dò cạnh", "\n".join(checks)):
            return
        try:
            from ..probing import disarm_lines, with_probe_setup
            routine = with_probe_setup(
                self.profile, sp,
                factory(self.profile, sp, start=start))
            cleanup = disarm_lines(self.profile, sp)
        except ProbeError as exc:
            messagebox.showerror("Không dò được", str(exc))
            return
        self.btn_probe.configure(state="disabled", text="Đang dò...")
        self.lbl_probe.configure(text="Đang dò...")
        self.controller.run_probe(
            routine, cleanup=cleanup,
            on_done=lambda out, err: self.events.put(("probe", out, err)),
            on_step=lambda note: self.events.put(("probe_step", note)))

    def _on_probe_step(self, note: str) -> None:
        self.lbl_probe.configure(text=f"Đang dò: {note}")

    def _on_probe_done(self, outcome, error) -> None:
        self.btn_probe.configure(state="normal", text="Bắt đầu dò")
        if error is not None or outcome is None:
            self.lbl_probe.configure(text=f"Dò dừng: {error}")
            messagebox.showerror("Dò cạnh không xong", str(error))
            return
        lines = [f"{k}: {v:.3f}" for k, v in outcome.values.items()]
        self.lbl_probe.configure(text=" · ".join(lines[:3]) or outcome.kind)
        body = [outcome.kind, ""] + lines
        if outcome.notes:
            body += [""] + outcome.notes
        if outcome.warnings:
            body += [""] + ["[!] " + w for w in outcome.warnings]
        self.status_var.set(f"Dò xong: {outcome.kind}")
        if outcome.warnings:
            messagebox.showwarning("Dò xong, có cảnh báo", "\n".join(body))
        else:
            messagebox.showinfo("Dò xong", "\n".join(body))

    # ==================================================================
    # Chế độ hiển thị
    # ==================================================================
    def _update_theme_button(self) -> None:
        other = theme.DARK if self.theme_name == "light" else theme.LIGHT
        self.btn_theme.configure(text=f"◐  Nền {other.label.lower()}")

    def toggle_theme(self) -> None:
        """Đổi qua lại giữa nền sáng và nền tối."""
        self.set_theme("dark" if self.theme_name == "light" else "light")

    def set_theme(self, name: str) -> None:
        self.theme_name = name
        theme.apply(self.root, name)
        theme.notify()                 # báo cho mọi lớp vẽ tự đổi màu
        theme.save_preference(name)
        self._update_theme_button()
        self._retheme_widgets()

    def _retheme_widgets(self) -> None:
        """Đổi màu những widget Tk thuần - ttk.Style không với tới được."""
        p = theme.current()
        col = getattr(self, "control_column", None)
        if col is not None:
            col.apply_theme()
        dlg = getattr(self, "_probe_dlg", None)
        if dlg is not None:
            try:
                dlg.configure(background=p.bg)
            except tk.TclError:
                pass
        try:
            self.txt_gcode.configure(background=p.field, foreground=p.fg,
                                     insertbackground=p.fg,
                                     highlightbackground=p.border)
            self.txt_gcode.tag_configure("cur", background=p.highlight)
        except tk.TclError:
            pass
        for view in (getattr(self, "preview", None), getattr(self, "machine_view", None),
                     getattr(self, "sim_view", None)):
            if view is not None and hasattr(view, "apply_theme"):
                try:
                    view.apply_theme()
                except tk.TclError:
                    pass
        self.status_var.set(f"Đã chuyển sang nền {p.label.lower()}.")

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
            self.btn_connect.configure(text="Kết nối", style="Accent.TButton")
            self.badge.set_state(None)
            self.lbl_conn.configure(text="Chọn cổng ở thẻ 1 rồi bấm Kết nối")
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
        self.btn_connect.configure(text="Ngắt kết nối", style="TButton")
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
                elif kind == "probe":
                    self._on_probe_done(item[1], item[2])
                elif kind == "probe_step":
                    self._on_probe_step(item[1])
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
        p.motion.corner_pivot_arcs = max(1, int(self.f_motion.get(
            "corner_pivot_arcs", p.motion.corner_pivot_arcs)))
        try:
            p.connection.baudrate = int(self.cmb_baud.get())
            p.connection.simulator_speed = max(0.01, float(self.cmb_simspeed.get()))
        except ValueError:
            pass
        if hasattr(self, "var_auto_limits"):
            self.clamp_sync()
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
                auto = " (phần mềm tự lấy vì ô bán kính để 0)" \
                    if p.pipe.corner_radius <= 0 else ""
                note += (f" · góc lượn R{sec.rc:.1f}{auto}"
                         f" · trục ngang cần chạy ±{sec.hx - sec.rc:.0f} mm")
                # Ghi luôn số thật vào ô nhập để người dùng không phải đoán:
                # gõ 0 rồi thấy máy báo R6 thì rất dễ tưởng phần mềm bỏ qua.
                if p.pipe.corner_radius <= 0 and "corner_radius" in self.f_pipe.vars:
                    self.f_pipe.vars["corner_radius"].set(f"{sec.rc:g}")
                    p.pipe.corner_radius = sec.rc
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
