"""Dung trang HTML doc lap (dep, xem tren dien thoai duoc) tu bo nao da huan luyen.

    python3 tools/make_artifact.py runs/car/best.npz runs/car/log.csv out.html
"""
import csv
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env, rollout  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "viz", "artifact_template.html")


def collect(npz, episodes=4, seed=4200, stride=2, max_steps=900, stage=3):
    pol, meta = GRUPolicy.load(npz)
    env = make_env(stage=stage, max_steps=max_steps, record=True)
    recs, stats = [], []
    tried = 0
    while len(recs) < episodes and tried < episodes * 6:
        _, st = rollout(pol, env, seed + tried)
        tried += 1
        stats.append(st)
        rec = env.episode_record()
        rec["frames"] = rec["frames"][::stride]
        rec["dt"] = rec["dt"] * stride
        rec["stats"] = st
        recs.append(rec)
    return pol, meta, recs, stats


def curve(log_path, max_points=400):
    rows = []
    if not os.path.exists(log_path):
        return rows
    with open(log_path) as f:
        for r in csv.DictReader(f):
            try:
                rows.append([int(r["gen"]), float(r["mean_fit"]), int(r["stage"])])
            except (ValueError, KeyError):
                continue
    if len(rows) > max_points:
        k = len(rows) // max_points + 1
        rows = rows[::k]
    return rows


def build(npz, log_path, out_path, episodes=4):
    pol, meta, recs, stats = collect(npz, episodes=episodes)
    m = lambda k: statistics.mean(float(s[k]) for s in stats)  # noqa: E731
    all_stats = {
        "fell": 100 * m("fell"),
        "arrivals": m("arrivals"),
        "charged": m("charged"),
        "distance": m("distance"),
    }
    facts = [
        ["%.0f%%" % all_stats["fell"], "so tap roi khoi ban"],
        ["%.1f" % all_stats["arrivals"], "lan toi den goi / tap"],
        ["%.0f m" % all_stats["distance"], "quang duong / tap 45 giay"],
        ["%d" % pol.n_params, "tham so trong bo nao"],
        ["20 / 2", "dau vao cam bien / kenh dong co"],
    ]
    data = {
        "policy": os.path.basename(npz),
        "params": pol.n_params,
        "gen": int(meta.get("gen", 0)),
        "facts": facts,
        "curve": curve(log_path),
        "episodes": recs,
    }
    with open(TEMPLATE) as f:
        html = f.read()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    i = html.index("/*__DATA__*/")
    j = html.index(";", i)
    html = html[:i] + blob + html[j:]
    with open(out_path, "w") as f:
        f.write(html)
    print("da tao %s (%.0f KB, %d tap)"
          % (out_path, os.path.getsize(out_path) / 1024, len(recs)))
    for k, v in all_stats.items():
        print("  %-10s %.2f" % (k, v))


if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0] if a else "runs/car/best.npz",
          a[1] if len(a) > 1 else "runs/car/log.csv",
          a[2] if len(a) > 2 else "runs/car/replay_artifact.html")
