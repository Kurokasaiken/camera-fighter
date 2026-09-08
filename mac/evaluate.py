"""T-006 — Evaluator PLAN-048e: metriche detection su sessioni con GT.

Carica sessions/*.meta.json (SOLO split=evaluation se --eval, o tutte),
replays le tracce, confronta eventi predetti vs ground truth.

Regole pre-registrate (freeze artifact):
- event matching: overlap temporale oppure |onset - gt.start| <= TOL_ONSET
  capture_ts; un GT puo' assorbire al massimo un predetto (greedy per onset)
- "gioco attivo" = unione degli intervalli GT +-PAD_MS
- FP/min riportato su active E su total span (nessun denominatore nascosto)
- metriche primarie: precision, recall, event-level F1, FP/min, latency
  (onset error). TN frame-level NON decisionale.
- bootstrap CI: resampling a livello SESSIONE (non frame: pseudoreplica)

Uso: venv/bin/python evaluate.py [sessions_dir] [--eval]
"""

from __future__ import annotations

import glob
import json
import os
import random
import sys

import msgpack

from jitter_buffer import JitterBuffer
from pipeline import Pipeline

TOL_ONSET_MS = 300        # tolleranza onset evento (pre-registrata)
PAD_MS = 250              # padding "gioco attivo" attorno agli intervalli GT
BOOTSTRAP_N = 2000


def replay(path: str) -> list:
    entries = msgpack.unpackb(open(path, "rb").read(), raw=False)
    pipe = Pipeline("combos.json")
    jb = JitterBuffer(on_emit=lambda ef: pipe.process(ef))
    for e in entries:
        jb.process_frame(e["seq_id"], e["payload"], e["arrival_ts"])
    if entries:
        jb.tick(entries[-1]["arrival_ts"] + 1000)
    return pipe.outputs, entries


def seq_to_ts(entries) -> dict:
    return {e["seq_id"]: float(e["payload"].get("ts", 0)) for e in entries}


def match_events(gt: list, pred: list):
    """Greedy per onset. Ritorna (tp, fn, fp, onset_errs)."""
    gt = sorted(gt, key=lambda g: g["start_ts"])
    pred = sorted(pred, key=lambda p: p["ts"])
    used_g, used_p = set(), set()
    onset_errs = []
    for pi, p in enumerate(pred):
        for gi, g in enumerate(gt):
            if gi in used_g:
                continue
            overlap = p["ts"] >= g["start_ts"] - TOL_ONSET_MS and \
                p["ts"] <= g["end_ts"] + TOL_ONSET_MS
            if overlap:
                used_g.add(gi)
                used_p.add(pi)
                onset_errs.append(abs(p["ts"] - g["start_ts"]))
                break
    return (len(used_p), len(gt) - len(used_g),
            len(pred) - len(used_p), onset_errs)


def evaluate(sessions_dir: str = "sessions", only_eval: bool = True):
    metas = sorted(glob.glob(os.path.join(sessions_dir, "*.meta.json")))
    results = []
    for mp in metas:
        meta = json.load(open(mp))
        if only_eval and meta.get("split") != "evaluation":
            continue
        trace = mp.replace(".meta.json", ".trace")
        if not os.path.exists(trace):
            continue
        outputs, entries = replay(trace)
        s2t = seq_to_ts(entries)
        pred = [{"ts": s2t.get(m.seq_end, 0), "action": m.action,
                 "gesture": meta["gesture"]}
                for o in outputs for m in o.motion_events]
        gt = meta.get("ground_truth", [])
        tp, fn, fp, errs = match_events(gt, pred)
        span = (entries[-1]["payload"]["ts"] - entries[0]["payload"]["ts"]) \
            if entries else 1
        active = sum(g["end_ts"] - g["start_ts"] + 2 * PAD_MS for g in gt) or 1
        results.append({
            "sid": meta["session_id"], "gesture": meta["gesture"],
            "tp": tp, "fn": fn, "fp": fp,
            "prec": tp / (tp + fp) if tp + fp else 0,
            "rec": tp / (tp + fn) if tp + fn else 0,
            "onset_ms": sum(errs) / len(errs) if errs else 0,
            "fp_min_total": fp / (span / 60000) if span else 0,
            "fp_min_active": fp / (active / 60000),
        })

    print(f"{'session':<38} {'gest':<10} TP FN FP  prec  rec  onset  FP/min_t  FP/min_a")
    for r in results:
        print(f"{r['sid']:<38} {r['gesture']:<10} {r['tp']:>2} {r['fn']:>2} "
              f"{r['fp']:>2}  {r['prec']:.2f}  {r['rec']:.2f}  "
              f"{r['onset_ms']:5.0f}  {r['fp_min_total']:7.2f}  "
              f"{r['fp_min_active']:7.2f}")

    if not results:
        print("(nessuna sessione trovata)")
        return
    # aggregate + bootstrap CI a livello sessione
    rng = random.Random(0)
    def agg(sample):
        tp = sum(r["tp"] for r in sample); fn = sum(r["fn"] for r in sample)
        fp = sum(r["fp"] for r in sample)
        return (tp / (tp + fp) if tp + fp else 0,
                tp / (tp + fn) if tp + fn else 0)
    ps, rs = zip(*(agg([rng.choice(results) for _ in results])
                   for _ in range(BOOTSTRAP_N)))
    p50 = sorted(ps); r50 = sorted(rs)
    print(f"\nAGGREGATE prec={sum(r['prec'] for r in results)/len(results):.2f} "
          f"[CI95 {p50[50]:.2f}..{p50[1950]:.2f}] "
          f"rec={sum(r['rec'] for r in results)/len(results):.2f} "
          f"[CI95 {r50[50]:.2f}..{r50[1950]:.2f}]  n_sessions={len(results)}")


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else "sessions"
    # default: solo split=evaluation (regola del piano); --all per diagnostica
    evaluate(d, only_eval=("--all" not in sys.argv))
