"""Bo dieu khien viet tay (khong hoc) - moc so sanh cho AI, va la ban du phong
co the nap thang vao ESP32 neu mang no-ron loi.

Lam dung quy trinh da mo ta:
  di long nhong -> LiDAR thay cai HOC chu U -> vong ra doi dien cua hoc
  -> hong ngoai co tin hieu tram sac khong -> co thi chui vao, khong thi bo qua.
Khi pin yeu thi uu tien ve sac, va sac DAY roi moi di tiep.

Chi dung dung nhung tin hieu ma phan cung that co (xem OBS_NAMES trong env).
"""
import math
import random

from sim.dock_detector import MAX_CAND
from sim.env import OBS_NAMES, SEC_CLIP
from sim.lidar import SECTORS as NSEC

I_CLIFF_F = OBS_NAMES.index("cliff_front")
I_CLIFF_R = OBS_NAMES.index("cliff_rear")
I_CAND = OBS_NAMES.index("cand0_seen")     # MAX_CAND x (seen,sin,cos,dist,ysin,ycos)
CAND_W = 6
I_IR_CALL = OBS_NAMES.index("ir_call_L")     # L, C, R roi seen, delta
I_IR_CALL_SEEN = OBS_NAMES.index("ir_call_seen")
I_IR_DOCK = OBS_NAMES.index("ir_dock_L")
I_IR_DOCK_SEEN = OBS_NAMES.index("ir_dock_seen")
LEASH = 0.30            # bien an toan tut duoi muc nay thi bat dau quanh quan
                        # gan tram, cho pin tut du thap moi cam sac
I_MEM = OBS_NAMES.index("mem_known")       # known, sin, cos, dist, hsin, hcos
APPROACH = 0.40                            # doi truoc cua hoc bao xa (m)
I_BATT = OBS_NAMES.index("battery")
I_BATT_LOW = OBS_NAMES.index("battery_low")
I_MARGIN = OBS_NAMES.index("return_margin")

CRUISE = 0.60
BATT_FULL = 0.999       # phai doi SAC DAY HAN. Bo ra o 96% thi lan sac do
                        # khong duoc tinh - luat la phai len toi 100%.


def sec_idx(ang):
    return int((ang + math.pi) / (2.0 * math.pi) * NSEC) % NSEC


def sec_min(obs, lo_ang, hi_ang):
    a = lo_ang
    best = 1.0
    while a <= hi_ang + 1e-6:
        v = obs[sec_idx(a)]
        if v < best:
            best = v
        a += 2.0 * math.pi / NSEC
    return best * SEC_CLIP


class ReactiveController:
    """deterministic=True: bo het lua chon ngau nhien, de mang no-ron hoc theo.

    Neu giao vien thinh thoang queo trai thinh thoang queo phai trong cung mot
    tinh huong thi hoc sinh chi hoc duoc trung binh cua hai cai do - tuc la di
    thang vao vat can.
    """

    def __init__(self, seed=0, deterministic=False, force_low=False):
        self.rng = random.Random(seed)
        self.det = deterministic
        # force_low: luon coi nhu dang yeu pin, tuc la chi lo ve tram sac
        # chu khong di long nhong. Lop cuong ep ve sac dung o che do nay.
        self.force_low = force_low
        self.reset()

    def _coin(self, obs=None):
        if self.det:
            return 1.0 if (self.t // 97) % 2 == 0 else -1.0
        return self.rng.choice((-1.0, 1.0))

    def _steps(self, base, span):
        return base + (span // 2 if self.det else self.rng.randrange(span))

    def reset(self):
        self.queue = []
        self.turn_bias = 1.0
        self.t = 0
        self.prev_batt = 1.0
        self.charging = False
        self.verify = 0          # so buoc da doi hong ngoai tra loi
        self.skip = 0            # so buoc lo di ung vien (vua gap hoc moi nhu)
        self.entering = 0        # da cam ket chui vao, con bao nhieu buoc
        self.hold = 0            # con bao nhieu buoc phai dung yen ma nap dien
        self.hunt = 0            # con bao nhieu buoc con bam theo den goi
        self.hunt_bear = 0.0
        self.hunt_manh = 0.0

    def _turn(self, spin, steps, speed=0.5):
        self.queue = [(speed * spin, -speed * spin)] * steps

    @staticmethod
    def _ir_bearing(obs, base):
        """Doan huong den tu ba mat thu. None = khong thay gi.

        Mot mat thi chi biet co/khong; ba mat thi ti le cuong do giua chung
        cho ra goc. Day dung la cach robot hut bui that do huong ve tram.
        """
        tr, gi, ph = obs[base], obs[base + 1], obs[base + 2]
        tong = tr + gi + ph
        if tong < 1e-6:
            return None, 0.0
        return (tr - ph) / tong * 1.15, tong

    def _cands(self, obs):
        """(huong toi cua, khoang cach, huong truc hoc) - tat ca theo than xe."""
        out = []
        for i in range(MAX_CAND):
            b = I_CAND + CAND_W * i
            if obs[b] > 0.5:
                out.append((math.atan2(obs[b + 1], obs[b + 2]),
                            obs[b + 3] * SEC_CLIP,
                            math.atan2(obs[b + 4], obs[b + 5])))
        return out

    def _approach_point(self, bear, dist, yaw):
        """Diem doi truoc cua hoc, theo he than xe.

        Cua o `dist` met theo huong `bear`; truc hoc chi theo `yaw`. Lui
        nguoc truc ra APPROACH met thi duoc cho dung doi dien.
        """
        return (dist * math.cos(bear) - APPROACH * math.cos(yaw),
                dist * math.sin(bear) - APPROACH * math.sin(yaw))

    def act(self, obs):
        self.t += 1
        batt = obs[I_BATT]
        self.charging = batt > self.prev_batt + 1e-6
        self.prev_batt = batt

        # 0) Dang nap dien thi dung yen cho DAY roi moi di.
        # Phai BAM CHAT: toc do xe giam dan sau khi dung nen co vai buoc
        # khong nap duoc, neu buoc nao cung hoi lai thi xe ra vao lien tuc
        # (do duoc: 22 lan cam sac moi duoc 1 lan tinh diem).
        if self.charging:
            self.hold = 500
        if self.hold > 0 and batt < BATT_FULL:
            self.hold -= 1
            self.queue = []
            return (0.0, 0.0)
        if batt >= BATT_FULL:
            self.hold = 0

        # 1) Mep ban - cat ngang moi lenh khac
        if obs[I_CLIFF_F] > 0.5:
            spin = self._coin()
            self.queue = [(-0.7, -0.7)] * 10 + [(0.55 * spin, -0.55 * spin)] * 16
            return self.queue.pop(0)
        if obs[I_CLIFF_R] > 0.5:
            self.queue = [(0.6, 0.6)] * 6
            return self.queue.pop(0)
        if self.queue:
            return self.queue.pop(0)

        front = sec_min(obs, -0.4, 0.4)
        cands = self._cands(obs)
        # "Kinh nghiem": bien an toan am nghia la pin con lai khong du cho
        # quang duong ve tram nua - do chinh xe tu do hao pin moi met ma tinh.
        # Ve som mot chut bao gio cung re hon chet pin giua ban.
        # Khong ve som: luat chi tinh mot lan sac khi da tung tut duoi 20%.
        # Nen chi CAM SAC khi bien an toan bao phai ve, hoac cham san cung.
        margin = obs[I_MARGIN]
        low = self.force_low or margin < 0.05 or obs[I_BATT] < 0.13
        # ... nhung truoc do da phai bat dau quanh quan gan tram roi, khong
        # thi luc pin tut duoi 20%% xe dang o dau kia can nha va khong ve kip.
        leash = (not low) and margin < LEASH

        if self.skip > 0:
            self.skip -= 1
            cands = []
        if not low:
            self.entering = 0

        # 2a) Da cam ket chui vao thi CU THE MA VAO.
        # Diem doi truoc cua nam SAU lung khi da vao trong, nen neu buoc nao
        # cung tinh lai "minh co dung cho doi khong" thi xe se lui ra roi vao,
        # lui ra roi vao mai. Vao la vao.
        if self.entering > 0:
            self.entering -= 1
            if cands:
                bear, dist, yaw = min(cands, key=lambda c: c[1])
                turn = max(-0.20, min(0.20, 1.0 * yaw + 0.9 * bear))
            else:
                turn = 0.0
            return (0.26 - turn, 0.26 + turn)

        # 2) Pin yeu + dang thay cai hoc -> vong ra doi dien roi chui vao
        if low and cands:
            bear, dist, yaw = min(cands, key=lambda c: c[1])
            tx, ty = self._approach_point(bear, dist, yaw)
            off = math.hypot(tx, ty)
            ir = obs[I_IR_DOCK_SEEN] > 0.5

            if off > 0.14:
                # chua vao dung cho doi dien: di toi diem do da
                ang = math.atan2(ty, tx)
                turn = max(-0.5, min(0.5, 1.4 * ang))
                if abs(ang) > 1.0:
                    return (-0.45 * (1.0 if ang > 0 else -1.0),
                            0.45 * (1.0 if ang > 0 else -1.0))
                sp = 0.40 if off > 0.4 else 0.25
                return (sp - turn, sp + turn)

            # da doi dien cua hoc: canh truc cho thang
            if abs(yaw) > 0.06:
                sp = max(-0.42, min(0.42, 1.6 * yaw))
                return (-sp, sp)

            # 3) Thang truc roi moi hoi hong ngoai: that hay moi nhu?
            if not ir:
                self.verify += 1
                if self.verify > 26:
                    self.verify = 0
                    self.skip = 90      # hoc moi nhu - lo di mot luc
                    self.queue = [(-0.5, -0.5)] * 12
                    return self.queue.pop(0)
                return (0.0, 0.0)

            # 4) Co tin hieu - cam ket chui vao
            self.verify = 0
            self.entering = 160
            turn = max(-0.20, min(0.20, 1.0 * yaw + 0.9 * bear))
            return (0.26 - turn, 0.26 + turn)

        # 5) Pin yeu, khong thay hoc: di theo tri nho, nho ca huong truc
        if low and obs[I_MEM] > 0.5 and front > 0.35:
            md = obs[I_MEM + 3] * 3.0
            mb = math.atan2(obs[I_MEM + 1], obs[I_MEM + 2])
            mh = math.atan2(obs[I_MEM + 4], obs[I_MEM + 5])
            if md > 0.7:
                ang = mb                      # con xa: cu nham thang tram
            else:                             # gan roi: vong ra truoc cua
                tx = md * math.cos(mb) - APPROACH * math.cos(mh)
                ty = md * math.sin(mb) - APPROACH * math.sin(mh)
                ang = math.atan2(ty, tx)
            turn = max(-0.5, min(0.5, 1.2 * ang))
            return (0.42 - turn, 0.42 + turn)

        # 5) Thay den goi thi LAI VE PHIA NO, va BAM THEO.
        # Khong bam thi vo ich: xe thay den vai buoc, chua kip toi thi gap
        # cai ghe, ne xong la quen mat. Do duoc: thay den 7%% so buoc ma toi
        # noi 0/5 lan. Nho mot cai chot 220 buoc la khac han.
        if low:
            self.hunt = 0
        else:
            bear, manh = self._ir_bearing(obs, I_IR_CALL)
            if bear is not None and obs[I_IR_CALL_SEEN] > 0.5:
                self.hunt = 220
                self.hunt_bear = bear
                self.hunt_manh = manh
            if self.hunt > 0:
                self.hunt -= 1
                if front > 0.40:
                    turn = max(-0.45, min(0.45, 1.3 * self.hunt_bear))
                    sp = 0.50 if self.hunt_manh < 0.5 else 0.28
                    return (sp - turn, sp + turn)
                # bi chan thi xuong phan ne vat can - nhung VAN giu trang thai
                # san, ne xong quay lai duoi tiep

        # 5b) Pin da voi: keo ve gan tram roi tiep tuc di quanh do
        if leash and obs[I_MEM] > 0.5 and front > 0.35:
            md = obs[I_MEM + 3] * 3.0
            if md > 1.6:
                mb = math.atan2(obs[I_MEM + 1], obs[I_MEM + 2])
                turn = max(-0.5, min(0.5, 1.2 * mb))
                return (0.45 - turn, 0.45 + turn)

        # 6) Tranh vat can
        if front < 0.40:
            left = sec_min(obs, 0.4, 1.6)
            right = sec_min(obs, -1.6, -0.4)
            spin = -1.0 if left > right else 1.0
            if front < 0.20:
                self.queue = [(-0.6, -0.6)] * 6
            self._turn(spin, self._steps(8, 8))
            return self.queue.pop(0)

        # 7) Di long nhong
        if self.t % 140 == 0:
            self.turn_bias = self._coin()
        wobble = 0.10 * self.turn_bias * math.sin(self.t * 0.03)
        return (CRUISE - wobble, CRUISE + wobble)
