"""T-008 — Hitbox capsula (PLAN-048e).

La hitbox nemico non e' un rettangolo arbitrario ma una CAPSULA:
  jointA -> jointB (es. spalla -> polso esteso in guardia) + radius
radius = reach geometrico + incertezza di misura (error envelope),
calcolati ESCLUSIVAMENTE sul calibration set e congelati nel freeze
artifact. L'evaluation set misura la capsula, mai la ottimizza.

Unita' di torso, stesso dominio di HitSignal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _dist_point_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


@dataclass(frozen=True)
class Capsule:
    ax: float
    ay: float
    bx: float
    by: float
    radius: float

    def contains(self, px, py, extra=0.0) -> bool:
        return _dist_point_segment(px, py, self.ax, self.ay,
                                   self.bx, self.by) <= self.radius + extra

    def segment_hits(self, p0, p1, extra=0.0) -> bool:
        """Swept test: il segmento p0->p1 tocca la capsula (8 campioni)."""
        for i in range(9):
            t = i / 8.0
            x = p0[0] + (p1[0] - p0[0]) * t
            y = p0[1] + (p1[1] - p0[1]) * t
            if self.contains(x, y, extra):
                return True
        return False


def capsule_from_reach(shoulder, wrist, reach_extra: float,
                       envelope: float) -> Capsule:
    """Capsula spalla->polso esteso. reach_extra = quota di reach oltre il
    polso osservato in guardia; envelope = incertezza di misura."""
    return Capsule(ax=shoulder[0], ay=shoulder[1],
                   bx=wrist[0] + reach_extra, by=wrist[1],
                   radius=envelope)
