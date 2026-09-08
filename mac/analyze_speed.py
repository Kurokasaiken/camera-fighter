"""Analizza la velocita del polso nella registrazione."""

import math
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
    packets = load_capture("captures/pugno_destro/rep_001.msgpack")
    prev = None
    for i, p in enumerate(packets):
        lm = p.get("landmarks", [])
        if not lm or len(lm) < 33:
            continue
        norm = normalize(lm)
        f = extract(norm)
        if not f:
            continue
        if prev:
            dx = f["right_wrist_x"] - prev["right_wrist_x"]
            dy = f["right_wrist_y"] - prev["right_wrist_y"]
            speed = math.hypot(dx, dy)
            print(f"frame {i:2d}: speed={speed:.4f}")
        prev = f


if __name__ == "__main__":
    main()
