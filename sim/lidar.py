"""Mo hinh LiDAR Camsense X1/X2 (loai thao tu robot hut bui).

Thong so theo datasheet nha ban:
  - tan so lay mau 3000 Hz (3000 diem/giay)
  - tan so quay 5-8 Hz (thuong 7 Hz)
  - tam do 0.12 m den 8.0 m

Cach dung that: firmware doc lien tuc goi UART, gom du mot VONG roi moi xu ly.
Mo phong dung y het: cu 1/scan_hz giay thi sinh ra tron mot vong diem, giua hai
vong thi du lieu cu dan di. Vong dieu khien chay 20 Hz nen moi vong quet duoc
dung cho ~3 buoc dieu khien - do tre nay la that va policy phai chiu duoc no.
"""
import math

import numpy as np

SAMPLE_HZ = 3000.0      # diem/giay
RMIN = 0.12             # m
RMAX = 8.0              # m
SECTORS = 12            # so quat chia deu 360 do cho dau vao cua mang no-ron
                        # (LiDAR co ~460 diem/vong; nen lai 12 huong cho mang,
                        #  phan tinh vi de bo do hinh dang lo)

RANGE_NOISE = 0.010     # sai so tuyet doi (m)
RANGE_NOISE_REL = 0.012 # sai so ti le theo khoang cach
ANG_JITTER = 0.004      # rung goc (rad) ~ 0.23 do
DROP_RATE = 0.02        # ti le diem mat (be mat den, guong, goc toi)


class Lidar:
    def __init__(self, sectors=SECTORS):
        self.sectors = sectors
        self.scan_hz = 7.0
        self.reset(np.random.default_rng(0), 7.0)

    def reset(self, nprng, scan_hz=None):
        self.nprng = nprng
        self.scan_hz = float(scan_hz if scan_hz is not None
                             else nprng.uniform(5.0, 8.0))
        # Chot so diem moi vong thanh boi so cua so quat: nho vay chia diem vao
        # quat chi la mot phep xoay mang, khong phai 400 lan tinh chi so.
        per = max(1, int(round(SAMPLE_HZ / self.scan_hz / self.sectors)))
        self.n = per * self.sectors
        self.scan_hz = SAMPLE_HZ / self.n
        self.period = 1.0 / self.scan_hz
        self.base = np.linspace(-math.pi, math.pi, self.n,
                                endpoint=False).astype(np.float32)
        self.cos_base = np.cos(self.base)
        self.sin_base = np.sin(self.base)
        self.acc = float(nprng.uniform(0.0, self.period))
        self.r = np.zeros(self.n, dtype=np.float32)       # 0 = khong co phan hoi
        self.r_filled = np.full(self.n, RMAX, dtype=np.float32)
        self.scan_theta = 0.0
        self.age = 0.0
        self.scans = 0
        self.scans_new = True

    # ------------------------------------------------------------------- quet
    def step(self, robot, world, dt):
        """Tra ve True neu vua quet xong mot vong moi trong buoc nay."""
        self.acc += dt
        self.age += dt
        self.scans_new = False
        if self.acc < self.period:
            return False
        self.acc -= self.period
        self.scans_new = True
        self._scan(robot, world)
        self.age = 0.0
        self.scans += 1
        return True

    def _scan(self, robot, world):
        g = self.nprng
        ang = self.base + robot.theta
        if ANG_JITTER > 0.0:
            ang = ang + g.normal(0.0, ANG_JITTER, self.n).astype(np.float32)
        r = world.raycast_batch(robot.x, robot.y, ang, RMAX)
        sigma = RANGE_NOISE + RANGE_NOISE_REL * r
        r = r + (g.normal(0.0, 1.0, self.n).astype(np.float32) * sigma)
        # Camsense tra ve so nguyen MILIMET qua UART, khong phai so thuc.
        # Lam tron o day chu khong de den luc dong goi: nho vay mo phong va
        # bo nao chay tren laptop nhin thay DUNG MOT day so nhu nhau, va
        # phep doi chieu quan sat moi co y nghia.
        r = np.round(r * 1000.0) * 0.001
        bad = (r >= RMAX - 0.02) | (r < RMIN) | (g.random(self.n) < DROP_RATE)
        self.r = np.where(bad, 0.0, r)
        self.r_filled = np.where(bad, RMAX, r)
        # Ghi lai goc theo hệ ODOMETRY cua chinh xe, khong phai goc that.
        # Khu nhoe chi can biet xe da quay bao nhieu TRONG mot vong quet
        # (~143 ms); lay hieu hai so cung he thi phan troi tich luy tu triet
        # tieu. Tru goc-that cho goc-odometry thi ra dung luong troi - va do
        # la loi tôi vua mac phai: bo do bi lech dan theo thoi gian chay.
        self.scan_theta = robot.oth

    # -------------------------------------------------------------- doc du lieu
    def shift_for(self, theta_now):
        """So o phai xoay de bu phan xe da quay ke tu luc quet.

        Firmware that lam dung viec nay bang odometry / IMU (de-skew).
        """
        d = (self.scan_theta - theta_now) % (2.0 * math.pi)
        return int(round(d / (2.0 * math.pi) * self.n)) % self.n

    def sector_ranges(self, theta_now):
        """Khoang cach gan nhat trong tung quat, theo he toa do than xe."""
        sh = self.shift_for(theta_now)
        rr = np.roll(self.r_filled, sh)
        return rr.reshape(self.sectors, -1).min(axis=1)

    def scan_body(self, theta_now):
        """(goc theo than xe tang dan, khoang cach) - dau vao cho bo do hinh."""
        sh = self.shift_for(theta_now)
        return self.base, np.roll(self.r, sh)

    def points_xy(self, theta_now):
        a, r = self.scan_body(theta_now)
        ok = r > 0.0
        return (r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok]))
