"""Simulatore: invia pacchetti MessagePack finti per testare il receiver Mac."""

import socket
import struct
import time

import msgpack

UDP_IP = "127.0.0.1"
UDP_PORT = 5005


def make_landmarks(base_pose: list, changes: dict) -> list:
    lm = [list(p) for p in base_pose]
    for idx, (x, y, c) in changes.items():
        lm[idx] = [x, y, c]
    return lm


def base_pose():
    # 33 landmark, x, y, confidenza. Vista laterale, giocatore rivolto a destra.
    lm = []
    for _ in range(33):
        lm.append([0.3, 0.5, 0.9])
    # Testa
    lm[0] = [0.3, 0.3, 0.9]
    # Spalle
    lm[11] = [0.3, 0.35, 0.9]  # left_shoulder
    lm[12] = [0.35, 0.35, 0.9]  # right_shoulder
    # Gomiti
    lm[13] = [0.3, 0.45, 0.9]
    lm[14] = [0.35, 0.45, 0.9]
    # Polsi (inizialmente vicini)
    lm[15] = [0.3, 0.55, 0.9]
    lm[16] = [0.35, 0.55, 0.9]
    # Fianchi
    lm[23] = [0.3, 0.6, 0.9]
    lm[24] = [0.35, 0.6, 0.9]
    # Ginocchia
    lm[25] = [0.3, 0.75, 0.9]
    lm[26] = [0.35, 0.75, 0.9]
    return lm


def send_packet(sock, seq, landmarks):
    packet = {
        "ts": int(time.time() * 1000),
        "seq": seq,
        "landmarks": landmarks,
    }
    data = msgpack.packb(packet)
    sock.sendto(data, (UDP_IP, UDP_PORT))
    print(f"Inviato {seq}", flush=True)


def animate_punch():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0
    pose = base_pose()
    # fermo
    for _ in range(10):
        seq += 1
        send_packet(sock, seq, pose)
        time.sleep(1 / 30)
    # pugno destro: polso destro avanza
    for i in range(5):
        seq += 1
        x = 0.35 + i * 0.06
        pose[16] = [x, 0.55, 0.9]
        send_packet(sock, seq, pose)
        time.sleep(1 / 60)
    # ritorno
    for i in range(5):
        seq += 1
        x = 0.65 - i * 0.06
        pose[16] = [x, 0.55, 0.9]
        send_packet(sock, seq, pose)
        time.sleep(1 / 60)
    # fermo
    for _ in range(10):
        seq += 1
        send_packet(sock, seq, base_pose())
        time.sleep(1 / 30)


def main():
    print(f"Simulatore: invio a {UDP_IP}:{UDP_PORT}")
    while True:
        print("Simulazione pugno destro...")
        animate_punch()
        time.sleep(2.0)


if __name__ == "__main__":
    main()
