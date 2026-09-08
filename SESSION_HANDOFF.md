# Session Handoff — Camera Fighter

## Sessione
- Data: 2026-08-24
- Agente: Devin / Claude
- Repository: `/Users/faustoboni/progetti_personali/camera-fighter`

## Cosa è stato fatto

1. Installato Mind Weaver nel progetto `camera-fighter` via `install.sh`.
2. Esplorato e implementato un prototipo di **avatar 2D controllato dai landmark** ML Kit/MediaPipe.
3. Scartato l'approccio **riconoscimento gesti** (pugni/calci) per eccessivi falsi positivi e ambiguità in vista laterale.
4. Creato pipeline di tracking: `UDP → LandmarkFrame → OneEuroFilter → AvatarPose → PySide6 Renderer`.
5. Implementati file principali:
   - `mac/main_avatar_v2.py` — main con scheletro grezzo a sinistra, avatar filtrato a destra.
   - `mac/main_raw.py` — scheletro grezzo semplice.
   - `mac/pose_mapper.py` — mappatura 33 landmark → `AvatarPose`, centrato, normalizzato, ruotato.
   - `mac/landmark_filter.py` — gestione confidence/occlusioni.
   - `mac/one_euro.py` — One Euro Filter.
   - `mac/avatar_pose.py` — dataclass `AvatarPose`.
   - `mac/renderer.py` — rendering PySide6.
6. Catturati pattern in `mind-weaver/.mw/runs/20260824-camera-fighter-avatar/pattern-candidate.md`.

## Stato attuale

- L'avatar si muove seguendo i landmark, ma necessita di calibrazione e tuning.
- Pygame non funziona con Python 3.14 Homebrew; PySide6 è il renderer attivo.
- Il nemico rettangolo rosso perde HP quando le hitbox gialle di mani/piedi lo toccano.
- Problemi residui: zoom, inclinazione, mirror da tarare sulle movimenti reali.

## File rilevanti

- `mac/main_avatar_v2.py` — entry point attuale.
- `mac/main_raw.py` — debug scheletro grezzo.
- `mac/pose_mapper.py` — mapping + rotazione.
- `mac/renderer.py` — finestra affiancata.
- `mac/one_euro.py`, `mac/avatar_pose.py`, `mac/landmark_filter.py` — pipeline.
- `mac/motion_controller.py`, `mac/main.py`, `mac/visualizer.py` — vecchie versioni.

## Prossimi passi consigliati

1. Tarare `One Euro Filter` (`min_cutoff`, `beta`) sui dati reali.
2. Verificare e correggere mirror/zoom/inclinazione con movimenti reali.
3. Aggiungere calibrazione iniziale (stance) e scelta di guardia.
4. Sostituire il nemico statico con un avversario o bot.
5. Aggiungere sprite sopra lo scheletro quando il tracking è stabile.

## Note

- Non modificare `CANON.md` senza approvazione esplicita del Director.
- Il progetto ora usa il protocollo Mind Weaver.
