"""Effect contract and shared image helpers.

An effect turns (live frame, person mask, empty-room plate, progress p) into an output
frame. p=0 means the person is fully visible, p=1 means they are fully gone. After
prepare() the output must depend only on the inputs and p, so "come back" is simply the
same effect played from p=1 down to p=0.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

EFFECTS: dict[str, type["Effect"]] = {}


def register(cls):
    EFFECTS[cls.id] = cls
    return cls


@dataclass
class EffectContext:
    """Snapshot taken when a transition starts."""
    frame: np.ndarray
    mask: np.ndarray
    plate: np.ndarray
    seed: int = 0
    rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)

    @property
    def h(self) -> int:
        return self.frame.shape[0]

    @property
    def w(self) -> int:
        return self.frame.shape[1]


class Effect:
    id = ""
    icon = ""
    spills = False  # may draw outside the person's bounding box

    def prepare(self, ctx: EffectContext) -> None:
        self.ctx = ctx

    def apply(self, frame: np.ndarray, mask: np.ndarray, plate: np.ndarray, p: float) -> np.ndarray:
        if p <= 0.0:
            return frame.copy()
        if p >= 1.0:
            return plate.copy()
        return self.render(frame, mask, plate, float(p))

    def render(self, frame, mask, plate, p):  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- math
def ease_in_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def smooth(e0: float, e1: float, x: float) -> float:
    """Scalar smoothstep."""
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def bell(x: float, centre: float, width: float) -> float:
    return float(np.exp(-((x - centre) / width) ** 2))


# ---------------------------------------------------------------- images
def composite(under: np.ndarray, over: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """alpha=0 → under, alpha=1 → over. alpha is HxW float."""
    a = np.clip(alpha, 0.0, 1.0).astype(np.float32, copy=False)
    return cv2.blendLinear(under, over, 1.0 - a, a)


def remove_person(frame: np.ndarray, plate: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return composite(frame, plate, mask)


def add_light(img: np.ndarray, light: np.ndarray) -> np.ndarray:
    """Additive, saturating. light is HxWx3 float in 0..255 units."""
    return cv2.add(img, np.clip(light, 0, 255).astype(np.uint8))


def mask_bbox(mask: np.ndarray, thresh: float = 0.5):
    ys, xs = np.nonzero(mask > thresh)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def mask_centroid(mask: np.ndarray) -> tuple[float, float]:
    m = cv2.moments(mask.astype(np.float32))
    if m["m00"] < 1e-6:
        h, w = mask.shape
        return w / 2.0, h / 2.0
    return m["m10"] / m["m00"], m["m01"] / m["m00"]


def half(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (w // 2, h // 2), interpolation=cv2.INTER_AREA)


def full(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """size = (w, h)."""
    return cv2.resize(img, size, interpolation=cv2.INTER_LINEAR)
