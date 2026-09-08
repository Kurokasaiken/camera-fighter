"""Sprite rig — avatar pixel-art riggato sulle ossa (feel test).

Ogni parte e' un PNG modulare (assets/main_hero) ancorato a un osso:
  l'asse verticale dello sprite viene allineato alla direzione osso A->B,
  scalato sulla lunghezza dell'osso, pivot = giunto prossimale (A).
Rotazione via QPainter (trasformazione smooth: gli sprite sono gia' grandi,
il downscale smussa i bordi — trucco RotSprite).

Mappa parti (identificata dal contact sheet):
  0003 testa+capelli | 0012 hoodie torso | 0009 shorts bacino
  0006 braccio nudo  | 0017 avambraccio nudo | 0018 pugno guantato
  0010 gamba intera  | 0013 scarpa
Parti facciali (occhi/bocca/orecchio) non usate nel feel test.

Tasto S nel renderer = toggle rig on/off.
"""

from __future__ import annotations

import math
import os

from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtCore import Qt

ASSETS = os.path.join(os.path.dirname(__file__), "assets", "main_hero")


def _pm(name: str) -> QPixmap:
    return QPixmap(os.path.join(ASSETS, name))


class SpriteRig:
    """Disegna i pezzi sprite sopra l'AvatarPose (in pixel schermo)."""

    def __init__(self):
        self.pix = {
            "head": _pm("sprite_0003.png"),
            "torso": _pm("sprite_0012.png"),
            "pelvis": _pm("sprite_0009.png"),
            "arm": _pm("sprite_0006.png"),
            "forearm": _pm("sprite_0017.png"),
            "fist": _pm("sprite_0018.png"),
            "leg": _pm("sprite_0010.png"),
            "shoe": _pm("sprite_0013.png"),
        }
        self.enabled = True
        self.mirror = True   # lo sprite guarda a sx; il nemico e' a +x

    # ------------------------------------------------------------ helpers

    def _bone(self, points, a, b):
        if a not in points or b not in points:
            return None
        ax, ay = points[a]
        bx, by = points[b]
        return ax, ay, bx, by

    def _draw_bone(self, painter, pm, bone, cover=1.15, pivot_y=0.1,
                   width_hint=None):
        """Sprite con asse verticale -> direzione A->B; pivot vicino al top.
        Solo transform del painter: MAI pixmap.scaled() per frame (e' la
        causa del lag)."""
        ax, ay, bx, by = bone
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L < 2 or pm.isNull():
            return
        ang = math.degrees(math.atan2(dy, dx)) + 90.0  # img 'down' = +90
        scale = (L * cover) / pm.height()
        t = QTransform()
        t.translate(ax, ay)
        t.rotate(ang)
        if self.mirror:
            t.scale(-1, 1)
        t.scale(scale, scale)
        t.translate(-pm.width() / 2, -pm.height() * pivot_y)
        painter.setTransform(t)
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, pm)
        painter.resetTransform()

    # -------------------------------------------------------------- draw

    def _draw_fixed(self, painter, pm, cx, cy, target_h, pivot=0.5):
        """Sprite verticale fermo (testa, bacino): nessuna rotazione d'osso."""
        if pm.isNull():
            return
        scale = target_h / pm.height()
        t = QTransform()
        t.translate(cx, cy)
        if self.mirror:
            t.scale(-1, 1)
        t.scale(scale, scale)
        t.translate(-pm.width() / 2, -pm.height() * pivot)
        painter.setTransform(t)
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, pm)
        painter.resetTransform()

    def draw(self, painter, points, scale_px):
        """points: nome -> (x,y) pixel schermo (da renderer._to_screen_avatar)."""
        if not self.enabled:
            return

        hip_c = sho_c = None
        if "left_hip" in points and "right_hip" in points:
            hip_c = ((points["left_hip"][0] + points["right_hip"][0]) / 2,
                     (points["left_hip"][1] + points["right_hip"][1]) / 2)
        if "left_shoulder" in points and "right_shoulder" in points:
            sho_c = ((points["left_shoulder"][0] + points["right_shoulder"][0]) / 2,
                     (points["left_shoulder"][1] + points["right_shoulder"][1]) / 2)
        torso_h = math.hypot(sho_c[0]-hip_c[0], sho_c[1]-hip_c[1]) \
            if hip_c and sho_c else scale_px

        # ordine di disegno: gamba dietro (R), torso+pelvis, gamba avanti (L),
        # braccia, scarpe, testa
        leg_r = self._bone(points, "right_hip", "right_ankle")
        if leg_r:
            self._draw_bone(painter, self.pix["leg"], leg_r)

        if hip_c:
            self._draw_fixed(painter, self.pix["pelvis"],
                             hip_c[0], hip_c[1], torso_h * 0.45, pivot=0.3)
        if hip_c and sho_c:
            self._draw_bone(painter, self.pix["torso"],
                            (hip_c[0], hip_c[1], sho_c[0], sho_c[1]),
                            cover=1.25, pivot_y=0.0)

        leg_l = self._bone(points, "left_hip", "left_ankle")
        if leg_l:
            self._draw_bone(painter, self.pix["leg"], leg_l)

        for side in ("right", "left"):   # dietro prima, avanti dopo
            ua = self._bone(points, f"{side}_shoulder", f"{side}_elbow")
            fa = self._bone(points, f"{side}_elbow", f"{side}_wrist")
            if ua:
                self._draw_bone(painter, self.pix["arm"], ua)
            if fa:
                self._draw_bone(painter, self.pix["forearm"], fa)
                w = points.get(f"{side}_wrist")
                if w:
                    ex = w[0] + (w[0] - fa[0]) * 0.4
                    ey = w[1] + (w[1] - fa[1]) * 0.4
                    self._draw_bone(painter, self.pix["fist"],
                                    (w[0], w[1], ex, ey), cover=1.0)

        # scarpe: orizzontali, puntate in avanti (+x), alla caviglia
        for side in ("left", "right"):
            a = points.get(f"{side}_ankle")
            if a:
                self._draw_fixed(painter, self.pix["shoe"],
                                 a[0] + scale_px * 0.15, a[1],
                                 scale_px * 0.18, pivot=0.6)

        # testa: verticale sopra le spalle (non ruota con il collo)
        if sho_c:
            self._draw_fixed(painter, self.pix["head"],
                             sho_c[0], sho_c[1] - torso_h * 0.15,
                             torso_h * 0.65, pivot=0.85)
