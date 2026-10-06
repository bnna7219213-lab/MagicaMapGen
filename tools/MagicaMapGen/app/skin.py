"""Nine-patch skin layer.

Panels, cards and the title bar can be painted with a generated frame instead of the
QSS ``border`` rules. The frame is drawn by ``tools/make_skins.py`` from the same
palette constants as the stylesheet, so the two cannot drift, and it is a real
nine-slice: the corner slice carries the ornament and is never stretched.

Skins are optional. Every entry point degrades to the plain QSS look when the assets
are absent, so the application still runs from a clean checkout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QWidget

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "skins"


def _load(name: str) -> Optional[QPixmap]:
    path = ASSETS / name
    if not path.exists():
        return None
    pm = QPixmap(str(path))
    return pm if not pm.isNull() else None


def draw_nine_patch(painter: QPainter, pm: QPixmap, rect: QRect, margin: int) -> None:
    """Stretch the middle of ``pm`` into ``rect``, keeping corners crisp.

    Qt's stylesheet ``border-image`` is unreliable for this (rounded corners and
    non-uniform scaling are the problem cases), so the nine slices are blitted
    manually -- predictable, and fast enough at panel sizes.
    """
    m = max(1, min(margin, pm.width() // 2 - 1, pm.height() // 2 - 1))
    sw, sh = pm.width(), pm.height()
    cx, cy = sw - m, sh - m
    dx, dy = rect.x(), rect.y()
    dw, dh = rect.width(), rect.height()
    if dw <= 2 * m or dh <= 2 * m:
        painter.drawPixmap(rect, pm)
        return

    painter.drawPixmap(QRect(dx, dy, m, m), pm, QRect(0, 0, m, m))
    painter.drawPixmap(QRect(dx + dw - m, dy, m, m), pm, QRect(cx, 0, m, m))
    painter.drawPixmap(QRect(dx, dy + dh - m, m, m), pm, QRect(0, cy, m, m))
    painter.drawPixmap(QRect(dx + dw - m, dy + dh - m, m, m), pm, QRect(cx, cy, m, m))
    painter.drawPixmap(QRect(dx + m, dy, dw - 2 * m, m), pm, QRect(m, 0, cx - m, m))
    painter.drawPixmap(QRect(dx + m, dy + dh - m, dw - 2 * m, m), pm, QRect(m, cy, cx - m, m))
    painter.drawPixmap(QRect(dx, dy + m, m, dh - 2 * m), pm, QRect(0, m, m, cy - m))
    painter.drawPixmap(QRect(dx + dw - m, dy + m, m, dh - 2 * m), pm, QRect(cx, m, m, cy - m))
    painter.drawPixmap(QRect(dx + m, dy + m, dw - 2 * m, dh - 2 * m), pm,
                       QRect(m, m, cx - m, cy - m))


class SkinnedFrame(QFrame):
    """A QFrame that paints a nine-patch skin behind its children.

    Falls back to the stylesheet border when the skin assets are missing or when
    ``skin_name`` is empty, so switching skins off is always safe.
    """

    def __init__(self, parent=None, skin_name: str = "frame_dark.png",
                 margin: int = 18, object_name: str = "Panel"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._skin_name = skin_name
        self._margin = margin
        self._pm: Optional[QPixmap] = _load(skin_name)
        self._apply_inset()

    def _inset(self) -> int:
        """Padding kept clear of the painted band.

        Derived from the slice rather than equal to it: the slice only has to be
        wide enough to carry the corner ornament, while every pixel of padding is
        taken out of the content area. An inset equal to the slice clipped the
        parameter rows, so this is deliberately smaller.
        """
        return max(6, self._margin - 6)

    def _apply_inset(self) -> None:
        inset = self._inset()
        if self._pm is not None:
            # The stylesheet border would double up with the painted frame.
            self.setStyleSheet("QFrame { border: none; background: transparent; }")
            self.setContentsMargins(inset, inset, inset, inset)
        else:
            # Reverting: hand the border and spacing back to the stylesheet.
            self.setStyleSheet("")
            self.setContentsMargins(0, 0, 0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, self._pm is not None)

    @property
    def skinned(self) -> bool:
        return self._pm is not None

    def set_skin(self, name: str, margin: int = None) -> None:
        """Apply a skin by asset filename. An empty name reverts to the QSS border."""
        self._skin_name = name
        if margin is not None:
            self._margin = margin
        self._pm = _load(name) if name else None
        self._apply_inset()
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        if self._pm is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        draw_nine_patch(painter, self._pm, self.rect(), self._margin)
        painter.end()


class SkinManager:
    """Holds the loaded skins and flips every registered frame at once."""

    #: Logical role -> (asset filename, nine-patch margin)
    ROLES = {
        "panel": ("frame_dark.png", 18),
        "card": ("frame_dark_small.png", 14),
        "plain": ("frame_plain.png", 18),
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._frames = []

    def register(self, frame: SkinnedFrame, role: str = "panel") -> SkinnedFrame:
        self._frames.append((frame, role))
        if self.enabled:
            name, margin = self.ROLES.get(role, self.ROLES["panel"])
            frame.set_skin(name, margin)
        return frame

    def available(self) -> Dict[str, bool]:
        return {role: _load(name) is not None
                for role, (name, _) in self.ROLES.items()}

    def set_enabled(self, on: bool) -> None:
        """Toggle skins. Reverting clears the override so the QSS border returns."""
        self.enabled = on
        for frame, role in self._frames:
            if on:
                name, margin = self.ROLES.get(role, self.ROLES["panel"])
                frame.set_skin(name, margin)
            else:
                frame.set_skin("")
            frame.update()
