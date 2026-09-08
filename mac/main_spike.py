"""Main spike headless — PLAN-048d.

Live:   python main_spike.py live [--trace out.trace]
Replay: python main_spike.py replay in.trace
Synth:  python main_spike.py synth <kind> [--loss X --reorder Y]

Pipeline: UDP -> JitterBuffer -> BodyModel -> MotionSignal -> Segmenter
          -> ComboEngine + HitSignal -> log eventi + report.
"""

from __future__ import annotations

import socket
import sys
import time

import msgpack

from jitter_buffer import JitterBuffer
from pipeline import Pipeline
from replay_harness import replay_trace
import synth_pose

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
COMBOS = "combos.json"


def log_out(o):
    for m in o.motion_events:
        print(f"  [MOTION] seq={m.seq_start}-{m.seq_end} {m.action} "
              f"{m.direction} v={m.peak_speed:.3f}", flush=True)
    for h in o.hit_events:
        print(f"  [HIT] seq={h.seq_id} {h.joint} speed={h.speed}", flush=True)
    for c in o.commits:
        print(f"  [COMMIT] {c.combo_id} seq={c.seq_start}-{c.seq_end} "
              f"score={c.score} t={c.t_decision:.0f}ms", flush=True)


def run_live(trace_path=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)
    pipe = Pipeline(COMBOS)
    entries = []
    jb = JitterBuffer(on_emit=lambda ef: log_out(pipe.process(ef)))
    t0 = time.monotonic()
    print(f"[spike] UDP :{UDP_PORT} (Ctrl+C per stop)", flush=True)
    try:
        while True:
            now = (time.monotonic() - t0) * 1000.0
            try:
                data, _ = sock.recvfrom(65535)
            except BlockingIOError:
                data = None
            if data is not None:
                try:
                    pkt = msgpack.unpackb(data, raw=False)
                except Exception:
                    pkt = None
                if pkt is not None:
                    pkt.setdefault("valid", True)
                    entries.append({"arrival_ts": now, "seq_id": pkt.get("seq", -1),
                                    "payload": pkt})
                    jb.process_frame(pkt.get("seq", -1), pkt, now)
            jb.tick(now)
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    if trace_path:
        with open(trace_path, "wb") as f:
            f.write(msgpack.packb(entries, use_bin_type=True))
        print(f"[spike] trace -> {trace_path}", flush=True)
    s = jb.stats
    print(f"[spike] received={s.received} reordered={s.reordered} "
          f"dup={s.duplicates} late={s.late} gaps={s.declared_gaps} "
          f"epochs={s.epochs} emitted={len(pipe.outputs)}", flush=True)


def run_replay(path):
    pipe = Pipeline(COMBOS)
    jb_ref = {"jb": None}
    # replay_trace guida il buffer; intercettiamo gli emit
    import replay_harness
    out_frames = []
    with open(path, "rb") as f:
        entries = msgpack.unpackb(f.read(), raw=False)

    jb = JitterBuffer(on_emit=lambda ef: log_out(pipe.process(ef)))
    for e in entries:
        ts = e["arrival_ts"]
        while jb._timers and jb._timers[0][0] < ts:
            jb.tick(jb._timers[0][0])
        jb.process_frame(e["seq_id"], e["payload"], ts)
        jb.tick(ts)
    jb.tick(entries[-1]["arrival_ts"] + 200)
    s = jb.stats
    print(f"[replay] emitted={len(pipe.outputs)} gaps={s.declared_gaps} "
          f"epochs={s.epochs}", flush=True)


def run_synth(kind, loss=0.0, reorder=0.0):
    pipe = Pipeline(COMBOS)
    frames = synth_pose.gen_trace(kind, loss=loss, reorder=reorder)
    jb = JitterBuffer(on_emit=lambda ef: log_out(pipe.process(ef)))
    for f in frames:
        ts = float(f["ts"])
        while jb._timers and jb._timers[0][0] < ts:
            jb.tick(jb._timers[0][0])
        jb.process_frame(f["seq"], f, ts)
        jb.tick(ts)
    jb.tick(frames[-1]["ts"] + 200)
    print(f"[synth:{kind}] emitted={len(pipe.outputs)} "
          f"commits={sum(len(o.commits) for o in pipe.outputs)} "
          f"hits={sum(len(o.hit_events) for o in pipe.outputs)}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    mode = sys.argv[1]
    if mode == "live":
        tp = sys.argv[sys.argv.index("--trace") + 1] if "--trace" in sys.argv else None
        run_live(tp)
    elif mode == "replay":
        run_replay(sys.argv[2])
    elif mode == "synth":
        kind = sys.argv[2]
        loss = float(sys.argv[sys.argv.index("--loss") + 1]) if "--loss" in sys.argv else 0.0
        ro = float(sys.argv[sys.argv.index("--reorder") + 1]) if "--reorder" in sys.argv else 0.0
        run_synth(kind, loss, ro)
