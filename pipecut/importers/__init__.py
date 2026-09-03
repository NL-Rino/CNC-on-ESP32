"""Nhập biên dạng từ tệp ngoài.

Một cửa duy nhất cho mọi định dạng - dùng ``load_curves`` rồi kết quả đi thẳng
vào dây chuyền xử lý sẵn có (bù kerf, vào/ra dao, xoay góc ống hộp, bù tốc độ
bốn trục), y như biên dạng do phần mềm tự sinh.

========  ==========================================================
Đuôi tệp  Nội dung
========  ==========================================================
.dxf      Bản vẽ CAD 2D (AutoCAD, LibreCAD, DraftSight...)
.svg      Hình vector (Inkscape, Illustrator, Figma...)
.nc .gcode .tap
          G-code **phẳng hai trục** xuất từ CAM bất kỳ
.stl .obj Mô hình 3D của chi tiết đã cắt - tự dò ra đường cắt
.csv .json
          Danh sách điểm (u, v) tự chuẩn bị
========  ==========================================================

STEP và IGES **không đọc được**: đó là định dạng B-rep, muốn đọc phải kèm cả
một nhân hình học rất nặng.  Mọi phần mềm CAD đều xuất được STL - hãy xuất STL
với sai số lưới nhỏ rồi nạp vào đây.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

from .common import (
    Curve2D,
    ImportError_,
    Point,
    dedupe,
    join_curves,
    summary,
    transform,
)

FORMATS: Dict[str, str] = {
    ".dxf": "dxf",
    ".svg": "svg",
    ".nc": "gcode", ".gcode": "gcode", ".tap": "gcode", ".ngc": "gcode",
    ".stl": "mesh", ".obj": "mesh",
    ".csv": "points", ".txt": "points", ".json": "points",
}

FORMAT_LABEL = {
    "dxf": "bản vẽ CAD 2D (DXF)",
    "svg": "hình vector (SVG)",
    "gcode": "G-code phẳng hai trục",
    "mesh": "mô hình 3D (STL/OBJ)",
    "points": "danh sách điểm (CSV/JSON)",
}

FILE_TYPES = [
    ("Mọi định dạng đọc được", "*.dxf *.svg *.nc *.gcode *.tap *.ngc *.stl *.obj *.csv *.json"),
    ("Bản vẽ CAD 2D", "*.dxf"),
    ("Hình vector", "*.svg"),
    ("G-code phẳng", "*.nc *.gcode *.tap *.ngc"),
    ("Mô hình 3D", "*.stl *.obj"),
    ("Danh sách điểm", "*.csv *.txt *.json"),
]


def detect_format(path: str) -> str:
    """Nhận diện định dạng theo đuôi tệp."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".step", ".stp", ".iges", ".igs"):
        raise ImportError_(
            f"Chưa đọc được {ext.upper().lstrip('.')}: đó là định dạng B-rep, cần cả "
            "một nhân hình học nặng mới dựng lại được. Hãy xuất chi tiết sang STL "
            "(sai số lưới 0,01-0,05 mm) rồi nạp lại."
        )
    fmt = FORMATS.get(ext)
    if not fmt:
        raise ImportError_(
            f"Không nhận ra đuôi tệp '{ext}'. Đọc được: "
            + ", ".join(sorted(set(FORMATS)))
        )
    return fmt


def load_points_file(path: str) -> List[Curve2D]:
    """Danh sách điểm (u, v): CSV/TXT hai cột hoặc JSON."""
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        raw = data.get("points", data) if isinstance(data, dict) else data
        pts = [(float(p[0]), float(p[1])) for p in raw]
        return [Curve2D(dedupe(pts), False, "points")]
    pts: List[Point] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s or s[0] in "#;":
                continue
            parts = s.replace(";", ",").replace("\t", ",").split(",")
            if len(parts) < 2:
                continue
            try:
                pts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    if len(pts) < 2:
        raise ImportError_(
            f"Tệp '{os.path.basename(path)}' không có đủ điểm hợp lệ "
            "(cần hai cột: u, v tính bằng mm)."
        )
    return [Curve2D(dedupe(pts), False, "points")]


def load_curves(
    path: str,
    section=None,
    tolerance: float = 0.05,
    join_tolerance: float = 0.05,
    layers: Optional[Sequence[str]] = None,
    svg_scale: Optional[float] = None,
    flip_y: bool = True,
    mesh_axis: str = "auto",
    mesh_roll: float = 0.0,
    mesh_tolerance: float = 0.4,
    notes: Optional[List[str]] = None,
) -> List[Curve2D]:
    """Đọc một tệp bất kỳ thành danh sách đường cong phẳng.

    Với mô hình 3D, kết quả đã là toạ độ trải phẳng ``(dọc phôi, chu vi)``; với
    các định dạng 2D thì là toạ độ trên tấm phẳng, sẽ được cuốn lên phôi ở bước
    sau.  ``section`` chỉ bắt buộc khi đọc mô hình 3D.

    Truyền một danh sách vào ``notes`` để nhận thêm cảnh báo (hiện chỉ mô hình
    3D dùng đến: báo khi tiết diện khai báo không khớp với mô hình).
    """
    if not path or not os.path.exists(path):
        raise ImportError_(f"Không tìm thấy tệp: {path}")
    fmt = detect_format(path)
    if fmt == "dxf":
        from . import dxf
        return dxf.load(path, tolerance=tolerance, layers=layers,
                        join_tolerance=join_tolerance)
    if fmt == "svg":
        from . import svg
        return svg.load(path, tolerance=tolerance, scale=svg_scale,
                        flip_y=flip_y, join_tolerance=join_tolerance)
    if fmt == "gcode":
        from . import gcode2d
        return gcode2d.load(path, tolerance=tolerance)
    if fmt == "mesh":
        if section is None:
            raise ImportError_("Đọc mô hình 3D cần biết tiết diện phôi.")
        from . import mesh
        return mesh.load(path, section, axis=mesh_axis, roll_deg=mesh_roll,
                         surface_tolerance=mesh_tolerance, notes=notes)
    return load_points_file(path)


def describe_file(path: str, section=None, **kw) -> str:
    """Mô tả ngắn nội dung một tệp, dùng để hiện lên giao diện trước khi nạp."""
    try:
        fmt = detect_format(path)
        curves = load_curves(path, section=section, **kw)
    except ImportError_ as exc:
        return f"Lỗi: {exc}"
    return f"{FORMAT_LABEL.get(fmt, fmt)} · {summary(curves)}"
