"""Chế độ **dò cạnh**: để máy tự tìm phôi rồi đặt gốc toạ độ.

Vì sao phải làm khác máy phay
-----------------------------
Máy phay dò cạnh bằng cách đưa đầu dò **chạm ngang** vào thành phôi.  Máy cắt
ống thì không: mỏ cắt treo thẳng đứng, chỉ đi lên xuống được, mà đâm ngang vào
ống thì gãy mỏ.

Cách làm ở đây chỉ cần **dò xuống**, đúng thứ mà một đầu cắt thả nổi (floating
head) làm được::

    dò xuống ở vị trí A  ->  chạm   =>  chỗ này còn phôi
    dò xuống ở vị trí B  ->  hụt    =>  chỗ này hết phôi
    chia đôi A-B, dò lại, lặp lại   =>  ra đúng mép phôi

Vài lần chia đôi là đủ: mỗi lần chia đôi khoảng cách còn một nửa, nên từ khoảng
tìm 40 mm xuống sai số 0,1 mm chỉ mất 9 lần dò.

Bốn việc dò được
----------------
====================  =====================================================
``surface``           Chạm mặt trên phôi -> đặt **gốc Z**
``center``            Tìm hai mép trái/phải -> đặt **gốc X** ở đúng tâm,
                      đồng thời **đo được bề rộng thật** của phôi
``end``               Tìm mặt đầu ống -> đặt **gốc Y**
``level``             (ống hộp) xoay tới khi mặt trên nằm ngang -> **gốc A**
====================  =====================================================

Tệp này **không nói chuyện với máy**: nó chỉ sinh ra từng bước và đọc kết quả
trả về, nên chạy và kiểm thử được không cần phần cứng.  Phần gửi lệnh nằm ở
``controller.run_probe``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Generator, List, Optional, Tuple

from .config import (
    MachineProfile,
    ROLE_ALONG,
    ROLE_CROSS,
    ROLE_RADIAL,
    ROLE_ROTARY,
    ROLE_SWIVEL,
)
from .protocol import ProbeResult


class ProbeError(RuntimeError):
    """Dò không ra kết quả dùng được."""


@dataclass
class ProbeSpec:
    """Thông số cho chế độ dò cạnh."""

    seek_feed: float = 300.0        # tốc độ dò lần đầu (mm/ph)
    latch_feed: float = 60.0        # tốc độ dò lại cho chính xác (mm/ph)
    travel_feed: float = 1500.0     # tốc độ di chuyển giữa các điểm dò
    retract: float = 2.0            # nhấc lên sau khi chạm (mm)
    clearance: float = 15.0         # chiều cao an toàn khi chạy ngang (mm)
    max_depth: float = 100.0        # quãng dò xuống tối đa (mm) - đặt theo
                                    # hành trình Z dùng được của máy
    search_span: float = 0.0        # nửa khoảng quét tìm mép (0 = tự tính)
    tolerance: float = 0.1          # dừng chia đôi khi khoảng còn nhỏ hơn (mm)
    max_bisect: int = 12            # số lần chia đôi tối đa
    level_span: float = 0.0         # khoảng cách hai điểm đo khi cân mặt (0 = tự)
    level_passes: int = 3           # số vòng lặp khi cân mặt phẳng
    level_tolerance: float = 0.15   # dừng khi hai điểm chênh nhau ít hơn (mm)
    double_tap: bool = True         # dò hai lần (nhanh rồi chậm) cho chính xác

    # --- Que dò riêng đặt cạnh mỏ cắt ---------------------------------
    # Đầu que dò không nằm cùng chỗ với mũi cắt, nên mọi số đo được là đo ở
    # **vị trí que dò**.  Ba số dưới đây nói que dò lệch khỏi mũi cắt bao
    # nhiêu, để phần mềm quy kết quả về đúng mũi cắt khi đặt gốc.
    #
    # Dùng đầu cắt thả nổi (chính mỏ chạm phôi) thì để cả ba bằng 0.
    offset_x: float = 0.0           # que dò lệch bao nhiêu theo trục ngang (mm)
    offset_y: float = 0.0           # que dò lệch bao nhiêu theo trục dọc phôi (mm)
    probe_below: float = 0.0        # đầu que dò THẤP HƠN mũi cắt bao nhiêu (mm)

    # --- Đầu đảo: một mô-tơ xoay qua lại giữa mỏ cắt và que dò ---------
    # Hai đầu gắn lệch nhau 90 độ trên cùng một trục đảo, nên xoay 90 độ là
    # đổi đầu nào chúc xuống.  Kiểu này có cái hay: khi mỗi đầu đã chúc
    # xuống thì cả hai nằm **đúng cùng một chỗ theo X và Y**, chỉ khác chiều
    # cao (bằng hiệu chiều dài hai đầu).  Vì vậy thường chỉ phải khai
    # ``probe_below``, còn hai số lệch ngang/dọc để 0 - trừ khi hai đầu còn
    # gắn lệch nhau dọc theo chính trục đảo.
    # --- Dò bằng chính mỏ cắt (ohmic) ---------------------------------
    # Kẹp một dây vào đầu mỏ plasma, cho Z hạ xuống tới khi béc chạm phôi là
    # đóng mạch.  Không cần đầu dò riêng, không cần trục đảo - đầu dò chính
    # là mũi cắt nên **mọi số lệch đều bằng 0**.
    #
    # Đổi lại phải lo phần điện: xem mục 12 trong hướng dẫn.  Nếu có rơ-le
    # tách dây dò ra khỏi mạch lúc cắt thì khai số ngõ ra ở đây, phần mềm sẽ
    # tự đóng lúc dò và ngắt trước khi cắt.
    ohmic: bool = False             # dò bằng chính mỏ cắt
    ohmic_output: int = -1          # ngõ ra số điều khiển rơ-le tách dây dò
                                    # (-1 = đấu chết, không có rơ-le)
    ohmic_settle: float = 0.3       # chờ rơ-le đóng/ngắt xong (giây)

    swivel: bool = False            # máy có trục đảo đầu không
    swivel_torch: float = 0.0       # góc trục đảo khi MỎ CẮT chúc xuống (độ)
    swivel_probe: float = 90.0      # góc trục đảo khi QUE DÒ chúc xuống (độ)
    swivel_z: float = 25.0          # nâng lên cao độ này rồi mới xoay đảo (mm)
    swivel_feed: float = 0.0        # tốc độ xoay đảo (độ/phút, 0 = chạy nhanh)
    swivel_dwell: float = 0.3       # chờ sau khi xoay xong cho hết rung (giây)

    @property
    def swing_radius(self) -> float:
        """Bán kính quét lớn nhất của đầu đảo khi xoay, tính từ mũi cắt.

        Lúc xoay, đầu nào dài hơn sẽ quét một cung; điểm thấp nhất của cung đó
        nằm sâu hơn mũi cắt đúng bằng hiệu chiều dài hai đầu.  Đây là số tối
        thiểu phải nâng lên trước khi xoay.
        """
        return max(0.0, self.probe_below)

    @property
    def has_offset(self) -> bool:
        return any(abs(v) > 1e-9 for v in
                   (self.offset_x, self.offset_y, self.probe_below))

    def offsets(self, profile) -> Dict[str, float]:
        """Khoảng lệch của que dò so với mũi cắt, theo từng chữ cái trục."""
        out: Dict[str, float] = {}
        xl = profile.letter(ROLE_CROSS)
        yl = profile.letter(ROLE_ALONG)
        zl = profile.letter(ROLE_RADIAL)
        if xl:
            out[xl] = self.offset_x
        if yl:
            out[yl] = self.offset_y
        if zl:
            # que dò thấp hơn mũi cắt => lệch theo Z là số âm
            out[zl] = -self.probe_below
        return out

    def validate(self) -> List[str]:
        msgs: List[str] = []
        if self.latch_feed > self.seek_feed:
            msgs.append("Tốc độ dò lại nên chậm hơn tốc độ dò lần đầu.")
        if self.retract <= 0:
            msgs.append("Phải nhấc mỏ lên sau khi chạm, nếu không lần dò sau bị kẹt.")
        if self.max_depth <= 0:
            msgs.append("Quãng dò xuống tối đa phải lớn hơn 0.")
        if self.clearance < self.retract:
            msgs.append("Chiều cao an toàn phải lớn hơn quãng nhấc.")
        if (abs(self.offset_x) > 1e-9 or abs(self.offset_y) > 1e-9) \
                and self.probe_below <= 0.0:
            msgs.append(
                "Đã khai que dò lệch khỏi mỏ nhưng chưa khai nó thấp hơn mỏ bao "
                "nhiêu. Que dò phải nhô xuống thấp hơn mũi cắt, không thì mỏ "
                "đâm vào phôi trước khi que kịp chạm."
            )
        if self.probe_below < 0.0:
            msgs.append("Que dò phải THẤP HƠN mũi cắt: số này không được âm.")
        if self.ohmic:
            if self.has_offset:
                msgs.append(
                    "Dò bằng chính mỏ cắt thì đầu dò CHÍNH LÀ mũi cắt, mọi số "
                    "lệch phải bằng 0."
                )
            if self.swivel:
                msgs.append(
                    "Đã chọn dò bằng chính mỏ cắt thì không cần đầu đảo nữa - "
                    "tắt một trong hai."
                )
            if self.ohmic_output >= 8:
                msgs.append("Số ngõ ra phải trong khoảng 0..7 (M62/M63 của FluidNC).")
            if self.seek_feed > 400.0:
                msgs.append(
                    f"Dò bằng chính mỏ cắt nên đi chậm: {self.seek_feed:g} mm/ph "
                    f"là nhanh quá, béc đập vào phôi sẽ móp lỗ. Nên để 150-300."
                )
        if self.swivel:
            if abs(self.swivel_probe - self.swivel_torch) < 1e-6:
                msgs.append(
                    "Góc đảo cho mỏ cắt và cho que dò đang trùng nhau - phần "
                    "mềm sẽ không đổi được đầu."
                )
            if self.swivel_z < self.swing_radius:
                msgs.append(
                    f"Cao độ xoay đảo ({self.swivel_z:g} mm) thấp hơn tầm quét "
                    f"của đầu dài ({self.swing_radius:g} mm) - xoay là đầu dò "
                    f"quét vào phôi. Nâng cao độ xoay lên."
                )
        return msgs


@dataclass
class Step:
    """Một bước trong quy trình dò: mấy dòng lệnh và có chờ kết quả dò không."""

    lines: List[str]
    probe: bool = False
    note: str = ""


@dataclass
class ProbeOutcome:
    """Kết quả cuối cùng của một quy trình dò."""

    kind: str
    values: Dict[str, float] = field(default_factory=dict)
    zero: Dict[str, float] = field(default_factory=dict)   # gốc toạ độ đề nghị
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def text(self) -> str:
        bits = [f"{k} = {v:.3f}" for k, v in self.values.items()]
        return f"{self.kind}: " + ", ".join(bits) if bits else self.kind


# Quy trình dò là một generator: nó *yield* từng bước, nhận lại kết quả dò.
Routine = Generator[Step, Optional[ProbeResult], ProbeOutcome]


def _zero_at(spec: ProbeSpec, profile: MachineProfile, letter: str) -> float:
    """Giá trị gốc chi tiết cần đặt cho một trục, đã bù khoảng lệch que dò.

    Số đo được là đo ở **đầu que dò**, nhưng gốc phải quy về **mũi cắt**.  Lúc
    que dò đang đứng đúng chỗ vừa tìm ra, mũi cắt còn cách chỗ đó đúng bằng
    khoảng lệch ``d``, nên toạ độ chi tiết ngay lúc này phải là ``-d`` chứ
    không phải 0.

    Ví dụ: que dò thấp hơn mũi cắt 12 mm.  Que chạm mặt phôi thì mũi cắt đang
    ở **trên** mặt phôi 12 mm, nên gốc Z phải đặt là +12, không phải 0.
    """
    return -spec.offsets(profile).get(letter, 0.0)


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


# --------------------------------------------------------------------------
# Những khối lệnh dùng lại
# --------------------------------------------------------------------------
def _probe_down(spec: ProbeSpec, z_letter: str, depth: float,
                feed: float, required: bool) -> Step:
    """Một lần dò xuống.

    ``G38.2`` báo lỗi nếu không chạm - dùng khi chắc chắn phải có phôi.
    ``G38.3`` không báo lỗi - dùng khi dò hụt là **thông tin hợp lệ**, tức là
    lúc đang tìm mép: hụt nghĩa là chỗ đó hết phôi rồi.
    """
    code = "G38.2" if required else "G38.3"
    return Step([f"G91 {code} {z_letter}{fmt(-abs(depth))} F{fmt(feed)}", "G90"],
                probe=True, note="dò xuống")


def _retract(spec: ProbeSpec, z_letter: str) -> Step:
    return Step([f"G91 G0 {z_letter}{fmt(spec.retract)}", "G90"], note="nhấc mỏ")


def _lift_to(spec: ProbeSpec, z_letter: str, z: float) -> Step:
    return Step([f"G0 {z_letter}{fmt(z)}"], note="lên cao độ an toàn")


def swivel_steps(profile: MachineProfile, spec: ProbeSpec,
                 to_probe: bool) -> List[Step]:
    """Các bước xoay đầu đảo sang que dò (hoặc trả về mỏ cắt).

    Trình tự bắt buộc: **nâng lên trước, xoay sau**.  Lúc xoay, đầu dài hơn
    quét một cung quanh trục đảo; không nâng đủ cao là nó quét thẳng vào phôi.
    """
    if not spec.swivel:
        return []
    sl = profile.letter(ROLE_SWIVEL)
    zl = profile.letter(ROLE_RADIAL)
    if not sl:
        raise ProbeError(
            "Đã bật đầu đảo nhưng hồ sơ máy chưa khai trục nào có vai trò "
            "'swivel'. Thêm một trục cho mô-tơ đảo đầu rồi thử lại."
        )
    angle = spec.swivel_probe if to_probe else spec.swivel_torch
    what = "que dò" if to_probe else "mỏ cắt"
    steps: List[Step] = []
    if zl:
        steps.append(Step([f"G0 {zl}{fmt(spec.swivel_z)}"],
                          note=f"nâng lên {spec.swivel_z:g} mm trước khi xoay đảo"))
    move = "G0" if spec.swivel_feed <= 0 else f"G1 F{fmt(spec.swivel_feed)}"
    steps.append(Step([f"{move} {sl}{fmt(angle)}"],
                      note=f"xoay đầu đảo về {what} ({angle:g}°)"))
    if spec.swivel_dwell > 0:
        steps.append(Step([f"G4 P{fmt(spec.swivel_dwell)}"], note="chờ hết rung"))
    return steps


def arm_steps(profile: MachineProfile, spec: ProbeSpec) -> List[Step]:
    """Chuẩn bị dò: tắt mỏ, đóng dây dò, đưa đầu dò vào tư thế.

    Bước **tắt nguồn cắt luôn được gửi**, bất kể phần cứng kiểu gì.  Dò với mỏ
    đang cháy là hỏng phôi và hỏng cả đầu dò.
    """
    steps: List[Step] = [Step([profile.process.off_command], note="tắt nguồn cắt")]
    if spec.ohmic and spec.ohmic_output >= 0:
        steps.append(Step([f"M62 P{int(spec.ohmic_output)}"],
                          note="đóng rơ-le nối dây dò vào mỏ"))
        if spec.ohmic_settle > 0:
            steps.append(Step([f"G4 P{fmt(spec.ohmic_settle)}"], note="chờ rơ-le đóng"))
    steps.extend(swivel_steps(profile, spec, to_probe=True))
    return steps


def disarm_lines(profile: MachineProfile, spec: ProbeSpec) -> List[str]:
    """Lệnh kết thúc dò: trả đầu về mỏ cắt, ngắt dây dò, tắt mỏ cho chắc.

    Bộ điều khiển gửi chuỗi này **kể cả khi quy trình dò báo lỗi giữa chừng**.
    Bỏ máy lại ở tư thế đầu dò chúc xuống, hoặc còn nối dây dò vào mỏ, là lần
    cắt sau hỏng ngay: đâm kim vào phôi, hoặc điện hồ quang chạy ngược vào
    mạch dò.
    """
    out: List[str] = []
    for step in swivel_steps(profile, spec, to_probe=False):
        out.extend(step.lines)
    if spec.ohmic and spec.ohmic_output >= 0:
        out.append(f"M63 P{int(spec.ohmic_output)}")
        if spec.ohmic_settle > 0:
            out.append(f"G4 P{fmt(spec.ohmic_settle)}")
    out.append(profile.process.off_command)
    return out


# tên cũ, giữ cho mã đang gọi
def stow_lines(profile: MachineProfile, spec: ProbeSpec) -> List[str]:
    return disarm_lines(profile, spec)


def _move_to(letter: str, value: float, feed: float) -> Step:
    return Step([f"G0 {letter}{fmt(value)}"], note=f"tới {letter}{fmt(value)}")


# --------------------------------------------------------------------------
# 1. Chạm mặt phôi
# --------------------------------------------------------------------------
def probe_surface(profile: MachineProfile, spec: ProbeSpec,
                  set_zero: bool = True,
                  start: Optional[Dict[str, float]] = None) -> Routine:
    """Dò xuống chạm mặt trên phôi.  Kết quả là cao độ mặt phôi."""
    zl = profile.letter(ROLE_RADIAL)
    if not zl:
        raise ProbeError("Hồ sơ máy chưa khai trục nâng hạ (radial).")

    res = yield _probe_down(spec, zl, spec.max_depth, spec.seek_feed, True)
    if res is None or not res.touched:
        raise ProbeError(
            f"Dò hết {spec.max_depth:g} mm mà không chạm gì. Kiểm tra phôi đã "
            "vào đúng chỗ chưa, và cảm biến chạm có nối đúng không."
        )
    z = res.get(zl)
    if spec.double_tap:
        yield _retract(spec, zl)
        res2 = yield _probe_down(spec, zl, spec.retract * 2.0, spec.latch_feed, True)
        if res2 is not None and res2.touched:
            z = res2.get(zl)
    yield _retract(spec, zl)

    out = ProbeOutcome(kind="Chạm mặt phôi", values={zl: z})
    if set_zero:
        out.zero[zl] = _zero_at(spec, profile, zl)
        if spec.probe_below > 0:
            out.notes.append(
                f"Đặt gốc {zl} tại mặt phôi, đã bù que dò thấp hơn mũi cắt "
                f"{spec.probe_below:g} mm.")
        else:
            out.notes.append(f"Đặt gốc {zl} ngay tại mặt phôi.")
    return out


# --------------------------------------------------------------------------
# 2. Tìm mép bằng cách chia đôi
# --------------------------------------------------------------------------
def _bisect_edge(spec: ProbeSpec, axis: str, z_letter: str,
                 inside: float, outside: float, depth: float,
                 z_safe: float) -> Routine:
    """Chia đôi giữa một điểm **còn phôi** và một điểm **hết phôi**.

    Trả về vị trí mép, kèm sai số còn lại của phép chia đôi.
    """
    lo, hi = inside, outside          # lo luôn còn phôi, hi luôn hết phôi
    for _ in range(spec.max_bisect):
        if abs(hi - lo) <= spec.tolerance:
            break
        mid = (lo + hi) / 2.0
        yield _lift_to(spec, z_letter, z_safe)
        yield _move_to(axis, mid, spec.travel_feed)
        res = yield _probe_down(spec, z_letter, depth, spec.seek_feed, False)
        if res is not None and res.touched:
            lo = mid
        else:
            hi = mid
    yield _lift_to(spec, z_letter, z_safe)
    edge = (lo + hi) / 2.0
    return ProbeOutcome(kind="mép", values={axis: edge, "sai_so": abs(hi - lo) / 2.0})


def section_extent(section, theta_deg: float, steps: int = 720) -> float:
    """Bề ngang của tiết diện khi phôi quay góc ``theta``.

    Ống hộp 50x50 ngửa mặt phẳng lên chỉ rộng **50 mm**, nhưng quay 45 độ cho
    góc chĩa ngang thì rộng tới **65,7 mm**.  Muốn đối chiếu bề rộng đo được
    với số đã khai thì phải so đúng con số ở góc quay hiện tại, chứ so với bán
    kính bao là sai hẳn.
    """
    a = math.radians(theta_deg)
    ca, sa = math.cos(a), math.sin(a)
    best = 0.0
    for i in range(steps):
        cx, cy = section.point_at(section.perimeter * i / steps)
        best = max(best, abs(cx * ca - cy * sa))
    return 2.0 * best


def extent_range(section, steps: int = 90) -> Tuple[float, float]:
    """Bề ngang nhỏ nhất và lớn nhất có thể, lấy trên mọi góc quay."""
    values = [section_extent(section, 360.0 * i / steps) for i in range(steps)]
    return (min(values), max(values))


def _expected_drop(profile: MachineProfile) -> float:
    """Mặt phôi tụt xuống bao nhiêu từ đỉnh ra tới mép ngoài cùng.

    Quyết định quãng dò xuống khi tìm mép: phải sâu hơn số này thì mới phân
    biệt được "còn phôi" với "hết phôi".  Ống hộp chỉ tụt bằng bán kính góc
    lượn; ống tròn tụt cả một bán kính.
    """
    section = profile.pipe.section()
    top = section.reference_height
    steps = 360
    far_x, far_y = 0.0, top
    for i in range(steps + 1):
        cx, cy = section.point_at(section.perimeter * i / steps)
        if cx > far_x:
            far_x, far_y = cx, cy
    return max(1.0, top - far_y)


def find_center(profile: MachineProfile, spec: ProbeSpec,
                set_zero: bool = True,
                start: Optional[Dict[str, float]] = None) -> Routine:
    """Tìm hai mép trái/phải của phôi -> tâm phôi và bề rộng thật.

    Đây là quy trình đáng giá nhất: ngoài việc đặt gốc X đúng đường tâm, nó
    còn **đo lại bề rộng phôi** và đối chiếu với số đã khai.  Khai sai kích
    thước là lỗi âm thầm nguy hiểm nhất - mọi thứ vẫn chạy, chỉ có đường cắt
    là sai chỗ.
    """
    xl = profile.letter(ROLE_CROSS)
    zl = profile.letter(ROLE_RADIAL)
    if not xl or not zl:
        raise ProbeError("Cần cả trục ngang và trục nâng hạ để tìm tâm phôi.")

    section = profile.pipe.section()
    half = section.max_radius
    span = spec.search_span if spec.search_span > 0 else half * 0.6 + 10.0

    # Quãng dò tìm mép phải đủ sâu để **chạm tới điểm rộng nhất** của tiết
    # diện, nếu không mép tìm được chỉ là "chỗ mặt tụt quá ngưỡng" chứ không
    # phải mép thật - và khi phôi bị xoay lệch thì hai bên tụt không đều nhau
    # nên tâm suy ra bị lệch theo.  Dò tới đúng mép thật thì tâm luôn đúng, vì
    # mọi tiết diện ở đây đều đối xứng qua tâm khi quay 180 độ.
    need = spec.clearance + section.reference_height + section.max_radius + 3.0
    depth_edge = min(need, spec.max_depth)
    capped = depth_edge < need - 1e-6

    # 1) chạm mặt ngay tại chỗ đang đứng để biết cao độ an toàn
    top = yield from probe_surface(profile, spec, set_zero=False, start=start)
    z_top = top.values[zl]
    z_safe = z_top + spec.clearance
    # Quét quanh **chỗ mỏ đang đứng**, không phải quanh gốc 0: lúc dò cạnh thì
    # gốc toạ độ chưa có nghĩa gì, người vận hành chỉ vừa rà mỏ vào giữa phôi.
    start_x = float((start or {}).get(xl, 0.0))

    edges: Dict[str, float] = {}
    errors: Dict[str, float] = {}
    for name, sign in (("trái", -1.0), ("phải", 1.0)):
        outside = start_x + sign * (half + span)
        # kiểm tra điểm ngoài đúng là hết phôi
        yield _lift_to(spec, zl, z_safe)
        yield _move_to(xl, outside, spec.travel_feed)
        res = yield _probe_down(spec, zl, depth_edge + spec.clearance,
                                spec.seek_feed, False)
        if res is not None and res.touched:
            raise ProbeError(
                f"Ở vị trí {xl}{outside:.1f} vẫn còn chạm phôi. Nới rộng khoảng "
                f"quét, hoặc kiểm tra lại kích thước phôi đã khai."
            )
        result = yield from _bisect_edge(spec, xl, zl, start_x, outside,
                                         depth_edge, z_safe)
        edges[name] = result.values[xl]
        errors[name] = result.values["sai_so"]

    centre = (edges["trái"] + edges["phải"]) / 2.0
    width = abs(edges["phải"] - edges["trái"])
    yield _lift_to(spec, zl, z_safe)
    yield _move_to(xl, centre, spec.travel_feed)

    out = ProbeOutcome(
        kind="Tìm tâm phôi",
        values={f"{xl}_trái": edges["trái"], f"{xl}_phải": edges["phải"],
                f"{xl}_tâm": centre, "bề_rộng": width,
                "sai_số": max(errors.values())},
    )
    # Đối chiếu bề rộng đo được với tiết diện đã khai.  Phôi có thể đang bị
    # xoay lệch nên phải so với **cả dải** bề ngang có thể có, rồi mới suy ra
    # đây là sai kích thước hay chỉ là phôi đặt nghiêng.
    flat = section_extent(section, 0.0)
    lo, hi = extent_range(section)
    slack = max(0.5, flat * 0.02)
    if width < lo - slack or width > hi + slack:
        out.warnings.append(
            f"Đo được bề rộng {width:.2f} mm, nhưng tiết diện đã khai chỉ có thể "
            f"rộng từ {lo:.2f} đến {hi:.2f} mm ở mọi góc xoay. Kích thước phôi "
            f"khai trong hồ sơ máy nhiều khả năng sai."
        )
    elif width > flat + slack:
        guess = min((abs(section_extent(section, t / 4.0) - width), t / 4.0)
                    for t in range(0, 361))[1]
        out.warnings.append(
            f"Bề rộng đo được {width:.2f} mm, rộng hơn mức {flat:.2f} mm của "
            f"tư thế mặt phẳng ngửa lên - phôi đang bị **xoay lệch khoảng "
            f"{guess:.1f}°**. Chạy 'Cân mặt phẳng' trước rồi tìm tâm lại."
        )
    else:
        out.notes.append(f"Bề rộng đo được {width:.2f} mm, khớp tiết diện đã "
                         f"khai ({flat:.2f} mm).")
    if capped:
        out.warnings.append(
            f"Quãng dò xuống bị chặn ở {spec.max_depth:g} mm, cần {need:.0f} mm "
            f"mới chắc chắn chạm tới mép rộng nhất. Kết quả vẫn dùng được nếu "
            f"mặt phôi đang nằm ngang; nếu phôi bị xoay lệch thì hãy chạy "
            f"'Cân mặt phẳng' trước, hoặc nới quãng dò tối đa."
        )
    if set_zero:
        out.zero[xl] = _zero_at(spec, profile, xl)
        extra = (f", đã bù que dò lệch {spec.offset_x:g} mm"
                 if abs(spec.offset_x) > 1e-9 else "")
        out.notes.append(f"Đặt gốc {xl} tại đúng đường tâm phôi{extra}.")
    return out


def find_end(profile: MachineProfile, spec: ProbeSpec,
             set_zero: bool = True,
             start: Optional[Dict[str, float]] = None) -> Routine:
    """Tìm mặt đầu ống dọc theo trục phôi -> đặt gốc theo chiều dọc."""
    yl = profile.letter(ROLE_ALONG)
    zl = profile.letter(ROLE_RADIAL)
    if not yl or not zl:
        raise ProbeError("Cần cả trục dọc phôi và trục nâng hạ để tìm đầu ống.")

    span = spec.search_span if spec.search_span > 0 else 60.0
    top = yield from probe_surface(profile, spec, set_zero=False, start=start)
    z_top = top.values[zl]
    z_safe = z_top + spec.clearance
    depth_edge = spec.clearance + 5.0

    # Chỗ đang đứng vừa được xác nhận là còn phôi ở bước chạm mặt bên trên.
    inside = float((start or {}).get(yl, 0.0))
    # Tự nới rộng khoảng quét cho tới khi ra khỏi phôi: người vận hành không
    # phải đoán trước đầu ống nằm cách chỗ đang đứng bao xa.
    reach = abs(span)
    outside = inside - reach
    for _ in range(6):
        yield _lift_to(spec, zl, z_safe)
        yield _move_to(yl, outside, spec.travel_feed)
        res = yield _probe_down(spec, zl, depth_edge, spec.seek_feed, False)
        if res is None or not res.touched:
            break
        reach *= 2.0
        outside = inside - reach
    else:
        raise ProbeError(
            f"Lùi tới {yl}{outside:.0f} mà vẫn còn chạm phôi. Kiểm tra cảm biến "
            f"chạm có bị kẹt ở trạng thái đóng không, hoặc đưa mỏ về gần đầu "
            f"ống rồi dò lại."
        )
    result = yield from _bisect_edge(spec, yl, zl, inside, outside,
                                     depth_edge, z_safe)
    edge = result.values[yl]
    out = ProbeOutcome(kind="Tìm đầu ống",
                       values={yl: edge, "sai_số": result.values["sai_so"]})
    if set_zero:
        out.zero[yl] = _zero_at(spec, profile, yl)
        extra = (f", đã bù que dò lệch {spec.offset_y:g} mm"
                 if abs(spec.offset_y) > 1e-9 else "")
        out.notes.append(f"Đặt gốc {yl} ngay tại mặt đầu ống{extra}.")
    return out


# --------------------------------------------------------------------------
# 4. Cân mặt phẳng ống hộp
# --------------------------------------------------------------------------
def level_face(profile: MachineProfile, spec: ProbeSpec,
               set_zero: bool = True,
               start: Optional[Dict[str, float]] = None) -> Routine:
    """Xoay ống tới khi **mặt trên nằm ngang** - dùng cho ống hộp.

    Đo cao độ ở hai điểm cách nhau trên mặt trên; nếu chênh nhau thì mặt đang
    nghiêng, xoay đúng góc nghiêng đó là mặt nằm ngang.  Vì mặt hộp là mặt
    phẳng nên phép này **chính xác chứ không phải mò**: một vòng là gần đúng
    ngay, các vòng sau chỉ để xác nhận.
    """
    xl = profile.letter(ROLE_CROSS)
    zl = profile.letter(ROLE_RADIAL)
    al = profile.letter(ROLE_ROTARY)
    if not (xl and zl and al):
        raise ProbeError("Cần trục ngang, trục nâng hạ và trục xoay để cân mặt.")
    if profile.pipe.is_round:
        raise ProbeError("Ống tròn không có mặt phẳng để cân - bỏ qua bước này.")

    section = profile.pipe.section()
    flat = max(2.0, section.hx - section.rc)      # nửa bề rộng phần phẳng
    span = spec.level_span if spec.level_span > 0 else flat * 0.7
    depth = spec.max_depth

    centre_x = float((start or {}).get(xl, 0.0))
    heights: List[Tuple[float, float]] = []
    tilt = 0.0
    first_tilt: Optional[float] = None
    turned = 0.0
    for _ in range(max(1, spec.level_passes)):
        heights = []
        for x in (centre_x - span, centre_x + span):
            yield _lift_to(spec, zl, spec.clearance)
            yield _move_to(xl, x, spec.travel_feed)
            res = yield _probe_down(spec, zl, depth, spec.seek_feed, True)
            if res is None or not res.touched:
                raise ProbeError(
                    f"Dò hụt ở {xl}{x:.1f}. Hai điểm đo phải nằm gọn trên mặt "
                    f"phẳng - thu nhỏ khoảng đo lại."
                )
            heights.append((x, res.get(zl)))
            yield _retract(spec, zl)
        (x1, z1), (x2, z2) = heights
        tilt = math.degrees(math.atan2(z2 - z1, x2 - x1))
        if first_tilt is None:
            first_tilt = tilt
        if abs(z2 - z1) <= spec.level_tolerance:
            break
        turned -= tilt
        yield Step([f"G91 G0 {al}{fmt(-tilt)}", "G90"],
                   note=f"xoay {-tilt:.2f}° cho mặt nằm ngang")

    (x1, z1), (x2, z2) = heights
    out = ProbeOutcome(kind="Cân mặt phẳng",
                       values={"nghiêng_ban_đầu": first_tilt or 0.0,
                               "đã_xoay": turned,
                               "chênh_còn_lại": z2 - z1})
    if abs(z2 - z1) > spec.level_tolerance:
        out.warnings.append(
            f"Còn chênh {z2 - z1:+.2f} mm sau {spec.level_passes} vòng. "
            f"Kiểm tra phôi có bị cong hay mâm cặp kẹp lệch không."
        )
    else:
        out.notes.append(f"Mặt trên đã nằm ngang (chênh {z2 - z1:+.3f} mm).")
    if set_zero:
        out.zero[al] = 0.0
        out.notes.append(f"Đặt gốc {al} tại vị trí mặt phẳng nằm ngang.")
    return out


def find_all(profile: MachineProfile, spec: ProbeSpec,
             set_zero: bool = True,
             start: Optional[Dict[str, float]] = None) -> Routine:
    """Chạy trọn gói: dò xong là có đủ bốn gốc toạ độ.

    Thứ tự có lý do:

    1. **Chạm mặt** trước để biết mặt phôi ở đâu, mọi bước sau mới dám hạ mỏ.
    2. **Cân mặt phẳng** (ống hộp) - phải làm trước khi tìm tâm, vì phôi xoay
       lệch thì bề rộng đo được không phải bề rộng thật.
    3. **Tìm tâm** theo trục ngang.
    4. **Tìm đầu ống** theo trục dọc.

    Cuối cùng mới đặt gốc một lượt, để nếu bước nào hỏng thì gốc cũ vẫn nguyên.
    """
    pos = dict(start or {})
    out = ProbeOutcome(kind="Dò cạnh trọn gói")

    def merge(part: ProbeOutcome, prefix: str) -> None:
        for k, v in part.values.items():
            out.values[f"{prefix}.{k}"] = v
        out.notes.extend(f"{prefix}: {t}" for t in part.notes)
        out.warnings.extend(f"{prefix}: {t}" for t in part.warnings)
        out.zero.update(part.zero)

    surface = yield from probe_surface(profile, spec, set_zero=set_zero, start=pos)
    merge(surface, "Chạm mặt")

    if not profile.pipe.is_round:
        level = yield from level_face(profile, spec, set_zero=set_zero, start=pos)
        merge(level, "Cân mặt")

    centre = yield from find_center(profile, spec, set_zero=set_zero, start=pos)
    merge(centre, "Tìm tâm")
    xl = profile.letter(ROLE_CROSS)
    if xl and f"{xl}_tâm" in centre.values:
        pos[xl] = centre.values[f"{xl}_tâm"]

    end = yield from find_end(profile, spec, set_zero=set_zero, start=pos)
    merge(end, "Đầu ống")
    return out


def with_probe_setup(profile: MachineProfile, spec: ProbeSpec,
                     routine: Routine) -> Routine:
    """Bọc một quy trình dò bằng bước chuẩn bị và bước kết thúc.

    Chuẩn bị (tắt mỏ, đóng dây dò, xoay đầu đảo) -> chạy quy trình -> kết thúc.
    Phần cứng kiểu nào cũng đi qua đây; máy đơn giản thì chỉ còn mỗi lệnh tắt
    nguồn cắt.

    Nếu quy trình lỗi giữa chừng, bước kết thúc **không** chạy ở đây - việc đó
    do ``controller.run_probe`` lo bằng chuỗi ``cleanup``, để nó chạy được cả
    khi người dùng bấm dừng.
    """
    for step in arm_steps(profile, spec):
        yield step
    outcome = yield from routine
    for line in disarm_lines(profile, spec):
        yield Step([line], note="kết thúc dò")
    if outcome is not None:
        if spec.swivel:
            outcome.notes.append("Đã trả đầu đảo về mỏ cắt.")
        if spec.ohmic and spec.ohmic_output >= 0:
            outcome.notes.append("Đã ngắt rơ-le dây dò khỏi mỏ cắt.")
    return outcome


# tên cũ, giữ cho mã đang gọi
with_swivel = with_probe_setup


ROUTINES: Dict[str, Tuple[str, Callable[..., Routine]]] = {
    "surface": ("Chạm mặt phôi (gốc Z)", probe_surface),
    "center": ("Tìm tâm phôi (gốc X)", find_center),
    "end": ("Tìm đầu ống (gốc Y)", find_end),
    "level": ("Cân mặt phẳng (gốc A, ống hộp)", level_face),
    "all": ("Dò trọn gói (Z -> A -> X -> Y)", find_all),
}
