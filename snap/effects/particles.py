"""Analytic particles: positions are a closed-form function of progress, so a particle
system can be played backwards for free. Time unit = one whole effect (p from 0 to 1)."""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Particles:
    x0: np.ndarray
    y0: np.ndarray
    vx: np.ndarray
    vy: np.ndarray
    t0: np.ndarray       # progress at which the particle is born
    life: np.ndarray     # lifetime, in progress units
    color: np.ndarray    # N x 3 uint8 BGR
    size: np.ndarray     # int square size in px
    ax: np.ndarray = None
    ay: np.ndarray = None
    wobble: np.ndarray = None  # amplitude (px) of a sideways sine drift
    phase: np.ndarray = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        n = len(self.x0)
        zeros = np.zeros(n, np.float32)
        self.ax = zeros if self.ax is None else self.ax
        self.ay = zeros if self.ay is None else self.ay
        self.wobble = zeros if self.wobble is None else self.wobble
        self.phase = zeros if self.phase is None else self.phase

    def __len__(self):
        return len(self.x0)

    def state(self, p: float):
        """-> (x, y, alive mask, normalised age in [0, 1))"""
        age = p - self.t0
        alive = (age >= 0) & (age < self.life)
        a = np.where(alive, age, 0.0)
        x = self.x0 + self.vx * a + 0.5 * self.ax * a * a + self.wobble * np.sin(self.phase + 14.0 * a)
        y = self.y0 + self.vy * a + 0.5 * self.ay * a * a
        return x, y, alive, a / np.maximum(self.life, 1e-6)


def splat(img: np.ndarray, x: np.ndarray, y: np.ndarray, colors: np.ndarray,
          alpha: np.ndarray, size: np.ndarray) -> None:
    """Alpha-blend square dots into img (in place). Off-image parts are clipped."""
    if len(x) == 0:
        return
    h, w = img.shape[:2]
    xi = np.floor(x).astype(np.int32)
    yi = np.floor(y).astype(np.int32)
    col = colors.astype(np.float32)
    a = np.clip(alpha, 0.0, 1.0).astype(np.float32)[:, None]
    for s in np.unique(size):
        sel = size == s
        bx, by, bc, ba = xi[sel], yi[sel], col[sel], a[sel]
        for dy in range(int(s)):
            for dx in range(int(s)):
                px, py = bx + dx, by + dy
                ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
                if not ok.any():
                    continue
                qx, qy, qa = px[ok], py[ok], ba[ok]
                under = img[qy, qx].astype(np.float32)
                img[qy, qx] = (under + (bc[ok] - under) * qa).astype(np.uint8)
