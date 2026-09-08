"""Pipeline orchestrator — PLAN-048d: i 3 signal path paralleli.

RawPoseFrame (da JitterBuffer) ->
    BodyModel  -> BodyFrame
    -> VisualPose   (avatar: restituisce BodyFrame grezzo, il renderer filtra)
    -> MotionSignal -> Segmenter -> MotionEvent -> ComboEngine -> COMMIT
    -> HitSignal    -> HitEvent -> CombatBridge

VisualPose e' indipendente: se il matcher fallisce, l'avatar funziona.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from body_model import build_body_frame, BodyFrame, BoneConstraint
from motion_signal import MotionSignal, DISTAL
from segmentation import Segmenter, MotionEvent
from combo_engine import ComboEngine, ComboCommit
from hit_signal import HitSignal, HitEvent
from leg_tracker import LegTracker
from z_gate import ZGate
from jitter_buffer import EmittedFrame

# Strike zone in unita' di torso davanti al busto (lato +x), calibrata su
# reach reale: i pugni veri arrivano a x~0.2-0.4, estensione piena ~0.8.
DEFAULT_HITBOX = (0.18, -1.0, 0.7, 1.4)

# Joint per HitSignal: calci = caviglia primaria, ginocchio fallback.
from landmarks import (RIGHT_ANKLE, LEFT_ANKLE, RIGHT_KNEE, LEFT_KNEE)
ACTION_JOINT = {
    "punch_right": ("right_wrist", None, None, None),
    "punch_left": ("left_wrist", None, None, None),
    "kick_right": ("right_ankle", "right_knee", RIGHT_ANKLE, RIGHT_KNEE),
    "kick_left": ("left_ankle", "left_knee", LEFT_ANKLE, LEFT_KNEE),
}


@dataclass
class FrameOutput:
    """Output deterministico per un frame emesso — base del gate A==B."""
    seq_id: int
    boundary: bool
    avatar_frame: BodyFrame | None
    motion_events: list = field(default_factory=list)
    hit_events: list = field(default_factory=list)
    commits: list = field(default_factory=list)


class Pipeline:
    def __init__(self, combos_path: str | None = None,
                 hitbox=DEFAULT_HITBOX,
                 calibration_path: str = "calibration.json"):
        # T-008: se esiste una calibrazione congelata, la hitbox diventa la
        # capsula spalla->polso+envelope invece del rettangolo di default.
        if hitbox == DEFAULT_HITBOX:
            import json as _json, os as _os
            if _os.path.exists(calibration_path):
                c = _json.load(open(calibration_path)).get("capsule")
                if c:
                    from capsule import Capsule
                    hitbox = Capsule(c["ax"], c["ay"], c["bx"], c["by"],
                                     c["radius"])
        self.motion = MotionSignal()
        self.segmenter = Segmenter()
        self.combo = ComboEngine(combos_path)
        self.hit = {a: HitSignal(a, j, hitbox, fb, ji, fi)
                    for a, (j, fb, ji, fi) in ACTION_JOINT.items()}
        self.legs = LegTracker()
        self.leg_unreliable_frames = 0
        self.bones = BoneConstraint()
        self.zgate = ZGate()          # T-005: osserva soltanto (soglia provv.)
        self.outputs: list[FrameOutput] = []

    def process(self, ef: EmittedFrame) -> FrameOutput:
        """Consuma un frame emesso dal jitter buffer. Deterministico."""
        pkt = ef.frame if isinstance(ef.frame, dict) else {}
        # identita' gambe: swap/merge -> ricostruzione fisica (gamba piantata
        # congelata, gamba attiva segue detection; conf ridotta = estimated)
        reliable, recon, _active = self.legs.update(pkt.get("landmarks", []))
        if not reliable and recon is not None:
            self.leg_unreliable_frames += 1
            pkt = dict(pkt)
            pkt["landmarks"] = recon
        bf = build_body_frame(pkt, ef.seq_id, ef.boundary)
        bf = self.bones.apply(bf)   # rigidita' ossea: anti foreshortening
        self.zgate.update(bf)       # T-005: misura affidabilita' z (no gating ancora)

        # --- MotionSignal -> segment -> combo ---
        ms = self.motion.update(bf)
        mev = self.segmenter.update(bf, ms)
        motion_events = [mev] if mev else []
        commits = []
        if mev:
            c = self.combo.update(mev, bf.capture_ts)
            if c:
                commits.append(c)

        # --- HitSignal parallelo (raw + conf, mai attraversa boundary) ---
        hit_events = []
        for action, hs in self.hit.items():
            v = ms.velocity.get(action, (0.0, 0.0))
            hev = hs.update(bf, v)
            if hev:
                hit_events.append(hev)

        # --- VisualPose: BodyFrame grezzo per l'avatar (sempre presente) ---
        out = FrameOutput(seq_id=ef.seq_id, boundary=ef.boundary,
                          avatar_frame=bf, motion_events=motion_events,
                          hit_events=hit_events, commits=commits)
        self.outputs.append(out)
        return out


def fingerprint(outputs: list[FrameOutput]) -> list:
    """Firma osservabile per il gate di determinismo."""
    fp = []
    for o in outputs:
        fp.append((
            o.seq_id, o.boundary,
            tuple((m.action, m.direction, round(m.peak_speed, 3))
                  for m in o.motion_events),
            tuple((h.joint, h.seq_id) for h in o.hit_events),
            tuple(c.combo_id for c in o.commits),
        ))
    return fp
