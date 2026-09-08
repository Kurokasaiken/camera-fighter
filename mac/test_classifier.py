"""Test offline del classificatore su una registrazione salvata."""

import json
import msgpack
import time

from classifier import Classifier


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
    clf = Classifier("calibration.json")
    packets = load_capture("captures/pugno_destro/rep_001.msgpack")
    print(f"Caricati {len(packets)} pacchetti.")

    events = []
    for p in packets:
        ts = p.get("ts", 0) / 1000.0
        ev = clf.update(p.get("landmarks", []), timestamp=ts)
        if ev:
            events.append(ev)
            print(f"  {ev} @ {ts}")

    print(f"\nEventi rilevati: {events}")


if __name__ == "__main__":
    main()
