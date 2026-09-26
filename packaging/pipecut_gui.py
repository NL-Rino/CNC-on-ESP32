"""Điểm vào của PipeCutStudio.exe (giao diện, không có cửa sổ dòng lệnh).

    PipeCutStudio.exe                      mở giao diện
    PipeCutStudio.exe cong-viec.json       mở luôn tệp công việc đó
    PipeCutStudio.exe --selftest ra.txt    dựng cửa sổ, sinh thử G-code rồi thoát;
                                           ghi "OK ..." vào ra.txt (để kiểm bản
                                           đóng gói trên máy không có màn hình người)
"""

import os
import sys
import traceback


def _selftest(out_path: str) -> int:
    try:
        import tkinter as tk

        from pipecut import __version__
        from pipecut.jobs import Job
        from pipecut.paths import resource
        from pipecut.ui.app import MainWindow

        root = tk.Tk()
        win = MainWindow(root)
        win.job = Job.load(resource("examples", "vi_du_ong_hop.json"))
        win.generate()
        root.update()
        lines = len(win.program.lines) if win.program else 0
        root.destroy()
        if lines <= 0:
            raise RuntimeError("không sinh được G-code")
        msg = f"OK PipeCut Studio {__version__}: giao diện dựng được, sinh {lines} dòng G-code\n"
        code = 0
    except Exception:
        msg = "LỖI\n" + traceback.format_exc()
        code = 1
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(msg)
    return code


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--selftest"]:
        return _selftest(args[1] if len(args) > 1 else "selftest.txt")
    job = next((a for a in args if a.lower().endswith(".json") and os.path.isfile(a)), None)
    from pipecut.ui.app import main as gui_main
    return gui_main(job_path=job)


if __name__ == "__main__":
    raise SystemExit(main())
