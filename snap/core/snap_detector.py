"""Finger-snap detection.

A snap is a sudden, bright (2-9 kHz) burst that dies away within a few tens of
milliseconds. We look for spikes of spectral flux in that band above an adaptive
threshold, then confirm the spike by checking that
  * the band energy really falls off quickly afterwards (rules out sustained sounds), and
  * there is no voice around it: consonants such as t/k/p/ç also make short bright
    bursts, but speech always has a vowel right before or after them, which puts strong
    energy in the 80-900 Hz voice band. A snap has none.
"""
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

FFT = 1024
HOP = 256
BAND = (2000.0, 9000.0)
VOICE_BAND = (80.0, 900.0)
HISTORY_S = 1.5
DECAY_DB = 10.0
MIN_RISE_DB = 6.0         # the burst must stand this far above the background
BG_MARGIN_DB = 3.0        # or it counts as decayed once back within this of the background
DECAY_WINDOW_S = 0.12
PEAK_FRAMES = 3           # frames after the onset in which the burst may still be growing
VOICE_BEFORE_S = (0.25, 0.04)   # look for a vowel this long before the onset ...
VOICE_AFTER_S = (0.04, 0.15)    # ... and this long after it
VOICE_GAP_DB = 15.0       # voice counts when the voice band comes this close to the burst's peak
VOICE_RISE_DB = 10.0      # ... and rises this far above its own noise floor (steady hum/fans don't)
VOICE_FLOOR_S = 3.0       # window for that noise floor (10th percentile of the voice band)
REFRACTORY_S = 1.5
FLUX_FLOOR = 0.3
LEVEL_FLOOR = 0.006       # band RMS a snap must reach at sensitivity 1


@dataclass
class _Candidate:
    onset: float
    peak_db: float
    bg_db: float
    voice_db: float           # loudest voice-band frame around the onset so far
    voice_floor_db: float     # the voice band's noise floor when the burst started
    seen: int = 0
    decayed: bool = False


class SnapAnalyzer:
    def __init__(self, samplerate: int, sensitivity: float = 6.0):
        self.sr = int(samplerate)
        self.window = np.hanning(FFT).astype(np.float32)
        freqs = np.fft.rfftfreq(FFT, 1.0 / self.sr)
        self.band = (freqs >= BAND[0]) & (freqs <= BAND[1])
        self.voice_band = (freqs >= VOICE_BAND[0]) & (freqs <= VOICE_BAND[1])
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
        self.voice_history = deque(maxlen=int(VOICE_BEFORE_S[0] / (HOP / self.sr)) + 2)  # (t, voice_db)
        self.voice_floor = deque(maxlen=int(VOICE_FLOOR_S / (HOP / self.sr)))
        self.candidate: _Candidate | None = None
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

    def _band_db(self, full: np.ndarray, band: np.ndarray) -> float:
        rms = float(np.sqrt(np.sum(full[band] ** 2) * self.norm))
        return 20.0 * np.log10(rms + 1e-9)

    def _frame(self, frame: np.ndarray, t: float):
        full = np.abs(np.fft.rfft(frame * self.window))
        spec = full[self.band]
        db = self._band_db(full, self.band)
        voice_db = self._band_db(full, self.voice_band)
        logmag = np.log1p(100.0 * spec)
        flux = 0.0 if self.prev_log is None else float(np.mean(np.maximum(0.0, logmag - self.prev_log)))
        self.prev_log = logmag

        thr = self._threshold()
        bg = float(np.median(np.fromiter(self.db_history, np.float32))) if self.db_history else db
        self.history.append(flux)
        self.db_history.append(db)
        self.level = max(flux / thr * 0.7, self.level * 0.85)

        hit = None
        c = self.candidate
        if c is not None:
            hit = self._follow(c, t, db, voice_db)
        elif (flux > thr and 10 ** (db / 20) > self.level_floor
                and t - self.last_snap > REFRACTORY_S):
            before = [v for ft, v in self.voice_history
                      if t - VOICE_BEFORE_S[0] <= ft <= t - VOICE_BEFORE_S[1]]
            floor = float(np.percentile(np.fromiter(self.voice_floor, np.float32), 10))                 if self.voice_floor else voice_db
            self.candidate = _Candidate(t, db, bg, max(before, default=-200.0), floor)
        self.voice_history.append((t, voice_db))
        self.voice_floor.append(voice_db)
        return hit

    def _follow(self, c: _Candidate, t: float, db: float, voice_db: float):
        """Track a candidate burst; returns its onset time once it is confirmed as a snap."""
        c.seen += 1
        age = t - c.onset
        if c.seen <= PEAK_FRAMES:
            c.peak_db = max(c.peak_db, db)
        elif not c.decayed and age <= DECAY_WINDOW_S:
            c.decayed = db <= max(c.peak_db - DECAY_DB, c.bg_db + BG_MARGIN_DB)
        if VOICE_AFTER_S[0] <= age <= VOICE_AFTER_S[1]:
            c.voice_db = max(c.voice_db, voice_db)

        if age > DECAY_WINDOW_S and not c.decayed:
            self.candidate = None              # sustained sound, not a snap
        elif age >= VOICE_AFTER_S[1]:
            self.candidate = None
            voiced = c.voice_db > max(c.peak_db - VOICE_GAP_DB, c.voice_floor_db + VOICE_RISE_DB)
            if c.decayed and not voiced and c.peak_db - c.bg_db >= MIN_RISE_DB:
                self.last_snap = c.onset
                return c.onset
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
