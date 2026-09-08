"""Replay di una registrazione via UDP per testare main.py offline."""

import argparse
import socket
import time

import msgpack


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="captures/pugno_destro/rep_001.msgpack")
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--speed", type=float, default=1.0, help="1.0 = realtime, 2.0 = doppio")
    parser.add_argument("--loop", type=int, default=1)
    args = parser.parse_args()

    packets = load_capture(args.file)
    if not packets:
        print("Nessun pacchetto trovato")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    for loop in range(args.loop):
        print(f"Loop {loop + 1}/{args.loop} — invio {len(packets)} pacchetti")
        for i, p in enumerate(packets):
            raw = msgpack.packb(p)
            sock.sendto(raw, (args.ip, args.port))
            if i + 1 < len(packets):
                dt = packets[i + 1].get("ts", p.get("ts", 0)) - p.get("ts", 0)
                if dt > 0:
                    time.sleep(max(dt / 1000.0 / args.speed, 0.001))
        time.sleep(0.5)

    sock.close()
    print("Replay completato")


if __name__ == "__main__":
    main()
