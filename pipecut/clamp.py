"""Căn tâm mâm cặp bằng tay: chạm mỏ vào bốn mặt ống, máy tự suy ra gốc.

Mâm cặp tự định tâm nên **đường tâm ống trùng đường tâm mâm cặp bất kể ống to
nhỏ**.  Nghĩa là hai số ``axis_x`` và ``axis_z`` ở đây là *hằng số cơ khí của
máy*, không phải của phôi: căn **một lần duy nhất**, sau đó thay ống bao nhiêu
lần cũng vẫn đúng - chỉ cần khai lại cỡ ống là phần mềm tính ra gốc X và gốc Z
mới, không phải dò lại gì cả.

Vì sao chạm bốn chỗ chứ không phải hai:

* **Sườn trái + sườn phải** cho ``axis_x``.  Lấy điểm giữa nên **đường kính béc
  tự triệt tiêu** - béc dày mỏng bao nhiêu cũng ra cùng một tâm, khỏi đo béc.
  Với ống tròn còn hay hơn: chạm ở cao độ nào cũng được, miễn **hai bên cùng
  một cao độ**, vì chỗ chạm bị thụt vào bao nhiêu thì thụt đều cả hai bên.
* **Đỉnh ở góc A + đỉnh ở góc A+180°** cho ``axis_z``.  Lấy điểm giữa nên **độ
  lệch tâm của mâm cặp cũng tự triệt tiêu**: ống kẹp lệch lên e mm thì quay nửa
  vòng thành lệch xuống e mm, cộng lại chia đôi là hết.  Còn *hiệu* của hai số
  đó chính là độ lệch tâm - phần mềm báo ra để biết mâm cặp hay ống có vấn đề.

Góc xoay A thì **không** nằm trong phép căn này: A phụ thuộc lần gá này đặt ống
nghiêng bao nhiêu, không phải hằng số của máy.  Ống hộp muốn mặt phẳng nằm ngang
thì xoay tay hoặc chạy quy trình "Cân mặt" trong :mod:`pipecut.probing`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Bốn lần chạm, đúng thứ tự nên làm.  Làm đỉnh trước cùng để có ngay cao độ an
# toàn, rồi mới thò xuống hai bên sườn.
TOUCH_ORDER: Tuple[str, ...] = ("top", "left", "right", "top180")

TOUCH_LABELS: Dict[str, str] = {
    "top": "Chạm đỉnh ống",
    "left": "Chạm sườn trái",
    "right": "Chạm sườn phải",
    "top180": "Xoay A đúng 180°, chạm đỉnh lần nữa",
}

TOUCH_HINTS: Dict[str, str] = {
    "top": "Ống hộp thì xoay cho một mặt phẳng nằm ngang trước. Hạ mỏ xuống "
           "đúng giữa mặt trên, sát tới khi chạm.",
    "left": "Nâng mỏ lên rồi đưa sang trái ống, hạ xuống ngang thân, đẩy X vào "
            "tới khi chạm sườn.",
    "right": "Sang phải, hạ xuống **đúng cao độ như lúc chạm sườn trái**, đẩy "
             "X vào tới khi chạm.",
    "top180": "Nâng mỏ, xoay A thêm 180°, hạ xuống giữa mặt trên chạm lần nữa. "
              "Bước này để khử lệch tâm mâm cặp.",
}


@dataclass
class Touch:
    """Một lần chạm: toạ độ **máy** của tất cả các trục ngay lúc chạm."""

    pos: Dict[str, float] = field(default_factory=dict)

    def get(self, letter: str, fallback: float = 0.0) -> float:
        return float(self.pos.get(letter.upper(), fallback))

    @classmethod
    def from_dict(cls, d: Any) -> "Touch":
        if isinstance(d, dict) and "pos" in d:
            d = d.get("pos") or {}
        return cls(pos={str(k).upper(): float(v) for k, v in dict(d or {}).items()})


@dataclass
class ClampCalibration:
    """Tâm mâm cặp trong toạ độ máy - căn một lần, dùng mãi."""

    valid: bool = False
    axis_x: float = 0.0        # toạ độ máy X của đường tâm mâm cặp
    axis_z: float = 0.0        # toạ độ máy Z của đường tâm mâm cặp
    auto_limits: bool = True   # tự siết hành trình theo cỡ ống đang khai
    margin: float = 25.0       # chừa thêm bao nhiêu mm ngoài vùng ống chiếm
    span_x: float = 0.0        # bề rộng đo được giữa hai sườn
    runout: float = 0.0        # lệch tâm đo được (nửa hiệu hai lần chạm đỉnh)
    ref_height: float = 0.0    # nửa chiều cao tiết diện lúc căn, để soát lại
    pipe_size: str = ""        # cỡ ống lúc căn, ghi lại cho biết
    date: str = ""
    note: str = ""
    touches: Dict[str, Touch] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def summary(self) -> str:
        if not self.valid:
            return "Chưa căn tâm mâm cặp."
        return (f"Tâm mâm cặp: X{self.axis_x:.3f} Z{self.axis_z:.3f} "
                f"(căn với {self.pipe_size or 'ống chưa ghi'}, {self.date or 'không rõ ngày'})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid, "axis_x": self.axis_x, "axis_z": self.axis_z,
            "auto_limits": self.auto_limits, "margin": self.margin,
            "span_x": self.span_x, "runout": self.runout,
            "ref_height": self.ref_height, "pipe_size": self.pipe_size,
            "date": self.date, "note": self.note,
            "touches": {k: dict(v.pos) for k, v in self.touches.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ClampCalibration":
        d = dict(d or {})
        touches = {str(k): Touch.from_dict(v) for k, v in (d.get("touches") or {}).items()}
        return cls(
            valid=bool(d.get("valid", False)),
            axis_x=float(d.get("axis_x", 0.0)),
            axis_z=float(d.get("axis_z", 0.0)),
            auto_limits=bool(d.get("auto_limits", True)),
            margin=float(d.get("margin", 25.0)),
            span_x=float(d.get("span_x", 0.0)),
            runout=float(d.get("runout", 0.0)),
            ref_height=float(d.get("ref_height", 0.0)),
            pipe_size=str(d.get("pipe_size", "")),
            date=str(d.get("date", "")),
            note=str(d.get("note", "")),
            touches=touches,
        )


class ClampError(ValueError):
    """Bộ số đo không đủ hoặc vô lý - không suy ra được tâm."""


# ----------------------------------------------------------------------
# Giải bộ bốn lần chạm ra tâm mâm cặp
# ----------------------------------------------------------------------
def solve(touches: Dict[str, Touch], pipe, letters: Optional[Dict[str, str]] = None,
          margin: float = 25.0) -> Tuple[ClampCalibration, List[str]]:
    """Từ bốn lần chạm suy ra tâm mâm cặp, kèm danh sách cảnh báo.

    ``letters`` cho biết chữ cái nào là trục ngang / nâng hạ / xoay của máy này
    (mặc định X, Z, A).  Trả về ``(hồ sơ căn, cảnh báo)`` - cảnh báo rỗng nghĩa
    là bộ số đo sạch; có cảnh báo vẫn ra kết quả, nhưng nên đọc trước khi dùng.
    """
    lt = dict(letters or {})
    cross = lt.get("cross", "X").upper()
    radial = lt.get("radial", "Z").upper()
    rotary = lt.get("rotary", "A").upper()

    missing = [k for k in TOUCH_ORDER if k not in touches]
    if missing:
        raise ClampError("Còn thiếu lần chạm: "
                         + ", ".join(TOUCH_LABELS.get(k, k) for k in missing))

    t_top, t_left = touches["top"], touches["left"]
    t_right, t_180 = touches["right"], touches["top180"]
    warns: List[str] = []

    # --- tâm ngang: điểm giữa hai sườn, đường kính béc tự triệt tiêu ---
    x_left, x_right = t_left.get(cross), t_right.get(cross)
    if x_right < x_left:
        x_left, x_right = x_right, x_left
        warns.append("Sườn phải đo được nhỏ hơn sườn trái - đã tự đảo lại hai "
                     "số. Kiểm tra xem có chạm nhầm bên không.")
    axis_x = (x_left + x_right) / 2.0
    span_x = x_right - x_left

    # Hai sườn phải chạm ở cùng cao độ thì phép lấy điểm giữa mới đúng với ống
    # tròn: lệch cao độ là hai bên thụt vào khác nhau.
    dz_side = abs(t_left.get(radial) - t_right.get(radial))
    if dz_side > 1.0:
        warns.append(f"Hai sườn chạm lệch cao độ {dz_side:.2f} mm. Với ống tròn "
                     f"thì tâm ngang sẽ sai - nên chạm lại cho cùng một cao độ Z.")

    # --- tâm đứng: điểm giữa hai lần chạm đỉnh, lệch tâm tự triệt tiêu ---
    z_top, z_180 = t_top.get(radial), t_180.get(radial)
    section = pipe.section()
    ref = float(section.reference_height)
    axis_z = (z_top + z_180) / 2.0 - ref
    runout = (z_top - z_180) / 2.0

    da = abs(t_180.get(rotary) - t_top.get(rotary))
    if da > 1e-9 and abs(da - 180.0) > 5.0:
        warns.append(f"Hai lần chạm đỉnh cách nhau {da:.1f}° chứ không phải 180°. "
                     f"Phép khử lệch tâm chỉ đúng khi đúng nửa vòng.")
    if abs(runout) > 0.5:
        warns.append(f"Ống kẹp lệch tâm {abs(runout):.2f} mm (đã khử trong kết "
                     f"quả). Lệch nhiều quá thì xem lại mâm cặp hoặc ống có cong.")

    # Chạm đỉnh phải ở gần đường tâm, không thì đo được thấp hơn đỉnh thật.
    for name, t in (("lần đầu", t_top), ("sau khi xoay 180°", t_180)):
        off = abs(t.get(cross) - axis_x)
        if off > 2.0:
            warns.append(f"Lúc chạm đỉnh {name}, mỏ lệch khỏi đường tâm "
                         f"{off:.1f} mm - đo được sẽ thấp hơn đỉnh thật.")

    # --- soát bề rộng: đo được phải bằng cỡ ống cộng bề dày béc ---
    width = _section_width(section)
    extra = span_x - width
    if extra < -1.0:
        warns.append(f"Bề rộng đo được {span_x:.1f} mm nhỏ hơn cỡ ống đã khai "
                     f"{width:.1f} mm. Kiểm tra lại cỡ ống hoặc chỗ chạm.")
    elif extra > 40.0:
        warns.append(f"Hai sườn cách nhau {span_x:.1f} mm, hơn cỡ ống đã khai "
                     f"{width:.1f} mm tới {extra:.1f} mm. Có chạm nhầm vào mâm "
                     f"cặp hay đồ gá không?")

    cal = ClampCalibration(
        valid=True, axis_x=axis_x, axis_z=axis_z, margin=margin,
        span_x=span_x, runout=runout, ref_height=ref,
        pipe_size=pipe.size_text, date=time.strftime("%Y-%m-%d %H:%M"),
        touches={k: Touch(dict(v.pos)) for k, v in touches.items()},
    )
    return cal, warns


def _section_width(section) -> float:
    """Bề rộng bao ngang của tiết diện ở tư thế mốc (mặt phẳng nằm ngang)."""
    xs = [p[0] for p in section.outline(180)]
    return max(xs) - min(xs) if xs else 0.0


# ----------------------------------------------------------------------
# Dùng kết quả: đặt gốc, siết hành trình
# ----------------------------------------------------------------------
def work_origin(cal: ClampCalibration, pipe) -> Dict[str, float]:
    """Toạ độ **máy** của gốc chi tiết X và Z, suy thẳng từ tâm mâm cặp.

    Quy ước của phần mềm: gốc X nằm trên đường tâm ống, gốc Z nằm ngay **mặt
    trên** phôi.  Tâm mâm cặp cộng nửa chiều cao tiết diện là ra mặt trên - nên
    đổi cỡ ống chỉ việc khai lại kích thước, khỏi rà lại.
    """
    if not cal.valid:
        raise ClampError("Chưa căn tâm mâm cặp.")
    return {"X": cal.axis_x, "Z": cal.axis_z + float(pipe.section().reference_height)}


def _wcs_index(work_offset: str) -> int:
    """G54..G59 -> P1..P6."""
    try:
        n = int(str(work_offset).strip().upper().lstrip("G")) - 53
    except (TypeError, ValueError):
        return 1
    return n if 1 <= n <= 6 else 1


def zero_commands(profile) -> List[str]:
    """Lệnh đặt gốc X-Z từ tâm mâm cặp - mỏ đang đứng ở đâu cũng chạy được.

    Dùng ``G10 L2`` (đặt thẳng gốc theo toạ độ máy) chứ không phải ``G10 L20``
    (đặt gốc tại chỗ đang đứng), nên **không phải rà mỏ vào đâu cả**.  ``G92.1``
    ở đầu để xoá mọi dịch gốc tạm còn sót - còn nó thì gốc vừa đặt sẽ lệch.
    """
    org = work_origin(profile.clamp, profile.pipe)
    cross = (profile.letter("cross") or "X").upper()
    radial = (profile.letter("radial") or "Z").upper()
    dec = getattr(profile.motion, "decimals", 3)
    return [
        "G92.1",
        f"G10 L2 P{_wcs_index(profile.work_offset)} "
        f"{cross}{org['X']:.{dec}f} {radial}{org['Z']:.{dec}f}",
    ]


def envelope(profile) -> Dict[str, Tuple[float, float]]:
    """Vùng hành trình **theo toạ độ chi tiết** mà cỡ ống đang khai cần tới.

    Trả về theo *vai trò* trục, không theo chữ cái.  Rỗng nghĩa là chưa căn
    tâm hoặc người dùng đã tắt chức năng tự siết hành trình.
    """
    cal = profile.clamp
    if not cal.valid or not cal.auto_limits:
        return {}
    pipe = profile.pipe
    section = pipe.section()
    m = max(0.0, float(cal.margin))
    r = float(section.max_radius)
    ref = float(section.reference_height)
    # Gốc Z ở mặt trên phôi tại tư thế mốc; chỗ cao nhất bề mặt vươn tới là
    # bán kính lớn nhất (góc ống hộp) trừ đi nửa chiều cao đó.
    top = max(0.0, r - ref)
    safe = float(getattr(profile.process, "safe_height", 25.0))
    return {
        # Gốc X trên đường tâm nên vùng cần đi là đối xứng hai bên.
        "cross": (-(r + m), r + m),
        # Gốc Z ngay mặt phôi: xuống dưới 0 là đã cắm vào phôi ở mọi góc xoay.
        "radial": (0.0, top + safe + m),
        # Gốc Y ở mặt đầu ống, cắt chạy vào trong thân ống.
        "along": (-m, float(pipe.length) + m),
    }


def limit_report(profile) -> List[str]:
    """Mô tả hành trình sau khi siết, để hiện cho người dùng đọc."""
    env = envelope(profile)
    if not env:
        return []
    out: List[str] = []
    for role, label in (("cross", "ngang"), ("radial", "nâng hạ"), ("along", "dọc ống")):
        ax = profile.axis(role)
        if ax is None or role not in env:
            continue
        lo, hi = profile.effective_travel(ax)
        out.append(f"{ax.letter} ({label}): {lo:.1f} .. {hi:.1f} mm")
    return out
