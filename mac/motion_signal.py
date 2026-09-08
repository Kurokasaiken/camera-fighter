"""MotionSignal — PLAN-048d / PLAN-048e T-002.

Derivata robusta per action, su TEMPO REALE (capture_ts del telefono):
  VALID+ELIGIBLE   -> velocity = dPos / dt_s   [unita' di torso / secondo]
  dt <= 0 (clock)  -> escluso: velocity=0, ref NON avanza (bug o perdita;
                      distinguiamo il gap per CAUSA, non per ampiezza)
  VALID+INELIGIBLE -> hold (non avanza il riferimento)
  INVALID/boundary -> velocity=0, reference=null
I gap di pacchetto non producono derivata: il jitter buffer marca boundary
sui salti di seq, quindi il riferimento non attraversa mai un hole UDP.
Median (finestra 3) + EMA leggero. Kinetic energy = somma |v|^2 arti.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from body_model import BodyFrame, eligible, limb_point, REQUIRED_LANDMARKS

ACTIONS = list(REQUIRED_LANDMARKS.keys())
# Punto distale primario: calci sulla CAVIGLIA quando visibile, altrimenti
# fallback sul GINOCCHIO. La scelta deve essere identica su entrambi i campioni
# della derivata (altrimenti salto di posizione finto).
from landmarks import RIGHT_ANKLE, LEFT_ANKLE

ANKLE_OF = {"kick_right": RIGHT_ANKLE, "kick_left": LEFT_ANKLE}
DISTAL = {"punch_right": "right_wrist", "punch_left": "left_wrist",
          "kick_right": "right_ankle", "kick_left": "left_ankle"}
KICK_FALLBACK = {"kick_right": "right_knee", "kick_left": "left_knee"}
ANKLE_CONF = 0.6


def distal_limb(action: str, f: "BodyFrame", ref) -> str:
    """Caviglia se confidente su f E su ref; altrimenti ginocchio (kick)."""
    ankle = ANKLE_OF.get(action)
    if ankle is None:
        return DISTAL[action]
    if ref is not None and f.conf[ankle] >= ANKLE_CONF and \
       ref.conf[ankle] >= ANKLE_CONF:
        return DISTAL[action]
    return KICK_FALLBACK[action]

MEDIAN_WIN = 3
EMA_ALPHA = 0.4
OCCLUSION_RECOVERY_FRAMES = 3  # hold velocity=0 per N frame post-reset


@dataclass(frozen=True)
class MotionSample:
    seq_id: int
    velocity: dict          # action -> (vx, vy) all'estremo distale
    energy: float           # somma |v|^2
    valid: bool
    boundary: bool


class MotionSignal:
    def __init__(self):
        self.last_ref = {a: None for a in ACTIONS}      # last_derivative_valid[action]
        self.vel_raw = {a: deque(maxlen=MEDIAN_WIN) for a in ACTIONS}
        self.vel_ema = {a: (0.0, 0.0) for a in ACTIONS}
        self._recovery_left = 0
        self.invalid_dt = 0            # clock regressioni escluse (T-002)

    def reset(self):
        self.last_ref = {a: None for a in ACTIONS}
        self.vel_raw = {a: deque(maxlen=MEDIAN_WIN) for a in ACTIONS}
        self.vel_ema = {a: (0.0, 0.0) for a in ACTIONS}
        self._recovery_left = OCCLUSION_RECOVERY_FRAMES

    def update(self, f: BodyFrame) -> MotionSample:
        if f.boundary:
            self.reset()
            # boundary_forced consumato: primo frame post-boundary -> v=0
            return MotionSample(f.seq_id, {a: (0.0, 0.0) for a in ACTIONS},
                                0.0, f.valid, True)

        recovery = self._recovery_left > 0
        self._recovery_left = max(0, self._recovery_left - 1)
        velocity = {}

        for action in ACTIONS:
            if not f.valid:
                velocity[action] = (0.0, 0.0)
                self.last_ref[action] = None
                continue
            if not eligible(f, action):
                velocity[action] = self.vel_ema[action]  # hold, no ref update
                continue
            ref = self.last_ref[action]
            # fallback caviglia->ginocchio: stessa scelta su ENTRAMBI i campioni
            # (invariante: identica definizione di posizione ai due capi)
            limb = distal_limb(action, f, ref)
            if ref is None:
                velocity[action] = (0.0, 0.0)
            else:
                dt_ms = f.capture_ts - ref.capture_ts   # T-002: tempo reale
                if dt_ms <= 0:
                    # clock regression / dt invalido: escluso, ref non avanza
                    self.invalid_dt += 1
                    velocity[action] = (0.0, 0.0)
                    continue
                p0 = limb_point(ref, limb)
                p1 = limb_point(f, limb)
                v = ((p1[0] - p0[0]) * 1000.0 / dt_ms,
                     (p1[1] - p0[1]) * 1000.0 / dt_ms)   # u/s
                # median su finestra 3
                dq = self.vel_raw[action]
                dq.append(v)
                med = tuple(sorted(c[i] for c in dq)[len(dq) // 2]
                            for i in range(2))
                # EMA leggero
                e = self.vel_ema[action]
                self.vel_ema[action] = (EMA_ALPHA * med[0] + (1 - EMA_ALPHA) * e[0],
                                        EMA_ALPHA * med[1] + (1 - EMA_ALPHA) * e[1])
                velocity[action] = self.vel_ema[action]
            self.last_ref[action] = f

        if recovery:
            velocity = {a: (0.0, 0.0) for a in ACTIONS}

        energy = sum(vx * vx + vy * vy for vx, vy in velocity.values())
        return MotionSample(f.seq_id, velocity, energy, f.valid, f.boundary)
