"""Căn tâm mâm cặp: chạm bốn mặt ống rồi suy ra gốc."""

import json
import math
import unittest

from pipecut.clamp import (TOUCH_ORDER, ClampError, Touch, envelope,
                           limit_report, solve, work_origin, zero_commands)
from pipecut.config import MachineProfile, PipeSpec
from pipecut.kinematics import Kinematics

AX, AZ = 123.4, -45.6      # tâm mâm cặp thật, toạ độ máy


def round_touches(radius=30.0, nozzle=6.0, side_z=None, runout=0.0,
                  axis_x=AX, axis_z=AZ):
    """Bốn lần chạm sinh ra từ một cái ống tròn ảo đặt đúng chỗ đã biết.

    Chạm sườn ở cao độ ``side_z``: chỗ chạm bị thụt vào theo hình tròn, đúng
    như ngoài đời - dùng để kiểm tra phép lấy điểm giữa có tự khử được không.
    """
    z = axis_z if side_z is None else side_z
    dh = z - axis_z
    half = math.sqrt(max(0.0, radius * radius - dh * dh))
    return {
        "top": Touch({"X": axis_x, "Z": axis_z + radius + runout, "A": 0.0}),
        "left": Touch({"X": axis_x - half - nozzle, "Z": z, "A": 0.0}),
        "right": Touch({"X": axis_x + half + nozzle, "Z": z, "A": 0.0}),
        "top180": Touch({"X": axis_x, "Z": axis_z + radius - runout, "A": 180.0}),
    }


def round_profile(diameter=60.0, length=1000.0):
    p = MachineProfile()
    p.pipe = PipeSpec(shape="round", outer_diameter=diameter,
                      wall_thickness=3.0, length=length)
    return p


class TestSolve(unittest.TestCase):
    def test_recovers_clamp_centre(self):
        p = round_profile()
        cal, warns = solve(round_touches(), p.pipe)
        self.assertEqual(warns, [])
        self.assertAlmostEqual(cal.axis_x, AX, places=9)
        self.assertAlmostEqual(cal.axis_z, AZ, places=9)
        self.assertTrue(cal.valid)

    def test_nozzle_diameter_cancels(self):
        """Béc dày mỏng bao nhiêu cũng ra cùng một tâm - đó là lý do lấy 2 sườn."""
        p = round_profile()
        centres = [solve(round_touches(nozzle=n), p.pipe)[0].axis_x
                   for n in (0.0, 3.0, 6.0, 20.0)]
        for c in centres:
            self.assertAlmostEqual(c, AX, places=9)

    def test_side_touch_height_cancels(self):
        """Chạm sườn cao hay thấp không sao, miễn hai bên cùng một cao độ."""
        p = round_profile()
        for dz in (0.0, -5.0, 8.0, 12.0):
            cal, warns = solve(round_touches(side_z=AZ + dz), p.pipe)
            self.assertAlmostEqual(cal.axis_x, AX, places=9)
            self.assertEqual(warns, [], f"lệch {dz} mm không nên có cảnh báo")

    def test_runout_is_cancelled_and_reported(self):
        p = round_profile()
        cal, warns = solve(round_touches(runout=0.8), p.pipe)
        self.assertAlmostEqual(cal.axis_z, AZ, places=9)   # đã khử
        self.assertAlmostEqual(cal.runout, 0.8, places=9)  # nhưng vẫn báo ra
        self.assertTrue(any("lệch tâm" in w for w in warns))

    def test_box_section_uses_half_height(self):
        p = MachineProfile()
        p.pipe = PipeSpec(shape="rect", width=50.0, height=30.0, wall_thickness=2.0)
        ref = p.pipe.section().reference_height
        t = {
            "top": Touch({"X": AX, "Z": AZ + ref, "A": 0.0}),
            "left": Touch({"X": AX - 25.0 - 6.0, "Z": AZ, "A": 0.0}),
            "right": Touch({"X": AX + 25.0 + 6.0, "Z": AZ, "A": 0.0}),
            "top180": Touch({"X": AX, "Z": AZ + ref, "A": 180.0}),
        }
        cal, warns = solve(t, p.pipe)
        self.assertAlmostEqual(cal.axis_z, AZ, places=9)
        self.assertAlmostEqual(cal.axis_x, AX, places=9)
        self.assertEqual(warns, [])

    def test_missing_touch_refuses(self):
        p = round_profile()
        t = round_touches()
        del t["top180"]
        with self.assertRaises(ClampError):
            solve(t, p.pipe)

    def test_custom_axis_letters(self):
        """Máy khai chữ cái khác thì đọc đúng cột đó, không bám cứng X/Z."""
        p = round_profile()
        t = {k: Touch({"U": v.get("X"), "W": v.get("Z"), "C": v.get("A")})
             for k, v in round_touches().items()}
        cal, _ = solve(t, p.pipe, letters={"cross": "U", "radial": "W", "rotary": "C"})
        self.assertAlmostEqual(cal.axis_x, AX, places=9)
        self.assertAlmostEqual(cal.axis_z, AZ, places=9)


class TestWarnings(unittest.TestCase):
    def test_sides_at_different_heights(self):
        p = round_profile()
        t = round_touches()
        t["right"] = Touch({"X": t["right"].get("X"), "Z": AZ + 9.0, "A": 0.0})
        _, warns = solve(t, p.pipe)
        self.assertTrue(any("lệch cao độ" in w for w in warns))

    def test_top_pair_not_half_turn(self):
        p = round_profile()
        t = round_touches()
        t["top180"] = Touch({"X": AX, "Z": AZ + 30.0, "A": 90.0})
        _, warns = solve(t, p.pipe)
        self.assertTrue(any("180" in w for w in warns))

    def test_top_touch_off_centre(self):
        p = round_profile()
        t = round_touches()
        t["top"] = Touch({"X": AX + 9.0, "Z": AZ + 30.0, "A": 0.0})
        _, warns = solve(t, p.pipe)
        self.assertTrue(any("lệch khỏi đường tâm" in w for w in warns))

    def test_span_narrower_than_declared_pipe(self):
        p = round_profile(diameter=60.0)
        t = round_touches(radius=15.0, nozzle=0.0)   # thật ra ống chỉ ⌀30
        _, warns = solve(t, p.pipe)
        self.assertTrue(any("nhỏ hơn cỡ ống" in w for w in warns))

    def test_span_far_too_wide(self):
        p = round_profile(diameter=60.0)
        t = round_touches(radius=30.0, nozzle=60.0)
        _, warns = solve(t, p.pipe)
        self.assertTrue(any("mâm cặp hay đồ gá" in w for w in warns))

    def test_swapped_sides_are_corrected(self):
        p = round_profile()
        t = round_touches()
        t["left"], t["right"] = t["right"], t["left"]
        cal, warns = solve(t, p.pipe)
        self.assertAlmostEqual(cal.axis_x, AX, places=9)
        self.assertTrue(any("đảo lại" in w for w in warns))


class TestUsingResult(unittest.TestCase):
    def setUp(self):
        self.p = round_profile()
        self.p.clamp, _ = solve(round_touches(), self.p.pipe)

    def test_origin_is_centreline_and_top_surface(self):
        org = work_origin(self.p.clamp, self.p.pipe)
        self.assertAlmostEqual(org["X"], AX, places=9)
        self.assertAlmostEqual(org["Z"], AZ + 30.0, places=9)

    def test_new_pipe_size_needs_no_recalibration(self):
        """Điểm cốt lõi: đổi cỡ ống chỉ khai lại kích thước, gốc tự đúng."""
        before = work_origin(self.p.clamp, self.p.pipe)["Z"]
        self.p.pipe = PipeSpec(shape="round", outer_diameter=100.0, wall_thickness=3.0)
        after = work_origin(self.p.clamp, self.p.pipe)["Z"]
        self.assertAlmostEqual(after - before, 20.0, places=9)  # (100-60)/2
        self.assertAlmostEqual(work_origin(self.p.clamp, self.p.pipe)["X"], AX, places=9)

    def test_zero_commands_set_offset_directly(self):
        lines = zero_commands(self.p)
        self.assertEqual(lines[0], "G92.1")
        # G10 L2 đặt thẳng gốc theo toạ độ máy: mỏ đứng đâu cũng đúng.
        self.assertIn("G10 L2 P1", lines[1])
        self.assertNotIn("L20", lines[1])
        self.assertIn("X123.400", lines[1])
        self.assertIn("Z-15.600", lines[1])

    def test_work_offset_selects_p_number(self):
        self.p.work_offset = "G56"
        self.assertIn("G10 L2 P3", zero_commands(self.p)[1])

    def test_uncalibrated_refuses(self):
        p = round_profile()
        with self.assertRaises(ClampError):
            zero_commands(p)


class TestLimits(unittest.TestCase):
    def setUp(self):
        self.p = round_profile(diameter=60.0, length=1000.0)
        self.p.clamp, _ = solve(round_touches(), self.p.pipe)

    def test_envelope_follows_pipe_size(self):
        env = envelope(self.p)
        m = self.p.clamp.margin
        self.assertAlmostEqual(env["cross"][1], 30.0 + m, places=6)
        self.assertAlmostEqual(env["cross"][0], -(30.0 + m), places=6)
        self.assertAlmostEqual(env["radial"][0], 0.0, places=6)
        self.assertAlmostEqual(env["along"][1], 1000.0 + m, places=6)

    def test_envelope_empty_until_calibrated(self):
        self.assertEqual(envelope(round_profile()), {})

    def test_auto_limits_can_be_turned_off(self):
        self.p.clamp.auto_limits = False
        self.assertEqual(envelope(self.p), {})
        self.assertEqual(limit_report(self.p), [])

    def test_never_widens_machine_travel(self):
        """Vùng ống cần chỉ được siết chặt hơn hành trình cơ khí, không nới ra."""
        ax = self.p.axis("along")
        ax.min_travel, ax.max_travel = 0.0, 500.0
        lo, hi = self.p.effective_travel(ax)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 500.0)

    def test_rotary_stays_unlimited(self):
        ax = self.p.axis("rotary")
        lo, hi = self.p.effective_travel(ax)
        self.assertEqual((lo, hi), (float("-inf"), float("inf")))

    def test_check_limits_uses_envelope(self):
        kin = Kinematics(self.p)
        cross = self.p.letter("cross")
        # Máy cho chạy ngang tới 100 mm, nhưng ống ⌀60 chỉ cần 55 mm.
        self.assertEqual(kin.check_limits({cross: 40.0}), [])
        msgs = kin.check_limits({cross: 90.0})
        self.assertTrue(msgs and "vượt hành trình" in msgs[0])

    def test_z_below_surface_is_rejected(self):
        """Gốc Z ở mặt phôi nên Z âm là đã cắm vào ống ở mọi góc xoay.

        Nới hành trình cơ khí xuống -50 để chắc chắn cái chặn Z âm đến từ vùng
        ống chiếm chứ không phải từ hành trình máy - không thì bài này xanh giả.
        """
        ax = self.p.axis("radial")
        ax.min_travel = -50.0
        kin = Kinematics(self.p)
        radial = ax.letter
        self.assertEqual(kin.check_limits({radial: 5.0}), [])
        self.assertTrue(kin.check_limits({radial: -3.0}))
        self.p.clamp.auto_limits = False           # tắt đi thì hết chặn
        self.assertEqual(kin.check_limits({radial: -3.0}), [])


class TestPersistence(unittest.TestCase):
    def test_survives_json_round_trip(self):
        p = round_profile()
        p.clamp, _ = solve(round_touches(), p.pipe)
        p.clamp.note = "mâm cặp 4 chấu"
        back = MachineProfile.from_dict(json.loads(json.dumps(p.to_dict())))
        self.assertTrue(back.clamp.valid)
        self.assertAlmostEqual(back.clamp.axis_x, AX, places=9)
        self.assertAlmostEqual(back.clamp.axis_z, AZ, places=9)
        self.assertEqual(back.clamp.note, "mâm cặp 4 chấu")
        self.assertEqual(sorted(back.clamp.touches), sorted(TOUCH_ORDER))
        self.assertAlmostEqual(back.clamp.touches["top"].get("Z"), AZ + 30.0, places=9)

    def test_default_profile_has_no_calibration(self):
        p = MachineProfile()
        self.assertFalse(p.clamp.valid)
        self.assertIn("Chưa căn", p.clamp.summary())

    def test_calibration_is_not_lost_by_asdict(self):
        p = round_profile()
        p.clamp, _ = solve(round_touches(), p.pipe)
        d = p.to_dict()
        self.assertIsInstance(d["clamp"]["touches"]["top"], dict)
        self.assertIn("X", d["clamp"]["touches"]["top"])


if __name__ == "__main__":
    unittest.main()
