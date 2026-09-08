"""G0 — Freeze artifact: sigilla e verifica i contratti del piano.

freeze.json contiene: commit SHA, hash dei file di contratto/evaluator/
config, versioni (schema/GT protocol/timebase/matching), provenance.
verify() controlla che i file sul disco corrispondano all'artifact —
fail-closed su qualsiasi mismatch.

Uso:
  venv/bin/python freeze_artifact.py seal     # crea freeze.json
  venv/bin/python freeze_artifact.py verify   # verifica, exit!=0 se FAIL
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import contracts

FREEZE_PATH = "freeze.json"
SEALED_FILES = [
    "contracts.py", "evaluate.py", "jitter_buffer.py", "pipeline.py",
    "motion_signal.py", "hit_signal.py", "combo_engine.py",
    "leg_tracker.py", "z_gate.py", "capsule.py", "combos.json",
    "body_model.py", "g05_sanity.py",
]


def _sha_file(p: str) -> str:
    if not os.path.exists(p):
        raise contracts.ContractError(f"file sigillato mancante: {p}")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(__file__) or ".").decode().strip()
    except Exception:
        return "nogit"


def build() -> dict:
    return {
        "schema": contracts.SCHEMA_VERSION,
        "freeze_version": "cf-freeze/1",
        "created": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "commit_sha": _git_sha(),
        "file_hashes": {f: _sha_file(f) for f in SEALED_FILES},
        "contracts": {
            "T_MATCH_MS": contracts.T_MATCH_MS,
            "T_NEAR_MS": contracts.T_NEAR_MS,
            "valid_actions": sorted(contracts.VALID_ACTIONS),
            "acceptance_matrix": contracts.ACCEPTANCE_MATRIX,
        },
        "gt_protocol_version": "gt/1",
        "timebase_version": "tb/1",
        "matching_version": "match/1",
        "seed_policy": "deterministic; bootstrap seed=0; no RNG elsewhere",
    }


def verify(path: str = FREEZE_PATH) -> dict:
    if not os.path.exists(path):
        raise contracts.ContractError("freeze.json assente: niente freeze")
    art = json.load(open(path))
    if art.get("schema") != contracts.SCHEMA_VERSION:
        raise contracts.ContractError("freeze: schema version mismatch")
    if art.get("freeze_version") != "cf-freeze/1":
        raise contracts.ContractError("freeze: versione artifact ignota")
    for f, h in art["file_hashes"].items():
        if _sha_file(f) != h:
            raise contracts.ContractError(f"freeze: hash mismatch su {f}")
    c = art["contracts"]
    if c["T_MATCH_MS"] != contracts.T_MATCH_MS or \
            c["acceptance_matrix"] != contracts.ACCEPTANCE_MATRIX:
        raise contracts.ContractError("freeze: contracts divergenti")
    return art


def seal(path: str = FREEZE_PATH) -> dict:
    art = build()
    art["artifact_sha"] = hashlib.sha256(
        json.dumps(art, sort_keys=True).encode()).hexdigest()
    with open(path, "w") as f:
        json.dump(art, f, indent=2, sort_keys=True)
    return art


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        art = verify()
        print(f"[freeze] VERIFY PASS — sha={art['commit_sha'][:8]} "
              f"files={len(art['file_hashes'])}")
    else:
        art = seal()
        print(f"[freeze] SEALED — sha={art['commit_sha'][:8]} "
              f"files={len(art['file_hashes'])} artifact={art['artifact_sha'][:12]}")
