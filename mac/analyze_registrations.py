"""Analizza quanto variano le feature tra le 5 registrazioni del pugno destro."""

import json
import math
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


def main():
    captures = sorted([f for f in os.listdir("captures/pugno_destro") if f.endswith(".msgpack")])
    if not captures:
        print("Nessuna cattura")
        return

    all_features = []
    for c in captures:
        packets = load_capture(f"captures/pugno_destro/{c}")
        features = []
        for p in packets:
            lm = p.get("landmarks", [])
            if not lm or len(lm) < 33:
                continue
            norm = normalize(lm)
            f = extract(norm)
            if f:
                features.append(f)
        all_features.append(features)

    # Calcola min/max per ogni feature in ogni ripetizione
    keys = list(all_features[0][0].keys())
    stats = {k: [] for k in keys}
    for rep in all_features:
        for k in keys:
            values = [f[k] for f in rep]
            stats[k].append({
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "range": max(values) - min(values),
            })

    print("=== VARIAZIONE FEATURE TRA 5 REGISTRAZIONI ===")
    print("Feature | min globale | max globale | range medio | variazione %")
    for k in keys:
        mins = [s["min"] for s in stats[k]]
        maxs = [s["max"] for s in stats[k]]
        ranges = [s["range"] for s in stats[k]]
        global_min = min(mins)
        global_max = max(maxs)
        range_mean = sum(ranges) / len(ranges)
        spread = max(maxs) - min(mins)
        variation = (spread / (abs(global_max - global_min) + 1e-6)) * 100
        print(f"{k:30s} | {global_min:8.3f} | {global_max:8.3f} | {range_mean:8.3f} | {variation:6.1f}%")

    # Salva statistiche
    with open("captures/pugno_destro/stats.json", "w", encoding="utf-8") as f:
        json.dump({k: [{kk: float(vv) for kk, vv in s.items()} for s in v] for k, v in stats.items()}, f, indent=2)
    print("\nSalvato: captures/pugno_destro/stats.json")


if __name__ == "__main__":
    main()
