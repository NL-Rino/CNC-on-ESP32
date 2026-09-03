"""Mô tả công việc gia công và bộ danh mục nguyên công.

Một *job* là danh sách các *nguyên công* (operation).  Mỗi nguyên công chỉ là
một cái tên kiểu + một từ điển tham số, nên lưu/nạp JSON rất gọn và giao diện
có thể **tự sinh biểu mẫu nhập liệu** từ ``OP_CATALOG`` mà không phải viết tay
từng ô nhập cho từng loại.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import shapes
from .config import MachineProfile, PipeSpec
from .toolpath import Contour, Toolpath


# --------------------------------------------------------------------------
# Danh mục nguyên công: nguồn dữ liệu duy nhất cho CLI, GUI và tài liệu
# --------------------------------------------------------------------------
def P(name: str, label: str, default: Any, unit: str = "", kind: str = "float",
      choices: Optional[Sequence[str]] = None, hint: str = "") -> Dict[str, Any]:
    return {"name": name, "label": label, "default": default, "unit": unit,
            "kind": kind, "choices": list(choices) if choices else None, "hint": hint}


ALL_SHAPES = ("round", "square", "rect")
ROUND_ONLY = ("round",)


OP_CATALOG: Dict[str, Dict[str, Any]] = {
    "cutoff": {
        "label": "Cắt đứt / cắt vát",
        "desc": "Cắt ống bằng mặt phẳng, vuông góc hoặc nghiêng một góc.",
        "params": [
            P("x", "Vị trí cắt", 200.0, "mm", hint="Đo từ gốc toạ độ trên trục X"),
            P("angle", "Góc vát", 0.0, "độ", hint="0 = cắt vuông; 30-45 = cắt xiên nối co"),
            P("roll", "Hướng vát", 0.0, "độ", hint="Xoay mặt phẳng vát quanh ống"),
            P("bevel_axis", "Dùng trục vát", True, "", "bool",
              hint="Nghiêng đầu cắt theo mặt phẳng cắt (cần trục thứ 4 là bevel)"),
        ],
    },
    "saddle": {
        "label": "Miệng cá (ôm ống chính)",
        "shapes": ROUND_ONLY,
        "desc": "Cắt đầu ống nhánh để ôm khít vào ống chính - mối nối chữ T/Y.",
        "params": [
            P("main_diameter", "Đường kính ống chính", 100.0, "mm"),
            P("angle", "Góc giữa hai ống", 90.0, "độ", hint="90 = chữ T, 45 = chữ Y"),
            P("offset", "Lệch tâm", 0.0, "mm", hint="Khoảng lệch giữa hai đường tâm"),
            P("x", "Vị trí gót", 250.0, "mm"),
            P("reference", "Chuẩn đo", "heel", "", "choice",
              choices=["heel", "toe", "axis"],
              hint="heel = điểm dài nhất, toe = đáy miệng cá, axis = giao hai tâm"),
            P("roll", "Xoay biên dạng", 0.0, "độ"),
            P("bevel_axis", "Dùng trục vát", True, "", "bool"),
        ],
    },
    "hole": {
        "label": "Lỗ xuyên thành ống",
        "shapes": ROUND_ONLY,
        "desc": "Lỗ do ống nhánh hoặc mũi khoan xuyên qua thành ống.",
        "params": [
            P("diameter", "Đường kính lỗ", 30.0, "mm"),
            P("x", "Vị trí tâm lỗ", 120.0, "mm"),
            P("theta", "Góc quay tâm lỗ", 0.0, "độ"),
            P("angle", "Góc xuyên", 90.0, "độ", hint="90 = hướng tâm, khác = lỗ xiên"),
            P("offset", "Lệch tâm", 0.0, "mm"),
        ],
    },
    "slot": {
        "label": "Rãnh / cửa sổ chữ nhật",
        "desc": "Cửa sổ chữ nhật bo góc, kích thước đo trên bề mặt ống.",
        "params": [
            P("x", "Tâm theo trục ống", 150.0, "mm"),
            P("theta", "Tâm theo góc quay", 0.0, "độ"),
            P("length", "Chiều dài dọc ống", 60.0, "mm"),
            P("width_deg", "Bề rộng theo góc", 90.0, "độ"),
            P("corner", "Bán kính bo góc", 5.0, "mm"),
        ],
    },
    "circle": {
        "label": "Lỗ tròn trên mặt",
        "desc": ("Đường tròn đo theo bề mặt phôi. Với ống hộp, nếu nằm gọn trong "
                 "một mặt phẳng thì đây chính là lỗ tròn thật, cắt vuông góc mặt."),
        "params": [
            P("diameter", "Đường kính", 40.0, "mm"),
            P("x", "Tâm theo trục ống", 150.0, "mm"),
            P("theta", "Tâm theo góc quay", 0.0, "độ"),
        ],
    },
    "helix": {
        "label": "Đường xoắn ốc",
        "desc": "Cắt xoắn quanh ống - lò xo, rãnh xoắn, ống mềm.",
        "params": [
            P("x_start", "Điểm đầu", 50.0, "mm"),
            P("x_end", "Điểm cuối", 250.0, "mm"),
            P("turns", "Số vòng", 4.0, "vòng"),
            P("theta_start", "Góc bắt đầu", 0.0, "độ"),
        ],
    },
    "axial": {
        "label": "Đường dọc thân ống",
        "desc": "Cắt hoặc vạch một đường thẳng dọc ống.",
        "params": [
            P("x_start", "Điểm đầu", 50.0, "mm"),
            P("x_end", "Điểm cuối", 200.0, "mm"),
            P("theta", "Góc quay", 0.0, "độ"),
            P("mark", "Chỉ vạch dấu", False, "", "bool"),
        ],
    },
    "ring_mark": {
        "label": "Vạch dấu vòng",
        "desc": "Vạch một vòng tròn quanh ống (không cắt đứt).",
        "params": [P("x", "Vị trí", 100.0, "mm")],
    },
    "weld_prep": {
        "label": "Vát mép hàn",
        "desc": "Cắt vuông đầu ống với trục vát giữ góc cố định tạo mép V.",
        "params": [
            P("x", "Vị trí cắt", 200.0, "mm"),
            P("angle", "Góc vát mép", 37.5, "độ"),
        ],
    },
    "pattern": {
        "label": "Nhập biên dạng từ tệp",
        "desc": ("Nạp biên dạng từ DXF, SVG, G-code phẳng, mô hình 3D (STL/OBJ) "
                 "hay danh sách điểm, rồi cuốn lên mặt phôi. Một tệp có thể chứa "
                 "nhiều đường - tất cả đều được nạp thành nguyên công con."),
        "params": [
            P("file", "Tệp biên dạng", "", "", "file",
              hint="DXF · SVG · NC/G-code · STL/OBJ · CSV/JSON"),
            P("x_offset", "Dịch dọc ống", 0.0, "mm"),
            P("theta_offset", "Dịch theo góc", 0.0, "độ"),
            P("scale", "Tỉ lệ", 1.0, ""),
            P("rotate", "Xoay biên dạng", 0.0, "độ",
              hint="Xoay trên tấm trải phẳng trước khi cuốn lên phôi"),
            P("mirror", "Lật", "none", "", "choice", choices=["none", "u", "v"],
              hint="u = lật theo chiều dọc ống, v = lật theo chiều chu vi"),
            P("closed", "Khép kín", "auto", "", "choice",
              choices=["auto", "yes", "no"],
              hint="auto = theo đúng tệp gốc"),
            P("corner", "Bo góc", 0.0, "mm"),
            P("layers", "Lớp cần lấy", "", "", "text",
              hint="Chỉ với DXF; nhiều lớp cách nhau bằng dấu phẩy, để trống là lấy hết"),
            P("mesh_axis", "Trục phôi trong mô hình", "auto", "", "choice",
              choices=["auto", "x", "y", "z"], hint="Chỉ với STL/OBJ"),
            P("mesh_roll", "Xoay mô hình quanh trục", 0.0, "độ", hint="Chỉ với STL/OBJ"),
            P("mesh_tol", "Dung sai bề mặt", 0.4, "mm",
              hint="Chỉ với STL/OBJ: sai lệch cho phép để coi một mảnh lưới là còn nằm trên mặt phôi"),
        ],
    },
}


def ops_for_shape(shape: str) -> List[str]:
    """Danh sách nguyên công dùng được với một dạng tiết diện phôi.

    Máy chỉ cắt ống hộp thì không cần thấy miệng cá hay lỗ xuyên thành - hai
    biên dạng đó là bài toán giao hai mặt trụ, chỉ có nghĩa với ống tròn.
    """
    return [k for k, v in OP_CATALOG.items()
            if shape in v.get("shapes", ALL_SHAPES)]


def default_params(op_type: str) -> Dict[str, Any]:
    spec = OP_CATALOG.get(op_type)
    if not spec:
        raise KeyError(f"Không có nguyên công '{op_type}'.")
    return {p["name"]: p["default"] for p in spec["params"]}


# --------------------------------------------------------------------------
# Nguyên công
# --------------------------------------------------------------------------
@dataclass
class Operation:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    name: str = ""
    enabled: bool = True

    def label(self) -> str:
        return self.name or OP_CATALOG.get(self.type, {}).get("label", self.type)

    def get(self, key: str, fallback: Any = None) -> Any:
        if key in self.params:
            return self.params[key]
        try:
            return default_params(self.type).get(key, fallback)
        except KeyError:
            return fallback

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "name": self.name, "enabled": self.enabled,
                "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Operation":
        return cls(type=d["type"], params=dict(d.get("params", {})),
                   name=d.get("name", ""), enabled=bool(d.get("enabled", True)))


# --------------------------------------------------------------------------
# Dựng biên dạng từ nguyên công
# --------------------------------------------------------------------------
def _resolve(path: str, base_dir: str) -> str:
    if base_dir and path and not os.path.isabs(path):
        return os.path.join(base_dir, path)
    return path


def _as_closed(value: Any, fallback: bool) -> Optional[bool]:
    """Ô "khép kín" nhận cả kiểu cũ (True/False) lẫn kiểu mới ("auto"/yes/no)."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("auto", ""):
        return None
    if text in ("yes", "true", "1", "co", "có"):
        return True
    if text in ("no", "false", "0", "khong", "không"):
        return False
    return fallback


def build_imported(op: Operation, section, tolerance: float,
                   base_dir: str = "") -> List[Contour]:
    """Nạp một tệp ngoài thành danh sách biên dạng đã cuốn lên phôi.

    Mọi định dạng đều đi chung một đường: bộ nhập trả về đường cong phẳng, rồi
    ``flat_pattern`` cuốn lên mặt phôi.  Nhờ vậy biên dạng nhập vào được hưởng
    y hệt dây chuyền xử lý của biên dạng tự sinh: bù bề rộng mạch cắt, vào/ra
    dao, xoay góc ống hộp, bù tốc độ tổng hợp bốn trục.
    """
    from .importers import ImportError_, load_curves

    gp = op.get
    path = _resolve(str(gp("file")), base_dir)
    layers = [x.strip() for x in str(gp("layers", "")).split(",") if x.strip()]
    notes: List[str] = []
    try:
        curves = load_curves(
            path,
            section=section,
            tolerance=tolerance,
            layers=layers or None,
            mesh_axis=str(gp("mesh_axis", "auto")),
            mesh_roll=float(gp("mesh_roll", 0.0)),
            mesh_tolerance=float(gp("mesh_tol", 0.4)),
            notes=notes,
        )
    except ImportError_ as exc:
        raise shapes.ShapeError(str(exc)) from exc

    force_closed = _as_closed(gp("closed", "auto"), True)
    out: List[Contour] = []
    for i, curve in enumerate(curves, 1):
        if curve.rapid or len(curve.points) < 2:
            continue
        name = op.label() if len(curves) == 1 else f"{op.label()} #{i}"
        closed = curve.closed if force_closed is None else force_closed
        contour = shapes.flat_pattern(
            section, curve.points,
            closed=closed,
            x_offset=float(gp("x_offset", 0.0)),
            theta_offset_deg=float(gp("theta_offset", 0.0)),
            scale=float(gp("scale", 1.0)),
            tolerance=tolerance,
            corner_radius=float(gp("corner", 0.0)),
            name=name,
            wrap=curve.wrap,
            rotate_deg=float(gp("rotate", 0.0)),
            mirror=str(gp("mirror", "none")),
        )
        contour.meta["source"] = os.path.basename(path)
        if curve.layer:
            contour.meta["layer"] = curve.layer
        out.append(contour)
    if not out:
        raise shapes.ShapeError(
            f"Tệp '{os.path.basename(path)}' không có đường cắt nào dùng được."
        )
    if notes:
        out[0].meta["notes"] = notes
    return out


def build_contours(op: Operation, section, tolerance: float,
                   base_dir: str = "") -> List[Contour]:
    """Dựng mọi biên dạng của một nguyên công (tệp nhập vào có thể nhiều đường)."""
    if op.type == "pattern":
        return build_imported(op, section, tolerance, base_dir)
    return [build_contour(op, section, tolerance, base_dir)]


def build_contour(op: Operation, section, tolerance: float,
                  base_dir: str = "") -> Contour:
    """Gọi hàm sinh biên dạng tương ứng với kiểu nguyên công."""
    t = op.type
    gp = op.get
    if t == "cutoff":
        return shapes.plane_cut(section, float(gp("x")), float(gp("angle")),
                                float(gp("roll")), tolerance=tolerance,
                                bevel=bool(gp("bevel_axis")), name=op.label())
    if t == "saddle":
        return shapes.saddle_cut(section, float(gp("main_diameter")) / 2.0,
                                 float(gp("angle")), float(gp("offset")),
                                 x_ref=float(gp("x")), reference=str(gp("reference")),
                                 roll_deg=float(gp("roll")), tolerance=tolerance,
                                 bevel=bool(gp("bevel_axis")), name=op.label())
    if t == "hole":
        return shapes.pierced_hole(section, float(gp("diameter")), float(gp("angle")),
                                   float(gp("offset")), float(gp("x")),
                                   float(gp("theta")), tolerance=tolerance,
                                   name=op.label())
    if t == "slot":
        return shapes.slot(section, float(gp("x")), float(gp("theta")),
                           float(gp("length")), angular_width_deg=float(gp("width_deg")),
                           corner_radius=float(gp("corner")), tolerance=tolerance,
                           name=op.label())
    if t == "circle":
        return shapes.surface_circle(section, float(gp("x")), float(gp("theta")),
                                     float(gp("diameter")), tolerance=tolerance,
                                     name=op.label())
    if t == "helix":
        return shapes.helix(section, float(gp("x_start")), float(gp("x_end")),
                            float(gp("turns")), float(gp("theta_start")),
                            tolerance=tolerance, name=op.label())
    if t == "axial":
        return shapes.axial_line(section, float(gp("x_start")), float(gp("x_end")),
                                 float(gp("theta")),
                                 kind="mark" if bool(gp("mark")) else "cut",
                                 name=op.label())
    if t == "ring_mark":
        return shapes.ring_mark(section, float(gp("x")), tolerance=tolerance, name=op.label())
    if t == "weld_prep":
        return shapes.weld_prep(section, float(gp("x")), float(gp("angle")),
                                tolerance=tolerance, name=op.label())
    if t == "pattern":
        # Tệp có thể chứa nhiều đường; hàm này chỉ trả về đường dài nhất.
        # Dùng build_contours nếu muốn lấy hết.
        return build_imported(op, section, tolerance, base_dir)[0]
    raise shapes.ShapeError(f"Nguyên công '{t}' chưa được hỗ trợ.")


# --------------------------------------------------------------------------
# Công việc
# --------------------------------------------------------------------------
@dataclass
class Job:
    name: str = "cong-viec"
    operations: List[Operation] = field(default_factory=list)
    pipe: Optional[PipeSpec] = None      # ghi đè phôi của hồ sơ máy
    # Mặc định GIỮ NGUYÊN thứ tự người dùng đã xếp.  Chỉ khi bật rõ ràng thì
    # phần mềm mới tự sắp lại (vạch dấu -> lỗ/rãnh -> cắt đứt từ ngoài vào).
    optimize_order: bool = False
    notes: str = ""
    source_path: str = ""

    def add(self, op_type: str, **params: Any) -> Operation:
        p = default_params(op_type)
        p.update(params)
        op = Operation(type=op_type, params=p)
        self.operations.append(op)
        return op

    # ------------------------------------------------------------------
    def build_toolpath(self, profile: MachineProfile) -> Tuple[Toolpath, List[str]]:
        """Dựng toàn bộ đường chạy dao.  Trả về (toolpath, danh sách cảnh báo)."""
        pipe = self.pipe or profile.pipe
        section = pipe.section()
        tol = profile.motion.chord_tolerance
        base_dir = os.path.dirname(self.source_path) if self.source_path else ""
        tp = Toolpath(section=section, name=self.name)
        warnings: List[str] = []
        for i, op in enumerate(self.operations, 1):
            if not op.enabled:
                continue
            try:
                contours = build_contours(op, section, tol, base_dir)
            except Exception as exc:
                warnings.append(f"Nguyên công {i} ({op.label()}): {exc}")
                continue
            for contour in contours:
                for note in contour.meta.pop("notes", []):
                    warnings.append(f"Nguyên công {i} ({op.label()}): {note}")
                tp.add(contour)
        if self.optimize_order and len(tp.contours) > 2:
            tp.contours = order_contours(tp.contours)
        else:
            warnings.extend(check_order(tp.contours))
        return tp, warnings

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "notes": self.notes,
            "optimize_order": self.optimize_order,
            "operations": [op.to_dict() for op in self.operations],
        }
        if self.pipe:
            d["pipe"] = {
                "outer_diameter": self.pipe.outer_diameter,
                "wall_thickness": self.pipe.wall_thickness,
                "length": self.pipe.length,
                "material": self.pipe.material,
            }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        pipe = PipeSpec.from_dict(d["pipe"]) if d.get("pipe") else None
        return cls(
            name=d.get("name", "cong-viec"),
            operations=[Operation.from_dict(o) for o in d.get("operations", [])],
            pipe=pipe,
            optimize_order=bool(d.get("optimize_order", False)),
            notes=d.get("notes", ""),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        self.source_path = path

    @classmethod
    def load(cls, path: str) -> "Job":
        with open(path, "r", encoding="utf-8") as fh:
            job = cls.from_dict(json.load(fh))
        job.source_path = path
        return job


def check_order(contours: Sequence[Contour]) -> List[str]:
    """Soát thứ tự cắt do người dùng tự xếp, chỉ **cảnh báo** chứ không đổi.

    Sau một nhát cắt đứt, phần phôi phía ngoài rơi ra nên mọi nguyên công nằm
    xa hơn nhát cắt đó sẽ không còn phôi để gia công.
    """
    msgs: List[str] = []
    cut_off_at: Optional[float] = None
    for i, c in enumerate(contours, 1):
        if c.wrap and c.kind == "cut":
            x = min(p[0] for p in c.points)
            cut_off_at = x if cut_off_at is None else min(cut_off_at, x)
        elif cut_off_at is not None and min(p[0] for p in c.points) > cut_off_at:
            msgs.append(
                f"Nguyên công {i} ('{c.name}') nằm ngoài nhát cắt đứt phía trước "
                f"(x > {cut_off_at:.0f} mm) - lúc đó phần phôi này đã rơi ra rồi. "
                f"Hãy xếp nhát cắt đứt xuống sau, hoặc bật tự sắp xếp thứ tự."
            )
    return msgs


def order_contours(contours: Sequence[Contour]) -> List[Contour]:
    """Sắp xếp thứ tự cắt theo láng giềng gần nhất để bớt quãng chạy không.

    Quy tắc công nghệ: cắt các lỗ/rãnh *trước*, cắt đứt/miệng cá *sau cùng* -
    vì sau khi cắt đứt thì phần phôi phía ngoài rơi ra, không còn gá được nữa.
    """
    marks = [c for c in contours if c.kind == "mark"]
    inner = [c for c in contours if c.kind != "mark" and not c.wrap]
    outer = [c for c in contours if c.kind != "mark" and c.wrap]

    def sort_group(group: Sequence[Contour]) -> List[Contour]:
        if len(group) < 2:
            return list(group)
        remaining = list(group)
        out = [remaining.pop(0)]
        while remaining:
            last = out[-1].points[-1]
            best_i, best_d = 0, float("inf")
            for i, c in enumerate(remaining):
                p = c.points[0]
                d = (p[0] - last[0]) ** 2 + (p[1] - last[1]) ** 2
                if d < best_d:
                    best_i, best_d = i, d
            out.append(remaining.pop(best_i))
        return out

    # vạch dấu trước (chưa cắt gì), rồi lỗ/rãnh, cuối cùng mới cắt đứt
    marks = sort_group(marks)
    inner = sort_group(inner)
    # cắt đứt theo thứ tự từ đầu tự do vào trong để phôi luôn còn được đỡ
    outer.sort(key=lambda c: -max(p[0] for p in c.points))
    return marks + inner + outer
