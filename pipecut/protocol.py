"""Giao thức FluidNC / Grbl 1.1: phân tích phản hồi và lệnh thời gian thực.

FluidNC nói cùng "ngôn ngữ" với Grbl 1.1 nên toàn bộ phần này dùng được cho
cả hai.  Ba nhóm dữ liệu đi ngược từ máy lên:

* ``ok`` / ``error:N``          - trả lời cho từng dòng lệnh đã gửi;
* ``<...>``                     - báo cáo trạng thái, trả lời cho ký tự ``?``;
* ``[MSG:...]``, ``ALARM:N``, ``$x=y`` - thông báo và cấu hình.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Lệnh thời gian thực (gửi 1 byte, không nằm trong hàng đợi, không cần 'ok')
# --------------------------------------------------------------------------
RT_STATUS = b"?"
RT_CYCLE_START = b"~"
RT_FEED_HOLD = b"!"
RT_RESET = b"\x18"          # Ctrl-X: khởi động lại phần mềm
RT_SAFETY_DOOR = b"\x84"
RT_JOG_CANCEL = b"\x85"
RT_FEED_100 = b"\x90"
RT_FEED_PLUS10 = b"\x91"
RT_FEED_MINUS10 = b"\x92"
RT_FEED_PLUS1 = b"\x93"
RT_FEED_MINUS1 = b"\x94"
RT_RAPID_100 = b"\x95"
RT_RAPID_50 = b"\x96"
RT_RAPID_25 = b"\x97"
RT_SPINDLE_100 = b"\x99"
RT_SPINDLE_PLUS10 = b"\x9a"
RT_SPINDLE_MINUS10 = b"\x9b"
RT_TOGGLE_SPINDLE = b"\x9e"
RT_TOGGLE_FLOOD = b"\xa0"
RT_TOGGLE_MIST = b"\xa1"

REALTIME_BYTES = {
    RT_STATUS, RT_CYCLE_START, RT_FEED_HOLD, RT_RESET, RT_SAFETY_DOOR,
    RT_JOG_CANCEL, RT_FEED_100, RT_FEED_PLUS10, RT_FEED_MINUS10, RT_FEED_PLUS1,
    RT_FEED_MINUS1, RT_RAPID_100, RT_RAPID_50, RT_RAPID_25, RT_SPINDLE_100,
    RT_SPINDLE_PLUS10, RT_SPINDLE_MINUS10, RT_TOGGLE_SPINDLE, RT_TOGGLE_FLOOD,
    RT_TOGGLE_MIST,
}

# Trạng thái máy
STATE_IDLE = "Idle"
STATE_RUN = "Run"
STATE_HOLD = "Hold"
STATE_JOG = "Jog"
STATE_ALARM = "Alarm"
STATE_DOOR = "Door"
STATE_CHECK = "Check"
STATE_HOME = "Home"
STATE_SLEEP = "Sleep"

STATE_VI = {
    STATE_IDLE: "Sẵn sàng",
    STATE_RUN: "Đang chạy",
    STATE_HOLD: "Tạm dừng",
    STATE_JOG: "Đang jog",
    STATE_ALARM: "BÁO ĐỘNG",
    STATE_DOOR: "Cửa an toàn",
    STATE_CHECK: "Kiểm tra",
    STATE_HOME: "Đang về gốc",
    STATE_SLEEP: "Ngủ",
}

ERROR_VI = {
    1: "Từ lệnh G-code không hợp lệ hoặc thiếu chữ cái",
    2: "Giá trị số trong dòng lệnh bị sai định dạng",
    3: "Lệnh '$' không được hỗ trợ",
    4: "Giá trị âm không hợp lệ",
    5: "Công tắc hành trình đang tắt, không thể về gốc",
    6: "Bước thời gian quá nhỏ",
    7: "Đọc EEPROM lỗi, đã dùng giá trị mặc định",
    8: "Lệnh '$' chỉ dùng được khi máy rảnh",
    9: "Đang khoá bởi báo động hoặc đang về gốc, G-code bị chặn",
    10: "Chưa bật soft limit, không dùng được",
    11: "Dòng lệnh quá dài",
    12: "Tốc độ bước vượt quá khả năng của bo mạch",
    13: "Cửa an toàn đang mở",
    14: "Chuỗi build info hoặc thông điệp quá dài",
    15: "Quãng đường jog vượt hành trình",
    16: "Lệnh jog thiếu '=' hoặc chứa lệnh cấm",
    17: "Laser cần bật chế độ laser",
    20: "Có lệnh G không được hỗ trợ",
    21: "Nhiều lệnh cùng nhóm modal trong một dòng",
    22: "Thiếu hoặc sai giá trị F (tốc độ chạy)",
    23: "Giá trị lệnh G cần số nguyên",
    24: "Hai lệnh cùng dùng chữ cái trục trong một dòng",
    25: "Từ lệnh bị lặp lại",
    26: "Lệnh cần chữ cái trục nhưng không có",
    27: "Số dòng N vượt giá trị cho phép",
    28: "Lệnh thiếu giá trị P hoặc L",
    29: "Hệ toạ độ chi tiết không được hỗ trợ",
    30: "G53 chỉ dùng được với G0 hoặc G1",
    31: "Có chữ cái trục thừa trong lệnh này",
    32: "G2/G3 cần ít nhất một trục trong mặt phẳng đang chọn",
    33: "Lệnh có toạ độ đích không hợp lệ",
    34: "Bán kính cung tròn không hợp lệ",
    35: "G2/G3 theo offset thiếu I, J hoặc K",
    36: "Có giá trị thừa không được dùng",
    37: "G43.1 phải tác động lên trục bù chiều dài dao",
    38: "Số hiệu dao vượt giới hạn",
}

ALARM_VI = {
    1: "Chạm công tắc hành trình cứng - vị trí đã mất, cần về gốc lại",
    2: "Lệnh chạy vượt hành trình mềm - toạ độ đích nằm ngoài vùng làm việc",
    3: "Đã reset khi máy đang chạy - vị trí có thể sai",
    4: "Dò tìm thất bại - đầu dò đã ở trạng thái kích hoạt",
    5: "Dò tìm thất bại - không chạm được đầu dò trong hành trình",
    6: "Về gốc thất bại - bị reset giữa chừng",
    7: "Về gốc thất bại - cửa an toàn mở",
    8: "Về gốc thất bại - không rời khỏi công tắc, kiểm tra dây",
    9: "Về gốc thất bại - không tìm thấy công tắc trong hành trình",
    10: "Về gốc thất bại - lỗi trục kép (dual motor)",
}


@dataclass
class MachineStatus:
    """Ảnh chụp trạng thái máy tại một thời điểm."""

    state: str = "Unknown"
    substate: Optional[int] = None
    mpos: Dict[str, float] = field(default_factory=dict)   # toạ độ máy
    wpos: Dict[str, float] = field(default_factory=dict)   # toạ độ chi tiết
    wco: Dict[str, float] = field(default_factory=dict)    # offset gốc chi tiết
    feed: float = 0.0
    spindle: float = 0.0
    planner_free: Optional[int] = None   # số block trống trong bộ đệm chuyển động
    rx_free: Optional[int] = None        # số byte trống trong bộ đệm nhận
    line: Optional[int] = None
    pins: str = ""
    overrides: Tuple[int, int, int] = (100, 100, 100)
    accessories: str = ""
    raw: str = ""

    @property
    def state_vi(self) -> str:
        return STATE_VI.get(self.state, self.state)

    @property
    def is_moving(self) -> bool:
        return self.state in (STATE_RUN, STATE_JOG, STATE_HOME)

    @property
    def is_alarm(self) -> bool:
        return self.state in (STATE_ALARM, STATE_DOOR)


_STATUS_RE = re.compile(r"^<(?P<body>.*)>$")


def parse_status(line: str, axis_letters: Optional[List[str]] = None) -> Optional[MachineStatus]:
    """Phân tích một dòng báo cáo trạng thái ``<...>``.

    ``axis_letters`` cho biết thứ tự trục để gán tên cho các số trong MPos;
    mặc định dùng X, Y, Z, A, B, C.
    """
    m = _STATUS_RE.match(line.strip())
    if not m:
        return None
    letters = [c.upper() for c in (axis_letters or list("XYZABC"))]
    st = MachineStatus(raw=line.strip())
    fields = m.group("body").split("|")
    if not fields:
        return None
    head = fields[0]
    if ":" in head:
        name, _, sub = head.partition(":")
        st.state = name
        try:
            st.substate = int(sub)
        except ValueError:
            st.substate = None
    else:
        st.state = head

    def to_map(values: str) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for i, v in enumerate(values.split(",")):
            if i >= len(letters):
                break
            try:
                out[letters[i]] = float(v)
            except ValueError:
                continue
        return out

    for f in fields[1:]:
        key, _, val = f.partition(":")
        if key == "MPos":
            st.mpos = to_map(val)
        elif key == "WPos":
            st.wpos = to_map(val)
        elif key == "WCO":
            st.wco = to_map(val)
        elif key == "FS":
            parts = val.split(",")
            try:
                st.feed = float(parts[0])
                if len(parts) > 1:
                    st.spindle = float(parts[1])
            except ValueError:
                pass
        elif key == "F":
            try:
                st.feed = float(val)
            except ValueError:
                pass
        elif key == "Bf":
            parts = val.split(",")
            try:
                st.planner_free = int(parts[0])
                if len(parts) > 1:
                    st.rx_free = int(parts[1])
            except ValueError:
                pass
        elif key == "Ln":
            try:
                st.line = int(val)
            except ValueError:
                pass
        elif key == "Pn":
            st.pins = val
        elif key == "Ov":
            parts = val.split(",")
            try:
                st.overrides = (int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        elif key == "A":
            st.accessories = val

    # FluidNC chỉ gửi WCO thỉnh thoảng; tự suy ra vế còn lại
    if st.mpos and st.wco and not st.wpos:
        st.wpos = {k: st.mpos.get(k, 0.0) - st.wco.get(k, 0.0) for k in st.mpos}
    elif st.wpos and st.wco and not st.mpos:
        st.mpos = {k: st.wpos.get(k, 0.0) + st.wco.get(k, 0.0) for k in st.wpos}
    return st


@dataclass
class Response:
    """Phân loại một dòng phản hồi bất kỳ từ máy."""

    kind: str          # ok | error | alarm | status | message | setting | welcome | other
    text: str = ""
    code: Optional[int] = None
    status: Optional[MachineStatus] = None

    @property
    def is_ack(self) -> bool:
        """Dòng này có phải là câu trả lời cho một lệnh đã gửi không."""
        return self.kind in ("ok", "error")

    @property
    def message_vi(self) -> str:
        if self.kind == "error":
            return f"Lỗi {self.code}: {ERROR_VI.get(self.code or 0, 'không rõ')}"
        if self.kind == "alarm":
            return f"BÁO ĐỘNG {self.code}: {ALARM_VI.get(self.code or 0, 'không rõ')}"
        return self.text


def parse_options(line: str) -> Optional[Tuple[int, int]]:
    """Đọc dòng ``[OPT:...]`` để lấy (số block planner, cỡ bộ đệm nhận).

    FluidNC và Grbl 1.1 đều tự khai hai con số này ở cuối dòng OPT, ví dụ
    ``[OPT:VL,16,128]``.  Biết cỡ bộ đệm thật thì phần nạp lệnh đếm ký tự giữ
    được bộ đệm gần đầy đúng mức, thay vì phải đoán dè dặt.
    """
    s = line.strip()
    if not (s.startswith("[OPT:") and s.endswith("]")):
        return None
    parts = s[5:-1].split(",")
    nums = [p.strip() for p in parts if p.strip().isdigit()]
    if len(nums) < 2:
        return None
    blocks, buffer = int(nums[-2]), int(nums[-1])
    if not (1 <= blocks <= 1000) or not (16 <= buffer <= 65536):
        return None
    return blocks, buffer


def parse_response(line: str, axis_letters: Optional[List[str]] = None) -> Response:
    """Nhận diện một dòng bất kỳ do máy gửi lên."""
    s = line.strip()
    if not s:
        return Response(kind="other", text="")
    low = s.lower()
    if low == "ok":
        return Response(kind="ok", text=s)
    if low.startswith("error:"):
        try:
            code = int(s.split(":", 1)[1].strip())
        except ValueError:
            code = None
        return Response(kind="error", text=s, code=code)
    if low.startswith("alarm:"):
        try:
            code = int(s.split(":", 1)[1].strip())
        except ValueError:
            code = None
        return Response(kind="alarm", text=s, code=code)
    if s.startswith("<") and s.endswith(">"):
        return Response(kind="status", text=s, status=parse_status(s, axis_letters))
    if s.startswith("[") and s.endswith("]"):
        return Response(kind="message", text=s)
    if s.startswith("$"):
        return Response(kind="setting", text=s)
    if "grbl" in low or "fluidnc" in low:
        return Response(kind="welcome", text=s)
    return Response(kind="other", text=s)


def jog_command(axes: Dict[str, float], feed: float, relative: bool = True,
                machine_coords: bool = False) -> str:
    """Dựng lệnh jog ``$J=`` của Grbl 1.1 / FluidNC.

    Lệnh jog không làm thay đổi trạng thái modal và có thể huỷ ngay bằng
    byte 0x85 - đúng thứ cần cho các nút bấm giữ trên giao diện.
    """
    parts = ["$J=", "G91 " if relative else "G90 "]
    if machine_coords and not relative:
        parts.append("G53 ")
    parts.append("G21 ")
    for letter, value in axes.items():
        parts.append(f"{letter.upper()}{value:.3f} ")
    parts.append(f"F{max(1.0, feed):.0f}")
    return "".join(parts).replace("= ", "=")
