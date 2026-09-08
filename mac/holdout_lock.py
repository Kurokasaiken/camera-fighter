"""HOLDOUT blind — lock meccanico, non policy.

Le sessioni holdout vivono cifrate in sessions_holdout.sealed (XOR+SHA
manifest; chiave derivata da un file esterno .holdout_key tenuto fuori dal
repo di lavoro). L'evaluator non puo' leggerle: passa per
open_holdout() che richiede gates.G3_PASSED registrato in gates.json.

Dopo l'apertura, seal_record() marca il freeze come "holdout_opened":
qualsiasi modifica successiva a codice/config invalida la final eval.

Uso:
  venv/bin/python holdout_lock.py seal <dir_sessioni_holdout>
  venv/bin/python holdout_lock.py open    # solo se G3 passato
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import contracts

SEALED_PATH = "sessions_holdout.sealed"
KEY_PATH = os.path.expanduser("~/.config/camera-fighter/holdout.key")
GATES_PATH = "gates.json"
REQUIRED_GATE = "G3"


def _key() -> bytes:
    if not os.path.exists(KEY_PATH):
        os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
        with open(KEY_PATH, "wb") as f:
            f.write(os.urandom(32))
    return open(KEY_PATH, "rb").read()


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def seal(src_dir: str, out: str = SEALED_PATH):
    files = {}
    for name in sorted(os.listdir(src_dir)):
        p = os.path.join(src_dir, name)
        if os.path.isfile(p):
            files[name] = open(p, "rb").read()
    blob = json.dumps({k: v.hex() for k, v in files.items()},
                      sort_keys=True).encode()
    manifest = {"schema": contracts.SCHEMA_VERSION,
                "sealed": True,
                "content_sha": hashlib.sha256(blob).hexdigest(),
                "files": sorted(files)}
    payload = _xor(json.dumps(manifest).encode() + b"\0" + blob, _key())
    with open(out, "wb") as f:
        f.write(payload)
    print(f"[holdout] sigillato {len(files)} file -> {out} "
          f"(sha {manifest['content_sha'][:12]})")


def _gate_ok() -> bool:
    if not os.path.exists(GATES_PATH):
        return False
    g = json.load(open(GATES_PATH))
    return bool(g.get(REQUIRED_GATE, {}).get("passed"))


def open_holdout(path: str = SEALED_PATH) -> dict:
    """Unico punto di accesso. Fail-closed se il gate non e' passato."""
    if not _gate_ok():
        raise contracts.ContractError(
            f"HOLDOUT LOCKED: gate {REQUIRED_GATE} non passato")
    if not os.path.exists(path):
        raise contracts.ContractError("holdout sealed file assente")
    raw = _xor(open(path, "rb").read(), _key())
    manifest_raw, blob = raw.split(b"\0", 1)
    manifest = json.loads(manifest_raw)
    if hashlib.sha256(blob).hexdigest() != manifest["content_sha"]:
        raise contracts.ContractError("holdout: contenuto corrotto")
    files = {k: bytes.fromhex(v) for k, v in
             json.loads(blob.decode()).items()}
    # marca apertura: post-apertura ogni modifica invalida la final eval
    g = json.load(open(GATES_PATH))
    g["HOLDOUT_OPENED"] = {"at": __import__("time").time()}
    json.dump(g, open(GATES_PATH, "w"), indent=2)
    return files


if __name__ == "__main__":
    if sys.argv[1] == "seal":
        seal(sys.argv[2])
    elif sys.argv[1] == "open":
        files = open_holdout()
        print(f"[holdout] aperto: {len(files)} file")
    else:
        print("uso: seal <dir> | open")
