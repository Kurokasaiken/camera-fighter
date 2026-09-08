"""Leg identity tracker — ricostruzione fisica durante merge/swap (T-007).

Stati espliciti per gamba (lo swap non si nasconde in un'euristica):
  TRACKED    — identita' affidabile
  UNCERTAIN  — conf bassa, identita' preservata ma non confermata
  LOST       — merge/occlusione: posizione non osservabile
  RECOVERED  — primo frame affidabile dopo LOST/UNCERTAIN
  SWAPPED    — assegnazione L/R contraddetta dalla continuita' temporale
  MERGED     — i due lati collassati sullo stesso landmark (frame-level)

Definizioni operative:
  MERGED  = dist(knee_L, knee_R) < MERGE_DIST oppure dist(ankle_L,R) < MERGE_DIST
  SWAPPED = dist(L->prevR) + dist(R->prevL) + SWAP_MARGIN
            < dist(L->prevL) + dist(R->prevR)
Attribuzione: il MERGE e' un artefatto ML Kit (upstream) — il tracker NON
puo' risolvere un merge gia' avvenuto; puo' solo congelare e segnare
estimated. IoU/continuita' aiutano a riassegnare, non a separare.

Metriche (per T-006/T-007 eval): swap_count, merge_count,
reconstructed_count, per-gamba: state, lost_frames, age, recovery_ts.
Identity CORRECTNESS va misurata su ground truth L/R (separata dalla
continuita': un tracker puo' essere continuo e sempre sbagliato).

Vincolo fisico: quando si calcia, una gamba e' PIANTATA a terra.
- Gamba attiva -> segue la detection.
- Gamba piantata -> congelata all'ultimo campione affidabile.
"""

from __future__ import annotations

import math

LK, RK = 25, 26
LA, RA = 27, 28
LHEEL, RHEEL = 29, 30
LFOOT, RFOOT = 31, 32

LEFT_JOINTS = (LK, LA, LHEEL, LFOOT)
RIGHT_JOINTS = (RK, RA, RHEEL, RFOOT)

MERGE_DIST = 0.05
SWAP_MARGIN = 0.02
ACTIVE_VEL = 0.01        # velocita' minima per considerare una gamba "attiva"
CONF_OK = 0.3
MAX_LOST = 30            # oltre: LOST definitivo, niente ricostruzione

# stati espliciti (T-007)
TRACKED, UNCERTAIN, LOST = "TRACKED", "UNCERTAIN", "LOST"
RECOVERED, SWAPPED, MERGED = "RECOVERED", "SWAPPED", "MERGED"


class LegTracker:
    def __init__(self):
        # traccia per lato: ultima posizione affidabile + velocita' recente
        self.pos = {"L": None, "R": None}     # dict joint_idx -> (x,y)
        self.vel = {"L": 0.0, "R": 0.0}
        # stato per gamba (T-007)
        self.leg_state = {"L": TRACKED, "R": TRACKED}
        self.lost_frames = {"L": 0, "R": 0}
        self.age = {"L": 0, "R": 0}
        self.recovered = {"L": 0, "R": 0}
        self.swap_count = 0
        self.merge_count = 0
        self.reconstructed_count = 0
        self.frame_state = TRACKED   # TRACKED | MERGED | SWAPPED | UNCERTAIN | LOST
        # alias storico per compatibilita'
        self.state = "reliable"

    def _leg_pos(self, lm, joints):
        return {i: (lm[i][0], lm[i][1]) for i in joints}

    def _leg_vel(self, new, old):
        if old is None:
            return 0.0
        return sum(math.dist(new[i], old[i]) for i in new) / len(new)

    def _set_state(self, side, state):
        prev = self.leg_state[side]
        if state == TRACKED and prev in (LOST, UNCERTAIN):
            self.leg_state[side] = RECOVERED
            self.recovered[side] += 1
        else:
            self.leg_state[side] = state
        if state == TRACKED or self.leg_state[side] == RECOVERED:
            self.lost_frames[side] = 0

    def update(self, landmarks):
        """Ritorna (affidabile, landmarks_out, active_leg).
        landmarks_out = ricostruzione se merged/swapped, altrimenti None.
        active_leg = 'L' | 'R' | None."""
        if not landmarks or len(landmarks) < 33:
            self.frame_state = LOST
            self.state = "reliable"
            return True, None, None

        lk, rk = landmarks[LK][:2], landmarks[RK][:2]
        la, ra = landmarks[LA][:2], landmarks[RA][:2]
        conf = min(landmarks[LK][2], landmarks[RK][2],
                   landmarks[LA][2], landmarks[RA][2])

        merged = math.dist(lk, rk) < MERGE_DIST or \
            math.dist(la, ra) < MERGE_DIST
        swapped = False
        if self.pos["L"] is not None and not merged:
            plk = self.pos["L"][LK]
            prk = self.pos["R"][RK]
            same = math.dist(lk, plk) + math.dist(rk, prk)
            cross = math.dist(lk, prk) + math.dist(rk, plk)
            swapped = cross + SWAP_MARGIN < same

        new_L = self._leg_pos(landmarks, LEFT_JOINTS)
        new_R = self._leg_pos(landmarks, RIGHT_JOINTS)

        if conf >= CONF_OK and not merged and not swapped:
            self.vel["L"] = 0.7 * self.vel["L"] + \
                0.3 * self._leg_vel(new_L, self.pos["L"])
            self.vel["R"] = 0.7 * self.vel["R"] + \
                0.3 * self._leg_vel(new_R, self.pos["R"])
            self.pos["L"], self.pos["R"] = new_L, new_R
            self._set_state("L", TRACKED)
            self._set_state("R", TRACKED)
            self.age["L"] += 1
            self.age["R"] += 1
            self.frame_state = TRACKED
            self.state = "reliable"
            return True, None, None

        # merged/swapped/occluso -> ricostruzione fisica (gamba attiva segue
        # la detection; piantata congelata). Non separiamo un merge gia'
        # avvenuto: segnamo LOST la gamba piantata.
        if merged:
            self.merge_count += 1
            self.frame_state = MERGED
        elif swapped:
            self.swap_count += 1
            self.frame_state = SWAPPED
        else:
            self.frame_state = UNCERTAIN if conf >= 0.1 else LOST
        self.reconstructed_count += 1
        self.state = ("merged" if merged else
                      "swapped" if swapped else "occluded")

        for side in ("L", "R"):
            self.lost_frames[side] += 1
            self._set_state(side, self.frame_state if self.frame_state
                            in (MERGED, SWAPPED, UNCERTAIN, LOST) else UNCERTAIN)

        # gamba attiva = quella con piu' velocita' recente (o nessuna)
        active = None
        if self.pos["L"] is not None:
            vL = self.vel["L"] + self._leg_vel(new_L, self.pos["L"])
            vR = self.vel["R"] + self._leg_vel(new_R, self.pos["R"])
            if vL > vR + ACTIVE_VEL:
                active = "L"
            elif vR > vL + ACTIVE_VEL:
                active = "R"

        out = [lm[:] for lm in landmarks]
        if active == "L" and self.pos["R"] is not None:
            for i, p in self.pos["R"].items():
                out[i] = [p[0], p[1], out[i][2] * 0.7]   # conf ridotta = estimated
            for i, p in new_L.items():
                out[i] = [p[0], p[1], landmarks[i][2]]
            self.pos["L"] = new_L
            self.leg_state["R"] = LOST if self.lost_frames["R"] > MAX_LOST \
                else UNCERTAIN
        elif active == "R" and self.pos["L"] is not None:
            for i, p in self.pos["L"].items():
                out[i] = [p[0], p[1], out[i][2] * 0.7]
            for i, p in new_R.items():
                out[i] = [p[0], p[1], landmarks[i][2]]
            self.pos["R"] = new_R
            self.leg_state["L"] = LOST if self.lost_frames["L"] > MAX_LOST \
                else UNCERTAIN
        else:
            # nessuna gamba attiva chiara: congela entrambe (postura ferma)
            for side, joints in (("L", LEFT_JOINTS), ("R", RIGHT_JOINTS)):
                if self.pos[side] is not None:
                    for i, p in self.pos[side].items():
                        out[i] = [p[0], p[1], out[i][2] * 0.5]
        return False, out, active
