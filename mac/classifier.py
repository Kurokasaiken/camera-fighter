import json
import time
from collections import deque

from calibration import FEATURES
from landmarks import (
    NOSE,
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ELBOW,
    RIGHT_ELBOW,
    LEFT_WRIST,
    RIGHT_WRIST,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
)


def point(landmarks, idx):
    if idx >= len(landmarks):
        return (0.0, 0.0, 0.0)
    return (landmarks[idx][0], landmarks[idx][1], landmarks[idx][2])


def dist_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


class Classifier:
    def __init__(self, calibration_path: str = None):
        self.history = deque(maxlen=10)
        self.smooth = []
        self.last_event_time = 0.0
        self.cooldown = 0.5  # secondi
        self.hysteresis = 0.02
        self.guard = False  # per la parata: transizione
        self.last_event = ""
        self.calibration = {}
        if calibration_path:
            self.load(calibration_path)

    def load(self, path: str):
        with open(path) as f:
            self.calibration = json.load(f)

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.calibration, f, indent=2)

    def _smoothed(self, landmarks: list) -> list:
        """Media mobile su 3 frame per ridurre rumore."""
        if not self.smooth:
            return landmarks
        n = len(landmarks)
        out = []
        for i in range(n):
            xs = [landmarks[i][0], self.smooth[i][0]]
            ys = [landmarks[i][1], self.smooth[i][1]]
            cs = [landmarks[i][2], self.smooth[i][2]]
            out.append([sum(xs) / 2, sum(ys) / 2, sum(cs) / 2])
        return out

    def update(self, landmarks: list, timestamp: float = None) -> str:
        if timestamp is None:
            timestamp = time.time()

        if not landmarks or len(landmarks) < 33:
            return ""

        # Smoothing
        smooth = self._smoothed(landmarks)
        self.smooth = smooth

        self.history.append((timestamp, smooth))

        if timestamp - self.last_event_time < self.cooldown:
            return ""

        if self.calibration:
            return self._match_calibrated(smooth, timestamp)
        else:
            return self._match_default(smooth, timestamp)

    def _velocity(self, idx: int, axis: str = "x") -> float:
        if len(self.history) < 2:
            return 0.0
        p_now = point(self.history[-1][1], idx)
        p_prev = point(self.history[-2][1], idx)
        dt = self.history[-1][0] - self.history[-2][0]
        if dt <= 0:
            return 0.0
        if axis == "x":
            return (p_now[0] - p_prev[0]) / dt
        return (p_now[1] - p_prev[1]) / dt

    def _avg_velocity(self, idx: int, n: int = 3, axis: str = "x") -> float:
        if len(self.history) < 2:
            return 0.0
        n = min(n, len(self.history) - 1)
        total = 0.0
        for i in range(1, n + 1):
            p_now = point(self.history[-i][1], idx)
            p_prev = point(self.history[-i - 1][1], idx)
            dt = self.history[-i][0] - self.history[-i - 1][0]
            if dt > 0:
                if axis == "x":
                    total += (p_now[0] - p_prev[0]) / dt
                else:
                    total += (p_now[1] - p_prev[1]) / dt
        return total / n

    def _match_default(self, landmarks: list, timestamp: float) -> str:
        rw = point(landmarks, RIGHT_WRIST)
        re = point(landmarks, RIGHT_ELBOW)
        lw = point(landmarks, LEFT_WRIST)
        le = point(landmarks, LEFT_ELBOW)
        rk = point(landmarks, RIGHT_KNEE)
        rh = point(landmarks, RIGHT_HIP)
        ra = point(landmarks, RIGHT_ANKLE)
        lk = point(landmarks, LEFT_KNEE)
        lh = point(landmarks, LEFT_HIP)
        la = point(landmarks, LEFT_ANKLE)
        nose = point(landmarks, NOSE)
        r_shoulder = point(landmarks, RIGHT_SHOULDER)
        l_shoulder = point(landmarks, LEFT_SHOULDER)

        # Velocità medie per pugni e calci
        v_rw_x = self._avg_velocity(RIGHT_WRIST, n=2, axis="x")
        v_lw_x = self._avg_velocity(LEFT_WRIST, n=2, axis="x")
        v_rk_x = self._avg_velocity(RIGHT_KNEE, n=2, axis="x")
        v_rk_y = self._avg_velocity(RIGHT_KNEE, n=2, axis="y")
        v_lk_x = self._avg_velocity(LEFT_KNEE, n=2, axis="x")
        v_lk_y = self._avg_velocity(LEFT_KNEE, n=2, axis="y")

        # Pugno destro: A → B con velocita, estensione, polso avanti
        right_punch_forward = v_rw_x > 0.7 and rw[0] > re[0] + 0.1
        right_arm_extends = rw[0] > r_shoulder[0] + 0.05
        right_punch = right_punch_forward and right_arm_extends

        # Pugno sinistro
        left_punch_forward = v_lw_x > 0.7 and lw[0] > le[0] + 0.1
        left_arm_extends = lw[0] > l_shoulder[0] + 0.05
        left_punch = left_punch_forward and left_arm_extends

        # Calcio destro: ginocchio avanza e sale, caviglia avanza
        right_kick_forward = v_rk_x > 0.3 and rk[0] > rh[0] + 0.05
        right_kick_up = v_rk_y < -0.25 and rk[1] < rh[1] - 0.05
        right_ankle_forward = ra[0] > rh[0] + 0.05
        right_kick = right_kick_forward and right_kick_up and right_ankle_forward

        # Calcio sinistro
        left_kick_forward = v_lk_x > 0.3 and lk[0] > lh[0] + 0.05
        left_kick_up = v_lk_y < -0.25 and lk[1] < lh[1] - 0.05
        left_ankle_forward = la[0] > lh[0] + 0.05
        left_kick = left_kick_forward and left_kick_up and left_ankle_forward

        # Parata: transizione. La mano entra nella guard zone (alta e vicino al viso)
        right_hand_guard = rw[1] < r_shoulder[1] - 0.05 and abs(rw[0] - nose[0]) < 0.15
        left_hand_guard = lw[1] < l_shoulder[1] - 0.05 and abs(lw[0] - nose[0]) < 0.15
        guard_now = right_hand_guard and left_hand_guard

        block_trigger = False
        if guard_now and not self.guard:
            block_trigger = True
        self.guard = guard_now

        # Schivata laterale: naso si sposta in x rapidamente
        v_nose_x = self._velocity(NOSE, "x")
        dodge = abs(v_nose_x) > 1.2

        # Arbitration: ogni frame puo avere un solo evento
        if right_punch:
            self.last_event_time = timestamp
            return "PUGNO DESTRO"
        if left_punch:
            self.last_event_time = timestamp
            return "PUGNO SINISTRO"
        if right_kick:
            self.last_event_time = timestamp
            return "CALCIO DESTRO"
        if left_kick:
            self.last_event_time = timestamp
            return "CALCIO SINISTRO"
        if block_trigger:
            self.last_event_time = timestamp
            return "PARATA"
        if dodge:
            self.last_event_time = timestamp
            return "SCHIVATA"

        return ""

    def _match_calibrated(self, landmarks, timestamp):
        if not self.calibration:
            return self._match_default(landmarks, timestamp)

        best_move = ""
        best_score = 0
        for move, data in self.calibration.items():
            features = data.get("features", [])
            ranges = data.get("ranges", {})
            if not features:
                continue
            matched = 0
            for f in features:
                if f not in FEATURES:
                    continue
                r = ranges.get(f, {})
                lo = r.get("min", 0.0) - self.hysteresis
                hi = r.get("max", 1.0) + self.hysteresis
                v = FEATURES[f](landmarks)
                if lo <= v <= hi:
                    matched += 1
            if matched == len(features) and matched > best_score:
                best_move = move
                best_score = matched

        if best_move:
            self.last_event_time = timestamp
            return best_move.upper()

        return self._match_default(landmarks, timestamp)
