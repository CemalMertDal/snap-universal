"""Burn: a glowing burn line climbs over the person, charring ahead of it and
throwing embers, leaving the empty room behind."""
import cv2
import numpy as np

from snap.effects.base import (Effect, EffectContext, add_light, composite, mask_bbox, register,
                               smooth, smoothstep)
from snap.effects.noise import fbm
from snap.effects.particles import Particles, splat

BURN_END = 0.8
GLOW_W = 0.02
CHAR_W = 0.09
EMBERS = 1500
FLAME_OUTER = np.array([10, 90, 255], np.float32)    # BGR orange-red
FLAME_CORE = np.array([170, 235, 255], np.float32)   # BGR hot yellow-white
EMBER_COLORS = np.array([[40, 160, 255], [80, 210, 255], [20, 110, 250]], np.float32)


@register
class Burn(Effect):
    id = "burn"
    icon = "🔥"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        x0, y0, x1, y1 = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        pad = int(0.04 * w)
        self.roi = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        rx0, ry0, rx1, ry1 = self.roi
        rh, rw = ry1 - ry0, rx1 - rx0

        noise = fbm(rh, rw, scale=max(6.0, rw * 0.08), octaves=4, seed=ctx.seed)
        grain = ctx.rng.random((rh, rw), dtype=np.float32)
        ys = np.arange(rh, dtype=np.float32)[:, None]
        ramp = 1.0 - ys / max(rh - 1, 1)                      # bottom burns first
        field = 0.6 * ramp + 0.35 * noise + 0.05 * grain
        inside = ctx.mask[ry0:ry1, rx0:rx1] > 0.3
        lo, hi = (field[inside].min(), field[inside].max()) if inside.any() else (0.0, 1.0)
        self.field = np.clip((field - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
        self.row_min = self.field.min(axis=1)
        self.row_max = self.field.max(axis=1)

        rng = ctx.rng
        m = ctx.mask[ry0:ry1, rx0:rx1].ravel().astype(np.float64)
        total = m.sum()
        n = int(min(EMBERS, total * 0.02)) if total > 0 else 0
        if n == 0:
            self.embers = None
            return
        idx = rng.choice(m.size, size=n, replace=False, p=m / total)
        ey, ex = np.divmod(idx, rw)
        self.embers = Particles(
            x0=(ex + rx0).astype(np.float32), y0=(ey + ry0).astype(np.float32),
            vx=rng.normal(0, 0.04 * w, n), vy=-rng.uniform(0.25, 0.6, n) * h,
            ay=-rng.uniform(0, 0.4, n) * h,
            t0=self._front_progress(self.field[ey, ex]), life=rng.uniform(0.1, 0.2, n),
            color=EMBER_COLORS[rng.integers(0, len(EMBER_COLORS), n)].astype(np.uint8),
            size=rng.choice([1, 2, 2, 3], size=n).astype(np.int32),
            wobble=rng.uniform(3, 12, n), phase=rng.uniform(0, 2 * np.pi, n))

    @staticmethod
    def _front_progress(f):
        """Progress at which the burn front reaches field value f."""
        return (f + 0.05) / 1.1 * BURN_END

    def render(self, frame, mask, plate, p):
        q = min(1.0, p / BURN_END)
        thr = q * 1.1 - 0.05
        rx0, ry0, rx1, ry1 = self.roi
        out = frame.copy()
        reach = 2.5 * GLOW_W

        # rows the front has fully passed: just swap the person for the room
        done = np.flatnonzero(self.row_max < thr - reach)
        if len(done):
            a, b = ry0 + done[0], ry0 + done[-1] + 1
            out[a:b, rx0:rx1] = composite(out[a:b, rx0:rx1], plate[a:b, rx0:rx1], mask[a:b, rx0:rx1])

        # rows the front is crossing right now
        band = np.flatnonzero((self.row_max >= thr - reach) & (self.row_min <= thr + max(CHAR_W, reach)))
        if len(band):
            r0, r1 = band[0], band[-1] + 1
            f = self.field[r0:r1]
            ys = slice(ry0 + r0, ry0 + r1)
            m = mask[ys, rx0:rx1]
            vis = smoothstep(thr - 0.008, thr + 0.008, f)
            char = (1.0 - smoothstep(thr, thr + CHAR_W, f)) * vis * smooth(0.0, 0.06, p)
            glow = np.clip(1.0 - ((f - thr) / reach) ** 2, 0.0, 1.0) ** 3
            glow *= np.clip(m * 1.5, 0, 1) * (smooth(0.0, 0.04, p) * (1 - smooth(0.9, 1.0, q)))
            sub = out[ys, rx0:rx1]
            sub[:] = composite(sub, np.zeros_like(sub), char * m * 0.75)
            sub[:] = composite(sub, plate[ys, rx0:rx1], m * (1.0 - vis))
            bloom = cv2.GaussianBlur(glow, (0, 0), 3)
            light = bloom[..., None] * (FLAME_OUTER * 1.3) + (glow ** 3)[..., None] * FLAME_CORE
            sub[:] = add_light(sub, light)

        # outside the ROI the person (if they moved) is removed at the same pace
        if q > 0:
            h, w = mask.shape
            for sl in ((slice(0, ry0), slice(0, w)), (slice(ry1, h), slice(0, w)),
                       (slice(ry0, ry1), slice(0, rx0)), (slice(ry0, ry1), slice(rx1, w))):
                ms = mask[sl]
                if ms.size and ms.max() > 0.01:
                    out[sl] = composite(out[sl], plate[sl], ms * q)

        e = self.embers
        if e is not None:
            x, y, alive, age = e.state(p)
            if alive.any():
                a = age[alive]
                flicker = 0.6 + 0.4 * np.sin(e.phase[alive] + a * 40.0)
                alpha = (1.0 - a) * flicker * (1.0 - smooth(0.9, 1.0, p))
                splat(out, x[alive], y[alive], e.color[alive], alpha, e.size[alive])
        return out
