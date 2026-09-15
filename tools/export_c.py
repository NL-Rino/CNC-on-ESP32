"""Xuat trong so cua bo nao ra file .h de nap vao ESP32.

    python3 tools/export_c.py runs/car/best.npz firmware/policy_weights.h
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from train.policy import GRUPolicy  # noqa: E402


def fmt(arr, per_line=8):
    flat = np.asarray(arr, dtype=np.float32).ravel()
    out = []
    for i in range(0, flat.size, per_line):
        out.append("  " + ", ".join("%.6ff" % v for v in flat[i:i + per_line]))
    return ",\n".join(out)


def export(npz_path, out_path):
    pol, meta = GRUPolicy.load(npz_path)
    p = pol.p
    lines = [
        "// Tu dong sinh boi tools/export_c.py - KHONG sua tay.",
        "// Nguon: %s (gen=%s, stage=%s)" % (os.path.basename(npz_path),
                                            meta.get("gen", "?"), meta.get("stage", "?")),
        "#pragma once",
        "",
        "#define BRAIN_OBS %d" % pol.obs_dim,
        "#define BRAIN_ACT %d" % pol.act_dim,
        "#define BRAIN_HID %d" % pol.hidden,
        "",
    ]
    for name in ("Wz", "Uz", "bz", "Wr", "Ur", "br", "Wn", "Un", "bn", "Wo", "bo"):
        a = p[name]
        dims = "[%d]" % a.size
        lines.append("static const float BRAIN_%s%s = {" % (name, dims))
        lines.append(fmt(a))
        lines.append("};")
        lines.append("")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print("da xuat %s (%d tham so, %.1f KB)"
          % (out_path, pol.n_params, os.path.getsize(out_path) / 1024))


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "runs/car/best.npz"
    dst = sys.argv[2] if len(sys.argv) > 2 else "firmware/policy_weights.h"
    export(src, dst)
