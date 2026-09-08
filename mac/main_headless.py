"""Versione headless con motion controller a bassa latenza."""

import socket
import time

import msgpack

from motion_controller import MotionController


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind(("0.0.0.0", 5005))
    sock.setblocking(False)
    print("Ascolto UDP su 0.0.0.0:5005", flush=True)

    controller = MotionController()

    packets = 0
    running = True
    while running:
        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packets += 1
                packet = msgpack.unpackb(data, raw=False)
                lm = packet.get("landmarks", [])
                ts = packet.get("ts", int(time.time() * 1000))

                if not lm or len(lm) < 33:
                    continue

                events = controller.update(lm, ts)
                for ev in events:
                    print(f"EVENT: {ev.side} {ev.type} {ev.direction} (conf={ev.confidence:.2f})", flush=True)

                if packets % 100 == 0:
                    print(f"pacchetto {packets}", flush=True)

        except BlockingIOError:
            pass
        except Exception as e:
            print(f"ERRORE: {e}", flush=True)

        time.sleep(0.001)


if __name__ == "__main__":
    main()
