"""T-008 — Calibrazione reach/hitbox da sessione di guardia (PLAN-048e).

Legge sessioni calibration con gesture 'guard': misura la distribuzione del
reach dei polsi in unita' di torso (x body-centric davanti al busto) e
produce calibration.json con:
  reach_p95      reach p95 dei polsi (x max osservato)
  envelope       incertezza di misura = p95 - p50 del reach (pre-registrato:
                 errore di scala/posizione, NON "larghezza che prende i colpi")
  capsule        (ax,ay,bx,by,radius) spalla->polso esteso + envelope

Tutto calcolato SOLO su split=calibration e scritto come freeze artifact
(calibration.json e' committabile e versionato).

Uso: venv/bin/python calibrate_reach.py [sessions_dir]
"""

from __future__ import annotations

import glob
import json
import os
import sys

import msgpack

from body_model import build_body_frame
from landmarks import RIGHT_WRIST, LEFT_WRIST, RIGHT_SHOULDER, LEFT_SHOULDER


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p / 100 * len(s)))] if s else 0.0


def main(sessions_dir="sessions", out_path="calibration.json"):
    reach = []
    shoulder = []
    for mp in glob.glob(os.path.join(sessions_dir, "*.meta.json")):
        meta = json.load(open(mp))
        if meta.get("split") != "calibration" or meta.get("gesture") != "guard":
            continue
        trace = mp.replace(".meta.json", ".trace")
        entries = msgpack.unpackb(open(trace, "rb").read(), raw=False)
        for e in entries:
            f = build_body_frame(e["payload"], e["seq_id"], False)
            if not f.valid:
                continue
            for w, s in ((RIGHT_WRIST, RIGHT_SHOULDER),
                         (LEFT_WRIST, LEFT_SHOULDER)):
                if f.conf[w] >= 0.6 and f.conf[s] >= 0.6:
                    reach.append(f.pos[w][0])      # x davanti al busto
                    shoulder.append(f.pos[s])

    if len(reach) < 50:
        print(f"[CAL] campioni insufficienti ({len(reach)}) — serve una "
              f"sessione 'guard' calibration")
        return

    p50, p95 = pct(reach, 50), pct(reach, 95)
    envelope = p95 - p50                       # incertezza di reach
    sho = (sum(s[0] for s in shoulder) / len(shoulder),
           sum(s[1] for s in shoulder) / len(shoulder))
    calib = {
        "version": 1,
        "source": "calibration set (guard sessions)",
        "n_samples": len(reach),
        "reach_p50": p50, "reach_p95": p95,
        "envelope": envelope,
        "capsule": {
            "ax": sho[0], "ay": sho[1],
            "bx": p95, "by": sho[1],
            "radius": envelope,
        },
    }
    with open(out_path, "w") as fp:
        json.dump(calib, fp, indent=2)
    print(f"[CAL] {out_path}: reach p50={p50:.2f} p95={p95:.2f} "
          f"envelope={envelope:.3f} n={len(reach)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sessions")
