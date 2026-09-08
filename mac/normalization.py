"""Normalizzazione dei landmark corporei per Camera Fighter."""

import math

from landmarks import LEFT_HIP, RIGHT_HIP, LEFT_SHOULDER, RIGHT_SHOULDER


def normalize(landmarks: list) -> list:
    """Normalizza i landmark rispetto a hip center e torso length.

    landmarks: lista di [x, y, c]
    Restituisce lista di [nx, ny, c]
    """
    if not landmarks or len(landmarks) < 12:
        return []

    left_hip = landmarks[LEFT_HIP]
    right_hip = landmarks[RIGHT_HIP]
    left_shoulder = landmarks[LEFT_SHOULDER]
    right_shoulder = landmarks[RIGHT_SHOULDER]

    if any(c < 0.3 for _, _, c in (left_hip, right_hip, left_shoulder, right_shoulder)):
        # fallback: usa hip se spalle non sono affidabili
        hip_center = (left_hip[0], left_hip[1])
        scale = 0.3  # default
    else:
        hip_center = ((left_hip[0] + right_hip[0]) / 2,
                      (left_hip[1] + right_hip[1]) / 2)
        shoulder_center = ((left_shoulder[0] + right_shoulder[0]) / 2,
                           (left_shoulder[1] + right_shoulder[1]) / 2)
        scale = math.dist(hip_center, shoulder_center)

    if scale == 0:
        scale = 1.0

    normalized = []
    for x, y, c in landmarks:
        nx = (x - hip_center[0]) / scale
        ny = (y - hip_center[1]) / scale
        normalized.append([nx, ny, c])

    return normalized
