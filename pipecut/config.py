"""Hồ sơ máy (machine profile): mô tả cơ khí, tiến trình cắt và tham số chuyển động.

Toàn bộ cấu hình được lưu bằng JSON (stdlib) nên không cần thư viện ngoài.
Mọi dataclass đều có ``from_dict``/``to_dict`` và bỏ qua khoá lạ để file cấu
hình cũ vẫn nạp được sau khi nâng cấp phần mềm.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, fields, asdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Vai trò của từng trục trên máy cắt ống
ROLE_ALONG = "along"    # chạy dọc theo trục ống (thường là X)
ROLE_CROSS = "cross"    # chạy ngang, vuông góc trục ống (thường là Y)
ROLE_RADIAL = "radial"  # nâng/hạ đầu cắt theo phương bán kính (thường là Z)
ROLE_ROTARY = "rotary"  # mâm cặp xoay ống (thường là A) - đơn vị ĐỘ
ROLE_BEVEL = "bevel"    # trục nghiêng đầu cắt để vát mép - đơn vị ĐỘ

ALL_ROLES = (ROLE_ALONG, ROLE_CROSS, ROLE_RADIAL, ROLE_ROTARY, ROLE_BEVEL)

if TYPE_CHECKING:  # tránh phụ thuộc vòng khi chạy thật
    from .section import Section
ANGULAR_ROLES = (ROLE_ROTARY, ROLE_BEVEL)


def _filter(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    """Chỉ giữ các khoá mà dataclass ``cls`` thực sự có."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in names}


@dataclass
class AxisSpec:
    """Một trục vật lý của máy."""

    letter: str = "X"           # chữ cái trong G-code: X Y Z A B C
    role: str = ROLE_ALONG      # vai trò cơ khí, xem ALL_ROLES
    enabled: bool = True
    max_rate: float = 3000.0    # tốc độ tối đa (mm/phút hoặc độ/phút)
    accel: float = 200.0        # gia tốc (mm/s^2 hoặc độ/s^2) - dùng để ước lượng thời gian
    max_travel: float = 1000.0  # hành trình (mm) hoặc 0 = vô hạn (trục xoay)
    min_travel: float = 0.0
    invert: bool = False        # đảo dấu khi xuất G-code
    offset: float = 0.0         # cộng thêm hằng số vào toạ độ xuất ra

    @property
    def is_angular(self) -> bool:
        return self.role in ANGULAR_ROLES

    def apply(self, value: float) -> float:
        return (-value if self.invert else value) + self.offset

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AxisSpec":
        return cls(**_filter(cls, d))


@dataclass
class PipeSpec:
    """Phôi đang gá trên mâm cặp: ống tròn hoặc ống hộp.

    * **Ống tròn** khai báo bằng ``outer_diameter``.
    * **Ống hộp** khai báo bằng ``width`` (cạnh ngang) và ``height`` (cạnh dọc);
      hộp vuông chỉ cần ``width``.  ``corner_radius`` để 0 thì phần mềm tự lấy
      2 lần chiều dày thành - sát với ống hộp thật.
    """

    shape: str = "round"          # round | square | rect
    outer_diameter: float = 60.0  # ống tròn
    width: float = 40.0           # ống hộp: cạnh theo phương ngang
    height: float = 40.0          # ống hộp: cạnh theo phương đứng
    corner_radius: float = 0.0    # bán kính góc lượn (0 = tự tính)
    wall_thickness: float = 3.0
    length: float = 1000.0
    material: str = "steel"

    def section(self) -> "Section":
        """Đối tượng tiết diện tương ứng (dùng cho mọi phép tính hình học)."""
        from .section import make_section
        return make_section(self.shape, self.outer_diameter, self.width,
                            self.height, self.corner_radius, self.wall_thickness)

    @property
    def is_round(self) -> bool:
        return self.shape == "round"

    @property
    def radius(self) -> float:
        """Bán kính bao ngoài - khoảng cách xa nhất từ tâm tới bề mặt."""
        if self.is_round:
            return self.outer_diameter / 2.0
        return self.section().max_radius

    @property
    def size_text(self) -> str:
        if self.is_round:
            return f"⌀{self.outer_diameter:g}"
        if self.shape == "square":
            return f"□{self.width:g}×{self.width:g}"
        return f"□{self.width:g}×{self.height:g}"

    @property
    def inner_radius(self) -> float:
        return max(0.1, self.radius - self.wall_thickness)

    def feed_radius(self, mode: str = "outer") -> float:
        """Bán kính dùng để quy đổi tốc độ vòng -> tốc độ cắt thực."""
        if not self.is_round:
            return self.radius
        r = self.outer_diameter / 2.0
        if mode == "inner":
            return max(0.1, r - self.wall_thickness)
        if mode == "mid":
            return max(0.1, r - self.wall_thickness / 2.0)
        return r

    def feed_scale(self, mode: str = "outer") -> float:
        """Hệ số quy đổi chiều dài cung ngoài sang cung dùng để tính tốc độ.

        Ống tròn cắt bằng nội suy quay nên có thể lấy tốc độ ở giữa thành ống;
        ống hộp cắt trên mặt phẳng nên luôn dùng đúng bề mặt ngoài (hệ số 1).
        """
        if not self.is_round:
            return 1.0
        r = self.outer_diameter / 2.0
        return self.feed_radius(mode) / r if r > 0 else 1.0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PipeSpec":
        return cls(**_filter(cls, d))


@dataclass
class ProcessSpec:
    """Tiến trình cắt: plasma / laser / oxy-gas / phay / bút vạch dấu."""

    kind: str = "plasma"           # plasma | laser | oxyfuel | router | marker
    kerf: float = 1.5              # bề rộng mạch cắt (mm)
    cut_feed: float = 1600.0       # tốc độ cắt thực trên bề mặt ống (mm/phút)
    plunge_feed: float = 600.0     # tốc độ hạ đầu cắt (mm/phút)
    rapid_feed: float = 3000.0     # tốc độ chạy không (mm/phút) khi không dùng G0
    cut_height: float = 1.6        # chiều cao mỏ cắt khi cắt (mm, so với Z0 chạm ống)
    pierce_height: float = 3.8     # chiều cao khi mồi/đục lỗ
    pierce_delay: float = 0.6      # thời gian chờ mồi (giây)
    safe_height: float = 20.0      # chiều cao an toàn để di chuyển nhanh
    on_command: str = "M3"         # lệnh bật nguồn cắt
    off_command: str = "M5"        # lệnh tắt nguồn cắt
    power: float = 1000.0          # giá trị S (laser/plasma THC/spindle)
    off_delay: float = 0.2         # dừng sau khi tắt (giây)
    use_g0: bool = True            # dùng G0 cho chạy không
    lead_in: float = 4.0           # chiều dài đoạn vào dao (mm)
    lead_out: float = 2.0          # chiều dài đoạn ra dao (mm)
    lead_type: str = "arc"         # none | line | arc
    lead_angle: float = 90.0       # góc vào dao so với hướng chạy (độ, chỉ dùng cho line)
    lead_start: float = 0.0        # dời điểm mồi quanh biên dạng, tính theo % chu vi
    lead_side: str = "auto"        # auto | inside | outside (biên dạng kín)
                                   # auto | plus | minus   (đường cắt quanh phôi)
    overcut: float = 1.0           # chạy vượt điểm khép kín (mm)
    kerf_side: str = "auto"        # auto | none | left | right
    use_radial: bool = True        # False = đầu cắt cố định (laser tiêu cự cứng)
    mark_power: float = 0.0        # công suất khi vạch dấu (0 = như khi cắt)
    mark_feed: float = 0.0         # tốc độ khi vạch dấu (0 = như khi cắt)

    @property
    def is_laser(self) -> bool:
        return self.kind == "laser"

    @property
    def uses_height_control(self) -> bool:
        """Plasma/oxy cần nâng hạ mỏ; laser/router thì vẫn dùng nhưng khác ý nghĩa."""
        return self.kind in ("plasma", "oxyfuel", "router")

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcessSpec":
        return cls(**_filter(cls, d))


@dataclass
class MotionSpec:
    """Tham số làm mượt và bảo vệ bộ đệm chuyển động của ESP32.

    ESP32 chạy FluidNC có bộ đệm planner hữu hạn (mặc định 16-32 block) và
    tốc độ nạp lệnh qua UART cũng hữu hạn.  Nếu bắn quá nhiều đoạn G1 siêu
    ngắn, máy sẽ bị "đói" dữ liệu -> giật cục.  Các tham số dưới đây điều
    tiết mật độ điểm để đường cắt vừa chính xác vừa mượt.
    """

    chord_tolerance: float = 0.05     # sai số dây cung khi rời rạc hoá đường cong (mm)
    simplify_tolerance: float = 0.02  # dung sai gộp điểm thẳng hàng (mm)
    min_segment: float = 0.25         # đoạn ngắn hơn giá trị này sẽ bị gộp (mm)
    max_segment: float = 8.0          # đoạn dài hơn sẽ bị chia nhỏ (mm)
    max_points_per_contour: int = 6000
    max_feed: float = 4000.0          # trần tốc độ tổng hợp (mm/phút)
    min_feed: float = 30.0
    feed_radius_mode: str = "outer"   # outer | mid | inner
    feed_change_threshold: float = 0.04  # chỉ ghi lại F khi lệch > 4%
    max_bevel: float = 45.0           # giới hạn góc trục vát (độ)
    bevel_pivot: float = 0.0          # khoảng cách tâm xoay -> mũi cắt (mm), để bù toạ độ
    bevel_invert: bool = False
    bevel_max_rate: float = 1800.0    # độ/phút, dùng để kẹp F khi trục vát chạy nhanh
    rotary_shortest_path: bool = True # khi chạy không: xoay theo đường ngắn nhất
    rotary_unwrap: bool = True        # khi cắt: quay liên tục, không nhảy +-180
    rotary_rewind: bool = False       # sau mỗi biên dạng, đặt lại góc A về 0..360
    decimals: int = 3
    corner_radius: float = 0.0        # bo góc mặc định cho đường có góc nhọn (mm)
    uniform_feed: bool = False        # cắt cả đường ở một tốc độ bề mặt duy nhất
    slow_warn_ratio: float = 0.7      # cảnh báo khi tốc độ tụt dưới tỉ lệ này
    # --- cách vượt qua góc lượn của ống hộp ---
    corner_mode: str = "follow"       # follow = cắt liền mạch qua góc
                                      # index  = dừng cắt, xoay 90 độ tại chỗ rồi cắt tiếp
    corner_torch_off: bool = True     # tắt nguồn cắt trong lúc xoay góc (chế độ index)
    corner_lift: float = 6.0          # nhấc thêm bao nhiêu mm khi xoay góc (nếu tắt mỏ)
    corner_rotate_rate: float = 0.0   # tốc độ xoay khi index (độ/phút, 0 = tối đa của trục)
    corner_dwell: float = 0.0         # dừng thêm sau khi xoay xong (giây)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MotionSpec":
        return cls(**_filter(cls, d))


@dataclass
class ConnectionSpec:
    """Thông số cổng COM và giao thức."""

    port: str = ""
    baudrate: int = 115200
    rx_buffer: int = 127          # FluidNC/Grbl: 127 an toàn, FluidNC thật là 255
    poll_interval: float = 0.2    # chu kỳ gửi '?' để lấy trạng thái (giây)
    connect_delay: float = 1.5    # chờ ESP32 khởi động sau khi mở cổng
    strip_comments: bool = True   # bỏ chú thích khi gửi để tiết kiệm bộ đệm
    timeout: float = 0.1
    simulator_speed: float = 1.0  # hệ số tăng tốc máy ảo (1 = thời gian thực)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConnectionSpec":
        return cls(**_filter(cls, d))


def _default_axes() -> List[AxisSpec]:
    """Bố trí trục mặc định, khớp với máy "ống tự tịnh tiến".

    * **Y** - ống ra vào (bàn mang mâm cặp chạy dọc theo trục ống)
    * **A** - mâm cặp xoay ống
    * **X** - mỏ cắt chạy ngang, vuông góc với trục Y
    * **Z** - mỏ cắt lên xuống
    """
    return [
        # Trục ngang lấy gốc trên đường tâm phôi nên hành trình đối xứng:
        # cắt ống hộp cần chạy sang cả hai bên mặt.
        AxisSpec(letter="X", role=ROLE_CROSS, max_rate=3000.0, accel=200.0,
                 min_travel=-100.0, max_travel=100.0),
        AxisSpec(letter="Y", role=ROLE_ALONG, max_rate=4000.0, accel=250.0, max_travel=1200.0),
        AxisSpec(letter="Z", role=ROLE_RADIAL, max_rate=2000.0, accel=200.0, max_travel=150.0),
        AxisSpec(letter="A", role=ROLE_ROTARY, max_rate=3600.0, accel=400.0, max_travel=0.0),
    ]


@dataclass
class MachineProfile:
    """Toàn bộ cấu hình một máy cắt ống."""

    name: str = "May cat ong ESP32 - 4 truc"
    description: str = ("FluidNC 4 truc: Y ong ra vao, A mam cap xoay, "
                        "X mo cat chay ngang, Z mo cat len xuong")
    axes: List[AxisSpec] = field(default_factory=_default_axes)
    pipe: PipeSpec = field(default_factory=PipeSpec)
    process: ProcessSpec = field(default_factory=ProcessSpec)
    motion: MotionSpec = field(default_factory=MotionSpec)
    connection: ConnectionSpec = field(default_factory=ConnectionSpec)
    layout: str = "pipe_moves"   # pipe_moves = ống tịnh tiến | torch_moves = xe mỏ cắt chạy
    work_offset: str = "G54"
    preamble: List[str] = field(default_factory=lambda: ["G21", "G90", "G94", "G54"])
    postamble: List[str] = field(default_factory=lambda: ["M5", "M30"])

    # ---------------- truy vấn trục ----------------
    def axis(self, role: str) -> Optional[AxisSpec]:
        for a in self.axes:
            if a.role == role and a.enabled:
                return a
        return None

    def letter(self, role: str) -> Optional[str]:
        a = self.axis(role)
        return a.letter if a else None

    def has_role(self, role: str) -> bool:
        return self.axis(role) is not None

    def axis_by_letter(self, letter: str) -> Optional[AxisSpec]:
        for a in self.axes:
            if a.letter.upper() == letter.upper():
                return a
        return None

    @property
    def letters(self) -> List[str]:
        """Thứ tự trục như FluidNC báo cáo trong MPos (X, Y, Z, A, B, C)."""
        order = "XYZABC"
        return sorted([a.letter.upper() for a in self.axes if a.enabled], key=lambda c: order.index(c))

    def validate(self) -> List[str]:
        """Trả về danh sách cảnh báo cấu hình (rỗng = hợp lệ)."""
        msgs: List[str] = []
        if not self.has_role(ROLE_ALONG):
            msgs.append("Thiếu trục dọc ống (role='along').")
        if not self.has_role(ROLE_ROTARY):
            msgs.append("Thiếu trục xoay mâm cặp (role='rotary').")
        if not self.has_role(ROLE_RADIAL):
            msgs.append("Thiếu trục nâng hạ đầu cắt (role='radial').")
        seen = set()
        for a in self.axes:
            if not a.enabled:
                continue
            key = a.letter.upper()
            if key in seen:
                msgs.append(f"Trục '{key}' bị khai báo trùng.")
            seen.add(key)
            if key not in "XYZABC":
                msgs.append(f"Chữ cái trục '{key}' không hợp lệ với FluidNC.")
            if a.role not in ALL_ROLES:
                msgs.append(f"Vai trò '{a.role}' của trục {key} không hợp lệ.")
        try:
            self.pipe.section()
        except Exception as exc:
            msgs.append(f"Tiết diện phôi không hợp lệ: {exc}")
        if self.pipe.is_round and self.pipe.outer_diameter <= 0:
            msgs.append("Đường kính ống phải > 0.")
        if not self.pipe.is_round and min(self.pipe.width, self.pipe.height) <= 0:
            msgs.append("Cạnh ống hộp phải > 0.")
        if self.pipe.wall_thickness >= self.pipe.radius:
            msgs.append("Chiều dày thành lớn hơn bán kính bao ngoài - kiểm tra lại.")
        if self.process.cut_height >= self.process.safe_height:
            msgs.append("Chiều cao an toàn phải lớn hơn chiều cao cắt.")
        if self.motion.chord_tolerance <= 0:
            msgs.append("chord_tolerance phải > 0.")
        return msgs

    # ---------------- nạp / lưu ----------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MachineProfile":
        d = dict(d or {})
        axes = [AxisSpec.from_dict(a) for a in d.get("axes", [])] or _default_axes()
        return cls(
            name=d.get("name", "May cat ong ESP32 - 4 truc"),
            description=d.get("description", ""),
            axes=axes,
            pipe=PipeSpec.from_dict(d.get("pipe", {})),
            process=ProcessSpec.from_dict(d.get("process", {})),
            motion=MotionSpec.from_dict(d.get("motion", {})),
            connection=ConnectionSpec.from_dict(d.get("connection", {})),
            layout=d.get("layout", "pipe_moves"),
            work_offset=d.get("work_offset", "G54"),
            preamble=list(d.get("preamble", ["G21", "G90", "G94", "G54"])),
            postamble=list(d.get("postamble", ["M5", "M30"])),
        )

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str) -> "MachineProfile":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @classmethod
    def load_or_default(cls, path: Optional[str]) -> "MachineProfile":
        if path and os.path.exists(path):
            return cls.load(path)
        return cls()


DEFAULT_PROFILE_PATHS = (
    os.path.join(os.getcwd(), "config", "machine_default.json"),
    os.path.join(os.path.expanduser("~"), ".pipecut", "machine.json"),
)


def find_profile() -> MachineProfile:
    """Tìm hồ sơ máy ở các vị trí quen thuộc, không có thì trả về mặc định."""
    for p in DEFAULT_PROFILE_PATHS:
        if os.path.exists(p):
            try:
                return MachineProfile.load(p)
            except Exception:
                continue
    return MachineProfile()
