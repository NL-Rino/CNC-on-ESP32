"""Kiểm thử giao thức FluidNC, bộ giả lập và cơ chế nạp lệnh."""

import time
import unittest

from pipecut import protocol as proto
from pipecut.config import MachineProfile
from pipecut.controller import DeviceController
from pipecut.gcode import build_program
from pipecut.jobs import Job
from pipecut.simulator import FluidNCSimulator
from pipecut.transport import LoopbackTransport, list_ports


class TestProtocol(unittest.TestCase):
    def test_phan_tich_bao_cao_trang_thai_day_du(self):
        line = ("<Run|MPos:12.500,1.000,3.000,90.250|FS:1200,1000"
                "|WCO:10.000,0.000,1.000,0.000|Bf:12,110|Ov:110,100,100|Pn:XP|Ln:42>")
        st = proto.parse_status(line, ["X", "Y", "Z", "A"])
        self.assertEqual(st.state, "Run")
        self.assertEqual(st.state_vi, "Đang chạy")
        self.assertAlmostEqual(st.mpos["A"], 90.25)
        self.assertAlmostEqual(st.wpos["X"], 2.5)      # tự suy ra từ MPos - WCO
        self.assertEqual((st.planner_free, st.rx_free), (12, 110))
        self.assertEqual(st.overrides, (110, 100, 100))
        self.assertEqual(st.line, 42)
        self.assertTrue(st.is_moving)

    def test_trang_thai_co_trang_thai_con(self):
        st = proto.parse_status("<Hold:0|MPos:0.000,0.000,0.000,0.000>")
        self.assertEqual(st.state, "Hold")
        self.assertEqual(st.substate, 0)

    def test_wpos_thay_cho_mpos(self):
        st = proto.parse_status("<Idle|WPos:1.000,2.000,3.000,4.000|WCO:1.000,0.000,0.000,0.000>",
                                ["X", "Y", "Z", "A"])
        self.assertAlmostEqual(st.mpos["X"], 2.0)

    def test_phan_loai_phan_hoi(self):
        cases = {
            "ok": "ok", "error:22": "error", "ALARM:1": "alarm",
            "<Idle|MPos:0.000,0.000>": "status", "[MSG:INFO]": "message",
            "$100=80.000": "setting", "Grbl 1.1f ['$' for help]": "welcome",
        }
        for text, kind in cases.items():
            self.assertEqual(proto.parse_response(text).kind, kind, text)

    def test_thong_diep_loi_tieng_viet(self):
        r = proto.parse_response("error:22")
        self.assertIn("F", r.message_vi)
        self.assertTrue(r.is_ack)
        a = proto.parse_response("ALARM:2")
        self.assertIn("hành trình mềm", a.message_vi)
        self.assertFalse(a.is_ack)

    def test_lenh_jog(self):
        cmd = proto.jog_command({"X": 10.0, "A": -5.0}, 1500.0)
        self.assertTrue(cmd.startswith("$J=G91 G21"))
        self.assertIn("X10.000", cmd)
        self.assertIn("A-5.000", cmd)
        self.assertIn("F1500", cmd)
        self.assertIn("G90", proto.jog_command({"X": 1.0}, 100.0, relative=False))

    def test_danh_sach_cong_luon_co_may_ao(self):
        self.assertIn("GIA-LAP", [p for p, _ in list_ports()])


class TestSimulator(unittest.TestCase):
    def setUp(self):
        self.sim = FluidNCSimulator(axes="XYZA", time_scale=500.0)
        self.t = LoopbackTransport(self.sim)
        self.t.open()
        self.t.read(400)

    def _send(self, *lines):
        for l in lines:
            self.t.write((l + "\n").encode())
        return self._drain()

    def _drain(self, seconds=0.6):
        out = ""
        end = time.time() + seconds
        while time.time() < end:
            out += self.t.read(4000).decode()
            if self.sim.state == "Idle" and not self.sim.queue:
                out += self.t.read(4000).decode()
                break
            time.sleep(0.005)
        return out

    def test_chay_lenh_va_tra_ok(self):
        out = self._send("G21", "G90", "G1 X20 A90 F2000")
        self.assertEqual(out.count("ok"), 3)
        self.assertAlmostEqual(self.sim.pos["X"], 20.0, places=3)
        self.assertAlmostEqual(self.sim.pos["A"], 90.0, places=3)

    def test_di_chuyen_tuong_doi(self):
        self._send("G90", "G0 X10", "G91", "G0 X5", "G90")
        self.assertAlmostEqual(self.sim.pos["X"], 15.0, places=3)

    def test_bao_cao_trang_thai(self):
        self.t.write(b"?")
        report = self.t.read(400).decode().strip()
        st = proto.parse_status(report, ["X", "Y", "Z", "A"])
        self.assertIsNotNone(st)
        self.assertEqual(st.state, "Idle")

    def test_tam_dung_va_chay_tiep(self):
        self.sim.time_scale = 1.0
        self.t.write(b"G1 X500 F100\n")
        self.t.read(100)
        self.sim.tick()
        self.t.write(b"!")
        self.assertEqual(self.sim.state, "Hold")
        self.t.write(b"~")
        self.assertIn(self.sim.state, ("Run", "Idle"))

    def test_bao_dong_chan_lenh_g_code(self):
        self.sim.raise_alarm(1)
        out = self._send("G0 X10")
        self.assertIn("error:9", out)

    def test_ve_goc_va_mo_khoa(self):
        self._send("G0 X50")
        self.sim.raise_alarm(1)
        self._send("$X")
        self.assertIsNone(self.sim.alarm)
        self._send("$H")
        self.assertAlmostEqual(self.sim.pos["X"], 0.0)


class TestStreaming(unittest.TestCase):
    def setUp(self):
        self.profile = MachineProfile()
        self.profile.connection.simulator_speed = 400.0
        job = Job(name="kiem-thu")
        job.add("hole", diameter=25.0, x=80.0)
        job.add("slot", x=140.0, theta=90.0, length=40.0, width_deg=60.0, corner=4.0)
        job.add("cutoff", x=220.0, angle=25.0)
        tp, _ = job.build_toolpath(self.profile)
        self.lines = build_program(self.profile, tp).stream_lines()
        self.controller = DeviceController(self.profile)

    def tearDown(self):
        try:
            self.controller.disconnect()
        except Exception:
            pass

    def test_nap_het_chuong_trinh_va_khong_tran_bo_dem(self):
        peak = [0]
        c = self.controller

        def watch(_pr):
            with c._lock:
                peak[0] = max(peak[0], c._pending_bytes)

        c.on_progress = watch
        c.connect(port="GIA-LAP")
        time.sleep(0.1)
        c.start_job(self.lines)
        end = time.time() + 60
        while c.progress.running and time.time() < end:
            time.sleep(0.05)
        self.assertFalse(c.progress.running)
        self.assertEqual(c.progress.acked, len(self.lines))
        self.assertEqual(c.progress.errors, [])
        limit = self.profile.connection.rx_buffer - 1
        self.assertLessEqual(peak[0], limit)         # không bao giờ tràn
        self.assertGreater(peak[0], limit * 0.5)     # nhưng vẫn luôn nạp đầy bộ đệm

    def test_dung_giua_chung(self):
        c = self.controller
        self.profile.connection.simulator_speed = 1.0   # chạy thời gian thực để kịp bấm dừng
        c.connect(port="GIA-LAP")
        time.sleep(0.1)
        c.start_job(self.lines)
        time.sleep(0.2)
        c.stop_job()
        time.sleep(0.1)
        self.assertFalse(c.progress.running)
        self.assertLess(c.progress.acked, len(self.lines))

    def test_loi_cu_phap_lam_dung_chuong_trinh(self):
        c = self.controller
        events = []
        c.on_event = lambda k, t: events.append(k)
        c.connect(port="GIA-LAP")
        time.sleep(0.1)
        sim = c.transport.device
        sim.raise_alarm(2)          # máy báo động -> mọi lệnh G-code bị từ chối
        c.start_job(self.lines)
        end = time.time() + 20
        while c.progress.running and time.time() < end:
            time.sleep(0.05)
        self.assertFalse(c.progress.running)
        self.assertTrue(c.progress.errors)
        self.assertIn("error", events)

    def test_lenh_nguoi_dung_duoc_uu_tien_hon_chuong_trinh(self):
        c = self.controller
        c.connect(port="GIA-LAP")
        time.sleep(0.1)
        sent = []
        c.on_line = lambda text, d: sent.append(text) if d == "tx" else None
        c.start_job(self.lines)
        c.send("G4 P0", front=True)
        end = time.time() + 60
        while c.progress.running and time.time() < end:
            time.sleep(0.05)
        self.assertIn("G4 P0", sent)
        # lệnh chen ngang không được tính vào tiến độ chương trình
        self.assertEqual(c.progress.acked, len(self.lines))


if __name__ == "__main__":
    unittest.main()


class TestLanTransport(unittest.TestCase):
    """Giao tiếp với FluidNC qua mạng LAN (cổng telnet), dùng socket thật."""

    def setUp(self):
        from pipecut.simulator import FluidNCServer

        self.profile = MachineProfile()
        self.profile.pipe.shape = "square"
        self.profile.pipe.width = 50.0
        cross = self.profile.axis("cross")
        cross.min_travel, cross.max_travel = -100.0, 100.0
        self.sim = FluidNCSimulator(axes="".join(self.profile.letters),
                                    rx_buffer=self.profile.connection.rx_buffer,
                                    time_scale=300.0)
        self.server = FluidNCServer(self.sim, "127.0.0.1", 0)
        self.port = self.server.start()
        self.controller = DeviceController(self.profile)

    def tearDown(self):
        try:
            self.controller.disconnect()
        finally:
            self.server.stop()

    def test_nhan_dien_dia_chi_mang(self):
        from pipecut.transport import parse_address

        self.assertEqual(parse_address("192.168.1.50"), ("192.168.1.50", 23))
        self.assertEqual(parse_address("192.168.1.50:2323"), ("192.168.1.50", 2323))
        self.assertEqual(parse_address("fluidnc.local"), ("fluidnc.local", 23))
        self.assertIsNone(parse_address("COM7"))
        self.assertIsNone(parse_address("/dev/ttyUSB0"))
        self.assertIsNone(parse_address("GIA-LAP"))

    def test_loc_chuoi_thuong_luong_telnet(self):
        from pipecut.transport import _strip_telnet

        self.assertEqual(_strip_telnet(b"ok\r\n"), b"ok\r\n")
        # IAC DO/WILL ... phải bị bỏ, dữ liệu thật giữ nguyên
        self.assertEqual(_strip_telnet(b"\xff\xfd\x18ok\r\n"), b"ok\r\n")
        self.assertEqual(_strip_telnet(b"a\xff\xffb"), b"a\xffb")

    def test_nap_tron_ven_mot_chuong_trinh_qua_mang(self):
        job = Job(name="qua-mang")
        job.add("cutoff", x=250.0, angle=0.0)
        tp, _w = job.build_toolpath(self.profile)
        lines = build_program(self.profile, tp).stream_lines()

        c = self.controller
        c.connect(port=f"127.0.0.1:{self.port}")
        self.assertTrue(c.is_connected)
        self.assertIn("LAN", c.transport.description)
        time.sleep(0.3)
        c.start_job(lines)
        end = time.time() + 60
        while c.progress.running and time.time() < end:
            time.sleep(0.05)
        self.assertFalse(c.progress.running)
        self.assertEqual(c.progress.acked, len(lines))
        self.assertEqual(c.progress.errors, [])
        # máy ảo phải thực sự chạy tới cuối chương trình
        self.assertGreater(abs(self.sim.pos["A"]), 300.0)

    def test_lay_duoc_bao_cao_trang_thai_qua_mang(self):
        c = self.controller
        c.connect(port=f"127.0.0.1:{self.port}")
        end = time.time() + 5
        while c.status is None and time.time() < end:
            time.sleep(0.05)
        self.assertIsNotNone(c.status)
        self.assertIn(c.status.state, ("Idle", "Run", "Jog"))
        self.assertIn(self.profile.letter("along"), c.status.mpos)

    def test_jog_va_lenh_thoi_gian_thuc_qua_mang(self):
        c = self.controller
        c.connect(port=f"127.0.0.1:{self.port}")
        time.sleep(0.2)
        c.jog({self.profile.letter("along"): 25.0}, 1000.0)
        end = time.time() + 5
        while abs(self.sim.pos["Y"]) < 24.0 and time.time() < end:
            time.sleep(0.05)
        self.assertAlmostEqual(self.sim.pos["Y"], 25.0, delta=0.5)
