"""Kiem tra nhanh phan mo phong. Chay: python3 tests/test_sim.py"""
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sim.env import OBS_DIM, OBS_NAMES, CarEnv, EnvConfig
from sim.robot import Robot, RobotSpec
from sim.sensors import SONAR_MAX, SensorSuite
from sim.world import IR_CALL, Beacon, Obstacle, World
from train.es import ES
from train.policy import GRUPolicy
from train.rollout import make_env, rollout


def test_obs_names_khop_kich_thuoc():
    assert len(OBS_NAMES) == OBS_DIM


def test_cung_seed_thi_cung_ket_qua():
    env = make_env(stage=3, max_steps=120)
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=3)
    r1, s1 = rollout(pol, env, 42)
    r2, s2 = rollout(pol, env, 42)
    assert abs(r1 - r2) < 1e-9 and s1 == s2


def test_sieu_am_do_dung_khoang_cach():
    w = World(4.0, 4.0)
    w.obstacles.append(Obstacle("box", x0=2.5, y0=1.5, x1=3.0, y1=2.5))
    spec = RobotSpec()
    rb = Robot(spec)
    rb.reset(1.0, 2.0, 0.0)
    s = SensorSuite(spec)
    rng = random.Random(0)
    best = min(s.read_sonar(rb, w, rng)[2] for _ in range(20))
    assert 1.3 < best < 1.6, best          # ~1.5 m tinh tu mat cam bien
    rb.reset(1.0, 2.0, math.pi)            # quay lung lai -> khong thay gi
    s.read_sonar(rb, w, rng)
    assert s.sonar[2] == SONAR_MAX


def test_cam_bien_vuc_bao_truoc_khi_roi():
    w = World(1.0, 1.0)
    spec = RobotSpec()
    rb = Robot(spec)
    rb.reset(0.5, 0.5, 0.0, 1.0)
    s = SensorSuite(spec)
    rng = random.Random(1)
    warned = False
    for _ in range(200):
        rb.step(1.0, 1.0, 0.05, w, rng)
        s.read_cliff(rb, w, rng)
        if s.cliff_front > 0.5 and not rb.fallen:
            warned = True
        if rb.fallen:
            break
    assert rb.fallen and warned, "cam bien vuc phai keu truoc khi xe roi"


def test_hong_ngoai_chi_thay_phia_truoc():
    w = World(3.0, 3.0)
    w.beacons.append(Beacon(2.5, 1.5, IR_CALL))
    spec = RobotSpec()
    rb = Robot(spec)
    s = SensorSuite(spec)
    rng = random.Random(2)
    rb.reset(1.0, 1.5, 0.0)
    v, seen = s.read_ir(rb, w, rng)
    assert v[IR_CALL] > 0.1 and seen[IR_CALL] > 0.5
    rb.reset(1.0, 1.5, math.pi)
    v, seen = s.read_ir(rb, w, rng)
    assert v[IR_CALL] < 0.05 and seen[IR_CALL] < 0.5


def test_hong_ngoai_bi_vat_can_che():
    w = World(3.0, 3.0)
    w.beacons.append(Beacon(2.5, 1.5, IR_CALL))
    w.obstacles.append(Obstacle("box", x0=1.6, y0=1.2, x1=1.8, y1=1.8))
    spec = RobotSpec()
    rb = Robot(spec)
    rb.reset(1.0, 1.5, 0.0)
    v, _ = SensorSuite(spec).read_ir(rb, w, random.Random(3))
    assert v[IR_CALL] == 0.0


def test_pin_tut_khi_chay_va_len_khi_sac():
    env = CarEnv(EnvConfig(stage=3, max_steps=50))
    env.reset(5)
    b0 = env.robot.battery
    for _ in range(40):
        env.step((0.0, 0.0))
    assert env.robot.battery < b0                      # van hao khi dung yen

    w = World(2.0, 2.0)
    w.dock = Beacon(1.0, 1.0, 1)
    w.dock_heading = 0.0
    rb = Robot()
    rb.reset(1.02, 1.0, 0.0, 0.3)
    gained = sum(rb.try_charge(w, 0.05) for _ in range(20))
    assert gained > 0.0 and rb.battery > 0.3


def test_luu_va_nap_lai_bo_nao():
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=7)
    obs = [0.1] * OBS_DIM
    a1 = pol.act(obs)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "w.npz")
        pol.save(p, gen=3, stage=2)
        pol2, meta = GRUPolicy.load(p)
    pol2.reset()
    a2 = pol2.act(obs)
    assert np.allclose(a1, a2) and int(meta["gen"]) == 3


def test_gru_co_tri_nho():
    """Cung mot dau vao nhung trang thai an khac -> hanh dong khac."""
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=11)
    obs = [0.3] * OBS_DIM
    a1 = pol.act(obs)
    for _ in range(5):
        pol.act([0.9] * OBS_DIM)
    a2 = pol.act(obs)
    assert not np.allclose(a1, a2)


def test_es_cai_thien_ham_don_gian():
    target = np.linspace(-1, 1, 25)

    def fit(x):
        return -float(np.sum((x - target) ** 2))

    es = ES(np.zeros(25), popsize=32, sigma=0.15, lr=0.12, weight_decay=0.0)
    first = fit(es.theta)
    for _ in range(120):
        pop = es.ask()
        es.tell([fit(p) for p in pop])
    assert fit(es.theta) > first * 0.2, "ES phai giam duoc sai so"


def test_ghi_hinh_tap():
    env = make_env(stage=3, max_steps=40, record=True)
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=1)
    rollout(pol, env, 9)
    rec = env.episode_record()
    assert len(rec["frames"]) == env.steps
    f = rec["frames"][0]
    for k in ("x", "y", "th", "sonar", "cliff", "ir", "u", "batt"):
        assert k in f


def test_cam_sac_di_qua_diem_tiep_can():
    """Khi con xa, muc tieu phai la diem tiep can truoc mat tram sac,
    khong phai chinh tram sac - neu khong xe se dam vao ngang hong."""
    env = CarEnv(EnvConfig(stage=3, max_steps=50))
    for seed in range(30):
        env.reset(seed)
        if env.world.dock is None:
            continue
        env.robot.battery = 0.2
        env.world.dock.active = True
        d = env.world.dock
        h = env.world.dock_heading
        env.robot.x = d.x - 0.9 * math.cos(h)
        env.robot.y = d.y - 0.9 * math.sin(h)
        g = env._active_goal()
        assert g is not None and g[2] == "dock_app"
        gx, gy = g[0], g[1]
        assert abs(math.hypot(gx - d.x, gy - d.y) - env.cfg.dock_approach) < 1e-6
        # dung sat truoc mat tram -> chuyen sang dam thang vao
        env.robot.x = d.x - 0.32 * math.cos(h)
        env.robot.y = d.y - 0.32 * math.sin(h)
        assert env._active_goal()[2] == "dock"
        return
    raise AssertionError("khong sinh duoc canh nao co tram sac")


def test_uu_tien_sac_hon_den_goi_khi_pin_yeu():
    env = CarEnv(EnvConfig(stage=3, max_steps=50))
    for seed in range(30):
        env.reset(seed)
        if env.world.dock is None:
            continue
        env.robot.battery = 0.1
        env.world.dock.active = True
        env._spawn_call()
        g = env._active_goal()
        assert g[2].startswith("dock"), "pin yeu thi phai di sac truoc"
        return


def main():
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print("  ok   %s" % name)
        except AssertionError as e:
            bad += 1
            print("  FAIL %s: %s" % (name, e))
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("  LOI  %s: %r" % (name, e))
    print("%d/%d dat" % (len(fns) - bad, len(fns)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
