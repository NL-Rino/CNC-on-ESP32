"""Evolution Strategies (OpenAI-ES) - "nuoi" bo nao bang chon loc tu nhien.

Khong can dao ham: moi the he sinh ra POP ca the bang cach cong nhieu Gauss
vao bo gen hien tai (lay mau doi xung +/- de giam phuong sai), cham diem tung
ca the trong mo phong, roi dich bo gen theo huong cac ca the diem cao.
Rat hop voi bai toan nay vi phan thuong thua va policy co trang thai an.
"""
import numpy as np


def rank_transform(fitness):
    """Chuan hoa theo thu hang -> ES khong bi mot ca the diem khung lam lech."""
    n = len(fitness)
    order = np.argsort(np.argsort(np.asarray(fitness, dtype=np.float64)))
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

    def tell(self, fitness):
        f = np.asarray(fitness, dtype=np.float64)
        shaped = rank_transform(f)
        plus = shaped[0::2]
        minus = shaped[1::2]
        grad = (plus - minus) @ self.eps / (self.popsize * self.sigma)
        grad -= self.weight_decay * self.theta
        self.theta += self.opt.step(grad)
        self.sigma = max(self.sigma_min, self.sigma * self.sigma_decay)
        self.gen += 1
        return {"gen": self.gen, "sigma": self.sigma,
                "grad_norm": float(np.linalg.norm(grad))}
