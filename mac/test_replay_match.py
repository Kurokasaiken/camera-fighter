"""Test: carica N pacchetti e fa match in tempo reale simulato."""

import msgpack

from features import extract
from matcher import Matcher
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
    matcher = Matcher("templates")
    packets = load_capture("captures/pugno_destro/rep_001.msgpack")
    print(f"Pacchetti: {len(packets)}")

    live = []
    for i, p in enumerate(packets):
        lm = p.get("landmarks", [])
        if not lm or len(lm) < 33:
            continue
        norm = normalize(lm)
        f = extract(norm)
        if f:
            live.append(f)

        if len(live) % 15 == 0 and len(live) >= 30:
            results = matcher.match(live)
            best, score = matcher.best(live, threshold=0.30)
            print(f"Frame {len(live)}: results={results}, best={best} ({score})")

    results = matcher.match(live)
    best, score = matcher.best(live, threshold=0.30)
    print(f"FINALE: results={results}, best={best} ({score})")


if __name__ == "__main__":
    main()
