"""Telemetria temporale e di rete — PLAN-048e T-001.

Domini temporali (non mescolabili):
- capture_ts: clock del telefono (SystemClock.elapsedRealtime, ms) nel
  pacchetto `pkt["ts"]`. Usato per desync display<->detection: stesso
  dominio, confronto valido.
- monotonic ms: clock Mac (time.monotonic, ms dall'avvio). Usato per
  latenze lato Mac: arrival->render, arrival->emit, processing.

display_latency  = render_mono - arrival_mono   (lato Mac, onesto: il
                   clock phone->Mac non e' sincronizzato, quindi la latenza
                   end-to-end assoluta non e' misurabile senza sync)
detection_latency= emit_virtual - arrival_mono  (jitter buffer, stesso dominio)
desync           = capture_ts(frame mostrato) - capture_ts(ultimo frame
                   usato dalla detection) — stesso dominio telefono

Associazione display<->detection: stesso istante di render, si confrontano
i DUE frame "correnti" (ultimo mostrato vs ultimo processato). Regola
deterministica: se non esiste ancora un frame detection -> NO_MATCH.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(p / 100.0 * len(s))))
    return s[i]


@dataclass
class Telemetry:
    """Raccoglie campioni per-frame; report() produce il riepilogo."""

    # rete / coda
    received: int = 0
    seq_gaps: int = 0            # salti di seq (frame mai arrivati)
    seq_lost: int = 0
    inter_arrival_ms: list = field(default_factory=list)
    queue_depths: list = field(default_factory=list)
    enqueue_to_emit_ms: list = field(default_factory=list)
    processing_ms: list = field(default_factory=list)

    # latenze
    display_latency_ms: list = field(default_factory=list)    # arrival->render
    detection_latency_ms: list = field(default_factory=list)  # arrival->emit
    desync_ms: list = field(default_factory=list)             # capture_ts domain
    desync_frames: list = field(default_factory=list)
    desync_no_match: int = 0

    # warm-up / recovery
    first_render_ms: float | None = None
    warmup_samples: int = 0           # render nei primi 500ms
    recovery_samples: list = field(default_factory=list)  # latenza post-gap

    _last_seq: int | None = None
    _last_arrival: float | None = None
    _t0: float = 0.0
    _arrival_by_seq: dict = field(default_factory=dict)
    _last_detection_cts: float | None = None   # capture_ts ultimo frame detection
    _last_detection_seq: int | None = None

    def start(self, t0_mono: float):
        self._t0 = t0_mono

    def on_arrival(self, seq: int, capture_ts: float, arrival_mono: float,
                   queue_depth: int):
        """Chiamato per ogni pacchetto UDP decodificato."""
        self.received += 1
        if self._last_seq is not None and seq > self._last_seq + 1:
            self.seq_gaps += 1
            self.seq_lost += seq - self._last_seq - 1
        if seq >= 0:
            self._last_seq = max(self._last_seq or seq, seq)
        if self._last_arrival is not None:
            self.inter_arrival_ms.append(arrival_mono - self._last_arrival)
        self._last_arrival = arrival_mono
        self.queue_depths.append(queue_depth)
        self._arrival_by_seq[seq] = arrival_mono
        if len(self._arrival_by_seq) > 4096:          # bound memoria
            self._arrival_by_seq = dict(
                list(self._arrival_by_seq.items())[-2048:])

    def on_emit(self, seq: int, emit_virtual_ms: float, proc_ms: float,
                capture_ts: float):
        """Chiamato quando il jitter buffer emette un frame verso detection."""
        arr = self._arrival_by_seq.get(seq)
        if arr is not None:
            self.enqueue_to_emit_ms.append(emit_virtual_ms - arr)
            self.detection_latency_ms.append(emit_virtual_ms - arr)
        self.processing_ms.append(proc_ms)
        self._last_detection_cts = capture_ts
        self._last_detection_seq = seq

    def on_render(self, seq: int, capture_ts: float, render_mono: float):
        """Chiamato quando il display mostra un frame."""
        arr = self._arrival_by_seq.get(seq)
        if arr is not None:
            lat = render_mono - arr
            self.display_latency_ms.append(lat)
            if self.first_render_ms is None:
                self.first_render_ms = render_mono - self._t0
            if render_mono - self._t0 < 500:
                self.warmup_samples += 1
            if arr - (self._last_arrival or arr) < -170:
                self.recovery_samples.append(lat)
        if self._last_detection_cts is None:
            self.desync_no_match += 1
        else:
            self.desync_ms.append(capture_ts - self._last_detection_cts)
            self.desync_frames.append(seq - (self._last_detection_seq or seq))

    def report(self) -> str:
        def stat(xs, unit="ms"):
            return (f"p50={_pct(xs,50):.1f} p95={_pct(xs,95):.1f} "
                    f"max={max(xs) if xs else 0:.1f}{unit}")
        lines = ["[TEL] report"]
        lines.append(f"  packets: received={self.received} "
                     f"seq_gaps={self.seq_gaps} seq_lost={self.seq_lost}")
        lines.append(f"  inter-arrival: {stat(self.inter_arrival_ms)}")
        lines.append(f"  queue depth:   p50={_pct(self.queue_depths,50):.0f} "
                     f"max={max(self.queue_depths) if self.queue_depths else 0}")
        lines.append(f"  enqueue->emit: {stat(self.enqueue_to_emit_ms)}")
        lines.append(f"  processing:    {stat(self.processing_ms)}")
        lines.append(f"  display_latency (arrival->render): "
                     f"{stat(self.display_latency_ms)}")
        lines.append(f"  detection_latency (arrival->emit): "
                     f"{stat(self.detection_latency_ms)}")
        lines.append(f"  desync (capture_ts domain): "
                     f"{stat(self.desync_ms)} "
                     f"frames_p50={_pct(self.desync_frames,50):.0f} "
                     f"no_match={self.desync_no_match}")
        lines.append(f"  first_render={self.first_render_ms or 0:.0f}ms "
                     f"warmup_samples={self.warmup_samples} "
                     f"recovery_samples={len(self.recovery_samples)}")
        return "\n".join(lines)
