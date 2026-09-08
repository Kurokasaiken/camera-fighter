"""T-003 — Rapporto lunghezze articolari vs prior anatomico (PLAN-048e).

Per ogni osso: lunghezza mediana/p10/p90 in unita' di torso (spine
hip_center -> shoulder_center, come build_body_frame) su frame VALID con
conf >= BONE_MIN_CONF ai due capi.

Confronto vs prior anatomico (DIAGNOSTICO, non target):
  upper_arm ~0.55, forearm ~0.45, thigh ~1.0, shin ~0.95, spine 1.0, hip_w ~0.5

Verdetto es-ante (soglia R pre-registrata): "uniforme" se la dispersione
relativa degli errori (|obs/prior - 1|) sta entro R_UNIFORM — altrimenti la
candidate e' per-segmento.

Con --constraint on|off confronta anche BoneConstraint ON vs OFF:
errore lunghezza, errore direzionale (deg vs direzione osservata raw),
errore endpoint.

Uso: venv/bin/python analyze_geometry.py visual_live.trace [--constraint off]
"""

from __future__ import annotations

import math
import sys

import msgpack

from body_model import build_body_frame, BoneConstraint, BONES, \
    BONE_MIN_CONF
from landmarks import (
    LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_WRIST, RIGHT_WRIST, LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE,
)

NAMES = {
    (LEFT_SHOULDER, LEFT_ELBOW): "upper_arm_L",
    (LEFT_ELBOW, LEFT_WRIST): "forearm_L",
    (RIGHT_SHOULDER, RIGHT_ELBOW): "upper_arm_R",
    (RIGHT_ELBOW, RIGHT_WRIST): "forearm_R",
    (LEFT_HIP, LEFT_KNEE): "thigh_L",
    (LEFT_KNEE, LEFT_ANKLE): "shin_L",
    (RIGHT_HIP, RIGHT_KNEE): "thigh_R",
    (RIGHT_KNEE, RIGHT_ANKLE): "shin_R",
    (LEFT_SHOULDER, RIGHT_SHOULDER): "shoulder_w",
    (LEFT_HIP, RIGHT_HIP): "hip_w",
}
PRIOR = {  # diagnostico, non target
    "upper_arm_L": 0.55, "upper_arm_R": 0.55,
    "forearm_L": 0.45, "forearm_R": 0.45,
    "thigh_L": 1.0, "thigh_R": 1.0,
    "shin_L": 0.95, "shin_R": 0.95,
    "shoulder_w": 0.55, "hip_w": 0.5,
}
R_UNIFORM = 0.30   # soglia ex-ante: dispersione relativa errori < 30%


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p / 100 * len(s)))] if s else 0.0


def analyze(path: str, constraint: bool):
    entries = msgpack.unpackb(open(path, "rb").read(), raw=False)
    bones = BoneConstraint()
    lens = {n: [] for n in NAMES.values()}
    dir_err = {n: [] for n in NAMES.values()}   # deg, solo se constraint
    end_err = {n: [] for n in NAMES.values()}
    used = 0

    for e in entries:
        pkt = e["payload"]
        raw = build_body_frame(pkt, e["seq_id"], False)
        if not raw.valid:
            continue
        f = bones.apply(raw) if constraint else raw
        used += 1
        for (a, b), name in NAMES.items():
            if raw.conf[a] < BONE_MIN_CONF or raw.conf[b] < BONE_MIN_CONF:
                continue
            ax, ay = raw.pos[a]; bx, by = raw.pos[b]
            raw_d = math.hypot(bx - ax, by - ay)
            if raw_d < 1e-6:
                continue
            cx, cy = f.pos[a]; dx, dy = f.pos[b]
            d = math.hypot(dx - cx, dy - cy)
            lens[name].append(d)
            if constraint and d > 1e-6:
                cos = ((bx - ax) * (dx - cx) + (by - ay) * (dy - cy)) \
                    / (raw_d * d)
                cos = max(-1.0, min(1.0, cos))
                dir_err[name].append(math.degrees(math.acos(cos)))
                end_err[name].append(
                    math.hypot(dx - bx, dy - cy))

    print(f"trace={path} frames_used={used} constraint={'ON' if constraint else 'OFF'}")
    print(f"{'segment':<14} {'n':>5} {'p10':>6} {'med':>6} {'p90':>6} "
          f"{'prior':>5} {'ratio':>6} {'direrr':>7} {'enderr':>7}")
    rel_errs = []
    for (a, b), name in NAMES.items():
        xs = lens[name]
        if not xs:
            continue
        med = pct(xs, 50)
        ratio = med / PRIOR[name] if PRIOR[name] else 0
        rel_errs.append(abs(ratio - 1.0))
        print(f"{name:<14} {len(xs):>5} {pct(xs,10):6.2f} {med:6.2f} "
              f"{pct(xs,90):6.2f} {PRIOR[name]:5.2f} {ratio:6.2f} "
              f"{pct(dir_err[name],50) if dir_err[name] else 0:7.1f} "
              f"{pct(end_err[name],50) if end_err[name] else 0:7.3f}")
    if rel_errs:
        disp = max(rel_errs)
        verdict = ("UNIFORME -> scalare unico" if disp < R_UNIFORM
                   else "NON UNIFORME -> candidate per-segmento (da congelare)")
        print(f"\ndispersione relativa errori = {disp:.2f} "
              f"(R_UNIFORM={R_UNIFORM}) -> {verdict}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "visual_live.trace"
    con = "--constraint" in sys.argv and "on" in sys.argv
    analyze(path, con)
