# -*- mode: python ; coding: utf-8 -*-
"""Đóng gói PipeCut Studio thành thư mục chạy được, không cần cài Python.

    pyinstaller packaging/pipecut.spec --noconfirm --clean

Ra ``dist/PipeCutStudio/`` gồm:

* ``PipeCutStudio.exe`` - giao diện, không bật cửa sổ dòng lệnh đen;
* ``pipecut.exe``       - dòng lệnh (``pipecut.exe gen ...``, ``pipecut.exe ports``);
* ``config/ examples/ firmware/ docs/`` - để **cạnh** tệp exe (không giấu trong
  ``_internal``) để người dùng mở ra xem, và để phần mềm tìm thấy qua
  ``pipecut.paths.resource_dir()``.
"""

import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from pipecut import __version__  # noqa: E402

from PyInstaller.utils.hooks import collect_submodules  # noqa: E402

# Nhiều module được nạp muộn bên trong hàm (tránh phụ thuộc vòng) - gom hết
# cho chắc, cộng pyserial để nói chuyện với cổng COM.
HIDDEN = collect_submodules("pipecut") + [
    "serial", "serial.tools", "serial.tools.list_ports",
    "serial.tools.list_ports_windows", "serial.tools.list_ports_common",
]
EXCLUDES = ["pytest", "unittest.mock", "numpy", "PIL", "yaml", "PyInstaller"]

ICON = os.path.join(SPECPATH, "pipecut.ico")
ICON = ICON if os.path.exists(ICON) else None

VERSION = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
        VarStruct, VSVersionInfo)
    nums = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:4])
    VERSION = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "NL-Rino"),
                StringStruct("FileDescription", "PipeCut Studio - máy cắt ống 4 trục ESP32 + FluidNC"),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductName", "PipeCut Studio"),
                StringStruct("ProductVersion", __version__),
                StringStruct("LegalCopyright", "NL-Rino"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )


def analysis(script):
    return Analysis(
        [os.path.join(SPECPATH, script)],
        pathex=[ROOT],
        hiddenimports=HIDDEN,
        excludes=EXCLUDES,
        noarchive=False,
    )


a_gui = analysis("pipecut_gui.py")
a_cli = analysis("pipecut_cli.py")

exe_gui = EXE(
    PYZ(a_gui.pure), a_gui.scripts, [],
    exclude_binaries=True, name="PipeCutStudio", console=False,
    icon=ICON, version=VERSION, upx=False,
)
exe_cli = EXE(
    PYZ(a_cli.pure), a_cli.scripts, [],
    exclude_binaries=True, name="pipecut", console=True,
    icon=ICON, version=VERSION, upx=False,
)
COLLECT(
    exe_gui, a_gui.binaries, a_gui.datas,
    exe_cli, a_cli.binaries, a_cli.datas,
    name="PipeCutStudio", upx=False,
)

# ---- tài nguyên đặt cạnh tệp exe ----
OUT = os.path.join(DISTPATH, "PipeCutStudio")
for folder in ("config", "examples", "firmware", "docs"):
    dst = os.path.join(OUT, folder)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, folder), dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in ("README.md", "CHANGELOG.md"):
    shutil.copy2(os.path.join(ROOT, name), os.path.join(OUT, name))
if ICON:
    shutil.copy2(ICON, os.path.join(OUT, "pipecut.ico"))
