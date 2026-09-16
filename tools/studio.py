"""Xuong lam viec: xem xe chay, ve nha, va dung huan luyen cho an toan.

    python -m tools.studio

Mo mot trang web chay ngay tren may ban (khong gui gi ra ngoai). Ba viec:
  - Xem xe chay trong mat bang bat ky, tua toi tua lui tung khung hinh
  - Ve nha cua minh: keo chuot tao tuong, dat tram sac, dat nguoi di lai
  - Nut DUNG AN TOAN cho phien huan luyen dang chay

Vi sao la web chu khong phai cua so Tk: trinh duyet thi may nao cung co san,
con tkinter thi khong. Va ca trang nay chi la mot file HTML tinh - khong can
cai them gi.
"""
import argparse
import json
import math
import os
import random
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from sim import layout as layout_mod  # noqa: E402
from sim.env import CarEnv, EnvConfig  # noqa: E402
from sim.failsafe import NGUONG, mac_dinh  # noqa: E402
from sim.perception import OBS_DIM  # noqa: E402


def rec_frames(env):
    return env.frames
from train.baseline import ReactiveController  # noqa: E402
from train.policy import GRUPolicy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "viz", "studio.html")
LAYOUTS = os.path.join(ROOT, "layouts")
RUNS = os.path.join(ROOT, "runs")
BRAINS = os.path.join(ROOT, "brains")


# ------------------------------------------------------------------- du lieu
def list_runs():
    out = []
    if not os.path.isdir(RUNS):
        return out
    for name in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, name)
        st = os.path.join(d, "state.npz")
        if not os.path.isfile(st):
            continue
        try:
            z = np.load(st, allow_pickle=True)
            out.append({
                "name": name,
                "gen": int(z["gen"]) if "gen" in z.files else 0,
                "stage": int(z["stage"]) if "stage" in z.files else -1,
                "best": (round(float(z["best_score"]), 1)
                         if "best_score" in z.files else None),
                "sigma": (round(float(z["es_sigma"]), 4)
                          if "es_sigma" in z.files else None),
                "mtime": os.path.getmtime(st),
                "stopping": os.path.exists(os.path.join(d, "STOP")),
            })
        except Exception:      # noqa: BLE001 - file dang duoc ghi do
            continue
    return out


def list_brains():
    """Liet ke bo nao, KEM so dau vao cua tung cai.

    Kho nay con giu bo nao tu cac doi cam bien truoc (40 hay 48 dau vao).
    Chung khong chay duoc voi mo phong hien tai, nhung neu chi liet ke ten
    thi nguoi dung chon nham roi an mot dong loi matmul vo nghia. Ghi ro so
    dau vao ngay tren danh sach va khoa chung lai.
    """
    out = []
    for folder in (BRAINS, RUNS):
        if not os.path.isdir(folder):
            continue
        for dirpath, _, files in os.walk(folder):
            for f in sorted(files):
                if not f.endswith(".npz") or f.startswith("state"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                try:
                    d = np.load(p, allow_pickle=True)
                    n = int(d["obs_dim"])
                    g = int(d["gen"]) if "gen" in d.files else None
                except Exception:      # noqa: BLE001 - file dang duoc ghi do
                    continue
                out.append({"path": rel, "obs": n, "gen": g,
                            "ok": n == OBS_DIM})
    out.sort(key=lambda b: (not b["ok"], b["path"]))
    return out


def list_layouts():
    if not os.path.isdir(LAYOUTS):
        return []
    return sorted(f[:-5] for f in os.listdir(LAYOUTS) if f.endswith(".json"))


def curve(run, max_points=400):
    p = os.path.join(RUNS, run, "log.csv")
    if not os.path.exists(p):
        return []
    import csv as _csv
    rows = []
    with open(p, newline="") as f:
        for r in _csv.DictReader(f):
            if r.get("eval_return"):
                try:
                    rows.append([int(r["gen"]), float(r["eval_return"]),
                                 int(r["stage"]), float(r["fell"] or 0)])
                except ValueError:
                    pass
    k = max(1, len(rows) // max_points)
    return rows[::k]


# ------------------------------------------------------------------ chay tap
def run_episode(brain=None, layout=None, seed=0, steps=900, stage=3,
                failsafe=NGUONG):
    lay = None
    if layout:
        lay = layout_mod.load(os.path.join(LAYOUTS, layout + ".json"))
    cfg = EnvConfig(stage=stage, layout=lay, max_steps=steps,
                    record=True, record_every=1, scan_every=2,
                    scan_points=0)          # xem tai cho -> gui du ca vong quet
    env = CarEnv(cfg)
    obs = env.reset(seed)
    if brain and brain != "viet-tay":
        pol, _ = GRUPolicy.load(os.path.join(ROOT, brain))
        if pol.obs_dim != OBS_DIM:
            raise ValueError(
                "bo nao %s duoc nuoi voi %d dau vao, mo phong bay gio dung "
                "%d. No thuoc doi cam bien cu (truoc khi co truc hoc va "
                "huong tram trong tri nho) nen khong chay duoc. Chon mot bo "
                "nao ghi '%d dau vao' trong danh sach, vi du brains/"
                "car_bay_v1.npz, hoac chon 'bo luat viet tay'."
                % (brain, pol.obs_dim, OBS_DIM, OBS_DIM))
        pol.reset()
        act = pol.act
    else:
        ctrl = ReactiveController(seed)
        ctrl.reset()
        act = ctrl.act
    fs = mac_dinh(failsafe) if failsafe > 0 else None
    done = False
    info = {}
    forced = []
    while not done:
        if fs is not None:
            a, f = fs.act(obs, act)
        else:
            a, f = act(obs), False
        forced.append(f)
        obs, _, done, info = env.step(a)
    for fr, f in zip(rec_frames(env), forced):
        if f:
            fr["fs"] = 1
    rec = env.episode_record()
    rec["stats"] = {
        "steps": env.steps, "distance": round(env.distance, 2),
        "charged": round(env.charged, 3), "full": env.full_charges,
        "arrivals": env.arrivals, "bumps": env.bumps,
        "fell": bool(info.get("fell")), "flat": bool(info.get("flat")),
        "battery": round(env.robot.battery, 3),
    }
    return rec


# -------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # im lang, khong spam terminal
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if u.path in ("/", "/index.html"):
                with open(PAGE, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/status":
                return self._json({"runs": list_runs(), "brains": list_brains(),
                                   "layouts": list_layouts()})
            if u.path == "/api/curve":
                return self._json(curve(q.get("run", "")))
            if u.path == "/api/layout":
                name = os.path.basename(q.get("name", ""))
                p = os.path.join(LAYOUTS, name + ".json")
                if not os.path.exists(p):
                    return self._json({"error": "khong co mat bang nay"}, 404)
                return self._json(layout_mod.load(p))
            if u.path == "/api/episode":
                rec = run_episode(brain=q.get("brain"),
                                  layout=q.get("layout") or None,
                                  seed=int(q.get("seed", 0)),
                                  steps=int(q.get("steps", 900)),
                                  stage=int(q.get("stage", 3)),
                                  failsafe=float(q.get("failsafe", NGUONG)))
                return self._json(rec)
        except ValueError as e:
            # ValueError la loi TA tu nem ra, cau chu da viet cho nguoi doc -
            # dung dan them ten kieu ngoai le vao truoc.
            return self._json({"error": str(e)}, 400)
        except Exception as e:          # noqa: BLE001 - tra loi thay vi chet
            return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 500)
        self._json({"error": "khong co duong dan nay"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return self._json({"error": "JSON hong"}, 400)
        try:
            if u.path == "/api/stop":
                run = os.path.basename(body.get("run", ""))
                d = os.path.join(RUNS, run)
                if not os.path.isdir(d):
                    return self._json({"error": "khong co phien nay"}, 404)
                open(os.path.join(d, "STOP"), "w").close()
                return self._json({"ok": True, "msg":
                                   "da dat lenh dung - phien se luu xong roi thoat"})
            if u.path == "/api/layout":
                name = os.path.basename(body.get("name") or "mat-bang")
                lay = body.get("layout") or {}
                errs = layout_mod.validate(lay)
                if errs:
                    return self._json({"error": " / ".join(errs)}, 400)
                layout_mod.save(os.path.join(LAYOUTS, name + ".json"), lay)
                return self._json({"ok": True, "name": name})
        except Exception as e:          # noqa: BLE001
            return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 500)
        self._json({"error": "khong co duong dan nay"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    os.makedirs(LAYOUTS, exist_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    url = "http://%s:%d/" % (a.host, a.port)
    print("xuong lam viec: %s   (Ctrl+C de dong)" % url)
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndong.")


if __name__ == "__main__":
    main()
