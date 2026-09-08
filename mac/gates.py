"""Gate sequencer: G0.1 -> G0 -> G0.5 -> raccolta -> G1 -> ... -> G4.

Enforced, non documentato: ogni transizione e' registrata in gates.json e
pass_gate() fallisce (ContractError) se l'ordine e' violato o se il freeze
non verifica. Sequenza:

  G0.1 contratti -> G0 freeze -> G0.5 sanity -> COLLECT -> G1 baseline
  -> G2 jab -> G3 robustezza -> HOLDOUT open -> FINAL -> G4 playtest

Uso:
  venv/bin/python gates.py status
  venv/bin/python gates.py pass G0.5   # dopo esecuzione reale della suite
"""

from __future__ import annotations

import json
import os
import sys
import time

import contracts

GATES_PATH = "gates.json"
ORDER = ["G0.1", "G0", "G0.5", "COLLECT", "G1", "G2", "G3",
         "HOLDOUT_OPEN", "FINAL", "G4"]


def _load() -> dict:
    return json.load(open(GATES_PATH)) if os.path.exists(GATES_PATH) else {}


def current() -> str:
    g = _load()
    for step in ORDER:
        if not g.get(step, {}).get("passed"):
            return step
    return "DONE"


def pass_gate(step: str, note: str = ""):
    if step not in ORDER:
        raise contracts.ContractError(f"gate sconosciuto: {step}")
    g = _load()
    idx = ORDER.index(step)
    for prev in ORDER[:idx]:
        if not g.get(prev, {}).get("passed"):
            raise contracts.ContractError(
                f"sequenza violata: {prev} non passato prima di {step}")
    # freeze deve verificare per ogni gate >= G0.5 (artifact sigillato)
    if idx >= ORDER.index("G0.5"):
        import freeze_artifact
        freeze_artifact.verify()
    # se holdout aperto, nessun gate precedente puo' essere ripassato
    if g.get("HOLDOUT_OPENED") and step != "FINAL":
        raise contracts.ContractError(
            "holdout gia' aperto: solo FINAL e' permesso")
    g[step] = {"passed": True, "at": time.time(), "note": note}
    json.dump(g, open(GATES_PATH, "w"), indent=2)
    print(f"[gate] {step} PASS -> prossimo: {current()}")


def status():
    g = _load()
    for step in ORDER:
        s = "PASS" if g.get(step, {}).get("passed") else "----"
        print(f"  {s}  {step}")
    print(f"corrente: {current()}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pass":
        pass_gate(sys.argv[2], " ".join(sys.argv[3:]))
    else:
        status()
