"""Moves engine callbacks (worker / audio / hotkey threads) onto the Qt UI thread."""
import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage


class EngineBridge(QObject):
    frame = Signal(QImage)
    status = Signal(object)
    log = Signal(str, dict)

    def on_frame(self, rgb: np.ndarray) -> None:
        h, w = rgb.shape[:2]
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self.frame.emit(image)

    def on_status(self, status) -> None:
        self.status.emit(status)

    def on_log(self, key: str, kwargs: dict) -> None:
        self.log.emit(key, dict(kwargs))
