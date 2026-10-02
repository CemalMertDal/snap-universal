"""Empty-room plate: the per-pixel median of a burst of frames (anything that moves
through the picture during the burst drops out)."""
import numpy as np


class PlateBuilder:
    def __init__(self, needed: int = 15):
        self.needed = needed
        self.frames: list[np.ndarray] = []

    @property
    def done(self) -> bool:
        return len(self.frames) >= self.needed

    def add(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def build(self) -> np.ndarray | None:
        if not self.frames:
            return None
        stack = np.stack(self.frames)
        k = len(self.frames) // 2
        # partition is much cheaper than a full median sort
        return np.partition(stack, k, axis=0)[k]
