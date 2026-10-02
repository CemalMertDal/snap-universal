import threading
import time

import numpy as np
import pytest

from snap import effects
from snap.core.engine import Engine, EngineConfig
from snap.core.sources import SyntheticSource


class FakeOutput:
    name = "Fake Cam"

    def __init__(self, w, h, fps):
        self.size = (w, h)
        self.frames = []
        self.closed = False
        self.lock = threading.Lock()

    def send(self, frame):
        with self.lock:
            self.frames.append(frame.copy())
            del self.frames[:-5]

    def last(self):
        with self.lock:
            return self.frames[-1] if self.frames else None

    def close(self):
        self.closed = True


class FakeSegmenter:
    def __init__(self, source):
        self.source = source
        self.closed = False

    def mask(self, frame, ts_ms):
        return self.source.last_mask.copy()

    def close(self):
        self.closed = True


class Harness:
    def __init__(self, effect="cloud", **kw):
        self.source = SyntheticSource(320, 240)
        self.outputs = []
        self.logs = []
        self.statuses = []
        self.frames = 0

        def make_output(w, h, fps):
            out = FakeOutput(w, h, fps)
            self.outputs.append(out)
            return out

        self.cfg = EngineConfig(
            source_factory=lambda: self.source,
            output_factory=make_output,
            segmenter_factory=lambda: FakeSegmenter(self.source),
            mic_factory=None,
            effect=effect, duration=0.25, fps=60, **kw)
        self.engine = Engine(on_frame=self._frame, on_status=self.statuses.append,
                             on_log=lambda key, kw: self.logs.append(key))

    def _frame(self, rgb):
        self.frames += 1

    def wait(self, cond, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.01)
        raise AssertionError("timed out waiting")

    def mode(self):
        return self.engine.status().mode


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(Engine, "COUNTDOWN_S", 0.1)
    monkeypatch.setattr(Engine, "HOLD_S", 0.15)


@pytest.fixture
def h(fast):
    harness = Harness()
    yield harness
    harness.engine.stop()


def _capture(h):
    h.source.person = False
    h.engine.capture_plate()
    h.wait(lambda: "log.plate_ok" in h.logs)
    h.source.person = True


def test_start_streams_frames_and_previews(h):
    h.engine.start(h.cfg)
    assert h.engine.running
    h.wait(lambda: h.outputs and h.outputs[0].last() is not None)
    h.wait(lambda: h.frames > 2)
    st = h.engine.status()
    assert st.running and st.mode == "live" and st.vcam_name == "Fake Cam"
    assert h.outputs[0].size == (320, 240)


def test_toggle_without_plate_is_refused(h):
    h.engine.start(h.cfg)
    h.engine.toggle()
    h.wait(lambda: "log.need_plate" in h.logs)
    assert h.mode() == "live"


def test_plate_capture_works_with_someone_in_frame(h):
    h.engine.start(h.cfg)
    h.engine.capture_plate()                       # person stays visible the whole time
    h.wait(lambda: "log.plate_ok" in h.logs)
    assert h.engine.status().has_plate


def test_countdown_is_reported(h):
    h.engine.start(h.cfg)
    h.engine.capture_plate()
    h.wait(lambda: any(s.countdown > 0 for s in h.statuses))


def test_full_vanish_and_return_cycle(h):
    h.engine.start(h.cfg)
    _capture(h)
    assert h.engine.status().has_plate
    h.engine.toggle()
    h.wait(lambda: h.mode() == "vanishing")
    h.wait(lambda: h.mode() == "gone")
    time.sleep(0.05)
    assert np.array_equal(h.outputs[0].last(), h.engine.plate)
    h.engine.toggle()
    h.wait(lambda: h.mode() == "appearing")
    h.wait(lambda: h.mode() == "live")


def test_toggle_while_transitioning_is_busy(h):
    h.engine.start(h.cfg)
    _capture(h)
    h.engine.toggle()
    h.wait(lambda: h.mode() == "vanishing")
    h.engine.toggle()
    h.wait(lambda: "log.busy" in h.logs)


def test_try_effect_comes_back_by_itself(h):
    h.engine.start(h.cfg)
    _capture(h)
    h.engine.try_effect()
    h.wait(lambda: h.mode() == "gone")
    h.wait(lambda: h.mode() == "live")


def test_manual_toggle_cancels_try_auto_return(h):
    h.engine.start(h.cfg)
    _capture(h)
    h.engine.try_effect()
    h.wait(lambda: h.mode() == "gone")
    h.engine.toggle()                                  # come back by hand
    h.wait(lambda: h.mode() == "live")
    h.engine.toggle()                                  # vanish for real this time
    h.wait(lambda: h.mode() == "gone")
    time.sleep(Engine.HOLD_S + 0.3)
    assert h.mode() == "gone"


def test_random_effect_is_resolved_and_reused(fast):
    harness = Harness(effect=effects.RANDOM_ID)
    try:
        harness.engine.start(harness.cfg)
        _capture(harness)
        harness.engine.toggle()
        harness.wait(lambda: harness.mode() == "gone")
        chosen = harness.engine.status().effect
        assert chosen in effects.effect_ids()
        harness.engine.toggle()
        harness.wait(lambda: harness.mode() == "appearing")
        assert harness.engine.status().effect == chosen
    finally:
        harness.engine.stop()


def test_stop_releases_everything(h):
    h.engine.start(h.cfg)
    h.wait(lambda: h.outputs and h.outputs[0].last() is not None)
    h.engine.stop()
    assert not h.engine.running
    assert h.outputs[0].closed
    assert h.source.closed
    assert h.engine.status().mode == "stopped"


def test_output_failure_aborts_start_cleanly(h):
    def broken(w, hh, fps):
        raise RuntimeError("no driver")
    h.cfg.output_factory = broken
    with pytest.raises(RuntimeError):
        h.engine.start(h.cfg)
    assert not h.engine.running
    assert h.source.closed


def test_crash_in_loop_stops_engine(h):
    h.engine.start(h.cfg)
    h.wait(lambda: h.outputs and h.outputs[0].last() is not None)

    def boom(frame):
        raise ValueError("kaboom")
    h.outputs[0].send = boom
    h.wait(lambda: not h.engine.running)
    assert "log.engine_error" in h.logs
    assert h.outputs[0].closed


def test_settings_can_change_while_running(h):
    h.engine.start(h.cfg)
    h.engine.set_effect("dust")
    h.engine.set_duration(0.3)
    h.engine.set_preview(False)
    h.wait(lambda: h.engine.status().effect == "dust")
