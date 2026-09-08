"""Calibrazione guidata per Camera Fighter.

Per ogni mossa, registra 3 ripetizioni lente e calcola i range delle feature scelte.
"""

import json
import os
import socket
import time
from collections import deque

import msgpack

from landmarks import (
    NOSE,
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ELBOW,
    RIGHT_ELBOW,
    LEFT_WRIST,
    RIGHT_WRIST,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
)


FEATURES = {
    # Polsi
    "right_wrist_x": (lambda lm: lm[RIGHT_WRIST][0]),
    "right_wrist_y": (lambda lm: lm[RIGHT_WRIST][1]),
    "left_wrist_x": (lambda lm: lm[LEFT_WRIST][0]),
    "left_wrist_y": (lambda lm: lm[LEFT_WRIST][1]),
    # Gomiti
    "right_elbow_x": (lambda lm: lm[RIGHT_ELBOW][0]),
    "right_elbow_y": (lambda lm: lm[RIGHT_ELBOW][1]),
    "left_elbow_x": (lambda lm: lm[LEFT_ELBOW][0]),
    "left_elbow_y": (lambda lm: lm[LEFT_ELBOW][1]),
    # Spalle
    "right_shoulder_x": (lambda lm: lm[RIGHT_SHOULDER][0]),
    "right_shoulder_y": (lambda lm: lm[RIGHT_SHOULDER][1]),
    "left_shoulder_x": (lambda lm: lm[LEFT_SHOULDER][0]),
    "left_shoulder_y": (lambda lm: lm[LEFT_SHOULDER][1]),
    # Fianchi
    "right_hip_x": (lambda lm: lm[RIGHT_HIP][0]),
    "right_hip_y": (lambda lm: lm[RIGHT_HIP][1]),
    "left_hip_x": (lambda lm: lm[LEFT_HIP][0]),
    "left_hip_y": (lambda lm: lm[LEFT_HIP][1]),
    # Ginocchia
    "right_knee_x": (lambda lm: lm[RIGHT_KNEE][0]),
    "right_knee_y": (lambda lm: lm[RIGHT_KNEE][1]),
    "left_knee_x": (lambda lm: lm[LEFT_KNEE][0]),
    "left_knee_y": (lambda lm: lm[LEFT_KNEE][1]),
    # Caviglie
    "right_ankle_y": (lambda lm: lm[RIGHT_ANKLE][1]),
    "left_ankle_y": (lambda lm: lm[LEFT_ANKLE][1]),
    # Naso
    "nose_x": (lambda lm: lm[NOSE][0]),
    "nose_y": (lambda lm: lm[NOSE][1]),
    # Relazioni laterali
    "right_wrist_ahead_elbow": (lambda lm: lm[RIGHT_WRIST][0] - lm[RIGHT_ELBOW][0]),
    "left_wrist_ahead_elbow": (lambda lm: lm[LEFT_WRIST][0] - lm[LEFT_ELBOW][0]),
    "right_wrist_above_shoulder": (lambda lm: lm[RIGHT_SHOULDER][1] - lm[RIGHT_WRIST][1]),
    "left_wrist_above_shoulder": (lambda lm: lm[LEFT_SHOULDER][1] - lm[LEFT_WRIST][1]),
    "right_knee_above_hip": (lambda lm: lm[RIGHT_HIP][1] - lm[RIGHT_KNEE][1]),
    "left_knee_above_hip": (lambda lm: lm[LEFT_HIP][1] - lm[LEFT_KNEE][1]),
    "nose_ahead_hips": (lambda lm: lm[NOSE][0] - (lm[LEFT_HIP][0] + lm[RIGHT_HIP][0]) / 2),
}


def choose_features():
    """L'utente sceglie quali feature usare per questo movimento."""
    print("\nFeature disponibili:")
    for i, name in enumerate(FEATURES.keys(), 1):
        print(f"  {i}. {name}")
    print("  0. usa le feature predefinite per pugno/calcio/parata/schivata")

    choice = input("Scegli numeri separati da virgola, oppure 0: ").strip()
    if choice == "0":
        return None
    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        names = list(FEATURES.keys())
        return [names[i - 1] for i in indices if 1 <= i <= len(names)]
    except (ValueError, IndexError):
        print("Scelta non valida, uso 0.")
        return None


def default_features(move_name: str):
    move = move_name.lower().strip()
    if "pugno" in move and "destro" in move:
        return ["right_wrist_x", "right_wrist_y", "right_wrist_ahead_elbow"]
    if "pugno" in move and "sinistro" in move:
        return ["left_wrist_x", "left_wrist_y", "left_wrist_ahead_elbow"]
    if "calcio" in move and "destro" in move:
        return ["right_knee_y", "right_knee_above_hip"]
    if "calcio" in move and "sinistro" in move:
        return ["left_knee_y", "left_knee_above_hip"]
    if "parata" in move:
        return ["right_wrist_above_shoulder", "left_wrist_above_shoulder"]
    if "schivata" in move:
        return ["nose_x", "nose_ahead_hips"]
    return ["right_wrist_x", "right_wrist_y"]


def record_sequence(sock, duration: float = 2.0):
    """Registra una sequenza di frame per un numero di secondi."""
    start = time.time()
    frames = []
    while time.time() - start < duration:
        try:
            data, _ = sock.recvfrom(65535)
            packet = msgpack.unpackb(data, raw=False)
            frames.append(packet.get("landmarks", []))
        except socket.timeout:
            pass
    return frames


def extract_feature_values(frames, feature_names):
    """Estrae i valori delle feature scelte da ogni frame."""
    values = {f: [] for f in feature_names}
    for lm in frames:
        if len(lm) < 33:
            continue
        for f in feature_names:
            try:
                values[f].append(FEATURES[f](lm))
            except (IndexError, KeyError):
                pass
    return values


def compute_ranges(recordings, feature_names):
    """Calcola min/max per ogni feature attraverso tutte le ripetizioni."""
    all_values = {f: [] for f in feature_names}
    for frames in recordings:
        values = extract_feature_values(frames, feature_names)
        for f in feature_names:
            all_values[f].extend(values[f])

    ranges = {}
    for f in feature_names:
        if all_values[f]:
            ranges[f] = {
                "min": float(min(all_values[f])),
                "max": float(max(all_values[f])),
            }
        else:
            ranges[f] = {"min": 0.0, "max": 1.0}
    return ranges


def load_calibration(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_calibration(calibration: dict, path: str):
    with open(path, "w") as f:
        json.dump(calibration, f, indent=2)


def main():
    path = "calibration.json"
    calibration = load_calibration(path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 5005))
    sock.settimeout(0.5)

    print("\n=== Calibrazione Camera Fighter ===")
    print("Il Mac è in ascolto sulla porta 5005.")
    print("Per ogni movimento farai 3 ripetizioni lente.\n")

    while True:
        move = input("Nome del movimento (es. 'pugno_destro', oppure INVIO per uscire): ").strip()
        if not move:
            break

        chosen = choose_features()
        feature_names = chosen if chosen else default_features(move)
        if not feature_names:
            print("Nessuna feature scelta, salto.")
            continue

        print(f"\nFeature selezionate per '{move}': {feature_names}")
        print("Quando premi INVIO inizierà una registrazione di 2 secondi.")

        recordings = []
        for i in range(3):
            input(f"Ripetizione {i+1}/3: premi INVIO ed esegui il movimento lento...")
            frames = record_sequence(sock, duration=2.0)
            recordings.append(frames)
            print(f"  Registrati {len(frames)} frame.")

        ranges = compute_ranges(recordings, feature_names)
        calibration[move] = {
            "features": feature_names,
            "ranges": ranges,
        }
        save_calibration(calibration, path)
        print(f"Salvato '{move}' in {path}.\n")

    sock.close()
    print("Calibrazione completata.")


if __name__ == "__main__":
    main()
