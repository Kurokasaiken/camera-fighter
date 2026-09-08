"""Scheletro grezzo esattamente come arriva dalla camera."""

import argparse
import socket
import time

import msgpack

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget

SKELETON = [
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (27, 31),
    (24, 26), (26, 28), (28, 30), (28, 32),
]


class RawSkeletonWidget(QWidget):
    def __init__(self, width=960, height=540, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setWindowTitle("Camera Fighter — Scheletro Grezzo")
        self.width_f = width
        self.height_f = height
        self.landmarks = []
        self.fps = 0.0

    def _to_screen(self, x, y):
        # Mirror sullo schermo come nella visualizzazione precedente
        return int((1 - x) * self.width_f), int(y * self.height_f)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 10, 20))

        if self.landmarks and len(self.landmarks) >= 33:
            # Linee scheletro
            pen = QPen(QColor(0, 255, 120))
            pen.setWidth(5)
            painter.setPen(pen)
            for a, b in SKELETON:
                if a < len(self.landmarks) and b < len(self.landmarks):
                    if self.landmarks[a][2] > 0.3 and self.landmarks[b][2] > 0.3:
                        x1, y1 = self._to_screen(self.landmarks[a][0], self.landmarks[a][1])
                        x2, y2 = self._to_screen(self.landmarks[b][0], self.landmarks[b][1])
                        painter.drawLine(x1, y1, x2, y2)

            # Punti
            for i, (x, y, c) in enumerate(self.landmarks):
                if c > 0.3:
                    color = QColor(0, 255, 120) if c > 0.7 else QColor(255, 200, 0) if c > 0.5 else QColor(255, 80, 80)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.NoPen)
                    sx, sy = self._to_screen(x, y)
                    painter.drawEllipse(sx - 7, sy - 7, 14, 14)

            # Numeri landmark
            painter.setPen(QColor(200, 200, 200))
            font = QFont("Helvetica", 8)
            painter.setFont(font)
            for i in [0, 11, 12, 15, 16, 23, 24, 27, 28]:
                if i < len(self.landmarks) and self.landmarks[i][2] > 0.3:
                    sx, sy = self._to_screen(self.landmarks[i][0], self.landmarks[i][1])
                    painter.drawText(sx + 8, sy, str(i))
        else:
            painter.setPen(QColor(150, 150, 150))
            font = QFont("Helvetica", 24)
            painter.setFont(font)
            painter.drawText(self.width_f // 2 - 150, self.height_f // 2, "In attesa di landmark...")

        # UI
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 16)
        painter.setFont(font)
        painter.drawText(20, 30, f"Landmarks: {len(self.landmarks)}")
        painter.drawText(20, 55, f"FPS: {self.fps:.1f}")

        painter.end()

    def update_landmarks(self, landmarks):
        self.landmarks = landmarks
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
    widget = RawSkeletonWidget()
    widget.show()

    last_packet = 0.0
    running = True
    while running and widget.isVisible():
        app.processEvents()

        try:
            while True:
                data, _ = sock.recvfrom(65535)
                packet = msgpack.unpackb(data, raw=False)
                landmarks = packet.get("landmarks", [])

                now = time.time()
                dt = now - last_packet
                widget.fps = 1.0 / dt if dt > 0 else 0.0
                last_packet = now

                widget.update_landmarks(landmarks)

        except BlockingIOError:
            pass

        time.sleep(0.001)

    sock.close()


if __name__ == "__main__":
    main()
