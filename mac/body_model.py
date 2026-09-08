"""Body Model — PLAN-048d S1.

RawPoseFrame -> BodyFrame: frame body-centric 2D (primario; ML Kit Z sperimentale).
- origine: hip center
- scala: spine length (hip center -> shoulder center)
- per-joint confidence (inFrameLikelihood, 3o elemento landmark)
- tracker_id, VALID/INELIGIBLE per action
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from landmarks import (
    LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP,
    LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST,
    LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE,
)

# azioni -> landmark richiesti (spec: punch={wrist,elbow,shoulder}, kick={ankle,knee,hip})
# Nota: caviglie/piedi hanno conf p50~0.33 su inquadratura reale laterale —
# i calci si rilevano dal GINOCCHIO (conf ~0.52) + ANCA (~0.87), non dal piede.
REQUIRED_LANDMARKS = {
    "punch_right": [RIGHT_WRIST, RIGHT_ELBOW, RIGHT_SHOULDER],
    "punch_left": [LEFT_WRIST, LEFT_ELBOW, LEFT_SHOULDER],
    "kick_right": [RIGHT_KNEE, RIGHT_HIP],
    "kick_left": [LEFT_KNEE, LEFT_HIP],
}

CONF_PER_LANDMARK = 0.6
CONF_MEAN = 0.7
CORE_JOINTS = [LEFT_HIP, RIGHT_HIP, LEFT_SHOULDER, RIGHT_SHOULDER]
CORE_CONF = 0.5


@dataclass(frozen=True)
class BodyFrame:
    seq_id: int
    capture_ts: float
    # posizioni body-centric normalizzate (unita' di torso), per landmark indice
    pos: tuple            # tuple[tuple[x,y], ...] len 33
    conf: tuple           # tuple[float] len 33
    valid: bool           # core joints ok
    tracker_id: str
    boundary: bool        # primo frame di nuova epoca (da jitter buffer)
    z: tuple = ()         # tuple[float] len 33 — position3D.z (T-005); vuota su vecchie tracce

    def point(self, idx: int):
        return self.pos[idx]


def build_body_frame(pkt: dict, seq_id: int, boundary: bool,
                     tracker_id: str = "A") -> BodyFrame:
    """pkt: {'landmarks': [[x,y,conf]...33], 'ts':...}. Coordinate immagine 0..1."""
    lms = pkt.get("landmarks", [])
    n = 33
    xs = [(lms[i][0] if i < len(lms) else 0.0) for i in range(n)]
    ys = [(lms[i][1] if i < len(lms) else 0.0) for i in range(n)]
    cs = [(lms[i][2] if i < len(lms) and len(lms[i]) > 2 else 0.0) for i in range(n)]
    # T-005: z = 4o elemento (position3D.z, in mm da ML Kit); tracce vecchie
    # (3 elementi) -> z=0, il gate le tratta come "assenti" non "fidate".
    zs = [(lms[i][3] if i < len(lms) and len(lms[i]) > 3 else 0.0)
          for i in range(n)]

    # origine = hip center; scala = spine length (2D, stabile in vista laterale)
    if len(lms) > RIGHT_HIP:
        hip_c = ((xs[LEFT_HIP] + xs[RIGHT_HIP]) / 2, (ys[LEFT_HIP] + ys[RIGHT_HIP]) / 2)
        sho_c = ((xs[LEFT_SHOULDER] + xs[RIGHT_SHOULDER]) / 2,
                 (ys[LEFT_SHOULDER] + ys[RIGHT_SHOULDER]) / 2)
        scale = math.dist(hip_c, sho_c)
        if scale < 1e-4:
            scale = 0.3  # fallback
        core_ok = all(cs[i] >= CORE_CONF for i in CORE_JOINTS)
    else:
        hip_c, scale, core_ok = (0.5, 0.5), 1.0, False

    pos = tuple(((xs[i] - hip_c[0]) / scale, (ys[i] - hip_c[1]) / scale)
                for i in range(n))

    return BodyFrame(seq_id=seq_id,
                     capture_ts=float(pkt.get("ts", 0)),
                     pos=pos, conf=tuple(cs), z=tuple(zs), valid=core_ok,
                     tracker_id=tracker_id, boundary=boundary)


# ---------------------------------------------------------------------------
# Vincolo di rigidita' ossea (workaround per il joint-snap di ML Kit)
#
# Osservato su dati reali: il segmento spalla->gomito si accorcia del ~35%
# quando il braccio si alza anche se resta nel piano immagine. Le ossa sono
# rigide: calibriamo la lunghezza MASSIMA osservata per osso (le stime possono
# solo accorciare, mai allungare -> il max cresce verso la lunghezza vera) e
# quando un segmento e' troppo corto estendiamo il punto distale lungo la sua
# direzione osservata. Direzione preservata, magnitudine ripristinata.
# ---------------------------------------------------------------------------

BONES = [
    (LEFT_SHOULDER, LEFT_ELBOW), (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW), (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_HIP, LEFT_KNEE), (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE), (RIGHT_KNEE, RIGHT_ANKLE),
    # larghezze: NON rigide (variano con la rotazione del busto) — valide
    # solo perche' il giocatore resta in vista laterale.
    (LEFT_SHOULDER, RIGHT_SHOULDER), (LEFT_HIP, RIGHT_HIP),
]
BONE_MIN_CONF = 0.7          # max solo con capi solidi (outlier -> no update)
BONE_RESTORE_FACTOR = 0.5    # ripristina solo se < 50% del max
BONE_MAX_STRETCH = 1.3       # estensione max = 1.3x l'osservato
BONE_COLLAPSE_FACTOR = 0.25  # sotto 25% del max: joint-snap, direzione persa
STRAIGHTEN_DEG = 172.0       # solo braccia quasi perfettamente distese
# in collasso, il distale va sulla linea verso il giunto a valle:
# gomito sulla direzione spalla->polso, polso lungo ultima direzione nota
RECOVERY_DIR = {
    (LEFT_SHOULDER, LEFT_ELBOW): LEFT_WRIST,
    (RIGHT_SHOULDER, RIGHT_ELBOW): RIGHT_WRIST,
    (LEFT_HIP, LEFT_KNEE): LEFT_ANKLE,
    (RIGHT_HIP, RIGHT_KNEE): RIGHT_ANKLE,
}


class BoneConstraint:
    """Max robusto per osso + ripristino conservativo. Per Pipeline."""

    def __init__(self):
        self.max_len: dict[tuple[int, int], float] = {}
        self.last_dir: dict[tuple[int, int], tuple] = {}  # direzione unitaria
        self.restored = 0
        self.collapsed = 0

    def apply(self, f: BodyFrame) -> BodyFrame:
        if not f.valid:
            return f
        pos = list(f.pos)
        conf = f.conf
        for a, b in BONES:
            if conf[a] < BONE_MIN_CONF or conf[b] < BONE_MIN_CONF:
                continue
            ax, ay = pos[a]
            bx, by = pos[b]
            d = math.hypot(bx - ax, by - ay)
            if d < 1e-6:
                continue
            m = self.max_len.get((a, b), 0.0)
            if d > m:
                self.max_len[(a, b)] = d if m == 0 else min(d, m * 1.2)
                self.last_dir[(a, b)] = ((bx - ax) / d, (by - ay) / d)
                continue
            if m <= 0:
                continue
            if d < m * BONE_COLLAPSE_FACTOR:
                # joint-snap: direzione a->b indefinita. Stima il distale
                # lungo la direzione verso il giunto a valle (gomito sulla
                # linea spalla->polso) o lungo l'ultima direzione nota.
                self.collapsed += 1
                dsw = RECOVERY_DIR.get((a, b))
                placed = False
                if dsw is not None and conf[dsw] >= BONE_MIN_CONF:
                    wx, wy = pos[dsw]
                    dl = math.hypot(wx - ax, wy - ay)
                    if dl > 1e-6:
                        ux, uy = (wx - ax) / dl, (wy - ay) / dl
                        pos[b] = (ax + ux * m, ay + uy * m)
                        placed = True
                if not placed and (a, b) in self.last_dir:
                    ux, uy = self.last_dir[(a, b)]
                    pos[b] = (ax + ux * m, ay + uy * m)
                    placed = True
                if placed:
                    continue
            elif d < m * BONE_RESTORE_FACTOR:
                k = min(m / d, BONE_MAX_STRETCH)
                pos[b] = (ax + (bx - ax) * k, ay + (by - ay) * k)
                self.restored += 1
            self.last_dir[(a, b)] = ((pos[b][0] - ax) /
                                     max(1e-6, math.dist(pos[a], pos[b])),
                                     (pos[b][1] - ay) /
                                     max(1e-6, math.dist(pos[a], pos[b])))

        # Raddrizzamento gomito: ML Kit posa il gomito sistematicamente fuori
        # dalla retta spalla->polso (angolo mediano reale ~148 anche a riposo
        # = bias del modello, non braccio piegato). Se l'angolo supera la
        # soglia, il gomito va sulla retta spalla->polso.
        for s, e, w in ((LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
                        (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
                        (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE),
                        (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)):
            if min(conf[s], conf[e], conf[w]) < BONE_MIN_CONF:
                continue
            ax, ay = pos[s]; bx, by = pos[e]; cx, cy = pos[w]
            v1 = (ax - bx, ay - by); v2 = (cx - bx, cy - by)
            n1 = math.hypot(*v1); n2 = math.hypot(*v2)
            if n1 < 1e-6 or n2 < 1e-6:
                continue
            cos = max(-1.0, min(1.0, (v1[0]*v2[0]+v1[1]*v2[1])/(n1*n2)))
            if math.degrees(math.acos(cos)) >= STRAIGHTEN_DEG:
                dl = math.hypot(cx-ax, cy-ay)
                if dl > 1e-6:
                    t = n1 / (n1 + n2)
                    pos[e] = (ax + (cx-ax)*t, ay + (cy-ay)*t)

        return BodyFrame(seq_id=f.seq_id, capture_ts=f.capture_ts,
                         pos=tuple(pos), conf=f.conf, valid=f.valid,
                         tracker_id=f.tracker_id, boundary=f.boundary,
                         z=f.z)


def eligible(frame: BodyFrame, action: str) -> bool:
    """ELIGIBLE(frame, action): VALID + landmark richiesti conf>=0.6 + mean>=0.7."""
    if not frame.valid:
        return False
    req = REQUIRED_LANDMARKS.get(action, [])
    if not req:
        return True
    confs = [frame.conf[i] for i in req]
    if any(c < CONF_PER_LANDMARK for c in confs):
        return False
    return sum(confs) / len(confs) >= CONF_MEAN


def limb_point(frame: BodyFrame, limb: str):
    """Punto distale dell'arto per hit/motion (wrist o ankle)."""
    table = {
        "right_wrist": RIGHT_WRIST, "left_wrist": LEFT_WRIST,
        "right_ankle": RIGHT_ANKLE, "left_ankle": LEFT_ANKLE,
        "right_elbow": RIGHT_ELBOW, "left_elbow": LEFT_ELBOW,
        "right_knee": RIGHT_KNEE, "left_knee": LEFT_KNEE,
        "right_hip": RIGHT_HIP, "left_hip": LEFT_HIP,
        "right_shoulder": RIGHT_SHOULDER, "left_shoulder": LEFT_SHOULDER,
    }
    idx = table.get(limb)
    return frame.pos[idx] if idx is not None else (0.0, 0.0)
