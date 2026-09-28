"""Beam: sci-fi teleport. The person turns to shimmering light inside a column of
light and fades out in vertical streaks, sparkling."""
import cv2
import numpy as np

from snap.effects.base import (Effect, EffectContext, bell, composite, mask_bbox, mask_centroid,
                               register, smooth)
from snap.effects.noise import value_noise_1d
from snap.effects.particles import splat

TINT = np.array([255, 250, 205], np.float32)    # BGR cyan-white
COLUMN = np.array([255, 235, 190], np.float32)  # BGR pale cyan
SPARKLE = np.array([255, 255, 235], np.float32)
LOW = 4                                         # glow/column computed at 1/4 res


@register
class Beam(Effect):
    id = "beam"
    icon = "💫"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        x0, y0, x1, y1 = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        pad = int(0.08 * w)
        self.roi = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        rx0, ry0, rx1, ry1 = self.roi
        rw, rh = rx1 - rx0, ry1 - ry0
        self.size = (rw, rh)
        rng = ctx.rng

        streak = value_noise_1d(rw, scale=max(3.0, rw * 0.015), seed=ctx.seed)
        self.streak = streak[None, :].astype(np.float32)

        cx, _ = mask_centroid(ctx.mask)
        lw, lh = max(2, rw // LOW), max(2, rh // LOW)
        xs = (np.arange(lw, dtype=np.float32) * LOW + rx0 - cx) / max(0.35 * (x1 - x0), 1)
        ys = np.arange(lh, dtype=np.float32) * LOW + ry0
        col_x = np.exp(-xs ** 2)
        col_y = smooth_arr((ys - (y0 - pad)) / max(pad, 1)) * smooth_arr((y1 + pad - ys) / max(pad, 1))
        self.column = (col_y[:, None] * col_x[None, :]).astype(np.float32)

        m = ctx.mask.ravel().astype(np.float64)
        total = m.sum()
        n = int(min(1400, total * 0.008)) if total > 0 else 0
        if n:
            idx = rng.choice(m.size, size=n, replace=False, p=m / total)
            sy, sx = np.divmod(idx, w)
            self.sparks = (sx.astype(np.float32), sy.astype(np.float32),
                           rng.uniform(0, 2 * np.pi, n), rng.uniform(3, 7, n),
                           rng.choice([2, 3, 3, 4], size=n).astype(np.int32))
        else:
            self.sparks = None

    def render(self, frame, mask, plate, p):
        rx0, ry0, rx1, ry1 = self.roi
        out = frame.copy()
        m = mask[ry0:ry1, rx0:rx1]
        sub = out[ry0:ry1, rx0:rx1]

        tint = 0.5 * smooth(0.0, 0.5, p)
        if tint > 0:
            sub[:] = composite(sub, np.broadcast_to(TINT.astype(np.uint8), sub.shape), m * tint)

        u = smooth(0.35, 0.85, p)
        hide = np.clip(u * 1.4 - 0.4 * self.streak, 0.0, 1.0) * m
        sub[:] = composite(sub, plate[ry0:ry1, rx0:rx1], hide)
        # anything of the person outside the ROI fades at the same pace
        outside = out.copy()
        out = composite(out, plate, mask * u)
        out[ry0:ry1, rx0:rx1] = outside[ry0:ry1, rx0:rx1]
        sub = out[ry0:ry1, rx0:rx1]

        k = bell(p, 0.6, 0.2) * smooth(0.0, 0.12, p) * (1 - smooth(0.88, 1.0, p))
        if k > 0.01:
            small = cv2.resize(m, self.column.shape[::-1], interpolation=cv2.INTER_AREA)
            aura = cv2.GaussianBlur(small, (0, 0), 3) * (1.0 - u * 0.6)
            light = (self.column * 0.6 + aura * 0.45) * (130.0 * k)
            light3 = np.clip(light[..., None] * (COLUMN / 255.0), 0, 255).astype(np.uint8)
            sub[:] = cv2.add(sub, cv2.resize(light3, self.size, interpolation=cv2.INTER_LINEAR))

        if self.sparks is not None:
            sk = bell(p, 0.55, 0.25) * smooth(0.0, 0.1, p) * (1 - smooth(0.9, 1.0, p))
            if sk > 0.01:
                sx, sy, ph, fr, size = self.sparks
                twinkle = np.sin(ph + fr * p * np.pi * 4) ** 2
                alpha = twinkle * sk
                keep = alpha > 0.05
                cols = np.broadcast_to(SPARKLE, (int(keep.sum()), 3))
                splat(out, sx[keep], sy[keep] - p * 30.0, cols, alpha[keep], size[keep])
        return out


def smooth_arr(x):
    t = np.clip(x, 0.0, 1.0)
    return t * t * (3 - 2 * t)
