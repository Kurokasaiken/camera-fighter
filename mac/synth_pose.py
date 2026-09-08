"""Generatore di pose sintetiche — PLAN-048d, test offline senza hardware.

Persona in vista laterale (rivolta a +x): produce frame landmark 33x[x,y,conf]
stile ML Kit (x,y in 0..1, conf = inFrameLikelihood).
Script: 'idle', 'single_punch', 'double_jab', 'walk', 'random', 'guard'.
"""

from __future__ import annotations

import math
import random

NOSE, LSH, RSH, LEL, REL, LWR, RWR = 0, 11, 12, 13, 14, 15, 16
LHIP, RHIP, LKNEE, RKNEE, LANK, RANK = 23, 24, 25, 26, 27, 28


def base_pose(cx=0.5, cy=0.55, torso=0.22):
    """Pose eretta laterale, persona verso +x (destra)."""
    lm = [[cx, cy, 0.9] for _ in range(33)]
    lm[NOSE] = [cx + 0.02, cy - torso * 1.15, 0.9]
    lm[LSH] = [cx, cy - torso, 0.9]
    lm[RSH] = [cx + 0.01, cy - torso, 0.9]
    lm[LEL] = [cx + 0.03, cy - torso * 0.55, 0.85]
    lm[REL] = [cx + 0.05, cy - torso * 0.55, 0.85]
    lm[LWR] = [cx + 0.05, cy - torso * 0.15, 0.85]
    lm[RWR] = [cx + 0.08, cy - torso * 0.15, 0.85]
    lm[LHIP] = [cx, cy, 0.9]
    lm[RHIP] = [cx + 0.01, cy, 0.9]
    lm[LKNEE] = [cx + 0.02, cy + torso * 0.9, 0.85]
    lm[RKNEE] = [cx + 0.04, cy + torso * 0.9, 0.85]
    lm[LANK] = [cx + 0.02, cy + torso * 1.8, 0.8]
    lm[RANK] = [cx + 0.05, cy + torso * 1.8, 0.8]
    return lm


def add_noise(lm, rng, sigma=0.004, conf_jitter=0.05):
    out = []
    for x, y, c in lm:
        out.append([x + rng.gauss(0, sigma), y + rng.gauss(0, sigma),
                    max(0.0, min(1.0, c + rng.gauss(0, conf_jitter)))])
    return out


def punch_traj(phase, wrist0, reach=0.28):
    """phase 0..1: estensione avanti (+x) e retrazione."""
    ext = math.sin(math.pi * phase)          # 0->1->0
    return [wrist0[0] + reach * ext, wrist0[1], wrist0[2]]


def gen_script(kind: str, n: int = 120, seed: int = 0):
    """Ritorna lista di pacchetti {'seq','ts','landmarks','valid'}."""
    rng = random.Random(seed)
    base = base_pose()
    frames = []
    ts = 0
    for i in range(n):
        lm = [p[:] for p in base]
        conf = 0.9

        if kind == "idle":
            pass  # solo rumore
        elif kind == "single_punch":
            if 40 <= i < 50:
                lm[RWR] = punch_traj((i - 40) / 9.0, base[RWR])
                lm[REL] = punch_traj((i - 40) / 9.0, base[REL], reach=0.15)
        elif kind == "double_jab":
            if 30 <= i < 40:                      # jab destro
                lm[RWR] = punch_traj((i - 30) / 9.0, base[RWR])
            if 50 <= i < 60:                      # cross sinistro
                lm[LWR] = punch_traj((i - 50) / 9.0, base[LWR])
                lm[LEL] = punch_traj((i - 50) / 9.0, base[LEL], reach=0.15)
        elif kind == "walk":
            sway = math.sin(i * 0.3) * 0.02
            for j in (LANK, RANK):
                lm[j][0] += sway
            for j in (LKNEE, RKNEE):
                lm[j][0] += sway * 0.5
        elif kind == "random":
            for j in (LWR, RWR, LANK, RANK):
                lm[j][0] += rng.uniform(-0.05, 0.05)
                lm[j][1] += rng.uniform(-0.05, 0.05)
        elif kind == "guard":
            lm[LWR] = [base[LSH][0] + 0.10, base[LSH][1] + 0.05, 0.85]
            lm[RWR] = [base[RSH][0] + 0.10, base[RSH][1] + 0.05, 0.85]

        frames.append({"seq": i, "ts": ts,
                       "landmarks": add_noise(lm, rng),
                       "valid": True})
        ts += 33
    return frames


def gen_trace(kind, n=120, seed=0, loss=0.0, reorder=0.0):
    """Pacchetti + eventuali perdite/riordini per testare il jitter buffer."""
    rng = random.Random(seed + 999)
    frames = gen_script(kind, n, seed)
    frames = [f for f in frames if rng.random() >= loss]
    i = 0
    while i < len(frames) - 1:
        if rng.random() < reorder:
            frames[i], frames[i + 1] = frames[i + 1], frames[i]
            i += 2
        else:
            i += 1
    return frames
