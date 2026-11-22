"""Reusable Qt widgets: image preview with rectangle picking, histogram, film strip."""
from __future__ import annotations

import sys

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QSizePolicy, QWidget


MAC = sys.platform == "darwin"


def keys_text(text: str) -> str:
    """Shortcut names as the user sees them. Qt already maps Ctrl to the
    Command key on macOS; this only fixes the words in labels and help."""
    if not MAC:
        return text
    for a, b in (("Ctrl+click", "⌘-click"), ("Ctrl+Shift+", "⇧⌘"), ("Ctrl+", "⌘"),
                 ("PgUp / PgDn", "fn↑ / fn↓")):
        text = text.replace(a, b)
    return text


def to_qimage(gray8: np.ndarray) -> QImage:
    gray8 = np.ascontiguousarray(gray8)
    h, w = gray8.shape
    return QImage(gray8.data, w, h, w, QImage.Format_Grayscale8).copy()


MIN_CROP = 0.05      # smallest crop side, as a fraction of the image
GRAB = 9             # pixels around an edge that grab it


class ImageView(QWidget):
    """Shows an image scaled to fit, in normalized (0..1) image coordinates.

    - Pick mode: dragging a rectangle emits rectPicked.
    - Crop mode: the crop is shown with the outside darkened; drag an edge or
      corner to resize, drag inside to move, drag outside to draw a new one.
      cropEdited is emitted when the mouse is released."""

    rectPicked = Signal(tuple)
    cropEdited = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)
        self._image: QImage | None = None
        self._target = QRectF()
        self._drag_start: QPointF | None = None
        self._drag_now: QPointF | None = None
        self.pick_mode = False
        # Outlines to draw: (normalized rect, QColor), in image coordinates.
        self.overlays: list[tuple[tuple, QColor]] = []
        self.placeholder = keys_text("Open a roll: press Ctrl+O and pick any scan in the folder,\nor drag the scans (or their folder) here")
        self.crop_mode = False
        self.crop_rect: tuple | None = None
        self._crop_drag = None      # (grab, start point, rect at start)
        self.setMouseTracking(True)

    def set_image(self, gray8: np.ndarray | None) -> None:
        self._image = None if gray8 is None else to_qimage(gray8)
        self.update()

    def set_pick_mode(self, on: bool) -> None:
        self.pick_mode = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def set_crop_mode(self, on: bool, rect: tuple | None = None) -> None:
        """Enter crop mode showing rect (None = no crop yet), or leave it."""
        self.crop_mode = on
        self.crop_rect = rect if on else None
        self._crop_drag = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

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
        if self._drag_start is not None and self._drag_now is not None:
            p.setPen(QPen(QColor(255, 210, 60), 2, Qt.DashLine))
            p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())
            return
        for rect, color in self.overlays:
            p.setPen(QPen(color, 2, Qt.DashLine))
            p.drawRect(self._from_norm(rect))
        if self.crop_mode and self.crop_rect is not None:
            self._paint_crop(p)

    def _paint_crop(self, p: QPainter):
        r, t = self._from_norm(self.crop_rect), self._target
        shade = QColor(0, 0, 0, 150)
        p.fillRect(QRectF(t.left(), t.top(), t.width(), r.top() - t.top()), shade)
        p.fillRect(QRectF(t.left(), r.bottom(), t.width(), t.bottom() - r.bottom()), shade)
        p.fillRect(QRectF(t.left(), r.top(), r.left() - t.left(), r.height()), shade)
        p.fillRect(QRectF(r.right(), r.top(), t.right() - r.right(), r.height()), shade)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for k in (1, 2):   # rule of thirds
            x = r.left() + r.width() * k / 3
            y = r.top() + r.height() * k / 3
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor(255, 210, 60), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setBrush(QColor(255, 210, 60))
        s = 10
        c = r.center()
        for x in (r.left(), c.x(), r.right()):
            for y in (r.top(), c.y(), r.bottom()):
                if (x, y) != (c.x(), c.y()):
                    p.drawRect(QRectF(x - s / 2, y - s / 2, s, s))

    # --- crop editing ------------------------------------------------------
    def _crop_grab(self, pos: QPointF) -> str:
        """What the mouse is over: edges/corners as a combination of l/r/t/b,
        'move' inside the crop, or 'new' outside it."""
        if self.crop_rect is None:
            return "new"
        r = self._from_norm(self.crop_rect)
        x, y = pos.x(), pos.y()
        if not (r.left() - GRAB <= x <= r.right() + GRAB and r.top() - GRAB <= y <= r.bottom() + GRAB):
            return "new"
        g = ""
        if abs(x - r.left()) <= GRAB:
            g += "l"
        elif abs(x - r.right()) <= GRAB:
            g += "r"
        if abs(y - r.top()) <= GRAB:
            g += "t"
        elif abs(y - r.bottom()) <= GRAB:
            g += "b"
        return g or "move"

    _CURSORS = {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor, "t": Qt.SizeVerCursor,
                "b": Qt.SizeVerCursor, "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
                "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor, "move": Qt.SizeAllCursor,
                "new": Qt.CrossCursor}

    def _crop_update(self, pos: QPointF):
        grab, (sx, sy), (x0, y0, x1, y1) = self._crop_drag
        px, py = self._to_norm(pos)
        dx, dy = px - sx, py - sy
        if grab == "new":
            x0, x1 = sorted((sx, px))
            y0, y1 = sorted((sy, py))
        elif grab == "move":
            dx = min(max(dx, -x0), 1 - x1)
            dy = min(max(dy, -y0), 1 - y1)
            x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
        else:
            if "l" in grab:
                x0 = min(max(x0 + dx, 0.0), x1 - MIN_CROP)
            if "r" in grab:
                x1 = max(min(x1 + dx, 1.0), x0 + MIN_CROP)
            if "t" in grab:
                y0 = min(max(y0 + dy, 0.0), y1 - MIN_CROP)
            if "b" in grab:
                y1 = max(min(y1 + dy, 1.0), y0 + MIN_CROP)
        self.crop_rect = (x0, y0, x1, y1)
        self.update()

    def mousePressEvent(self, e):
        if self._image is None or e.button() != Qt.LeftButton:
            return
        if self.crop_mode:
            start = self._to_norm(e.position())
            self._crop_drag = (self._crop_grab(e.position()), start, self.crop_rect or (*start, *start))
        elif self.pick_mode:
            self._drag_start = self._drag_now = e.position()
            self.update()

    def mouseMoveEvent(self, e):
        if self._crop_drag is not None:
            self._crop_update(e.position())
        elif self.crop_mode and self._image is not None:
            self.setCursor(self._CURSORS[self._crop_grab(e.position())])
        elif self._drag_start is not None:
            self._drag_now = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._crop_drag is not None:
            before = self._crop_drag[2]
            self._crop_update(e.position())
            self._crop_drag = None
            x0, y0, x1, y1 = self.crop_rect
            if x1 - x0 < MIN_CROP or y1 - y0 < MIN_CROP:   # a click, not a drag: keep the old crop
                self.crop_rect = before if before[2] - before[0] >= MIN_CROP else None
                self.update()
                return
            self.cropEdited.emit(self.crop_rect)
            return
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


class FilmStrip(QListWidget):
    """Horizontal strip of frame thumbnails. Multi-select with Ctrl/Shift."""

    THUMB = QSize(150, 100)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setIconSize(self.THUMB)
        self.setGridSize(QSize(self.THUMB.width() + 14, self.THUMB.height() + 30))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(self.THUMB.height() + 52)
        self.setStyleSheet("QListWidget { background: #202020; color: #ccc; }")
        self._items: dict[str, QListWidgetItem] = {}

    def wheelEvent(self, e):
        """The mouse wheel scrolls the strip sideways."""
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - (e.angleDelta().y() or e.angleDelta().x()))
        e.accept()

    def set_frames(self, names: list[str]) -> None:
        self.clear()
        self._items = {}
        blank = QPixmap(self.THUMB)
        blank.fill(QColor(55, 55, 55))
        for name in names:
            item = QListWidgetItem(QIcon(blank), name)
            item.setData(Qt.UserRole, name)
            item.setTextAlignment(Qt.AlignHCenter)
            self.addItem(item)
            self._items[name] = item

    def set_thumbnail(self, name: str, gray8: np.ndarray) -> None:
        item = self._items.get(name)
        if item is None:
            return
        pix = QPixmap.fromImage(to_qimage(gray8)).scaled(
            self.THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item.setIcon(QIcon(pix))

    def set_edited(self, name: str, edited: bool) -> None:
        item = self._items.get(name)
        if item is not None:
            item.setText(("● " if edited else "") + name)

    def icon(self, name: str) -> QIcon:
        item = self._items.get(name)
        return item.icon() if item else QIcon()

    def current_name(self) -> str | None:
        item = self.currentItem()
        return item.data(Qt.UserRole) if item else None

    def selected_names(self) -> list[str]:
        names = [i.data(Qt.UserRole) for i in self.selectedItems()]
        order = {n: k for k, n in enumerate(self._items)}
        return sorted(names, key=order.get)

    def select_name(self, name: str) -> None:
        item = self._items.get(name)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)
