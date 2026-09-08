from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget

from landmarks import LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW
from landmarks import LEFT_WRIST, RIGHT_WRIST, LEFT_HIP, RIGHT_HIP
from landmarks import LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE

WAIT = "WAIT"
READY = "READY"
COUNTDOWN = "COUNTDOWN"
RECORDING = "RECORDING"
REVIEW = "REVIEW"

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


class SkeletonWidget(QWidget):
    def __init__(self, width=960, height=540, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setWindowTitle("Camera Fighter — Receiver")
        self.width_f = width
        self.height_f = height

        self.latest_landmarks = []
        self.state = WAIT
        self.quality = {}
        self.fps = 0.0
        self.technique = ""
        self.debug_values = {}

    def _mirror_x(self, x: float) -> float:
        return (1 - x) * self.width_f

    def _y(self, y: float) -> float:
        return y * self.height_f

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 30))

        points = []
        for lm in self.latest_landmarks:
            x, y, c = lm
            points.append((self._mirror_x(x), self._y(y), c))

        # Linee scheletro
        pen = QPen()
        pen.setWidth(5)
        for a, b in SKELETON:
            if a < len(points) and b < len(points):
                pa, pb = points[a], points[b]
                if pa[2] > 0.3 and pb[2] > 0.3:
                    cmin = min(pa[2], pb[2])
                    if cmin > 0.7:
                        color = QColor(0, 255, 0)
                    elif cmin > 0.5:
                        color = QColor(255, 200, 0)
                    else:
                        color = QColor(255, 80, 80)
                    pen.setColor(color)
                    painter.setPen(pen)
                    painter.drawLine(pa[0], pa[1], pb[0], pb[1])

        # Punti
        for x, y, c in points:
            if c > 0.3:
                if c > 0.7:
                    color = QColor(0, 255, 0)
                elif c > 0.5:
                    color = QColor(255, 200, 0)
                else:
                    color = QColor(255, 80, 80)
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(int(x - 8), int(y - 8), 16, 16)

        # Testo
        painter.setPen(QColor(255, 255, 255))
        big_font = QFont("Helvetica", 48, QFont.Bold)
        painter.setFont(big_font)

        if self.state == WAIT:
            state_text = "POSIZIONATI"
        elif self.state == READY:
            state_text = "PRONTO"
        elif self.state == COUNTDOWN:
            state_text = "VAI"
        elif self.state == RECORDING:
            state_text = "REC"
        elif self.state == REVIEW:
            state_text = "REVIEW"
        else:
            state_text = self.state

        painter.drawText(int(self.width_f // 2 - 180), 80, state_text)

        # Evento riconosciuto
        if self.technique:
            painter.setPen(QColor(255, 80, 80))
            font = QFont("Helvetica", 24, QFont.Bold)
            painter.setFont(font)
            painter.drawText(int(self.width_f // 2 - 120), 140, self.technique)

        # Qualita
        q = self.quality or {}
        q_label = q.get("label", "---")
        q_score = q.get("score", 0.0)
        painter.setPen(QColor(200, 200, 200))
        font = QFont("Helvetica", 16)
        painter.setFont(font)
        painter.drawText(20, 30, f"Qualita: {q_label} ({q_score:.0%})")

        # FPS
        painter.drawText(int(self.width_f - 120), 30, f"FPS: {self.fps:.1f}")

        # Debug values
        y = 180
        for name, vals in self.debug_values.items():
            line = f"{name}: v={vals['v']:.2f} avg={vals['avg']:.2f} a={vals['a']:.2f}"
            painter.setPen(QColor(180, 220, 255))
            painter.drawText(20, y, line)
            y += 22

        # Istruzioni
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(20, int(self.height_f - 20), "R = start/stop  |  Q = esci")

        painter.end()


class Visualizer:
    def __init__(self, width: int = 960, height: int = 540):
        self.app = QApplication.instance() or QApplication([])
        self.widget = SkeletonWidget(width, height)
        self.widget.show()
        print("OK", flush=True)
        self.timer = QTimer()
        self.timer.timeout.connect(self._process)
        self.timer.start(16)  # ~60 FPS

    def _process(self):
        self.app.processEvents()

    def draw(self, landmarks: list, state: str = WAIT, countdown: int = 0,
             quality: dict = None, fps: float = 0.0, recording: bool = False,
             recorded: int = 0, technique: str = "", debug_values: dict = None):
        self.widget.latest_landmarks = landmarks
        self.widget.state = state
        self.widget.quality = quality or {}
        self.widget.fps = fps
        self.widget.technique = technique or ""
        self.widget.debug_values = debug_values or {}
        self.widget.update()
