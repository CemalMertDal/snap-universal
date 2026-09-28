"""Dust: the person crumbles along a noisy front and blows away as drifting grains."""
import cv2
import numpy as np

from snap.effects.base import (Effect, EffectContext, composite, mask_bbox, register, smooth,
                               smoothstep)
from snap.effects.noise import fbm
from snap.effects.particles import Particles, splat

BODY_END = 0.65          # the body is fully gone at this progress
BAND = 0.03              # softness of the crumbling edge
MAX_GRAINS = 9000
DUST = np.array([96, 104, 112], np.float32)   # BGR ash grey
WIND = np.array([1.0, -0.3], np.float32)


def _detach_field(ctx: EffectContext, bbox, roi) -> np.ndarray:
    """Per-pixel progress (0..1) at which each pixel of the ROI crumbles."""
    x0, y0, x1, y1 = bbox
    rx0, ry0, rx1, ry1 = roi
    rh, rw = ry1 - ry0, rx1 - rx0
    coarse = fbm(max(2, rh // 2), max(2, rw // 2), scale=max(8.0, ctx.w * 0.02), octaves=4, seed=ctx.seed)
    coarse = cv2.resize(coarse, (rw, rh), interpolation=cv2.INTER_LINEAR)
    grain = ctx.rng.random((rh, rw), dtype=np.float32)
    yy, xx = np.mgrid[ry0:ry1, rx0:rx1].astype(np.float32)
    d = WIND / np.linalg.norm(WIND)
    ramp = ((xx - x0) * d[0] + (yy - y0) * d[1]) / max(x1 - x0, y1 - y0, 1)
    field = 0.35 * coarse + 0.55 * ramp + 0.1 * grain
    inside = ctx.mask[ry0:ry1, rx0:rx1] > 0.3
    lo, hi = (field[inside].min(), field[inside].max()) if inside.any() else (0.0, 1.0)
    return np.clip((field - lo) / max(hi - lo, 1e-6), 0.0, 1.0)


@register
class Dust(Effect):
    id = "dust"
    icon = "✨"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        bbox = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        pad = int(0.06 * w)
        x0, y0, x1, y1 = bbox
        self.roi = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        self.field = _detach_field(ctx, bbox, self.roi)

        rng = ctx.rng
        weights = ctx.mask.ravel().astype(np.float64)
        total = weights.sum()
        n = int(min(MAX_GRAINS, total * 0.06)) if total > 0 else 0
        if n == 0:
            self.grains = None
            return
        idx = rng.choice(weights.size, size=n, replace=False, p=weights / total)
        ys, xs = np.divmod(idx, w)
        rx0, ry0, rx1, ry1 = self.roi
        detach = self.field[np.clip(ys - ry0, 0, ry1 - ry0 - 1), np.clip(xs - rx0, 0, rx1 - rx0 - 1)]
        t0 = detach * BODY_END
        dirn = WIND / np.linalg.norm(WIND)
        speed = rng.uniform(0.5, 1.0, n) * w
        self.grains = Particles(
            x0=xs.astype(np.float32) + rng.uniform(0, 1, n),
            y0=ys.astype(np.float32) + rng.uniform(0, 1, n),
            vx=dirn[0] * speed + rng.normal(0, 0.05 * w, n),
            vy=dirn[1] * speed + rng.normal(0, 0.06 * h, n),
            ax=rng.uniform(0.6, 1.2, n) * w, ay=-rng.uniform(0.0, 0.5, n) * h,
            t0=t0, life=rng.uniform(0.25, 0.35, n),
            color=ctx.frame[ys, xs].copy(),
            size=rng.choice([1, 2, 2, 3], size=n).astype(np.int32),
            wobble=rng.uniform(2, 9, n), phase=rng.uniform(0, 2 * np.pi, n))

    def render(self, frame, mask, plate, p):
        q = min(1.0, p / BODY_END)
        thr = q * (1 + 2 * BAND) - BAND
        rx0, ry0, rx1, ry1 = self.roi
        out = frame.copy()
        m = mask[ry0:ry1, rx0:rx1]
        if q < 1.0:
            vis = smoothstep(thr - BAND, thr + BAND, self.field)
            sub = composite(out[ry0:ry1, rx0:rx1], plate[ry0:ry1, rx0:rx1], m * (1.0 - vis))
            # darken the crumbling rim a little so the edge reads as material, not a fade
            rim = vis * (1.0 - vis) * (4.0 * 0.35) * m
            out[ry0:ry1, rx0:rx1] = composite(sub, np.zeros_like(sub), rim)
        else:
            out[ry0:ry1, rx0:rx1] = composite(out[ry0:ry1, rx0:rx1], plate[ry0:ry1, rx0:rx1], m)
        # anything of the person outside the ROI crumbles away at the same pace
        if q > 0:
            h, w = mask.shape
            for sl in ((slice(0, ry0), slice(0, w)), (slice(ry1, h), slice(0, w)),
                       (slice(ry0, ry1), slice(0, rx0)), (slice(ry0, ry1), slice(rx1, w))):
                ms = mask[sl]
                if ms.size and ms.max() > 0.01:
                    out[sl] = composite(out[sl], plate[sl], ms * q)

        g = self.grains
        if g is None:
            return out
        x, y, alive, age = g.state(p)
        if not alive.any():
            return out
        a = age[alive]
        color = g.color[alive].astype(np.float32)
        color = color + (DUST - color) * (0.7 * a)[:, None]
        alpha = (1.0 - a * a) * (1.0 - smooth(0.9, 1.0, p))
        splat(out, x[alive], y[alive], color, alpha, g.size[alive])
        return out
