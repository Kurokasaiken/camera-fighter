"""G1+ — Evaluator unica autorita' (PLAN-048e v3.1).

Fail-closed: richiede freeze verificato, meta con schema cf-contracts/1,
GT validati via contracts.validate_gt_event, timebase via
contracts.estimate_offset (offset non stimabile => sessione esclusa).

Matching: contracts.match_events — unico algoritmo autorizzato.
Split: default "validation"; --split calibration|validation; --final
apre l'holdout via holdout_lock.open_holdout (richiede gate G3).

Uso:
  venv/bin/python evaluate.py [sessions_dir] [--split validation] [--final]
"""

from __future__ import annotations

import glob
import json
import os
import random
import sys

import msgpack

import contracts
import freeze_artifact
from jitter_buffer import JitterBuffer
from pipeline import Pipeline

PAD_MS = 250
BOOTSTRAP_N = 2000


def replay(path: str):
    entries = msgpack.unpackb(open(path, "rb").read(), raw=False)
    pipe = Pipeline("combos.json")
    jb = JitterBuffer(on_emit=lambda ef: pipe.process(ef))
    for e in entries:
        jb.process_frame(e["seq_id"], e["payload"], e["arrival_ts"])
    if entries:
        jb.tick(entries[-1]["arrival_ts"] + 1000)
    return pipe.outputs, entries


def _norm_action(raw: str):
    """'punch_left' -> ('punch','left'); 'jab' -> ('jab','unknown')."""
    for s in ("_left", "_right"):
        if raw.endswith(s):
            return raw[: -len(s)], s[1:]
    return raw, "unknown"


def session_metrics(meta: dict, entries: list, outputs: list) -> dict:
    """Metriche di una sessione — contratto contracts.match_events."""
    contracts.estimate_offset(entries)   # INVALID_SESSION se non stimabile
    s2t = {e["seq_id"]: float(e["payload"].get("ts", 0)) for e in entries}
    det = []
    for i, o in enumerate(outputs):
        for m in o.motion_events:
            act, side = _norm_action(m.action)
            det.append({"event_id": f"{meta['session_id']}#{i}",
                        "action": act, "side": side,
                        "onset_ts": s2t.get(m.seq_end, 0),
                        "emitted_ts": 0.0,
                        "tracking_quality": "GOOD"})
    gt = [contracts.validate_gt_event(g) for g in meta.get("ground_truth", [])]
    r = contracts.match_events(gt, det)
    span = (entries[-1]["payload"]["ts"] - entries[0]["payload"]["ts"]) \
        if entries else 1
    onset = sorted(r["onset_errs"])
    return {
        "sid": meta["session_id"], "gesture": meta["gesture"],
        **{k: r[k] for k in ("tp", "miss", "fp", "suppressed",
                             "lr_confusion", "unknown_side")},
        "prec": r["tp"] / (r["tp"] + r["fp"]) if r["tp"] + r["fp"] else 0,
        "rec": r["tp"] / (r["tp"] + r["miss"]) if r["tp"] + r["miss"] else 0,
        "onset_p50": onset[len(onset) // 2] if onset else 0,
        "onset_p95": onset[int(len(onset) * 0.95)] if onset else 0,
        "fp_min_total": r["fp"] / (span / 60000) if span else 0,
        "unknown_rate": r["unknown_side"] / len(det) if det else 0,
        "n_det": len(det), "n_gt": len(gt),
    }


def evaluate(sessions_dir: str = "sessions", split: str = "validation"):
    freeze_artifact.verify()   # fail-closed: artifact deve essere integro
    metas = sorted(glob.glob(os.path.join(sessions_dir, "*.meta.json")))
    results, excluded = [], []
    for mp in metas:
        try:
            meta = contracts.validate_session_meta(json.load(open(mp)))
        except contracts.ContractError as e:
            excluded.append((mp, str(e)))
            continue
        if meta["split"] != split:
            continue
        trace = mp.replace(".meta.json", ".trace")
        if not os.path.exists(trace):
            excluded.append((mp, "trace mancante"))
            continue
        try:
            outputs, entries = replay(trace)
            results.append(session_metrics(meta, entries, outputs))
        except contracts.ContractError as e:
            excluded.append((mp, str(e)))

    hdr = (f"{'session':<36} {'gest':<10} TP MS FP SP LRC UNK "
           f"prec  rec  o50  o95  FP/min")
    print(hdr)
    for r in results:
        print(f"{r['sid']:<36} {r['gesture']:<10} {r['tp']:>2} {r['miss']:>2} "
              f"{r['fp']:>2} {r['suppressed']:>2} {r['lr_confusion']:>3} "
              f"{r['unknown_side']:>3}  {r['prec']:.2f}  {r['rec']:.2f}  "
              f"{r['onset_p50']:3.0f} {r['onset_p95']:4.0f}  "
              f"{r['fp_min_total']:6.2f}")
    for mp, why in excluded:
        print(f"  EXCLUDED {os.path.basename(mp)}: {why}")
    if not results:
        print("(nessuna sessione nello split richiesto)")
        return

    rng = random.Random(0)
    def agg(sample):
        tp = sum(r["tp"] for r in sample)
        fn = sum(r["miss"] for r in sample)
        fp = sum(r["fp"] for r in sample)
        return (tp / (tp + fp) if tp + fp else 0,
                tp / (tp + fn) if tp + fn else 0)
    ps, rs = zip(*(agg([rng.choice(results) for _ in results])
                   for _ in range(BOOTSTRAP_N)))
    p50, r50 = sorted(ps), sorted(rs)
    print(f"\nAGGREGATE[{split}] prec={sum(r['prec'] for r in results)/len(results):.2f} "
          f"[CI95 {p50[50]:.2f}..{p50[1950]:.2f}] "
          f"rec={sum(r['rec'] for r in results)/len(results):.2f} "
          f"[CI95 {r50[50]:.2f}..{r50[1950]:.2f}]  n={len(results)}")


def evaluate_holdout():
    """Final evaluation: unico path autorizzato sull'holdout."""
    import holdout_lock
    files = holdout_lock.open_holdout()
    print(f"[final] holdout aperto: {len(files)} file — "
          f"implementare replay su payload (v3.1)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--final" in args:
        evaluate_holdout()
    else:
        d = next((a for a in args if not a.startswith("-")), "sessions")
        sp = "validation"
        if "--split" in args:
            sp = args[args.index("--split") + 1]
        evaluate(d, split=sp)
