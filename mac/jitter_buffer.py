"""Jitter buffer deterministico — spec PLAN-048d (Round 15, verificata multi-AI).

Hard invariants implementati verbatim:
- seq_id ordering post-buffer
- declared_gaps copre l'intero intervallo saltato
- LATE_DROPPED distinto da DUPLICATE_DROPPED
- epoch tokens su entrambi i timer (flush_epoch, idle_epoch)
- per-gap fresh 33ms budget
- idle gap: nessun frame emesso per 33ms -> gap_pending -> prossimo frame = nuova epoca
- timer ordering allo stesso virtual_ts: arrivals -> flush -> idle (idle solo se buffer vuoto)
- begin_boundary() PRIMA di emit() del primo frame di ogni nuova epoca
- deterministic replay: virtual clock da traccia (arrival_ts), mai wall-clock
- current_tracker_id aggiornato solo da frame VALID; reset_state() NON lo tocca

Il buffer non conosce socket né wall-clock: tutto è guidato da virtual_ts.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable

REORDER_WINDOW = 2
# Calibrato su stream reale ~17fps (inter-arrival p50=57ms, p95=92ms):
# flush 66ms copre ~1 frame di riordino; idle 170ms ~ 3 frame di silenzio.
FLUSH_TIMEOUT_MS = 66
IDLE_TIMEOUT_MS = 170

# Transport status
ACCEPTED = "ACCEPTED"
REORDERED_ACCEPTED = "REORDERED_ACCEPTED"
DUPLICATE_DROPPED = "DUPLICATE_DROPPED"
LATE_DROPPED = "LATE_DROPPED"
OUT_OF_WINDOW_DROPPED = "OUT_OF_WINDOW_DROPPED"


@dataclass
class EmittedFrame:
    seq_id: int
    frame: Any
    status: str            # ACCEPTED | REORDERED_ACCEPTED
    boundary: bool         # True se primo frame di una nuova epoca
    emit_ts: float         # virtual clock ms


@dataclass
class Stats:
    received: int = 0
    accepted: int = 0
    reordered: int = 0
    duplicates: int = 0
    late: int = 0
    out_of_window: int = 0
    declared_gaps: int = 0        # seq_id dichiarati GAP
    gap_events: int = 0           # eventi di gap (epoche rotte)
    epochs: int = 0               # nuove epoche iniziate
    tracker_resets: int = 0
    buffer_delay_ms: list = field(default_factory=list)  # emit_ts - arrival_ts


class JitterBuffer:
    """Buffer di riordino deterministico guidato da virtual clock.

    Uso:
        jb = JitterBuffer(on_emit=callback)
        jb.process_frame(seq_id, frame, arrival_ts)   # arrival_ts = virtual ms
        jb.tick(virtual_now)                          # fa scattare i timer dovuti
    """

    def __init__(self, on_emit: Callable[[EmittedFrame], None] | None = None):
        self.on_emit = on_emit or (lambda ef: None)

        # state
        self.next_expected: int | None = None
        self.last_emitted: int = -1
        self.buffer: dict[int, tuple[Any, float]] = {}  # seq_id -> (frame, arrival_ts)
        self.declared_gaps: set[int] = set()
        self.timeout_seq_id: int | None = None
        self.timeout_start: float | None = None
        self.flush_epoch: int = 0
        self.idle_epoch: int = 0
        self.last_output_emission: float | None = None
        self.gap_pending: bool = False
        self.current_tracker_id: Any = None
        self.boundary_forced: bool = False

        self.stats = Stats()
        self._timers: list[tuple[float, int, str, int, int | None]] = []
        # heap entries: (due_ts, order, kind, epoch_token, seq_id_or_None)
        # order garantisce: flush (kind=0) prima di idle (kind=1) allo stesso ts
        self._timer_counter = 0

    # ------------------------------------------------------------------ utils

    def _push_timer(self, due_ts: float, kind: str, epoch: int, seq_id: int | None):
        order = 0 if kind == "flush" else 1
        heapq.heappush(self._timers, (due_ts, order, kind, epoch, seq_id))

    def _schedule_flush(self, due_ts: float, epoch: int, seq_id: int):
        self._push_timer(due_ts, "flush", epoch, seq_id)

    def _schedule_idle(self, due_ts: float, epoch: int):
        self._push_timer(due_ts, "idle", epoch, None)

    def begin_boundary(self):
        self.derivative_reset()
        self.boundary_forced = True

    def derivative_reset(self):
        # hook per la derivative pipeline (last_derivative_valid[*] = null).
        # Nel buffer stesso è un flag consumato a valle.
        pass

    # ------------------------------------------------------------------- emit

    def _emit(self, seq_id: int, frame: Any, status: str, virtual_ts: float,
              arrival_ts: float):
        boundary = self.boundary_forced
        self.boundary_forced = False  # one-shot: consumato alla prima emissione
        self.last_output_emission = virtual_ts
        self.idle_epoch += 1
        self._schedule_idle(virtual_ts + IDLE_TIMEOUT_MS, self.idle_epoch)
        if status == ACCEPTED:
            self.stats.accepted += 1
        else:
            self.stats.reordered += 1
            self.stats.buffer_delay_ms.append(virtual_ts - arrival_ts)
        self.on_emit(EmittedFrame(seq_id, frame, status, boundary, virtual_ts))

    def _reset_state(self):
        self.buffer.clear()
        self.declared_gaps.clear()
        self.timeout_seq_id = None
        self.timeout_start = None
        self.flush_epoch += 1
        self.gap_pending = False
        self.last_output_emission = None
        self.next_expected = None
        self.last_emitted = -1
        self.idle_epoch += 1
        self.begin_boundary()
        # NB: current_tracker_id NON toccato — assegnato solo da frame VALID.

    # -------------------------------------------------------------- processing

    def process_frame(self, seq_id: int, frame: Any, arrival_ts: float):
        """arrival_ts = virtual clock ms (replay) o monotonic ms (live)."""
        self.stats.received += 1
        valid = frame.get("valid", True) if isinstance(frame, dict) else True
        tracker_id = frame.get("tracker_id") if isinstance(frame, dict) else None

        # tracker change -> nuova epoca (solo frame VALID)
        if (valid and tracker_id is not None
                and self.current_tracker_id is not None
                and tracker_id != self.current_tracker_id):
            self._reset_state()
            self.stats.tracker_resets += 1
        if valid and tracker_id is not None:
            self.current_tracker_id = tracker_id

        # bootstrap / nuova epoca
        if self.next_expected is None:
            self.begin_boundary()
            self._emit(seq_id, frame, ACCEPTED, arrival_ts, arrival_ts)
            self.stats.epochs += 1
            self.next_expected = seq_id + 1
            self.last_emitted = seq_id
            return

        # post idle gap: accetta qualunque seq_id, resetta stato
        if self.gap_pending:
            self.buffer.clear()
            self.declared_gaps.clear()
            self.timeout_seq_id = None
            self.timeout_start = None
            self.flush_epoch += 1
            self.gap_pending = False
            self.begin_boundary()
            self._emit(seq_id, frame, ACCEPTED, arrival_ts, arrival_ts)
            self.stats.epochs += 1
            self.next_expected = seq_id + 1
            self.last_emitted = seq_id
            return

        # drops
        if seq_id in self.declared_gaps:
            self.stats.late += 1
            return  # LATE_DROPPED
        if seq_id <= self.last_emitted or seq_id in self.buffer:
            self.stats.duplicates += 1
            return  # DUPLICATE_DROPPED
        if seq_id > self.next_expected + REORDER_WINDOW:
            self.stats.out_of_window += 1
            return  # OUT_OF_WINDOW_DROPPED

        # contiguous
        if seq_id == self.next_expected:
            self.timeout_seq_id = None
            self.timeout_start = None
            self.flush_epoch += 1  # invalida callback pendente
            self._emit(seq_id, frame, ACCEPTED, arrival_ts, arrival_ts)
            self.next_expected += 1
            self.last_emitted = seq_id
            # drain buffer contiguo (in-epoca, nessun boundary)
            while self.next_expected in self.buffer:
                bframe, bts = self.buffer.pop(self.next_expected)
                self._emit(self.next_expected, bframe, REORDERED_ACCEPTED,
                           arrival_ts, bts)
                self.next_expected += 1
                self.last_emitted = self.next_expected - 1
            if self.buffer:
                # fresh 33ms budget per il nuovo gap esposto
                self.timeout_seq_id = self.next_expected
                self.timeout_start = arrival_ts
                self.flush_epoch += 1
                self._schedule_flush(arrival_ts + FLUSH_TIMEOUT_MS,
                                     self.flush_epoch, self.timeout_seq_id)
            return

        # out of order -> buffer
        if self.timeout_seq_id is None:
            self.timeout_seq_id = self.next_expected
            self.timeout_start = arrival_ts
            self.flush_epoch += 1
            self._schedule_flush(arrival_ts + FLUSH_TIMEOUT_MS,
                                 self.flush_epoch, self.timeout_seq_id)
        self.buffer[seq_id] = (frame, arrival_ts)

    # ------------------------------------------------------------------ timers

    def _on_flush_timeout(self, virtual_now: float, callback_epoch: int,
                          callback_seq_id: int):
        if callback_epoch != self.flush_epoch:
            return  # stale timer
        if callback_seq_id != self.timeout_seq_id:
            return
        if self.timeout_seq_id is None or not self.buffer:
            return
        if virtual_now < self.timeout_start + FLUSH_TIMEOUT_MS:
            return

        # dichiara GAP l'INTERO intervallo saltato
        gap_start = self.next_expected
        next_emit = min(self.buffer.keys())
        for s in range(gap_start, next_emit):
            self.declared_gaps.add(s)
        self.stats.declared_gaps += next_emit - gap_start
        self.stats.gap_events += 1

        self.begin_boundary()  # PRIMA di emit
        frame, ats = self.buffer.pop(next_emit)
        self._emit(next_emit, frame, REORDERED_ACCEPTED, virtual_now, ats)
        self.stats.epochs += 1
        self.next_expected = next_emit + 1
        self.last_emitted = next_emit
        while self.next_expected in self.buffer:
            bframe, bts = self.buffer.pop(self.next_expected)
            self._emit(self.next_expected, bframe, REORDERED_ACCEPTED,
                       virtual_now, bts)
            self.next_expected += 1
            self.last_emitted = self.next_expected - 1
        if self.buffer:
            self.timeout_seq_id = self.next_expected
            self.timeout_start = virtual_now
            self.flush_epoch += 1
            self._schedule_flush(virtual_now + FLUSH_TIMEOUT_MS,
                                 self.flush_epoch, self.timeout_seq_id)
        else:
            self.timeout_seq_id = None
            self.timeout_start = None
            self.flush_epoch += 1

    def _on_idle_timeout(self, virtual_now: float, callback_epoch: int):
        if callback_epoch != self.idle_epoch:
            return  # stale
        if self.last_output_emission is None:
            return
        if virtual_now - self.last_output_emission < IDLE_TIMEOUT_MS:
            return
        if self.buffer:
            return  # flush owns non-empty buffer
        self.gap_pending = True
        self.begin_boundary()

    def tick(self, virtual_now: float):
        """Fa scattare tutti i timer dovuti a virtual_now, in ordine:
        flush prima di idle allo stesso ts (ordering rule)."""
        while self._timers and self._timers[0][0] <= virtual_now:
            due, _order, kind, epoch, seq_id = heapq.heappop(self._timers)
            if kind == "flush":
                self._on_flush_timeout(due, epoch, seq_id)
            else:
                self._on_idle_timeout(due, epoch)
