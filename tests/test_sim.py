"""Kiem tra nhanh phan mo phong. Chay: python3 tests/test_sim.py"""
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sim.dock_detector import detect, detect_lidar
from sim.env import OBS_DIM, OBS_NAMES, CarEnv, EnvConfig
from sim.geometry import wrap_angle
from sim.lidar import RMAX, RMIN, SECTORS, Lidar
from sim.robot import Robot, RobotSpec
from sim.sensors import SensorSuite
from sim.world import IR_CALL, IR_DOCK, Beacon, Dock, Obstacle, World, make_world
from train.es import ES
from train.policy import GRUPolicy
from train.rollout import make_env, rollout


def _lidar_on(world, robot, seed=0):
    ld = Lidar()
    ld.reset(np.random.default_rng(seed), 7.0)
    ld._scan(robot, world)
    return ld


def test_obs_names_khop_kich_thuoc():
    assert len(OBS_NAMES) == OBS_DIM


def test_cung_seed_thi_cung_ket_qua():
    env = make_env(stage=3, max_steps=150)
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=3)
    r1, s1 = rollout(pol, env, 42)
    r2, s2 = rollout(pol, env, 42)
    assert abs(r1 - r2) < 1e-9 and s1 == s2


def test_lidar_do_dung_khoang_cach():
    w = World(6.0, 6.0)
    w.obstacles.append(Obstacle("box", x0=3.5, y0=2.5, x1=4.0, y1=3.5))
    w.bake()
    rb = Robot()
    rb.reset(1.0, 3.0, 0.0)
    ld = _lidar_on(w, rb)
    a, r = ld.base, ld.r
    fwd = np.argmin(np.abs(a))            # tia thang truoc mat
    assert 2.4 < r[fwd] < 2.6, r[fwd]     # hop cach 2.5 m
    back = np.argmin(np.abs(np.abs(a) - math.pi))
    assert r[back] == 0.0                 # phia sau khong co gi -> khong phan hoi


def test_lidar_ton_trong_tam_do():
    w = World(6.0, 6.0)
    w.obstacles.append(Obstacle("circle", x=1.05, y=3.0, r=0.02))  # rat gan
    w.bake()
    rb = Robot()
    rb.reset(1.0, 3.0, 0.0)
    ld = _lidar_on(w, rb)
    ok = ld.r[ld.r > 0.0]
    assert ok.size == 0 or ok.min() >= RMIN - 1e-6
    assert ld.r.max() < RMAX


def test_lidar_bu_goc_khi_xe_quay():
    """Vong quet cu van phai chi dung huong sau khi xe da quay (de-skew)."""
    w = World(6.0, 6.0)
    w.obstacles.append(Obstacle("box", x0=3.0, y0=2.9, x1=3.2, y1=3.1))
    w.bake()
    rb = Robot()
    rb.reset(1.0, 3.0, 0.0)
    ld = _lidar_on(w, rb)
    s0 = ld.sector_ranges(rb.theta)
    front = int(np.argmin(s0))
    rb.theta = math.pi / 2                # xe quay trai 90 do, chua quet lai
    s1 = ld.sector_ranges(rb.theta)
    moved = (front - int(np.argmin(s1))) % SECTORS
    assert moved == SECTORS // 4, moved   # vat phai nhay sang ben phai 90 do


def _lone_dock(heading=math.pi):
    w = World(6.0, 6.0)
    dock = Dock(3.0, 3.0, heading)
    w.dock = dock
    w.add_bay(dock)
    w.beacons.append(dock.beacon)
    w.bake()
    return w, dock


def test_bo_do_tim_duoc_hoc():
    w, dock = _lone_dock()                # cua hoc quay ve phia +x
    rb = Robot()
    mx, my = dock.mouth
    hit = 0
    for k in range(12):
        rb.reset(mx + 0.7, my, math.pi)
        ld = _lidar_on(w, rb, seed=k)
        for c in detect_lidar(ld, rb.theta):
            if abs(c.bearing) < 0.2 and abs(c.dist - 0.7) < 0.15:
                hit += 1
                break
    assert hit >= 10, "chi tim thay %d/12 lan" % hit


def test_bo_do_cho_ra_truc_cua_hoc():
    """Thu quan trong nhat: hoc chu U cho biet no QUAY VE DAU.

    Khong co con so nay thi khong the canh xe vao khe chi ho 5 mm moi ben.
    """
    w, dock = _lone_dock()
    rb = Robot()
    mx, my = dock.mouth
    errs = []
    for k in range(20):
        rb.reset(mx + 0.55, my + 0.12 * ((k % 5) - 2), math.pi)
        ld = _lidar_on(w, rb, seed=k)
        for c in detect_lidar(ld, rb.theta):
            if abs(c.dist - 0.6) < 0.25:
                errs.append(abs(wrap_angle(rb.theta + c.yaw - dock.heading)))
                break
    assert len(errs) >= 16, "chi do duoc truc %d/20 lan" % len(errs)
    med = sorted(errs)[len(errs) // 2]
    assert med < math.radians(8.0), "truc lech trung vi %.1f do" % math.degrees(med)


def test_bo_do_khong_nham_hop_dac_la_hoc():
    """Hop dac cung co bang 40 cm cung khong duoc tinh la hoc: no LOI ra
    truoc day cung chu khong LOM vao sau."""
    w = World(6.0, 6.0)
    w.add_obstacle(Obstacle("box", x0=3.0, y0=2.8, x1=3.4, y1=3.2))
    w.bake()
    rb = Robot()
    for k in range(10):
        rb.reset(2.0, 3.0, 0.0)
        ld = _lidar_on(w, rb, seed=k)
        for c in detect_lidar(ld, rb.theta):
            assert abs(c.bearing) > 0.4, "nham hop dac thanh hoc: %r" % (c,)


def _capture_window(flare, steps=3):
    """Lech ngang toi da o cua ma xe van chui tron vao duoc (m)."""
    import sim.world as WW
    old_f, old_s = WW.BAY_FLARE, WW.BAY_FLARE_STEPS
    WW.BAY_FLARE, WW.BAY_FLARE_STEPS = flare, max(1, steps)
    try:
        w, dock = _lone_dock(0.0)

        class NoSlip(RobotSpec):
            slip_noise = 0.0

        rb = Robot(NoSlip())
        best = -1.0
        for i in range(20):
            lat = 0.0025 * i
            x, y = dock.local_to_world(-0.40, lat)
            rb.reset(x, y, dock.heading, 0.5)
            rng = random.Random(1)
            for _ in range(140):
                rb.step(0.30, 0.30, 0.05, w, rng)
            if rb.try_charge(w, 0.05, True) > 0.0:
                best = lat
        return best
    finally:
        WW.BAY_FLARE, WW.BAY_FLARE_STEPS = old_f, old_s


def test_mieng_hoc_loe_la_thu_lam_cho_viec_cam_sac_kha_thi():
    """Hoc thang tuot 31 cm voi xe tron 30 cm chi ho 5 mm moi ben - khong
    cach nao lai vao chuan den the. Vat hai goc trong o mieng noi cua so bat
    ra gap muoi lan. Test nay giu cho con so do khong am tham tut di."""
    thang = _capture_window(0.0, 0)
    loe = _capture_window(0.08, 3)
    assert thang <= 0.006, "hoc thang tuot ma bat duoc +-%.0f mm?" % (1000 * thang)
    assert loe >= 0.030, "co doan loe ma chi bat duoc +-%.0f mm" % (1000 * loe)
    assert loe > 4.0 * max(thang, 0.0025)


def test_than_xe_tron_khong_co_rang_buoc_goc_khi_chui_vao():
    """Xe TRON nen quay the nao cung lot qua khe, mien la dung truc. Xe vuong
    cung kich thuoc nghieng 2 do la da can khe 31.0 cm - het cua."""
    w, dock = _lone_dock(0.0)
    rb = Robot()
    for deg in (0, 5, 15, 30):
        x, y = dock.local_to_world(-0.05)
        rb.reset(x, y, dock.heading + math.radians(deg), 0.5)
        assert w.min_obstacle_clearance(rb.x, rb.y) >= rb.spec.radius, \
            "xe tron o giua hoc ma bao ket khi quay %d do" % deg


def test_bo_do_bo_qua_tuong_dai():
    w = World(8.0, 8.0)
    w.obstacles.append(Obstacle("box", x0=3.0, y0=0.0, x1=3.2, y1=6.0))
    w.bake()
    rb = Robot()
    rb.reset(1.0, 3.0, 0.0)
    ld = _lidar_on(w, rb)
    for c in detect_lidar(ld, rb.theta):
        assert abs(c.bearing) > 0.3, "tuong dai bi nham la tram sac"


def test_cam_bien_vuc_bao_truoc_khi_roi():
    w = World(1.0, 1.0)
    rb = Robot()
    rb.reset(0.5, 0.5, 0.0, 1.0)
    s = SensorSuite(RobotSpec())
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


def test_hong_ngoai_tram_sac_chi_thay_tu_phia_truoc():
    w, dock = _lone_dock()
    rb = Robot()
    s = SensorSuite(RobotSpec())
    rng = random.Random(2)
    mx, my = dock.mouth
    rb.reset(mx + 0.6, my, math.pi)       # doi dien cua hoc, nhin vao
    v, seen = s.read_ir(rb, w, rng)
    assert seen[IR_DOCK] > 0.5 and v[IR_DOCK] > 0.1
    rb.reset(2.2, 3.0, 0.0)               # sau lung hoc, nhin vao
    v, seen = s.read_ir(rb, w, rng)
    assert seen[IR_DOCK] < 0.5, "khong duoc thay den tu phia sau tram"
    # Hai vach ben bop chum hong ngoai lai: dung lech nhieu la mat tin hieu.
    # Day chinh la ly do xe phai vong ra doi dien cua hoc roi moi hoi IR.
    for deg, want in ((20, True), (65, False)):
        a = dock.heading + math.pi + math.radians(deg)
        x, y = mx + 0.6 * math.cos(a), my + 0.6 * math.sin(a)
        rb.reset(x, y, math.atan2(my - y, mx - x))
        v, seen = s.read_ir(rb, w, rng)
        assert (seen[IR_DOCK] > 0.5) is want, \
            "lech %d do: thay=%s ma mong doi %s" % (deg, seen[IR_DOCK], want)


def test_khong_bat_tay_hong_ngoai_thi_khong_sac():
    w = World(4.0, 4.0)
    dock = Dock(2.0, 2.0, math.pi)
    w.dock = dock
    rb = Robot()
    px, py = dock.pocket
    rb.reset(px, py, dock.heading, 0.3)
    assert rb.try_charge(w, 0.05, ir_ok=False) == 0.0
    assert rb.try_charge(w, 0.05, ir_ok=True) > 0.0


def test_odometry_troi_nhung_van_bam_theo():
    rb = Robot()
    rng = random.Random(5)
    rb.reset(1.0, 1.0, 0.0, 1.0, rng)
    w = World(20.0, 20.0)
    travelled = 0.0
    for _ in range(200):
        px, py = rb.x, rb.y
        rb.step(0.8, 0.8, 0.05, w, rng)
        travelled += math.hypot(rb.x - px, rb.y - py)
    err = math.hypot(rb.x - rb.ox, rb.y - rb.oy)
    assert err > 0.0, "odometry phai troi chu khong the chinh xac tuyet doi"
    assert err < 0.25 * travelled, "troi %.2f m tren %.2f m la qua nhieu" % (
        err, travelled)


def test_nho_vi_tri_tram_sac_sau_khi_sac():
    env = CarEnv(EnvConfig(stage=3, max_steps=60))
    for seed in range(40):
        env.reset(seed)
        if env.world.dock is None:
            continue
        d = env.world.dock
        px, py = d.pocket
        env.robot.reset(px, py, d.heading, 0.3, env.rng)
        env.per.ir_hand = env.per.steps   # gia lap vua bat tay hong ngoai xong
        env.step((0.0, 0.0))
        assert env.mem is not None, "sac xong phai nho vi tri tram"
        # lui ra 0.6 m roi hoi lai: tri nho phai chi nguoc ve phia tram
        back = d.heading + math.pi
        env.robot.ox += 0.6 * math.cos(back)
        env.robot.oy += 0.6 * math.sin(back)
        dist, bear, head = env._memory_polar()
        assert 0.4 < dist < 0.8, dist
        assert abs(bear) < 0.3, bear
        # nho ca HUONG TRUC: hoc chi chui vao duoc tu mot phia
        assert abs(wrap_angle(head - (d.heading - env.robot.oth))) < 0.2, head
        return
    raise AssertionError("khong sinh duoc canh nao co tram sac")


def test_uoc_luong_pin_ve_tram():
    env = CarEnv(EnvConfig(stage=3, max_steps=80))
    env.reset(3)
    env.per.mem = (env.robot.ox + 2.0, env.robot.oy, env.robot.oth)
    far = env._return_margin(2.0)
    near = env._return_margin(0.2)
    assert near > far, "cang xa tram thi bien an toan cang mong"


def test_luu_va_nap_lai_bo_nao():
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=7)
    obs = [0.1] * OBS_DIM
    a1 = pol.act(obs)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "w.npz")
        pol.save(p, gen=3, stage=2)
        pol2, meta = GRUPolicy.load(p)
    pol2.reset()
    assert np.allclose(a1, pol2.act(obs)) and int(meta["gen"]) == 3


def test_gru_co_tri_nho():
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=11)
    obs = [0.3] * OBS_DIM
    a1 = pol.act(obs)
    for _ in range(5):
        pol.act([0.9] * OBS_DIM)
    assert not np.allclose(a1, pol.act(obs))


def test_es_cai_thien_ham_don_gian():
    target = np.linspace(-1, 1, 25)

    def fit(x):
        return -float(np.sum((x - target) ** 2))

    es = ES(np.zeros(25), popsize=32, sigma=0.15, lr=0.12, weight_decay=0.0)
    first = fit(es.theta)
    for _ in range(120):
        es.tell([fit(p) for p in es.ask()])
    assert fit(es.theta) > first * 0.2


def test_ghi_hinh_tap():
    env = make_env(stage=3, max_steps=60, record=True)
    pol = GRUPolicy(OBS_DIM, 2, 8, seed=1)
    rollout(pol, env, 9)
    rec = env.episode_record()
    assert rec["frames"]
    f = rec["frames"][0]
    for k in ("x", "y", "th", "cliff", "ir", "u", "batt", "cand"):
        assert k in f
    assert any("scan" in fr for fr in rec["frames"])


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
