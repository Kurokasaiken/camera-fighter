"""Calcola e disegna un avatar 2D laterale dai landmark ML Kit."""

import math

from landmarks import (
    LEFT_ANKLE, LEFT_ELBOW, LEFT_HIP, LEFT_KNEE,
    LEFT_SHOULDER, LEFT_WRIST,
    RIGHT_ANKLE, RIGHT_ELBOW, RIGHT_HIP, RIGHT_KNEE,
    RIGHT_SHOULDER, RIGHT_WRIST,
)


def _point(lm, idx):
    return (lm[idx][0], lm[idx][1]) if idx < len(lm) else (0.0, 0.0)


def _conf(lm, idx):
    return lm[idx][2] if idx < len(lm) else 0.0


def _angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _mirror_x(x, width):
    return (1 - x) * width


def _y(y, height):
    return y * height


def _segment(start, angle, length):
    return start[0] + math.cos(angle) * length, start[1] + math.sin(angle) * length


def _scale(lm):
    if not lm or len(lm) < 28:
        return 1.0
    ls = _point(lm, LEFT_SHOULDER)
    rs = _point(lm, RIGHT_SHOULDER)
    lh = _point(lm, LEFT_HIP)
    rh = _point(lm, RIGHT_HIP)
    hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
    shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
    torso_h = math.hypot(shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1])
    return max(torso_h, 0.01)


def build_avatar(lm, width, height):
    """Restituisce dizionario con punti dell'avatar in pixel."""
    scale = _scale(lm)
    if scale == 1.0 or not lm:
        return None

    # Pixel per unità di torso
    px_per_u = min(width, height) / 6.0

    def to_px(p):
        return (_mirror_x(p[0], width), _y(p[1], height))

    hip_mid = to_px(((_point(lm, LEFT_HIP)[0] + _point(lm, RIGHT_HIP)[0]) / 2,
                     (_point(lm, LEFT_HIP)[1] + _point(lm, RIGHT_HIP)[1]) / 2))
    shoulder_mid = to_px(((_point(lm, LEFT_SHOULDER)[0] + _point(lm, RIGHT_SHOULDER)[0]) / 2,
                          (_point(lm, LEFT_SHOULDER)[1] + _point(lm, RIGHT_SHOULDER)[1]) / 2))

    # Angoli dei segmenti del giocatore (in coordinate immagine)
    r_arm_angle = _angle(_point(lm, RIGHT_SHOULDER), _point(lm, RIGHT_ELBOW))
    r_forearm_angle = _angle(_point(lm, RIGHT_ELBOW), _point(lm, RIGHT_WRIST))
    l_arm_angle = _angle(_point(lm, LEFT_SHOULDER), _point(lm, LEFT_ELBOW))
    l_forearm_angle = _angle(_point(lm, LEFT_ELBOW), _point(lm, LEFT_WRIST))
    r_leg_angle = _angle(_point(lm, RIGHT_HIP), _point(lm, RIGHT_KNEE))
    r_shin_angle = _angle(_point(lm, RIGHT_KNEE), _point(lm, RIGHT_ANKLE))
    l_leg_angle = _angle(_point(lm, LEFT_HIP), _point(lm, LEFT_KNEE))
    l_shin_angle = _angle(_point(lm, LEFT_KNEE), _point(lm, LEFT_ANKLE))

    # Mappa in avatar 2D laterale, centrato
    torso_len = scale * px_per_u
    arm_len = torso_len * 0.6
    forearm_len = torso_len * 0.5
    leg_len = torso_len * 0.7
    shin_len = torso_len * 0.7
    head_r = torso_len * 0.25

    center_x = width // 2
    center_y = int(height * 0.65)

    avatar = {
        "head_center": (center_x, int(center_y - torso_len - head_r * 0.8)),
        "head_r": head_r,
        "shoulder": (center_x, int(center_y - torso_len)),
        "hip": (center_x, center_y),
    }

    # Braccia
    sa = avatar["shoulder"]
    avatar["right_elbow"] = _segment(sa, -r_arm_angle, arm_len)
    avatar["right_wrist"] = _segment(avatar["right_elbow"], -r_forearm_angle, forearm_len)
    avatar["left_elbow"] = _segment(sa, -l_arm_angle, arm_len)
    avatar["left_wrist"] = _segment(avatar["left_elbow"], -l_forearm_angle, forearm_len)

    # Gambe
    hp = avatar["hip"]
    avatar["right_knee"] = _segment(hp, -r_leg_angle, leg_len)
    avatar["right_ankle"] = _segment(avatar["right_knee"], -r_shin_angle, shin_len)
    avatar["left_knee"] = _segment(hp, -l_leg_angle, leg_len)
    avatar["left_ankle"] = _segment(avatar["left_knee"], -l_shin_angle, shin_len)

    # Hitbox (pugni e piedi)
    avatar["hitboxes"] = [
        {"x": avatar["right_wrist"][0], "y": avatar["right_wrist"][1], "r": head_r * 0.6, "limb": "right_hand"},
        {"x": avatar["left_wrist"][0], "y": avatar["left_wrist"][1], "r": head_r * 0.6, "limb": "left_hand"},
        {"x": avatar["right_ankle"][0], "y": avatar["right_ankle"][1], "r": head_r * 0.7, "limb": "right_foot"},
        {"x": avatar["left_ankle"][0], "y": avatar["left_ankle"][1], "r": head_r * 0.7, "limb": "left_foot"},
    ]

    return avatar


def check_hits(avatar, enemy):
    """enemy = {'x', 'y', 'w', 'h'}. Restituisce lista di hit."""
    if not avatar or "hitboxes" not in avatar:
        return []
    hits = []
    ex, ey, ew, eh = enemy["x"], enemy["y"], enemy["w"], enemy["h"]
    for hb in avatar["hitboxes"]:
        if ex < hb["x"] < ex + ew and ey < hb["y"] < ey + eh:
            hits.append(hb["limb"])
    return hits
