"""Evolution Strategies (OpenAI-ES) - "nuoi" bo nao bang chon loc tu nhien.

Khong can dao ham: moi the he sinh ra POP ca the bang cach cong nhieu Gauss
vao bo gen hien tai (lay mau doi xung +/- de giam phuong sai), cham diem tung
ca the trong mo phong, roi dich bo gen theo huong cac ca the diem cao.
Rat hop voi bai toan nay vi phan thuong thua va policy co trang thai an.
"""
import json

import numpy as np


def rank_transform(fitness):
    """Chuan hoa theo thu hang -> ES khong bi mot ca the diem khung lam lech.

    Ca quan the diem BANG NHAU thi phai tra ve 0 het. Truoc day khong:
    argsort cua mot day bang nhau tra ve dung thu tu chi so, nen ca the chi
    so chan luon "thang" ca the chi so le - ES nhan mot gradient co he thong
    tu hu khong va di lang thang. Day chinh la thu da pha hong mot phien
    chay 5.900 the he.
    """
    f = np.asarray(fitness, dtype=np.float64)
    n = f.size
    spread = float(f.max() - f.min())
    if spread <= 1e-9 * max(1.0, abs(float(f.mean()))):
        return np.zeros(n)
    order = np.argsort(np.argsort(f))
    ranks = order / max(n - 1, 1) - 0.5
    std = ranks.std()
    return ranks / (std + 1e-8)


class Adam:
    def __init__(self, n, lr=0.03, b1=0.9, b2=0.999, eps=1e-8):
        self.m = np.zeros(n, dtype=np.float64)
        self.v = np.zeros(n, dtype=np.float64)
        self.lr = lr
        self.b1 = b1
        self.b2 = b2
        self.eps = eps
        self.t = 0

    def step(self, grad):
        self.t += 1
        self.m = self.b1 * self.m + (1 - self.b1) * grad
        self.v = self.b2 * self.v + (1 - self.b2) * grad * grad
        mhat = self.m / (1 - self.b1 ** self.t)
        vhat = self.v / (1 - self.b2 ** self.t)
        return self.lr * mhat / (np.sqrt(vhat) + self.eps)


class ES:
    """popsize phai la so chan: moi cap la mot mau doi xung (+eps, -eps)."""

    def __init__(self, theta, popsize=64, sigma=0.08, lr=0.03,
                 weight_decay=0.005, sigma_decay=0.999, sigma_min=0.02, seed=0):
        # weight_decay o day la kieu TACH ROI (AdamW). Cong thang vao gradient
        # thi Adam chuan hoa luon ca no, nen luc can ghim nhat lai khong ghim
        # duoc - trong so cu the phinh dan cho toi khi tanh bao hoa va bo nao
        # tra ve (+1,+1) voi MOI dau vao. Da thay chuyen do that: mot phien
        # chay den the he 7578 thi |theta| trung binh len 2.2, dinh 10.1, va
        # ca 48 ca the cham diem giong het nhau.
        assert popsize % 2 == 0, "popsize phai chan"
        self.theta = np.asarray(theta, dtype=np.float64).copy()
        self.n = self.theta.size
        self.popsize = popsize
        self.sigma = sigma
        self.sigma_decay = sigma_decay
        self.sigma_min = sigma_min
        self.weight_decay = weight_decay
        self.opt = Adam(self.n, lr=lr)
        self.rng = np.random.default_rng(seed)
        self.gen = 0

    def ask(self):
        half = self.popsize // 2
        self.eps = self.rng.standard_normal((half, self.n))
        pop = np.empty((self.popsize, self.n))
        pop[0::2] = self.theta + self.sigma * self.eps
        pop[1::2] = self.theta - self.sigma * self.eps
        return pop.astype(np.float32)

    # ------------------------------------------------------------ luu / nap
    def state_dict(self):
        """Toan bo thu can de chay tiep y het cho vua dung.

        Khong chi theta: sigma da giam den dau, Adam da tich luy bao nhieu
        dong luong, bo sinh so ngau nhien dang o dau. Nap lai ma thieu may
        thu nay thi tien hoa bi giat lui - khong mat het, nhung mat cong.
        """
        return {
            "es_theta": self.theta,
            "es_sigma": np.float64(self.sigma),
            "es_gen": np.int64(self.gen),
            "es_popsize": np.int64(self.popsize),
            "opt_m": self.opt.m,
            "opt_v": self.opt.v,
            "opt_t": np.int64(self.opt.t),
            "opt_lr": np.float64(self.opt.lr),
            "rng_state": np.str_(json.dumps(
                self.rng.bit_generator.state, default=str)),
        }

    def load_state(self, d):
        self.theta = np.asarray(d["es_theta"], dtype=np.float64).copy()
        self.n = self.theta.size
        self.sigma = float(d["es_sigma"])
        self.gen = int(d["es_gen"])
        self.opt.m = np.asarray(d["opt_m"], dtype=np.float64).copy()
        self.opt.v = np.asarray(d["opt_v"], dtype=np.float64).copy()
        self.opt.t = int(d["opt_t"])
        self.opt.lr = float(d["opt_lr"])
        try:
            st = json.loads(str(d["rng_state"]))
            st["bit_generator"] = str(st["bit_generator"])
            if isinstance(st.get("state"), dict):
                for k in ("state", "inc"):
                    if k in st["state"]:
                        st["state"][k] = int(st["state"][k])
            self.rng.bit_generator.state = st
        except Exception:      # noqa: BLE001 - thieu no chi kem ngau nhien
            pass

    def tell(self, fitness):
        f = np.asarray(fitness, dtype=np.float64)
        shaped = rank_transform(f)
        plus = shaped[0::2]
        minus = shaped[1::2]
        grad = (plus - minus) @ self.eps / (self.popsize * self.sigma)
        self.theta += self.opt.step(grad)
        if self.weight_decay:
            self.theta *= 1.0 - self.opt.lr * self.weight_decay
        self.spread = float(np.max(f) - np.min(f))
        self.sat = float(np.abs(self.theta).mean())
        self.sigma = max(self.sigma_min, self.sigma * self.sigma_decay)
        self.gen += 1
        return {"gen": self.gen, "sigma": self.sigma,
                "spread": self.spread, "theta_abs": self.sat,
                "grad_norm": float(np.linalg.norm(grad))}
