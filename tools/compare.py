"""So sanh bo nao da hoc voi bo dieu khien viet tay tren CUNG bo canh.

    python3 tools/compare.py runs/car/best.npz --episodes 30
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.baseline import ReactiveController  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env, rollout  # noqa: E402

FIELDS = [
    ("return", "diem", "%8.1f"),
    ("fell", "roi khoi ban %", "%8.0f"),
    ("flat", "het pin %", "%8.0f"),
    ("arrivals", "lan toi den goi", "%8.2f"),
    ("charged", "pin nap duoc", "%8.3f"),
    ("full_charges", "lan sac day", "%8.2f"),
    ("distance", "quang duong m", "%8.1f"),
    ("bumps", "buoc va cham", "%8.1f"),
    ("cells", "o luoi da di", "%8.1f"),
]


def run(policy, episodes, seed0, stage, max_steps):
    env = make_env(stage=stage, max_steps=max_steps)
    rows = [rollout(policy, env, seed0 + i)[1] for i in range(episodes)]
    out = {}
    for k, _, _ in FIELDS:
        vals = [float(r[k]) for r in rows]
        out[k] = statistics.mean(vals) * (100 if k in ("fell", "flat") else 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy", nargs="?", default="runs/car/best.npz")
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--seed", type=int, default=5000)
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=5000)
    args = ap.parse_args()

    pol, meta = GRUPolicy.load(args.policy)
    ai = run(pol, args.episodes, args.seed, args.stage, args.max_steps)
    bl = run(ReactiveController(0), args.episodes, args.seed, args.stage, args.max_steps)

    print("%d tap, cung seed cho ca hai (stage %d)\n" % (args.episodes, args.stage))
    print("%-18s %10s %10s" % ("", "AI da hoc", "viet tay"))
    for k, label, fmt in FIELDS:
        print(("%-18s " + fmt + "   " + fmt) % (label, ai[k], bl[k]))


if __name__ == "__main__":
    main()
