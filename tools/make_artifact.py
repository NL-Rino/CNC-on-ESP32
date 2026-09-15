"""Dung trang HTML doc lap (dep, xem tren dien thoai duoc) tu bo nao da huan luyen.

    python3 tools/make_artifact.py runs/car/best.npz runs/car/log.csv out.html
"""
import csv
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.baseline import ReactiveController  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402
from train.rollout import make_env, rollout  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "viz", "artifact_template.html")


def _run(agent, who, episodes, seed, stage, max_steps, want_charge=False):
    """want_charge: tim seed ma xe co cam sac thanh cong (de xem cho ro)."""
    env = make_env(stage=stage, max_steps=max_steps, record=True)
    recs, stats = [], []
    i = 0
    tries = 0
    while len(recs) < episodes and tries < episodes * 12:
        tries += 1
        if want_charge:
            probe = make_env(stage=stage, max_steps=max_steps)
            if hasattr(agent, "reset"):
                agent.reset()
            _, pst = rollout(agent, probe, seed + i)
            if pst["charged"] < 0.15 and tries < episodes * 10:
                i += 1
                continue
        _, st = rollout(agent, env, seed + i)
        i += 1
        stats.append(st)
        rec = env.episode_record()
        rec["stats"] = st
        rec["who"] = who
        rec["seed"] = seed + i - 1
        recs.append(rec)
    return recs, stats


def collect(npz, episodes=3, seed=4200, max_steps=1300, stage=3, teacher=2):
    """Ghi hinh: vai tap cua bo nao da hoc + vai tap cua bo dieu khien viet tay."""
    pol, meta = GRUPolicy.load(npz)
    recs, stats = _run(pol, "AI", episodes, seed, stage, max_steps)
    if teacher:
        t_recs, _ = _run(ReactiveController(0), "viet tay", teacher,
                         seed + 500, stage, max_steps, want_charge=True)
        recs = t_recs + recs
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


def build(npz, log_path, out_path, episodes=3):
    pol, meta, recs, stats = collect(npz, episodes=episodes)
    m = lambda k: statistics.mean(float(s[k]) for s in stats)  # noqa: E731
    all_stats = {
        "fell": 100 * m("fell"),
        "arrivals": m("arrivals"),
        "charged": m("charged"),
        "full": m("full_charges"),
        "distance": m("distance"),
    }
    ep0 = recs[0]
    facts = [
        ["%d" % ep0.get("lidar_n", 460), "điểm LiDAR mỗi vòng"],
        ["%.1f Hz" % ep0.get("scan_hz", 7), "tốc độ quét — dữ liệu luôn cũ 3 chu kỳ"],
        ["40 / 31 cm", "hộc sạc: ngoài / lòng trong"],
        ["5 mm", "khe hở mỗi bên khi xe 30 cm chui vào"],
        ["%d" % pol.n_params, "tham số trong bộ não"],
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
