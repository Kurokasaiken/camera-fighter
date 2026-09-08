from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QWidget

from avatar_pose import AvatarPose
from combat import HITBOX_RADIUS_U


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


class SkeletonRenderer(QWidget):
    def __init__(self, width=1200, height=600, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setWindowTitle("Camera Fighter — Scheletro + Avatar")
        self.width_f = width
        self.height_f = height
        self.pose = None
        self.raw_landmarks = []
        self.fps = 0.0
        self.now = 0.0
        self.combat = None
        self.flash_until = 0.0
        self.hit_marks = []
        self.rig = None          # SpriteRig opzionale (tasto S = toggle)
        # Le coordinate avatar sono normalizzate sulla lunghezza del torso:
        # un corpo intero misura ~2.9 unita'. Con questo fattore occupa la
        # stessa altezza in pixel dello scheletro grezzo a sinistra.
        self.scale_px = min(width, height) * 0.13

    def _to_screen_raw(self, x, y, cx, cy, scale):
        """Landmark 0..1 → schermo, in una regione, stessa direzione dell'avatar."""
        return int(cx + (x - 0.5) * scale), int(cy + (y - 0.5) * scale)

    def _avatar_origin(self):
        mid = self.width_f // 2
        # stessa altezza dello scheletro a sinistra: centri allineati
        return mid + (self.width_f - mid) // 2, self.height_f // 2

    def _u_to_screen(self, ux, uy, cx, cy):
        return int(cx + ux * self.scale_px), int(cy + uy * self.scale_px)

    def _to_screen_avatar(self, p, cx, cy):
        return self._u_to_screen(p.x, p.y, cx, cy)

    def _draw_raw_skeleton(self, painter, cx, cy, scale):
        if not self.raw_landmarks or len(self.raw_landmarks) < 33:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(cx - 80, cy, "In attesa...")
            return

        # Colore = segmento x lato: stessa famiglia per osso, tonalita'
        # diversa SX/DX. Cosi' si vede sia il segmento sia lo swap di lato.
        SEG_L = {}
        SEG_R = {}
        def seg(li, ri, cl, cr):
            for i in li: SEG_L[i] = QColor(*cl)
            for i in ri: SEG_R[i] = QColor(*cr)
        seg([11], [12], (255, 255, 255), (200, 200, 255))   # spalle
        seg([13], [14], (255, 140, 60), (255, 60, 160))     # gomiti
        seg([15, 17, 19, 21], [16, 18, 20, 22],
            (255, 200, 80), (255, 100, 200))                # polsi/mani
        seg([23], [24], (80, 220, 255), (60, 160, 255))     # anche
        seg([25], [26], (120, 255, 120), (40, 200, 220))    # ginocchia
        seg([27, 29, 31], [28, 30, 32],
            (255, 255, 80), (180, 255, 120))                # caviglie/piedi
        SEG_COLORS = {**SEG_L, **SEG_R}
        # linee: colore del capo a valle (braccio=colore polso, ecc.)
        BONE_COLOR = {}
        for a, b in SKELETON:
            BONE_COLOR[(a, b)] = SEG_COLORS.get(b, QColor(0, 255, 120))

        for a, b in SKELETON:
            if a <= 10 or b <= 10:
                continue          # niente linee faccia: testa = solo pallino naso
            if a < len(self.raw_landmarks) and b < len(self.raw_landmarks):
                if self.raw_landmarks[a][2] > 0.3 and self.raw_landmarks[b][2] > 0.3:
                    painter.setPen(QPen(BONE_COLOR.get((a, b),
                                            QColor(0, 255, 120)), 4))
                    x1, y1 = self._to_screen_raw(self.raw_landmarks[a][0], self.raw_landmarks[a][1], cx, cy, scale)
                    x2, y2 = self._to_screen_raw(self.raw_landmarks[b][0], self.raw_landmarks[b][1], cx, cy, scale)
                    painter.drawLine(x1, y1, x2, y2)

        for i, lmi in enumerate(self.raw_landmarks):
            x, y, c = lmi[0], lmi[1], (lmi[2] if len(lmi) > 2 else 0.0)
            if c > 0.3:
                if i <= 10:
                    # testa: un solo punto (naso=0), le altre 10 facce di ML Kit
                    # creano rumore visivo inutile sullo scheletro
                    if i != 0:
                        continue
                    base = QColor(200, 200, 200)
                else:
                    base = SEG_COLORS.get(i, QColor(0, 255, 120))
                color = base if c > 0.5 else QColor(255, 80, 80)
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.NoPen)
                sx, sy = self._to_screen_raw(x, y, cx, cy, scale)
                painter.drawEllipse(sx - 5, sy - 5, 10, 10)
                # lettere identita' su gomiti e ginocchia
                if i in (13, 14, 25, 26):
                    painter.setPen(QColor(255, 255, 255))
                    painter.setFont(QFont("Helvetica", 10, QFont.Bold))
                    painter.drawText(sx - 3, sy + 4, "L" if i in (13, 25) else "R")

    def _draw_avatar(self, painter, cx, cy):
        if not self.pose:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(cx - 80, cy, "In attesa...")
            return

        points = {}
        for name, joint in self.pose.all_joints():
            points[name] = self._to_screen_avatar(joint, cx, cy)

        if self.rig is not None and self.rig.enabled:
            self.rig.draw(painter, points, self.scale_px)
        else:
            pairs = [
                ("left_shoulder", "right_shoulder"),
                ("left_shoulder", "left_elbow"),
                ("left_elbow", "left_wrist"),
                ("right_shoulder", "right_elbow"),
                ("right_elbow", "right_wrist"),
                ("left_shoulder", "left_hip"),
                ("right_shoulder", "right_hip"),
                ("left_hip", "right_hip"),
                ("left_hip", "left_knee"),
                ("left_knee", "left_ankle"),
                ("right_hip", "right_knee"),
                ("right_knee", "right_ankle"),
            ]
            pen = QPen(QColor(0, 255, 255))
            pen.setWidth(6)
            painter.setPen(pen)
            for a, b in pairs:
                if a in points and b in points:
                    painter.drawLine(points[a][0], points[a][1], points[b][0], points[b][1])

            for name, (x, y) in points.items():
                painter.setBrush(QBrush(QColor(0, 255, 255)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(x - 7, y - 7, 14, 14)

        # Hitbox
        r = int(self.scale_px * HITBOX_RADIUS_U)
        for name in ["left_wrist", "right_wrist", "left_ankle", "right_ankle"]:
            if name in points:
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                painter.setBrush(QBrush(QColor(255, 255, 0, 80)))
                x, y = points[name]
                painter.drawEllipse(x - r, y - r, r * 2, r * 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 10, 20))

        # Linea divisoria
        mid = self.width_f // 2
        painter.setPen(QPen(QColor(60, 60, 60), 2, Qt.DotLine))
        painter.drawLine(mid, 0, mid, self.height_f)

        # Titoli
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(20, 40, "SCHELETRO GREZZO")
        painter.drawText(mid + 20, 40, "AVATAR FILTRATO")

        # Sinistra: scheletro grezzo
        raw_cx = mid // 2
        raw_cy = self.height_f // 2
        raw_scale = min(self.width_f, self.height_f) * 0.5
        self._draw_raw_skeleton(painter, raw_cx, raw_cy, raw_scale)

        # Destra: avatar + nemico
        avatar_cx, avatar_cy = self._avatar_origin()

        if self.combat:
            e = self.combat.enemy
            ex, ey = self._u_to_screen(e.x, e.y, avatar_cx, avatar_cy)
            ex2, ey2 = self._u_to_screen(e.x + e.w, e.y + e.h, avatar_cx, avatar_cy)
            flashing = self.now < self.flash_until
            painter.setBrush(QBrush(QColor(255, 220, 220) if flashing else QColor(180, 60, 60)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(ex, ey, ex2 - ex, ey2 - ey, 10, 10)

            # Barra HP sopra il nemico
            frac = e.hp / e.max_hp if e.max_hp else 0.0
            painter.setBrush(QBrush(QColor(50, 50, 50)))
            painter.drawRect(ex, ey - 18, ex2 - ex, 8)
            painter.setBrush(QBrush(QColor(80, 220, 80)))
            painter.drawRect(ex, ey - 18, int((ex2 - ex) * frac), 8)

            if self.combat.ko_at is not None:
                painter.setPen(QColor(255, 200, 80))
                painter.setFont(QFont("Helvetica", 26, QFont.Bold))
                painter.drawText(ex - 10, ey - 30, "KO")

        # Linea di centro
        painter.setPen(QPen(QColor(80, 80, 80), 1, Qt.DotLine))
        painter.drawLine(avatar_cx, 0, avatar_cx, self.height_f)

        self._draw_avatar(painter, avatar_cx, avatar_cy)

        # Strike zone del nuovo motore (unita' torso, origine anca):
        # in coord avatar l'anca e' a y=+0.5 -> traslazione
        try:
            from pipeline import DEFAULT_HITBOX
            hx, hy, hw, hh = DEFAULT_HITBOX
            bx1, by1 = self._u_to_screen(hx, hy + 0.5, avatar_cx, avatar_cy)
            bx2, by2 = self._u_to_screen(hx + hw, hy + hh + 0.5,
                                         avatar_cx, avatar_cy)
            painter.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(255, 255, 0, 30)))
            painter.drawRect(min(bx1, bx2), min(by1, by2),
                             abs(bx2 - bx1), abs(by2 - by1))
        except Exception:
            pass

        # Segni di impatto
        for mx, my, expires in self.hit_marks:
            if self.now >= expires:
                continue
            sx, sy = self._u_to_screen(mx, my, avatar_cx, avatar_cy)
            painter.setPen(QPen(QColor(255, 240, 120), 3))
            painter.setBrush(Qt.NoBrush)
            r = int(self.scale_px * 0.25)
            painter.drawEllipse(sx - r, sy - r, r * 2, r * 2)

        # UI
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 14)
        painter.setFont(font)
        hp = self.combat.enemy.hp if self.combat else 0
        painter.drawText(20, self.height_f - 40, f"HP nemico: {hp}")
        painter.drawText(20, self.height_f - 20, f"FPS: {self.fps:.1f} | Landmarks: {len(self.raw_landmarks)}")

        # Diagnostica: lunghezza braccio dell'AVATAR (unita' torso avatar),
        # quella che decide il reach verso il nemico
        if self.pose:
            import math as _m
            out = []
            for s, e, tag in ((self.pose.left_shoulder, self.pose.left_elbow, "L"),
                              (self.pose.right_shoulder, self.pose.right_elbow, "R")):
                d = _m.hypot(e.x - s.x, e.y - s.y)
                out.append(f"{tag} {d:.2f}")
            painter.setPen(QColor(255, 230, 120))
            painter.setFont(QFont("Helvetica", 34, QFont.Bold))
            painter.drawText(20, 90, "    ".join(out))

        painter.end()

    def update_pose(self, pose: AvatarPose, raw_landmarks, fps: float, hits=()):
        self.pose = pose
        self.raw_landmarks = raw_landmarks
        self.fps = fps
        if pose:
            self.now = pose.timestamp

        for h in hits:
            self.flash_until = self.now + 0.12
            self.hit_marks.append((h.x, h.y, self.now + 0.25))
        self.hit_marks = [m for m in self.hit_marks if m[2] > self.now]

        self.update()
