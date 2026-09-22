"""Analizza una sessione di calibrate_arm_angle_bias.py: per ogni angolo noto,
misura la lunghezza 2D osservata del bicipite (in unita' torso) e lo z medio
stimato da ML Kit. Produce bias(angolo) = lunghezza_osservata / lunghezza_a_0.

Uso:
  venv/bin/python analyze_arm_angle_bias.py <session_id>
  venv/bin/python analyze_arm_angle_bias.py sessions/20260916-153000-armbias-left-a1b2c3

Se il bias e' significativo e monotono con l'angolo, scrive anche
arm_bias_calibration.json con la funzione di correzione misurata.
"""

import json
import math
import sys

import msgpack

SHOULDER = {"left": 11, "right": 12}
ELBOW = {"left": 13, "right": 14}
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12


def torso_length(l):
    shx = (l[LEFT_SHOULDER][0] + l[RIGHT_SHOULDER][0]) / 2
    shy = (l[LEFT_SHOULDER][1] + l[RIGHT_SHOULDER][1]) / 2
    hpx = (l[LEFT_HIP][0] + l[RIGHT_HIP][0]) / 2
    hpy = (l[LEFT_HIP][1] + l[RIGHT_HIP][1]) / 2
    return math.hypot(shx - hpx, shy - hpy)


def main():
    if len(sys.argv) < 2:
        print("uso: analyze_arm_angle_bias.py <session_id_or_path>")
        sys.exit(1)

    sid = sys.argv[1]
    base = sid if sid.startswith("sessions/") else f"sessions/{sid}"
    if base.endswith(".trace") or base.endswith(".meta.json"):
        base = base.rsplit(".", 1)[0].rsplit(".meta", 1)[0]

    with open(f"{base}.meta.json") as f:
        meta = json.load(f)
    with open(f"{base}.trace", "rb") as f:
        entries = msgpack.unpackb(f.read(), raw=False)

    side = meta["side"]
    s_idx, e_idx = SHOULDER[side], ELBOW[side]
    segments = meta["segments"]

    print(f"Sessione: {meta['session_id']} | braccio={side} | {len(entries)} frame totali\n")

    results = []
    for seg in segments:
        angle = seg["angle_deg"]
        lo, hi = seg["start_ms"], seg["end_ms"]

        lengths = []
        zs = []
        for e in entries:
            if not (lo <= e["arrival_ts"] <= hi):
                continue
            l = e["payload"].get("landmarks", [])
            if len(l) < 33:
                continue
            if min(l[s_idx][2], l[e_idx][2], l[LEFT_HIP][2], l[RIGHT_HIP][2]) < 0.7:
                continue
            torso = torso_length(l)
            if torso < 0.05:
                continue
            d2d = math.hypot(l[e_idx][0] - l[s_idx][0], l[e_idx][1] - l[s_idx][1]) / torso
            lengths.append(d2d)
            if len(l[e_idx]) > 3 and len(l[s_idx]) > 3:
                zs.append(l[e_idx][3] - l[s_idx][3])

        if not lengths:
            print(f"angolo {angle:>3}°: nessun campione valido (conf bassa?)")
            continue

        lengths.sort()
        med_len = lengths[len(lengths) // 2]
        med_z = sorted(zs)[len(zs) // 2] if zs else float("nan")
        results.append({"angle_deg": angle, "median_length": med_len,
                        "median_dz_mm": med_z, "n_samples": len(lengths)})
        print(f"angolo {angle:>3}°: lunghezza 2D mediana={med_len:.3f} (n={len(lengths)})  "
              f"Δz stimato={med_z:+.1f}mm")

    if len(results) < 2:
        print("\nServono almeno 2 angoli con campioni validi per calcolare il bias.")
        return

    ref = results[0]["median_length"]  # riferimento: primo angolo (tipicamente 0°)
    print(f"\n=== Bias relativo a {results[0]['angle_deg']}° (lunghezza={ref:.3f}) ===")
    for r in results:
        bias = r["median_length"] / ref if ref > 0 else float("nan")
        pct = (bias - 1.0) * 100
        flag = " <-- accorciamento >10%" if pct < -10 else ""
        print(f"  {r['angle_deg']:>3}°: bias={bias:.3f}  ({pct:+.1f}%){flag}")

    # Monotonia: il bias scende costantemente con l'angolo?
    biases = [r["median_length"] / ref for r in results]
    monotonic = all(biases[i] >= biases[i + 1] - 0.02 for i in range(len(biases) - 1))
    print(f"\nMonotono (decresce con l'angolo)? {'sì' if monotonic else 'no — non lineare, serve più dati'}")

    out = {
        "side": side,
        "session_id": meta["session_id"],
        "reference_angle_deg": results[0]["angle_deg"],
        "reference_length": ref,
        "curve": [{"angle_deg": r["angle_deg"],
                   "bias": r["median_length"] / ref,
                   "median_length": r["median_length"],
                   "n_samples": r["n_samples"]} for r in results],
    }
    out_path = "arm_bias_calibration.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nScritto {out_path} — curva di correzione misurata.")


if __name__ == "__main__":
    main()
