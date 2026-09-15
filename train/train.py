"""Vong huan luyen: "nuoi" bo nao cua xe bang Evolution Strategies.

Vi du:
    python3 -m train.train --gens 200 --pop 64 --jobs 4 --curriculum
"""
import argparse
import csv
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.env import ACT_DIM, OBS_DIM  # noqa: E402
from train.es import ES  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env, rollout  # noqa: E402

_ENV = None
_POL = None


def _init_worker(hidden, max_steps):
    global _ENV, _POL
    _ENV = make_env(stage=3, max_steps=max_steps)
    _POL = GRUPolicy(OBS_DIM, ACT_DIM, hidden)


def _score(job):
    """job = (theta, seeds, stage) -> diem trung binh cua mot ca the."""
    theta, seeds, stage = job
    _POL.set_params(theta)
    _ENV.cfg.stage = stage
    tot = 0.0
    for s in seeds:
        r, _ = rollout(_POL, _ENV, s)
        tot += r
    return tot / len(seeds)


def evaluate(theta, hidden, stage, seeds, max_steps):
    pol = GRUPolicy(OBS_DIM, ACT_DIM, hidden)
    pol.set_params(theta)
    env = make_env(stage=stage, max_steps=max_steps)
    agg = {"return": 0.0, "arrivals": 0.0, "charged": 0.0, "distance": 0.0,
           "bumps": 0.0, "fell": 0.0, "flat": 0.0, "cells": 0.0}
    for s in seeds:
        _, st = rollout(pol, env, s)
        for k in agg:
            agg[k] += float(st[k])
    for k in agg:
        agg[k] /= len(seeds)
    return agg


# Dieu kien len cap trong chuong trinh hoc
def stage_passed(stage, ev):
    if stage == 0:
        return ev["fell"] <= 0.10 and ev["cells"] >= 14
    if stage == 1:
        return ev["fell"] <= 0.10 and ev["cells"] >= 12 and ev["bumps"] <= 60
    if stage == 2:
        return ev["fell"] <= 0.10 and ev["arrivals"] >= 1.0
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--pop", type=int, default=64)
    ap.add_argument("--episodes", type=int, default=3, help="so tap moi ca the")
    ap.add_argument("--sigma", type=float, default=0.08)
    ap.add_argument("--lr", type=float, default=0.035)
    ap.add_argument("--hidden", type=int, default=16)
    ap.add_argument("--max-steps", type=int, default=900)
    ap.add_argument("--stage", type=int, default=3)
    ap.add_argument("--curriculum", action="store_true",
                    help="bat dau tu stage 0 va tu dong len cap")
    ap.add_argument("--min-gens-per-stage", type=int, default=15)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--eval-every", type=int, default=5)
    ap.add_argument("--eval-episodes", type=int, default=8)
    ap.add_argument("--out", default="runs/car")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--time-budget", type=float, default=0.0,
                    help="dung sau bao nhieu phut (0 = khong gioi han)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    stage = 0 if args.curriculum else args.stage
    hidden = args.hidden

    pol = GRUPolicy(OBS_DIM, ACT_DIM, hidden, seed=args.seed)
    start_gen = 0
    if args.resume:
        pol, meta = GRUPolicy.load(args.resume)
        hidden = pol.hidden
        if "stage" in meta:
            stage = int(meta["stage"])
        if "gen" in meta:
            start_gen = int(meta["gen"])
        print("resume tu %s (gen=%d, stage=%d)" % (args.resume, start_gen, stage))

    es = ES(pol.get_params(), popsize=args.pop, sigma=args.sigma, lr=args.lr,
            seed=args.seed + 1)
    print("tham so bo nao: %d | pop=%d | episodes=%d | jobs=%d"
          % (pol.n_params, args.pop, args.episodes, args.jobs))

    log_path = os.path.join(args.out, "log.csv")
    new_log = not os.path.exists(log_path)
    log_f = open(log_path, "a", newline="")
    log = csv.writer(log_f)
    if new_log:
        log.writerow(["gen", "stage", "mean_fit", "max_fit", "sigma",
                      "eval_return", "arrivals", "charged", "cells",
                      "bumps", "fell", "flat", "secs"])

    best_score = -1e18
    stage_gen0 = 0
    rng = np.random.default_rng(args.seed + 7)
    t_start = time.time()

    pool = Pool(args.jobs, initializer=_init_worker,
                initargs=(hidden, args.max_steps)) if args.jobs > 1 else None
    if pool is None:
        _init_worker(hidden, args.max_steps)

    try:
        for g in range(start_gen, start_gen + args.gens):
            t0 = time.time()
            pop = es.ask()
            seeds = [int(rng.integers(0, 2 ** 31 - 1)) for _ in range(args.episodes)]
            jobs = [(pop[i], seeds, stage) for i in range(len(pop))]
            if pool is not None:
                fits = pool.map(_score, jobs, chunksize=max(1, len(jobs) // (args.jobs * 4)))
            else:
                fits = [_score(j) for j in jobs]
            info = es.tell(fits)
            dt = time.time() - t0
            mean_fit = float(np.mean(fits))
            max_fit = float(np.max(fits))

            line = ("gen %4d | stage %d | fit %8.1f (max %8.1f) | sigma %.3f | %4.1fs"
                    % (g, stage, mean_fit, max_fit, info["sigma"], dt))

            ev = None
            if (g + 1) % args.eval_every == 0 or g == start_gen:
                eseeds = [1_000_000 + i for i in range(args.eval_episodes)]
                ev = evaluate(es.theta.astype(np.float32), hidden, stage,
                              eseeds, args.max_steps)
                line += ("\n         eval: R %7.1f | toi_diem %.2f | sac %.2f"
                         " | o_da_di %.1f | va_cham %.1f | roi %.0f%% | het_pin %.0f%%"
                         % (ev["return"], ev["arrivals"], ev["charged"],
                            ev["cells"], ev["bumps"], 100 * ev["fell"],
                            100 * ev["flat"]))
                if ev["return"] > best_score:
                    best_score = ev["return"]
                    pol.set_params(es.theta.astype(np.float32))
                    pol.save(os.path.join(args.out, "best.npz"), gen=g,
                             stage=stage, score=ev["return"])
            print(line, flush=True)

            log.writerow([g, stage, round(mean_fit, 2), round(max_fit, 2),
                          round(info["sigma"], 4),
                          round(ev["return"], 2) if ev else "",
                          round(ev["arrivals"], 3) if ev else "",
                          round(ev["charged"], 3) if ev else "",
                          round(ev["cells"], 2) if ev else "",
                          round(ev["bumps"], 2) if ev else "",
                          round(ev["fell"], 3) if ev else "",
                          round(ev["flat"], 3) if ev else "",
                          round(dt, 2)])
            log_f.flush()

            pol.set_params(es.theta.astype(np.float32))
            pol.save(os.path.join(args.out, "last.npz"), gen=g, stage=stage)

            # len cap
            if args.curriculum and ev is not None and stage < 3 and \
                    (g - stage_gen0) >= args.min_gens_per_stage and stage_passed(stage, ev):
                stage += 1
                stage_gen0 = g
                best_score = -1e18
                es.sigma = max(es.sigma, args.sigma * 0.8)
                print(">>> len cap: stage %d (xe da qua bai truoc)" % stage, flush=True)

            if args.time_budget > 0 and (time.time() - t_start) / 60.0 > args.time_budget:
                print("het thoi gian cho phep, dung lai.", flush=True)
                break
    finally:
        if pool is not None:
            pool.close()
            pool.join()
        log_f.close()

    pol.set_params(es.theta.astype(np.float32))
    pol.save(os.path.join(args.out, "last.npz"), gen=start_gen + args.gens,
             stage=stage)
    print("xong. bo nao tot nhat: %s/best.npz" % args.out)


if __name__ == "__main__":
    main()
