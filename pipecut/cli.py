"""Giao diện dòng lệnh của PipeCut Studio.

Ví dụ::

    python -m pipecut ports                       # liệt kê cổng COM
    python -m pipecut ops                         # xem danh mục nguyên công
    python -m pipecut gen examples/ong_T.json -o ra.nc --svg xem.svg
    python -m pipecut sim ra.nc                   # chạy thử trên máy ảo
    python -m pipecut send ra.nc --port COM5      # nạp xuống máy thật
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
from .transport import list_ports


# --------------------------------------------------------------------------
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
    profile = _load_profile(args.profile)
    job = Job.load(args.job)
    if args.diameter:
        profile.pipe.outer_diameter = args.diameter
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
    print(f"Ống            : D{profile.pipe.outer_diameter:.1f} x {profile.pipe.wall_thickness:.1f} mm")
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
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
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
    return _stream(profile, lines, "GIA-LAP", None, args.quiet)


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
    profile = MachineProfile()
    profile.save(os.path.join(out_dir, "machine_demo.json"))

    job = Job(name="ong-nhanh-chu-T")
    job.add("ring_mark", x=40)
    job.add("hole", diameter=25, x=90, theta=0)
    job.add("hole", diameter=25, x=90, theta=180)
    job.add("slot", x=150, theta=90, length=45, width_deg=70, corner=5)
    job.add("saddle", main_diameter=114.3, angle=90, x=260)
    job.save(os.path.join(out_dir, "vi_du_ong_T.json"))
    print(f"Đã tạo tệp mẫu trong: {out_dir}")
    return 0


# --------------------------------------------------------------------------
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

    sp = sub.add_parser("profile", help="xem hoặc tạo hồ sơ máy")
    sp.add_argument("--init", metavar="TỆP", help="tạo hồ sơ mặc định")
    sp.set_defaults(func=cmd_profile)

    sg = sub.add_parser("gen", help="sinh G-code từ tệp công việc")
    sg.add_argument("job")
    sg.add_argument("-o", "--output", help="tệp .nc xuất ra")
    sg.add_argument("--svg", help="đồng thời xuất bản vẽ xem trước")
    sg.add_argument("--diameter", type=float, help="ghi đè đường kính ống")
    sg.add_argument("--feed", type=float, help="ghi đè tốc độ cắt")
    sg.add_argument("--kerf", type=float, help="ghi đè bề rộng mạch cắt")
    sg.set_defaults(func=cmd_gen)

    spv = sub.add_parser("preview", help="chỉ xuất bản vẽ xem trước")
    spv.add_argument("job")
    spv.add_argument("--svg", help="tệp SVG xuất ra")
    spv.add_argument("--diameter", type=float)
    spv.add_argument("--feed", type=float)
    spv.add_argument("--kerf", type=float)
    spv.set_defaults(func=cmd_preview)

    ss = sub.add_parser("send", help="nạp tệp G-code xuống máy")
    ss.add_argument("file")
    ss.add_argument("--port", required=True, help="ví dụ COM5, /dev/ttyUSB0 hoặc GIA-LAP")
    ss.add_argument("--baud", type=int)
    ss.add_argument("-q", "--quiet", action="store_true")
    ss.set_defaults(func=cmd_send)

    sm = sub.add_parser("sim", help="chạy thử tệp G-code trên máy ảo")
    sm.add_argument("file")
    sm.add_argument("--speed", type=float, default=None,
                    help="hệ số tăng tốc máy ảo (1 = thời gian thực)")
    sm.add_argument("-q", "--quiet", action="store_true")
    sm.set_defaults(func=cmd_sim)

    sr = sub.add_parser("run", help="sinh G-code rồi nạp thẳng xuống máy")
    sr.add_argument("job")
    sr.add_argument("--port", required=True)
    sr.add_argument("--baud", type=int)
    sr.add_argument("-y", "--yes", action="store_true", help="không hỏi xác nhận")
    sr.add_argument("-q", "--quiet", action="store_true")
    sr.set_defaults(func=cmd_run)

    su = sub.add_parser("ui", help="mở giao diện đồ hoạ")
    su.add_argument("--job", help="mở sẵn một tệp công việc")
    su.set_defaults(func=cmd_ui)

    sd = sub.add_parser("demo", help="tạo tệp cấu hình và công việc mẫu")
    sd.add_argument("--dir", default="examples")
    sd.set_defaults(func=cmd_demo)
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
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
