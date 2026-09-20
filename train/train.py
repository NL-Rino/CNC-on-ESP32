"""Vong huan luyen: "nuoi" bo nao cua xe bang Evolution Strategies.

Vi du:
    python3 -m train.train --gens 200 --pop 64 --jobs 4 --curriculum
"""
import argparse
import csv
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

# Cap 0-1 chi can tap ngan (song sot + ne vat can); cap 3 phai du dai de pin
# can it nhat mot lan, neu khong xe khong co ly do gi de hoc di sac.
# Nha to + nhiem vu 5 den goi & 3 lan sac thi tap phai dai han han truoc.
# Mot chu ky pin (xa den duoi 20% roi nap day) mat ~1500 buoc, ba chu ky la
# 4500 - cong them thoi gian di tim den goi.
STAGE_STEPS = (900, 1400, 3000, 5000)


def steps_for(stage, cap):
    return min(cap, STAGE_STEPS[max(0, min(3, stage))])


def _init_worker(hidden, max_steps):
    global _ENV, _POL
    _ENV = make_env(stage=3, max_steps=max_steps)
    _POL = GRUPolicy(OBS_DIM, ACT_DIM, hidden)


def _score(job):
    """job = (theta, seeds, stage, max_steps) -> diem trung binh cua mot ca the."""
    theta, seeds, stage, cap = job
    _POL.set_params(theta)
    _ENV.cfg.stage = stage
    _ENV.cfg.max_steps = steps_for(stage, cap)
    tot = 0.0
    for s in seeds:
        r, _ = rollout(_POL, _ENV, s)
        tot += r
    return tot / len(seeds)


def evaluate(theta, hidden, stage, seeds, max_steps):
    pol = GRUPolicy(OBS_DIM, ACT_DIM, hidden)
    pol.set_params(theta)
    env = make_env(stage=stage, max_steps=steps_for(stage, max_steps))
    agg = {"return": 0.0, "arrivals": 0.0, "charged": 0.0, "distance": 0.0,
           "bumps": 0.0, "fell": 0.0, "flat": 0.0, "cells": 0.0,
           "full_charges": 0.0, "task_done": 0.0}
    for s in seeds:
        _, st = rollout(pol, env, s)
        for k in agg:
            agg[k] += float(st[k])
    for k in agg:
        agg[k] /= len(seeds)
    return agg


# Dieu kien len cap trong chuong trinh hoc
def stage_passed(stage, ev):
    """`cells` bay gio la SO O LUOI LiDAR DA QUET QUA, khong phai o da di qua."""
    if stage == 0:
        return ev["fell"] <= 0.10 and ev["cells"] >= 120
    if stage == 1:
        return ev["fell"] <= 0.10 and ev["cells"] >= 180 and ev["bumps"] <= 200
    if stage == 2:
        # Chua co den goi o bac nay; doi hoi song sot va biet tu ve sac.
        return (ev["fell"] <= 0.10 and ev["flat"] <= 0.25
                and ev["full_charges"] >= 0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--pop", type=int, default=64)
    ap.add_argument("--episodes", type=int, default=3, help="so tap moi ca the")
    ap.add_argument("--sigma", type=float, default=0.08)
    ap.add_argument("--lr", type=float, default=0.035)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--max-steps", type=int, default=1600)
    ap.add_argument("--stage", type=int, default=-1,
                    help="-1 = tu quyet (nap lai thi theo file, moi thi 3)")
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
    stop_path = os.path.join(args.out, "STOP")
    if os.path.exists(stop_path):
        os.remove(stop_path)       # don file dung cu, khong thi vua chay da dung
    hidden = args.hidden

    pol = GRUPolicy(OBS_DIM, ACT_DIM, hidden, seed=args.seed)
    start_gen = 0
    saved_stage = None
    saved_state = None
    resume_path = args.resume
    if resume_path and os.path.isdir(resume_path):
        cand = os.path.join(resume_path, "state.npz")
        resume_path = cand if os.path.exists(cand) else \
            os.path.join(resume_path, "last.npz")
    if resume_path:
        pol, meta = GRUPolicy.load(resume_path)
        hidden = pol.hidden
        if "gen" in meta:
            start_gen = int(meta["gen"])
        if "es_theta" in meta:
            saved_state = meta
            saved_stage = int(meta["stage"]) if "stage" in meta else None

    # Cap hoc: --stage N ep cung; khong thi nap lai diem cu dang do (theo
    # file), con moi tinh thi --curriculum -> 0, mac dinh -> 3.
    if args.stage >= 0:
        stage = args.stage
    elif saved_stage is not None:
        stage = saved_stage
    elif args.curriculum:
        stage = 0
    else:
        stage = 3

    es = ES(pol.get_params(), popsize=args.pop, sigma=args.sigma, lr=args.lr,
            seed=args.seed + 1)
    stage_gen0 = start_gen
    best_score = -1e18
    if saved_state is not None:
        es.load_state(saved_state)
        stage_gen0 = int(saved_state.get("stage_gen0", start_gen))
        best_score = float(saved_state.get("best_score", -1e18))
        print("chay tiep tu %s: gen %d, stage %d, sigma %.4f"
              % (resume_path, start_gen, stage, es.sigma))
    elif resume_path:
        print("nap TRONG SO tu %s (gen %d) nhung file nay khong co trang thai"
              % (resume_path, start_gen))
        print("   tien hoa -> bat dau lai sigma=%.3f. Muon chay tiep dung cho"
              " vua dung thi tro --resume vao THU MUC run (vd runs/bay11)."
              % args.sigma)
    print("tham so bo nao: %d | pop=%d | episodes=%d | jobs=%d"
          % (pol.n_params, args.pop, args.episodes, args.jobs))

    log_path = os.path.join(args.out, "log.csv")
    new_log = not os.path.exists(log_path)
    log_f = open(log_path, "a", newline="")
    log = csv.writer(log_f)
    if new_log:
        log.writerow(["gen", "stage", "mean_fit", "max_fit", "sigma",
                      "eval_return", "arrivals", "charged", "full_charges",
                      "cells", "bumps", "fell", "flat", "secs"])

    rng = np.random.default_rng(args.seed + 7)
    t_start = time.time()

    pool = Pool(args.jobs, initializer=_init_worker,
                initargs=(hidden, args.max_steps)) if args.jobs > 1 else None
    if pool is None:
        _init_worker(hidden, args.max_steps)

    def save_state(g, st):
        """Anh chup DAY DU: nap lai la chay tiep dung cho vua dung.

        Khong dung best.npz de chay tiep duoc: no chi duoc ghi khi diem danh
        gia PHA KY LUC, nen den the he 6000 ma ky luc lap tu 1744 thi no van
        ghi gen=1744 - nap lai la tut ve day. Day la loi that, da mat gio cua
        nguoi dung. state.npz thi ghi moi the he, khong dieu kien gi.
        """
        pol.set_params(es.theta.astype(np.float32))
        extra = es.state_dict()
        extra["stage"] = np.int64(st)
        extra["stage_gen0"] = np.int64(stage_gen0)
        extra["best_score"] = np.float64(best_score)
        tmp = os.path.join(args.out, "state.tmp.npz")
        pol.save(tmp, gen=g + 1, **extra)
        os.replace(tmp, os.path.join(args.out, "state.npz"))

    stopped = ""
    flat_gens = 0
    g = start_gen - 1
    try:
        for g in range(start_gen, start_gen + args.gens):
            t0 = time.time()
            pop = es.ask()
            seeds = [int(rng.integers(0, 2 ** 31 - 1)) for _ in range(args.episodes)]
            jobs = [(pop[i], seeds, stage, args.max_steps) for i in range(len(pop))]
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

            # Ca quan the cham diem giong het nhau = bo nao da bao hoa: tanh
            # dinh +-1 nen doi trong so khong con doi hanh vi. Khong bao thi
            # nguoi dung dot hang nghin the he ma khong biet gi.
            if info.get("spread", 1.0) < 1e-6:
                flat_gens += 1
                if flat_gens in (10, 50, 200):
                    print("  !! %d the he lien ca quan the diem GIONG HET nhau."
                          " Bo nao co the da bao hoa (|theta| tb %.2f)."
                          " Weight decay dang keo trong so xuong; neu sau vai"
                          " tram the he van thay dong nay thi nen chay lai tu"
                          " mot diem luu cu hon." % (flat_gens, info["theta_abs"]),
                          flush=True)
            else:
                flat_gens = 0

            ev = None
            if (g + 1) % args.eval_every == 0 or g == start_gen:
                eseeds = [1_000_000 + i for i in range(args.eval_episodes)]
                ev = evaluate(es.theta.astype(np.float32), hidden, stage,
                              eseeds, args.max_steps)
                line += ("\n         eval: R %7.1f | toi_diem %.2f | sac %.2f"
                         " (day %.2f) | o_phu %.0f | va_cham %.1f"
                         " | roi %.0f%% | het_pin %.0f%%"
                         % (ev["return"], ev["arrivals"], ev["charged"],
                            ev["full_charges"], ev["cells"], ev["bumps"],
                            100 * ev["fell"], 100 * ev["flat"]))
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
                          round(ev["full_charges"], 3) if ev else "",
                          round(ev["cells"], 2) if ev else "",
                          round(ev["bumps"], 2) if ev else "",
                          round(ev["fell"], 3) if ev else "",
                          round(ev["flat"], 3) if ev else "",
                          round(dt, 2)])
            log_f.flush()

            pol.set_params(es.theta.astype(np.float32))
            pol.save(os.path.join(args.out, "last.npz"), gen=g + 1, stage=stage)
            save_state(g, stage)

            if os.path.exists(stop_path):
                stopped = "co nguoi bam nut dung"
                break

            # len cap
            if args.curriculum and ev is not None and stage < 3 and \
                    (g - stage_gen0) >= args.min_gens_per_stage and stage_passed(stage, ev):
                stage += 1
                stage_gen0 = g
                best_score = -1e18
                es.sigma = max(es.sigma, args.sigma * 0.8)
                print(">>> len cap: stage %d (xe da qua bai truoc)" % stage, flush=True)

            if args.time_budget > 0 and (time.time() - t_start) / 60.0 > args.time_budget:
                stopped = "het thoi gian cho phep"
                break
    except KeyboardInterrupt:
        stopped = "Ctrl+C"
    finally:
        save_state(g, stage)
        if pool is not None:
            pool.close()
            pool.join()
        log_f.close()

    if os.path.exists(stop_path):
        os.remove(stop_path)
    print("\n%s o the he %d (stage %d)."
          % (stopped or "chay xong", g + 1, stage), flush=True)
    print("  bo nao diem cao nhat : %s" % os.path.join(args.out, "best.npz"))
    print("  chay tiep dung cho nay: python -m train.train --resume %s ..."
          % args.out)


if __name__ == "__main__":
    main()
