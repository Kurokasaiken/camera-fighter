"""G0.1 — Contratti di valutazione Camera Fighter (PLAN-048e v3.1).

Tutto ciò che definisce il significato di TP/FN/FP/UNKNOWN, la timebase,
il matching, l'acceptance matrix e la politica fail-closed.

Regole congelate (non modificabili dopo G0 senza nuovo freeze):
- Schema versioning obbligatorio: SCHEMA_VERSION nei file; sconosciuto =>
  ContractError (fail-closed, mai interpretazione implicita).
- GT event: {action, side, onset_interval:[min,max], annotation_ts,
  confidence}. L'incertezza e' proprieta' della procedura, non valore fisso.
- TIMEBASE: capture_ts monotonic (ms, dominio phone). arrival_ts monotonic
  (ms, dominio mac). Conversione t_mac = t_phone + offset, stimato per
  sessione; offset non stimabile => INVALID_SESSION.
- Matching deterministico: detection matcha GT se
  det.onset_ts ∈ [gt.onset_min - T_MATCH, gt.onset_max + T_MATCH]
  (estremi INCLUSIVI). Greedy per onset_ts crescente; tie-break seq_id
  crescente. Un GT matcha al massimo una detection e viceversa.
- Side: LEFT/RIGHT/UNKNOWN. GT LEFT + det LEFT => TP side-ok;
  det RIGHT => LR_CONFUSION; det UNKNOWN => UNKNOWN_SIDE (non FP, non
  confusion, contabilizzato in unknown_rate); no det => MISS.
- Detection non matchata => FP (salvo tracking_quality==LOST nel suo
  intervallo: allora SUPPRESSED, contabilizzato in suppression_rate).
- MotionEvent immutabile post-emissione: event_id unico, emitted_ts nel
  dominio mac. event_latency = emitted_ts - onset_ts (stessa timebase).
- Dati corrotti/NaN/timestamp non monotoni => fail-closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SCHEMA_VERSION = "cf-contracts/1"
T_MATCH_MS = 300          # inclusivo: [min - T, max + T]
T_NEAR_MS = 90            # eventi ravvicinati: gap < T_NEAR => near
VALID_ACTIONS = {"jab", "double_jab", "kick", "block", "dodge", "idle",
                 "guard", "walk", "transitions", "punch", "hook",
                 "uppercut", "movement", "none"}
VALID_SIDES = {"left", "right", "both", "unknown"}
TQ = {"GOOD", "DEGRADED", "LOST"}


class ContractError(Exception):
    """Fail-closed: ogni violazione blocca la valutazione."""


# ---------------------------------------------------------------- GT schema

def validate_gt_event(ev: dict) -> dict:
    """Valida un evento GT; solleva ContractError su qualsiasi difetto."""
    if not isinstance(ev, dict):
        raise ContractError("GT event non dict")
    for k in ("action", "side", "onset_interval", "annotation_ts"):
        if k not in ev:
            raise ContractError(f"GT event senza campo {k}")
    if ev["action"] not in VALID_ACTIONS:
        raise ContractError(f"GT action sconosciuta: {ev['action']}")
    if ev["side"] not in VALID_SIDES:
        raise ContractError(f"GT side sconosciuto: {ev['side']}")
    oi = ev["onset_interval"]
    if not (isinstance(oi, (list, tuple)) and len(oi) == 2):
        raise ContractError("onset_interval deve essere [min, max]")
    lo, hi = float(oi[0]), float(oi[1])
    if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
        raise ContractError(f"onset_interval invalido: {oi}")
    if not math.isfinite(float(ev["annotation_ts"])):
        raise ContractError("annotation_ts non finito")
    conf = float(ev.get("confidence", 1.0))
    if not (0.0 <= conf <= 1.0):
        raise ContractError(f"GT confidence fuori [0,1]: {conf}")
    return {"action": ev["action"], "side": ev["side"],
            "onset_min": lo, "onset_max": hi,
            "annotation_ts": float(ev["annotation_ts"]),
            "confidence": conf,
            "context": ev.get("context", "unknown")}


def validate_session_meta(meta: dict) -> dict:
    if meta.get("schema") != SCHEMA_VERSION:
        raise ContractError(f"schema meta sconosciuto: {meta.get('schema')}")
    for k in ("session_id", "split", "dataset_id", "gt_protocol_version"):
        if k not in meta:
            raise ContractError(f"meta senza {k}")
    if meta["split"] not in ("calibration", "validation", "holdout"):
        raise ContractError(f"split sconosciuto: {meta['split']}")
    return meta


# ------------------------------------------------------------- timebase

def estimate_offset(entries: list, min_pairs: int = 5,
                    max_jitter_ms: float = 250.0) -> float:
    """Stima offset phone->mac: t_mac = t_phone + offset.

    Usa mediana(arrival_ts - capture_ts). Se dispersione > max_jitter o
    campioni insufficienti => INVALID_SESSION (ContractError).
    """
    pairs = [(float(e["arrival_ts"]), float(e["payload"].get("ts", float("nan"))))
             for e in entries if e.get("payload", {}).get("ts") is not None]
    if len(pairs) < min_pairs:
        raise ContractError(
            f"INVALID_SESSION: offset non stimabile, {len(pairs)} pairs")
    deltas = sorted(a - c for a, c in pairs)
    med = deltas[len(deltas) // 2]
    spread = deltas[int(len(deltas) * 0.95)] - deltas[int(len(deltas) * 0.05)]
    if spread > max_jitter_ms:
        raise ContractError(
            f"INVALID_SESSION: offset jitter {spread:.0f}ms > {max_jitter_ms}")
    return med


def to_mac_ts(t_phone: float, offset: float) -> float:
    return t_phone + offset


# -------------------------------------------------------------- matching

def match_events(gt: list, det: list):
    """Matching deterministico. Ritorna dict con conteggi e dettagli.

    gt: lista validate_gt_event. det: lista MotionEvent-like dict
    {onset_ts, emitted_ts, side, action, event_id, tracking_quality}.
    Tutto nel dominio capture_ts (onset) — emitted_ts in dominio mac solo
    per latency (convertito dal chiamante se serve).
    """
    gt_s = sorted(range(len(gt)),
                  key=lambda i: (gt[i]["onset_min"], i))
    det_s = sorted(range(len(det)),
                   key=lambda i: (det[i]["onset_ts"], det[i].get("event_id", 0)))
    used_g, out = set(), {"tp": 0, "miss": 0, "fp": 0, "suppressed": 0,
                          "lr_confusion": 0, "unknown_side": 0,
                          "onset_errs": [], "pairs": []}
    used_d = set()
    for di in det_s:
        d = det[di]
        best = None
        for gi in gt_s:
            if gi in used_g:
                continue
            g = gt[gi]
            if g["onset_min"] - T_MATCH_MS <= d["onset_ts"] <= \
                    g["onset_max"] + T_MATCH_MS and \
                    (g["action"] == d.get("action") or
                     g["action"] in ("none", "unknown") or
                     d.get("action") in ("none", "unknown")):
                best = gi
                break
        if best is None:
            if d.get("tracking_quality") == "LOST":
                out["suppressed"] += 1
            else:
                out["fp"] += 1
            continue
        used_g.add(best); used_d.add(di)
        g = gt[best]
        mid = (g["onset_min"] + g["onset_max"]) / 2
        out["onset_errs"].append(abs(d["onset_ts"] - mid))
        gs, ds = g["side"], d.get("side", "unknown")
        if gs in ("both", "unknown") or ds == gs:
            out["tp"] += 1
        elif ds == "unknown":
            out["tp"] += 1; out["unknown_side"] += 1
        else:
            out["lr_confusion"] += 1
        out["pairs"].append((best, d.get("event_id", di)))
    out["miss"] = len(gt) - len(used_g)
    return out


# ------------------------------------------------------- acceptance matrix

# metric, denominator, class: "gate" | "diagnostic" — valori post-baseline
ACCEPTANCE_MATRIX = [
    {"metric": "recall_jab", "denominator": "GT jab events",
     "cls": "gate", "target": ">=0.90"},
    {"metric": "fp_per_min_idle", "denominator": "minutes in idle ctx",
     "cls": "gate", "target": "target 0"},
    {"metric": "fp_per_min_guard", "denominator": "minutes in guard ctx",
     "cls": "gate", "target": "target 0"},
    {"metric": "fp_per_min_transition", "denominator": "min in transition",
     "cls": "diagnostic"},
    {"metric": "onset_err_median", "denominator": "matched events",
     "cls": "gate", "target": "<=50ms"},
    {"metric": "onset_err_p95", "denominator": "matched events",
     "cls": "gate", "target": "<=100ms"},
    {"metric": "event_latency_p95", "denominator": "emitted events",
     "cls": "gate", "target": "<=180ms"},
    {"metric": "duplicate_rate", "denominator": "detections",
     "cls": "gate", "target": "<=2%"},
    {"metric": "lr_confusion", "denominator": "side-known GT matches",
     "cls": "gate", "target": "<=2%"},
    {"metric": "unknown_rate", "denominator": "detections",
     "cls": "diagnostic"},
    {"metric": "double_jab_separation", "denominator": "GT double_jab",
     "cls": "gate", "target": ">=95%"},
    {"metric": "fp_burst", "denominator": "sessions",
     "cls": "diagnostic"},
    {"metric": "tracking_coverage", "denominator": "frames",
     "cls": "diagnostic"},
    {"metric": "suppression_rate", "denominator": "candidate events",
     "cls": "diagnostic"},
]
