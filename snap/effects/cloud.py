"""Cloud Puff: cartoon clouds roll in over the person, the person is swapped for the
empty room while hidden, then the clouds billow outward and dissolve."""
from dataclasses import dataclass

import cv2
import numpy as np

from snap.effects.base import (Effect, EffectContext, composite, mask_bbox, mask_centroid,
                               register, smooth, smoothstep)
from snap.effects.noise import fbm

HIGHLIGHT = np.array([252, 252, 255], np.float32)   # BGR, faintly warm white
SHADOW = np.array([228, 212, 200], np.float32)      # BGR, cool blue-grey
LIGHT_DIR = np.array([-0.45, -0.75, 0.55], np.float32)
LIGHT_DIR /= np.linalg.norm(LIGHT_DIR)

SWAP = (0.46, 0.54)       # person → plate while fully covered
CORE_IN = (0.16, 0.40)
CORE_OUT = (0.56, 0.80)
GROW = 0.30               # progress span over which a puff grows
DISPERSE_START = 0.55
DOWN = 3                  # cloud layer is rendered at 1/DOWN resolution


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    t = min(1.0, max(0.0, t))
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _make_sprite(radius: float, rng: np.random.Generator, seed: int) -> np.ndarray:
    """Premultiplied BGRA float32 sprite of one puff (a cluster of lit, fluffy discs)."""
    size = int(np.ceil(radius * 2.9)) | 1
    c = size / 2.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    grain = fbm(size, size, scale=max(4.0, radius * 0.35), octaves=3, seed=seed)

    discs = [(0.0, radius * 0.18, radius * 0.62)]
    for _ in range(int(rng.integers(5, 9))):
        ang = rng.uniform(np.pi * 0.95, np.pi * 2.05)          # mostly the upper half
        dist = rng.uniform(0.3, 0.6) * radius
        discs.append((np.cos(ang) * dist, np.sin(ang) * dist * 0.8, rng.uniform(0.3, 0.5) * radius))
    discs.sort(key=lambda d: d[1])                             # back (top) to front (bottom)

    rgb = np.zeros((size, size, 3), np.float32)
    alpha = np.zeros((size, size), np.float32)
    for ox, oy, rr in discs:
        nx = (xx - (c + ox)) / rr
        ny = (yy - (c + oy)) / rr
        r2 = nx * nx + ny * ny
        d = np.sqrt(r2) + (grain - 0.5) * 0.35
        a = smoothstep(1.0, 0.78, d)
        nz = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))
        lit = np.clip(nx * LIGHT_DIR[0] + ny * LIGHT_DIR[1] + nz * LIGHT_DIR[2], 0.0, 1.0)
        shade = (0.55 + 0.45 * lit)[..., None]
        color = SHADOW + (HIGHLIGHT - SHADOW) * shade
        rgb = color * a[..., None] + rgb * (1 - a[..., None])
        alpha = a + alpha * (1 - a)
    sprite = np.empty((size, size, 4), np.float32)
    sprite[..., :3] = rgb * alpha[..., None]
    sprite[..., 3] = alpha
    return sprite


@dataclass
class _Puff:
    x: float          # centre, half-res px
    y: float
    sprite: np.ndarray
    delay: float
    dx: float         # dispersal direction (unit)
    dy: float
    travel: float     # dispersal distance, half-res px
    gather: float     # how far outside it starts before rolling in, half-res px
    burst: bool = False


@register
class CloudPuff(Effect):
    id = "cloud"
    icon = "☁️"
    spills = True

    def prepare(self, ctx: EffectContext) -> None:
        super().prepare(ctx)
        rng = ctx.rng
        h, w = ctx.h, ctx.w
        self.hh, self.hw = -(-h // DOWN), -(-w // DOWN)
        m = ctx.mask
        bbox = mask_bbox(m) or (int(w * 0.35), int(h * 0.2), int(w * 0.65), h)
        x0, y0, x1, y1 = bbox
        cx, cy = mask_centroid(m) if m.max() > 0.5 else ((x0 + x1) / 2, (y0 + y1) / 2)
        big = max(x1 - x0, y1 - y0)
        R = float(np.clip(0.2 * big, 0.07 * h, 0.2 * h))       # full-res puff radius

        person = (m > 0.5).astype(np.uint8)
        grow = max(3, int(R * 0.25))
        dil = cv2.dilate(person, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1,) * 2))

        centres = []  # (x, y, radius, delay, gather, burst)
        step = 1.3 * R
        for gy in np.arange(y0, y1 + step, step):
            for gx in np.arange(x0, x1 + step, step):
                px = gx + rng.uniform(-0.2, 0.2) * R
                py = gy + rng.uniform(-0.2, 0.2) * R
                ix, iy = int(np.clip(px, 0, w - 1)), int(np.clip(py, 0, h - 1))
                if dil[iy, ix]:
                    centres.append((px, py, R * rng.uniform(0.9, 1.1), rng.uniform(0.04, 0.18), 0.0, False))

        contours, _ = cv2.findContours(person, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            outline = max(contours, key=cv2.contourArea)[:, 0, :].astype(np.float32)
            stride = max(1, int(1.4 * R))
            for px, py in outline[:: stride]:
                vx, vy = px - cx, py - cy
                n = max(np.hypot(vx, vy), 1e-3)
                ox, oy = px + vx / n * 0.25 * R, py + vy / n * 0.25 * R
                centres.append((ox, oy, R * rng.uniform(0.85, 1.05), rng.uniform(0.0, 0.08), R * 0.6, False))
            for i in range(8):
                px, py = outline[int(rng.integers(len(outline)))]
                centres.append((px, py, R * rng.uniform(0.3, 0.42), 0.40, 0.0, True))
        if not centres:
            centres.append((cx, cy, R, 0.0, 0.0, False))

        # a few sprite shapes, reused (sprites are the expensive part to build)
        def bucket(r):
            return max(6, int(round(r / DOWN / 6)) * 6)

        sprite_bank = {}
        for b in sorted({bucket(r) for _, _, r, _, _, _ in centres}):
            sprite_bank[b] = [_make_sprite(b, rng, ctx.seed * 131 + b * 7 + k) for k in range(2)]

        self.puffs = []
        for px, py, r, delay, gather, burst in centres:
            sprite = sprite_bank[bucket(r)][int(rng.integers(2))]
            vx, vy = px - cx, py - cy
            n = max(np.hypot(vx, vy), 1e-3)
            ang = np.arctan2(vy / n, vx / n) + rng.uniform(-0.5, 0.5)
            travel = (R / DOWN) * (rng.uniform(1.6, 2.6) if burst else rng.uniform(0.5, 1.3))
            self.puffs.append(_Puff(px / DOWN, py / DOWN, sprite, delay, float(np.cos(ang)),
                                    float(np.sin(ang)) - 0.25, travel, gather / DOWN, burst))
        self.puffs.sort(key=lambda q: (q.burst, q.y))

        # Dense core under the puffs: guarantees full coverage of the silhouette. It is
        # clipped to the puff cluster's envelope so it never shows as a person-shaped blob.
        core_grow = max(3, int(R * 0.12))
        core = cv2.dilate(person, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * core_grow + 1,) * 2))
        core = cv2.resize(core.astype(np.float32), (self.hw, self.hh), interpolation=cv2.INTER_AREA)
        envelope = np.zeros((self.hh, self.hw), np.uint8)
        for puff in self.puffs:
            if not puff.burst:
                cv2.circle(envelope, (int(puff.x), int(puff.y)), int(0.8 * R / DOWN), 1, -1)
        core = np.maximum(core, cv2.GaussianBlur(envelope.astype(np.float32), (0, 0), R / DOWN * 0.08))
        core = cv2.GaussianBlur(core, (0, 0), max(1.0, R / DOWN * 0.06))
        tex = fbm(self.hh, self.hw, scale=max(4.0, R / DOWN * 0.6), octaves=3, seed=ctx.seed + 5)
        alpha = smoothstep(0.3, 0.55, core + (tex - 0.5) * 0.3)
        shade = (0.7 + 0.3 * tex)[..., None]
        self.core = np.empty((self.hh, self.hw, 4), np.float32)
        self.core[..., :3] = (SHADOW + (HIGHLIGHT - SHADOW) * shade) * alpha[..., None]
        self.core[..., 3] = alpha

    # ------------------------------------------------------------ cloud layer (half res)
    def _layer(self, p: float):
        L = np.zeros((self.hh, self.hw, 4), np.float32)
        core_a = smooth(*CORE_IN, p) * (1 - smooth(*CORE_OUT, p))
        if core_a > 0:
            np.multiply(self.core, core_a, out=L)

        q = max(0.0, (p - DISPERSE_START) / (1 - DISPERSE_START))
        for puff in self.puffs:
            g = (p - puff.delay) / GROW
            if g <= 0:
                continue
            if puff.burst:
                t = (p - puff.delay) / 0.4
                scale = 0.4 + 0.6 * smooth(0.0, 1.0, t)
                fade = smooth(0.0, 0.15, t) * (1 - smooth(0.35, 1.0, t))
                shift = puff.travel * (1 - (1 - min(t, 1.0)) ** 2)
            else:
                scale = _ease_out_back(g) * (1 + 0.4 * q)
                fade = smooth(0.0, 0.1, p - puff.delay) * (1 - smooth(0.1, 1.0, q))
                shift = puff.travel * q ** 1.3 - puff.gather * (1 - min(g, 1.0))
            if fade <= 0.003 or scale <= 0.02:
                continue
            self._stamp(L, puff, scale, fade, puff.x + puff.dx * shift, puff.y + puff.dy * shift)
        return L

    @staticmethod
    def _stamp(L, puff, scale, fade, x, y):
        base = puff.sprite.shape[0]
        size = max(3, int(base * scale))
        spr = cv2.resize(puff.sprite, (size, size), interpolation=cv2.INTER_LINEAR)
        hh, hw = L.shape[:2]
        left, top = int(x - size / 2), int(y - size / 2)
        l0, t0 = max(0, left), max(0, top)
        r0, b0 = min(hw, left + size), min(hh, top + size)
        if r0 <= l0 or b0 <= t0:
            return
        s = spr[t0 - top:b0 - top, l0 - left:r0 - left]
        if fade < 1.0:
            s = s * fade
        roi = L[t0:b0, l0:r0]
        roi *= (1.0 - s[..., 3:4])
        roi += s

    def coverage(self, p: float) -> np.ndarray:
        L = self._layer(p)
        return cv2.resize(L[..., 3], (self.ctx.w, self.ctx.h), interpolation=cv2.INTER_LINEAR)

    def render(self, frame, mask, plate, p):
        base = composite(frame, plate, mask * smooth(*SWAP, p)) if p > SWAP[0] else frame.copy()
        L = self._layer(p)
        A = L[..., 3]
        rows = np.flatnonzero(A.max(axis=1) > 0.002)
        if len(rows) == 0:
            return base
        cols = np.flatnonzero(A.max(axis=0) > 0.002)
        h, w = frame.shape[:2]
        ht, hb = max(0, rows[0] - 1), min(self.hh, rows[-1] + 2)
        hl, hr = max(0, cols[0] - 1), min(self.hw, cols[-1] + 2)
        t, b, l, r = ht * DOWN, min(h, hb * DOWN), hl * DOWN, min(w, hr * DOWN)
        crop = L[ht:hb, hl:hr]
        a = crop[..., 3]
        color = (crop[..., :3] / np.maximum(a, 1e-4)[..., None]).clip(0, 255).astype(np.uint8)
        size = ((hr - hl) * DOWN, (hb - ht) * DOWN)
        color = cv2.resize(color, size, interpolation=cv2.INTER_LINEAR)[:b - t, :r - l]
        a = cv2.resize(a, size, interpolation=cv2.INTER_LINEAR)[:b - t, :r - l]
        base[t:b, l:r] = composite(base[t:b, l:r], color, a)
        return base
