"""Receiver minimale: stampa i pacchetti UDP ricevuti."""

import socket

import msgpack

UDP_IP = "0.0.0.0"
UDP_PORT = 5005


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Ascolto UDP su {UDP_IP}:{UDP_PORT}", flush=True)

    while True:
        data, addr = sock.recvfrom(65535)
        try:
            packet = msgpack.unpackb(data, raw=False)
            seq = packet.get("seq", -1)
            ts = packet.get("ts", -1)
            landmarks = packet.get("landmarks", [])
            print(f"[{seq} @ {ts}] ricevuti {len(landmarks)} landmark da {addr}", flush=True)
        except Exception as e:
            print(f"Errore decoding: {e}", flush=True)


if __name__ == "__main__":
    main()
