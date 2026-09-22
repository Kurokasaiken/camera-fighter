import math

from avatar_pose import AvatarPose, Point2D


ML_KIT_TO_AVATAR = {
    0: "nose",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
}


def _rotate_point(x, y, cx, cy, angle):
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dx = x - cx
    dy = y - cy
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


class LandmarkToAvatarMapper:
    def __init__(self, min_cutoff=2.0, beta=0.05, mirror_x=True):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.mirror_x = mirror_x
        self.filters = {}

    def _body_center_and_scale(self, landmarks):
        if not landmarks or len(landmarks) < 28:
            return (0.5, 0.5), 1.0, 0.0
        ls = landmarks[11]
        rs = landmarks[12]
        lh = landmarks[23]
        rh = landmarks[24]
        hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
        shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
        center = ((hip_mid[0] + shoulder_mid[0]) / 2,
                  (hip_mid[1] + shoulder_mid[1]) / 2)
        torso_h = ((shoulder_mid[0] - hip_mid[0]) ** 2 + (shoulder_mid[1] - hip_mid[1]) ** 2) ** 0.5
        scale = max(torso_h, 0.05)

        # Angolo del vettore fianchi -> spalle, misurato come atan2(dy, dx).
        # Nelle coord immagine y cresce verso il basso, quindi un torso dritto
        # punta verso -y e ha angolo -pi/2.
        torso_angle = math.atan2(shoulder_mid[1] - hip_mid[1],
                                 shoulder_mid[0] - hip_mid[0])
        # _rotate_point somma l'angolo al vettore: per portare il torso a -pi/2
        # serve la differenza fra angolo target e angolo attuale.
        return center, scale, -math.pi / 2 - torso_angle

    def _ensure_filter(self, idx):
        from landmark_filter import FilteredLandmark
        if idx not in self.filters:
            self.filters[idx] = FilteredLandmark(self.min_cutoff, self.beta)
        return self.filters[idx]

    def map(self, landmarks, timestamp):
        center, scale, angle = self._body_center_and_scale(landmarks)
        cx, cy = center
        pose = AvatarPose(timestamp=timestamp)

        for idx, attr in ML_KIT_TO_AVATAR.items():
            if idx >= len(landmarks):
                continue
            lm = landmarks[idx]
            x, y, conf = lm[0], lm[1], (lm[2] if len(lm) > 2 else 0.0)
            flt = self._ensure_filter(idx)
            xf, yf, conf_f, visible = flt.update(x, y, conf, timestamp)

            # Ruota per mettere il torso in verticale
            rx, ry = _rotate_point(xf, yf, cx, cy, angle)

            # Coordinate relative al centro, normalizzate
            px = (rx - cx) / scale
            py = (ry - cy) / scale

            # offset laterale: l'avatar segue lo spostamento del corpo
            # nell'inquadratura (unita' torso), cosi' e' speculare allo
            # scheletro grezzo invece di restare sempre centrato
            px += (cx - 0.5) / scale

            if self.mirror_x:
                px = -px

            setattr(pose, attr, Point2D(x=px, y=py, confidence=conf_f, visible=visible))

        # Anti "gomito sempre piegato": i filtri OneEuro sono per-joint, quindi
        # il polso parte prima del gomito e il braccio sembra piegato anche
        # quando e' disteso (dati reali: 43% frame con angolo >160).
        # Se l'angolo al gomito supera la soglia, il gomito va sulla retta
        # spalla->polso mantenendo la frazione di distanza osservata.
        self._straighten_arm(pose, "left_shoulder", "left_elbow", "left_wrist")
        self._straighten_arm(pose, "right_shoulder", "right_elbow", "right_wrist")

        # Anti "braccio accorciato quando alzo lateralmente": vincolo di lunghezza osso
        # ML Kit allucina profondità → articoli si accorciano. Forziamo lunghezze anatomiche
        # proporzionate al torso (identico a silhouette.py LEN dict).
        self._enforce_bone_length(pose, "left_shoulder", "left_elbow", "left_wrist", "left")
        self._enforce_bone_length(pose, "right_shoulder", "right_elbow", "right_wrist", "right")
        self._enforce_bone_length(pose, "left_hip", "left_knee", "left_ankle", "left")
        self._enforce_bone_length(pose, "right_hip", "right_knee", "right_ankle", "right")

        return pose

    # Lunghezze anatomiche fisse, identiche a silhouette.py LEN dict
    BONE_LEN = {
        ("left_shoulder", "left_elbow"): 0.50,
        ("left_elbow", "left_wrist"): 0.50,
        ("right_shoulder", "right_elbow"): 0.50,
        ("right_elbow", "right_wrist"): 0.50,
        ("left_hip", "left_knee"): 0.85,
        ("left_knee", "left_ankle"): 0.85,
        ("right_hip", "right_knee"): 0.85,
        ("right_knee", "right_ankle"): 0.85,
    }

    STRAIGHTEN_DEG = 165.0

    def _straighten_arm(self, pose, s_name, e_name, w_name):
        s, e, w = getattr(pose, s_name), getattr(pose, e_name), getattr(pose, w_name)
        v1 = (s.x - e.x, s.y - e.y)
        v2 = (w.x - e.x, w.y - e.y)
        n1 = math.hypot(*v1); n2 = math.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            return
        cos = max(-1.0, min(1.0, (v1[0]*v2[0] + v1[1]*v2[1]) / (n1*n2)))
        if math.degrees(math.acos(cos)) < self.STRAIGHTEN_DEG:
            return
        # braccio quasi disteso: gomito sulla retta spalla->polso
        dl = math.hypot(w.x - s.x, w.y - s.y)
        if dl < 1e-6:
            return
        t = n1 / (n1 + n2)          # frazione spalla->gomito lungo il braccio
        e.x = s.x + (w.x - s.x) * t
        e.y = s.y + (w.y - s.y) * t

    def _enforce_bone_length(self, pose, s_name, e_name, w_name, side):
        """Forza lunghezze anatomiche fisse: contrasta allucinazione ML Kit profondità.

        Quando il braccio esce dall'asse verticale, ML Kit allucina profondità →
        joint si accorciano. Questo vincolo mantiene lunghezze proporzionate al torso.
        """
        s = getattr(pose, s_name, None)
        e = getattr(pose, e_name, None)
        w = getattr(pose, w_name, None)
        if not (s and e and w):
            return

        # Lunghezze anatomiche in unita' torso
        l1_target = self.BONE_LEN.get((s_name, e_name), 0.5)
        l2_target = self.BONE_LEN.get((e_name, w_name), 0.5)

        # Estrai torso length dalle spalle/fianchi
        ls = getattr(pose, "left_shoulder", None)
        rs = getattr(pose, "right_shoulder", None)
        lh = getattr(pose, "left_hip", None)
        rh = getattr(pose, "right_hip", None)
        if not (ls and rs and lh and rh):
            return

        torso_length = math.hypot(
            (ls.x + rs.x) / 2 - (lh.x + rh.x) / 2,
            (ls.y + rs.y) / 2 - (lh.y + rh.y) / 2
        )
        if torso_length < 0.05:
            return

        l1_desired = l1_target * torso_length
        l2_desired = l2_target * torso_length

        # Direzione spalla->gomito, applica lunghezza desiderata
        dx1, dy1 = e.x - s.x, e.y - s.y
        d1 = math.hypot(dx1, dy1)
        if d1 > 0.001:
            e.x = s.x + (dx1 / d1) * l1_desired
            e.y = s.y + (dy1 / d1) * l1_desired

        # Direzione gomito->polso, applica lunghezza desiderata
        dx2, dy2 = w.x - e.x, w.y - e.y
        d2 = math.hypot(dx2, dy2)
        if d2 > 0.001:
            w.x = e.x + (dx2 / d2) * l2_desired
            w.y = e.y + (dy2 / d2) * l2_desired
