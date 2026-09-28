import time

import numpy as np
import pytest

from snap import effects
from snap.effects import noise
from snap.effects.base import (Effect, EffectContext, composite, ease_in_out_cubic, mask_bbox,
                               mask_centroid, smoothstep)
from snap.effects.particles import Particles, splat
from tests.effect_fixtures import make_scene

SCENE = make_scene()


class _Fade(Effect):
    """Minimal effect used to exercise the contract tests themselves."""
    id = "_fade"

    def render(self, frame, mask, plate, p):
        return composite(frame, plate, mask * p)


EFFECT_CLASSES = [effects.EFFECTS[i] for i in effects.effect_ids()] + [_Fade]


def _prepared(cls, seed=7):
    frame, plate, mask = SCENE
    fx = cls()
    fx.prepare(EffectContext(frame=frame, mask=mask, plate=plate, seed=seed))
    return fx


def _diff(a, b):
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


# ---------------------------------------------------------------- contract, every effect
@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_output_shape_and_type(cls):
    frame, plate, mask = SCENE
    out = _prepared(cls).apply(frame, mask, plate, 0.5)
    assert out.shape == frame.shape and out.dtype == np.uint8


@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_endpoints_are_exact(cls):
    frame, plate, mask = SCENE
    fx = _prepared(cls)
    assert np.array_equal(fx.apply(frame, mask, plate, 0.0), frame)
    assert np.array_equal(fx.apply(frame, mask, plate, 1.0), plate)


@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_no_pop_at_start_or_end(cls):
    frame, plate, mask = SCENE
    fx = _prepared(cls)
    assert _diff(fx.apply(frame, mask, plate, 0.01), frame) < 3.0
    assert _diff(fx.apply(frame, mask, plate, 0.99), plate) < 3.0


@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_midpoint_is_a_real_transition(cls):
    frame, plate, mask = SCENE
    out = _prepared(cls).apply(frame, mask, plate, 0.5)
    assert _diff(out, frame) > 1.0
    assert _diff(out, plate) > 0.3


@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_render_is_deterministic(cls):
    frame, plate, mask = SCENE
    fx = _prepared(cls)
    a = fx.apply(frame, mask, plate, 0.37)
    b = fx.apply(frame, mask, plate, 0.37)
    assert np.array_equal(a, b)
    c = _prepared(cls).apply(frame, mask, plate, 0.37)
    assert np.array_equal(a, c)


@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_contained_effects_leave_far_pixels_alone(cls):
    if cls.spills:
        pytest.skip("effect is allowed to draw outside the person")
    frame, plate, mask = SCENE
    out = _prepared(cls).apply(frame, mask, plate, 0.5)
    x0, y0, x1, y1 = mask_bbox(mask)
    pad = int(0.12 * frame.shape[1])
    outside = np.ones(mask.shape, bool)
    outside[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = False
    assert np.abs(out[outside].astype(int) - frame[outside].astype(int)).max() <= 2


@pytest.mark.perf
@pytest.mark.parametrize("cls", EFFECT_CLASSES, ids=lambda c: c.id)
def test_render_fits_frame_budget(cls):
    frame, plate, mask = SCENE
    fx = _prepared(cls)
    fx.apply(frame, mask, plate, 0.3)  # warm-up
    times = []
    for i in range(15):
        p = 0.05 + 0.9 * i / 14
        t = time.perf_counter()
        fx.apply(frame, mask, plate, p)
        times.append(time.perf_counter() - t)
    assert float(np.median(times)) * 1000 <= 15.0


# ---------------------------------------------------------------- effect specifics
def test_cloud_covers_person_while_swapping():
    frame, plate, mask = SCENE
    fx = _prepared(effects.EFFECTS["cloud"])
    person = mask > 0.5
    for p in (0.46, 0.5, 0.54):
        cover = fx.coverage(p)
        assert cover.shape == mask.shape
        assert float((cover[person] >= 0.98).mean()) >= 0.98, p


# ---------------------------------------------------------------- registry
def test_registry_ids_and_random():
    ids = effects.effect_ids()
    assert ids == effects.ORDER
    assert len(ids) == len(set(ids))
    assert effects.RANDOM_ID not in ids
    rng = np.random.default_rng(1)
    if ids:
        assert effects.resolve_effect(effects.RANDOM_ID, rng) in ids
        assert effects.resolve_effect(ids[0], rng) == ids[0]
    assert effects.resolve_effect("nonsense", rng) in ids + [effects.DEFAULT_ID]


# ---------------------------------------------------------------- helpers
def test_fbm_range_and_determinism():
    a = noise.fbm(90, 160, scale=24, octaves=4, seed=3)
    b = noise.fbm(90, 160, scale=24, octaves=4, seed=3)
    c = noise.fbm(90, 160, scale=24, octaves=4, seed=4)
    assert a.shape == (90, 160) and a.dtype == np.float32
    assert a.min() >= 0.0 and a.max() <= 1.0 and a.max() - a.min() > 0.9
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_value_noise_1d():
    v = noise.value_noise_1d(300, scale=40, seed=2)
    assert v.shape == (300,) and 0.0 <= v.min() and v.max() <= 1.0
    assert np.abs(np.diff(v)).max() < 0.2  # smooth


def test_composite_endpoints():
    frame, plate, mask = SCENE
    assert np.array_equal(composite(frame, plate, np.zeros_like(mask)), frame)
    assert np.array_equal(composite(frame, plate, np.ones_like(mask)), plate)


def test_mask_helpers():
    _, _, mask = SCENE
    x0, y0, x1, y1 = mask_bbox(mask)
    assert x0 < 640 < x1 and y0 < 360 < y1
    cx, cy = mask_centroid(mask)
    assert abs(cx - 640) < 5
    assert mask_bbox(np.zeros((10, 10), np.float32)) is None


def test_easing_and_smoothstep():
    assert ease_in_out_cubic(0.0) == 0.0 and ease_in_out_cubic(1.0) == 1.0
    assert abs(ease_in_out_cubic(0.5) - 0.5) < 1e-6
    s = smoothstep(0.2, 0.4, np.array([0.0, 0.3, 1.0]))
    assert s[0] == 0.0 and 0 < s[1] < 1 and s[2] == 1.0


def test_particles_move_and_expire():
    n = 3
    parts = Particles(
        x0=np.full(n, 10.0), y0=np.full(n, 10.0), vx=np.full(n, 100.0), vy=np.zeros(n),
        t0=np.array([0.0, 0.5, 0.9]), life=np.full(n, 0.3),
        color=np.zeros((n, 3), np.uint8), size=np.ones(n, np.int32))
    x, y, alive, age = parts.state(0.2)
    assert alive.tolist() == [True, False, False]
    assert x[0] == pytest.approx(30.0)
    assert 0 < age[0] < 1
    _, _, alive, _ = parts.state(0.6)
    assert alive.tolist() == [False, True, False]


def test_splat_clips_to_image():
    img = np.zeros((20, 20, 3), np.uint8)
    x = np.array([-5.0, 5.0, 19.5, 100.0])
    y = np.array([5.0, 5.0, 19.5, 5.0])
    colors = np.full((4, 3), 255, np.uint8)
    splat(img, x, y, colors, np.ones(4, np.float32), np.full(4, 3, np.int32))
    assert img[5:8, 5:8].min() == 255
    assert img[19, 19].max() == 255
    assert img.sum() == 255 * 3 * (9 + 1)
