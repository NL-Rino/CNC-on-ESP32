"""Bo dieu khien viet tay (khong hoc) - moc so sanh cho AI, va la ban du phong
co the nap thang vao ESP32 neu mang no-ron loi.

Lam dung quy trinh da mo ta:
  di long nhong -> LiDAR thay vat 15x15 cm -> quay dau lai nhin no
  -> hong ngoai co tin hieu tram sac khong -> co thi vo cam, khong thi bo qua.
Khi pin yeu thi uu tien ve sac, va sac DAY roi moi di tiep.

Chi dung dung nhung tin hieu ma phan cung that co (xem OBS_NAMES trong env).
"""
import math
import random

NSEC = 16
I_CLIFF_F, I_CLIFF_R = 16, 17
I_CAND = 18                      # 3 ung vien x (seen, sin, cos, dist)
I_IR_CALL, I_IR_CALL_SEEN = 30, 31
I_IR_DOCK, I_IR_DOCK_SEEN = 32, 33
I_MEM = 36                       # known, sin, cos, dist
I_BATT, I_BATT_LOW, I_MARGIN = 40, 41, 42
SEC_CLIP = 3.0

CRUISE = 0.60
BATT_FULL = 0.96


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
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.queue = []
        self.turn_bias = self.rng.choice((-1.0, 1.0))
        self.t = 0
        self.prev_batt = 1.0
        self.charging = False
        self.checking = 0        # so buoc con lai cua pha "quay dau xem IR"
        self.check_bear = 0.0

    def _turn(self, spin, steps, speed=0.5):
        self.queue = [(speed * spin, -speed * spin)] * steps

    def _cands(self, obs):
        out = []
        for i in range(3):
            b = I_CAND + 4 * i
            if obs[b] > 0.5:
                out.append((math.atan2(obs[b + 1], obs[b + 2]),
                            obs[b + 3] * SEC_CLIP))
        return out

    def act(self, obs):
        self.t += 1
        batt = obs[I_BATT]
        self.charging = batt > self.prev_batt + 1e-6
        self.prev_batt = batt

        # 0) Dang nap dien thi dung yen cho DAY roi moi di
        if self.charging and batt < BATT_FULL:
            self.queue = []
            return (0.0, 0.0)

        # 1) Mep ban - cat ngang moi lenh khac
        if obs[I_CLIFF_F] > 0.5:
            spin = self.rng.choice((-1.0, 1.0))
            self.queue = [(-0.7, -0.7)] * 10 + [(0.55 * spin, -0.55 * spin)] * 16
            return self.queue.pop(0)
        if obs[I_CLIFF_R] > 0.5:
            self.queue = [(0.6, 0.6)] * 6
            return self.queue.pop(0)
        if self.queue:
            return self.queue.pop(0)

        front = sec_min(obs, -0.4, 0.4)
        cands = self._cands(obs)
        low = obs[I_BATT_LOW] > 0.5 or obs[I_MARGIN] < 0.0

        # 2) Dang thay den tram sac va pin yeu -> vao cam
        if low and obs[I_IR_DOCK_SEEN] > 0.5:
            near = [c for c in cands if abs(c[0]) < 0.9]
            bear = near[0][0] if near else 0.0
            dist = near[0][1] if near else 1.0
            if dist < 0.45:
                speed = 0.16
            elif dist < 0.9:
                speed = 0.30
            else:
                speed = 0.45
            turn = max(-0.45, min(0.45, 1.3 * bear))
            return (speed - turn, speed + turn)

        # 3) Pin yeu: thay vat dung kich thuoc -> quay dau lai hoi hong ngoai
        if low and self.checking > 0:
            self.checking -= 1
            turn = max(-0.5, min(0.5, 1.5 * self.check_bear))
            return (-turn, turn)
        if low and cands:
            bear, dist = min(cands, key=lambda c: c[1])
            if dist < 2.0 and abs(bear) > 0.25:
                self.check_bear = bear
                self.checking = 12
                turn = max(-0.5, min(0.5, 1.5 * bear))
                return (-turn, turn)
            if dist < 2.0 and front > 0.35:
                turn = max(-0.4, min(0.4, 1.2 * bear))
                return (0.40 - turn, 0.40 + turn)

        # 4) Pin yeu, khong thay gi: di theo tri nho vi tri tram sac
        if low and obs[I_MEM] > 0.5 and front > 0.35:
            bear = math.atan2(obs[I_MEM + 1], obs[I_MEM + 2])
            turn = max(-0.5, min(0.5, 1.2 * bear))
            return (0.45 - turn, 0.45 + turn)

        # 5) Co den goi thi toi
        if not low and obs[I_IR_CALL_SEEN] > 0.5 and front > 0.35:
            speed = 0.55 if obs[I_IR_CALL] < 0.6 else 0.35
            return (speed, speed)

        # 6) Tranh vat can
        if front < 0.40:
            left = sec_min(obs, 0.4, 1.6)
            right = sec_min(obs, -1.6, -0.4)
            spin = -1.0 if left > right else 1.0
            if front < 0.20:
                self.queue = [(-0.6, -0.6)] * 6
            self._turn(spin, 8 + self.rng.randrange(8))
            return self.queue.pop(0)

        # 7) Di long nhong
        if self.t % 140 == 0:
            self.turn_bias = self.rng.choice((-1.0, 1.0))
        wobble = 0.10 * self.turn_bias * math.sin(self.t * 0.03)
        return (CRUISE - wobble, CRUISE + wobble)
