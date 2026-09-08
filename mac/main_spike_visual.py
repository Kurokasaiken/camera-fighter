"""Spike visuale — PLAN-048e T-001: doppio path display/detection.

DISPLAY path (bassa latenza): ogni pacchetto UDP aggiorna SUBITO scheletro
grezzo + avatar — niente jitter buffer. Quello che vedi e' quello che arriva.

DETECTION path (deterministico): UDP -> JitterBuffer -> Pipeline -> eventi
(motion/hit/commit) + combat/HP. Resta buffered e replay-compatibile.

Telemetria: arrival->render, arrival->emit, desync capture_ts, rete/coda.
Sinistra: scheletro grezzo. Destra: avatar filtrato + nemico + hitbox.
"""

from __future__ import annotations

import socket
import time

import msgpack
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from jitter_buffer import JitterBuffer
from pipeline import Pipeline
from combat import CombatSystem
from pose_mapper import LandmarkToAvatarMapper
from renderer import SkeletonRenderer
from telemetry import Telemetry

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
COMBOS = "combos.json"
TRACE = "visual_live.trace"


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    app = QApplication([])
    renderer = SkeletonRenderer()
    renderer.show()

    # due mapper separati: il filtro OneEuro e' stateful e i due path hanno
    # frequenze diverse — condividerlo corromperebbe entrambi.
    mapper_display = LandmarkToAvatarMapper()   # raw path
    mapper_detect = LandmarkToAvatarMapper()    # detection path (combat/HP)

    combat = CombatSystem()
    renderer.combat = combat
    # avatar: silhouette nera (LIMBO-style), tasto S = on/off
    try:
        from silhouette import SilhouetteRig
        renderer.rig = SilhouetteRig()
    except Exception as e:
        print(f"[visual] silhouette non caricata: {e}", flush=True)
    pipe = Pipeline(COMBOS)
    tel = Telemetry()
    entries = []
    banner = {"text": "", "until": 0.0}
    state = {"disp_seq": -1, "disp_cts": 0.0}

    def on_emit(ef):
        """DETECTION path: frame ordinato dal jitter buffer."""
        t_in = time.monotonic()
        out = pipe.process(ef)
        pkt = ef.frame if isinstance(ef.frame, dict) else {}
        lms = pkt.get("landmarks", [])
        pose = mapper_detect.map(lms, time.time())
        combat.update(pose)
        proc_ms = (time.monotonic() - t_in) * 1000.0
        tel.on_emit(ef.seq_id, ef.emit_ts, proc_ms,
                    float(pkt.get("ts", 0)))
        for m in out.motion_events:
            print(f"[MOTION] {m.action} {m.direction} v={m.peak_speed:.2f}",
                  flush=True)
        for h in out.hit_events:
            print(f"[HIT] {h.joint} v={h.speed}", flush=True)
        for c in out.commits:
            banner["text"] = f"COMBO: {c.combo_id}!"
            banner["until"] = time.time() + 1.2
            print(f"[COMMIT] {c.combo_id} score={c.score}", flush=True)

    def on_packet(pkt, arrival_mono):
        """DISPLAY path: latenza minima, nessun buffer."""
        lms = pkt.get("landmarks", [])
        renderer.raw_landmarks = lms
        pose = mapper_display.map(lms, time.time())
        renderer.pose = pose
        renderer.now = time.time()
        renderer.hit_marks = getattr(renderer, "hit_marks", [])
        renderer.update()
        render_mono = (time.monotonic() - t0) * 1000.0
        seq = pkt.get("seq", -1)
        cts = float(pkt.get("ts", 0))
        tel.on_render(seq, cts, render_mono)
        state["disp_seq"], state["disp_cts"] = seq, cts

    jb = JitterBuffer(on_emit=on_emit)
    t0 = time.monotonic()
    tel.start(t0)
    print(f"[visual] UDP :{UDP_PORT} — dual-path on, muoviti! "
          f"(chiudi finestra per stop)", flush=True)

    # tasto R = reset HP nemico al massimo
    orig_key = renderer.keyPressEvent
    def key_handler(ev):
        if ev.key() == Qt.Key_R:
            combat.reset()
            print("[visual] HP nemico resettati", flush=True)
        elif ev.key() == Qt.Key_S and renderer.rig is not None:
            renderer.rig.enabled = not renderer.rig.enabled
            print(f"[visual] sprite rig {'ON' if renderer.rig.enabled else 'OFF'}",
                  flush=True)
        else:
            orig_key(ev)
    renderer.keyPressEvent = key_handler

    while renderer.isVisible():
        app.processEvents()
        now_ms = (time.monotonic() - t0) * 1000.0
        drained = 0
        try:
            while True:
                data, _ = sock.recvfrom(65535)
                drained += 1
                pkt = msgpack.unpackb(data, raw=False)
                pkt.setdefault("valid", True)
                seq = pkt.get("seq", -1)
                entries.append({"arrival_ts": now_ms, "seq_id": seq,
                                "payload": pkt})
                # telemetria rete/coda: drained-1 = pacchetti ancora in coda
                tel.on_arrival(seq, float(pkt.get("ts", 0)), now_ms,
                               queue_depth=0)
                on_packet(pkt, now_ms)          # display: subito
                jb.process_frame(seq, pkt, now_ms)  # detection: buffered
        except BlockingIOError:
            pass
        # queue_depth reale = pacchetti accumulati nel socket prima del drain
        if drained:
            tel.queue_depths[-drained:] = [drained] * drained
        jb.tick(now_ms)

        if banner["text"] and time.time() < banner["until"]:
            renderer.setWindowTitle(f"Camera Fighter — {banner['text']}")
        else:
            renderer.setWindowTitle("Camera Fighter — Spike")

        time.sleep(0.005)

    if entries:
        with open(TRACE, "wb") as f:
            f.write(msgpack.packb(entries, use_bin_type=True))
        s = jb.stats
        print(f"[visual] trace -> {TRACE} | received={s.received} "
              f"reordered={s.reordered} dup={s.duplicates} late={s.late} "
              f"gaps={s.declared_gaps} epochs={s.epochs}", flush=True)
        print(tel.report(), flush=True)


if __name__ == "__main__":
    main()
