"""Finger-snap detection.

A snap is a sudden, bright (2-9 kHz) burst that dies away within a few tens of
milliseconds. We look for spikes of spectral flux in that band above an adaptive
threshold, then confirm the spike by checking that the band energy really falls off
quickly afterwards, which rules out speech, music and other sustained sounds.
"""
from collections import deque
from typing import Callable

import numpy as np

FFT = 1024
HOP = 256
BAND = (2000.0, 9000.0)
HISTORY_S = 1.5
DECAY_DB = 10.0
MIN_RISE_DB = 6.0         # the burst must stand this far above the background
BG_MARGIN_DB = 3.0        # or it counts as decayed once back within this of the background
DECAY_WINDOW_S = 0.12
PEAK_FRAMES = 3           # frames after the onset in which the burst may still be growing
REFRACTORY_S = 1.5
FLUX_FLOOR = 0.3
LEVEL_FLOOR = 0.006       # band RMS a snap must reach at sensitivity 1


class SnapAnalyzer:
    def __init__(self, samplerate: int, sensitivity: float = 6.0):
        self.sr = int(samplerate)
        self.window = np.hanning(FFT).astype(np.float32)
        freqs = np.fft.rfftfreq(FFT, 1.0 / self.sr)
        self.band = (freqs >= BAND[0]) & (freqs <= BAND[1])
        self.norm = 2.0 / (FFT * float(np.sum(self.window ** 2)))
        self.hop_s = HOP / self.sr
        self.set_sensitivity(sensitivity)
        self.reset()

    def set_sensitivity(self, value: float) -> None:
        s = float(min(10.0, max(1.0, value)))
        self.sensitivity = s
        self.k = 14.0 - (s - 1.0) * (11.0 / 9.0)
        self.level_floor = LEVEL_FLOOR * (0.72 ** (s - 1.0))
        self.flux_floor = FLUX_FLOOR * (0.8 ** (s - 1.0))

    def reset(self) -> None:
        self.buf = np.zeros(0, np.float32)
        self.frame_idx = 0
        self.prev_log = None
        n = max(8, int(HISTORY_S / (HOP / self.sr)))
        self.history = deque(maxlen=n)
        self.db_history = deque(maxlen=n)
        self.candidate = None      # (onset_time, peak_db, background_db, frames_seen)
        self.last_snap = -1e9
        self.level = 0.0

    # ------------------------------------------------------------ streaming
    def feed(self, block: np.ndarray) -> list[float]:
        """Feed mono samples; returns stream times (s) of confirmed snaps."""
        block = np.asarray(block, dtype=np.float32).ravel()
        self.buf = np.concatenate([self.buf, block])
        hits = []
        while len(self.buf) >= FFT:
            frame = self.buf[:FFT]
            self.buf = self.buf[HOP:]
            t = (self.frame_idx * HOP + FFT / 2) / self.sr
            self.frame_idx += 1
            hit = self._frame(frame, t)
            if hit is not None:
                hits.append(hit)
        return hits

    def _frame(self, frame: np.ndarray, t: float):
        spec = np.abs(np.fft.rfft(frame * self.window))[self.band]
        rms = float(np.sqrt(np.sum(spec ** 2) * self.norm))
        db = 20.0 * np.log10(rms + 1e-9)
        logmag = np.log1p(100.0 * spec)
        flux = 0.0 if self.prev_log is None else float(np.mean(np.maximum(0.0, logmag - self.prev_log)))
        self.prev_log = logmag

        thr = self._threshold()
        bg = float(np.median(np.fromiter(self.db_history, np.float32))) if self.db_history else db
        self.history.append(flux)
        self.db_history.append(db)
        self.level = max(flux / thr * 0.7, self.level * 0.85)

        if self.candidate is not None:
            onset, peak_db, bg0, seen = self.candidate
            seen += 1
            if seen <= PEAK_FRAMES:
                peak_db = max(peak_db, db)
            self.candidate = (onset, peak_db, bg0, seen)
            decayed = db <= max(peak_db - DECAY_DB, bg0 + BG_MARGIN_DB)
            if seen > PEAK_FRAMES and decayed and peak_db - bg0 >= MIN_RISE_DB:
                self.candidate = None
                self.last_snap = onset
                return onset
            if t - onset > DECAY_WINDOW_S:
                self.candidate = None          # sustained sound, not a snap
            return None

        if (flux > thr and rms > self.level_floor
                and t - self.last_snap > REFRACTORY_S):
            self.candidate = (t, db, bg, 0)
        return None

    def _threshold(self) -> float:
        if len(self.history) < 4:
            return self.flux_floor * 3
        h = np.fromiter(self.history, np.float32)
        med = float(np.median(h))
        mad = float(np.median(np.abs(h - med)))
        return med + self.k * 1.4826 * mad + self.flux_floor


class MicListener:
    """Feeds a microphone into a SnapAnalyzer; calls on_snap from the audio thread."""

    def __init__(self, device: int | None, sensitivity: float, on_snap: Callable[[], None]):
        self.device = device
        self.on_snap = on_snap
        self._sensitivity = sensitivity
        self.analyzer = None
        self.stream = None

    @property
    def running(self) -> bool:
        return self.stream is not None

    @property
    def level(self) -> float:
        return self.analyzer.level if self.analyzer else 0.0

    def set_sensitivity(self, value: float) -> None:
        self._sensitivity = value
        if self.analyzer:
            self.analyzer.set_sensitivity(value)

    def start(self) -> None:
        import sounddevice as sd
        self.stop()
        info = sd.query_devices(self.device, "input")
        sr = int(info["default_samplerate"])
        self.analyzer = SnapAnalyzer(sr, self._sensitivity)

        def callback(indata, frames, time_info, status):
            if self.analyzer.feed(indata[:, 0]):
                try:
                    self.on_snap()
                except Exception:
                    pass

        try:
            stream = sd.InputStream(samplerate=sr, blocksize=HOP, channels=1, dtype="float32",
                                    device=self.device, callback=callback)
        except Exception:
            # some WASAPI endpoints only open with their native channel count
            channels = max(1, int(info["max_input_channels"]))
            stream = sd.InputStream(samplerate=sr, blocksize=HOP, channels=channels, dtype="float32",
                                    device=self.device, callback=callback)
        stream.start()
        self.stream = stream

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
