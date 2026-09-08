"""Receiver con avatar 2D controllato dai landmark."""

import argparse
import os
import socket
import time

import msgpack

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget

from avatar import build_avatar, check_hits
from landmarks import LEFT_ANKLE, LEFT_ELBOW, LEFT_HIP, LEFT_KNEE
from landmarks import LEFT_SHOULDER, LEFT_WRIST
from landmarks import RIGHT_ANKLE, RIGHT_ELBOW, RIGHT_HIP, RIGHT_KNEE
from landmarks import RIGHT_SHOULDER, RIGHT_WRIST


SKELETON = [
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (RIGHT_HIP, RIGHT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_KNEE, RIGHT_ANKLE),
]


class AvatarWidget(QWidget):
    def __init__(self, width=960, height=540, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setWindowTitle("Camera Fighter — Avatar")
        self.width_f = width
        self.height_f = height
        self.latest_landmarks = []
        self.avatar = None
        self.enemy = {"x": width - 200, "y": int(height * 0.4), "w": 80, "h": 180, "hp": 100}
        self.score = 0
        self.last_hits = set()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 35))

        # Conteggio pacchetti
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 14)
        painter.setFont(font)
        painter.drawText(20, 80, f"Landmarks: {len(self.latest_landmarks)}")

        # Disegna nemico
        painter.setBrush(QBrush(QColor(180, 60, 60)))
        painter.setPen(Qt.NoPen)
        e = self.enemy
        painter.drawRoundedRect(int(e["x"]), int(e["y"]), e["w"], e["h"], 10, 10)

        # Disegna avatar
        if self.avatar:
            a = self.avatar
            pen = QPen(QColor(0, 255, 120))
            pen.setWidth(6)
            painter.setPen(pen)

            # Torso
            painter.drawLine(int(a["shoulder"][0]), int(a["shoulder"][1]),
                            int(a["hip"][0]), int(a["hip"][1]))

            # Braccia
            painter.drawLine(int(a["shoulder"][0]), int(a["shoulder"][1]),
                            int(a["right_elbow"][0]), int(a["right_elbow"][1]))
            painter.drawLine(int(a["right_elbow"][0]), int(a["right_elbow"][1]),
                            int(a["right_wrist"][0]), int(a["right_wrist"][1]))
            painter.drawLine(int(a["shoulder"][0]), int(a["shoulder"][1]),
                            int(a["left_elbow"][0]), int(a["left_elbow"][1]))
            painter.drawLine(int(a["left_elbow"][0]), int(a["left_elbow"][1]),
                            int(a["left_wrist"][0]), int(a["left_wrist"][1]))

            # Gambe
            painter.drawLine(int(a["hip"][0]), int(a["hip"][1]),
                            int(a["right_knee"][0]), int(a["right_knee"][1]))
            painter.drawLine(int(a["right_knee"][0]), int(a["right_knee"][1]),
                            int(a["right_ankle"][0]), int(a["right_ankle"][1]))
            painter.drawLine(int(a["hip"][0]), int(a["hip"][1]),
                            int(a["left_knee"][0]), int(a["left_knee"][1]))
            painter.drawLine(int(a["left_knee"][0]), int(a["left_knee"][1]),
                            int(a["left_ankle"][0]), int(a["left_ankle"][1]))

            # Testa
            painter.setBrush(QBrush(QColor(0, 255, 120)))
            painter.drawEllipse(int(a["head_center"][0] - a["head_r"]),
                               int(a["head_center"][1] - a["head_r"]),
                               int(a["head_r"] * 2), int(a["head_r"] * 2))

            # Hitbox debug
            painter.setPen(QPen(QColor(255, 255, 0, 120)))
            painter.setBrush(Qt.NoBrush)
            for hb in a["hitboxes"]:
                painter.drawEllipse(int(hb["x"] - hb["r"]), int(hb["y"] - hb["r"]),
                                   int(hb["r"] * 2), int(hb["r"] * 2))
        else:
            # Avatar placeholder in attesa di dati
            painter.setPen(QPen(QColor(100, 100, 100)))
            cx, cy = self.width_f // 2, int(self.height_f * 0.65)
            painter.drawText(int(cx - 80), int(cy - 80), "In attesa di landmark...")

        # UI
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 18)
        painter.setFont(font)
        painter.drawText(20, 30, f"HP nemico: {self.enemy['hp']}")
        painter.drawText(20, 55, f"Colpi: {self.score}")
        painter.drawText(20, self.height_f - 20, "Muovi le braccia/gambe verso il rettangolo rosso per colpire")

        painter.end()

    def update_landmarks(self, landmarks):
        self.latest_landmarks = landmarks
        self.avatar = build_avatar(landmarks, self.width_f, self.height_f)
        if not self.avatar and len(landmarks) >= 33:
            # Dati arrivati ma non validi per scale; prova con fallback
            print(f"Landmarks ricevuti: {len(landmarks)}, scale troppo piccola o zero", flush=True)
        if self.avatar:
            hits = check_hits(self.avatar, self.enemy)
            # non contare hit consecutive nello stesso frame
            new_hits = [h for h in hits if h not in self.last_hits]
            for _ in new_hits:
                self.enemy["hp"] = max(0, self.enemy["hp"] - 5)
                self.score += 1
            self.last_hits = set(hits)
        self.update()


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
    widget = AvatarWidget()
    widget.show()

    last_frame = time.time()
    running = True
    while running and widget.isVisible():
        app.processEvents()

        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packet = msgpack.unpackb(data, raw=False)
                landmarks = packet.get("landmarks", [])
                widget.update_landmarks(landmarks)
                last_frame = time.time()
        except BlockingIOError:
            pass

        if time.time() - last_frame > 5:
            widget.update()

        time.sleep(0.001)

    sock.close()


if __name__ == "__main__":
    main()
