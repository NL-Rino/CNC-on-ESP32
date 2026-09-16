"""Doc/ghi mot MAT BANG do nguoi dung tu ve (tools/studio.py).

Mo phong sinh canh ngau nhien thi tot cho viec nuoi, nhung de xem xe chay
trong dung can nha cua minh thi phai ve duoc. File JSON, don vi MET, goc toa
do o goc duoi ben trai.

    {"width": 5.0, "height": 4.0, "boundary": "wall",
     "obstacles": [{"kind":"box","x0":1,"y0":1,"x1":2,"y1":1.4}, ...],
     "bays":      [{"x":4.6,"y":2.0,"heading":0.0,"tag":"dock"}],
     "movers":    [{"x":1,"y":3,"r":0.2,"speed":0.9,"heading":1.57}]}
"""
import json
import math
import os

from .world import Bay, Dock, Mover, Obstacle, World

DEFAULT_MOVER_R = 0.20      # nguoi di lai, tinh theo be ngang hai chan
DEFAULT_MOVER_V = 0.85      # m/s - nhip di bo trong nha


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path, layout):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=1)


def validate(layout):
    """Tra ve danh sach loi. Rong nghia la dung dung duoc."""
    errs = []
    w = float(layout.get("width", 0))
    h = float(layout.get("height", 0))
    if not (1.0 <= w <= 30.0) or not (1.0 <= h <= 30.0):
        errs.append("kich thuoc phong phai trong khoang 1-30 m (dang %.1f x %.1f)"
                    % (w, h))
    if layout.get("boundary", "wall") not in ("wall", "cliff"):
        errs.append("boundary phai la 'wall' hoac 'cliff'")
    docks = [b for b in layout.get("bays", []) if b.get("tag", "dock") == "dock"]
    if len(docks) > 1:
        errs.append("chi duoc mot tram sac that (cac hoc con lai de tag='decoy')")
    for i, b in enumerate(layout.get("bays", [])):
        # Hoc rong 40 cm -> tam phai cach tuong it nhat 20 cm
        if not (0.2 <= float(b.get("x", -1)) <= w - 0.2 and
                0.2 <= float(b.get("y", -1)) <= h - 0.2):
            errs.append("hoc #%d nam ngoai phong" % (i + 1))
    return errs


def build_world(layout, rng=None):
    """Dung World tu mat bang. rng chi dung cho vat di chuyen."""
    w = World(float(layout["width"]), float(layout["height"]),
              boundary=layout.get("boundary", "wall"))
    if w.boundary == "wall":
        w.add_boundary_walls()
    for o in layout.get("obstacles", []):
        if o.get("kind") == "circle":
            w.add_obstacle(Obstacle("circle", tag=o.get("tag", ""),
                                    x=float(o["x"]), y=float(o["y"]),
                                    r=float(o["r"])))
        else:
            x0, x1 = sorted((float(o["x0"]), float(o["x1"])))
            y0, y1 = sorted((float(o["y0"]), float(o["y1"])))
            w.add_obstacle(Obstacle("box", tag=o.get("tag", ""),
                                    x0=x0, y0=y0, x1=x1, y1=y1))
    for b in layout.get("bays", []):
        tag = b.get("tag", "dock")
        x, y, hd = float(b["x"]), float(b["y"]), float(b.get("heading", 0.0))
        if tag == "dock" and w.dock is None:
            d = Dock(x, y, hd)
            w.dock = d
            w.add_bay(d)
            w.beacons.append(d.beacon)
        else:
            w.add_bay(Bay(x, y, hd, tag="decoy"))
    for m in layout.get("movers", []):
        w.add_mover(Mover(float(m["x"]), float(m["y"]),
                          float(m.get("r", DEFAULT_MOVER_R)),
                          float(m.get("speed", DEFAULT_MOVER_V)),
                          float(m.get("heading", 0.0))))
    w.bake()
    return w


def from_world(world, name="mat-bang"):
    """Nguoc lai: xuat mot canh mo phong ra mat bang de mo trong trinh ve."""
    bay_walls = {id(wl) for b in world.bays for wl in b.walls}
    mover_obs = {id(m.ob) for m in world.movers}
    return {
        "name": name,
        "width": round(world.width, 3),
        "height": round(world.height, 3),
        "boundary": world.boundary,
        "obstacles": [o.as_dict() for o in world.obstacles
                      if id(o) not in bay_walls and id(o) not in mover_obs
                      and o.tag != "wall"],
        "bays": [{"x": round(b.x, 3), "y": round(b.y, 3),
                  "heading": round(b.heading, 4), "tag": b.tag}
                 for b in world.bays],
        "movers": [{"x": round(m.ob.x, 3), "y": round(m.ob.y, 3),
                    "r": round(m.ob.r, 3), "speed": round(m.speed, 3),
                    "heading": round(math.atan2(m.vy, m.vx), 4)}
                   for m in world.movers],
    }
