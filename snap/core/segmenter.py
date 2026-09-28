"""Person segmentation with MediaPipe's selfie segmenter (Tasks API)."""
import cv2
import numpy as np

from snap.paths import resource_path

MODEL = ("assets", "models", "selfie_segmenter.tflite")
SMOOTHING = 0.6   # temporal EMA weight of the newest mask


def _stub_matplotlib() -> None:
    """MediaPipe imports matplotlib.pyplot for its drawing helpers, which we never use.
    The packaged app leaves matplotlib out (~40 MB); give the import an empty module."""
    try:
        import matplotlib.pyplot  # noqa: F401
    except ImportError:
        import sys
        import types
        pkg = types.ModuleType("matplotlib")
        pkg.__path__ = []
        pyplot = types.ModuleType("matplotlib.pyplot")
        pkg.pyplot = pyplot
        sys.modules["matplotlib"] = pkg
        sys.modules["matplotlib.pyplot"] = pyplot


class PersonSegmenter:
    def __init__(self, model_path=None):
        _stub_matplotlib()
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        data = open(model_path or resource_path(*MODEL), "rb").read()
        options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_buffer=data),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        self._seg = vision.ImageSegmenter.create_from_options(options)
        self._last_ts = -1
        self._ema = None

    def mask(self, frame_bgr: np.ndarray, ts_ms: int) -> np.ndarray:
        """Person probability per pixel, float32 HxW in [0, 1]."""
        ts = max(int(ts_ms), self._last_ts + 1)       # MediaPipe needs strictly increasing time
        self._last_ts = ts
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._seg.segment_for_video(image, ts)
        m = np.array(result.confidence_masks[0].numpy_view(), dtype=np.float32).reshape(frame_bgr.shape[:2])
        if self._ema is None or self._ema.shape != m.shape:
            self._ema = m
        else:
            self._ema += (m - self._ema) * SMOOTHING
        return np.clip(self._ema, 0.0, 1.0)

    def close(self) -> None:
        if self._seg is not None:
            self._seg.close()
            self._seg = None


def hide_mask(mask: np.ndarray) -> np.ndarray:
    """Grow and feather the person mask so no halo of the person survives compositing."""
    h, w = mask.shape
    q = 4                                            # work at quarter resolution
    small = cv2.resize(mask, (max(1, w // q), max(1, h // q)), interpolation=cv2.INTER_AREA)
    small = np.clip((small - 0.25) * 2.0, 0.0, 1.0)
    r = max(1, int(round(0.012 * w / q)))            # ~1.2% of the frame width
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    grown = cv2.GaussianBlur(cv2.dilate(small, kernel), (0, 0), r * 0.5)
    out = cv2.resize(grown, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.max(out, mask), 0.0, 1.0)
