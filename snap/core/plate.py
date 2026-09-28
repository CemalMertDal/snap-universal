"""Empty-room plate: the per-pixel median of several person-free frames."""
import numpy as np


class PlateBuilder:
    def __init__(self, needed: int = 15, min_ok: int = 5, max_cover: float = 0.015):
        self.needed = needed
        self.min_ok = min_ok
        self.max_cover = max_cover
        self.attempts = 0
        self.frames: list[np.ndarray] = []

    @property
    def accepted(self) -> int:
        return len(self.frames)

    @property
    def done(self) -> bool:
        return self.attempts >= self.needed

    def add(self, frame: np.ndarray, mask: np.ndarray) -> None:
        self.attempts += 1
        if float(mask.mean()) <= self.max_cover:
            self.frames.append(frame.copy())

    def build(self) -> np.ndarray | None:
        if len(self.frames) < self.min_ok:
            return None
        stack = np.stack(self.frames)
        k = len(self.frames) // 2
        # partition is much cheaper than a full median sort
        return np.partition(stack, k, axis=0)[k]
