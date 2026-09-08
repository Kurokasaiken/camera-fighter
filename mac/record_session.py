"""T-004 — Recorder sessioni strutturate (PLAN-048e).

Ogni sessione produce DUE file in sessions/:
  <session_id>.trace      pacchetti grezzi (arrival_ts, seq_id, payload)
  <session_id>.meta.json  metadata: session_id, gesture atteso, lato,
                          split (calibration|evaluation), condizioni,
                          versione pipeline (git sha), note.

Regole (dal piano): split a livello di SESSIONE; mai mescolare
calibration/evaluation nella stessa sessione; il Director dichiara lo
split PRIMA della registrazione.

Uso:
  venv/bin/python record_session.py <gesture> <lato> <split> [note...]
  es: record_session.py jab right calibration veloce

Durante la registrazione premi INVIO per marcare start/end evento
(ground truth sincronizzata su capture_ts del frame piu' vicino).
Ctrl+C termina e salva.
"""

from __future__ import annotations

import json
import select
import socket
import subprocess
import sys
import time
import uuid

import msgpack

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
OUT_DIR = "sessions"

GESTURES = {"idle", "jab", "double_jab", "kick", "block", "dodge",
            "walk", "transitions", "guard"}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def main():
    gesture = sys.argv[1] if len(sys.argv) > 1 else "idle"
    side = sys.argv[2] if len(sys.argv) > 2 else "both"
    split = sys.argv[3] if len(sys.argv) > 3 else "calibration"
    note = " ".join(sys.argv[4:])
    assert gesture in GESTURES, f"gesture sconosciuto: {GESTURES}"
    assert split in ("calibration", "evaluation")

    sid = f"{time.strftime('%Y%m%d-%H%M%S')}-{gesture}-{uuid.uuid4().hex[:6]}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    entries = []
    marks = []            # (mono_ms, "start"|"end") poi mappati su capture_ts
    t0 = time.monotonic()
    print(f"[REC] {sid} | gesture={gesture} side={side} split={split}")
    print("[REC] INVIO = marca start/end evento | Ctrl+C = salva")

    try:
        while True:
            now_ms = (time.monotonic() - t0) * 1000.0
            try:
                while True:
                    data, _ = sock.recvfrom(65535)
                    pkt = msgpack.unpackb(data, raw=False)
                    pkt.setdefault("valid", True)
                    entries.append({"arrival_ts": now_ms,
                                    "seq_id": pkt.get("seq", -1),
                                    "payload": pkt})
            except BlockingIOError:
                pass
            # INVIO su stdin marca un evento GT
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                marks.append(now_ms)
                print(f"[REC] mark #{len(marks)} @ {now_ms:.0f}ms",
                      flush=True)
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass

    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    # marks -> ground truth intervals su capture_ts del frame piu' vicino
    # (regola deterministica: nearest capture_ts, tie-break seq_id minore)
    gt = []
    for i in range(0, len(marks) - 1, 2):
        s, e2 = marks[i], marks[i + 1]
        def nearest(m):
            best = min(entries, key=lambda x: (abs(x["arrival_ts"] - m),
                                               x["seq_id"]))
            return float(best["payload"].get("ts", 0))
        gt.append({"gesture": gesture, "side": side,
                   "start_ts": nearest(s), "end_ts": nearest(e2)})
    if len(marks) % 2:
        print("[REC] WARN: mark dispari, ultimo ignorato")

    meta = {
        "session_id": sid, "gesture": gesture, "side": side,
        "split": split, "note": note, "pipeline_sha": git_sha(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_frames": len(entries),
        "span_ms": (entries[-1]["arrival_ts"] - entries[0]["arrival_ts"]
                    if entries else 0),
        "ground_truth": gt,
        "rules": {"labeling": "INVIO marca start/end; nearest capture_ts, "
                              "tie-break seq_id; eventi ravvicinati ammessi; "
                              "evento abortito = marca singola (ignorata)"},
    }
    with open(f"{OUT_DIR}/{sid}.trace", "wb") as f:
        f.write(msgpack.packb(entries, use_bin_type=True))
    with open(f"{OUT_DIR}/{sid}.meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[REC] salvato {OUT_DIR}/{sid}.trace ({len(entries)} frames) + meta")


if __name__ == "__main__":
    main()
