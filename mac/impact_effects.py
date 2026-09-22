"""Vocabolario d'impatto per SUMI — hitstop, flash, scossa, schizzo, afterimage.

Classe standalone ImpactEffect gestisce lo stato degli effetti d'impatto.
Nessuna dipendenza da renderer o main_spike_visual — pura logica di timing e decadimento.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class InkDrop:
    """Una goccia d'inchiostro: (x, y, raggio, creation_time, decay_ms)."""
    x: float
    y: float
    r: float
    creation_time: float
    decay_ms: float

    def alpha_remaining(self, now: float) -> float:
        """Ritorna alpha 0.0-1.0 basato su decadimento esponenziale."""
        elapsed = (now - self.creation_time) * 1000.0
        if elapsed >= self.decay_ms:
            return 0.0
        return 1.0 - (elapsed / self.decay_ms)

    def is_alive(self, now: float) -> bool:
        """Vero se alpha > 0."""
        return self.alpha_remaining(now) > 0.0


@dataclass
class HitstopState:
    """Stato di un hitstop: durata, tempo inizio."""
    duration_ms: float
    start_time: float

    def is_active(self, now: float) -> bool:
        """Vero se ancora dentro la durata."""
        elapsed = (now - self.start_time) * 1000.0
        return elapsed < self.duration_ms

    def progress(self, now: float) -> float:
        """Ritorna 0.0-1.0: avanzamento di hitstop."""
        elapsed = (now - self.start_time) * 1000.0
        return min(1.0, elapsed / self.duration_ms)


@dataclass
class FlashState:
    """Stato di un lampo bianco: durata, intensità, tempo inizio."""
    duration_ms: float
    intensity: float  # 0.0-1.0
    start_time: float

    def is_active(self, now: float) -> bool:
        """Vero se ancora dentro la durata."""
        elapsed = (now - self.start_time) * 1000.0
        return elapsed < self.duration_ms

    def alpha(self, now: float) -> float:
        """Ritorna alpha 0.0-1.0 basato su durata."""
        elapsed = (now - self.start_time) * 1000.0
        progress = min(1.0, elapsed / self.duration_ms)
        return self.intensity * (1.0 - progress)  # fade out


@dataclass
class ShakeState:
    """Stato di una scossa: distanza, durata, tempo inizio."""
    distance_px: float
    duration_ms: float
    start_time: float

    def is_active(self, now: float) -> bool:
        """Vero se ancora dentro la durata."""
        elapsed = (now - self.start_time) * 1000.0
        return elapsed < self.duration_ms

    def offset(self, now: float) -> Tuple[float, float]:
        """Ritorna (dx, dy) oscillando fra ±distance."""
        import math
        elapsed = (now - self.start_time) * 1000.0
        progress = elapsed / self.duration_ms
        angle = progress * 8 * math.pi  # 4 oscillazioni complete
        magnitude = self.distance_px * (1.0 - progress)  # decay
        return (magnitude * math.sin(angle), magnitude * math.cos(angle))


class ImpactEffect:
    """Gestisce lo stato degli effetti d'impatto per SUMI vocabolario."""

    def __init__(self):
        self.hitstops: List[HitstopState] = []
        self.flashes: List[FlashState] = []
        self.shakes: List[ShakeState] = []
        self.ink_drops: List[InkDrop] = []
        self.afterimage_poses = deque(maxlen=20)  # ring buffer ~350ms a 17fps
        self.last_tick_time = time.time()

    def tick(self, now: float = None) -> None:
        """Aggiorna decadimento di tutti gli effetti. Chiama ogni frame."""
        if now is None:
            now = time.time()
        self.last_tick_time = now

        # Pulisci effetti morti
        self.hitstops = [h for h in self.hitstops if h.is_active(now)]
        self.flashes = [f for f in self.flashes if f.is_active(now)]
        self.shakes = [s for s in self.shakes if s.is_active(now)]
        self.ink_drops = [d for d in self.ink_drops if d.is_alive(now)]

    def hitstop(self, duration_ms: float, now: float = None) -> None:
        """Attiva un hitstop (congelamento) di durata_ms."""
        if now is None:
            now = time.time()
        self.hitstops.append(HitstopState(duration_ms, now))

    def flash_white(self, duration_ms: float, intensity: float = 1.0, now: float = None) -> None:
        """Attiva un lampo bianco di durata_ms e intensità (0.0-1.0)."""
        if now is None:
            now = time.time()
        self.flashes.append(FlashState(duration_ms, intensity, now))

    def screen_shake(self, distance_px: float, duration_ms: float, now: float = None) -> None:
        """Attiva una scossa dello schermo."""
        if now is None:
            now = time.time()
        self.shakes.append(ShakeState(distance_px, duration_ms, now))

    def ink_splash(self, x: float, y: float, count: int = 10, decay_ms: float = 180.0, now: float = None) -> None:
        """Crea gocce d'inchiostro a (x, y) con count gocce e decadimento decay_ms."""
        if now is None:
            now = time.time()
        import random
        for _ in range(count):
            r = random.uniform(2, 8)
            self.ink_drops.append(InkDrop(x, y, r, now, decay_ms))

    def afterimage_ring(self, poses: deque, alpha_list: List[float] = None) -> List[Tuple]:
        """Prepara afterimage: ritorna lista di (pose, alpha) per frame passati.
        poses: ring buffer di AvatarPose.
        alpha_list: list di alpha per ogni pose (default [0.55, 0.35, 0.18] per pose[-6,-4,-2]).
        """
        if alpha_list is None:
            alpha_list = [0.55, 0.35, 0.18]
        if len(poses) < 3:
            return []
        # Ritorna pose[-6/-4/-2] con alpha da alpha_list
        result = []
        indices = [-6, -4, -2]
        for i, alpha in zip(indices, alpha_list):
            if -i <= len(poses):
                result.append((poses[i], alpha))
        return result

    # Query state
    def is_hitstop_active(self, now: float = None) -> bool:
        """Vero se almeno uno hitstop è attivo."""
        if now is None:
            now = time.time()
        return any(h.is_active(now) for h in self.hitstops)

    def is_flash_active(self, now: float = None) -> float:
        """Ritorna alpha 0.0-1.0 massimo di flash attivi."""
        if now is None:
            now = time.time()
        if not self.flashes:
            return 0.0
        return max(f.alpha(now) for f in self.flashes)

    def shake_offset(self, now: float = None) -> Tuple[float, float]:
        """Ritorna (dx, dy) massima scossa attiva."""
        if now is None:
            now = time.time()
        if not self.shakes:
            return (0.0, 0.0)
        # Somma tutte le scosse (se molteplici)
        dx, dy = 0.0, 0.0
        for s in self.shakes:
            sdx, sdy = s.offset(now)
            dx += sdx
            dy += sdy
        return (dx, dy)

    def get_ink_drops(self, now: float = None) -> List[Tuple[float, float, float, float]]:
        """Ritorna lista di (x, y, r, alpha) per gocce d'inchiostro attive."""
        if now is None:
            now = time.time()
        return [(d.x, d.y, d.r, d.alpha_remaining(now)) for d in self.ink_drops if d.is_alive(now)]

    def get_afterimage(self, poses: deque, now: float = None) -> List[Tuple]:
        """Ritorna lista di (pose, alpha) per rendering afterimage."""
        if now is None:
            now = time.time()
        return self.afterimage_ring(poses)
