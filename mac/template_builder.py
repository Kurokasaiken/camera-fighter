"""Costruisce template di feature normalizzate da registrazioni."""

import argparse
import json
import os

import msgpack

from features import extract
from normalization import normalize


def load_capture(path: str) -> list:
    packets = []
    with open(path, "rb") as f:
        data = f.read()
    unpacker = msgpack.Unpacker(raw=False)
    unpacker.feed(data)
    for p in unpacker:
        if isinstance(p, dict) and "landmarks" in p:
            packets.append(p)
    return packets


def _variance(values: list) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def trim_sequence(frames: list, feature_key: str = "right_wrist_ahead_shoulder",
                  window: int = 25) -> list:
    """Trova la finestra di movimento piu intensa e la restituisce."""
    if len(frames) <= window:
        return frames

    best_start = 0
    best_var = 0.0
    for i in range(0, len(frames) - window + 1):
        values = [f.get(feature_key, 0.0) for f in frames[i:i + window]]
        var = _variance(values)
        if var > best_var:
            best_var = var
            best_start = i

    return frames[best_start:best_start + window]


def build_template(capture_dir: str, technique: str, max_frames: int = 150,
                   template_window: int = 25) -> dict:
    """Costruisce un template semplice: trimmato sul movimento principale."""
    captures = sorted([f for f in os.listdir(capture_dir) if f.endswith(".msgpack")])
    if not captures:
        raise ValueError(f"Nessuna cattura in {capture_dir}")

    all_features = []

    for c in captures:
        packets = load_capture(os.path.join(capture_dir, c))
        features = []
        for p in packets:
            lm = p.get("landmarks", [])
            if not lm or len(lm) < 33:
                continue
            norm = normalize(lm)
            f = extract(norm)
            if f:
                features.append(f)
        all_features.append(features[:max_frames])

    # Per semplicita, prendi la prima registrazione come template canonico
    # troncata ai primi N frame: include guardia, pugno e inizio ritorno.
    # In futuro: media DTW-allineata
    canonical = all_features[0][:template_window]

    # Calcola min/max per normalizzazione
    feature_keys = list(canonical[0].keys()) if canonical else []
    ranges = {}
    for k in feature_keys:
        values = [f[k] for f in canonical]
        if values:
            ranges[k] = {
                "min": float(min(values)),
                "max": float(max(values)),
            }

    return {
        "technique": technique,
        "samples": len(all_features),
        "feature_keys": feature_keys,
        "ranges": ranges,
        "frames": canonical,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--technique", required=True)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    template = build_template(args.dir, args.technique)

    out = args.out or f"templates/{args.technique}.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    print(f"Template salvato: {out}")


if __name__ == "__main__":
    main()
