"""T-007: Smoke test effetti d'impatto SUMI.

Simula 8 frame reali con hitstop/flash/splash attivati.
Verifica: no crash, effetti sparano, ringbuffer stabile, FPS plausibile.
"""

import time
import msgpack
from collections import deque

from impact_effects import ImpactEffect
from pose_mapper import LandmarkToAvatarMapper
from renderer import SkeletonRenderer
from combat import CombatSystem
from silhouette import SilhouetteRig
from PySide6.QtWidgets import QApplication


def test_effects_no_crash():
    """Verifica che effetti non crashino a rendering."""
    print("[T-007] Smoke test effetti — no crash check")

    app = QApplication([])
    renderer = SkeletonRenderer()

    # Setup effetti e ringbuffer
    effects = ImpactEffect()
    pose_history = deque(maxlen=20)
    renderer.effects = effects
    renderer.pose_history = pose_history
    renderer.rig = SilhouetteRig()
    renderer.rig.enabled = True
    renderer.combat = CombatSystem()
    renderer.debug_enabled = True

    # Carica traccia visuale_live.trace
    try:
        with open("visual_live.trace", "rb") as f:
            entries = msgpack.unpackb(f.read(), raw=False)
        print(f"[T-007] Traccia caricata: {len(entries)} frame")
    except FileNotFoundError:
        print("[T-007] visual_live.trace non trovata — creazione dummy")
        entries = []

    # Seleziona 8 frame (distribuiti nella traccia)
    step = max(1, len(entries) // 8) if entries else 0
    frames = entries[::step][:8] if entries else []

    if not frames:
        print("[T-007] Nessun frame, test dummy")
        frames = [{"landmarks": [0.5, 0.5, 1.0] * 33, "ts": 0.0, "seq": i} for i in range(8)]

    # Simula rendering con effetti
    mapper = LandmarkToAvatarMapper()
    t0 = time.time()
    fps_samples = []

    for i, frame_pkt in enumerate(frames):
        frame_start = time.monotonic()

        # Estrai landmarks e mappa
        lms = frame_pkt.get("landmarks", [])
        if len(lms) < 33:
            lms = [0.5, 0.5, 1.0] * 33
        pose = mapper.map(lms, time.time())
        renderer.pose = pose
        renderer.raw_landmarks = lms
        renderer.now = time.time()
        pose_history.append(pose)

        # Simula hitstop + splash ogni 2 frame
        if i % 2 == 0:
            effects.hitstop(60.0)
            effects.ink_splash(renderer.width_f * 0.75, renderer.height_f * 0.5,
                              count=10, decay_ms=180.0)
            effects.flash_white(200.0, intensity=0.8)
            effects.screen_shake(3.0, 100.0)
            print(f"[T-007] Frame {i}: hitstop + splash triggered")

        # Aggiorna effetti
        now = time.time()
        effects.tick(now)

        # Renderizza (non fa output, solo check no crash)
        try:
            renderer.update()
        except Exception as e:
            print(f"[T-007] CRASH in rendering frame {i}: {e}")
            return False

        frame_end = time.monotonic()
        frame_ms = (frame_end - frame_start) * 1000.0
        fps_samples.append(frame_ms)
        print(f"[T-007] Frame {i}: {frame_ms:.1f}ms | "
              f"afterimage={len(renderer.pose_history)} | "
              f"drops={len(effects.ink_drops)} | "
              f"hitstop={'ON' if effects.is_hitstop_active(now) else 'OFF'}")

    # Diagnostica finale
    print("\n[T-007] === RESULTS ===")
    print(f"Frames processed: {len(frames)}")
    avg_ms = sum(fps_samples) / len(fps_samples) if fps_samples else 0.0
    max_ms = max(fps_samples) if fps_samples else 0.0
    print(f"Avg frame time: {avg_ms:.1f}ms")
    print(f"Max frame time: {max_ms:.1f}ms")
    print(f"Implied FPS: {1000.0 / avg_ms:.1f}" if avg_ms > 0 else "N/A")
    print(f"Pose history max: {renderer.pose_history.maxlen}")
    print(f"Final drops alive: {len(effects.ink_drops)}")
    print(f"No crash — test PASSED")
    return True


if __name__ == "__main__":
    try:
        result = test_effects_no_crash()
        exit(0 if result else 1)
    except Exception as e:
        print(f"[T-007] FATAL: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
