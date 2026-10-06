"""Map preview rendering.

Reads the delivered map.json directly - no engine, no OBJ round-trip. The biome grid
is an RLE of ids plus a legend carrying colour_hex, and instances carry world metres,
so a faithful preview is a pure CPU projection of the contract the generator already
publishes. That keeps the preview honest: it cannot show anything the engine would not
also read.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF

# Instance colours, keyed by the generator's object_type. Chosen to read against the
# dark-fantasy ground; water biomes deliberately get no marker.
INSTANCE_COLORS: Dict[str, str] = {
    "pine_snow_sparse": "#2f5d4a",
    "pine_snow_dense": "#274f3f",
    "tree_broadleaf": "#4a7a35",
    "tree_forest": "#3d6630",
    "tree_palm": "#5c8a3a",
    "birch_snow_dead": "#8a8577",
    "ice_boulder": "#7d8f9c",
    "rock": "#6b6659",
    "snow_drift": "#d8e2ea",
    "frozen_reed": "#8d7a45",
    "grass_tuft": "#6d9a3e",
    "reed": "#7d9440",
}
DEFAULT_INSTANCE = "#7a6a55"


def _hex_to_qcolor(value: str, alpha: int = 255) -> QColor:
    value = (value or "").lstrip("#")
    if len(value) != 6:
        return QColor(255, 0, 255, alpha)
    try:
        return QColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)
    except ValueError:
        return QColor(255, 0, 255, alpha)


def decode_rle(runs: List[List[int]], total: int) -> List[int]:
    """Expand [[value, run_length], ...] into a flat list of exactly `total` cells."""
    flat: List[int] = []
    for pair in runs or []:
        if len(pair) < 2:
            continue
        value, length = int(pair[0]), int(pair[1])
        flat.extend([value] * length)
        if len(flat) >= total:
            break
    if len(flat) < total:
        flat.extend([0] * (total - len(flat)))
    return flat[:total]


def render_map(summary, width: int = 720, height: int = 560,
               show_instances: bool = True, show_grid: bool = False) -> Optional[QImage]:
    """Render a MapSummary to a QImage. Returns None if the document is unusable."""
    grid = summary.grid
    w = int(grid.get("width", 0) or 0)
    h = int(grid.get("height", 0) or 0)
    if w < 1 or h < 1:
        return None

    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(_hex_to_qcolor("#0d0b0a"))

    tile = max(1, int(min(width / w, height / h)))
    ox = (width - tile * w) // 2
    oy = (height - tile * h) // 2

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    colors: Dict[int, QColor] = {}
    for entry in summary.legend or []:
        try:
            colors[int(entry.get("id", -1))] = _hex_to_qcolor(entry.get("color_hex", "#ff00ff"))
        except Exception:
            continue

    cells = decode_rle(grid.get("biome_rle"), w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            col = colors.get(cells[row + x])
            if col is None:
                col = QColor(255, 0, 255)
            painter.fillRect(ox + x * tile, oy + y * tile, tile, tile, col)

    if show_grid and tile >= 4:
        pen = QPen(QColor(0, 0, 0, 46))
        pen.setWidth(1)
        painter.setPen(pen)
        for x in range(w + 1):
            painter.drawLine(ox + x * tile, oy, ox + x * tile, oy + h * tile)
        for y in range(h + 1):
            painter.drawLine(ox, oy + y * tile, ox + w * tile, oy + y * tile)
        painter.setPen(Qt.PenStyle.NoPen)

    if show_instances:
        cell_m = float(grid.get("tile_size_meters", 8.0) or 8.0)
        px_per_m = tile / cell_m
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for inst in summary.instances or []:
            world = inst.get("world") or [0, 0, 0]
            if len(world) < 3:
                continue
            wx, wy, wz = float(world[0]), float(world[1]), float(world[2])
            # mapgen is Y-up with world_z = (y + 0.5) * cell; the preview is top-down so
            # screen y comes from world_z, and height only tints the marker.
            sx = ox + wx * px_per_m
            sy = oy + wz * px_per_m
            if not (ox - tile <= sx <= ox + w * tile + tile and oy - tile <= sy <= oy + h * tile + tile):
                continue
            col = _hex_to_qcolor(INSTANCE_COLORS.get(str(inst.get("type", "")), DEFAULT_INSTANCE))
            lift = max(0.0, min(1.0, wy / max(1e-6, float(grid.get("height_scale_meters", 120.0) or 120.0))))
            col = QColor(
                int(col.red() * (0.45 + 0.55 * lift)),
                int(col.green() * (0.45 + 0.55 * lift)),
                int(col.blue() * (0.45 + 0.55 * lift)), 235)
            r = max(1.2, min(tile * 0.48, 0.9 + lift * 1.6))
            painter.setBrush(QBrush(col))
            painter.setPen(QPen(QColor(12, 10, 9, 190), 0.8))
            painter.drawEllipse(QPointF(sx, sy), r, r)

    painter.end()
    return img
