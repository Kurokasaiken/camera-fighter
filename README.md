# Camera Fighter — Fase 1 Prototipo

Gioco picchiaduro 2D controllato con la camera del telefono.

## Architettura

- **Android**: Kotlin + CameraX + ML Kit Pose. Invia landmark via UDP in MessagePack.
- **Mac**: Python + Pygame. Riceve landmark, classifica i gesti, mostra lo scheletro.

## Mosse iniziali

- Pugno destro
- Pugno sinistro
- Calcio destro
- Parata
- Schivata

## Setup rapido

1. Apri `android/` in Android Studio.
2. Configura l'indirizzo IP del Mac in `MainActivity.kt`.
3. Esegui l'app Android e metti il telefono in orizzontale di lato.
4. Avvia `mac/receiver.py` sul Mac.
