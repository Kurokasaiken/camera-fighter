"""CombatBridge — PLAN-048d: pending queue + upgrade retroattivo.

HitSignal emette HitEvent immediati (non bloccare il gameplay).
Se un ComboCommit arriva entro RETROACTIVE_WINDOW_SEQ sullo stesso arto,
l'hit viene promosso a "combo hit" (danno x2). Solo l'hit piu' recente.
"""

from __future__ import annotations

from dataclasses import dataclass

RETROACTIVE_WINDOW_SEQ = 15   # ~500ms a 30fps
COMBO_DAMAGE_MULT = 2.0
BASE_DAMAGE = 8


@dataclass
class PendingHit:
    seq_id: int
    joint: str
    upgraded: bool = False


class CombatBridge:
    def __init__(self):
        self.pending: list[PendingHit] = []
        self.damage_log = []

    def on_hit(self, seq_id: int, joint: str):
        self.pending.append(PendingHit(seq_id, joint))
        self.damage_log.append((seq_id, joint, BASE_DAMAGE, False))
        return BASE_DAMAGE

    def on_commit(self, combo_id: str, seq_end: int):
        """Upgrade retroattivo: solo l'hit piu' recente nella finestra."""
        upgraded = False
        for ph in reversed(self.pending):
            if 0 <= seq_end - ph.seq_id <= RETROACTIVE_WINDOW_SEQ and \
               not ph.upgraded:
                ph.upgraded = True
                # marca nel log
                for i in range(len(self.damage_log) - 1, -1, -1):
                    if self.damage_log[i][0] == ph.seq_id and \
                       self.damage_log[i][1] == ph.joint:
                        s, j, _d, _u = self.damage_log[i]
                        self.damage_log[i] = (s, j,
                                              int(BASE_DAMAGE * COMBO_DAMAGE_MULT),
                                              True)
                        break
                upgraded = True
                break
        # scadenza
        self.pending = [p for p in self.pending
                        if seq_end - p.seq_id <= RETROACTIVE_WINDOW_SEQ * 2]
        return upgraded
