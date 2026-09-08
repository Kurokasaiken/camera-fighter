"""Calcolo qualita della posa e warning per Camera Fighter."""

import math

# Landmark indices ML Kit Pose (33 landmark)
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28

CORE_LANDMARKS = [
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_WRIST, RIGHT_WRIST,
    LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_ANKLE, RIGHT_ANKLE,
]

WARNING_LABELS = {
    NOSE: "testa",
    LEFT_WRIST: "polso sinistro",
    RIGHT_WRIST: "polso destro",
    LEFT_ANKLE: "caviglia sinistra",
    RIGHT_ANKLE: "caviglia destra",
    LEFT_KNEE: "ginocchio sinistro",
    RIGHT_KNEE: "ginocchio destro",
}


def compute_quality(landmarks: list, required: list = None) -> dict:
    """Restituisce qualita e warning per una lista di landmark.

    landmarks: lista di [x, y, c]
    """
    if not landmarks:
        return {
            "score": 0.0,
            "label": "NO POSE",
            "color": (255, 0, 0),
            "visible": 0,
            "total": 0,
            "warnings": ["nessun landmark ricevuto"],
        }

    indices = required if required is not None else CORE_LANDMARKS
    confidences = []
    warnings = []

    for idx in indices:
        if idx < len(landmarks):
            c = landmarks[idx][2]
            confidences.append(c)
            if c < 0.5:
                name = WARNING_LABELS.get(idx, f"giuntura {idx}")
                warnings.append(f"{name} non visibile")
        else:
            confidences.append(0.0)

    score = sum(confidences) / len(confidences) if confidences else 0.0

    if score > 0.80:
        label = "OTTIMO"
        color = (0, 255, 0)
    elif score > 0.55:
        label = "ACCETTABILE"
        color = (255, 255, 0)
    else:
        label = "SCARSO"
        color = (255, 80, 80)

    visible = sum(1 for c in confidences if c > 0.5)

    return {
        "score": score,
        "label": label,
        "color": color,
        "visible": visible,
        "total": len(confidences),
        "warnings": warnings[:3],
    }


def body_in_frame(landmarks: list) -> bool:
    """Verifica che almeno testa e bacino siano nel frame."""
    if not landmarks or len(landmarks) < max(CORE_LANDMARKS) + 1:
        return False
    nose = landmarks[NOSE][2]
    left_hip = landmarks[LEFT_HIP][2]
    right_hip = landmarks[RIGHT_HIP][2]
    return nose > 0.5 and (left_hip > 0.5 or right_hip > 0.5)
