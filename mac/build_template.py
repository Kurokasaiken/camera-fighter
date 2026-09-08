"""Costruisce un template semplice da una cartella di registrazioni."""

import argparse
import json
import os

import msgpack

from calibration import FEATURES, default_features
from quality import RIGHT_WRIST, RIGHT_ELBOW, RIGHT_SHOULDER


def load_capture(path: str) -> list:
    """Carica una cattura .msgpack e restituisce lista di pacchetti."""
    packets = []
    with open(path, "rb") as f:
        data = f.read()
    unpacker = msgpack.Unpacker(raw=False)
    unpacker.feed(data)
    for p in unpacker:
        if isinstance(p, dict) and "landmarks" in p:
            packets.append(p)
    return packets


def distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def extract_features(packets: list) -> dict:
    """Estrae feature principali per un pugno destro."""
    wrist_x = []
    wrist_y = []
    wrist_dist_shoulder = []
    elbow_angle = []

    for p in packets:
        lm = p.get("landmarks", [])
        if len(lm) < 17:
            continue
        w = lm[RIGHT_WRIST]
        s = lm[RIGHT_SHOULDER]
        e = lm[RIGHT_ELBOW]

        wrist_x.append(w[0])
        wrist_y.append(w[1])
        wrist_dist_shoulder.append(distance(w, s))

        # angolo spalla-gomito-polso
        v1 = (s[0] - e[0], s[1] - e[1])
        v2 = (w[0] - e[0], w[1] - e[1])
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
        mag2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5
        if mag1 > 0 and mag2 > 0:
            cos = max(-1, min(1, dot / (mag1 * mag2)))
            import math
            elbow_angle.append(math.degrees(math.acos(cos)))

    return {
        "wrist_x_min": min(wrist_x) if wrist_x else 0,
        "wrist_x_max": max(wrist_x) if wrist_x else 0,
        "wrist_x_range": max(wrist_x) - min(wrist_x) if wrist_x else 0,
        "wrist_dist_min": min(wrist_dist_shoulder) if wrist_dist_shoulder else 0,
        "wrist_dist_max": max(wrist_dist_shoulder) if wrist_dist_shoulder else 0,
        "elbow_angle_min": min(elbow_angle) if elbow_angle else 0,
        "elbow_angle_max": max(elbow_angle) if elbow_angle else 0,
        "frames": len(packets),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--technique", required=True, help="Nome tecnica")
    parser.add_argument("--dir", required=True, help="Cartella con le catture")
    parser.add_argument("--out", default=None, help="File output template")
    args = parser.parse_args()

    captures = sorted([f for f in os.listdir(args.dir) if f.endswith(".msgpack")])
    if not captures:
        print("Nessuna cattura trovata.")
        return

    all_features = []
    for c in captures:
        path = os.path.join(args.dir, c)
        packets = load_capture(path)
        f = extract_features(packets)
        print(f"{c}: {f}")
        all_features.append(f)

    # Calibrazione compatibile con classifier.py
    feature_names = default_features(args.technique)
    all_values = {f: [] for f in feature_names}

    for c in captures:
        path = os.path.join(args.dir, c)
        packets = load_capture(path)
        for p in packets:
            lm = p.get("landmarks", [])
            if len(lm) < 33:
                continue
            for f in feature_names:
                try:
                    all_values[f].append(FEATURES[f](lm))
                except (IndexError, KeyError):
                    pass

    ranges = {}
    for f in feature_names:
        if all_values[f]:
            ranges[f] = {
                "min": float(min(all_values[f])),
                "max": float(max(all_values[f])),
            }
        else:
            ranges[f] = {"min": 0.0, "max": 1.0}

    calibration = {
        args.technique: {
            "features": feature_names,
            "ranges": ranges,
        }
    }

    out = args.out or "calibration.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2)
    print(f"Calibrazione salvata: {out}")


if __name__ == "__main__":
    main()
