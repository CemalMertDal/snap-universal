"""Small custom-painted widgets that follow the Fluent theme."""
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import isDarkTheme, themeColor

from snap.i18n import t


def fixed_height(widget):
    """Keep a label at its natural height so layouts don't pad it."""
    widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)
    return widget


def muted(label):
    """Secondary text colour for a Fluent label, in both themes."""
    label.setTextColor(QColor(96, 96, 106), QColor(160, 160, 172))
    return label


class PreviewView(QWidget):
    """Aspect-correct video preview with rounded corners and an optional overlay text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: QImage | None = None
        self._overlay = ""
        self._placeholder = t("home.placeholder")
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, image) -> None:
        if isinstance(image, np.ndarray):
            h, w = image.shape[:2]
            image = QImage(image.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self._image = image
        self.update()

    def clear(self) -> None:
        self._image = None
        self.update()

    def set_overlay(self, text: str) -> None:
        if text != self._overlay:
            self._overlay = text
            self.update()

    def _target(self) -> QRectF:
        r = QRectF(self.rect())
        aspect = 16 / 9
        if self._image is not None and self._image.height():
            aspect = self._image.width() / self._image.height()
        w, h = r.width(), r.height()
        if w / h > aspect:
            w = h * aspect
        else:
            h = w / aspect
        return QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        target = self._target()
        path = QPainterPath()
        path.addRoundedRect(target, 10, 10)
        p.setClipPath(path)
        dark = isDarkTheme()
        p.fillRect(target, QColor(28, 28, 32) if dark else QColor(232, 232, 238))
        if self._image is not None:
            p.drawImage(target, self._image)
        else:
            p.setPen(QColor(170, 170, 180) if dark else QColor(110, 110, 120))
            f = QFont(self.font())
            f.setPointSize(11)
            p.setFont(f)
            p.drawText(target, Qt.AlignmentFlag.AlignCenter, self._placeholder)
        if self._overlay:
            p.fillRect(target, QColor(0, 0, 0, 110))
            f = QFont(self.font())
            f.setPointSize(22)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255))
            p.drawText(target, Qt.AlignmentFlag.AlignCenter, self._overlay)
        p.end()


class LevelMeter(QWidget):
    """Horizontal level bar with a threshold marker; turns green above the marker."""

    THRESHOLD = 0.7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._enabled = True
        self.setFixedHeight(10)
        self.setMinimumWidth(160)

    def set_level(self, level: float) -> None:
        level = float(min(1.0, max(0.0, level)))
        if abs(level - self._level) > 0.004:
            self._level = level
            self.update()

    def set_active(self, active: bool) -> None:
        self._enabled = active
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        radius = r.height() / 2
        dark = isDarkTheme()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 25))
        p.drawRoundedRect(r, radius, radius)
        if self._enabled and self._level > 0:
            fill = QRectF(r.left(), r.top(), r.width() * self._level, r.height())
            color = QColor(46, 204, 113) if self._level >= self.THRESHOLD else themeColor()
            p.setBrush(color)
            p.drawRoundedRect(fill, radius, radius)
        x = r.left() + r.width() * self.THRESHOLD
        p.setPen(QPen(QColor(255, 255, 255, 200) if dark else QColor(0, 0, 0, 160), 2))
        p.drawLine(int(x), int(r.top()) - 1, int(x), int(r.bottom()) + 1)
        p.end()


class StatusDot(QWidget):
    COLORS = {"stopped": QColor(150, 150, 160), "live": QColor(46, 204, 113),
              "vanishing": QColor(241, 196, 15), "appearing": QColor(241, 196, 15),
              "gone": QColor(155, 89, 182), "warning": QColor(230, 126, 34)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = self.COLORS["stopped"]
        self.setFixedSize(12, 12)

    def set_state(self, state: str) -> None:
        self._color = self.COLORS.get(state, self.COLORS["stopped"])
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(1, 1, 10, 10))
        p.end()
