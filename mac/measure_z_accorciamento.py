"""Misura empirica: il braccio si accorcia quando è alzato lateralmente?"""

import msgpack
import math

with open('visual_live.trace', 'rb') as f:
    e = msgpack.unpackb(f.read(), raw=False)

frames = [x['payload'] for x in e if x.get('payload', {}).get('landmarks')]

LS, LE, RS, RE = 11, 13, 12, 14
LH, RH = 23, 24

measurements = []
for p in frames:
    l = p['landmarks']
    if len(l) < 33:
        continue

    # joint confidence: minimo 0.7
    if min(l[LS][2], l[LE][2], l[RS][2], l[RE][2], l[LH][2], l[RH][2]) < 0.7:
        continue

    # torso come scala di riferimento
    shx = (l[LS][0] + l[RS][0]) / 2  # shoulder mid x
    shy = (l[LS][1] + l[RS][1]) / 2  # shoulder mid y
    hpx = (l[LH][0] + l[RH][0]) / 2  # hip mid x
    hpy = (l[LH][1] + l[RH][1]) / 2  # hip mid y
    torso = math.hypot(shx - hpx, shy - hpy)
    if torso < 0.05:
        continue

    # LEFT ARM
    # 2D length in torso units
    d2d_l = math.hypot(l[LE][0] - l[LS][0], l[LE][1] - l[LS][1]) / torso
    # Z delta: ML Kit position3D.z (indice 3)
    dz_l = (l[LE][3] - l[LS][3]) if len(l[LE]) > 3 and len(l[LS]) > 3 else 0
    # Lateral elevation: how far is elbow from shoulder horizontally
    lat_l = abs(l[LE][0] - l[LS][0])

    # RIGHT ARM
    d2d_r = math.hypot(l[RE][0] - l[RS][0], l[RE][1] - l[RS][1]) / torso
    dz_r = (l[RE][3] - l[RS][3]) if len(l[RE]) > 3 and len(l[RS]) > 3 else 0
    lat_r = abs(l[RE][0] - l[RS][0])

    measurements.append({'d2d_l': d2d_l, 'dz_l': dz_l, 'lat_l': lat_l,
                         'd2d_r': d2d_r, 'dz_r': dz_r, 'lat_r': lat_r})

print(f"Campioni validi: {len(measurements)}\n")

if measurements:
    d2d_all = sorted([m['d2d_l'] for m in measurements] + [m['d2d_r'] for m in measurements])
    dz_all = sorted([m['dz_l'] for m in measurements] + [m['dz_r'] for m in measurements])
    lat_all = sorted([m['lat_l'] for m in measurements] + [m['lat_r'] for m in measurements])

    print("=== 2D Arm Length (torso units) ===")
    print(f"Range: [{d2d_all[0]:.3f} ... {d2d_all[-1]:.3f}]")
    med_len = d2d_all[len(d2d_all) // 2]
    print(f"Mediana: {med_len:.3f}")
    print(f"Ratio min/max: {d2d_all[0] / d2d_all[-1]:.2f} (1.0=costante, 0.8=accorcia 20%)")

    print("\n=== Z Delta shoulder→elbow (mm) ===")
    print(f"Range: [{dz_all[0]:.1f} ... {dz_all[-1]:.1f}] mm")
    print(f"Mediana: {dz_all[len(dz_all) // 2]:.1f} mm")

    # Quartili di lateralita'
    lat_q25 = lat_all[len(lat_all) // 4]
    lat_q75 = lat_all[3 * len(lat_all) // 4]

    hi_lat = [m for m in measurements for arm in ['l', 'r']
              if (m['lat_' + arm] > lat_q75)]
    lo_lat = [m for m in measurements for arm in ['l', 'r']
              if (m['lat_' + arm] < lat_q25)]

    print(f"\n=== Confronto Braccio Alto vs Basso ===")
    print(f"ALTO (lateral > {lat_q75:.3f}, n={len(hi_lat)}):")
    d2d_hi = sorted([m['d2d_l'] for m in measurements if m['lat_l'] > lat_q75] +
                    [m['d2d_r'] for m in measurements if m['lat_r'] > lat_q75])
    if d2d_hi:
        print(f"  2D length mediana: {d2d_hi[len(d2d_hi) // 2]:.3f}")

    print(f"BASSO (lateral < {lat_q25:.3f}, n={len(lo_lat)}):")
    d2d_lo = sorted([m['d2d_l'] for m in measurements if m['lat_l'] < lat_q25] +
                    [m['d2d_r'] for m in measurements if m['lat_r'] < lat_q25])
    if d2d_lo:
        print(f"  2D length mediana: {d2d_lo[len(d2d_lo) // 2]:.3f}")

    if d2d_hi and d2d_lo:
        diff = d2d_lo[len(d2d_lo) // 2] - d2d_hi[len(d2d_hi) // 2]
        print(f"\nDifferenza (basso - alto): {diff:.3f}")
        if abs(diff) > 0.05:
            print("*** SIGNIFICATIVA: il braccio si accorcia quando è alzato! ***")
            print(f"    Entità: {abs(diff) / med_len * 100:.1f}% dell'immagine")
        else:
            print("→ Entro rumore naturale")
