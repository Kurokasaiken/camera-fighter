"""S0 live receiver — PLAN-048d.

UDP -> JitterBuffer -> frame ordinati -> traccia registrata.
Il virtual clock live è monotonic ms; i timer scattano via tick().
Ctrl+C -> salva traccia + stampa report.
"""

from __future__ import annotations

import socket
import sys
import time

import msgpack

from jitter_buffer import JitterBuffer

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
TRACE_PATH = "s0_live.trace"


def main(trace_path: str = TRACE_PATH):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    entries = []          # traccia per replay deterministico
    emitted = []

    jb = JitterBuffer(on_emit=lambda ef: emitted.append(ef))
    t0 = time.monotonic()
    print(f"[S0] UDP :{UDP_PORT} -> jitter buffer -> trace {trace_path}",
          flush=True)

    try:
        while True:
            now_ms = (time.monotonic() - t0) * 1000.0
            try:
                data, _addr = sock.recvfrom(65535)
            except BlockingIOError:
                data = None
            if data is not None:
                try:
                    pkt = msgpack.unpackb(data, raw=False)
                except Exception:
                    pkt = None
                if pkt is not None:
                    seq = pkt.get("seq", -1)
                    pkt.setdefault("valid", True)
                    entries.append({"arrival_ts": now_ms, "seq_id": seq,
                                    "payload": pkt})
                    jb.process_frame(seq, pkt, now_ms)
            jb.tick(now_ms)
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass

    # flush finale + salvataggio
    jb.tick((time.monotonic() - t0) * 1000.0 + 200)
    with open(trace_path, "wb") as f:
        f.write(msgpack.packb(entries, use_bin_type=True))

    s = jb.stats
    print("\n[S0] report live:", flush=True)
    for k in ("received", "accepted", "reordered", "duplicates", "late",
              "out_of_window", "declared_gaps", "gap_events", "epochs",
              "tracker_resets"):
        print(f"  {k}: {getattr(s, k)}", flush=True)
    print(f"  emitted: {len(emitted)}", flush=True)
    print(f"  trace -> {trace_path}  (verifica: python replay_harness.py check "
          f"{trace_path})", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else TRACE_PATH)
