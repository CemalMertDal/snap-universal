"""Headless smoke test (`Snap.exe --selftest`): proves a build has everything it needs
without opening any camera, microphone or virtual camera."""
import time
import traceback
from pathlib import Path

import numpy as np

from snap.paths import user_data_dir


def _snap_signal(sr: int) -> np.ndarray:
    rng = np.random.default_rng(1)
    sig = rng.normal(0, 1e-4, sr * 2).astype(np.float32)
    n = int(0.06 * sr)
    t = np.arange(n) / sr
    burst = np.diff(rng.normal(0, 1, n) * np.exp(-t / 0.008), prepend=0.0)
    sig[sr:sr + n] += (burst / np.abs(burst).max() * 0.5).astype(np.float32)
    return sig


def run(log_path: Path | None = None) -> int:
    log_path = Path(log_path) if log_path else user_data_dir() / "selftest.log"
    lines, ok = [], True

    def step(name, fn):
        nonlocal ok
        start = time.perf_counter()
        try:
            detail = fn()
            lines.append(f"OK   {name} ({(time.perf_counter() - start) * 1000:.0f} ms) {detail or ''}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")

    from snap.core.sources import SyntheticSource
    src = SyntheticSource(640, 360)
    src.open()
    frame = src.read()
    mask = src.last_mask
    plate = src.room

    def segment():
        from snap.core.segmenter import PersonSegmenter, hide_mask
        seg = PersonSegmenter()
        m = seg.mask(frame, 0)
        seg.close()
        hide_mask(m)
        return f"mask {m.shape}"

    def render_effects():
        from snap import effects
        from snap.effects.base import EffectContext
        assert effects.effect_ids() == effects.ORDER, f"effects missing: {effects.effect_ids()}"
        done = []
        for eid in effects.effect_ids():
            fx = effects.get_effect(eid)
            fx.prepare(EffectContext(frame=frame, mask=mask, plate=plate, seed=1))
            for p in (0.0, 0.5, 1.0):
                out = fx.apply(frame, mask, plate, p)
                assert out.shape == frame.shape and out.dtype == np.uint8
            done.append(eid)
        return "effects: " + ", ".join(done)

    def snap_detector():
        from snap.core.snap_detector import SnapAnalyzer
        an = SnapAnalyzer(48000, 6.0)
        hits = an.feed(_snap_signal(48000))
        assert len(hits) == 1, hits
        return f"snap at {hits[0]:.3f}s"

    def vcam_layout():
        from snap.core import vcam
        from snap.core.vcam import obs
        obs.bgr_to_nv12(frame)
        return f"{len(vcam.devices_registered())} capture devices registered"

    def ui_imports():
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import qfluentwidgets  # noqa: F401
        import snap.ui.main_window  # noqa: F401
        return "ui modules import"

    for name, fn in (("segmenter", segment), ("effects", render_effects), ("snap detector", snap_detector),
                     ("virtual camera", vcam_layout), ("ui", ui_imports)):
        step(name, fn)

    lines.append("RESULT " + ("PASS" if ok else "FAIL"))
    try:
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1
