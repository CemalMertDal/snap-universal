"""Synthetic scene used by effect tests: a textured room and a person-shaped blob."""
import cv2
import numpy as np


def make_scene(h: int = 720, w: int = 1280, seed: int = 0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    plate = np.empty((h, w, 3), np.float32)
    plate[..., 0] = 90 + 60 * (xx / w)
    plate[..., 1] = 110 + 40 * (yy / h)
    plate[..., 2] = 140 - 30 * (xx / w)
    grain = cv2.resize(rng.random((h // 16, w // 16)).astype(np.float32), (w, h),
                       interpolation=cv2.INTER_CUBIC)
    plate += (grain[..., None] - 0.5) * 40
    plate = np.clip(plate, 0, 255).astype(np.uint8)

    person = np.zeros((h, w), np.uint8)
    cx = w // 2
    cv2.ellipse(person, (cx, int(h * 0.30)), (int(w * 0.055), int(h * 0.11)), 0, 0, 360, 255, -1)
    cv2.ellipse(person, (cx, int(h * 0.85)), (int(w * 0.16), int(h * 0.42)), 0, 180, 360, 255, -1)
    cv2.rectangle(person, (cx - int(w * 0.16), int(h * 0.85)), (cx + int(w * 0.16), h), 255, -1)
    mask = cv2.GaussianBlur(person.astype(np.float32) / 255.0, (0, 0), 3)

    skin = np.empty((h, w, 3), np.float32)
    skin[..., 0] = 60 + 50 * np.sin(xx / 23.0)
    skin[..., 1] = 80 + 40 * np.cos(yy / 17.0)
    skin[..., 2] = 200
    frame = plate.astype(np.float32) * (1 - mask[..., None]) + skin * mask[..., None]
    frame = np.clip(frame, 0, 255).astype(np.uint8)
    return frame, plate, mask
