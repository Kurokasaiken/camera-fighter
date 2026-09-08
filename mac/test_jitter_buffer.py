"""Test S0 — jitter buffer + determinismo replay (PLAN-048d)."""

from __future__ import annotations

import os
import tempfile

from jitter_buffer import (JitterBuffer, REORDER_WINDOW, FLUSH_TIMEOUT_MS)
from replay_harness import synth_trace, replay_trace, fingerprint


def mk_frame(seq, valid=True, tracker="A"):
    return {"seq": seq, "valid": valid, "tracker_id": tracker}


def feed(jb, seqs, start_ts=0.0, step=33.0):
    out = []
    jb.on_emit = out.append
    t = start_ts
    for s in seqs:
        while jb._timers and jb._timers[0][0] < t:
            jb.tick(jb._timers[0][0])
        jb.process_frame(s, mk_frame(s), t)
        jb.tick(t)
        t += step
    return out, t


def test_in_order():
    jb = JitterBuffer()
    out, _ = feed(jb, [1, 2, 3, 4])
    assert [e.seq_id for e in out] == [1, 2, 3, 4]
    assert all(e.status == "ACCEPTED" for e in out)
    assert out[0].boundary is True and not any(e.boundary for e in out[1:])


def test_reorder_within_window():
    jb = JitterBuffer()
    out, _ = feed(jb, [1, 3, 2, 4])
    assert [e.seq_id for e in out] == [1, 2, 3, 4]
    assert out[2].status == "REORDERED_ACCEPTED"  # seq 3 arrivato fuori ordine


def test_duplicate_dropped():
    jb = JitterBuffer()
    out, _ = feed(jb, [1, 2, 2, 3])
    assert [e.seq_id for e in out] == [1, 2, 3]
    assert jb.stats.duplicates == 1


def test_gap_flush_and_boundary():
    jb = JitterBuffer()
    out, _ = feed(jb, [1, 2, 5])  # 5 fuori finestra? no: 5 <= 3+2 -> buffered
    # next_expected=3, buffer={5}: flush dopo 33ms
    jb.tick(3 * 33.0 + FLUSH_TIMEOUT_MS + 1)
    seqs = [e.seq_id for e in out]
    assert seqs == [1, 2, 5]
    assert jb.stats.declared_gaps == 2          # 3 e 4 dichiarati GAP
    assert out[-1].boundary is True             # nuova epoca al primo frame post-gap
    assert 3 in jb.declared_gaps and 4 in jb.declared_gaps


def test_late_after_gap_is_late_dropped():
    jb = JitterBuffer()
    out, t = feed(jb, [1, 2, 5])          # flush per seq 3 scade a t=66+66=132
    jb.tick(140)                        # flush -> gap 3,4 dichiarati, emesso 5
    jb.process_frame(3, mk_frame(3), 145)   # late per gap dichiarato (idle a 310)
    assert jb.stats.late == 1
    jb.process_frame(2, mk_frame(2), 146)   # duplicato
    assert jb.stats.duplicates == 1


def test_out_of_window():
    jb = JitterBuffer()
    out, _ = feed(jb, [1, 2, 10])  # 10 > 3+2
    assert jb.stats.out_of_window == 1
    assert [e.seq_id for e in out] == [1, 2]


def test_idle_gap_resets_epoch():
    jb = JitterBuffer()
    out, t = feed(jb, [1, 2, 3])
    jb.tick(t + 200)                   # idle 170ms -> gap_pending
    assert jb.gap_pending is True
    jb.process_frame(50, mk_frame(50), t + 220)   # seq lontano accettato
    assert out[-1].seq_id == 50 and out[-1].boundary is True
    assert jb.next_expected == 51


def test_tracker_change_resets():
    jb = JitterBuffer()
    out, t = feed(jb, [1, 2, 3])
    jb.process_frame(4, mk_frame(4, tracker="B"), t)
    assert jb.stats.tracker_resets == 1
    assert out[-1].boundary is True


def test_invalid_frame_no_tracker_reset():
    jb = JitterBuffer()
    out, t = feed(jb, [1, 2])
    jb.process_frame(3, mk_frame(3, valid=False, tracker="B"), t)
    assert jb.stats.tracker_resets == 0


def test_determinism_synth():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.trace")
        synth_trace(p, n=300, loss=0.05, reorder=0.15, seed=7)
        _j1, o1 = replay_trace(p)
        _j2, o2 = replay_trace(p)
        assert fingerprint(o1) == fingerprint(o2)


def test_reorder_heavy_trace():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.trace")
        synth_trace(p, n=500, loss=0.10, reorder=0.30, seed=1)
        jb, out = replay_trace(p)
        seqs = [e.seq_id for e in out]
        # output strettamente crescente entro ogni epoca
        for a, b, ef in zip(seqs, seqs[1:], out[1:]):
            assert b > a or ef.boundary
        assert jb.stats.declared_gaps >= 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} test passati")
