"""Bo dieu khien viet tay (khong hoc) - moc so sanh cho AI.

Cung la ban du phong co the nap thang vao ESP32 neu mang no-ron loi.
Chi dung dung nhung tin hieu ma phan cung that co.

Bai hoc quan trong: may bo phan ung kieu nay luon can "cam ket" theo mot
huong trong vai chuc mili giay, neu khong nhieu cam bien se lam no rung
lac tai cho (do la cai ma mang hoc duoc se tu xu ly bang trang thai an).
"""
import math
import random

I_SON = slice(0, 5)
I_CLIFF_F, I_CLIFF_R = 5, 6
I_IR_CALL, I_IR_CALL_SEEN, I_IR_DOCK, I_IR_DOCK_SEEN = 7, 8, 9, 10
I_BATT, I_BATT_LOW = 13, 14

CRUISE = 0.62


class ReactiveController:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.queue = []          # chuoi lenh dang cho chay (cam ket)
        self.best_ir = 0.0
        self.turn_bias = self.rng.choice((-1.0, 1.0))
        self.t = 0

    # spin > 0 -> queo phai, spin < 0 -> queo trai
    def _turn(self, spin, steps, speed=0.5):
        self.queue = [(speed * spin, -speed * spin)] * steps

    def act(self, obs):
        self.t += 1
        left90, left45, front, right45, right90 = obs[I_SON]
        cliff_f, cliff_r = obs[I_CLIFF_F], obs[I_CLIFF_R]
        ir_call, ir_dock = obs[I_IR_CALL], obs[I_IR_DOCK]
        seen_call, seen_dock = obs[I_IR_CALL_SEEN], obs[I_IR_DOCK_SEEN]

        # 1) Mep ban - uu tien cao nhat, cat ngang moi lenh khac
        if cliff_f > 0.5:
            spin = self.rng.choice((-1.0, 1.0))
            self.queue = [(-0.7, -0.7)] * 10
            self.queue += [(0.55 * spin, -0.55 * spin)] * 16
            return self.queue.pop(0)
        if cliff_r > 0.5:
            self.queue = [(0.6, 0.6)] * 6
            return self.queue.pop(0)
        if self.queue:
            return self.queue.pop(0)

        # 2) Bam hong ngoai: den goi truoc, tram sac khi pin yeu
        target = 0.0
        if seen_call > 0.5:
            target = ir_call
        elif seen_dock > 0.5 and obs[I_BATT_LOW] > 0.5:
            target = ir_dock
        if target > 0.05 and front > 0.32:
            speed = 0.55 if target < 0.6 else 0.30
            delta = target - self.best_ir
            self.best_ir = max(self.best_ir * 0.98, target)
            turn = 0.0 if delta > -0.01 else 0.22 * self.turn_bias
            return (speed - turn, speed + turn)
        self.best_ir *= 0.98

        # 3) Tranh vat can - cam ket queo mot huong trong ~0.5 giay
        if front < 0.34 or left45 < 0.24 or right45 < 0.24:
            spin = -1.0 if (left45 + left90) > (right45 + right90) else 1.0
            steps = 8 + self.rng.randrange(8)
            if front < 0.16:
                self.queue = [(-0.6, -0.6)] * 6
            self._turn(spin, steps)
            return self.queue.pop(0)

        # 4) Di long nhong
        if self.t % 140 == 0:
            self.turn_bias = self.rng.choice((-1.0, 1.0))
        wobble = 0.10 * self.turn_bias * math.sin(self.t * 0.03)
        return (CRUISE - wobble, CRUISE + wobble)
