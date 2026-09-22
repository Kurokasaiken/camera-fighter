---
title: SUMI Art Direction
status: completed
created: 2026-09-09
closed: 2026-09-09
---

# PLAN-049: SUMI — Inchiostro su carta + vocabolario d'impatto

## Spec (immutabile dopo battesimo)

**Decisione:** Direzione SUMI (picchiaduro-2d, inchiostro su carta sumi-e).

**Visuale:**
- Sfondo: QLinearGradient verticale #EFE6D6 (top) → #D6C7AC (bottom)
- Grana carta: tile 256×256 random (seed=7), Multiply 6% opacity, baked at init
- Silhouette: BLACK = #1B1A19 (nero profondo sumi), BACK = (30,30,40) per profondità, collo fra testa e spalle
- Nemico: rettangolo vermiglio #B23A2E (lato ombra #7E211A)
- Palette: HP verde #64C864, testo grigio #CCCCCC, terra marrone #8B6F47
- Scale: 155 px/unità torso (da 78)

**Effetti d'impatto (nuovo vocabolario):**
- Hitstop: 60ms al contatto (congelamento visibile)
- Lampo bianco: 200ms full-screen opacity
- Scossa: ±3px su painter.translate
- Schizzo inchiostro: 10 gocce nere + 7 linee di concentrazione, decay 180ms
- Afterimage: pose[-6/-4/-2] con alpha 55/35/18%

**Architettura:**
- Due layer: Display (17fps rete) + Effects (60Hz timer)
- Nessuna modifica a: audio, camera, combattimento, jitter_buffer, leg_tracker

**Vincoli hard:**
- QPainterPath.simplified() cost 8-15ms/frame → fallback drawLine RoundCap se supera 12ms
- 17fps reale → hitstop 60ms ammesso come trade-off
- Solo QPainter, zero GPU/shader
- Zero asset nuovo (riusa SilhouetteRig)

---

## Tasks

### T-001: Applica interventi comuni a renderer.py

**Descrizione:**
Modifica renderer.py per scale, palette, terra, ombra, debug demansionato. Questa è la BASE su cui gli altri layer si costruiscono.

**Checklist:**
- [ ] scale_px: 78 → 155 (riga 39)
- [ ] BLACK silhouette: (30,30,40) → (70,70,90) in silhouette.py
- [ ] Palette nemico: (180,60,60) → #8B2D2D
- [ ] Palette testo: (255,255,255) → #CCCCCC
- [ ] Palette HP: (80,220,80) → #64C864
- [ ] Terra: linea #8B6F47 at 80% height, h=5px
- [ ] Ombra: ellittica radial gradient sotto piedi
- [ ] Debug demansionato: inset 200×300 top-left, 50% opacity, flag toggle

**File:**
- mac/renderer.py
- mac/silhouette.py

**Dipende:** nessuno  
**Produce:** versione BASE guardabile  
**Costo:** ~2 ore, ~60 righe  

---

### T-002: Disegna sfondo carta + grana in renderer.py

**Descrizione:**
Aggiungi QLinearGradient per il fondo carta e bake la grana texture. Questo layer è immediatamente visibile e produce il 40% dell'estetica SUMI.

**Checklist:**
- [ ] QLinearGradient #EFE6D6→#D6C7AC, fillRect paintEvent inizio
- [ ] Bake grana: numpy seed=7, 256×256, QImage Grayscale8
- [ ] Disegna grana con setCompositionMode(Multiply), setOpacity(0.06)
- [ ] Verifica tiling visuale (tessuto o artefatti?)
- [ ] Smoke test: grana non è rumorosa a movimento veloce?

**File:**
- mac/renderer.py

**Dipende:** T-001  
**Produce:** versione SUMI base senza effetti  
**Costo:** ~1 ora, ~30 righe  

---

### T-003: Aggiungi collo e tweak silhouette.py

**Descrizione:**
Chiudi il buco fra testa e spalle disegnando un collo. Update BLACK color a #1B1A19 per match della palette.

**Checklist:**
- [ ] Update BLACK = QColor(0x1B, 0x1A, 0x19) in silhouette.py
- [ ] Disegna collo: QPen RoundCap fra neck_base (centro spalle) e neck_top (base testa)
- [ ] Larghezza collo: torso × 0.08
- [ ] Smoke test: collo è ben proporzionato? Testa galleggia ancora?

**File:**
- mac/silhouette.py

**Dipende:** T-002  
**Produce:** silhouette leggibile con collo  
**Costo:** ~45 min, ~15 righe  

---

### T-004: Crea impact_effects.py

**Descrizione:**
Nuovo file standalone con API per gli effetti d'impatto: hitstop, flash, shake, ink splash, afterimage. Gestione state con ringbuffer e decay per frame.

**Checklist:**
- [ ] Classe ImpactEffect con metodi: hitstop(), flash_white(), screen_shake(), ink_splash(), afterimage_ring()
- [ ] Ringbuffer per events, decay basato su dt (millisecondi)
- [ ] Gocce di inchiostro: lista di (x, y, r, creation_time, decay_ms)
- [ ] Afterimage: ring buffer di pose con history ~350ms
- [ ] Nessuna dipendenza da renderer.py o main_spike_visual.py (standalone)

**File:**
- mac/impact_effects.py (nuovo)

**Dipende:** nessuno  
**Produce:** API per effetti (non renderizzati ancora)  
**Costo:** ~1.5 ore, ~120 righe  

---

### T-005: Integra timer 60Hz e effects loop in main_spike_visual.py

**Descrizione:**
Aggiungi QTimer(16ms) per effetti. Mantieni HitEvent queue, converti in ImpactEffect, aggiorna ringbuffer pose per afterimage.

**Checklist:**
- [ ] QTimer(16ms) che chiama tick_effects(dt)
- [ ] Leggi HitEvent da combat.last_events quando emission
- [ ] Converti HitEvent.joint + speed → ImpactEffect.hitstop + ink_splash
- [ ] Ringbuffer pose: append nuova pose ogni frame, discard >350ms
- [ ] Verifica ringbuffer non esplode in memoria

**File:**
- mac/main_spike_visual.py

**Dipende:** T-001, T-002, T-003, T-004  
**Produce:** loop 60Hz attivo, effetti sparano ma no rendering  
**Costo:** ~1 ora, ~60 righe  

---

### T-006: Disegna effetti in renderer.py.paintEvent

**Descrizione:**
Aggiungi passate di disegno per afterimage, ink splash, screen shake, lampo bianco. Questo layer rende visibili gli effetti sul display.

**Checklist:**
- [ ] Afterimage: loop pose[-6/-4/-2], disegna rig con alpha 55/35/18%
- [ ] Ink splash: loop gocce, disegna cerchi neri con alpha decadimento
- [ ] Screen shake: painter.translate(shake_x, shake_y) all'inizio paintEvent
- [ ] Flash bianco: drawRect full-screen con QColor(255,255,255,alpha) se active
- [ ] Ordine: terra → nemico → avatar → afterimage → splash → flash → testo
- [ ] Verifica QPainterPath.simplified() cost (8-15ms?), fallback a drawLine RoundCap se >12ms

**File:**
- mac/renderer.py

**Dipende:** T-005  
**Produce:** effetti visibili sul display  
**Costo:** ~1.5 ore, ~60 righe  

---

### T-007: Smoke test e tuning

**Descrizione:**
Renderizza 8 frame reali con effetti accesi (traccia visiva_live.trace, frame scelti come nel test). Verifica visibilità, performance, nessun crash. Tuning numeri.

**Checklist:**
- [ ] Renderizza stessa traccia + frames del test decisivo
- [ ] Hitstop 60ms legge come "congelamento" senza lag?
- [ ] Afterimage offusca il corpo principale?
- [ ] Grana carta non rumorosa a movimento veloce?
- [ ] Ringbuffer storico non crash?
- [ ] FPS stabile 17fps + 60Hz effetti?
- [ ] Se QPainterPath.simplified() >12ms, switch a drawLine RoundCap
- [ ] Tuning numeri: hitstop_ms, alpha_list, shake_distance, grana opacity, afterimage decay

**File:**
- mac/renderer.py, mac/main_spike_visual.py, mac/impact_effects.py

**Dipende:** T-006  
**Produce:** versione SUMI "pronta per il gioco"  
**Costo:** ~1 ora (no codice, tuning costanti)  

---

### T-008: Integra controlli in main_spike_visual.py

**Descrizione:**
Aggiungi hotkey per debug toggle, vocabolario toggle, calibrazione nemico. Rendi main_spike_visual.py giocabile con SUMI.

**Checklist:**
- [ ] Tasto D = toggle debug (inset on/off)
- [ ] Tasto V = toggle vocabolario effetti (isolati o insieme?)
- [ ] Tasto C = calibra nemico (posiziona dove il giocatore lo vede)
- [ ] Verifica hotkey non conflitto con altri (R reset HP, S silhouette, etc.)
- [ ] Loggare azioni per debug

**File:**
- mac/main_spike_visual.py, mac/renderer.py

**Dipende:** T-007  
**Produce:** main_spike_visual.py giocabile con SUMI + effetti + controlli  
**Costo:** ~45 min, ~30 righe  

---

## Dipendenze e sequenza

```
T-004 (standalone)
  |
  T-001 → T-002 → T-003 ┐
                        ├→ T-005 → T-006 → T-007 → T-008
                        (no blocchi, lineare)
```

**Path critico:** T-001 → T-002 → T-003 → T-005 → T-006 → T-007 → T-008  
**Durata:** ~9 giorni / ~10-12 ore lavoro concentrato = 2-3 giorni reali a 4h/day

---

## Decisioni aperte

1. **Afterimage retroattiva (pose[-4/-3/-2]) vs. prospettica?**
   - Dichiarato: retroattiva per semplicità

2. **Grana 256×256 tiling visibile a 1000×600?**
   - Dichiarato: riusato, switch a 512×512 se artefatti

3. **Hitstop 60ms visibile a 17fps è acceptable?**
   - Dichiarato: sì, trade-off fra impatto e semplicità. Testabile in T-007.

4. **Vocabolario d'impatto completo o aggiungere dopo?**
   - Dichiarato: completo come scritto. Altro = PLAN futuro.

---

## Note di implementazione

- `test_visual_base.py` del test decisivo è un prototipo — usalo come reference per T-002.
- SilhouetteRig non modifica lo stato durante draw — è pure. OK.
- RingBuffer di pose: `from collections import deque; poses = deque(maxlen=20)` è sufficiente (350ms / 17fps ≈ 6 frame).
- Hitstop è uno "stop" della posa corrente; non è un freeze completo — il prossimo frame UDP arriva e sposta subito.
- Grana baked significa QImage calcolata una volta a init e riusata. Cost zero per frame.

---

## Exit criteria

Piano completato quando:
- [ ] main_spike_visual.py lancia senza crash
- [ ] 8 frame dalla traccia visiva_live.trace rendono in SUMI con tutti gli effetti
- [ ] Hitstop + lampo + scossa sono temporizzati e visibili
- [ ] Afterimage non causa lag e non è offuscante
- [ ] Nessuna regressione su jitter_buffer, combat, leg_tracker
