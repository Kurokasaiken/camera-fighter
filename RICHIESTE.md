# Richieste

## Aperte / In corso

### R-001: Avatar 2D controllato dai landmark
**Stato:** in corso  
**Richiesta originale:** muovere un avatar 2D in tempo reale seguendo i landmark della posa, in modo da colpire un nemico con mani e piedi.  
**Note:** scartata la strada del riconoscimento gesti per eccessivi falsi positivi.  
**File coinvolti:** `mac/main_avatar_v2.py`, `mac/pose_mapper.py`, `mac/renderer.py`.

### R-002: Correggere mirror/zoom/inclinazione avatar
**Stato:** aperta  
**Richiesta originale:** l'avatar è mirrored, zoomato e inclinato; deve essere dritto, coerente e della giusta dimensione.  
**Note:** lavoro in corso su `pose_mapper.py` e `renderer.py`.

## Completate

### R-000: Installare Mind Weaver su camera-fighter
**Stato:** completata  
**Esito:** Mind Weaver installato con `install.sh`, creati `AGENTS.md`, `CANON.md`, `context/`, `plans/`, skill in `.agents/skills/`.

---

## S0 completato — PLAN-048d (transport + jitter buffer + replay)

||**Data:** 2026-09-08
||**Cosa:** implementato transport layer deterministico per lo spike Kata Matcher.
||**File:** `mac/jitter_buffer.py` (spec PLAN-048d verbatim: epoch tokens, declared_gaps intervallo intero, begin_boundary pre-emit, idle gap, tracker reset), `mac/replay_harness.py` (record/replay/report/check), `mac/receiver_s0.py` (live loop), `mac/test_jitter_buffer.py` (11 test).
||**Patch Android:** `ts` ora `SystemClock.elapsedRealtime()` (monotonic); confidence (`inFrameLikelihood`) già presente nel pacchetto.
||**Esito test:** 11/11 PASS. Replay deterministico A==B su traccia sintetica (loss 5%, reorder 15%).
||**Osservazione:** con jitter di arrivo >33ms, `idle_timeout=33ms` genera epoche frequenti (164 epoche/287 frame su traccia sintetica). Parametro tunable da calibrare su dati reali (candidato: ~66ms).
||**Gate S0 su dati reali:** `python receiver_s0.py live.trace` → `python replay_harness.py check live.trace` (A==B) → `python replay_harness.py report live.trace`.
||**Collegamenti:** `plans/PLAN-048d` (repo mind-weaver).

---

## Spike S0-S3 implementato — PLAN-048d pipeline completa

||**Data:** 2026-09-08
||**Cosa:** implementazione completa dello spike senza hardware (test su dati sintetici).
||**Architettura:** `jitter_buffer.py` (S0, spec verbatim) → `body_model.py` (S1: body-centric 2D, hip-center origin, spine-length scale, conf per joint, VALID/ELIGIBLE) → `motion_signal.py` (derivata robusta per-action, median+EMA, recovery 3 frame, boundary reset) → `segmentation.py` (energy peaks → MotionEvent immutabili) → `combo_engine.py` (subsequence matching su event stream, timeout-based, single-writer) + `hit_signal.py` (swept test, adiacenza+ELIGIBLE+tracker, HitGate) + `combat_bridge.py` (pending queue, upgrade retroattivo 15 seq) + `pipeline.py` (3 path paralleli) + `main_spike.py` (live/replay/synth) + `synth_pose.py` + `combos.json` (1 combo hardcoded: double_jab).
||**Esito test:** test_jitter_buffer 11/11, test_spike 7/7. S2-synth: TP=10 FN=0 FP=1 TN=39 → acc=0.98 recall=1.00 FP=1/40 (entro criterio FP≤1/40).
||**Determinismo:** A==B verificato su tracce con loss 5% + reorder 15%.
||**Note:** (1) eventi estranei non rompono la sequenza combo — solo timeout; (2) MIN_IMPACT_SPEED=1.5 u/frame non raggiunta dal pugno sintetico — da calibrare su dati reali; (3) idle_timeout=33ms tunable (candidato ~66ms); (4) Android: ts→elapsedRealtime monotonic.
||**S4 resta da fare:** con 4 persone reali quando il Director ha tempo — harness pronto (record → check A==B → report + telemetria).

---

## Calibrazione su dati reali — sessione live 12:58

||**Data:** 2026-09-08
||**Cosa:** prima traccia reale (11 min, 11076 pacchetti) analizzata; soglie ricalibrate.
||**Scoperte:** stream reale ~17fps (non 30); rete ottima (6 lost/11076); jitter buffer: epoche 269→5 dopo idle_timeout=170ms; velocità polso idle p50=0.15 u/frame, pugno p95=0.5; conf caviglie p50=0.33 → calci quasi mai ELIGIBLE (ML Kit non vede i piedi in questa inquadratura — le combo dello spike restano sui pugni); reach polso body-centric max x≈1.0, p99=0.37.
||**Valori calibrati:** FLUSH=66ms, IDLE=170ms, ENERGY_ON=0.06/OFF=0.025, min_speed step=0.18, MIN_IMPACT_SPEED=0.35, hitbox=(0.18,-1.0,0.7,1.4).
||**Esito su traccia reale:** replay deterministico A==B ✅; 97 MotionEvent; 2 COMMIT double_jab; HitSignal funziona ma hitbox da mappare sulla calibrazione di stance.
||**Aperto:** posizione nemico deve derivare dalla calibrazione di stance (reach misurato), non da costante; conf caviglie troppo bassa per kick actions; S4 resta da fare con utenti reali.

---

## Ricostruzione fisica delle gambe (merge/swap ML Kit)

||**Data:** 2026-09-08
||**Cosa:** in vista laterale ML Kit fonde/scambia le gambe (125 swap + migliaia merge). Invece di marcare i calci INELIGIBLE, `leg_tracker.py` ricostruisce: la gamba ATTIVA (quella con velocita' recente) segue la detection, la gamba PIANTATA viene congelata all'ultima posizione affidabile (vincolo fisico: un piede regge il peso). Conf ridotta = estimated.
||**Esito su traccia reale:** kick events tornati a 41 (vs 10 con soppressione) senza falsi scambi di lato; gambe colorate L=arancione/R=magenta nello scheletro grezzo con lettera L/R sulle ginocchia.
||**Nota:** i kick si misurano sulla caviglia quando visibile (conf>=0.6 su entrambi i capi della derivata), altrimenti fallback ginocchio.
