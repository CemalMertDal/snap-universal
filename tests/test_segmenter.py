import numpy as np
import pytest

from snap.core.segmenter import PersonSegmenter, hide_mask
from tests.effect_fixtures import make_scene


@pytest.fixture(scope="module")
def segmenter():
    seg = PersonSegmenter()
    yield seg
    seg.close()


def test_mask_shape_type_and_range(segmenter):
    frame, _, _ = make_scene()
    m = segmenter.mask(frame, 0)
    assert m.shape == frame.shape[:2] and m.dtype == np.float32
    assert 0.0 <= float(m.min()) and float(m.max()) <= 1.0


def test_repeated_or_backwards_timestamps_are_tolerated(segmenter):
    frame, _, _ = make_scene(360, 640)
    segmenter.mask(frame, 1000)
    segmenter.mask(frame, 1000)
    segmenter.mask(frame, 500)


def test_hide_mask_grows_and_stays_in_range():
    _, _, mask = make_scene()
    grown = hide_mask(mask)
    assert grown.shape == mask.shape and grown.dtype == np.float32
    assert 0.0 <= float(grown.min()) and float(grown.max()) <= 1.0
    assert grown.sum() > mask.sum() * 1.02
    # everything that was person stays fully hidden
    assert float(grown[mask > 0.5].min()) > 0.95
