"""Bo nao cua xe: mot mang GRU nho chay bang numpy.

GRU (co trang thai an) rat quan trong o day: xe chi co MOT mat thu hong ngoai,
muon biet den phat tu huong nao thi phai xoay va NHO lai cuong do vua do duoc.
Mang thuan feed-forward khong lam duoc viec do.
"""
import numpy as np


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class GRUPolicy:
    def __init__(self, obs_dim, act_dim, hidden=16, seed=0):
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.hidden = hidden
        self.shapes = [
            ("Wz", (hidden, obs_dim)), ("Uz", (hidden, hidden)), ("bz", (hidden,)),
            ("Wr", (hidden, obs_dim)), ("Ur", (hidden, hidden)), ("br", (hidden,)),
            ("Wn", (hidden, obs_dim)), ("Un", (hidden, hidden)), ("bn", (hidden,)),
            ("Wo", (act_dim, hidden)), ("bo", (act_dim,)),
        ]
        self.sizes = [int(np.prod(s)) for _, s in self.shapes]
        self.n_params = int(sum(self.sizes))
        self.theta = self._init_theta(seed)
        self.set_params(self.theta)
        self.reset()

    def _init_theta(self, seed):
        rng = np.random.default_rng(seed)
        parts = []
        for (name, shape), n in zip(self.shapes, self.sizes):
            if name.startswith("b"):
                v = np.zeros(n, dtype=np.float32)
                if name == "bz":
                    v += -1.0     # mac dinh giu trang thai an (cong quen cham)
            elif name == "Wo":
                v = rng.normal(0.0, 0.10, n).astype(np.float32)
            else:
                fan_in = shape[1]
                v = rng.normal(0.0, 1.0 / np.sqrt(fan_in), n).astype(np.float32)
            parts.append(v)
        return np.concatenate(parts)

    # ------------------------------------------------------------------- params
    def set_params(self, theta):
        self.theta = np.asarray(theta, dtype=np.float32)
        p = {}
        i = 0
        for (name, shape), n in zip(self.shapes, self.sizes):
            p[name] = self.theta[i:i + n].reshape(shape)
            i += n
        self.p = p

    def get_params(self):
        return self.theta

    # ------------------------------------------------------------------ inference
    def reset(self):
        self.h = np.zeros(self.hidden, dtype=np.float32)

    def act(self, obs):
        p = self.p
        x = np.asarray(obs, dtype=np.float32)
        h = self.h
        z = sigmoid(p["Wz"] @ x + p["Uz"] @ h + p["bz"])
        r = sigmoid(p["Wr"] @ x + p["Ur"] @ h + p["br"])
        n = np.tanh(p["Wn"] @ x + r * (p["Un"] @ h) + p["bn"])
        h = (1.0 - z) * h + z * n
        self.h = h
        return np.tanh(p["Wo"] @ h + p["bo"])

    def act_batch(self, X, H):
        """Chay mot buoc cho nhieu tap song song. X: [E,obs], H: [E,hidden]."""
        p = self.p
        xz = X @ p["Wz"].T
        xr = X @ p["Wr"].T
        xn = X @ p["Wn"].T
        z = sigmoid(xz + H @ p["Uz"].T + p["bz"])
        r = sigmoid(xr + H @ p["Ur"].T + p["br"])
        n = np.tanh(xn + r * (H @ p["Un"].T) + p["bn"])
        H = (1.0 - z) * H + z * n
        return np.tanh(H @ p["Wo"].T + p["bo"]), H

    # ---------------------------------------------------------------- luu / doc
    def save(self, path, **meta):
        np.savez(path, theta=self.theta, obs_dim=self.obs_dim,
                 act_dim=self.act_dim, hidden=self.hidden,
                 **{k: np.asarray(v) for k, v in meta.items()})

    @staticmethod
    def load(path):
        d = np.load(path, allow_pickle=True)
        pol = GRUPolicy(int(d["obs_dim"]), int(d["act_dim"]), int(d["hidden"]))
        pol.set_params(d["theta"])
        meta = {k: d[k] for k in d.files if k not in
                ("theta", "obs_dim", "act_dim", "hidden")}
        return pol, meta
