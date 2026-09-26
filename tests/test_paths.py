"""Đường dẫn khi chạy từ bản cài (Program Files không ghi được, thư mục đang đứng tuỳ ý)."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from pipecut import paths
from pipecut.config import MachineProfile, find_profile, profile_search_paths


class TestPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.env = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        self.env.start()
        self.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        self.env.stop()
        self.tmp.cleanup()

    def test_ho_so_nguoi_dung_da_luu_dung_dau(self):
        """Lưu vào ~/.pipecut/machine.json thì lần sau mở phải nạp đúng cái đó,
        kể cả khi đang đứng trong thư mục cài có sẵn config/machine_default.json."""
        os.chdir(paths.resource_dir())                      # có config/machine_default.json
        p = MachineProfile()
        p.name = "máy của tôi"
        os.makedirs(paths.user_dir(), exist_ok=True)
        p.save(paths.user_profile_path())
        self.assertEqual(profile_search_paths()[0], os.path.abspath(paths.user_profile_path()))
        self.assertEqual(find_profile().name, "máy của tôi")

    def test_chay_tu_loi_tat_o_thu_muc_khac_van_tim_thay_ho_so_mau(self):
        os.chdir(self.home)                                 # không có config/ ở đây
        shipped = MachineProfile.load(paths.resource("config", "machine_default.json"))
        self.assertEqual(find_profile().name, shipped.name)

    def test_ban_dong_goi_lay_tai_nguyen_canh_tep_exe(self):
        fake_exe = os.path.join(self.home, "PipeCut Studio", "PipeCutStudio.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", fake_exe):
            self.assertTrue(paths.is_frozen())
            self.assertEqual(paths.resource_dir(), os.path.dirname(fake_exe))
            self.assertEqual(paths.resource("examples"),
                             os.path.join(os.path.dirname(fake_exe), "examples"))

    def test_thu_muc_luu_cua_nguoi_dung_ghi_duoc(self):
        self.assertTrue(paths.writable(paths.user_dir(create=True)))
        self.assertTrue(paths.writable(paths.documents_dir(create=True)))
        self.assertTrue(paths.documents_dir().startswith(self.home))


if __name__ == "__main__":
    unittest.main()
