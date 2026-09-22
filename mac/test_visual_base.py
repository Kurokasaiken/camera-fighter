"""Test decisivo art direction: BASE vs SUMI vs LASTRA.

Renderizza 3 versioni della stessa posa per falsificare SUMI vs LASTRA.
Non modifica renderer.py o silhouette.py — usa varianti standalone.
Output: 3 PNG contact sheet 8-frame ognuno.
"""

import os
import sys
import math
import numpy as np
import msgpack
from collections import deque

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QBrush, QFont,
                           QLinearGradient, QRadialGradient, QPolygonF, QTransform)
from PySide6.QtCore import Qt, QPointF

from pose_mapper import LandmarkToAvatarMapper
from avatar_pose import AvatarPose
from combat import CombatSystem

# ============================================================================
# SILHOUETTE VARIANTS
# ============================================================================

class SilhouetteRigTest:
    """Versione testabile di SilhouetteRig con parametri variabili."""

    def __init__(self, black_color=None, with_neck=True):
        self.BLACK = black_color or QColor(30, 30, 40)
        self.BACK = QColor(18, 18, 26)
        self.EDGE = QColor(90, 90, 110)
        self.EYE = QColor(240, 240, 235)
        self.with_neck = with_neck

        self.w_torso = 0.42
        self.w_upper = 0.16
        self.w_fore = 0.14
        self.w_thigh = 0.20
        self.w_shin = 0.16
        self.head_r = 0.34
        self.joint_r = 0.10

    def _cap(self, painter, ax, ay, bx, by, w):
        pen = QPen(self.BLACK, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(ax, ay, bx, by)

    def _dot(self, painter, x, y, r, color=None):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color or self.BLACK))
        painter.drawEllipse(x - r, y - r, 2 * r, 2 * r)

    def draw(self, painter, points, scale_px):
        """Same as original silhouette.py but with configurable colors."""
        if not points:
            return

        g = lambda n: points.get(n)
        hip_c = sho_c = None
        if g("left_hip") and g("right_hip"):
            hip_c = ((g("left_hip")[0] + g("right_hip")[0]) / 2,
                     (g("left_hip")[1] + g("right_hip")[1]) / 2)
        if g("left_shoulder") and g("right_shoulder"):
            sho_c = ((g("left_shoulder")[0] + g("right_shoulder")[0]) / 2,
                     (g("left_shoulder")[1] + g("right_shoulder")[1]) / 2)
        if not hip_c or not sho_c:
            return

        torso = math.hypot(sho_c[0] - hip_c[0], sho_c[1] - hip_c[1]) or scale_px
        w = lambda f: max(4, int(torso * f))
        R = self.joint_r * torso

        # Rig cinematica proporzionale (identico all'originale)
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF

        dx, dy = sho_c[0] - hip_c[0], sho_c[1] - hip_c[1]
        L = math.hypot(dx, dy) or 1
        px, py = -dy / L, dx / L
        sh_w = torso * 0.30

        def _dir(a, b):
            ddx, ddy = b[0]-a[0], b[1]-a[1]
            l = math.hypot(ddx, ddy) or 1.0
            return ddx/l, ddy/l

        def _chain(anchor, mid, end, l1, l2):
            m = (anchor[0], anchor[1])
            if mid:
                ux, uy = _dir(anchor, mid)
                m = (anchor[0]+ux*l1, anchor[1]+uy*l1)
            e = (m[0], m[1]+l2)
            if mid and end:
                ux, uy = _dir(mid, end)
                e = (m[0]+ux*l2, m[1]+uy*l2)
            return m, e

        LEN = {"upper": 0.50, "fore": 0.50, "thigh": 0.85, "shin": 0.85}
        prop = {}
        for side in ("left", "right"):
            spt = g(f"{side}_shoulder")
            sign = 1.0
            if spt:
                off = (spt[0]-sho_c[0])*px + (spt[1]-sho_c[1])*py
                sign = 1.0 if off >= 0 else -1.0
            elif side == "right":
                sign = -1.0
            sho = (sho_c[0] + px*sh_w*sign, sho_c[1] + py*sh_w*sign)
            hip = g(f"{side}_hip") or hip_c
            elb, wri = _chain(sho, g(f"{side}_elbow"), g(f"{side}_wrist"),
                              LEN["upper"]*torso, LEN["fore"]*torso)
            knee, ank = _chain(hip, g(f"{side}_knee"), g(f"{side}_ankle"),
                               LEN["thigh"]*torso, LEN["shin"]*torso)
            prop[side] = {"sho": sho, "elb": elb, "wri": wri,
                          "hip": hip, "knee": knee, "ank": ank}

        # Disegno gambe dietro
        for side, shade in (("right", self.BACK), ("left", self.BLACK)):
            p = prop.get(side)
            if not p:
                continue
            h, k, a = p["hip"], p["knee"], p["ank"]
            pen = QPen(shade, w(self.w_thigh))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(h[0]), int(h[1]), int(k[0]), int(k[1]))
            pen.setWidth(w(self.w_shin))
            painter.setPen(pen)
            painter.drawLine(int(k[0]), int(k[1]), int(a[0]), int(a[1]))
            self._dot(painter, k[0], k[1], R * 0.8, shade)
            painter.drawLine(int(a[0]), int(a[1]),
                             int(a[0] + torso * 0.22), int(a[1]))

        # Torso
        ws = torso * 0.55
        ww = torso * 0.30
        def _torso(off, col):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(col))
            poly = QPolygonF([
                QPointF(sho_c[0] + px * (ws + off), sho_c[1] + py * (ws + off)),
                QPointF(sho_c[0] - px * (ws + off), sho_c[1] - py * (ws + off)),
                QPointF(hip_c[0] - px * (ww + off), hip_c[1] - py * (ww + off)),
                QPointF(hip_c[0] + px * (ww + off), hip_c[1] + py * (ww + off)),
            ])
            painter.drawPolygon(poly)
        _torso(4, self.EDGE)
        _torso(0, self.BLACK)
        for side in ("left", "right"):
            if side in prop:
                self._dot(painter, prop[side]["sho"][0], prop[side]["sho"][1],
                          torso * 0.16, self.BLACK if side == "left" else self.BACK)

        # Braccia
        for side, shade in (("right", self.BACK), ("left", self.BLACK)):
            p = prop.get(side)
            if not p:
                continue
            s, e, wr = p["sho"], p["elb"], p["wri"]
            pen = QPen(shade, w(self.w_upper))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(s[0]), int(s[1]), int(e[0]), int(e[1]))
            pen.setWidth(w(self.w_fore))
            painter.setPen(pen)
            painter.drawLine(int(e[0]), int(e[1]), int(wr[0]), int(wr[1]))
            self._dot(painter, e[0], e[1], R * 0.8, shade)
            self._dot(painter, wr[0], wr[1], R, shade)

        # Spalle giunto
        self._dot(painter, sho_c[0], sho_c[1], R * 1.2)

        # TESTA + COLLO (NUOVO)
        if g("nose"):
            nx, ny = g("nose")
            hx = sho_c[0] + (nx - sho_c[0]) * 0.8
            hy = sho_c[1] + (ny - sho_c[1]) * 0.8 - torso * 0.30
            r = self.head_r * torso

            if self.with_neck:
                # Collo: linea dal centro spalle al base della testa
                neck_base = (sho_c[0], sho_c[1])
                neck_top = (hx, hy + r * 0.4)  # Base testa, non centro
                pen = QPen(self.BLACK, max(2, int(torso * 0.08)))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(int(neck_base[0]), int(neck_base[1]),
                                int(neck_top[0]), int(neck_top[1]))

            self._dot(painter, hx, hy, r + 3, self.EDGE)
            self._dot(painter, hx, hy, r)
            self._dot(painter, hx + r * 0.35, hy - r * 0.1, r * 0.14, self.EYE)


# ============================================================================
# TEST HARNESS
# ============================================================================

def make_grana(seed=7, size=256):
    """Generate paper texture tile."""
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 256, (size, size), dtype=np.uint8)
    img = QImage(data.data, size, size, size, QImage.Format_Grayscale8)
    return QImage(img)  # copy


def render_variant(poses, variant_name, W=1000, H=600):
    """Render one contact sheet variant."""
    app = QApplication.instance() or QApplication([])

    if variant_name == "BASE":
        scale_px = 155
        BLACK = QColor(70, 70, 90)
        bg_color = QColor(10, 10, 20)
        nemico_color = QColor(0x8B, 0x2D, 0x2D)
        text_color = QColor(0xCC, 0xCC, 0xCC)
        hp_color = QColor(0x64, 0xC8, 0x64)
        with_neck = True
        with_background = False

    elif variant_name == "SUMI":
        scale_px = 155
        BLACK = QColor(0x1B, 0x1A, 0x19)
        bg_color = None  # Will use gradient
        nemico_color = QColor(0xB2, 0x3A, 0x2E)
        text_color = QColor(0xCC, 0xCC, 0xCC)
        hp_color = QColor(0x64, 0xC8, 0x64)
        with_neck = True
        with_background = True
        grana = make_grana(seed=7)

    elif variant_name == "LASTRA":
        scale_px = 155
        BLACK = QColor(0x00, 0xEE, 0xFF)  # Cyan
        bg_color = QColor(10, 10, 20)
        nemico_color = QColor(0x8B, 0x2D, 0x2D)
        text_color = QColor(0xCC, 0xCC, 0xCC)
        hp_color = QColor(0x64, 0xC8, 0x64)
        with_neck = True
        with_background = False

    GROUND_Y = int(H * 0.80)

    sheet = QImage(W * 4, H * 2, QImage.Format_RGB32)
    sheet.fill(QColor(10, 10, 20))

    rig = SilhouetteRigTest(black_color=BLACK, with_neck=with_neck)

    for idx, pose in enumerate(poses):
        if idx >= 8:
            break
        row, col = idx // 4, idx % 4

        # Single frame canvas
        frame = QImage(W, H, QImage.Format_RGB32)
        p = QPainter(frame)
        p.setRenderHint(QPainter.Antialiasing)

        # Background
        if variant_name == "SUMI":
            # Gradient carta
            g = QLinearGradient(0, 0, 0, GROUND_Y)
            g.setColorAt(0.0, QColor(0xEF, 0xE6, 0xD6))
            g.setColorAt(1.0, QColor(0xD6, 0xC7, 0xAC))
            p.fillRect(0, 0, W, GROUND_Y, QBrush(g))
            # Grana
            p.setCompositionMode(QPainter.CompositionMode_Multiply)
            p.setOpacity(0.06)
            p.drawImage(0, 0, grana.scaledToWidth(W))
            p.setOpacity(1.0)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            # Cielo sotto
            p.fillRect(0, GROUND_Y, W, H - GROUND_Y, QBrush(QColor(30, 20, 20)))
        else:
            frame.fill(bg_color)

        # Terra + ombra
        p.setPen(QPen(QColor(0x8B, 0x6F, 0x47), 5))
        p.drawLine(0, GROUND_Y, W, GROUND_Y)

        # Ombra ellittica sotto piedi
        if pose:
            cx = W // 2
            g = QRadialGradient(cx, GROUND_Y, int(scale_px * 0.75))
            g.setColorAt(0.0, QColor(0, 0, 0, 130))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(cx - int(scale_px * 0.75), GROUND_Y - int(scale_px * 0.15),
                         int(scale_px * 1.5), int(scale_px * 0.3))

            # Avatar
            points = {}
            for name, joint in pose.all_joints():
                points[name] = (int(cx + joint.x * scale_px),
                               int(GROUND_Y + joint.y * scale_px))

            rig.draw(p, points, scale_px)

            # Nemico semplice
            enemy_x = int(W * 0.68)
            enemy_y = int(GROUND_Y - scale_px * 1.8)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(nemico_color))
            p.drawRect(enemy_x, enemy_y, int(scale_px * 0.5), int(scale_px * 2.8))

            # HP bar (verde morbido)
            hp_bar_w = int(scale_px * 0.5)
            p.fillRect(enemy_x, enemy_y - 12, hp_bar_w, 6, QBrush(QColor(50, 50, 50)))
            p.fillRect(enemy_x, enemy_y - 12, int(hp_bar_w * 0.75), 6, QBrush(hp_color))

        p.end()

        # Paste into sheet
        sheet_p = QPainter(sheet)
        sheet_p.drawImage(col * W, row * H, frame)
        sheet_p.end()

    return sheet


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    entries = msgpack.unpackb(open("visual_live.trace", "rb").read(), raw=False)

    # Pick 8 frames spread across the trace
    picks = [400, 1500, 2600, 3400, 4200, 5600, 6800, 8000]

    # Render poses
    mapper = LandmarkToAvatarMapper()
    poses = []

    for frame_start in picks:
        t = 0.0
        pose = None
        for e in entries[frame_start:frame_start+40]:
            lms = e["payload"].get("landmarks", [])
            if not lms:
                continue
            t += 1/17.0
            pose = mapper.map(lms, t)
        poses.append(pose)

    print(f"[test] Loaded {len(poses)} poses")

    # Render 3 variants
    for variant in ["BASE", "SUMI", "LASTRA"]:
        sheet = render_variant(poses, variant)
        out = f"test_visual_{variant.lower()}.png"
        sheet.save(out)
        print(f"[test] Saved {out}")

    print("[test] Done. Compare test_visual_*.png side-by-side.")
