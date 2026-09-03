"""Sinh G-code cho FluidNC.

Đặc điểm bộ hậu xử lý này:

* **Modal triệt để** - chỉ ghi ra từ lệnh nào thực sự thay đổi (G1/G0, X, A,
  Z, B, F).  Dòng lệnh ngắn đi 40-60% nên UART 115200 nạp được nhiều block
  hơn trong cùng một khoảng thời gian; với ESP32 đây là khác biệt thấy rõ
  giữa chạy mượt và chạy giật.
* **F chỉ ghi lại khi lệch quá ngưỡng** (mặc định 2%), tránh việc mỗi dòng
  đều kèm F làm dài lệnh vô ích.
* Toạ độ được rút gọn số 0 thừa ở đuôi.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import MachineProfile, ROLE_BEVEL, ROLE_RADIAL, ROLE_ROTARY
from .kinematics import AxisValues, Kinematics
from .pathops import Pass, process_contour
from .toolpath import Contour, CutPoint, Toolpath


@dataclass
class ProgramStats:
    lines: int = 0
    moves: int = 0
    cut_length: float = 0.0      # mm đường cắt thật trên bề mặt
    rapid_length: float = 0.0
    estimated_time: float = 0.0  # giây
    pierces: int = 0
    warnings: List[str] = field(default_factory=list)
    contours: List[Dict[str, object]] = field(default_factory=list)
    bounds: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    @property
    def time_text(self) -> str:
        t = int(round(self.estimated_time))
        return f"{t // 3600:d}h {t % 3600 // 60:02d}m {t % 60:02d}s" if t >= 3600 else f"{t // 60:d}m {t % 60:02d}s"


@dataclass
class Program:
    lines: List[str] = field(default_factory=list)
    stats: ProgramStats = field(default_factory=ProgramStats)
    passes: List[Pass] = field(default_factory=list)
    name: str = "job"

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.text())

    def stream_lines(self, strip_comments: bool = True) -> List[str]:
        """Danh sách dòng dùng để gửi xuống máy (bỏ chú thích cho nhẹ bộ đệm)."""
        out: List[str] = []
        for ln in self.lines:
            s = strip_gcode_comment(ln) if strip_comments else ln.strip()
            if s:
                out.append(s)
        return out


def strip_gcode_comment(line: str) -> str:
    """Bỏ chú thích ``( ... )`` và ``; ...`` rồi thu gọn khoảng trắng."""
    out = []
    depth = 0
    for ch in line:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            if ch == ";":
                break
            out.append(ch)
    return " ".join("".join(out).split())


def fmt(value: float, decimals: int = 3) -> str:
    """Định dạng số gọn nhất có thể (bỏ 0 thừa) nhưng vẫn đủ độ chính xác."""
    if abs(value) < 0.5 * 10 ** (-decimals):
        return "0"
    s = f"{value:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


class GCodeBuilder:
    """Bộ ghi G-code có nhớ trạng thái modal."""

    def __init__(self, profile: MachineProfile):
        self.profile = profile
        self.decimals = profile.motion.decimals
        self.lines: List[str] = []
        self.position: AxisValues = {}
        self.mode: Optional[str] = None
        self.feed: Optional[float] = None
        self.moves = 0

    # ---- ghi thô ----
    def raw(self, line: str) -> None:
        if line:
            self.lines.append(line)

    def comment(self, text: str) -> None:
        self.lines.append(f"({text})")

    def blank(self) -> None:
        self.lines.append("")

    def dwell(self, seconds: float) -> None:
        if seconds and seconds > 0:
            self.raw(f"G4 P{fmt(seconds, 3)}")

    # ---- dịch chuyển ----
    def _changed_words(self, target: AxisValues) -> List[str]:
        eps = 0.5 * 10 ** (-self.decimals)
        words: List[str] = []
        for letter in self.profile.letters:
            if letter not in target:
                continue
            v = target[letter]
            cur = self.position.get(letter)
            if cur is None or abs(v - cur) > eps:
                words.append(f"{letter}{fmt(v, self.decimals)}")
        return words

    def move(self, target: AxisValues, feed: Optional[float] = None,
             comment: str = "") -> bool:
        """Ghi một lệnh G0/G1.  Trả về False nếu không có gì thay đổi."""
        words = self._changed_words(target)
        need_feed = False
        mode = "G0" if feed is None else "G1"
        if feed is not None:
            thr = self.profile.motion.feed_change_threshold
            if self.feed is None or self.feed <= 0:
                need_feed = True
            elif abs(feed - self.feed) / max(self.feed, 1e-6) > thr:
                need_feed = True
        if not words:
            if need_feed and mode == "G1":
                self.raw(f"F{fmt(feed, 0)}")
                self.feed = feed
            return False
        parts: List[str] = []
        if self.mode != mode:
            parts.append(mode)
            self.mode = mode
        parts.extend(words)
        if need_feed:
            parts.append(f"F{fmt(feed, 0)}")
            self.feed = feed
        line = " ".join(parts)
        if comment:
            line += f" ({comment})"
        self.raw(line)
        self.position.update(target)
        self.moves += 1
        return True


# --------------------------------------------------------------------------
# Trình biên dịch: Toolpath -> Program
# --------------------------------------------------------------------------
class PostProcessor:
    """Ghép toàn bộ: biên dạng -> đường chạy dao -> G-code FluidNC."""

    def __init__(self, profile: MachineProfile):
        self.profile = profile
        self.kin = Kinematics(profile)
        self.process = profile.process
        self.motion = profile.motion

    # ------------------------------------------------------------------
    def build(self, toolpath: Toolpath, name: Optional[str] = None) -> Program:
        pf = self.profile
        pr = self.process
        b = GCodeBuilder(pf)
        stats = ProgramStats()
        job_name = name or toolpath.name

        radius = toolpath.radius or pf.pipe.radius
        z_safe = pr.safe_height
        z_cut = pr.cut_height
        z_pierce = pr.pierce_height
        use_z = pr.use_radial and pf.axis(ROLE_RADIAL) is not None

        b.comment(f"PipeCut Studio - {job_name}")
        b.comment(f"May: {pf.name}")
        b.comment(f"Ong: OD {pf.pipe.outer_diameter:.1f} x day {pf.pipe.wall_thickness:.1f} mm")
        b.comment(f"Tien trinh: {pr.kind}  kerf {pr.kerf:.2f}  F be mat {pr.cut_feed:.0f} mm/ph")
        b.comment("Truc: " + ", ".join(f"{a.letter}={a.role}" for a in pf.axes if a.enabled))
        for line in pf.preamble:
            b.raw(line)
        b.blank()

        passes: List[Pass] = []
        for contour in toolpath.contours:
            try:
                ps = process_contour(contour, radius, self.motion, pr)
            except Exception as exc:  # biên dạng hỏng không được làm chết cả job
                stats.warnings.append(f"Bỏ qua '{contour.name}': {exc}")
                continue
            passes.append(ps)
            self._emit_pass(b, ps, stats, z_safe, z_cut, z_pierce, use_z)

        if use_z:
            b.move({pf.letter(ROLE_RADIAL): pf.axis(ROLE_RADIAL).apply(z_safe)}, None,
                   comment="ve chieu cao an toan")
        b.blank()
        for line in pf.postamble:
            b.raw(line)

        stats.lines = len(b.lines)
        stats.moves = b.moves
        stats.bounds = self._bounds(passes, z_safe)
        stats.warnings.extend(self._limit_warnings(passes, z_safe, z_cut))
        program = Program(lines=b.lines, stats=stats, passes=passes, name=job_name)

        # Thời gian chạy được tính lại bằng chính bộ diễn giải dùng cho mô phỏng,
        # để con số trên giao diện và trên thanh thời gian mô phỏng luôn khớp nhau.
        # (nhập ở đây để tránh phụ thuộc vòng giữa hai module)
        from .gsim import Playback

        try:
            stats.estimated_time = Playback(pf, program.stream_lines()).duration
        except Exception:
            pass  # giữ ước tính tích luỹ nếu có gì bất thường
        return program

    # ------------------------------------------------------------------
    def _emit_pass(self, b: GCodeBuilder, ps: Pass, stats: ProgramStats,
                   z_safe: float, z_cut: float, z_pierce: float, use_z: bool) -> None:
        pf = self.profile
        pr = self.process
        kin = self.kin
        is_mark = ps.kind == "mark"
        feed_target = (pr.mark_feed or pr.cut_feed) if is_mark else pr.cut_feed
        power = (pr.mark_power or pr.power) if is_mark else pr.power
        z_letter = pf.letter(ROLE_RADIAL)
        rot = pf.axis(ROLE_ROTARY)

        pts = ps.points
        if len(pts) < 2:
            return
        b.blank()
        b.comment(f"--- {ps.name} ({len(pts)} diem) ---")

        # 1) nâng lên chiều cao an toàn
        if use_z:
            b.move({z_letter: pf.axis(ROLE_RADIAL).apply(z_safe)}, None)

        # 2) chạy nhanh tới điểm mồi, quay theo đường ngắn nhất
        start = CutPoint(pts[0].x, pts[0].theta, pts[0].bevel, pts[0].cross)
        if rot:
            cur = b.position.get(rot.letter)
            if cur is not None:
                cur_theta = -cur if rot.invert else cur
                start.theta = kin.shortest_rotary(cur_theta - rot.offset, start.theta)
        shift = start.theta - pts[0].theta
        target = kin.axis_values(start, None)
        prev_pos = dict(b.position)
        b.move(target, None, comment="toi diem moi")
        stats.rapid_length += self._rapid_len(prev_pos, target)
        stats.estimated_time += self._rapid_time(prev_pos, target)

        # 3) mồi / bật nguồn cắt
        if use_z:
            b.move({z_letter: pf.axis(ROLE_RADIAL).apply(z_pierce)}, None)
        on_cmd = pr.on_command
        if power and ("S" not in on_cmd.upper()):
            on_cmd = f"{on_cmd} S{fmt(power, 0)}"
        b.raw(on_cmd)
        stats.pierces += 1
        b.dwell(pr.pierce_delay)
        if use_z and abs(z_pierce - z_cut) > 1e-6:
            b.move({z_letter: pf.axis(ROLE_RADIAL).apply(z_cut)}, pr.plunge_feed,
                   comment="ha xuong chieu cao cat")
            stats.estimated_time += abs(z_pierce - z_cut) / max(pr.plunge_feed, 1.0) * 60.0
        elif use_z:
            b.move({z_letter: pf.axis(ROLE_RADIAL).apply(z_cut)}, pr.plunge_feed)
        stats.estimated_time += pr.pierce_delay

        # 4) chạy cắt: mỗi đoạn có F riêng theo tốc độ bề mặt không đổi
        z_now = z_cut if use_z else None
        prev = start
        cut_len = 0.0
        for raw_pt in pts[1:]:
            cur = CutPoint(raw_pt.x, raw_pt.theta + shift, raw_pt.bevel, raw_pt.cross)
            feed, l_real, l_mach = kin.feed_for(prev, cur, feed_target, z_now, z_now)
            if l_mach <= 1e-9:
                continue
            b.move(kin.axis_values(cur, None), feed)
            cut_len += l_real
            stats.estimated_time += l_mach / max(feed, 1e-6) * 60.0
            prev = cur

        # 5) tắt nguồn cắt
        b.raw(pr.off_command)
        b.dwell(pr.off_delay)
        stats.estimated_time += pr.off_delay

        # 6) tuỳ chọn: đặt lại góc trục xoay về 0..360 để số không cộng dồn mãi
        if rot and self.motion.rotary_rewind:
            cur = b.position.get(rot.letter)
            if cur is not None:
                folded = cur % 360.0
                if abs(folded - cur) > 1e-6:
                    b.raw(f"G10 L20 P1 {rot.letter}{fmt(folded, pf.motion.decimals)}")
                    b.position[rot.letter] = folded
        stats.cut_length += cut_len
        stats.contours.append({
            "name": ps.name,
            "kind": ps.kind,
            "points": len(pts),
            "length": round(cut_len, 2),
        })

    # ------------------------------------------------------------------
    def _rapid_len(self, a: AxisValues, b_: AxisValues) -> float:
        if not a:
            return 0.0
        return self.kin.machine_distance(a, b_)

    def _rapid_time(self, a: AxisValues, b_: AxisValues) -> float:
        if not a:
            return 0.0
        length = self.kin.machine_distance(a, b_)
        if length <= 1e-9:
            return 0.0
        feed = self.kin.clamp_by_axis_rates(1e9, a, b_, length)
        feed = min(feed, 1e9)
        return length / max(feed, 1e-6) * 60.0

    def _bounds(self, passes: Sequence[Pass], z_safe: float) -> Dict[str, Tuple[float, float]]:
        out: Dict[str, Tuple[float, float]] = {}
        for ps in passes:
            for p in ps.points:
                for letter, value in self.kin.axis_values(p, None).items():
                    lo, hi = out.get(letter, (value, value))
                    out[letter] = (min(lo, value), max(hi, value))
        return {k: (round(v[0], 3) + 0.0, round(v[1], 3) + 0.0) for k, v in out.items()}

    def _limit_warnings(self, passes: Sequence[Pass], z_safe: float, z_cut: float) -> List[str]:
        msgs: List[str] = []
        seen = set()
        for ps in passes:
            for p in ps.points:
                for m in self.kin.check_limits(self.kin.axis_values(p, None)):
                    key = m.split("=")[0]
                    if key not in seen:
                        seen.add(key)
                        msgs.append(f"{ps.name}: {m}")
        for z in (z_safe, z_cut):
            for m in self.kin.check_limits({self.profile.letter(ROLE_RADIAL) or "Z": z}):
                if m not in msgs:
                    msgs.append(m)
        return msgs


def build_program(profile: MachineProfile, toolpath: Toolpath,
                  name: Optional[str] = None) -> Program:
    """Hàm tiện dụng: hồ sơ máy + đường chạy dao -> chương trình G-code."""
    return PostProcessor(profile).build(toolpath, name)
