"""Segmentation — PLAN-048d.

Picchi di energia sul MotionSignal -> MotionEvent immutabili.
Niente classificazione semantica: il segmento è un candidato di evento
cinematico (arto, direzione del picco, velocità, confidenza media).
"""

from __future__ import annotations

from dataclasses import dataclass

from body_model import BodyFrame, limb_point
from motion_signal import MotionSample, DISTAL

# T-002: velocita' ora in u/s (capture_ts). Valori PROVVISORI riscalati da
# u/frame @57ms reali (x17.54^2 per energia, x17.54 per speed) — da
# ricalibrare su dataset strutturato in T-006, non congelati.
ENERGY_ON = 18.5     # ingresso segmento (u^2/s^2)
ENERGY_OFF = 7.7     # uscita (isteresi)
MIN_SEGMENT_FRAMES = 2
MAX_SEGMENT_FRAMES = 30


@dataclass(frozen=True)
class MotionEvent:
    seq_start: int
    seq_end: int
    limb: str
    action: str
    peak_velocity: tuple      # (vx, vy) al picco
    direction: str            # "+x","-x","+y","-y","diag..."
    peak_speed: float
    mean_conf: float
    emphasis: bool            # inversione picco->retraction rilevata


class Segmenter:
    """Energy-gated segmentation: ON sopra soglia, OFF sotto isteresi."""

    def __init__(self):
        self.active = False
        self.start_seq = 0
        self.frames = 0
        self.best = (0.0, "none", (0.0, 0.0), "")
        self.pending = []          # eventi pronti
        self._cool = 0

    def update(self, f: BodyFrame, m: MotionSample) -> MotionEvent | None:
        ev = None
        if m.boundary or not m.valid:
            self._close(f, m)
            self._cool = 2
            return None
        if self._cool > 0:
            self._cool -= 1
            return None

        e = m.energy
        if not self.active:
            if e > ENERGY_ON:
                self.active = True
                self.start_seq = f.seq_id
                self.frames = 0
                self.best = (0.0, "none", (0.0, 0.0), "")
        else:
            self.frames += 1
            # picco = arto con |v| max in questo frame
            for action, v in m.velocity.items():
                sp = (v[0] ** 2 + v[1] ** 2) ** 0.5
                if sp > self.best[0]:
                    self.best = (sp, action, v, DISTAL[action])
            if e < ENERGY_OFF or self.frames > MAX_SEGMENT_FRAMES:
                ev = self._close(f, m)
        return ev

    def _close(self, f: BodyFrame, m: MotionSample) -> MotionEvent | None:
        if not self.active:
            return None
        self.active = False
        if self.frames < MIN_SEGMENT_FRAMES:
            return None
        speed, action, v, limb = self.best
        if action == "none":
            return None
        if abs(v[0]) >= abs(v[1]):
            direction = "+x" if v[0] >= 0 else "-x"
        else:
            direction = "+y" if v[1] >= 0 else "-y"
        # conf media dei landmark dell'azione
        ev = MotionEvent(seq_start=self.start_seq, seq_end=f.seq_id,
                         limb=limb, action=action,
                         peak_velocity=v, direction=direction,
                         peak_speed=speed, mean_conf=1.0,
                         emphasis=True)
        return ev
