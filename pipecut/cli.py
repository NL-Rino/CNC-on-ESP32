"""Giao diện dòng lệnh của PipeCut Studio.

Ví dụ::

    python -m pipecut ports                       # liệt kê cổng COM
    python -m pipecut scan                        # dò ESP32 trong mạng LAN
    python -m pipecut ops                         # xem danh mục nguyên công
    python -m pipecut import ban_ve.dxf           # xem thử một tệp nhập vào
    python -m pipecut gen examples/ong_T.json -o ra.nc --svg xem.svg
    python -m pipecut sim ra.nc                   # chạy thử trên máy ảo
    python -m pipecut sim ra.nc --serve 2323      # máy ảo mở cổng mạng
    python -m pipecut send ra.nc --port COM5      # nạp xuống máy thật
    python -m pipecut send ra.nc --port 192.168.1.50   # nạp qua WiFi/LAN
    python -m pipecut run examples/ong_T.json --port COM5
    python -m pipecut ui                          # mở giao diện đồ hoạ
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional, Sequence

from . import __version__
from .config import MachineProfile, find_profile
from .gcode import build_program
from .jobs import OP_CATALOG, Job
from .transport import discover_lan, list_ports


# --------------------------------------------------------------------------
def _apply_theme(name: Optional[str]) -> None:
    """Đặt tông màu cho bản vẽ SVG xuất ra từ dòng lệnh."""
    if not name:
        return
    from . import palette
    if name not in palette.THEMES:
        print(f"  [!] Không có tông màu '{name}'. Chọn: "
              + ", ".join(palette.THEMES), file=sys.stderr)
        return
    palette.set_palette(name)
    palette.notify()


def _load_profile(path: Optional[str]) -> MachineProfile:
    profile = MachineProfile.load(path) if path else find_profile()
    for w in profile.validate():
        print(f"  [!] Cấu hình máy: {w}", file=sys.stderr)
    return profile


def _bar(fraction: float, width: int = 34) -> str:
    n = int(max(0.0, min(1.0, fraction)) * width)
    return "[" + "#" * n + "-" * (width - n) + "]"


# --------------------------------------------------------------------------
def cmd_ports(args: argparse.Namespace) -> int:
    print("Cổng nối tiếp khả dụng:")
    for port, desc in list_ports():
        print(f"  {port:<14} {desc}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    print(f"Đang dò FluidNC trong mạng LAN (cổng {args.tcp_port}, "
          f"chờ tối đa {args.timeout:g}s mỗi địa chỉ)...")
    found = discover_lan(port=args.tcp_port, timeout=args.timeout)
    if not found:
        print("  Không thấy máy nào. Kiểm tra ESP32 đã nối cùng mạng WiFi và "
              "đã bật Telnet trong FluidNC chưa.")
        return 1
    for addr, desc in found:
        print(f"  {addr:<22} {desc}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """Xem thử một tệp nhập vào trước khi đưa vào công việc."""
    from .importers import ImportError_, describe_file, detect_format, load_curves

    profile = _load_profile(args.profile)
    section = profile.pipe.section()
    notes: List[str] = []
    try:
        fmt = detect_format(args.file)
        curves = load_curves(args.file, section=section,
                             tolerance=profile.motion.chord_tolerance,
                             layers=args.layers.split(",") if args.layers else None,
                             mesh_axis=args.mesh_axis, mesh_roll=args.mesh_roll,
                             mesh_tolerance=args.mesh_tol, notes=notes)
    except ImportError_ as exc:
        print(f"  [!] {exc}", file=sys.stderr)
        return 2
    print(f"{args.file}\n  định dạng : {fmt}\n  phôi      : {section.describe()}")
    for note in notes:
        print(f"  [!] {note}")
    print(f"\n  {'#':<4}{'tên':<14}{'điểm':>7}{'dài (mm)':>11}  {'kiểu':<10}"
          f"{'khổ u × v (mm)':>22}")
    for i, c in enumerate(curves, 1):
        x0, y0, x1, y1 = c.bounds()
        kind = "quấn vòng" if c.wrap else ("khép kín" if c.closed else "hở")
        print(f"  {i:<4}{(c.layer or c.name)[:13]:<14}{len(c.points):>7}"
              f"{c.length:>11.2f}  {kind:<10}{f'{x1-x0:.1f} × {y1-y0:.1f}':>22}")
    total = sum(c.length for c in curves)
    print(f"\n  Tổng: {len(curves)} đường, {total:.1f} mm đường cắt.")
    print(f"  Dùng trong tệp công việc: nguyên công 'pattern' với file=\"{args.file}\".")
    return 0


def cmd_ops(args: argparse.Namespace) -> int:
    print("Danh mục nguyên công (dùng trong tệp công việc .json):\n")
    for key, spec in OP_CATALOG.items():
        print(f"  {key:<11} {spec['label']}")
        print(f"  {'':<11} {spec['desc']}")
        for p in spec["params"]:
            unit = f" [{p['unit']}]" if p["unit"] else ""
            hint = f"  - {p['hint']}" if p["hint"] else ""
            print(f"  {'':<13} {p['name']:<15} {p['label']}{unit} = {p['default']!r}{hint}")
        print()
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    if args.init:
        profile = MachineProfile()
        os.makedirs(os.path.dirname(os.path.abspath(args.init)) or ".", exist_ok=True)
        profile.save(args.init)
        print(f"Đã tạo hồ sơ máy mặc định: {args.init}")
        return 0
    profile = _load_profile(args.profile)
    print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_gen(args: argparse.Namespace) -> int:
    _apply_theme(getattr(args, "theme", None))
    profile = _load_profile(args.profile)
    job = Job.load(args.job)
    if getattr(args, "shape", None):
        profile.pipe.shape = args.shape
    if args.diameter:
        profile.pipe.outer_diameter = args.diameter
    if getattr(args, "width", None):
        profile.pipe.width = args.width
    if getattr(args, "height", None):
        profile.pipe.height = args.height
    if args.feed:
        profile.process.cut_feed = args.feed
    if args.kerf is not None:
        profile.process.kerf = args.kerf
    toolpath, warns = job.build_toolpath(profile)
    if not toolpath.contours:
        print("Không có biên dạng nào được tạo.", file=sys.stderr)
        for w in warns:
            print(f"  [!] {w}", file=sys.stderr)
        return 2
    program = build_program(profile, toolpath, job.name)
    out = args.output or os.path.splitext(args.job)[0] + ".nc"
    program.save(out)

    s = program.stats
    print(f"Công việc      : {job.name}")
    print(f"Phôi           : {profile.pipe.section().describe()} "
          f"x dày {profile.pipe.wall_thickness:.1f} mm")
    print(f"Số biên dạng   : {len(toolpath.contours)}")
    print(f"Chiều dài cắt  : {s.cut_length:.1f} mm  ({s.pierces} điểm mồi)")
    print(f"Số dòng G-code : {s.lines}  ({s.moves} lệnh dịch chuyển)")
    print(f"Thời gian ước  : {s.time_text}")
    print(f"Giới hạn trục  : " + ", ".join(f"{k}:{v[0]:.1f}..{v[1]:.1f}" for k, v in s.bounds.items()))
    print(f"Đã ghi         : {out}")
    for w in warns + s.warnings:
        print(f"  [!] {w}")
    if args.svg:
        from .svgview import save_svg
        save_svg(args.svg, profile, program.passes, title=f"{job.name} - {profile.name}")
        print(f"Bản xem trước  : {args.svg}")
    if getattr(args, "machine_svg", None):
        from .gsim import Playback
        from .svgview import save_machine_svg
        pb = Playback(profile, program.stream_lines())
        at = max(0.0, min(1.0, (args.at or 60.0) / 100.0)) * pb.duration
        from .config import ROLE_ALONG
        letter = profile.letter(ROLE_ALONG)
        save_machine_svg(args.machine_svg, profile, pb.state_at(at), pb.trace_until(at),
                         title=f"{job.name} - giây {at:.1f}/{pb.duration:.1f}",
                         along_range=pb.axis_range(letter) if letter else None)
        print(f"Ảnh mô phỏng   : {args.machine_svg}  (tại giây {at:.1f})")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    _apply_theme(getattr(args, "theme", None))
    args.output = os.devnull
    args.svg = args.svg or os.path.splitext(args.job)[0] + ".svg"
    return cmd_gen(args)


def _stream(profile: MachineProfile, lines: Sequence[str], port: str,
            baud: Optional[int] = None, quiet: bool = False,
            time_scale: Optional[float] = None) -> int:
    from .controller import DeviceController

    controller = DeviceController(profile)
    simulator = None
    if port.upper() in ("GIA-LAP", "SIM", "SIMULATOR"):
        from .simulator import FluidNCSimulator
        simulator = FluidNCSimulator(axes="".join(profile.letters),
                                     rx_buffer=profile.connection.rx_buffer,
                                     time_scale=time_scale or profile.connection.simulator_speed)
    errors: List[str] = []
    controller.on_event = lambda kind, text: (
        errors.append(text) if kind in ("error", "alarm") else None,
        print(f"\n  * {text}") if not quiet else None,
    )
    try:
        controller.connect(port=port, baudrate=baud, simulator=simulator)
    except Exception as exc:
        print(f"Không kết nối được: {exc}", file=sys.stderr)
        return 3
    time.sleep(profile.connection.connect_delay if simulator is None else 0.1)
    controller.query_firmware()
    time.sleep(0.3)
    controller.start_job(lines)
    try:
        while controller.progress.running:
            p = controller.progress
            st = controller.status
            pos = ""
            if st and st.mpos:
                pos = " ".join(f"{k}{v:8.2f}" for k, v in st.mpos.items())
            sys.stdout.write(
                f"\r{_bar(p.acked / max(p.total, 1))} {p.percent:5.1f}%  "
                f"{p.acked}/{p.total}  {st.state_vi if st else '...':<10} {pos}   "
            )
            sys.stdout.flush()
            time.sleep(0.15)
        controller.wait_idle(120.0)
    except KeyboardInterrupt:
        controller.stop_job()
        print("\nĐã dừng theo yêu cầu người dùng.")
        controller.disconnect()
        return 130
    p = controller.progress
    sys.stdout.write(f"\r{_bar(1.0)} 100.0%  {p.acked}/{p.total} dòng"
                     f"  trong {p.elapsed:.1f}s{' ' * 30}\n")
    controller.disconnect()
    if p.errors or errors:
        for e in p.errors:
            print(f"  [!] {e}")
        return 4
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    with open(args.file, "r", encoding="utf-8") as fh:
        raw = fh.read().splitlines()
    from .gcode import strip_gcode_comment
    lines = [strip_gcode_comment(l) for l in raw]
    lines = [l for l in lines if l]
    print(f"Nạp {len(lines)} dòng từ {args.file} tới {args.port}")
    return _stream(profile, lines, args.port, args.baud, args.quiet)


def cmd_sim(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    if getattr(args, "speed", None):
        profile.connection.simulator_speed = args.speed
    with open(args.file, "r", encoding="utf-8") as fh:
        raw = fh.read().splitlines()
    from .gcode import strip_gcode_comment
    lines = [l for l in (strip_gcode_comment(x) for x in raw) if l]
    print(f"Chạy thử {len(lines)} dòng trên máy ảo "
          f"(tốc độ x{profile.connection.simulator_speed:g})")
    if getattr(args, "serve", None):
        return _serve_sim(profile, args.serve)
    return _stream(profile, lines, "GIA-LAP", None, args.quiet)


def _serve_sim(profile: MachineProfile, port: int) -> int:
    """Mở máy ảo ra mạng LAN: thử toàn bộ đường kết nối WiFi mà không cần ESP32."""
    import socket

    from .simulator import FluidNCServer, FluidNCSimulator

    sim = FluidNCSimulator(
        axes="".join(a.letter for a in profile.axes),
        rx_buffer=profile.connection.rx_buffer,
        time_scale=profile.connection.simulator_speed,
    )
    # 0.0.0.0 để máy khác trong mạng LAN cũng nối tới thử được
    server = FluidNCServer(sim, host="0.0.0.0", port=port)
    actual = server.start()
    try:
        host = socket.gethostbyname(socket.gethostname())
    except OSError:
        host = "127.0.0.1"
    print(f"Máy ảo đang lắng nghe tại {host}:{actual} (và 127.0.0.1:{actual}).")
    print(f"Nạp thử bằng:  python -m pipecut send <tep.nc> --port {host}:{actual}")
    print("Nhấn Ctrl+C để dừng.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nĐã dừng máy ảo.")
    finally:
        server.stop()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    job = Job.load(args.job)
    toolpath, warns = job.build_toolpath(profile)
    for w in warns:
        print(f"  [!] {w}")
    if not toolpath.contours:
        return 2
    program = build_program(profile, toolpath, job.name)
    print(f"{job.name}: {program.stats.lines} dòng, ước tính {program.stats.time_text}")
    if not args.yes:
        answer = input("Bắt đầu cắt? Kiểm tra phôi và nguồn cắt trước. [y/N] ").strip().lower()
        if answer not in ("y", "yes", "c", "co", "có"):
            print("Đã huỷ.")
            return 1
    return _stream(profile, program.stream_lines(), args.port, args.baud, args.quiet)


def cmd_ui(args: argparse.Namespace) -> int:
    _apply_theme(getattr(args, "theme", None))
    try:
        from .ui.app import main as ui_main
    except ImportError as exc:
        print(f"Không mở được giao diện: {exc}", file=sys.stderr)
        print("Tkinter thường có sẵn cùng Python trên Windows/macOS.", file=sys.stderr)
        print("Trên Linux cài thêm:  sudo apt install python3-tk", file=sys.stderr)
        return 5
    return ui_main(profile_path=args.profile, job_path=args.job)


def cmd_demo(args: argparse.Namespace) -> int:
    """Sinh bộ tệp ví dụ để dùng thử ngay."""
    out_dir = args.dir
    os.makedirs(out_dir, exist_ok=True)
    job = Job(name="ong-nhanh-chu-T")
    job.add("ring_mark", x=40)
    job.add("hole", diameter=25, x=90, theta=0)
    job.add("hole", diameter=25, x=90, theta=180)
    job.add("slot", x=150, theta=90, length=45, width_deg=70, corner=5)
    job.add("saddle", main_diameter=114.3, angle=90, x=260)
    job.save(os.path.join(out_dir, "vi_du_ong_T.json"))
    print(f"Đã tạo tệp công việc mẫu trong: {out_dir}")
    print("Hồ sơ máy mẫu có sẵn trong thư mục config/")
    return 0


# --------------------------------------------------------------------------
def _add_profile_arg(sp: argparse.ArgumentParser) -> None:
    """Cho phép đặt --profile ở cả trước lẫn sau tên lệnh con.

    ``SUPPRESS`` để khi không gõ thì không ghi đè giá trị đã đặt ở mức trên.
    """
    sp.add_argument("-p", "--profile", default=argparse.SUPPRESS,
                    help="tệp hồ sơ máy (.json)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pipecut",
        description="PipeCut Studio - phần mềm máy cắt ống 4 trục ESP32/FluidNC",
    )
    ap.add_argument("--version", action="version", version=f"PipeCut Studio {__version__}")
    ap.add_argument("-p", "--profile", help="tệp hồ sơ máy (.json)")
    sub = ap.add_subparsers(dest="command")

    sub.add_parser("ports", help="liệt kê cổng COM").set_defaults(func=cmd_ports)
    sub.add_parser("ops", help="xem danh mục nguyên công").set_defaults(func=cmd_ops)

    sc = sub.add_parser("scan", help="dò tìm ESP32 trong mạng LAN")
    sc.add_argument("--tcp-port", type=int, default=23, help="cổng Telnet của FluidNC")
    sc.add_argument("--timeout", type=float, default=0.25, help="chờ mỗi địa chỉ (giây)")
    sc.set_defaults(func=cmd_scan)

    si = sub.add_parser("import", help="xem thử tệp DXF/SVG/G-code/STL trước khi dùng")
    si.add_argument("file")
    si.add_argument("--layers", default="", help="chỉ lấy các lớp DXF này, cách nhau bằng dấu phẩy")
    si.add_argument("--mesh-axis", default="auto", choices=["auto", "x", "y", "z"],
                    help="trục phôi trong mô hình 3D")
    si.add_argument("--mesh-roll", type=float, default=0.0,
                    help="mô hình 3D đang bị xoay quanh trục bao nhiêu độ")
    si.add_argument("--mesh-tol", type=float, default=0.4,
                    help="dung sai coi một mảnh lưới là còn nằm trên mặt phôi (mm)")
    _add_profile_arg(si)
    si.set_defaults(func=cmd_import)

    sp = sub.add_parser("profile", help="xem hoặc tạo hồ sơ máy")
    sp.add_argument("--init", metavar="TỆP", help="tạo hồ sơ mặc định")
    _add_profile_arg(sp)
    sp.set_defaults(func=cmd_profile)

    sg = sub.add_parser("gen", help="sinh G-code từ tệp công việc")
    sg.add_argument("job")
    sg.add_argument("-o", "--output", help="tệp .nc xuất ra")
    sg.add_argument("--svg", help="đồng thời xuất bản vẽ xem trước")
    sg.add_argument("--machine-svg", dest="machine_svg",
                    help="xuất ảnh mô phỏng máy (SVG) tại một thời điểm")
    sg.add_argument("--at", type=float,
                    help="thời điểm chụp ảnh mô phỏng, tính theo %% chương trình (mặc định 60)")
    sg.add_argument("--diameter", type=float, help="ghi đè đường kính ống tròn")
    sg.add_argument("--shape", choices=["round", "square", "rect"],
                    help="ghi đè hình dạng phôi")
    sg.add_argument("--width", type=float, help="ghi đè cạnh ngang ống hộp")
    sg.add_argument("--height", type=float, help="ghi đè cạnh dọc ống hộp")
    sg.add_argument("--feed", type=float, help="ghi đè tốc độ cắt")
    sg.add_argument("--kerf", type=float, help="ghi đè bề rộng mạch cắt")
    _add_profile_arg(sg)
    sg.add_argument("--theme", choices=["light", "dark"],
                    help="tông màu: sáng hoặc tối")
    sg.set_defaults(func=cmd_gen)

    spv = sub.add_parser("preview", help="chỉ xuất bản vẽ xem trước")
    spv.add_argument("job")
    spv.add_argument("--svg", help="tệp SVG xuất ra")
    spv.add_argument("--machine-svg", dest="machine_svg",
                     help="xuất thêm ảnh mô phỏng máy")
    spv.add_argument("--at", type=float, help="thời điểm chụp, %% chương trình")
    spv.add_argument("--diameter", type=float)
    spv.add_argument("--shape", choices=["round", "square", "rect"])
    spv.add_argument("--width", type=float)
    spv.add_argument("--height", type=float)
    spv.add_argument("--feed", type=float)
    spv.add_argument("--kerf", type=float)
    _add_profile_arg(spv)
    spv.add_argument("--theme", choices=["light", "dark"],
                    help="tông màu: sáng hoặc tối")
    spv.set_defaults(func=cmd_preview)

    ss = sub.add_parser("send", help="nạp tệp G-code xuống máy")
    ss.add_argument("file")
    ss.add_argument("--port", required=True, help="ví dụ COM5, /dev/ttyUSB0 hoặc GIA-LAP")
    ss.add_argument("--baud", type=int)
    ss.add_argument("-q", "--quiet", action="store_true")
    _add_profile_arg(ss)
    ss.set_defaults(func=cmd_send)

    sm = sub.add_parser("sim", help="chạy thử tệp G-code trên máy ảo")
    sm.add_argument("file")
    sm.add_argument("--speed", type=float, default=None,
                    help="hệ số tăng tốc máy ảo (1 = thời gian thực)")
    sm.add_argument("--serve", type=int, nargs="?", const=2323, default=None,
                    metavar="CONG",
                    help="mở máy ảo ra mạng LAN ở cổng này để thử phần kết nối WiFi")
    sm.add_argument("-q", "--quiet", action="store_true")
    _add_profile_arg(sm)
    sm.set_defaults(func=cmd_sim)

    sr = sub.add_parser("run", help="sinh G-code rồi nạp thẳng xuống máy")
    sr.add_argument("job")
    sr.add_argument("--port", required=True)
    sr.add_argument("--baud", type=int)
    sr.add_argument("-y", "--yes", action="store_true", help="không hỏi xác nhận")
    sr.add_argument("-q", "--quiet", action="store_true")
    _add_profile_arg(sr)
    sr.set_defaults(func=cmd_run)

    su = sub.add_parser("ui", help="mở giao diện đồ hoạ")
    su.add_argument("--job", help="mở sẵn một tệp công việc")
    _add_profile_arg(su)
    su.add_argument("--theme", choices=["light", "dark"],
                    help="tông màu: sáng hoặc tối")
    su.set_defaults(func=cmd_ui)

    sd = sub.add_parser("demo", help="tạo tệp cấu hình và công việc mẫu")
    sd.add_argument("--dir", default="examples")
    sd.set_defaults(func=cmd_demo)
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not hasattr(args, "profile"):
        args.profile = None
    if not getattr(args, "command", None):
        ap.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except FileNotFoundError as exc:
        print(f"Không tìm thấy tệp: {exc.filename}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nĐã huỷ.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
