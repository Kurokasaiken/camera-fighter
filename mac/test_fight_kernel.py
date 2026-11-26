"""test_fight_kernel.py — verifica deterministica del kernel MUGEN.

Copre: hit connect, hitonce dedup, guard (chip+blockstun), hitstop freeze,
KO/down/getup, determinismo stesso script, dodge che accorcia la hurtbox,
AI nemico. Esegui: python3 mac/test_fight_kernel.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fight_kernel import FightKernel, St, Ph, MOVES, TICK, Ev

T = TICK
FAILED = []


def check(name, cond, info=""):
    if cond:
        print(f"  ok  {name}")
    else:
        FAILED.append(name)
        print(f" FAIL {name} {info}")


def run(k, seconds, actions_fn=None):
    """Avanza `seconds` di sim; actions_fn(tick)->actions|None."""
    evs = []
    n = int(seconds / T)
    for i in range(n):
        a = actions_fn(k.tick) if actions_fn else None
        evs.extend(k.update(T, None, a))
    return evs


print("== jab connette: danno, hitstun, hitstop, combo ==")
k = FightKernel(enemy_ai=False)
k.e.x = 0.6  # in range
evs = run(k, 0.5, lambda t: {"punch_right"} if t == 0 else None)
hits = [e for e in evs if e.type == "hit"]
check("un hit emesso", len(hits) == 1, hits)
check("danno corretto", hits and hits[0].damage == MOVES["punch_right"].damage)
check("combo=1", hits and hits[0].combo == 1)
check("hp scesi", k.e.hp == 100 - MOVES["punch_right"].damage)
check("vittima in hitstun o oltre", k.e.state in (St.HITSTUN, St.IDLE))

print("== hitonce: niente re-hit nella stessa finestra attiva ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6
evs = run(k, 0.6, lambda t: {"punch_right"} if t == 0 else None)
hits = [e for e in evs if e.type == "hit"]
check("un solo hit per attacco", len(hits) == 1, hits)

print("== guard: chip damage + blockstun, niente hitstun ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6
k._start_attack(k.e, MOVES["enemy_jab"])   # attacco nemico manuale
evs = run(k, 0.5, lambda t: {"blocking": True})
blocks = [e for e in evs if e.type == "block"]
hits = [e for e in evs if e.type == "hit"]
check("block emesso", len(blocks) == 1, evs)
check("nessun hit pieno", len(hits) == 0)
check("chip damage = guard_damage",
      k.p.hp == 100 - MOVES["enemy_jab"].guard_damage)
check("vittima in blockstun poi idle", k.p.state in (St.BLOCKSTUN, St.IDLE))

print("== hitstop: statetime congelato durante il freeze ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6
hit_tick = None; frozen = []
for i in range(40):
    a = {"punch_right"} if k.tick == 0 else None
    evs = k.update(T, None, a)
    if any(e.type == "hit" for e in evs):
        hit_tick = k.tick
        break
check("hit atterrato", hit_tick is not None)
# nei tick di hitstop la vittima non avanza statetime (cmd_state.frozen)
for _ in range(4):
    k.update(T)
    frozen.append(k.snapshot()["e"]["sT"])
check("statetime fermo in hitstop",
      frozen[0] == frozen[1] == frozen[2] == frozen[3], frozen)
check("hitstop ancora attivo", k.e.hitstop > 0, k.e.hitstop)

print("== KO -> stato KO, niente getup ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6; k.e.hp = 5
evs = run(k, 0.6, lambda t: {"punch_right"} if t == 0 else None)
kos = [e for e in evs if e.type == "ko"]
check("evento KO", len(kos) == 1)
check("stato KO", k.e.state == St.KO)
check("hp=0", k.e.hp == 0)

print("== knockdown: calcio pesante -> DOWN poi GETUP ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6
evs = run(k, 0.6, lambda t: {"kick_right"} if t == 0 else None)
downs = [e for e in evs if e.type == "down"]
check("down emesso (kby>0.03)", len(downs) == 1, evs[-6:])
check("stato DOWN", k.e.state == St.DOWN)
evs2 = run(k, 2.2)
check("getup->idle", k.e.state == St.IDLE)

print("== dodge: hurtbox dimezzata, colpo manca ==")
k = FightKernel(enemy_ai=False); k.e.x = 0.6
k._start_attack(k.e, MOVES["enemy_jab"])
evs = run(k, 0.6, lambda t: {"dodge"} if t == 0 else None)
check("il jab manca il player abbassato",
      k.p.hp == 100 and not any(e.type == "hit" and e.attacker == "e" for e in evs),
      k.p.hp)

print("== determinismo: stesso script -> stesso snapshot ==")
def script(seed):
    k_ = FightKernel(seed=seed)
    evs = []
    for i in range(300):
        a = {"punch_right"} if i == 10 else ({"blocking": True} if 100 <= i < 200 else None)
        evs.extend(k_.update(T, None, a))
    return k_.snapshot(), [e.type for e in evs]
s1, t1 = script(1); s2, t2 = script(1)
check("snapshot identici", s1 == s2, f"{s1}\n{s2}")
check("eventi identici", t1 == t2)

print("== AI nemico: attacca in range e puo' parare (deterministica) ==")
k = FightKernel(); k.e.x = 0.6
evs = run(k, 3.0)
ai_hits = [e for e in evs if e.attacker == "e" and e.type == "hit"]
check("nemico ha attaccato", len(ai_hits) >= 1, evs[-8:])
# AI con guard reattiva: il player attacca -> a volte 'block'
k2 = FightKernel(); k2.e.x = 0.6
evs2 = run(k2, 1.2, lambda t: {"punch_right"} if t == 5 else None)
got_block_or_hit = any(e.type in ("block", "hit") for e in evs2)
check("l'AI reagisce all'attacco del player", got_block_or_hit)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED)); sys.exit(1)
print("tutti i test verdi")
