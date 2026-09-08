"""T-005 — Rejection gate su z di ML Kit (PLAN-048e).

Lo z di position3D e' una stima euristica instabile: si usa SOLO dove la
varianza per-landmark su finestra mobile e' sotto soglia pre-registrata.
Sopra soglia il landmark e' marcato z-unreliable e la pipeline resta al 2D
+ BoneConstraint — degradazione controllata, non dipendenza instabile.

Gate articolato per SEGMENTO (braccia/gambe/torso), non reject globale.
Assenza di z (vecchie tracce, 3 elementi) => sempre unreliable, mai fidato.

La soglia Z_STD_MAX e' PROVVISORIA: va misurata sul calibration set e
congelata nel freeze artifact prima dell'evaluation (regole del piano).
"""

from __future__ import annotations

from collections import deque

from landmarks import (
    LEFT_WRIST, RIGHT_WRIST, LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_ANKLE, RIGHT_ANKLE, LEFT_KNEE, RIGHT_KNEE,
    LEFT_HIP, RIGHT_HIP, LEFT_SHOULDER, RIGHT_SHOULDER,
)

Z_WINDOW = 15          # finestra mobile per la varianza (pre-registrata)
Z_STD_MAX = 60.0       # mm — PROVVISORIO, da misurare su calibration set
Z_MIN_ABS = 1e-6       # z tutto zero = traccia senza z -> unreliable

SEGMENTS = {
    "arms":  (LEFT_WRIST, RIGHT_WRIST, LEFT_ELBOW, RIGHT_ELBOW),
    "legs":  (LEFT_ANKLE, RIGHT_ANKLE, LEFT_KNEE, RIGHT_KNEE),
    "torso": (LEFT_HIP, RIGHT_HIP, LEFT_SHOULDER, RIGHT_SHOULDER),
}


def _std(xs) -> float:
    n = len(xs)
    if n < 3:
        return float("inf")
    m = sum(xs) / n
    return (sum((x - m) ** 2 for x in xs) / n) ** 0.5


class ZGate:
    """Per landmark: finestra mobile di z -> reliable/unreliable."""

    def __init__(self):
        self.hist = {}            # idx -> deque di z
        self.reliable = {}        # idx -> bool
        self.dropped = 0          # frame in cui un landmark e' risultato unreliable

    def update(self, f) -> dict:
        """f: BodyFrame. Ritorna segment -> bool (True = z usabile)."""
        out = {}
        if not f.z:
            for seg in SEGMENTS:
                out[seg] = False
            return out
        for seg, idxs in SEGMENTS.items():
            ok = True
            for i in idxs:
                h = self.hist.setdefault(i, deque(maxlen=Z_WINDOW))
                h.append(f.z[i])
                r = _std(h) <= Z_STD_MAX and any(
                    abs(v) > Z_MIN_ABS for v in h)
                self.reliable[i] = r
                if not r:
                    self.dropped += 1
                    ok = False
            out[seg] = ok
        return out
