"""Calibrazione bias(angolo) — misura il bug segnalato dal Director (2026-09-16):

  braccia lungo i fianchi: bicipite ~0.55 (unita' torso)
  T-pose (braccia orizzontali): bicipite ~0.41

Nessun vero movimento in profondita' e' coinvolto (l'abduzione laterale resta
nel piano frontale, parallelo alla camera) — quindi la differenza NON e'
ambiguita' di profondita' geometrica, e' un bias sistematico che ML Kit
inventa quando stima z internamente (vedi ricerca in sessione: "the model is
guessing how far each joint sticks out ... based on patterns it learned in
training"). Se il bias e' funzione dell'angolo osservato, e' calibrabile.

Protocollo: il Director si mette di fronte alla camera, fermo, e tiene un
braccio a una sequenza di angoli noti (dichiarati da tastiera, non misurati
da sensori esterni — l'operatore stesso allinea il braccio a occhio/goniometro
o a un riferimento visivo tipo linea sul muro). Per ogni angolo: countdown,
poi N secondi di raccolta frame etichettati con quell'angolo.

Uso:
  venv/bin/python calibrate_arm_angle_bias.py [side] [hold_seconds]
  es: calibrate_arm_angle_bias.py left 4

Angoli di default: 0 (braccio lungo il fianco) fino a 90 (T-pose) a passi di 15.
Premi INVIO per iniziare ogni fase, Ctrl+C per terminare in anticipo (salva
comunque le fasi completate).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid

import msgpack

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
OUT_DIR = "sessions"

DEFAULT_ANGLES = [0, 15, 30, 45, 60, 75, 90]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def drain_socket(sock, entries, t0):
    """Svuota il socket UDP non bloccante, accumula in entries."""
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


def main():
    side = sys.argv[1] if len(sys.argv) > 1 else "left"
    hold_s = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    assert side in ("left", "right")

    sid = f"{time.strftime('%Y%m%d-%H%M%S')}-armbias-{side}-{uuid.uuid4().hex[:6]}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    entries = []
    segments = []  # {"angle_deg": int, "start_ms": float, "end_ms": float}
    t0 = time.monotonic()

    print(f"[CAL] {sid} | braccio={side} | hold={hold_s}s per angolo")
    print("[CAL] Mettiti di fronte alla camera, fermo, stessa distanza per tutta la sessione.")
    print("[CAL] Per ogni angolo: allinea il braccio, premi INVIO, resta fermo.\n")

    try:
        for angle in DEFAULT_ANGLES:
            input(f"[CAL] Prossimo: {side} a {angle}° dal fianco (0=giu', 90=T-pose). "
                  f"Premi INVIO quando sei pronto e fermo...")
            print(f"[CAL] Registro {angle}°", end="", flush=True)

            # drain eventuale backlog prima di iniziare il segmento pulito
            drain_socket(sock, entries, t0)
            start_ms = (time.monotonic() - t0) * 1000.0

            elapsed = 0.0
            while elapsed < hold_s:
                drain_socket(sock, entries, t0)
                time.sleep(0.02)
                elapsed = (time.monotonic() - t0) * 1000.0 / 1000.0 - start_ms / 1000.0
                print(".", end="", flush=True)

            end_ms = (time.monotonic() - t0) * 1000.0
            segments.append({"angle_deg": angle, "start_ms": start_ms, "end_ms": end_ms})
            print(f" fatto ({end_ms - start_ms:.0f}ms)")
    except KeyboardInterrupt:
        print("\n[CAL] interrotto — salvo le fasi completate")

    os.makedirs(OUT_DIR, exist_ok=True)

    meta = {
        "session_id": sid,
        "kind": "arm_angle_bias_calibration",
        "side": side,
        "hold_seconds": hold_s,
        "segments": segments,
        "pipeline_sha": git_sha(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_frames": len(entries),
        "note": "misura bias(angolo) su bicipite — vedi calibrate_arm_angle_bias.py docstring",
    }

    with open(f"{OUT_DIR}/{sid}.trace", "wb") as f:
        f.write(msgpack.packb(entries, use_bin_type=True))
    with open(f"{OUT_DIR}/{sid}.meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n[CAL] salvato {OUT_DIR}/{sid}.trace ({len(entries)} frame) + meta")
    print(f"[CAL] analizza con: venv/bin/python analyze_arm_angle_bias.py {sid}")


if __name__ == "__main__":
    main()
