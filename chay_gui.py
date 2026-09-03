#!/usr/bin/env python3
"""Mở giao diện PipeCut Studio (nháy đúp tệp này trên Windows cũng chạy được)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    try:
        from pipecut.ui.app import main
    except ImportError as exc:
        print("Không mở được giao diện:", exc)
        print("Tkinter thường đi kèm Python trên Windows/macOS.")
        print("Trên Linux cài thêm:  sudo apt install python3-tk")
        input("Nhấn Enter để đóng...")
        raise SystemExit(1)
    raise SystemExit(main())
