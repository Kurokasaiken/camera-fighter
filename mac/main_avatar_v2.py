"""Receiver con avatar V2: One Euro Filter + AvatarPose."""

import argparse
import socket
import time

import msgpack

from PySide6.QtWidgets import QApplication

from combat import CombatSystem
from pose_mapper import LandmarkToAvatarMapper
from renderer import SkeletonRenderer
from sfx import SoundBank


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind((args.ip, args.port))
    sock.setblocking(False)
    print(f"Ascolto UDP su {args.ip}:{args.port}", flush=True)

    app = QApplication([])
    renderer = SkeletonRenderer()
    renderer.show()

    mapper = LandmarkToAvatarMapper()
    combat = CombatSystem()
    renderer.combat = combat

    sounds = SoundBank()
    sounds.load("hit", "hit.wav")
    last_packet = 0.0
    fps = 0.0

    running = True
    while running and renderer.isVisible():
        app.processEvents()

        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packet = msgpack.unpackb(data, raw=False)
                landmarks = packet.get("landmarks", [])
                ts = packet.get("ts", int(time.time() * 1000)) / 1000.0

                now = time.time()
                dt = now - last_packet
                fps = 1.0 / dt if dt > 0 else 0.0
                last_packet = now

                pose = mapper.map(landmarks, ts)
                hits = combat.update(pose)
                for h in hits:
                    sounds.play("hit")
                    print(f"HIT {h.joint} v={h.speed:.1f} hp={combat.enemy.hp}", flush=True)
                renderer.update_pose(pose, landmarks, fps, hits)

        except BlockingIOError:
            pass

        time.sleep(0.001)

    sock.close()


if __name__ == "__main__":
    main()
