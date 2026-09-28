"""Vortex: the person is twisted and sucked into a single point."""
import cv2
import numpy as np

from snap.effects.base import (Effect, EffectContext, bell, composite, mask_bbox,
                               mask_centroid, register, smooth)

TWIST = 4.5 * np.pi
GLOW = np.array([255, 150, 190], np.float32)   # BGR violet-blue
MAP_DOWN = 4                                   # remap tables are computed at 1/4 res


@register
class Vortex(Effect):
    id = "vortex"
    icon = "🌀"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        h, w = ctx.h, ctx.w
        bbox = mask_bbox(ctx.mask) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        cx, cy = mask_centroid(ctx.mask)
        x0, y0, x1, y1 = bbox
        R = 1.05 * max(np.hypot(x - cx, y - cy) for x in (x0, x1) for y in (y0, y1))
        self.cx, self.cy, self.R = cx, cy, R
        self.roi = (max(0, int(cx - R)), max(0, int(cy - R)), min(w, int(cx + R) + 1), min(h, int(cy + R) + 1))
        rx0, ry0, rx1, ry1 = self.roi
        self.size = (rx1 - rx0, ry1 - ry0)
        sw, sh = max(2, self.size[0] // MAP_DOWN), max(2, self.size[1] // MAP_DOWN)
        xs = np.linspace(rx0, rx1 - 1, sw, dtype=np.float32)
        ys = np.linspace(ry0, ry1 - 1, sh, dtype=np.float32)
        gx, gy = np.meshgrid(xs, ys)
        self.r = np.hypot(gx - cx, gy - cy)
        self.theta = np.arctan2(gy - cy, gx - cx)

    def _maps(self, p: float):
        s = max(1.0 - p ** 1.5, 1e-3)
        falloff = np.clip(1.2 - self.r / self.R, 0.0, 1.2)
        ang = self.theta - TWIST * p * p * falloff
        rad = self.r / s
        mx = (self.cx + rad * np.cos(ang)).astype(np.float32)
        my = (self.cy + rad * np.sin(ang)).astype(np.float32)
        mx = cv2.resize(mx, self.size, interpolation=cv2.INTER_LINEAR)
        my = cv2.resize(my, self.size, interpolation=cv2.INTER_LINEAR)
        return mx, my

    def render(self, frame, mask, plate, p):
        out = composite(frame, plate, mask)
        rx0, ry0, rx1, ry1 = self.roi
        mx, my = self._maps(p)
        person = cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        alpha = cv2.remap(mask, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        alpha *= 1.0 - smooth(0.85, 1.0, p)
        sub = out[ry0:ry1, rx0:rx1]
        sub[:] = composite(sub, person, alpha)

        k = bell(p, 0.6, 0.22) * smooth(0.0, 0.1, p) * (1 - smooth(0.9, 1.0, p))
        if k > 0.01:
            arms = 0.5 + 0.5 * np.cos(3 * self.theta + 9.0 * self.r / self.R - 18.0 * p)
            glow = (arms * np.exp(-self.r / (0.45 * self.R)) * (90.0 * k)).astype(np.float32)
            glow = cv2.GaussianBlur(glow, (0, 0), 1.5)
            light = np.clip(glow[..., None] * (GLOW / 255.0), 0, 255).astype(np.uint8)
            sub[:] = cv2.add(sub, cv2.resize(light, self.size, interpolation=cv2.INTER_LINEAR))
        return out
