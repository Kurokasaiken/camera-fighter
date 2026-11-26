"""fight_kernel.py — kernel di combattimento semantico MUGEN (PLAN-050+).

Porting *semantico* dal MUGEN 1.1 ricostruito (vendor/mugen-unleashed nel
repo fighting-style — decompilazione C di mugen.exe, differential-tested) e
da Ikemen GO usato come oracolo strumentabile. NON un port di codice: le
strutture portano identiche, le costanti sono riscalate per la camera
(latenza landmark ~50-100ms contro input istantaneo a 60Hz — vedi
audit/ikemen-notes.md in fighting-style).

Cosa portiamo da MUGEN:
- stati a tempo (startup/active/recovery) invece di hit continuo
- clsn1 (attacco) vivo SOLO nella finestra attiva, clsn2 (corpo) sempre
- serial dedup: un'istanza di mossa = max 1 hit per bersaglio
  (playerstate.c: tgt->hit_ids[att->index] == hd->serial -> return 0)
- hitstop: entrambi congelati N tick sul connect (char.c:203
  hitpause_time>0 -> cmd_state.frozen=1)
- hitstun/blockstun: la vittima entra in stato, non perde solo hp
- guard: parata tenuta + attacco in range -> blockstun + danno ridotto
  (char.c:268-340: movetype==IDLE && ctrl && in_guard_dist -> st120)
- tick deterministico a 60Hz: il kernel accumula dt e steppa tick fissi
  (stesso modello del lab fighting-style, replayable)

Stati Fighter: IDLE ATTACK HITSTUN BLOCKSTUN DOWN GETUP KO.
La mossa e' una MoveDef: chi colpisce (limb), quando (startup/active/
recovery in tick), con quali proprieta' (danno, hitstop, hitstun, knockback).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

TICK = 1.0 / 60.0


class St(IntEnum):
    IDLE = 0
    ATTACK = 1
    HITSTUN = 2
    BLOCKSTUN = 3
    DOWN = 4
    GETUP = 5
    KO = 6


class Ph(IntEnum):
    STARTUP = 0
    ACTIVE = 1
    RECOVERY = 2


@dataclass(frozen=True)
class MoveDef:
    """L'"HitDef" di una mossa. Tempi in tick 60Hz, riscalati per camera.

    MUGEN jab ~ (startup 3-5, active 2-4, recovery 8-14): sotto camera la
    startup vera e' ~100-200ms per latenza+classificazione, quindi le
    finestre sono ~2x rispetto al canone. Le PROPRIETA' (pausetime, stun,
    knockback) restano nella scala MUGEN — e' quella che da' il feel.
    """
    name: str
    limb: str              # joint attaccante (hitbox su quel punto)
    startup: int           # tick prima dei frame attivi
    active: int            # tick in cui clsn1 e' vivo
    recovery: int          # tick dopo la finestra (non si puo' agire)
    damage: int
    guard_damage: int      # MUGEN guarddamage: chip damage su parata
    hitstop: int           # tick di freeze su entrambi (MUGEN pausetime)
    hitstun: int           # tick di stun della vittima
    blockstun: int         # tick di stun su parata riuscita
    kbx: float             # knockback orizzontale (u torso/tick)
    kby: float             # knockback verticale (0 = niente juggle/lancio)
    reach: float           # estensione max del clsn1 (u torso)
    fall: bool = False     # MUGEN fall=1: la vittima va in DOWN


# Tabella mosse — valori di partenza, da calibrare su landmark reali.
MOVES: dict[str, MoveDef] = {
    # jab: corto, veloce, poco danno — punch_left (braccio guida)
    "punch_left": MoveDef(
        "punch_left", "left_wrist",
        startup=7, active=6, recovery=11,
        damage=5, guard_damage=1,
        hitstop=6, hitstun=14, blockstun=9,
        kbx=0.015, kby=0.0, reach=0.55,
    ),
    # cross/diretto: il pugno forte — punch_right
    "punch_right": MoveDef(
        "punch_right", "right_wrist",
        startup=11, active=7, recovery=16,
        damage=8, guard_damage=1,
        hitstop=8, hitstun=18, blockstun=12,
        kbx=0.030, kby=0.0, reach=0.70,
    ),
    # kick: lungo startup, portata e danno maggiori
    "kick_right": MoveDef(
        "kick_right", "right_ankle",
        startup=16, active=8, recovery=22,
        damage=12, guard_damage=2,
        hitstop=10, hitstun=24, blockstun=15,
        kbx=0.045, kby=0.02, reach=0.95, fall=True,
    ),
    "kick_left": MoveDef(
        "kick_left", "left_ankle",
        startup=14, active=7, recovery=20,
        damage=10, guard_damage=2,
        hitstop=9, hitstun=22, blockstun=14,
        kbx=0.040, kby=0.015, reach=0.85,
    ),
    # Mosse del nemico AI (specchiate: limb = punto di contatto logico)
    "enemy_jab": MoveDef(
        "enemy_jab", "enemy_fist",
        startup=12, active=6, recovery=14,
        damage=4, guard_damage=1,
        hitstop=6, hitstun=13, blockstun=9,
        kbx=-0.015, kby=0.0, reach=0.55,
    ),
    "enemy_hook": MoveDef(
        "enemy_hook", "enemy_fist",
        startup=18, active=7, recovery=20,
        damage=9, guard_damage=2,
        hitstop=9, hitstun=20, blockstun=13,
        kbx=-0.035, kby=0.0, reach=0.65,
    ),
}


@dataclass
class Ev:
    """Evento emesso dal kernel — renderer/impact_effects li consumano."""
    tick: int
    type: str            # hit|block|ko|down|getup|whiff_recover|state
    attacker: str        # "p" | "e"
    move: str = ""
    damage: int = 0
    x: float = 0.0       # punto di impatto (u torso)
    y: float = 0.0
    hitstop: int = 0
    combo: int = 0       # hitcount MUGEN-style: colpi in hitstun consecutivi
    victim_hp: int = 0


@dataclass
class Fighter:
    """Stato di un combattente. mirror di MugenChar: stateno/statetime,
    hitpausetime, hitcount, serial dedup."""
    side: str              # "p" player | "e" enemy
    hp: int = 100
    max_hp: int = 100
    x: float = 0.0         # posizione orizzontale (u torso, player-centric)
    y: float = 0.0         # altezza da terra della hurtbox (u torso)
    facing: int = 1        # +1 attacca verso +x
    state: St = St.IDLE
    statetime: int = 0
    move: MoveDef | None = None
    phase: Ph = Ph.STARTUP
    hitstop: int = 0
    attack_serial: int = 0   # serial dell'attacco corrente (dedup hitonce)
    hit_ids: set = field(default_factory=set)  # serial gia' connessi (dedup)
    stun_until: int = 0
    vel_x: float = 0.0
    vel_y: float = 0.0
    blocking: bool = False  # posa parata tenuta (dal classifier)
    dodging: bool = False   # schivata: hurtbox ridotta per N tick
    dodge_until: int = 0

    @property
    def alive(self):
        return self.hp > 0

    @property
    def can_act(self):
        # MUGEN ctrl: agisci solo da IDLE
        return self.state == St.IDLE and self.hitstop == 0 and self.alive


@dataclass
class CapsuleBox:
    """clsn come capsula orizzontale+verticale semplificata a box."""
    x: float
    y: float
    w: float
    h: float

    def overlaps(self, o: "CapsuleBox") -> bool:
        return (self.x < o.x + o.w and self.x + self.w > o.x and
                self.y < o.y + o.h and self.y + self.h > o.y)


# Hurt box del corpo (clsn2): torace+testa. In u torso, y negativo = alto.
PLAYER_HURT = CapsuleBox(-0.28, -1.55, 0.56, 1.35)   # davanti alla camera
ENEMY_HURT_W = 0.6
ENEMY_HURT_H = 2.4

DOWN_TIME = 90       # tick a terra (MUGEN liedown.time ~60+)
GETUP_TIME = 25
GUARD_RANGE = 1.05   # distanza entro cui la parata vale (inguarddist)
ENEMY_WALK = 0.006   # u/tick — il nemico chiude la distanza
ENEMY_RANGE = 0.75   # distanza a cui il nemico decide di attaccare
ENEMY_DECIDE = 45    # tick medi fra decisioni AI


class FightKernel:
    """Due Fighter + risoluzione hit a tick fissi.

    Uso:
        k = FightKernel()
        evs = k.update(dt, pose, actions)
    - dt: secondi reali dall'ultimo frame (accumulati in tick fissi 60Hz)
    - pose: oggetto con attributi left_wrist/right_wrist/left_ankle/
      right_ankle (+ .x/.y) e idealmente nose/left_hip per la hurtbox —
      None accettato (kernel gira comunque: utile per replay/test)
    - actions: set di nomi mossa iniziati QUESTO frame
      {"punch_left","kick_right",...} piu' flag "blocking"/"dodging"
      oppure dict {"moves": set, "blocking": bool, "dodging": bool}
    Ritorna lista di Ev di questo step (vuota se nessun tick e' maturato).
    """

    def __init__(self, enemy_x: float = 0.85, seed: int = 1,
                 enemy_ai: bool = True):
        self.p = Fighter("p", x=0.0, facing=1)
        self.e = Fighter("e", x=enemy_x, facing=-1)
        self.enemy_ai = enemy_ai   # False = nemico passivo (test/replay)
        self.tick = 0
        self._acc = 0.0
        self._serial = 0       # serial attack id (dedup hitonce)
        self._rng = seed       # xorshift — AI nemico deterministica
        self._ai_next = ENEMY_DECIDE
        self._combo = 0
        self._last_pose = None

    # --- RNG deterministico (stesso ruolo di sys.rand: replayable) ---
    def _rand(self) -> int:
        self._rng ^= (self._rng << 13) & 0xFFFFFFFF
        self._rng ^= self._rng >> 17
        self._rng ^= (self._rng << 5) & 0xFFFFFFFF
        self._rng &= 0xFFFFFFFF
        return self._rng

    # --- API principale -------------------------------------------------
    def update(self, dt: float, pose=None, actions=None):
        evs = []
        self._acc += dt
        # cap: mai piu' di 4 tick per frame (anti-spiral, come il lab)
        steps = min(4, int(self._acc / TICK))
        self._acc -= steps * TICK
        for _ in range(steps):
            evs.extend(self._step(pose, actions))
            actions = None  # gli action-start valgono solo il primo tick
        if pose is not None:
            self._last_pose = pose
        return evs

    # --- un tick di simulazione -----------------------------------------
    def _step(self, pose, actions):
        evs = []
        self.tick += 1
        p, e = self.p, self.e

        # 0) hitstop: MUGEN congela i due lati, non fa avanzare gli stati
        #    (char.c:203: hitpause_time>0 -> cmd_state.frozen=1)
        if p.hitstop > 0 or e.hitstop > 0:
            if p.hitstop > 0: p.hitstop -= 1
            if e.hitstop > 0: e.hitstop -= 1
            self._knockback(e, evs)
            return evs

        # 1) input player: pose -> flag parata/schivata + action start
        if actions:
            if isinstance(actions, dict):
                moves = actions.get("moves", set())
                p.blocking = bool(actions.get("blocking"))
                dodging = bool(actions.get("dodging"))
            else:
                moves = set(actions)
                p.blocking = "block" in moves
                dodging = "dodge" in moves
                moves -= {"block", "dodge"}
            if dodging and p.can_act:
                p.dodging = True
                p.dodge_until = self.tick + 18   # ~300ms di hurtbox ridotta
            for mv in moves:
                md = MOVES.get(mv)
                if md and p.can_act:
                    self._start_attack(p, md)
                    break   # una mossa per tick

        # 2) AI nemico: idle + in range + decisione -> jab/hook
        self._ai_step(evs)

        # 3) avanzamento stati (statetime)
        self._advance(p, evs)
        self._advance(e, evs)

        # 4) risoluzione hit: clsn1 attivi vs clsn2 corpo
        self._resolve_hit(p, e, evs)
        self._resolve_hit(e, p, evs)

        # 5) fisica knockback/fall + chiusura distanza del nemico
        self._knockback(p, evs)
        self._knockback(e, evs)
        self._enemy_spacing(evs)
        return evs

    # --- attacco ---------------------------------------------------------
    def _start_attack(self, f: Fighter, md: MoveDef):
        f.state = St.ATTACK
        f.statetime = 0
        f.move = md
        f.phase = Ph.STARTUP
        self._serial += 1
        f.attack_serial = self._serial

    def _advance(self, f: Fighter, evs):
        f.statetime += 1
        if f.state == St.ATTACK and f.move:
            md = f.move
            if f.phase == Ph.STARTUP and f.statetime >= md.startup:
                f.phase = Ph.ACTIVE
                f.statetime = 0
            elif f.phase == Ph.ACTIVE and f.statetime >= md.active:
                f.phase = Ph.RECOVERY
                f.statetime = 0
            elif f.phase == Ph.RECOVERY and f.statetime >= md.recovery:
                f.state = St.IDLE
                f.statetime = 0
                f.move = None
        elif f.state in (St.HITSTUN, St.BLOCKSTUN):
            if self.tick >= f.stun_until:
                f.state = St.IDLE
                f.statetime = 0
        elif f.state == St.DOWN:
            if f.statetime >= DOWN_TIME:
                f.state = St.GETUP
                f.statetime = 0
                evs.append(Ev(self.tick, "getup", f.side, victim_hp=f.hp))
        elif f.state == St.GETUP:
            if f.statetime >= GETUP_TIME:
                f.state = St.IDLE
                f.statetime = 0
        if f.dodging and self.tick > f.dodge_until:
            f.dodging = False

    # --- clsn -------------------------------------------------------------
    def _attack_box(self, f: Fighter, pose) -> CapsuleBox | None:
        """clsn1: vivo solo nella fase ACTIVE. Estensione interpolata
        startup->reach nella finestra attiva (l'arto "arriva")."""
        if f.state != St.ATTACK or f.phase != Ph.ACTIVE or not f.move:
            return None
        md = f.move
        prog = min(1.0, f.statetime / max(1, md.active))
        ext = md.reach * (0.4 + 0.6 * prog)
        if f.side == "p":
            # posizione articolazione reale se disponibile, altrimenti reach
            jx = self._joint_x(md.limb, pose, default=ext)
            jy = self._joint_y(md.limb, pose, default=-1.0)
            return CapsuleBox(jx - 0.11, jy - 0.11, 0.22, 0.22)
        # nemico: box davanti al suo corpo, in direzione -x
        cx = f.x - ext if f.facing < 0 else f.x + ext
        return CapsuleBox(cx - 0.12, -1.15, 0.24, 0.5)

    def _hurt_box(self, f: Fighter, pose) -> CapsuleBox:
        """clsn2: il corpo. La schivata non restringe il box — e' i-frame
        (NotHitBy), gestita in _resolve_hit."""
        if f.side == "p":
            return CapsuleBox(PLAYER_HURT.x, PLAYER_HURT.y,
                              PLAYER_HURT.w, PLAYER_HURT.h)
        return CapsuleBox(f.x - ENEMY_HURT_W / 2, f.y - ENEMY_HURT_H / 2,
                          ENEMY_HURT_W, ENEMY_HURT_H)

    # --- risoluzione hit (MUGEN order: dedup -> guard -> hit) -------------
    def _resolve_hit(self, att: Fighter, vic: Fighter, evs):
        ab = self._attack_box(att, self._last_pose if att.side == "p" else None)
        if ab is None:
            return
        hb = self._hurt_box(vic, self._last_pose if vic.side == "p" else None)
        if not ab.overlaps(hb):
            return
        # serial dedup: MUGEN tgt->hit_ids[att] == serial -> niente re-hit
        if att.attack_serial in vic.hit_ids:
            return
        # dodge = i-frames: in MUGEN la schivata e' uno stato NotHitBy —
        # la hurtbox non esiste per quei tick, non solo piu' piccola.
        if vic.dodging:
            vic.hit_ids.add(att.attack_serial)  # l'attacco e' comunque consumato
            return
        vic.hit_ids.add(att.attack_serial)

        md = att.move
        impact_x = ab.x + ab.w / 2
        impact_y = ab.y + ab.h / 2

        # parata: vittima tiene la posa + attacco in range -> blockstun
        in_range = abs(att.x - vic.x) < GUARD_RANGE + md.reach * 0.5
        if vic.blocking and in_range and vic.state in (St.IDLE, St.BLOCKSTUN):
            vic.state = St.BLOCKSTUN
            vic.statetime = 0
            vic.stun_until = self.tick + md.blockstun
            vic.hp = max(0, vic.hp - md.guard_damage)
            att.hitstop = vic.hitstop = max(1, md.hitstop - 2)  # guard pausetime
            evs.append(Ev(self.tick, "block", att.side, md.name,
                          md.guard_damage, impact_x, impact_y,
                          att.hitstop, self._combo, vic.hp))
            return

        # hit pieno
        vic.hp = max(0, vic.hp - md.damage)
        self._combo = self._combo + 1 if vic.state in (St.HITSTUN, St.DOWN) else 1
        att.hitstop = vic.hitstop = md.hitstop
        vic.vel_x = md.kbx * -att.facing * att.facing  # direzione del colpo
        vic.vel_x = md.kbx if att.side == "p" else -md.kbx
        vic.vel_y = -abs(md.kby)
        vic.state = St.HITSTUN
        vic.statetime = 0
        vic.stun_until = self.tick + md.hitstun
        evs.append(Ev(self.tick, "hit", att.side, md.name, md.damage,
                      impact_x, impact_y, md.hitstop, self._combo, vic.hp))
        if vic.hp <= 0:
            vic.state = St.KO
            vic.statetime = 0
            evs.append(Ev(self.tick, "ko", att.side, md.name, md.damage,
                          impact_x, impact_y, victim_hp=0))
        elif md.fall:
            vic.state = St.DOWN
            vic.statetime = 0
            evs.append(Ev(self.tick, "down", att.side, md.name,
                          victim_hp=vic.hp))

    # --- fisica minima ----------------------------------------------------
    def _knockback(self, f: Fighter, evs):
        if f.vel_x == 0 and f.vel_y == 0:
            return
        f.x += f.vel_x
        f.y += f.vel_y
        f.vel_x *= 0.82   # friction MUGEN-style
        if f.vel_y < 0:
            f.vel_y += 0.004  # gravita'
        if f.y > 0:
            f.y = 0
            f.vel_y = 0
        if abs(f.vel_x) < 0.001:
            f.vel_x = 0

    def _enemy_spacing(self, evs):
        """Il nemico cammina verso il player quando idle e lontano."""
        e = self.e
        if e.state != St.IDLE or not e.alive or not self.enemy_ai:
            return
        d = e.x - self.p.x
        if d > ENEMY_RANGE:
            e.x -= ENEMY_WALK

    def _ai_step(self, evs):
        """AI nemico minimale, deterministica (seed fissato a costruzione).
        Decide da IDLE: in range -> jab/hook; il player attacca -> a volte
        alza la guardia (blocking) per un intervallo."""
        e = self.e
        if e.state != St.IDLE or not e.alive or not self.enemy_ai:
            return
        self._ai_next -= 1
        if self._ai_next > 0:
            # reattivita' parata: se il player e' in ATTACK startup, puo' coprire
            if self.p.state == St.ATTACK and self.p.phase == Ph.STARTUP \
               and self._rand() % 100 < 35:
                e.blocking = True
            elif self.p.state != St.ATTACK:
                e.blocking = False
            return
        e.blocking = False
        self._ai_next = ENEMY_DECIDE + self._rand() % 40
        d = e.x - self.p.x
        if d < ENEMY_RANGE + 0.3:
            mv = "enemy_jab" if self._rand() % 100 < 65 else "enemy_hook"
            self._start_attack(e, MOVES[mv])

    # --- utilita' pose ----------------------------------------------------
    def _joint_x(self, name, pose, default):
        if pose is None:
            return default
        j = getattr(pose, name, None)
        return j.x if j is not None else default

    def _joint_y(self, name, pose, default):
        if pose is None:
            return default
        j = getattr(pose, name, None)
        return j.y if j is not None else default

    # --- introspection per renderer/HUD -----------------------------------
    def snapshot(self) -> dict:
        """Stato serializzabile (dump/replay/debug HUD)."""
        return {
            "t": self.tick,
            "p": {"hp": self.p.hp, "st": int(self.p.state), "sT": self.p.statetime,
                  "x": round(self.p.x, 4), "blk": self.p.blocking,
                  "mv": self.p.move.name if self.p.move else ""},
            "e": {"hp": self.e.hp, "st": int(self.e.state), "sT": self.e.statetime,
                  "x": round(self.e.x, 4), "blk": self.e.blocking,
                  "mv": self.e.move.name if self.e.move else ""},
            "combo": self._combo,
        }

    def reset(self):
        self.__init__(enemy_x=self.e.x if self.e.alive else 0.85)
