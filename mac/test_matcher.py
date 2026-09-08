"""Test offline del matcher su una registrazione."""

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
    packets = load_capture("captures/pugno_destro/rep_002.msgpack")
    live = []
    for p in packets:
        lm = p.get("landmarks", [])
        if not lm or len(lm) < 33:
            continue
        norm = normalize(lm)
        f = extract(norm)
        if f:
            live.append(f)

    print(f"Live frames: {len(live)}")
    results = matcher.match(live)
    print(f"Match: {results}")
    best, score = matcher.best(live)
    print(f"Best: {best} ({score})")


if __name__ == "__main__":
    main()
