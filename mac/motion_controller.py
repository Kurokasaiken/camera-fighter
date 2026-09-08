"""Motion controller a bassa latenza: onset detection per pugni e calci."""

import json
import math
from dataclasses import dataclass
from enum import Enum

from landmarks import (
    LEFT_ANKLE, RIGHT_ANKLE,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_WRIST, RIGHT_WRIST,
    LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_HIP, RIGHT_HIP,
)


class State(Enum):
    IDLE = "idle"
    WINDUP = "windup"
    COOLDOWN = "cooldown"


@dataclass
class MotionEvent:
    limb: str
    side: str
    type: str
    direction: str
    confidence: float
    timestamp: int


def _angle(a: tuple, b: tuple, c: tuple) -> float:
    """Angolo al punto b, in gradi."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])
    if mag1 == 0 or mag2 == 0:
        return 180.0
    cos = max(-1, min(1, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos))


class LimbTracker:
    """Traccia posizione, velocita e accelerazione di un landmark."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.smoothed = None
        self.prev_pos = None
        self.prev_time = None
        self.velocity = 0.0
        self.acceleration = 0.0
        self.speed_history = []

    def update(self, pos: float, now_ms: int):
        """pos: coordinata normalizzata (x o y). now_ms: timestamp."""
        if self.smoothed is None:
            self.smoothed = pos
        else:
            self.smoothed = self.smoothed * (1 - self.alpha) + pos * self.alpha

        if self.prev_pos is None or self.prev_time is None:
            self.prev_pos = self.smoothed
            self.prev_time = now_ms
            return

        dt = max((now_ms - self.prev_time) / 1000.0, 0.008)
        new_velocity = (self.smoothed - self.prev_pos) / dt

        self.acceleration = (new_velocity - self.velocity) / dt
        self.velocity = new_velocity
        self.prev_pos = self.smoothed
        self.prev_time = now_ms

        self.speed_history.append(abs(self.velocity))
        if len(self.speed_history) > 3:
            self.speed_history.pop(0)

    def avg_speed(self) -> float:
        if not self.speed_history:
            return 0.0
        return sum(self.speed_history) / len(self.speed_history)


class OnsetDetector:
    """FSM per rilevare l'inizio di un colpo da un arto."""

    def __init__(self,
                 speed_threshold: float = 1.8,
                 accel_threshold: float = 10.0,
                 extension_threshold: float = 0.12,
                 cooldown_ms: int = 180,
                 min_angle: float = 0.0,
                 expected_sign: int = 0):
        self.speed_threshold = speed_threshold
        self.accel_threshold = accel_threshold
        self.extension_threshold = extension_threshold
        self.cooldown_ms = cooldown_ms
        self.min_angle = min_angle
        self.expected_sign = expected_sign  # -1 = sinistra, +1 = destra, 0 = qualsiasi

        self.state = State.IDLE
        self.state_time = 0
        self.last_event_time = -100_000
        self.fast_frames = 0
        self.tracker = LimbTracker(alpha=0.3)
        self.direction_tracker = LimbTracker(alpha=0.3)

    def update(self, pos: float, reference: float, now_ms: int, limb: str, side: str, angle: float = None) -> MotionEvent:
        self.tracker.update(pos, now_ms)
        self.direction_tracker.update(pos, now_ms)

        speed = self.tracker.avg_speed()
        raw_speed = abs(self.tracker.velocity)
        velocity = self.direction_tracker.velocity
        accel = abs(self.tracker.acceleration)
        extension = abs(pos - reference)

        # COOLDOWN -> IDLE
        if self.state == State.COOLDOWN:
            if now_ms - self.state_time >= self.cooldown_ms:
                self.state = State.IDLE
            else:
                return None

        # IDLE -> WINDUP
        if self.state == State.IDLE:
            direction_ok = (self.expected_sign == 0 or
                            (self.expected_sign < 0 and velocity < 0) or
                            (self.expected_sign > 0 and velocity > 0))
            if speed > self.speed_threshold and direction_ok:
                self.fast_frames += 1
                if self.fast_frames >= 2:
                    self.state = State.WINDUP
                    self.state_time = now_ms
                    self.fast_frames = 0
            else:
                self.fast_frames = 0
            return None

        # WINDUP -> STRIKE
        if self.state == State.WINDUP:
            direction_ok = (self.expected_sign == 0 or
                            (self.expected_sign < 0 and velocity < 0) or
                            (self.expected_sign > 0 and velocity > 0))
            angle_ok = (angle is None or self.min_angle <= 0 or angle >= self.min_angle)
            if (speed > self.speed_threshold and
                    raw_speed > self.speed_threshold and
                    extension > self.extension_threshold and
                    angle_ok and
                    direction_ok and
                    now_ms - self.last_event_time > 100):
                self.state = State.COOLDOWN
                self.state_time = now_ms
                self.last_event_time = now_ms

                direction = "RIGHT" if self.direction_tracker.velocity > 0 else "LEFT"
                confidence = min(1.0, speed / (self.speed_threshold * 2.0))

                return MotionEvent(
                    limb=limb,
                    side=side,
                    type="STRIKE",
                    direction=direction,
                    confidence=confidence,
                    timestamp=now_ms,
                )

            # candidato scomparso
            if now_ms - self.state_time > 180:
                self.state = State.IDLE

        return None


class MotionController:
    """Controlla 4 arti e classifica pugni/calci."""

    def __init__(self, config_path: str = "techniques.json"):
        self.config = self._load_config(config_path)
        self.global_cooldown_ms = 120
        self.last_global_event = -100_000
        pc = self.config["punch"]
        kc = self.config["kick"]

        # Personaggio rivolto a destra:
        # - arto destro si muove in avanti verso sinistra (v < 0)
        # - arto sinistro si muove in avanti verso destra (v > 0)
        self.detectors = {
            "right_hand": OnsetDetector(
                speed_threshold=pc.get("min_wrist_speed", 3.0),
                accel_threshold=pc.get("min_wrist_accel", 12.0),
                extension_threshold=pc.get("min_wrist_extension", 0.15),
                cooldown_ms=pc.get("cooldown_ms", 250),
                min_angle=pc.get("min_elbow_angle", 140),
                expected_sign=-1,
            ),
            "left_hand": OnsetDetector(
                speed_threshold=pc.get("min_wrist_speed", 3.0),
                accel_threshold=pc.get("min_wrist_accel", 12.0),
                extension_threshold=pc.get("min_wrist_extension", 0.15),
                cooldown_ms=pc.get("cooldown_ms", 250),
                min_angle=pc.get("min_elbow_angle", 140),
                expected_sign=+1,
            ),
            "right_foot": OnsetDetector(
                speed_threshold=kc.get("min_ankle_speed", 2.5),
                accel_threshold=kc.get("min_ankle_accel", 10.0),
                extension_threshold=kc.get("min_ankle_extension", 0.18),
                cooldown_ms=kc.get("cooldown_ms", 300),
                min_angle=kc.get("min_knee_angle", 140),
                expected_sign=-1,
            ),
            "left_foot": OnsetDetector(
                speed_threshold=kc.get("min_ankle_speed", 2.5),
                accel_threshold=kc.get("min_ankle_accel", 10.0),
                extension_threshold=kc.get("min_ankle_extension", 0.18),
                cooldown_ms=kc.get("cooldown_ms", 300),
                min_angle=kc.get("min_knee_angle", 140),
                expected_sign=+1,
            ),
        }

    def _load_config(self, path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "punch": {
                    "min_elbow_angle": 140,
                    "min_wrist_speed": 3.0,
                    "min_wrist_accel": 12.0,
                    "min_wrist_extension": 0.15,
                    "cooldown_ms": 250,
                },
                "kick": {
                    "min_knee_angle": 140,
                    "min_ankle_speed": 2.5,
                    "min_ankle_accel": 10.0,
                    "min_ankle_extension": 0.18,
                    "cooldown_ms": 300,
                },
            }

    def _point(self, lm: list, idx: int):
        if idx < len(lm):
            return (lm[idx][0], lm[idx][1])
        return (0.0, 0.0)

    def _conf(self, lm: list, idx: int) -> float:
        return lm[idx][2] if idx < len(lm) else 0.0

    def _normalize(self, lm: list) -> dict:
        """Restituisce landmark normalizzati rispetto a torso."""
        if not lm or len(lm) < 28:
            return {}

        ls = self._point(lm, LEFT_SHOULDER)
        rs = self._point(lm, RIGHT_SHOULDER)
        lh = self._point(lm, LEFT_HIP)
        rh = self._point(lm, RIGHT_HIP)

        hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
        shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)

        torso_h = math.hypot(shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1])
        if torso_h == 0:
            torso_h = 1.0

        def norm(idx: int):
            x, y = self._point(lm, idx)
            return {
                "x": (x - hip_mid[0]) / torso_h,
                "y": (y - hip_mid[1]) / torso_h,
                "c": self._conf(lm, idx),
            }

        return {
            "left_wrist": norm(LEFT_WRIST),
            "right_wrist": norm(RIGHT_WRIST),
            "left_ankle": norm(LEFT_ANKLE),
            "right_ankle": norm(RIGHT_ANKLE),
            "left_knee": norm(LEFT_KNEE),
            "right_knee": norm(RIGHT_KNEE),
            "left_elbow": norm(LEFT_ELBOW),
            "right_elbow": norm(RIGHT_ELBOW),
            "left_shoulder": norm(LEFT_SHOULDER),
            "right_shoulder": norm(RIGHT_SHOULDER),
            "left_hip": norm(LEFT_HIP),
            "right_hip": norm(RIGHT_HIP),
            "hip_mid": hip_mid,
            "torso_h": torso_h,
        }

    def update(self, lm: list, now_ms: int) -> list:
        """Riceve 33 landmark e restituisce 0 o 1 MotionEvent (migliore)."""
        if now_ms - self.last_global_event < self.global_cooldown_ms:
            return []

        candidates = []
        norm = self._normalize(lm)
        if not norm:
            return []

        # Pugni: polso vs spalla
        for side in ("right", "left"):
            wrist = norm[f"{side}_wrist"]
            shoulder = norm[f"{side}_shoulder"]

            if wrist["c"] < 0.5 or shoulder["c"] < 0.5:
                continue

            detector = self.detectors[f"{side}_hand"]
            ev = detector.update(wrist["x"], shoulder["x"], now_ms, limb="hand", side=side)
            if ev:
                ev.type = "PUNCH"
                candidates.append(ev)

        # Calci: caviglia vs anca; il ginocchio deve alzarsi
        for side in ("right", "left"):
            ankle = norm[f"{side}_ankle"]
            knee = norm[f"{side}_knee"]
            hip = norm[f"{side}_hip"]

            if ankle["c"] < 0.5 or knee["c"] < 0.5 or hip["c"] < 0.5:
                continue

            # Il ginocchio deve salire (y decresce in coordinate normalizzate)
            if knee["y"] > hip["y"] - 0.15:
                continue

            detector = self.detectors[f"{side}_foot"]
            ev = detector.update(ankle["x"], hip["x"], now_ms, limb="foot", side=side)
            if ev:
                ev.type = self._classify_kick(norm, side)
                candidates.append(ev)

        if not candidates:
            return []

        best = max(candidates, key=lambda e: e.confidence)
        self.last_global_event = now_ms
        return [best]

    def _classify_kick(self, norm: dict, side: str) -> str:
        """Euristica semplice: frontale vs laterale dal ginocchio."""
        knee = norm[f"{side}_knee"]
        ankle = norm[f"{side}_ankle"]
        other_hip_key = "right_hip" if side == "left" else "left_hip"
        other_hip = norm[other_hip_key]

        # Laterale: ginocchio si sposta lateralmente rispetto all'altra anca
        knee_lateral = abs(knee["x"] - other_hip["x"])
        # Frontale: ginocchio va avanti (x decresce per personaggio rivolto a destra)
        knee_forward = -knee["x"]

        if knee_lateral > 0.25:
            return "SIDE_KICK"
        if knee_forward > 0.20:
            return "FRONT_KICK"
        return "KICK"
