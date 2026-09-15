"""Hoc bat chuoc (behavior cloning): day bo nao lam theo bo dieu khien viet tay.

Mo vong nay ra vi mo tu dau qua cham: bo nao co 3154 tham so, ma ES phai do
dam qua hang tram the he moi tu tim ra duoc phan xa "thay vuc thi lui".
Trong khi do ta DA CO mot bo luat chay duoc. Cho mang hoc theo no truoc (muc
tieu day dac, moi buoc deu co dap an, khong can chay mo phong lai) roi moi tha
vao tien hoa de no tu vuot thay.

    python3 -m train.imitate --episodes 16 --steps 400 --gens 300
"""
import argparse
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.env import ACT_DIM, OBS_DIM  # noqa: E402
from train.baseline import ReactiveController  # noqa: E402
from train.es import ES  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env  # noqa: E402

_X = _Y = _POL = None


def collect(n_eps, steps, stage=3, seed0=0):
    """Chay giao vien, ghi lai (cam bien -> lenh ga) tung buoc."""
    env = make_env(stage=stage, max_steps=steps)
    X = np.zeros((n_eps, steps, OBS_DIM), dtype=np.float32)
    Y = np.zeros((n_eps, steps, ACT_DIM), dtype=np.float32)
    teacher = ReactiveController(0, deterministic=True)
    for e in range(n_eps):
        obs = env.reset(seed0 + e)
        teacher.reset()
        for t in range(steps):
            a = teacher.act(obs)
            X[e, t] = obs
            Y[e, t] = a
            obs, _, done, _ = env.step(a)
            if done:
                obs = env.reset(seed0 + e + 10000)
                teacher.reset()
    return X, Y


def _init(X, Y, hidden):
    global _X, _Y, _POL
    _X, _Y = X, Y
    _POL = GRUPolicy(OBS_DIM, ACT_DIM, hidden)


def _loss(theta):
    _POL.set_params(theta)
    E, T, _ = _X.shape
    H = np.zeros((E, _POL.hidden), dtype=np.float32)
    err = 0.0
    for t in range(T):
        a, H = _POL.act_batch(_X[:, t], H)
        d = a - _Y[:, t]
        err += float(np.einsum("ij,ij->", d, d))
    return -err / (E * T * ACT_DIM)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=16)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--pop", type=int, default=64)
    ap.add_argument("--sigma", type=float, default=0.10)
    ap.add_argument("--lr", type=float, default=0.06)
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--out", default="runs/bc.npz")
    args = ap.parse_args()

    t0 = time.time()
    X, Y = collect(args.episodes, args.steps, args.stage)
    print("gom %d tap x %d buoc = %d mau (%.1fs)"
          % (args.episodes, args.steps, X.shape[0] * X.shape[1], time.time() - t0))
    print("ga trai/phai cua giao vien: trung binh %.2f / %.2f"
          % (Y[..., 0].mean(), Y[..., 1].mean()))

    pol = GRUPolicy(OBS_DIM, ACT_DIM, args.hidden, seed=0)
    es = ES(pol.get_params(), popsize=args.pop, sigma=args.sigma, lr=args.lr,
            weight_decay=0.002, seed=1)
    pool = Pool(args.jobs, initializer=_init, initargs=(X, Y, args.hidden)) \
        if args.jobs > 1 else None
    if pool is None:
        _init(X, Y, args.hidden)

    try:
        for g in range(args.gens):
            pop = es.ask()
            losses = pool.map(_loss, list(pop), chunksize=4) if pool else \
                [_loss(p) for p in pop]
            es.tell(losses)
            if g % 10 == 0 or g == args.gens - 1:
                _init(X, Y, args.hidden)
                cur = _loss(es.theta.astype(np.float32))
                print("gen %4d | sai so binh phuong %.4f | sigma %.3f | %.0fs"
                      % (g, -cur, es.sigma, time.time() - t0), flush=True)
                # luu lien tuc: hoc bat chuoc hay chung lai som, dung de mat
                pol.set_params(es.theta.astype(np.float32))
                pol.save(args.out, gen=g, stage=args.stage, bc=1)
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    pol.set_params(es.theta.astype(np.float32))
    pol.save(args.out, gen=args.gens, stage=args.stage, bc=1)
    print("da luu %s" % args.out)


if __name__ == "__main__":
    main()
