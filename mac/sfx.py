"""Effetti sonori. Isolato dal rendering: chi colpisce chiama play(), basta."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

ASSETS = Path(__file__).parent / "assets"

# QSoundEffect tronca il suono se lo si riavvia mentre e' ancora in corso:
# con piu' istanze a rotazione due colpi ravvicinati si sentono entrambi.
VOICES = 4


class SoundBank:
    def __init__(self, volume=0.6):
        self._voices = {}
        self._next = {}
        self._volume = volume

    def load(self, name, filename):
        path = ASSETS / filename
        if not path.exists():
            print(f"[sfx] manca {path}, suono '{name}' disattivato", flush=True)
            return
        voices = []
        for _ in range(VOICES):
            e = QSoundEffect()
            e.setSource(QUrl.fromLocalFile(str(path)))
            e.setVolume(self._volume)
            voices.append(e)
        self._voices[name] = voices
        self._next[name] = 0

    def play(self, name):
        voices = self._voices.get(name)
        if not voices:
            return
        i = self._next[name]
        voices[i].play()
        self._next[name] = (i + 1) % len(voices)
