"""Reusable Qt widgets: image preview with rectangle picking, histogram."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


def to_qimage(gray8: np.ndarray) -> QImage:
    gray8 = np.ascontiguousarray(gray8)
    h, w = gray8.shape
    return QImage(gray8.data, w, h, w, QImage.Format_Grayscale8).copy()


class ImageView(QWidget):
    """Shows an image scaled to fit. In pick mode, dragging a rectangle emits
    it in normalized (0..1) image coordinates."""

    rectPicked = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)
        self._image: QImage | None = None
        self._target = QRectF()
        self._drag_start: QPointF | None = None
        self._drag_now: QPointF | None = None
        self.pick_mode = False
        self.overlay_rect: tuple | None = None   # normalized rect to outline
        self.placeholder = "Open a RAW file (Ctrl+O)"

    def set_image(self, gray8: np.ndarray | None) -> None:
        self._image = None if gray8 is None else to_qimage(gray8)
        self.update()

    def set_pick_mode(self, on: bool) -> None:
        self.pick_mode = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    # --- geometry --------------------------------------------------------
    def _fit_rect(self) -> QRectF:
        if self._image is None:
            return QRectF()
        iw, ih = self._image.width(), self._image.height()
        scale = min(self.width() / iw, self.height() / ih)
        w, h = iw * scale, ih * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_norm(self, p: QPointF) -> tuple[float, float]:
        t = self._target
        x = min(max((p.x() - t.left()) / t.width(), 0.0), 1.0)
        y = min(max((p.y() - t.top()) / t.height(), 0.0), 1.0)
        return x, y

    def _from_norm(self, rect: tuple) -> QRectF:
        t = self._target
        x0, y0, x1, y1 = rect
        return QRectF(t.left() + x0 * t.width(), t.top() + y0 * t.height(),
                      (x1 - x0) * t.width(), (y1 - y0) * t.height())

    # --- events ----------------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(40, 40, 40))
        if self._image is None:
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignCenter, self.placeholder)
            return
        self._target = self._fit_rect()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self._target, self._image)
        pen = QPen(QColor(255, 80, 60), 2, Qt.DashLine)
        p.setPen(pen)
        if self._drag_start is not None and self._drag_now is not None:
            p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())
        elif self.overlay_rect is not None:
            p.drawRect(self._from_norm(self.overlay_rect))

    def mousePressEvent(self, e):
        if self.pick_mode and self._image is not None and e.button() == Qt.LeftButton:
            self._drag_start = self._drag_now = e.position()
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start is not None:
            self._drag_now = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start is None:
            return
        (x0, y0), (x1, y1) = self._to_norm(self._drag_start), self._to_norm(e.position())
        self._drag_start = self._drag_now = None
        rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        # A plain click samples a small square around the point.
        if rect[2] - rect[0] < 0.005 or rect[3] - rect[1] < 0.005:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            rect = (max(cx - 0.01, 0), max(cy - 0.01, 0), min(cx + 0.01, 1), min(cy + 0.01, 1))
        self.update()
        self.rectPicked.emit(rect)


class HistogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)
        self._hist: np.ndarray | None = None

    def set_image(self, gray8: np.ndarray | None) -> None:
        if gray8 is None:
            self._hist = None
        else:
            h = np.bincount(gray8.ravel(), minlength=256).astype(np.float64)
            self._hist = np.sqrt(h / max(h.max(), 1))   # sqrt keeps small bins visible
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 30))
        if self._hist is None:
            return
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(200, 200, 200))
        bar = w / 256
        for i, v in enumerate(self._hist):
            bh = v * (h - 4)
            p.drawRect(QRectF(i * bar, h - bh, bar + 0.5, bh))
        # Clipping warnings at the ends.
        p.setBrush(QColor(255, 80, 60))
        for i in (0, 255):
            if self._hist[i] > 0.15:
                p.drawRect(QRectF(i * bar - (2 if i else 0), 0, 3, 6))
