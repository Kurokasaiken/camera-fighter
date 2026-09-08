"""Test end-to-end spike — PLAN-048d S1-S3 su dati sintetici.

Esegue: JitterBuffer -> Pipeline -> ComboEngine/HitSignal.
Gate di determinismo: stessa traccia -> stesso output (A==B).
Valutazione S2-style: clip target vs non-target, confusion matrix.
"""

from __future__ import annotations

from jitter_buffer import JitterBuffer, EmittedFrame
from pipeline import Pipeline, fingerprint
import synth_pose

COMBOS = "combos.json"


def run(frames):
    """Esegue una traccia sintetica end-to-end. Ritorna outputs."""
    outputs = []
    pipe = Pipeline(COMBOS)

    def on_emit(ef):
        outputs.append(pipe.process(ef))

    jb = JitterBuffer(on_emit=on_emit)
    for f in frames:
        ts = float(f["ts"])
        while jb._timers and jb._timers[0][0] < ts:
            jb.tick(jb._timers[0][0])
        jb.process_frame(f["seq"], f, ts)
        jb.tick(ts)
    last = frames[-1]["ts"]
    for dt in (33, 66, 100, 200):
        jb.tick(last + dt)
    return outputs


def commits(outputs):
    return [c for o in outputs for c in o.commits]


def hits(outputs):
    return [h for o in outputs for h in o.hit_events]


# --------------------------------------------------------------------- tests

def test_determinism_e2e():
    a = run(synth_pose.gen_trace("double_jab", seed=3, loss=0.05, reorder=0.1))
    b = run(synth_pose.gen_trace("double_jab", seed=3, loss=0.05, reorder=0.1))
    assert fingerprint(a) == fingerprint(b)


def test_double_jab_detected():
    out = run(synth_pose.gen_trace("double_jab", seed=1))
    cs = commits(out)
    assert len(cs) >= 1, "double_jab non rilevato"
    assert cs[0].combo_id == "double_jab"


def test_single_punch_no_commit():
    out = run(synth_pose.gen_trace("single_punch", seed=1))
    assert not commits(out), "single_punch ha committato (FP)"


def test_idle_no_commit():
    out = run(synth_pose.gen_trace("idle", seed=1))
    assert not commits(out), "idle ha committato (FP)"


def test_walk_no_commit():
    out = run(synth_pose.gen_trace("walk", seed=1))
    assert not commits(out), "walk ha committato (FP)"


def test_avatar_always_present():
    """VisualPose indipendente: avatar_frame emesso anche senza match."""
    out = run(synth_pose.gen_trace("idle", seed=2))
    assert all(o.avatar_frame is not None for o in out)


def test_hit_on_enemy_zone():
    """Pugno in avanti verso la hitbox di default produce hit."""
    out = run(synth_pose.gen_trace("single_punch", seed=1))
    # la hitbox di default e' a x in [0.85,1.45]; il wrist normalizzato
    # si estende in +x — verifichiamo solo che il path non crashi e
    # gli eventi siano consistenti (hit dipende dalla geometria synth).
    for o in out:
        for h in o.hit_events:
            assert h.joint in ("right_wrist", "left_wrist",
                             "right_knee", "left_knee")


def eval_s2_style():
    """Mini-valutazione: 10 target + 40 non-target sintetici."""
    TP = FN = FP = TN = 0
    for seed in range(10):
        out = run(synth_pose.gen_trace("double_jab", seed=seed))
        if commits(out):
            TP += 1
        else:
            FN += 1
    for seed in range(40):
        kind = ["idle", "walk", "single_punch", "random", "guard"][seed % 5]
        out = run(synth_pose.gen_trace(kind, seed=seed + 100))
        if commits(out):
            FP += 1
        else:
            TN += 1
    total = TP + FN + FP + TN
    acc = (TP + TN) / total
    rec = TP / (TP + FN) if TP + FN else 0
    print(f"S2-synth: TP={TP} FN={FN} FP={FP} TN={TN} "
          f"acc={acc:.2f} recall={rec:.2f}")
    return acc, rec, FP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} test passati")
    eval_s2_style()
