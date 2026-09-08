"""Registratore CLI automatizzato per tecniche Camera Fighter.

Uso manuale:
    python record_technique.py --technique pugno_destro --reps 5

Uso automatico:
    python record_technique.py --technique mae_geri --reps 5 --auto --duration 4
"""

import argparse
import datetime
import json
import os
import signal
import socket
import sys
import time

import msgpack


def flush_input():
    """Svuota stdin, funziona meglio con input() pulito."""
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--technique", required=True, help="Nome della tecnica (es. pugno_destro)")
    parser.add_argument("--reps", type=int, default=5, help="Numero di ripetizioni")
    parser.add_argument("--auto", action="store_true", help="Registra automaticamente per --duration secondi")
    parser.add_argument("--duration", type=float, default=4.0, help="Durata in secondi per modalita automatica")
    parser.add_argument("--ip", default="0.0.0.0", help="IP di ascolto")
    parser.add_argument("--port", type=int, default=5005, help="Porta UDP")
    args = parser.parse_args()

    capture_dir = os.path.join("captures", args.technique)
    os.makedirs(capture_dir, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.ip, args.port))
    sock.setblocking(False)
    print(f"Ascolto UDP su {args.ip}:{args.port}")
    print(f"Tecnica: {args.technique} | Ripetizioni: {args.reps}")
    print("Assicurati che il telefono stia trasmettendo.")

    partial_packets = []

    def save_partial():
        if not partial_packets:
            return
        filename = os.path.join(
            capture_dir,
            f"rep_000_partial_{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.msgpack"
        )
        with open(filename, "wb") as f:
            for p in partial_packets:
                f.write(msgpack.packb(p))
                f.write(b"\x00")
        print(f"\nSalvata cattura parziale: {filename}")

    def handler(sig, frame):
        print("\nInterruzione.")
        save_partial()
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)

    for rep in range(1, args.reps + 1):
        filename = os.path.join(capture_dir, f"rep_{rep:03d}.msgpack")
        metafile = os.path.join(capture_dir, f"rep_{rep:03d}.json")

        print(f"\n=== Ripetizione {rep}/{args.reps} ===")

        if args.auto:
            for i in range(3, 0, -1):
                print(f"  Inizio tra {i}...")
                time.sleep(1)
            print("  REC!")
            duration = args.duration
        else:
            input("  Premi INVIO per iniziare la registrazione...")
            print("  REC! Premi INVIO per fermare.")
            duration = None

        recorded = []
        start = time.time()
        running = True

        if args.auto:
            while time.time() - start < duration:
                try:
                    while True:
                        data, _ = sock.recvfrom(65535)
                        packet = msgpack.unpackb(data, raw=False)
                        recorded.append(packet)
                except BlockingIOError:
                    pass
                time.sleep(0.001)
                if len(recorded) % 30 == 0 and len(recorded) > 0:
                    print(f"    frame: {len(recorded)}", end="\r")
        else:
            # Modalita manuale: registra in un thread concorrente mentre aspetta input.
            import threading

            stop_event = threading.Event()

            def capture():
                while not stop_event.is_set():
                    try:
                        while True:
                            data, _ = sock.recvfrom(65535)
                            packet = msgpack.unpackb(data, raw=False)
                            recorded.append(packet)
                    except BlockingIOError:
                        pass
                    time.sleep(0.001)

            t = threading.Thread(target=capture)
            t.start()
            input()
            stop_event.set()
            t.join(timeout=0.5)

        end = time.time()

        with open(filename, "wb") as f:
            for p in recorded:
                f.write(msgpack.packb(p))

        meta = {
            "technique": args.technique,
            "rep": rep,
            "timestamp": datetime.datetime.now().isoformat(),
            "duration_s": round(end - start, 3),
            "frames": len(recorded),
            "file": filename,
        }
        with open(metafile, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        print(f"  Salvato: {filename} ({len(recorded)} frame in {end - start:.2f}s)")

        if not args.auto and rep < args.reps:
            input("  Premi INVIO per la prossima ripetizione...")

    print("\nRegistrazione completata.")
    print(f"File in: {capture_dir}")
    sock.close()


if __name__ == "__main__":
    main()
