"""Test match con diverse finestre di frame centrali."""

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
    live = []
    for p in packets:
        lm = p.get("landmarks", [])
        if not lm or len(lm) < 33:
            continue
        norm = normalize(lm)
        f = extract(norm)
        if f:
            live.append(f)

    for window in [15, 20, 25, 30, 35, 40]:
        for start in [0, 5, 10, 15, 20]:
            sub = live[start:start + window]
            if len(sub) < window:
                continue
            results = matcher.match(sub)
            best, score = matcher.best(sub, threshold=0.30)
            print(f"start={start:2d} window={window:2d} -> {best} {score:.3f}  {results}")


if __name__ == "__main__":
    main()
