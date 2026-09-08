"""Debug: mostra i valori grezzi del motion controller in tempo reale."""

import math
import socket
import time

import msgpack

from landmarks import (
    LEFT_ANKLE, RIGHT_ANKLE,
    LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_WRIST, RIGHT_WRIST,
)


def _point(lm, idx):
    return (lm[idx][0], lm[idx][1]) if idx < len(lm) else (0.0, 0.0)


def _conf(lm, idx):
    return lm[idx][2] if idx < len(lm) else 0.0


def _normalize(lm):
    if not lm or len(lm) < 28:
        return {}
    ls = _point(lm, LEFT_SHOULDER)
    rs = _point(lm, RIGHT_SHOULDER)
    lh = _point(lm, LEFT_HIP)
    rh = _point(lm, RIGHT_HIP)
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
            "c": _conf(lm, idx),
        }

    return {
        "left_wrist": norm(LEFT_WRIST),
        "right_wrist": norm(RIGHT_WRIST),
        "left_elbow": norm(LEFT_ELBOW),
        "right_elbow": norm(RIGHT_ELBOW),
        "left_ankle": norm(LEFT_ANKLE),
        "right_ankle": norm(RIGHT_ANKLE),
        "left_knee": norm(LEFT_KNEE),
        "right_knee": norm(RIGHT_KNEE),
        "left_shoulder": norm(LEFT_SHOULDER),
        "right_shoulder": norm(RIGHT_SHOULDER),
        "left_hip": norm(LEFT_HIP),
        "right_hip": norm(RIGHT_HIP),
    }


def _angle(a, b, c):
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])
    if mag1 == 0 or mag2 == 0:
        return 180.0
    cos = max(-1, min(1, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos))


class LimbDebug:
    def __init__(self, alpha=0.3):
        self.alpha = alpha
        self.smoothed = None
        self.prev_pos = None
        self.prev_time = None
        self.prev_v = 0.0
        self.v = 0.0
        self.a = 0.0
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
        v = (self.smoothed - self.prev_pos) / dt
        self.a = (v - self.prev_v) / dt
        self.prev_v = v
        self.v = v
        self.prev_pos = self.smoothed
        self.prev_time = now_ms

        self.speed_history.append(abs(self.v))
        if len(self.speed_history) > 3:
            self.speed_history.pop(0)

    def avg_speed(self):
        if not self.speed_history:
            return 0.0
        return sum(self.speed_history) / len(self.speed_history)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind(("0.0.0.0", 5005))
    sock.setblocking(False)
    print("Ascolto UDP su 0.0.0.0:5005", flush=True)
    print("\n" + "-" * 80)
    print("DEBUG: muoviti e guarda i valori. Chiudi con Ctrl+C.")
    print("-" * 80 + "\n")

    debugs = {
        "right_wrist": LimbDebug(),
        "left_wrist": LimbDebug(),
        "right_ankle": LimbDebug(),
        "left_ankle": LimbDebug(),
    }

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

                norm = _normalize(lm)
                if not norm:
                    continue

                for name, tracker in debugs.items():
                    side, part = name.split("_", 1)
                    key = f"{side}_{part}"
                    tracker.update(norm[key]["x"], ts)

                rw = norm["right_wrist"]
                lw = norm["left_wrist"]
                ra = norm["right_ankle"]
                la = norm["left_ankle"]

                re_a = _angle((norm["right_shoulder"]["x"], norm["right_shoulder"]["y"]),
                              (norm["right_elbow"]["x"], norm["right_elbow"]["y"]),
                              (rw["x"], rw["y"]))
                le_a = _angle((norm["left_shoulder"]["x"], norm["left_shoulder"]["y"]),
                              (norm["left_elbow"]["x"], norm["left_elbow"]["y"]),
                              (lw["x"], lw["y"]))
                rk_a = _angle((norm["right_hip"]["x"], norm["right_hip"]["y"]),
                              (norm["right_knee"]["x"], norm["right_knee"]["y"]),
                              (ra["x"], ra["y"]))
                lk_a = _angle((norm["left_hip"]["x"], norm["left_hip"]["y"]),
                              (norm["left_knee"]["x"], norm["left_knee"]["y"]),
                              (la["x"], la["y"]))

                if packets % 5 == 0:
                    print(f"--- frame {packets} ---", flush=True)
                    print(f"RIGHT HAND  x={rw['x']:.2f} y={rw['y']:.2f}  "
                          f"v={debugs['right_wrist'].v:+.2f}  "
                          f"avg={debugs['right_wrist'].avg_speed():.2f}  "
                          f"a={debugs['right_wrist'].a:+.2f}  "
                          f"elbow={re_a:.0f}  "
                          f"ext={abs(rw['x'] - norm['right_shoulder']['x']):.2f}",
                          flush=True)
                    print(f"LEFT  HAND  x={lw['x']:.2f} y={lw['y']:.2f}  "
                          f"v={debugs['left_wrist'].v:+.2f}  "
                          f"avg={debugs['left_wrist'].avg_speed():.2f}  "
                          f"a={debugs['left_wrist'].a:+.2f}  "
                          f"elbow={le_a:.0f}  "
                          f"ext={abs(lw['x'] - norm['left_shoulder']['x']):.2f}",
                          flush=True)
                    print(f"RIGHT FOOT  x={ra['x']:.2f} y={ra['y']:.2f}  "
                          f"v={debugs['right_ankle'].v:+.2f}  "
                          f"avg={debugs['right_ankle'].avg_speed():.2f}  "
                          f"a={debugs['right_ankle'].a:+.2f}  "
                          f"knee={rk_a:.0f}  "
                          f"lift={norm['right_hip']['y'] - norm['right_knee']['y']:.2f}",
                          flush=True)
                    print(f"LEFT  FOOT  x={la['x']:.2f} y={la['y']:.2f}  "
                          f"v={debugs['left_ankle'].v:+.2f}  "
                          f"avg={debugs['left_ankle'].avg_speed():.2f}  "
                          f"a={debugs['left_ankle'].a:+.2f}  "
                          f"knee={lk_a:.0f}  "
                          f"lift={norm['left_hip']['y'] - norm['left_knee']['y']:.2f}",
                          flush=True)
                    print()

        except BlockingIOError:
            pass
        except KeyboardInterrupt:
            running = False

        time.sleep(0.001)


if __name__ == "__main__":
    main()
