from typing import Protocol

import numpy as np


class VirtualOutput(Protocol):
    name: str

    def send(self, frame_bgr: np.ndarray) -> None: ...

    def close(self) -> None: ...


class VCamError(RuntimeError):
    """code: "not_installed" | "in_use" | "failed"."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
