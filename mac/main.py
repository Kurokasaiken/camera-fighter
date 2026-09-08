"""Receiver e visualizzatore principale per Camera Fighter."""

import argparse
import datetime
import math
import os
import socket
import time

import msgpack

from landmarks import LEFT_WRIST, RIGHT_WRIST, LEFT_ANKLE, RIGHT_ANKLE
from motion_controller import MotionController
from quality import compute_quality
from visualizer import WAIT, RECORDING, Visualizer


def _point(lm, idx):
    return (lm[idx][0], lm[idx][1]) if idx < len(lm) else (0.0, 0.0)


def _conf(lm, idx):
    return lm[idx][2] if idx < len(lm) else 0.0


def _normalize_lm(lm):
    if not lm or len(lm) < 28:
        return {}
    ls = _point(lm, 11)  # LEFT_SHOULDER
    rs = _point(lm, 12)  # RIGHT_SHOULDER
    lh = _point(lm, 23)  # LEFT_HIP
    rh = _point(lm, 24)  # RIGHT_HIP
    hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
    shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
    torso_h = math.hypot(shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1])
    if torso_h == 0:
        torso_h = 1.0

    def norm(idx):
        x, y = _point(lm, idx)
        return {
            "x": (x - hip_mid[0]) / torso_h,
            "y": (y - hip_mid[1]) / torso_h,
        }

    return {
        "right_wrist": norm(RIGHT_WRIST),
        "left_wrist": norm(LEFT_WRIST),
        "right_ankle": norm(RIGHT_ANKLE),
        "left_ankle": norm(LEFT_ANKLE),
    }


class LimbDebug:
    def __init__(self, alpha=0.3):
        self.alpha = alpha
        self.smoothed = None
        self.prev_pos = None
        self.prev_time = None
        self.v = 0.0
        self.speed_history = []

    def update(self, pos, now_ms):
        if self.smoothed is None:
            self.smoothed = pos
        else:
            self.smoothed = self.smoothed * (1 - self.alpha) + pos * self.alpha

        if self.prev_pos is None or self.prev_time is None:
            self.prev_pos = self.smoothed
            self.prev_time = now_ms
            return

        dt = max((now_ms - self.prev_time) / 1000.0, 0.008)
        self.v = (self.smoothed - self.prev_pos) / dt
        self.prev_pos = self.smoothed
        self.prev_time = now_ms

        self.speed_history.append(abs(self.v))
        if len(self.speed_history) > 3:
            self.speed_history.pop(0)

    def avg(self):
        if not self.speed_history:
            return 0.0
        return sum(self.speed_history) / len(self.speed_history)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="0.0.0.0", help="IP di ascolto")
    parser.add_argument("--port", type=int, default=5005, help="Porta UDP")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind((args.ip, args.port))
    sock.setblocking(False)
    print(f"Ascolto UDP su {args.ip}:{args.port}", flush=True)

    controller = MotionController()
    vis = Visualizer()

    latest_landmarks = []
    latest_event = ""
    last_packet_time = 0.0
    fps = 0.0

    recording = False
    recorded_packets = []
    capture_dir = "captures"
    os.makedirs(capture_dir, exist_ok=True)

    debugs = {
        "right_hand": LimbDebug(),
        "left_hand": LimbDebug(),
        "right_foot": LimbDebug(),
        "left_foot": LimbDebug(),
    }
    prev_norm = None

    running = True
    while running and vis.widget.isVisible():
        vis.app.processEvents()

        # Ricezione UDP
        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packet = msgpack.unpackb(data, raw=False)
                latest_landmarks = packet.get("landmarks", [])
                ts = packet.get("ts", int(time.time() * 1000))
                last_packet_time = time.time()
                if recording:
                    recorded_packets.append(packet)

                norm = _normalize_lm(latest_landmarks)
                if norm and norm.get("right_wrist"):
                    debugs["right_hand"].update(norm["right_wrist"]["x"], ts)
                    debugs["left_hand"].update(norm["left_wrist"]["x"], ts)
                    debugs["right_foot"].update(norm["right_ankle"]["x"], ts)
                    debugs["left_foot"].update(norm["left_ankle"]["x"], ts)

                events = controller.update(latest_landmarks, ts)
                if events:
                    ev = events[0]
                    latest_event = f"{ev.side} {ev.type} {ev.direction}"
                    print(f"MATCH: {latest_event}", flush=True)

        except BlockingIOError:
            pass

        # FPS di ricezione approssimativo
        if latest_landmarks:
            fps = 1.0 / (time.time() - last_packet_time) if (time.time() - last_packet_time) > 0 else 0.0

        debug_values = {
            "right_hand": {"v": debugs["right_hand"].v, "avg": debugs["right_hand"].avg(), "a": 0.0},
            "left_hand": {"v": debugs["left_hand"].v, "avg": debugs["left_hand"].avg(), "a": 0.0},
            "right_foot": {"v": debugs["right_foot"].v, "avg": debugs["right_foot"].avg(), "a": 0.0},
            "left_foot": {"v": debugs["left_foot"].v, "avg": debugs["left_foot"].avg(), "a": 0.0},
        }

        state = RECORDING if recording else WAIT
        vis.draw(
            latest_landmarks,
            state=state,
            quality=compute_quality(latest_landmarks),
            fps=fps,
            recording=recording,
            recorded=len(recorded_packets),
            technique=latest_event,
            debug_values=debug_values,
        )
        time.sleep(0.0001)

    sock.close()


if __name__ == "__main__":
    main()
