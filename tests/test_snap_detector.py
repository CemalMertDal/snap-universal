import numpy as np
import pytest

from snap.core.snap_detector import SnapAnalyzer

SR = 48000


def silence(seconds, level=1e-4, seed=0):
    return np.random.default_rng(seed).normal(0, level, int(SR * seconds)).astype(np.float32)


def make_snap(amp=0.5, seed=1):
    """Short broadband click with a fast exponential decay."""
    rng = np.random.default_rng(seed)
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    burst = rng.normal(0, 1, n) * np.exp(-t / 0.008)
    burst = np.diff(burst, prepend=0.0)             # tilt toward high frequencies
    return (burst / np.abs(burst).max() * amp).astype(np.float32)


def place(signal, clip, at):
    i = int(at * SR)
    signal[i:i + len(clip)] += clip[: len(signal) - i]
    return signal


def speech_like(seconds=3.0, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    f0 = 140 * (1 + 0.05 * np.sin(2 * np.pi * 0.7 * t))
    phase = 2 * np.pi * np.cumsum(f0) / SR
    voiced = sum(np.sin(k * phase) / k for k in range(1, 28))
    syllables = 0.55 + 0.45 * np.sin(2 * np.pi * 4 * t)
    sig = 0.12 * voiced * syllables
    # fricatives ("s", "sh"): high band noise with soft 25 ms ramps
    for start in (0.4, 1.3, 2.2):
        n = int(0.17 * SR)
        env = np.ones(n)
        ramp = int(0.025 * SR)
        env[:ramp] = np.linspace(0, 1, ramp)
        env[-ramp:] = np.linspace(1, 0, ramp)
        hiss = np.diff(rng.normal(0, 1, n + 1)) * env * 0.08
        i = int(start * SR)
        sig[i:i + n] += hiss
    return sig.astype(np.float32)


def run(signal, sensitivity=6.0, block=256):
    an = SnapAnalyzer(SR, sensitivity)
    hits = []
    for i in range(0, len(signal), block):
        hits += an.feed(signal[i:i + block])
    return hits


def test_single_snap_detected_once_at_the_right_time():
    sig = place(silence(2.0), make_snap(), 1.0)
    hits = run(sig)
    assert len(hits) == 1
    assert abs(hits[0] - 1.0) < 0.03


def test_three_spaced_snaps():
    sig = silence(5.5)
    for at in (0.5, 2.5, 4.5):
        place(sig, make_snap(seed=int(at * 10)), at)
    assert len(run(sig)) == 3


def test_snaps_over_background_noise():
    sig = silence(5.5, level=0.01)
    for at in (0.8, 2.8, 4.8):
        place(sig, make_snap(seed=int(at * 10)), at)
    assert len(run(sig)) == 3


def test_refractory_period_merges_close_snaps():
    sig = silence(2.5)
    place(sig, make_snap(seed=3), 1.0)
    place(sig, make_snap(seed=4), 1.5)
    assert len(run(sig)) == 1


@pytest.mark.parametrize("name,signal", [
    ("speech", speech_like()),
    ("tone", (0.3 * np.sin(2 * np.pi * 3000 * np.arange(3 * SR) / SR)).astype(np.float32)),
    ("hum", (0.4 * np.sin(2 * np.pi * 50 * np.arange(3 * SR) / SR)).astype(np.float32)),
    ("noise", silence(3.0, level=0.02, seed=5)),
    ("swell", (silence(3.0, level=1.0, seed=6) * np.linspace(0, 0.05, 3 * SR)).astype(np.float32)),
])
def test_no_false_triggers(name, signal):
    assert run(signal) == [], name


def test_higher_sensitivity_never_detects_less():
    sig = silence(6.5, level=0.004)
    for at in (0.8, 2.8, 4.8):
        place(sig, make_snap(amp=0.08, seed=int(at * 10)), at)
    counts = [len(run(sig, sensitivity=s)) for s in (1, 4, 7, 10)]
    assert counts == sorted(counts)
    assert counts[-1] == 3


def test_block_size_does_not_change_results():
    sig = silence(5.5, level=0.005)
    for at in (0.5, 2.5, 4.5):
        place(sig, make_snap(seed=int(at * 10)), at)
    assert run(sig, block=256) == run(sig, block=4096) == run(sig, block=333)


def test_level_rises_on_a_snap():
    an = SnapAnalyzer(SR, 6.0)
    an.feed(silence(1.0))
    quiet = an.level
    an.feed(make_snap()[:2048])
    assert an.level > quiet and an.level > 0.7
