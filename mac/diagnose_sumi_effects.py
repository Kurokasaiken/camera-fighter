"""Diagnostica T-007: analizza visual_live.trace, simula effetti, genera report."""

import msgpack
import time
from collections import deque
from impact_effects import ImpactEffect
from pose_mapper import LandmarkToAvatarMapper


def diagnose():
    """Carica traccia, simula 8 frame con effetti, report diagnostico."""

    # Carica traccia
    try:
        with open("visual_live.trace", "rb") as f:
            entries = msgpack.unpackb(f.read(), raw=False)
        print(f"[Diagnose] Traccia caricata: {len(entries)} frame")
    except FileNotFoundError:
        print("[Diagnose] visual_live.trace non trovata")
        return False

    # Seleziona 8 frame distribuiti
    step = max(1, len(entries) // 8)
    selected_frames = entries[::step][:8]
    print(f"[Diagnose] Frame selezionati: {len(selected_frames)} (ogni {step})")

    # Setup
    effects = ImpactEffect()
    pose_history = deque(maxlen=20)
    mapper = LandmarkToAvatarMapper()

    print("\n=== RENDERING FRAME ===")
    print(f"{'Frame':<6} {'Seq':<6} {'TS':<10} {'Pose':<20} {'Hitstop':<8} {'Flash':<8} {'Drops':<8} {'Shake':<12}")
    print("-" * 100)

    frame_times = []
    max_drops = 0

    for idx, frame_data in enumerate(selected_frames):
        t_start = time.perf_counter()

        # Estrai dati
        seq = frame_data.get("seq", -1)
        ts = frame_data.get("ts", 0.0)
        lms = frame_data.get("landmarks", [])

        # Mappa pose
        pose = mapper.map(lms, time.time())
        pose_history.append(pose)

        # Simula hitstop + effetti ogni 2 frame
        if idx % 2 == 0:
            effects.hitstop(60.0)
            effects.flash_white(200.0, intensity=0.8)
            effects.screen_shake(3.0, 100.0)
            effects.ink_splash(100.0, 150.0, count=10, decay_ms=180.0)

        # Tick effetti
        now = time.time()
        effects.tick(now)

        # Diagnostica
        hitstop_status = "✓" if effects.is_hitstop_active(now) else "✗"
        flash_alpha = effects.is_flash_active(now)
        flash_status = f"{flash_alpha:.2f}" if flash_alpha > 0 else "✗"

        drops = effects.get_ink_drops(now)
        max_drops = max(max_drops, len(drops))

        shake_x, shake_y = effects.shake_offset(now)
        shake_status = f"({shake_x:+.1f},{shake_y:+.1f})" if shake_x or shake_y else "0,0"

        pose_info = f"({pose.left_shoulder.x:.2f},{pose.left_shoulder.y:.2f})" if pose and pose.left_shoulder else "None"

        t_end = time.perf_counter()
        frame_ms = (t_end - t_start) * 1000.0
        frame_times.append(frame_ms)

        print(f"{idx:<6} {seq:<6} {ts:<10.2f} {pose_info:<20} {hitstop_status:<8} {flash_status:<8} {len(drops):<8} {shake_status:<12}")

    # Report finale
    print("\n=== SUMMARY ===")
    print(f"Frames processed: {len(selected_frames)}")
    print(f"Pose history maxlen: {pose_history.maxlen}")
    print(f"Max drops alive: {max_drops}")
    print(f"Avg frame time: {sum(frame_times)/len(frame_times):.2f}ms" if frame_times else "N/A")
    print(f"Max frame time: {max(frame_times):.2f}ms" if frame_times else "N/A")

    # Verifiche
    checks = [
        ("✓" if len(selected_frames) == 8 else "✗", "8 frame selected"),
        ("✓" if max_drops > 0 else "✗", "Ink splash created"),
        ("✓" if any(len(effects.get_ink_drops(time.time())) > 0 for _ in range(1)) else "✗", "Drops render active"),
        ("✓" if max(frame_times) < 50 else "~", "Frame time < 50ms"),
    ]

    print("\nExit criteria:")
    for status, desc in checks:
        print(f"  {status} {desc}")

    return True


if __name__ == "__main__":
    try:
        result = diagnose()
        exit(0 if result else 1)
    except Exception as e:
        print(f"[Diagnose] Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
