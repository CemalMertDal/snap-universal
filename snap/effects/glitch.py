"""Glitch: the person flickers and breaks up in digital corruption, then cuts out."""
import numpy as np

from snap.effects.base import Effect, EffectContext, composite, mask_bbox, register, smooth

STEPS = 40   # corruption pattern changes this many times over the whole effect


@register
class Glitch(Effect):
    id = "glitch"
    icon = "📺"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        x0, y0, x1, y1 = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        pad = int(0.06 * h)
        # corruption tears across the full width of the rows the person occupies
        self.roi = (0, max(0, y0 - pad), w, min(h, y1 + pad))

    def render(self, frame, mask, plate, p):
        intensity = np.sin(np.pi * p) ** 0.7
        step = int(p * STEPS)
        rng = np.random.default_rng(self.ctx.seed * 7919 + step)

        vis = 1.0 - smooth(0.15, 0.9, p)
        roll = rng.random()
        if roll < 0.35 * smooth(0.2, 0.8, p):
            vis = 0.0                                    # drop-out frame
        elif roll > 1.0 - 0.3 * intensity * (1.0 - vis):
            vis = min(1.0, vis + 0.6)                    # flash back in
        out = composite(frame, plate, mask * (1.0 - vis))
        if intensity < 0.02:
            return out

        rx0, ry0, rx1, ry1 = self.roi
        src = out[ry0:ry1, rx0:rx1].copy()
        sub = out[ry0:ry1, rx0:rx1]
        rh, rw = src.shape[:2]

        # horizontal slice tearing
        for _ in range(int(3 + 12 * intensity)):
            y = int(rng.integers(0, rh))
            hgt = int(rng.integers(3, max(4, int(40 * intensity) + 4)))
            dx = int(rng.normal(0, 45 * intensity))
            ys = slice(y, min(rh, y + hgt))
            sub[ys] = np.roll(src[ys], dx, axis=1)

        # RGB channel split
        d = int(round(14 * intensity))
        if d:
            shifted = sub.copy()
            sub[:, d:, 2] = shifted[:, :-d, 2]
            sub[:, :-d, 0] = shifted[:, d:, 0]

        # corrupted blocks copied from elsewhere, some with swapped channels
        for _ in range(int(8 * intensity)):
            bh, bw = int(rng.integers(8, 60)), int(rng.integers(16, 120))
            if bh >= rh or bw >= rw:
                continue
            ty, tx = int(rng.integers(0, rh - bh)), int(rng.integers(0, rw - bw))
            sy, sx = int(rng.integers(0, rh - bh)), int(rng.integers(0, rw - bw))
            block = src[sy:sy + bh, sx:sx + bw]
            sub[ty:ty + bh, tx:tx + bw] = block[..., ::-1] if rng.random() < 0.4 else block

        # scanlines over the whole picture, so no box edge shows
        out[::2] = (out[::2].astype(np.float32) * (1.0 - 0.18 * intensity)).astype(np.uint8)
        return out
