"""Feature extraction da landmark normalizzati."""

import math

from landmarks import (
    NOSE,
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_WRIST, RIGHT_WRIST,
    LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_ANKLE, RIGHT_ANKLE,
)


def _point(lm, idx):
    return (lm[idx][0], lm[idx][1]) if len(lm) > idx else (0.0, 0.0)


def _conf(lm, idx):
    return lm[idx][2] if len(lm) > idx else 0.0


def _angle(a, b, c):
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos = max(-1, min(1, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos))


def _conf_weight(lm, indices):
    confs = [lm[i][2] for i in indices if i < len(lm)]
    return min(confs) if confs else 0.0


def extract(lm: list) -> dict:
    """Estrae un feature vector da un singolo frame di landmark."""
    if not lm or len(lm) < 28:
        return {}

    rw = _point(lm, RIGHT_WRIST)
    re = _point(lm, RIGHT_ELBOW)
    rs = _point(lm, RIGHT_SHOULDER)
    lw = _point(lm, LEFT_WRIST)
    le = _point(lm, LEFT_ELBOW)
    ls = _point(lm, LEFT_SHOULDER)
    rk = _point(lm, RIGHT_KNEE)
    rh = _point(lm, RIGHT_HIP)
    ra = _point(lm, RIGHT_ANKLE)
    lk = _point(lm, LEFT_KNEE)
    lh = _point(lm, LEFT_HIP)
    la = _point(lm, LEFT_ANKLE)
    nose = _point(lm, NOSE)

    features = {
        # Posizioni relative normalizzate
        "right_wrist_x": rw[0],
        "right_wrist_y": rw[1],
        "right_wrist_ahead_elbow": rw[0] - re[0],
        "right_wrist_ahead_shoulder": rw[0] - rs[0],
        "right_wrist_above_shoulder": rs[1] - rw[1],

        "left_wrist_x": lw[0],
        "left_wrist_y": lw[1],
        "left_wrist_ahead_elbow": lw[0] - le[0],
        "left_wrist_ahead_shoulder": lw[0] - ls[0],
        "left_wrist_above_shoulder": ls[1] - lw[1],

        "right_knee_x": rk[0],
        "right_knee_y": rk[1],
        "right_knee_above_hip": rh[1] - rk[1],
        "right_ankle_x": ra[0],
        "right_ankle_y": ra[1],

        "left_knee_x": lk[0],
        "left_knee_y": lk[1],
        "left_knee_above_hip": lh[1] - lk[1],
        "left_ankle_x": la[0],
        "left_ankle_y": la[1],

        "nose_x": nose[0],
        "nose_y": nose[1],

        # Angoli articolari
        "right_elbow_angle": _angle(rs, re, rw),
        "left_elbow_angle": _angle(ls, le, lw),
        "right_knee_angle": _angle(rh, rk, ra),
        "left_knee_angle": _angle(lh, lk, la),

        # Confidenze minime (per pesare)
        "right_arm_conf": _conf_weight(lm, [RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST]),
        "left_arm_conf": _conf_weight(lm, [LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST]),
        "right_leg_conf": _conf_weight(lm, [RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE]),
        "left_leg_conf": _conf_weight(lm, [LEFT_HIP, LEFT_KNEE, LEFT_ANKLE]),
    }

    return features
