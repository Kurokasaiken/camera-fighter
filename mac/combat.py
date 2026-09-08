"""Logica di combattimento, in unita' di torso: indipendente da pixel e da FPS."""

from dataclasses import dataclass, field


# Arti che colpiscono, e raggio della loro hitbox in unita' di torso.
STRIKERS = ["left_wrist", "right_wrist", "left_ankle", "right_ankle"]
HITBOX_RADIUS_U = 0.11

# Un colpo conta solo se l'arto si muove VERSO il nemico: sotto questa soglia
# (unita' di torso al secondo) e' una mano appoggiata, non un pugno. Essendo una
# velocita' di avvicinamento, il ritorno del braccio e' negativo e non colpisce.
MIN_STRIKE_SPEED = 2.0

# Tempo minimo fra due colpi dello stesso arto.
STRIKE_COOLDOWN = 0.35

DAMAGE = 8

# Quanto resta a terra il nemico prima di tornare in piedi con HP pieni.
RESPAWN_DELAY = 1.5


@dataclass
class Enemy:
    """Rettangolo in unita' di torso, relativo al centro del corpo del giocatore."""
    x: float = 0.85
    y: float = -1.0   # testa ~1u sopra l'anca: stessa linea di terra dell'avatar
    w: float = 0.6
    h: float = 2.8    # piedi a +1.8, allineati ai piedi dell'avatar
    hp: int = 100
    max_hp: int = 100

    def distance(self, px, py):
        """Distanza dal bordo del rettangolo, 0 se il punto e' dentro."""
        dx = max(self.x - px, 0.0, px - (self.x + self.w))
        dy = max(self.y - py, 0.0, py - (self.y + self.h))
        return (dx * dx + dy * dy) ** 0.5

    def contains(self, px, py, radius):
        nx = min(max(px, self.x), self.x + self.w)
        ny = min(max(py, self.y), self.y + self.h)
        return (px - nx) ** 2 + (py - ny) ** 2 <= radius ** 2


@dataclass
class HitEvent:
    joint: str
    x: float
    y: float
    speed: float
    damage: int


class CombatSystem:
    def __init__(self, enemy=None):
        self.enemy = enemy or Enemy()
        self._prev = {}
        self._last_hit = {}
        self.last_events = []
        self.ko_at = None

    def update(self, pose):
        """Consuma una AvatarPose, ritorna gli HitEvent di questo frame."""
        events = []
        if pose is None:
            self.last_events = events
            return events

        t = pose.timestamp

        if self.ko_at is not None:
            if t - self.ko_at >= RESPAWN_DELAY:
                self.reset()
            else:
                for name in STRIKERS:
                    self._approach_speed(name, getattr(pose, name), t)
                self.last_events = events
                return events

        for name in STRIKERS:
            joint = getattr(pose, name)
            speed = self._approach_speed(name, joint, t)
            if speed < MIN_STRIKE_SPEED:
                continue
            if t - self._last_hit.get(name, -1e9) < STRIKE_COOLDOWN:
                continue
            if not self.enemy.contains(joint.x, joint.y, HITBOX_RADIUS_U):
                continue

            self._last_hit[name] = t
            self.enemy.hp = max(0, self.enemy.hp - DAMAGE)
            if self.enemy.hp == 0:
                self.ko_at = t
            events.append(HitEvent(name, joint.x, joint.y, speed, DAMAGE))

        self.last_events = events
        return events

    def _approach_speed(self, name, joint, t):
        """Quanto in fretta l'arto si avvicina al nemico. Negativa quando si allontana.

        Misurata come riduzione della distanza dal bersaglio, non come velocita'
        assoluta: cosi' l'andata conta e il ritorno del braccio no.
        """
        d = self.enemy.distance(joint.x, joint.y)
        prev = self._prev.get(name)
        self._prev[name] = (d, t)
        if prev is None:
            return 0.0
        d_prev, t_prev = prev
        dt = t - t_prev
        if dt <= 0:
            return 0.0
        return (d_prev - d) / dt

    def reset(self):
        self.enemy.hp = self.enemy.max_hp
        self._last_hit.clear()
        self.ko_at = None
