import pytest

from snap.core.transition import Transition


def test_vanish_goes_from_zero_to_one_monotonically():
    tr = Transition(effect=None, effect_id="x", duration=2.0, vanish=True, start=10.0)
    ps = [tr.p(10.0 + i * 0.1) for i in range(21)]
    assert ps[0] == 0.0 and ps[-1] == 1.0
    assert all(b >= a for a, b in zip(ps, ps[1:]))
    assert ps[10] == pytest.approx(0.5, abs=1e-6)
    assert ps[2] < 0.2          # eased: slow start


def test_appear_goes_from_one_to_zero():
    tr = Transition(effect=None, effect_id="x", duration=1.0, vanish=False, start=0.0)
    assert tr.p(0.0) == 1.0 and tr.p(1.0) == 0.0
    assert tr.p(-5) == 1.0 and tr.p(5) == 0.0


def test_done():
    tr = Transition(effect=None, effect_id="x", duration=1.0, vanish=True, start=0.0)
    assert not tr.done(0.99)
    assert tr.done(1.0)
