"""The frame loop: camera → segmentation → transition effect → virtual camera.

All public methods are thread-safe: they only enqueue commands that the worker thread
applies between frames. Callbacks (on_frame, on_status, on_log) run on the worker thread.
"""
import math
import queue
import threading
import time
import traceback
from dataclasses import dataclass, replace
from typing import Callable

import cv2
import numpy as np

from snap import effects
from snap.core.plate import PlateBuilder
from snap.core.segmenter import hide_mask
from snap.core.transition import Transition
from snap.effects.base import EffectContext


@dataclass
class Status:
    running: bool = False
    mode: str = "stopped"          # stopped | live | vanishing | gone | appearing
    has_plate: bool = False
    countdown: int = 0             # seconds left before the room is captured; 0 = none
    capturing: bool = False
    fps: float = 0.0
    vcam_name: str = ""
    effect: str = ""
    snap_enabled: bool = True
    mic_ok: bool = False
    mic_level: float = 0.0


@dataclass
class EngineConfig:
    source_factory: Callable
    output_factory: Callable       # (width, height, fps) -> VirtualOutput
    segmenter_factory: Callable    # () -> object with mask(frame, ts_ms) and close()
    mic_factory: Callable | None = None   # (device, sensitivity, on_snap) -> MicListener
    mic_device: int | None = None
    sensitivity: float = 6.0
    snap_enabled: bool = True
    effect: str = effects.DEFAULT_ID
    duration: float = 2.0
    fps: int = 30
    preview: bool = True


class Engine:
    COUNTDOWN_S = 3.0
    HOLD_S = 1.0           # how long "Try" stays gone before coming back
    PREVIEW_WIDTH = 640
    STATUS_EVERY_S = 0.1

    def __init__(self, on_frame=None, on_status=None, on_log=None):
        self.on_frame = on_frame or (lambda rgb: None)
        self.on_status = on_status or (lambda st: None)
        self.on_log = on_log or (lambda key, kw: None)
        self._commands: queue.Queue = queue.Queue()
        self._thread = None
        self._stop = threading.Event()
        self._status = Status()
        self._lock = threading.Lock()
        self.plate = None
        self.mic = None

    # ------------------------------------------------------------ public API
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> Status:
        with self._lock:
            return replace(self._status)

    def start(self, cfg: EngineConfig) -> None:
        if self.running:
            return
        self.cfg = cfg
        source = cfg.source_factory()
        size = source.open()
        output = segmenter = None
        try:
            output = cfg.output_factory(size[0], size[1], cfg.fps)
            segmenter = cfg.segmenter_factory()
        except BaseException:
            for thing in (output, source):
                if thing is not None:
                    try:
                        thing.close()
                    except Exception:
                        pass
            raise
        self.source, self.output, self.segmenter, self.size = source, output, segmenter, size
        self.plate = None
        self._rng = np.random.default_rng()
        self._effect_id = cfg.effect
        self._duration = cfg.duration
        self._preview = cfg.preview
        self._snap_enabled = cfg.snap_enabled
        self._sensitivity = cfg.sensitivity
        self._mode = "live"
        self._transition = None
        self._auto_return_at = None
        self._countdown_end = None
        self._plate_builder = None
        self._plate_job = None
        self._commands = queue.Queue()
        self._start_mic(cfg.mic_device)
        self._set_status(running=True, mode="live", has_plate=False, countdown=0, capturing=False,
                         vcam_name=getattr(output, "name", ""), effect=cfg.effect,
                         snap_enabled=cfg.snap_enabled)
        self.on_log("log.started", {"name": getattr(output, "name", "")})
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="snap-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=5)

    def toggle(self) -> None:
        self._commands.put(("toggle",))

    def capture_plate(self) -> None:
        self._commands.put(("capture",))

    def try_effect(self) -> None:
        self._commands.put(("try",))

    def set_effect(self, effect_id: str) -> None:
        self._commands.put(("effect", effect_id))

    def set_duration(self, seconds: float) -> None:
        self._commands.put(("duration", float(seconds)))

    def set_preview(self, enabled: bool) -> None:
        self._commands.put(("preview", bool(enabled)))

    def set_snap_enabled(self, enabled: bool) -> None:
        self._commands.put(("snap", bool(enabled)))

    def set_sensitivity(self, value: float) -> None:
        self._commands.put(("sensitivity", float(value)))

    def set_mic(self, device: int | None) -> None:
        self._commands.put(("mic", device))

    # ------------------------------------------------------------ mic
    def _on_snap(self) -> None:
        if self._snap_enabled:
            self.toggle()

    def _start_mic(self, device) -> None:
        self._stop_mic()
        factory = self.cfg.mic_factory
        if factory is None:
            self._set_status(mic_ok=False)
            return
        try:
            mic = factory(device, self._sensitivity, self._on_snap)
            mic.start()
            self.mic = mic
            self._set_status(mic_ok=True)
            self.on_log("log.mic_ok", {})
        except Exception as e:
            self.mic = None
            self._set_status(mic_ok=False)
            self.on_log("log.mic_failed", {"error": str(e)})

    def _stop_mic(self) -> None:
        if self.mic is not None:
            try:
                self.mic.stop()
            except Exception:
                pass
            self.mic = None

    # ------------------------------------------------------------ worker
    def _set_status(self, **changes) -> None:
        with self._lock:
            for k, v in changes.items():
                setattr(self._status, k, v)

    def _publish(self) -> None:
        self.on_status(self.status())

    def _run(self) -> None:
        period = 1.0 / max(1, self.cfg.fps)
        t0 = time.monotonic()
        next_t = t0
        last_status = 0.0
        frame_times = []
        misses = 0
        try:
            while not self._stop.is_set():
                frame = self.source.read()
                now = time.monotonic()
                if frame is None:
                    misses += 1
                    if misses > 150:
                        raise RuntimeError("camera stopped delivering frames")
                    time.sleep(0.01)
                    continue
                misses = 0
                self._frame = frame
                self._mask = None
                self._ts_ms = int((now - t0) * 1000)

                self._drain_commands(now)
                self._update_capture(now)
                out = self._render(now)
                self.output.send(out)

                frame_times.append(now)
                frame_times = frame_times[-30:]
                if self._preview and len(frame_times) % 2 == 0:
                    self._send_preview(out)
                if now - last_status >= self.STATUS_EVERY_S:
                    last_status = now
                    fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0]) if len(frame_times) > 1 else 0.0
                    self._set_status(fps=round(fps, 1), mic_level=self.mic.level if self.mic else 0.0)
                    self._publish()

                next_t += period
                delay = next_t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.monotonic()
        except Exception as e:
            self.on_log("log.engine_error", {"error": str(e), "trace": traceback.format_exc()})
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self._stop_mic()
        for thing in (self.segmenter, self.output, self.source):
            try:
                thing.close()
            except Exception:
                pass
        self._set_status(running=False, mode="stopped", countdown=0, capturing=False, fps=0.0,
                         mic_ok=False, mic_level=0.0)
        self._publish()
        self.on_log("log.stopped", {})

    # ------------------------------------------------------------ per-frame pieces
    def _person_mask(self) -> np.ndarray:
        if self._mask is None:
            self._mask = self.segmenter.mask(self._frame, self._ts_ms)
        return self._mask

    def _drain_commands(self, now: float) -> None:
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                break
            name = cmd[0]
            if name == "toggle":
                self._auto_return_at = None           # a manual toggle cancels "Try"
                self._toggle(now)
            elif name == "try":
                if self._mode == "live" and self._toggle(now):
                    self._auto_return_at = -1.0     # set once "gone" is reached
            elif name == "capture":
                self._begin_capture(now)
            elif name == "effect":
                self._effect_id = cmd[1]
                if self._transition is None and self._mode == "live":
                    self._set_status(effect=cmd[1])
            elif name == "duration":
                self._duration = cmd[1]
            elif name == "preview":
                self._preview = cmd[1]
            elif name == "snap":
                self._snap_enabled = cmd[1]
                self._set_status(snap_enabled=cmd[1])
            elif name == "sensitivity":
                self._sensitivity = cmd[1]
                if self.mic is not None:
                    self.mic.set_sensitivity(cmd[1])
            elif name == "mic":
                self._start_mic(cmd[1])

    def _toggle(self, now: float) -> bool:
        if self._mode in ("vanishing", "appearing"):
            self.on_log("log.busy", {})
            return False
        if self.plate is None or self.plate.shape[:2] != self._frame.shape[:2]:
            self.on_log("log.need_plate", {})
            return False
        vanish = self._mode == "live"
        if vanish:
            self._current_id = effects.resolve_effect(self._effect_id, self._rng)
        effect = effects.get_effect(self._current_id)
        hide = hide_mask(self._person_mask())
        effect.prepare(EffectContext(frame=self._frame, mask=hide, plate=self.plate,
                                     seed=int(self._rng.integers(1 << 30))))
        self._transition = Transition(effect, self._current_id, self._duration, vanish, now)
        self._mode = "vanishing" if vanish else "appearing"
        self._set_status(mode=self._mode, effect=self._current_id)
        self._publish()
        return True

    def _render(self, now: float) -> np.ndarray:
        tr = self._transition
        if tr is not None:
            p = tr.p(now)
            out = tr.effect.apply(self._frame, hide_mask(self._person_mask()), self.plate, p)
            if tr.done(now):
                self._transition = None
                self._mode = "gone" if tr.vanish else "live"
                if self._mode == "gone" and self._auto_return_at == -1.0:
                    self._auto_return_at = now + self.HOLD_S
                if self._mode == "live":
                    self._set_status(effect=self._effect_id)
                self._set_status(mode=self._mode)
                self._publish()
            return out
        if self._mode == "gone":
            if self._auto_return_at is not None and self._auto_return_at > 0 and now >= self._auto_return_at:
                self._auto_return_at = None
                self._toggle(now)
            return self.plate
        return self._frame

    # ------------------------------------------------------------ empty room capture
    def _begin_capture(self, now: float) -> None:
        if self._countdown_end is not None or self._plate_builder is not None or self._plate_job is not None:
            return
        if self._mode != "live":
            self.on_log("log.busy", {})
            return
        self._countdown_end = now + self.COUNTDOWN_S
        self._set_status(countdown=int(math.ceil(self.COUNTDOWN_S)), capturing=True)
        self._publish()

    def _update_capture(self, now: float) -> None:
        if self._countdown_end is not None:
            left = self._countdown_end - now
            if left > 0:
                n = int(math.ceil(left))
                if n != self._status.countdown:
                    self._set_status(countdown=n)
                    self._publish()
                return
            self._countdown_end = None
            self._plate_builder = PlateBuilder()
            self._set_status(countdown=0)
            self._publish()
        if self._plate_builder is not None:
            self._plate_builder.add(self._frame, self._person_mask())
            if self._plate_builder.done:
                builder, self._plate_builder = self._plate_builder, None
                self._plate_job = threading.Thread(target=self._build_plate, args=(builder,), daemon=True)
                self._plate_job.start()

    def _build_plate(self, builder: PlateBuilder) -> None:
        plate = builder.build()
        if plate is None:
            self.on_log("log.plate_person", {})
        else:
            self.plate = plate
            self.on_log("log.plate_ok", {})
        self._set_status(has_plate=self.plate is not None, capturing=False)
        self._plate_job = None
        self._publish()

    # ------------------------------------------------------------ preview
    def _send_preview(self, out: np.ndarray) -> None:
        h, w = out.shape[:2]
        if w > self.PREVIEW_WIDTH:
            out = cv2.resize(out, (self.PREVIEW_WIDTH, int(h * self.PREVIEW_WIDTH / w)),
                             interpolation=cv2.INTER_AREA)
        self.on_frame(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
