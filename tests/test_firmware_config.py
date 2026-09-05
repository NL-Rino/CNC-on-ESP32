"""Soát tệp cấu hình FluidNC mẫu.

Khai sai một khoá trong YAML là FluidNC **lặng lẽ bỏ qua cả khối**: khai nhầm
tên driver thì trục không có chân STEP/DIR nên đứng im, khai nhầm chỗ nguồn cắt
thì mỏ không bao giờ kích.  Bộ này đối chiếu mọi khoá với danh sách lấy từ
chính mã nguồn FluidNC 4.0.4.
"""

import os
import re
import unittest

try:
    import yaml
except ImportError:                                   # pragma: no cover
    yaml = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {
    "esp32": os.path.join(REPO, "firmware", "fluidnc_pipe4axis.yaml"),
    "esp32s3": os.path.join(REPO, "firmware", "fluidnc_pipe4axis_s3.yaml"),
}

# --- danh sách khoá hợp lệ, lấy từ mã nguồn FluidNC v4.0.4 -------------
ROOT = {"name", "board", "meta", "stepping", "planner_blocks", "arc_tolerance_mm",
        "junction_deviation_mm", "verbose_errors", "report_inches", "i2so", "spi",
        "sdcard", "ethernet", "kinematics", "axes", "control", "coolant", "probe",
        "macros", "extenders", "start", "parking", "user_outputs", "user_inputs",
        "enable_parking_override_control",
        # nguồn cắt khai ngay ở gốc, tên khối là loại nguồn cắt
        "Relay", "PWM", "OnOff", "NoSpindle"}
STEPPING = {"engine", "idle_ms", "pulse_us", "dir_delay_us", "disable_delay_us",
            "segments"}
ENGINES = {"Timed", "RMT", "I2S_STATIC", "I2S_STREAM"}
AXES = {"shared_stepper_disable_pin", "shared_stepper_reset_pin", "homing_runs"}
AXIS = {"steps_per_mm", "max_rate_mm_per_min", "acceleration_mm_per_sec2",
        "max_travel_mm", "soft_limits", "idle_disable", "homing", "motor0", "motor1"}
HOMING = {"cycle", "allow_single_axis", "positive_direction", "mpos_mm",
          "feed_mm_per_min", "seek_mm_per_min", "settle_ms", "seek_scaler",
          "feed_scaler"}
DRIVERS = {"standard_stepper", "tmc_2130", "tmc_5160", "tmc_2208", "tmc_2209",
           "dynamixel2", "rc_servo", "solenoid"}
MOTOR = {"limit_neg_pin", "limit_pos_pin", "limit_all_pin", "hard_limits",
         "pulloff_mm"} | DRIVERS
PROBE = {"pin", "toolsetter_pin", "check_mode_start", "hard_stop",
         "probe_hard_limit"}
CONTROL = {"safety_door_pin", "reset_pin", "feed_hold_pin", "cycle_start_pin",
           "fault_pin", "estop_pin", "homing_button_pin", "macro0_pin",
           "macro1_pin", "macro2_pin", "macro3_pin"}
START = {"must_home", "deactivate_parking", "check_limits"}
MACROS = {"macro0", "macro1", "macro2", "macro3", "startup_line0", "startup_line1",
          "name"}
SPINDLE = {"output_pin", "enable_pin", "direction_pin", "disable_with_s0",
           "s0_with_disable", "spinup_ms", "spindown_ms", "tool_num", "speed_map",
           "off_on_alarm", "atc", "m6_macro", "pwm_hz"}

# --- chân không dùng được, theo từng dòng chip -------------------------
BAD_PINS = {
    # flash; chân khởi động; phát xung lúc bật nguồn; UART0
    "esp32": {0, 1, 2, 3, 5, 6, 7, 8, 11, 12, 14, 15, 16, 17},
    # 19/20 USB-Serial-JTAG; 22..25 KHÔNG TỒN TẠI; 26..32 flash;
    # 33..37 PSRAM octal; 43/44 UART0; 0/3/45/46 chân khởi động;
    # 38/48 đèn RGB.  (21 là chân thường, dùng được.)
    "esp32s3": {19, 20} | set(range(22, 38)) | {0, 3, 43, 44, 45, 46, 48},
}
PIN_RE = re.compile(r"^\s*(\w*_pin|pin):\s*gpio\.(\d+)", re.M)


@unittest.skipIf(yaml is None, "cần pyyaml")
class TestFirmwareConfig(unittest.TestCase):
    def _load(self, key):
        with open(FILES[key], encoding="utf-8") as fh:
            text = fh.read()
        return text, yaml.safe_load(text)

    def test_yaml_doc_duoc(self):
        for key in FILES:
            _, doc = self._load(key)
            self.assertIsInstance(doc, dict, key)

    def test_moi_khoa_deu_hop_le(self):
        for key in FILES:
            _, doc = self._load(key)
            bad = [k for k in doc if k not in ROOT]
            self.assertFalse(bad, f"{key}: khoá gốc lạ {bad}")
            for section, allowed in (("stepping", STEPPING), ("probe", PROBE),
                                     ("control", CONTROL), ("start", START),
                                     ("macros", MACROS), ("Relay", SPINDLE)):
                bad = [k for k in (doc.get(section) or {}) if k not in allowed]
                self.assertFalse(bad, f"{key}.{section}: khoá lạ {bad}")
            for name, axis in doc["axes"].items():
                if not isinstance(axis, dict):
                    self.assertIn(name, AXES, f"{key}.axes.{name}")
                    continue
                bad = [k for k in axis if k not in AXIS]
                self.assertFalse(bad, f"{key}.{name}: khoá lạ {bad}")
                bad = [k for k in (axis.get("homing") or {}) if k not in HOMING]
                self.assertFalse(bad, f"{key}.{name}.homing: khoá lạ {bad}")
                for slot in ("motor0", "motor1"):
                    motor = axis.get(slot) or {}
                    bad = [k for k in motor if k not in MOTOR]
                    self.assertFalse(bad, f"{key}.{name}.{slot}: khoá lạ {bad}")

    def test_moi_truc_deu_co_driver_hop_le(self):
        """Khai nhầm tên driver thì trục không có chân STEP/DIR - đứng im."""
        for key in FILES:
            _, doc = self._load(key)
            for name, axis in doc["axes"].items():
                if not isinstance(axis, dict):
                    continue
                motor = axis.get("motor0") or {}
                found = [k for k in motor if k in DRIVERS]
                self.assertEqual(len(found), 1,
                                 f"{key}.{name}.motor0 phải có đúng một driver, "
                                 f"thấy {found or 'không có'}")
                pins = motor[found[0]]
                self.assertIn("step_pin", pins, f"{key}.{name}")
                self.assertIn("direction_pin", pins, f"{key}.{name}")

    def test_nguon_cat_khai_o_goc_khong_long_trong_spindle(self):
        """FluidNC không có khoá 'spindle' - lồng vào là mỏ không bao giờ kích."""
        for key in FILES:
            _, doc = self._load(key)
            self.assertNotIn("spindle", doc, f"{key}: nguồn cắt bị lồng sai chỗ")
            kinds = [k for k in ("Relay", "PWM", "OnOff", "NoSpindle") if k in doc]
            self.assertEqual(len(kinds), 1, f"{key}: phải khai đúng một nguồn cắt")
            self.assertIn("output_pin", doc[kinds[0]], key)

    def test_engine_hop_le(self):
        for key in FILES:
            _, doc = self._load(key)
            self.assertIn(doc["stepping"]["engine"], ENGINES, key)

    def test_khong_dung_chan_cam(self):
        for key, forbidden in BAD_PINS.items():
            text, _ = self._load(key)
            used = {int(m.group(2)) for m in PIN_RE.finditer(text)}
            clash = sorted(used & forbidden)
            self.assertFalse(clash, f"{key}: dùng chân cấm {clash}")

    def test_khong_trung_chan(self):
        for key in FILES:
            text, _ = self._load(key)
            seen = {}
            for m in PIN_RE.finditer(text):
                role, num = m.group(1), int(m.group(2))
                if role == "disable_pin":      # ENABLE dùng chung là đúng ý
                    continue
                self.assertNotIn(num, seen,
                                 f"{key}: gpio {num} dùng cho cả "
                                 f"{seen.get(num)} lẫn {role}")
                seen[num] = role

    def test_truc_xoay_khong_gioi_han_hanh_trinh(self):
        """Mâm cặp quay vô hạn: bật soft_limits là chạy được vài vòng rồi báo động."""
        for key in FILES:
            _, doc = self._load(key)
            a = doc["axes"]["a"]
            self.assertFalse(a.get("soft_limits", False), key)
            self.assertEqual(a.get("homing", {}).get("cycle", 0), 0, key)

    def test_z_ve_goc_truoc_tien(self):
        """Z phải về gốc trước, không thì mỏ quét ngang qua phôi."""
        for key in FILES:
            _, doc = self._load(key)
            cycles = {n: (ax.get("homing") or {}).get("cycle", 0)
                      for n, ax in doc["axes"].items() if isinstance(ax, dict)}
            self.assertEqual(cycles["z"], 1, f"{key}: {cycles}")
            for other in ("x", "y"):
                self.assertGreater(cycles[other], cycles["z"], key)

    def test_ro_le_mo_cat_khong_o_chan_khoi_dong(self):
        """Chân khởi động có thể phát xung lúc bật nguồn - mỏ phụt một nhát."""
        for key in FILES:
            _, doc = self._load(key)
            pin = str(doc["Relay"]["output_pin"])
            num = int(pin.split(".")[1].split(":")[0])
            self.assertNotIn(num, BAD_PINS[key], f"{key}: rơ-le ở chân {num}")


if __name__ == "__main__":
    unittest.main()
