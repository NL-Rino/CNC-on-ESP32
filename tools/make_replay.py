"""Nhoi du lieu tap mo phong vao mot file HTML doc lap de xem tren trinh duyet.

    python3 -m train.evaluate --policy runs/car/best.npz --record demo.json
    python3 tools/make_replay.py demo.json viz/replay.html
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "viz", "replay_template.html")


def build(json_path, out_path):
    with open(json_path) as f:
        data = json.load(f)
    with open(TEMPLATE) as f:
        html = f.read()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    marker = "/*__DATA__*/"
    i = html.index(marker)
    j = html.index(";", i)
    html = html[:i] + blob + html[j:]
    with open(out_path, "w") as f:
        f.write(html)
    n = sum(len(e["frames"]) for e in data.get("episodes", []))
    print("da tao %s (%d tap, %d khung hinh, %.1f KB)"
          % (out_path, len(data.get("episodes", [])), n,
             os.path.getsize(out_path) / 1024))


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "demo.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "viz/replay.html"
    build(src, dst)
