"""Silhouette fighter — avatar a sagoma piena (stile LIMBO).

Corpo = capsule nere spesse + giunti tondi + testa. Proporzioni FISSE
anatomiche (l'osso decide la DIREZIONE, la lunghezza e' quella disegnata):
il rumore di tracking sparisce nel nero e il braccio non puo' diventare
enorme perche' la parte non viene stirata sull'osso — solo orientata.

Tasto S = toggle (con sprite_rig condiviso). Tasto V = silhouette/stick.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtCore import Qt

BLACK = QColor(0x1B, 0x1A, 0x19)    # corpo: nero sumi profondo, leggibile su carta (#EFE6D6-#D6C7AC)
BACK = QColor(18, 18, 26)           # lato "dietro" ancora piu' scuro (profondita')
EDGE = QColor(90, 90, 110)          # bordo sottile per staccare dal fondo
EYE = QColor(240, 240, 235)


class SilhouetteRig:
    """Disegna una silhouette piena sopra l'AvatarPose (pixel schermo)."""

    def __init__(self):
        self.enabled = False   # default OFF: si attiva con tasto S
        # spessori in frazione dell'altezza torso (proporzioni fisse)
        self.w_torso = 0.42
        self.w_upper = 0.16     # braccio
        self.w_fore = 0.14      # avambraccio
        self.w_thigh = 0.20     # coscia
        self.w_shin = 0.16      # stinco
        self.head_r = 0.34      # raggio testa (in unita' torso)
        self.joint_r = 0.10     # raggio giunti

    # ------------------------------------------------------------ helpers

    def _cap(self, painter, ax, ay, bx, by, w):
        """Capsula nera A->B con larghezza w (px)."""
        pen = QPen(BLACK, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(ax, ay, bx, by)

    def _dot(self, painter, x, y, r, color=None):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color or BLACK))
        painter.drawEllipse(x - r, y - r, 2 * r, 2 * r)

    # -------------------------------------------------------------- draw

    def draw(self, painter, points, scale_px):
        if not self.enabled:
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

        # ---- cinematica proporzionale -----------------------------------
        # L'avatar NON copia le coordinate assolute: copia la DIREZIONE di
        # ogni osso e applica lunghezze anatomiche fisse (delta), tutte
        # proporzionali al torso e alla larghezza delle spalle.
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        dx, dy = sho_c[0] - hip_c[0], sho_c[1] - hip_c[1]
        L = math.hypot(dx, dy) or 1
        px, py = -dy / L, dx / L          # perpendicolare alla spina
        sh_w = torso * 0.30               # meta' larghezza spalle

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

        # estremita' spalle: le braccia attaccano dove le spalle finiscono
        LEN = {"upper": 0.50, "fore": 0.50, "thigh": 0.85, "shin": 0.85}
        prop = {}   # side -> dict di punti proporzionali
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

        # ---- disegno: gamba dietro -> torso -> gamba avanti -> braccia ---
        for side, shade in (("right", BACK), ("left", BLACK)):
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

        # torso trapezio: spalle larghe -> vita stretta
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
        _torso(4, EDGE)
        _torso(0, BLACK)
        for side in ("left", "right"):
            if side in prop:
                self._dot(painter, prop[side]["sho"][0], prop[side]["sho"][1],
                          torso * 0.16, BLACK if side == "left" else BACK)

        # braccia dalle estremita' spalle, lunghezze fisse
        for side, shade in (("right", BACK), ("left", BLACK)):
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
            self._dot(painter, wr[0], wr[1], R, shade)   # pugno

        # spalle: giunto rotondo al centro
        self._dot(painter, sho_c[0], sho_c[1], R * 1.2)

        # testa: sfera sopra le spalle + occhio
        if g("nose"):
            nx, ny = g("nose")
            hx = sho_c[0] + (nx - sho_c[0]) * 0.8
            hy = sho_c[1] + (ny - sho_c[1]) * 0.8 - torso * 0.30
            r = self.head_r * torso

            # collo: linea fra centro spalle e base testa
            neck_base = sho_c
            neck_top = (hx, hy + r * 0.4)
            pen = QPen(self.BLACK, max(2, int(torso * 0.08)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(neck_base[0]), int(neck_base[1]),
                            int(neck_top[0]), int(neck_top[1]))

            self._dot(painter, hx, hy, r + 3, EDGE)
            self._dot(painter, hx, hy, r)
            self._dot(painter, hx + r * 0.35, hy - r * 0.1, r * 0.14, EYE)
