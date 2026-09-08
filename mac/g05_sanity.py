"""G0.5 — Evaluator sanity suite: PASS/FAIL su casi sintetici noti.

Gate reale: ogni caso deve produrre ESATTAMENTE il risultato atteso.
Copre: matching boundaries (T_MATCH inclusivo), duplicate, unicita'
GT<->detection, UNKNOWN != FP != confusion, INVALID_SESSION su offset non
stimabile, fail-closed su schema/dati corrotti, determinismo byte-for-byte.

Uso: venv/bin/python g05_sanity.py   -> exit 0 = PASS, exit 1 = FAIL
"""

from __future__ import annotations

import sys

import contracts
from contracts import ContractError

T = contracts.T_MATCH_MS
RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {detail}")


def gt(action="jab", side="left", lo=1000, hi=1020, **kw):
    ev = {"action": action, "side": side, "onset_interval": [lo, hi],
          "annotation_ts": 0.0, "confidence": 1.0}
    ev.update(kw)
    return contracts.validate_gt_event(ev)


def det(onset, side="left", action="jab", eid=1, tq="GOOD", emitted=None):
    return {"event_id": eid, "action": action, "side": side,
            "onset_ts": onset, "emitted_ts": emitted or onset + 100,
            "tracking_quality": tq}


# ---- matching boundaries -------------------------------------------------
g = [gt()]
check("match: onset al bordo min (inclusivo)",
      contracts.match_events(g, [det(1000 - T)])["tp"] == 1)
check("match: onset al bordo max (inclusivo)",
      contracts.match_events(g, [det(1020 + T)])["tp"] == 1)
check("match: 1ms oltre il bordo => FP+miss",
      (lambda r: r["fp"] == 1 and r["miss"] == 1)
      (contracts.match_events(g, [det(1020 + T + 1)])))

# ---- unicita' e duplicati -------------------------------------------------
r = contracts.match_events(g, [det(1000, eid=1), det(1010, eid=2)])
check("unicita': 1 GT + 2 det => 1 TP + 1 FP", r["tp"] == 1 and r["fp"] == 1)
r = contracts.match_events([gt(), gt(lo=5000, hi=5020)],
                           [det(1010, eid=2), det(1000, eid=1),
                            det(5005, eid=3)])
check("ordine: det non ordinati => greedy per onset, duplicato = FP",
      r["tp"] == 2 and r["fp"] == 1)

# ---- UNKNOWN / confusion --------------------------------------------------
r = contracts.match_events(g, [det(1000, side="unknown")])
check("UNKNOWN side != FP != confusion", r["tp"] == 1 and
      r["unknown_side"] == 1 and r["lr_confusion"] == 0 and r["fp"] == 0)
r = contracts.match_events(g, [det(1000, side="right")])
check("LEFT vs RIGHT => lr_confusion", r["lr_confusion"] == 1)
r = contracts.match_events(g, [det(9000)])
check("det fuori finestra => FP", r["fp"] == 1 and r["miss"] == 1)
r = contracts.match_events(g, [det(9000, tq="LOST")])
check("det in LOST => suppressed non FP", r["suppressed"] == 1 and
      r["fp"] == 0)

# ---- GT schema fail-closed ------------------------------------------------
def must_fail(name, fn):
    try:
        fn()
        check(name, False, "nessun errore sollevato")
    except ContractError:
        check(name, True)
    except Exception as e:
        check(name, False, f"errore non-Contract: {e!r}")

must_fail("FC: GT senza action", lambda: contracts.validate_gt_event({}))
must_fail("FC: GT action ignota",
          lambda: contracts.validate_gt_event({"action": "x", "side": "left",
              "onset_interval": [0, 1], "annotation_ts": 0}))
must_fail("FC: onset_interval invertito",
          lambda: contracts.validate_gt_event({"action": "jab",
              "side": "left", "onset_interval": [5, 1], "annotation_ts": 0}))
must_fail("FC: meta schema ignoto",
          lambda: contracts.validate_session_meta({"schema": "x"}))
must_fail("FC: split ignoto", lambda: contracts.validate_session_meta(
    {"schema": contracts.SCHEMA_VERSION, "session_id": "s",
     "split": "test", "dataset_id": "d", "gt_protocol_version": "gt/1"}))

# ---- timebase -------------------------------------------------------------
def _entries(offset, jitter):
    return [{"arrival_ts": 100000 + i * 60 + (jitter if i % 2 else 0),
             "seq_id": i, "payload": {"ts": 50000 + i * 60}}
            for i in range(10)]

check("timebase: offset stimabile", abs(
    contracts.estimate_offset(_entries(50000, 0)) - 50000) < 1)
must_fail("FC: offset non stimabile (troppi pochi frame)",
          lambda: contracts.estimate_offset(_entries(50000, 0)[:3]))
must_fail("FC: offset jitter eccessivo => INVALID_SESSION",
          lambda: contracts.estimate_offset(_entries(50000, 400)))

# ---- determinismo byte-for-byte -------------------------------------------
det_list = [det(1000, eid=2), det(5005, eid=1), det(9999, eid=3)]
gt_list = [gt(), gt(lo=5000, hi=5020)]
r1 = contracts.match_events(gt_list, det_list)
r2 = contracts.match_events(gt_list, det_list)
r3 = contracts.match_events(gt_list, list(reversed(det_list)))
check("determinismo: stesso input => stesso output",
      repr(r1) == repr(r2) == repr(r3))

# ---- esito ----------------------------------------------------------------
fails = [n for n, ok, _ in RESULTS if not ok]
print(f"\nG0.5: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS"
      + (f" — FAIL: {fails}" if fails else ""))
sys.exit(1 if fails else 0)
