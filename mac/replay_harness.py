"""Replay harness + report S0 — PLAN-048d.

Record:  salva traccia (arrival_ts, seq_id, payload) in .msgpack
Replay:  ri-esegue la traccia su un JitterBuffer nuovo a virtual clock
Gate:    LIVE outputs == REPLAY outputs  (determinismo)

Uso:
    python replay_harness.py record out.trace          # da UDP live
    python replay_harness.py replay out.trace          # replay determinista
    python replay_harness.py check  out.trace          # replay 2x, confronta
    python replay_harness.py synth  out.trace --loss 0.05 --reorder 0.1
"""

from __future__ import annotations

import json
import socket
import sys
import time
from dataclasses import asdict

import msgpack

from jitter_buffer import JitterBuffer, EmittedFrame

UDP_IP = "0.0.0.0"
UDP_PORT = 5005


# --------------------------------------------------------------------- record

def record_trace(path: str, max_seconds: float | None = None):
    """Ascolta UDP e registra (arrival_ts, seq_id, raw_payload) su file."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(0.5)
    t0 = time.monotonic()
    entries = []
    print(f"[record] UDP :{UDP_PORT} -> {path}  (Ctrl+C per stop)", flush=True)
    try:
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                if max_seconds and time.monotonic() - t0 > max_seconds:
                    break
                continue
            arrival_ms = (time.monotonic() - t0) * 1000.0
            try:
                pkt = msgpack.unpackb(data, raw=False)
            except Exception:
                continue
            entries.append({
                "arrival_ts": arrival_ms,
                "seq_id": pkt.get("seq", -1),
                "payload": pkt,
            })
    except KeyboardInterrupt:
        pass
    with open(path, "wb") as f:
        f.write(msgpack.packb(entries, use_bin_type=True))
    print(f"[record] {len(entries)} pacchetti -> {path}", flush=True)


# --------------------------------------------------------------------- replay

def _run_trace(entries, collect):
    """Esegue la traccia su un buffer fresco a virtual clock. Deterministico."""
    jb = JitterBuffer(on_emit=collect)
    last_ts = 0.0
    for e in entries:
        ts = e["arrival_ts"]
        # timer dovuti PRIMA dell'arrivo (due < ts): flush poi idle allo stesso ts
        while jb._timers and jb._timers[0][0] < ts:
            jb.tick(jb._timers[0][0])
        jb.process_frame(e["seq_id"], e["payload"], ts)
        # timer dovuti ESATTAMENTE a ts (dopo l'arrivo, ordering rule)
        jb.tick(ts)
        last_ts = ts
    # drain finale: simula 200ms di silenzio per far scattare flush+idle
    for dt in (33, 66, 100, 200):
        jb.tick(last_ts + dt)
    return jb


def replay_trace(path: str):
    with open(path, "rb") as f:
        entries = msgpack.unpackb(f.read(), raw=False)
    out = []
    jb = _run_trace(entries, out.append)
    return jb, out


def fingerprint(out: list[EmittedFrame]) -> list:
    """Firma deterministica dell'output (solo campi osservabili a valle)."""
    return [(e.seq_id, e.status, e.boundary) for e in out]


def check_determinism(path: str) -> bool:
    jb1, out1 = replay_trace(path)
    jb2, out2 = replay_trace(path)
    a, b = fingerprint(out1), fingerprint(out2)
    same = a == b
    print(f"[check] replay#1={len(a)} frame, replay#2={len(b)} frame, "
          f"A==B -> {same}", flush=True)
    return same


# --------------------------------------------------------------------- report

def _pct(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * p / 100))]


def report(path: str):
    jb, out = replay_trace(path)
    s = jb.stats
    emitted_seqs = [e.seq_id for e in out]
    inter = [b - a for a, b in zip(emitted_seqs, emitted_seqs[1:])]
    delays = s.buffer_delay_ms
    rep = {
        "packets_received": s.received,
        "accepted": s.accepted,
        "reordered": s.reordered,
        "duplicates_dropped": s.duplicates,
        "late_dropped": s.late,
        "out_of_window_dropped": s.out_of_window,
        "declared_gap_seq_ids": s.declared_gaps,
        "gap_events": s.gap_events,
        "epochs": s.epochs,
        "tracker_resets": s.tracker_resets,
        "emitted": len(out),
        "inter_frame_seq_delta_p50": _pct(inter, 50),
        "inter_frame_seq_delta_p95": _pct(inter, 95),
        "inter_frame_seq_delta_p99": _pct(inter, 99),
        "buffer_delay_ms_p50": _pct(delays, 50),
        "buffer_delay_ms_p95": _pct(delays, 95),
        "buffer_delay_ms_p99": _pct(delays, 99),
        "deterministic": check_determinism(path),
    }
    print(json.dumps(rep, indent=2), flush=True)
    return rep


# ------------------------------------------------------------------- synthetic

def synth_trace(path: str, n: int = 300, loss: float = 0.0,
                reorder: float = 0.0, seed: int = 42):
    """Genera una traccia sintetica: frame a 33ms, con perdite e riordini."""
    import random
    rng = random.Random(seed)
    entries = []
    t = 0.0
    seqs = list(range(n))
    # perdite
    alive = [s for s in seqs if rng.random() >= loss]
    # riordino: scambia coppie adiacenti con prob reorder
    i = 0
    while i < len(alive) - 1:
        if rng.random() < reorder:
            alive[i], alive[i + 1] = alive[i + 1], alive[i]
            i += 2
        else:
            i += 1
    for s in alive:
        t += 33.0 + rng.uniform(-4, 4)  # jitter di reale arrivo
        entries.append({
            "arrival_ts": t,
            "seq_id": s,
            "payload": {"seq": s, "ts": int(t), "landmarks": [],
                        "valid": True},
        })
    with open(path, "wb") as f:
        f.write(msgpack.packb(entries, use_bin_type=True))
    print(f"[synth] {len(entries)} frame -> {path} "
          f"(loss={loss}, reorder={reorder})", flush=True)


# ------------------------------------------------------------------------ cli

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "record":
        record_trace(path)
    elif cmd == "replay":
        _jb, out = replay_trace(path)
        for e in out:
            print(f"emit seq={e.seq_id} status={e.status} "
                  f"boundary={e.boundary} ts={e.emit_ts:.1f}")
    elif cmd == "report":
        report(path)
    elif cmd == "check":
        ok = check_determinism(path)
        sys.exit(0 if ok else 1)
    elif cmd == "synth":
        loss = float(sys.argv[sys.argv.index("--loss") + 1]) if "--loss" in sys.argv else 0.0
        reorder = float(sys.argv[sys.argv.index("--reorder") + 1]) if "--reorder" in sys.argv else 0.0
        synth_trace(path, loss=loss, reorder=reorder)


if __name__ == "__main__":
    main()
