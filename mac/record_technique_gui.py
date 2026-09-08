"""Registratore con HUD Pygame per Camera Fighter.

Uso:
    python record_technique_gui.py --technique pugno_destro --reps 5 --duration 4

Controlli:
    R  = inizia/ferma manualmente
    S  = salva subito
    Q  = esci
"""

import argparse
import datetime
import json
import os
import signal
import socket
import sys
import time

import msgpack
import pygame

from quality import compute_quality, body_in_frame
from visualizer import WAIT, READY, COUNTDOWN, RECORDING, REVIEW, Visualizer


def save_recording(capture_dir: str, technique: str, rep: int, packets: list):
    os.makedirs(capture_dir, exist_ok=True)
    filename = os.path.join(capture_dir, f"rep_{rep:03d}.msgpack")
    metafile = os.path.join(capture_dir, f"rep_{rep:03d}.json")

    with open(filename, "wb") as f:
        for p in packets:
            f.write(msgpack.packb(p))

    meta = {
        "technique": technique,
        "rep": rep,
        "timestamp": datetime.datetime.now().isoformat(),
        "frames": len(packets),
        "file": filename,
    }
    with open(metafile, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--technique", required=True, help="Nome della tecnica")
    parser.add_argument("--reps", type=int, default=5, help="Numero di ripetizioni")
    parser.add_argument("--duration", type=float, default=4.0, help="Durata registrazione in secondi")
    parser.add_argument("--ip", default="0.0.0.0", help="IP di ascolto")
    parser.add_argument("--port", type=int, default=5005, help="Porta UDP")
    args = parser.parse_args()

    capture_dir = os.path.join("captures", args.technique)
    os.makedirs(capture_dir, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.ip, args.port))
    sock.setblocking(False)

    vis = Visualizer()

    quality_buffer = []
    state = WAIT
    countdown = 3
    countdown_start = 0.0
    rep = 0
    recorded_packets = []
    recording_start = 0.0
    last_packet_time = 0.0
    fps = 0.0
    quality = {}

    running = True

    def handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handler)

    print(f"Ascolto UDP su {args.ip}:{args.port}")
    print(f"Tecnica: {args.technique} | Ripetizioni: {args.reps}")
    print("Controlli: R = start/stop | S = salva | Q = esci")

    while running and rep < args.reps:
        # Ricezione UDP
        latest_landmarks = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    running = False
                elif event.key == pygame.K_r:
                    if state == WAIT:
                        state = COUNTDOWN
                        countdown = 3
                        countdown_start = time.time()
                    elif state == COUNTDOWN:
                        # salta countdown
                        state = RECORDING
                        recorded_packets = []
                        recording_start = time.time()
                    elif state == RECORDING:
                        state = REVIEW
                        rep += 1
                        filename = save_recording(capture_dir, args.technique, rep, recorded_packets)
                        print(f"Salvato: {filename} ({len(recorded_packets)} frame)")
                        state = WAIT
                        quality_buffer = []
                elif event.key == pygame.K_s:
                    if state == RECORDING:
                        state = REVIEW
                        rep += 1
                        filename = save_recording(capture_dir, args.technique, rep, recorded_packets)
                        print(f"Salvato: {filename} ({len(recorded_packets)} frame)")
                        state = WAIT
                        quality_buffer = []

        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packet = msgpack.unpackb(data, raw=False)
                latest_landmarks = packet.get("landmarks", [])
                last_packet_time = time.time()

                if state == RECORDING:
                    recorded_packets.append(packet)

                q = compute_quality(latest_landmarks)
                quality = q

        except BlockingIOError:
            pass

        # Countdown
        if state == COUNTDOWN:
            elapsed = time.time() - countdown_start
            if elapsed >= 3.0:
                state = RECORDING
                recorded_packets = []
                recording_start = time.time()
            else:
                remaining = 3.0 - elapsed
                countdown = int(remaining) + 1

        # Fine recording automatico
        if state == RECORDING and (time.time() - recording_start) >= args.duration:
            state = REVIEW
            rep += 1
            filename = save_recording(capture_dir, args.technique, rep, recorded_packets)
            print(f"Salvato: {filename} ({len(recorded_packets)} frame)")
            state = WAIT
            quality_buffer = []

        # FPS
        if latest_landmarks:
            fps = 1.0 / (time.time() - last_packet_time) if (time.time() - last_packet_time) > 0 else 0.0

        vis.draw(
            latest_landmarks,
            state=state,
            countdown=countdown,
            quality=quality,
            fps=fps,
            recording=state == RECORDING,
            recorded=len(recorded_packets),
            technique=args.technique,
        )

    pygame.quit()
    sock.close()
    print("Uscita.")


if __name__ == "__main__":
    main()
