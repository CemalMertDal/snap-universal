"""Where frames come from: a real camera, or a synthetic scene for tests."""
from typing import Protocol

import cv2
import numpy as np


class CameraError(RuntimeError):
    pass


class FrameSource(Protocol):
    def open(self) -> tuple[int, int]: ...

    def read(self) -> np.ndarray | None: ...

    def close(self) -> None: ...


class CameraSource:
    def __init__(self, index: int, width: int, height: int, fps: int = 30):
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self.cap = None

    def open(self) -> tuple[int, int]:
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if not ok or frame is None:
            cap.release()
            raise CameraError("camera gave no frame")
        self.cap = cap
        h, w = frame.shape[:2]
        return w - w % 2, h - h % 2

    def read(self) -> np.ndarray | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        h, w = frame.shape[:2]
        return frame[: h - h % 2, : w - w % 2]

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class SyntheticSource:
    """A textured room with a person-shaped blob swaying in it. `person` hides it."""

    def __init__(self, width: int = 640, height: int = 360):
        self.width, self.height = width, height
        self.person = True
        self.closed = False
        self.t = 0
        rng = np.random.default_rng(0)
        room = cv2.resize(rng.integers(40, 200, (height // 8, width // 8, 3), dtype=np.uint8),
                          (width, height), interpolation=cv2.INTER_CUBIC)
        self.room = room
        self.last_mask = np.zeros((height, width), np.float32)

    def open(self) -> tuple[int, int]:
        self.closed = False
        return self.width, self.height

    def read(self) -> np.ndarray | None:
        self.t += 1
        frame = self.room.copy()
        mask = np.zeros((self.height, self.width), np.uint8)
        if self.person:
            cx = int(self.width / 2 + np.sin(self.t / 15) * self.width * 0.05)
            cv2.ellipse(mask, (cx, int(self.height * 0.35)), (self.width // 14, self.height // 7),
                        0, 0, 360, 255, -1)
            cv2.ellipse(mask, (cx, self.height), (self.width // 6, int(self.height * 0.45)),
                        0, 180, 360, 255, -1)
            frame[mask > 0] = (60, 90, 220)
        self.last_mask = mask.astype(np.float32) / 255.0
        return frame

    def close(self) -> None:
        self.closed = True
