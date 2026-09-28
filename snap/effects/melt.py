"""Melt: the person slumps and drips down column by column, then drains away."""
import cv2
import numpy as np

from snap.effects.base import Effect, EffectContext, composite, mask_bbox, register, smooth
from snap.effects.noise import value_noise_1d


@register
class Melt(Effect):
    id = "melt"
    icon = "🫠"
    spills = False

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        x0, y0, x1, y1 = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        pad = int(0.1 * w)
        self.roi = (max(0, x0 - pad), max(0, y0 - int(0.05 * h)), min(w, x1 + pad), h)
        rx0, ry0, rx1, ry1 = self.roi
        rw, rh = rx1 - rx0, ry1 - ry0
        rng = ctx.rng

        speed = 0.35 + 0.65 * value_noise_1d(rw, scale=max(8.0, rw * 0.07), seed=ctx.seed)
        for _ in range(max(3, rw // 60)):                      # a few fast drips
            c = int(rng.integers(0, rw))
            half = int(rng.integers(3, 10))
            speed[max(0, c - half):c + half] *= rng.uniform(1.4, 1.9)
        speed = cv2.GaussianBlur(speed.reshape(1, -1).astype(np.float32), (0, 0), 2).ravel()

        v = np.clip((np.arange(rh, dtype=np.float32) - (y0 - ry0)) / max(y1 - y0, 1), 0.0, 1.0)
        self.profile = (0.35 + 0.65 * v)[:, None] * speed[None, :]   # rh x rw
        self.gx = np.arange(rx0, rx1, dtype=np.float32)[None, :].repeat(rh, 0)
        self.gy = np.arange(ry0, ry1, dtype=np.float32)[:, None].repeat(rw, 1)
        self.wob = (np.sin(self.gy / 23.0 + rng.uniform(0, 6.28)) * 2.5).astype(np.float32)
        self.drop = 1.3 * (y1 - y0)

    def render(self, frame, mask, plate, p):
        out = composite(frame, plate, mask)
        rx0, ry0, rx1, ry1 = self.roi
        dy = self.profile * (self.drop * p * p)
        my = self.gy - dy
        mx = self.gx + self.wob * p
        person = cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        alpha = cv2.remap(mask, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        # stretched parts get darker and glossier-looking; everything drains away at the end
        stretch = np.clip(dy / (0.5 * self.drop + 1e-6), 0.0, 1.0)
        person = composite(person, np.zeros_like(person), stretch * 0.3)
        alpha *= 1.0 - smooth(0.55, 0.97, p)
        sub = out[ry0:ry1, rx0:rx1]
        sub[:] = composite(sub, person, alpha)
        return out
