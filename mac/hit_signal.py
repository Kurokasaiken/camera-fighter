"""HitSignal — PLAN-048d S3: swept hit test.

Segmento (prev_pos -> curr_pos) interseca hitbox espansa.
Mai attraversa: gap seq_id, INVALID, INELIGIBLE, tracker change, boundary.
HitGate refractory per arto. Retroattività gestita da combat_bridge.
"""

from __future__ import annotations

from dataclasses import dataclass

from body_model import BodyFrame, limb_point, eligible

HITBOX_RADIUS_U = 0.11
HITBOX_EXPANSION = 0.05      # espansione per swept test
# T-002: u/s. Provvisorio: 0.35 u/frame @57ms -> ~6.1 u/s. Da ricalibrare T-006.
MIN_IMPACT_SPEED = 6.1       # |v| minima (u/s): p90 pugno reale ~7
HIT_GATE_SEQ = 4             # refractory ~4 frame (~230ms a 17fps reali)


@dataclass(frozen=True)
class HitEvent:
    seq_id: int
    joint: str
    x: float
    y: float
    speed: float
    boundary_reset: bool


def _segment_hits_box(p0, p1, box, radius):
    """True se il segmento p0->p1 entra nella zona espansa di radius.
    `box` puo' essere una tupla (x,y,w,h) legacy oppure una Capsule (T-008).
    Campionamento a 8 punti (spike: sufficiente e deterministico)."""
    from capsule import Capsule
    if isinstance(box, Capsule):
        return box.segment_hits(p0, p1, extra=radius)
    bx, by, bw, bh = box
    r = radius
    for i in range(9):
        t = i / 8.0
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        if (bx - r) <= x <= (bx + bw + r) and (by - r) <= y <= (by + bh + r):
            return True
    return False


class HitSignal:
    """Un'istanza per action (punch_right, ...). Mantiene l'ultimo frame
    ELIGIBLE per quell'azione. joint_fallback: se il joint primario ha
    conf < 0.6 su uno dei due capi, usa il fallback (stessa scelta su
    entrambi i capi, come la derivata)."""

    def __init__(self, action: str, joint: str, hitbox,
                 joint_fallback: str | None = None,
                 joint_conf_idx: int | None = None,
                 fallback_conf_idx: int | None = None):
        self.action = action
        self.joint = joint            # es. 'right_wrist' / 'right_ankle'
        self.joint_fallback = joint_fallback
        self.joint_idx = joint_conf_idx
        self.fallback_idx = fallback_conf_idx
        self.hitbox = hitbox          # (x, y, w, h) in unita' di torso
        self.last_eligible: BodyFrame | None = None
        self.last_hit_seq = -10**9

    def _pick_joint(self, f: BodyFrame, prev: BodyFrame) -> str:
        if (self.joint_fallback and self.joint_idx is not None
                and not (f.conf[self.joint_idx] >= 0.6
                         and prev.conf[self.joint_idx] >= 0.6)):
            return self.joint_fallback
        return self.joint

    def update(self, f: BodyFrame, velocity) -> HitEvent | None:
        """velocity = (vx,vy) per questa action dal MotionSignal."""
        if f.boundary:
            self.last_eligible = None
            return None
        if not f.valid or not eligible(f, self.action):
            return None  # INELIGIBLE/INVALID: nessuno sweep, no ref update

        prev = self.last_eligible
        self.last_eligible = f
        if prev is None:
            return None
        # swept richiede adiacenza + stesso tracker
        if f.seq_id != prev.seq_id + 1:
            return None
        if f.tracker_id != prev.tracker_id:
            return None

        speed = (velocity[0] ** 2 + velocity[1] ** 2) ** 0.5
        if speed < MIN_IMPACT_SPEED:
            return None
        if f.seq_id - self.last_hit_seq < HIT_GATE_SEQ:
            return None

        joint = self._pick_joint(f, prev)
        p0 = limb_point(prev, joint)
        p1 = limb_point(f, joint)
        if _segment_hits_box(p0, p1, self.hitbox,
                             HITBOX_RADIUS_U + HITBOX_EXPANSION):
            self.last_hit_seq = f.seq_id
            return HitEvent(f.seq_id, joint, p1[0], p1[1],
                            round(speed, 3), False)
        return None
