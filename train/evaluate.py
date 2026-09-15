"""Cham diem mot bo nao da huan luyen, xem lai bang ASCII hoac xuat file replay.

Vi du:
    python3 -m train.evaluate --policy runs/car/best.npz --episodes 20
    python3 -m train.evaluate --policy runs/car/best.npz --ascii --seed 7
    python3 -m train.evaluate --policy runs/car/best.npz --record demo.json
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.render import print_frame  # noqa: E402
from train.baseline import ReactiveController  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env, rollout  # noqa: E402


def load_policy(path, baseline=False, seed=0):
    if baseline or path is None:
        return ReactiveController(seed), "baseline (viet tay)"
    pol, meta = GRUPolicy.load(path)
    tag = "%s (gen=%s, stage=%s)" % (path, meta.get("gen", "?"), meta.get("stage", "?"))
    return pol, tag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="runs/car/best.npz")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=1300)
    ap.add_argument("--ascii", action="store_true", help="xem truc tiep tren terminal")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--record", default=None, help="luu cac tap dau ra file JSON")
    ap.add_argument("--record-episodes", type=int, default=3)
    args = ap.parse_args()

    pol, tag = load_policy(args.policy, args.baseline, args.seed)
    print("policy:", tag)

    if args.ascii:
        env = make_env(stage=args.stage, max_steps=args.max_steps)
        delay = 1.0 / args.fps
        def cb(e):
            print_frame(e)
            time.sleep(delay)
        r, st = rollout(pol, env, args.seed, render_cb=cb)
        print("return %.1f | %s" % (r, st))
        return

    env = make_env(stage=args.stage, max_steps=args.max_steps,
                   record=bool(args.record))
    rows = []
    recs = []
    for i in range(args.episodes):
        env.cfg.record = bool(args.record) and i < args.record_episodes
        r, st = rollout(pol, env, args.seed + i)
        rows.append(st)
        if env.cfg.record:
            rec = env.episode_record()
            rec["stats"] = {k: (round(v, 3) if isinstance(v, float) else v)
                            for k, v in st.items()}
            rec["seed"] = args.seed + i
            recs.append(rec)
    if args.record:
        with open(args.record, "w") as f:
            json.dump({"policy": tag, "episodes": recs}, f)
        print("da luu replay ->", args.record)

    def m(k):
        return statistics.mean(float(x[k]) for x in rows)

    print("--- %d tap ---" % args.episodes)
    print("return        : %8.1f (do lech %.1f)" % (m("return"),
          statistics.pstdev([float(x["return"]) for x in rows])))
    print("roi khoi ban  : %8.0f %%" % (100 * m("fell")))
    print("het pin       : %8.0f %%" % (100 * m("flat")))
    print("lan toi dich  : %8.2f / tap" % m("arrivals"))
    print("pin nap duoc  : %8.3f / tap" % m("charged"))
    print("lan sac day   : %8.2f / tap" % m("full_charges"))
    print("quang duong   : %8.1f m" % m("distance"))
    print("buoc va cham  : %8.1f" % m("bumps"))
    print("o luoi da di  : %8.1f" % m("cells"))


if __name__ == "__main__":
    main()
