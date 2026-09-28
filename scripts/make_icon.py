"""Draws the app icon: a white cartoon puff on a violet gradient tile.
Writes assets/icon.png (256 px) and assets/icon.ico (16-256 px, PNG-compressed)."""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QRadialGradient)

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _star(cx, cy, r):
    path = QPainterPath()
    pts = []
    for i in range(8):
        rad = r if i % 2 == 0 else r * 0.28
        ang = i * 3.14159265 / 4 - 3.14159265 / 2
        pts.append(QPointF(cx + rad * __import__("math").cos(ang), cy + rad * __import__("math").sin(ang)))
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    return path


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)

    tile = QRectF(s * 0.03, s * 0.03, s * 0.94, s * 0.94)
    grad = QLinearGradient(tile.topLeft(), tile.bottomRight())
    grad.setColorAt(0.0, QColor("#8A7BFF"))
    grad.setColorAt(1.0, QColor("#B04CE0"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(tile, s * 0.22, s * 0.22)

    glow = QRadialGradient(QPointF(s * 0.3, s * 0.2), s * 0.7)
    glow.setColorAt(0.0, QColor(255, 255, 255, 60))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(glow)
    p.drawRoundedRect(tile, s * 0.22, s * 0.22)

    cloud = QPainterPath()
    cloud.setFillRule(Qt.FillRule.WindingFill)
    for cx, cy, r in ((0.36, 0.58, 0.16), (0.52, 0.47, 0.21), (0.68, 0.58, 0.15)):
        cloud.addEllipse(QPointF(s * cx, s * cy), s * r, s * r)
    cloud.addRoundedRect(QRectF(s * 0.22, s * 0.55, s * 0.58, s * 0.18), s * 0.09, s * 0.09)
    cloud = cloud.simplified()

    p.setBrush(QColor(60, 20, 120, 70))
    p.drawPath(cloud.translated(0, s * 0.035))
    body = QLinearGradient(QPointF(0, s * 0.28), QPointF(0, s * 0.74))
    body.setColorAt(0.0, QColor("#FFFFFF"))
    body.setColorAt(1.0, QColor("#E6E0FF"))
    p.setBrush(body)
    p.drawPath(cloud)

    if size >= 32:
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(_star(s * 0.77, s * 0.25, s * 0.09))
        p.drawPath(_star(s * 0.86, s * 0.40, s * 0.045))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    draw(256).save(str(out / "icon.png"))
    images = [png_bytes(draw(n)) for n in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, offset = b"", 6 + 16 * len(images)
    for n, data in zip(SIZES, images):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    (out / "icon.ico").write_bytes(header + entries + b"".join(images))
    print("wrote", out / "icon.png", out / "icon.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
