"""Nine-patch skin layer.

Panels, cards and the title bar can be painted with a generated frame instead of the
QSS ``border`` rules. The frame is drawn by ``tools/make_skins.py`` from the same
palette constants as the stylesheet, so the two cannot drift, and it is a real
nine-slice: the corner slice carries the ornament and is never stretched.

Skins are optional. ``SkinManager.apply`` is a no-op when the assets are missing, so
the application still runs from a clean checkout with the plain QSS look.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QWidget

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "skins"


def _load(name: str) -> Optional[QPixmap]:
    path = ASSETS / name
    if not path.exists():
        return None
    pm = QPixmap(str(path))
    return pm if not pm.isNull() else None


def draw_nine_patch(painter: QPainter, pm: QPixmap, rect: QRect,
                    margin: int) -> None:
    """Stretch the middle of ``pm`` into ``rect``, keeping corners crisp.

    Qt's stylesheet ``border-image`` is unreliable for this (rounded corners and
    non-uniform scaling are the problem cases), so the nine slices are blitted
    manually. Straight ``drawPixmap`` with source rects, which is both predictable and
    fast enough at panel sizes.
    """
    m = max(1, min(margin, pm.width() // 2 - 1, pm.height() // 2 - 1))
    sw, sh = pm.width(), pm.height()
    cx, cy = sw - m, sh - m
    dx, dy = rect.x(), rect.y()
    dw, dh = rect.width(), rect.height()
    if dw <= 2 * m or dh <= 2 * m:
        painter.drawPixmap(rect, pm)
        return

    # Corners.
    painter.drawPixmap(QRect(dx, dy, m, m), pm, QRect(0, 0, m, m))
    painter.drawPixmap(QRect(dx + dw - m, dy, m, m), pm, QRect(cx, 0, m, m))
    painter.drawPixmap(QRect(dx, dy + dh - m, m, m), pm, QRect(0, cy, m, m))
    painter.drawPixmap(QRect(dx + dw - m, dy + dh - m, m, m), pm, QRect(cx, cy, m, m))
    # Edges.
    painter.drawPixmap(QRect(dx + m, dy, dw - 2 * m, m), pm, QRect(m, 0, cx - m, m))
    painter.drawPixmap(QRect(dx + m, dy + dh - m, dw - 2 * m, m), pm, QRect(m, cy, cx - m, m))
    painter.drawPixmap(QRect(dx, dy + m, m, dh - 2 * m), pm, QRect(0, m, m, cy - m))
    painter.drawPixmap(QRect(dx + dw - m, dy + m, m, dh - 2 * m), pm, QRect(cx, m, m, cy - m))
    # Centre.
    painter.drawPixmap(QRect(dx + m, dy + m, dw - 2 * m, dh - 2 * m), pm,
                       QRect(m, m, cx - m, cy - m))
