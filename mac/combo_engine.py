"""Combo Engine — PLAN-048d S2: UNA combo hardcoded + state machine.

Subsequence matching su MotionEvent stream (non classificazione):
  template = sequenza ordinata di (action, direction) con vincoli temporali.
Stato: IDLE -> TRACKING -> (match | timeout -> IDLE).
Single-writer: solo questo modulo emette ComboProgress/COMMIT.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from segmentation import MotionEvent

# Finestra massima fra primo e ultimo step (ms, su capture_ts).
MAX_COMBO_WINDOW_MS = 1500
# Pausa massima fra step consecutivi (ms).
MAX_STEP_GAP_MS = 700
# Refractory post-commit.
COMMIT_COOLDOWN_MS = 400

STATE_IDLE = "IDLE"
STATE_TRACKING = "TRACKING"


@dataclass(frozen=True)
class ComboCommit:
    combo_id: str
    seq_start: int
    seq_end: int
    t_decision: float       # virtual/capture ts dell'ultimo step
    score: float


class ComboEngine:
    """Matcher di sequenza su MotionEvent. Un template = lista di step
    {action_prefix, direction}. Un evento matcha uno step se action endswith
    o uguale e direction coincide (o step.direction == 'any')."""

    def __init__(self, combos_path: str | None = None):
        self.templates = []
        if combos_path and os.path.exists(combos_path):
            with open(combos_path, encoding="utf-8") as fp:
                data = json.load(fp)
            self.templates = data.get("combos", [])
        self.state = STATE_IDLE
        self.matched_steps = []       # indici step matchati
        self.window_start_ts = 0.0
        self.last_step_ts = 0.0
        self.seq_start = 0
        self.cooldown_until = 0.0
        self.last_commit: ComboCommit | None = None

    def _step_matches(self, step: dict, ev: MotionEvent) -> bool:
        act = step.get("action", "")
        if act and act != "any" and not ev.action.startswith(act):
            return False
        d = step.get("direction", "any")
        if d != "any" and ev.direction != d:
            return False
        return ev.peak_speed >= step.get("min_speed", 0.0)

    def update(self, ev: MotionEvent, now_ts: float) -> ComboCommit | None:
        """Consuma un MotionEvent; ritorna ComboCommit al match completo."""
        if now_ts < self.cooldown_until:
            return None

        commit = None
        for tpl in self.templates:
            steps = tpl.get("steps", [])
            if not steps:
                continue
            c = self._feed_template(tpl, steps, ev, now_ts)
            if c is not None:
                commit = c
        return commit

    def _feed_template(self, tpl, steps, ev, now_ts) -> ComboCommit | None:
        # stato tracking per template: lista di (step_idx, ev) — semplificato:
        # proviamo a estendere la sequenza corrente di questo template.
        tr = tpl.setdefault("_progress", [])
        tr_start = tpl.setdefault("_t0", 0.0)
        tr_last = tpl.setdefault("_tlast", 0.0)

        nxt = len(tr)
        if nxt >= len(steps):
            tr.clear()
            nxt = 0

        # finestra scaduta -> riparti
        if tr and (now_ts - tr_last > MAX_STEP_GAP_MS or
                   now_ts - tr_start > MAX_COMBO_WINDOW_MS):
            tr.clear()
            nxt = 0

        if self._step_matches(steps[nxt], ev):
            if not tr:
                tpl["_t0"] = now_ts
                self.seq_start = ev.seq_start
            tr.append(ev)
            tpl["_tlast"] = now_ts
            if len(tr) == len(steps):
                avg_speed = sum(e.peak_speed for e in tr) / len(tr)
                commit = ComboCommit(
                    combo_id=tpl.get("id", "combo"),
                    seq_start=self.seq_start, seq_end=ev.seq_end,
                    t_decision=now_ts, score=round(avg_speed, 4))
                tr.clear()
                self.cooldown_until = now_ts + COMMIT_COOLDOWN_MS
                self.last_commit = commit
                return commit
        elif tr:
            # evento estraneo (es. retrazione -x): NON rompe la sequenza.
            # Solo il timeout sopra la invalida. Se matcha step0 -> restart.
            if self._step_matches(steps[0], ev):
                tr.clear()
                tr.append(ev)
                tpl["_t0"] = now_ts
                tpl["_tlast"] = now_ts
                self.seq_start = ev.seq_start
        return None
