"""Seeded value noise. Cheap: random grids upsampled with bicubic interpolation."""
import cv2
import numpy as np


def fbm(h: int, w: int, scale: float, octaves: int = 4, seed: int = 0,
        persistence: float = 0.5) -> np.ndarray:
    """Fractal noise in [0, 1], shape (h, w), float32. `scale` = feature size in pixels."""
    rng = np.random.default_rng(seed)
    total = np.zeros((h, w), np.float32)
    amp, cell = 1.0, float(scale)
    for _ in range(octaves):
        gh = max(2, int(np.ceil(h / cell)) + 2)
        gw = max(2, int(np.ceil(w / cell)) + 2)
        grid = rng.random((gh, gw)).astype(np.float32)
        up = cv2.resize(grid, (int(gw * cell), int(gh * cell)), interpolation=cv2.INTER_CUBIC)
        total += amp * up[:h, :w]
        amp *= persistence
        cell = max(1.0, cell / 2)
    lo, hi = float(total.min()), float(total.max())
    return (total - lo) / max(hi - lo, 1e-6)


def value_noise_1d(n: int, scale: float, seed: int = 0) -> np.ndarray:
    """Smooth 1-D noise in [0, 1], length n."""
    rng = np.random.default_rng(seed)
    knots = int(np.ceil(n / scale)) + 2
    values = rng.random(knots).astype(np.float32)
    pos = np.arange(n, dtype=np.float32) / scale
    i = np.floor(pos).astype(int)
    f = pos - i
    f = f * f * (3 - 2 * f)
    return values[i] * (1 - f) + values[i + 1] * f
