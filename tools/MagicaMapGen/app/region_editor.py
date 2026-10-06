"""Region editor for the 局部概率化 layer.

A region is a normalised shape plus per-category overrides. It is the fourth layer of
the model (theme -> category -> distribution -> region) and the part a designer uses
most, so it gets a real editor rather than a JSON text box. The widget emits a plain
dict shaped exactly like mapgen's config ``regions`` array, and the generator stays the
only thing that interprets it.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import theme

SHAPES = ("rect", "circle", "polygon", "all")


class RegionEditor(QWidget):
    """Add, edit and remove regions; emits a mapgen-compatible list."""

    changed = pyqtSignal()

    def __init__(self, categories: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.categories = list(categories or [])
        self.regions: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.list = QListWidget()
        self.list.setMinimumHeight(90)
        self.list.currentRowChanged.connect(self._on_select)
        root.addWidget(self.list)

        buttons = QHBoxLayout()
        for text, slot in (("Add rect", lambda: self.add_region("rect")),
                           ("Add circle", lambda: self.add_region("circle")),
                           ("Add all", lambda: self.add_region("all")),
                           ("Remove", self.remove_selected)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        root.addLayout(buttons)

        self.editor = QWidget()
        form = QFormLayout(self.editor)
        form.setContentsMargins(6, 0, 0, 0)
        form.setSpacing(6)

        self.ed_id = QLineEdit()
        self.ed_id.setPlaceholderText("region_id")
        self.ed_id.textChanged.connect(self._on_field_changed)
        form.addRow("Id", self.ed_id)

        # Priority resolves which region owns a cell when two of them overlap. It is
        # an int, and mapgen requires the values to be distinct, so the SpinBox starts
        # at 1 and the editor assigns the next free value for each new region.
        self.ed_priority = QSpinBox()
        self.ed_priority.setRange(0, 999)
        self.ed_priority.setToolTip(
            "Higher wins when regions overlap. Values must be unique across regions.")
        self.ed_priority.valueChanged.connect(self._on_field_changed)
        form.addRow("Priority", self.ed_priority)

        self.ed_shape = QComboBox()
        self.ed_shape.addItems(list(SHAPES))
        self.ed_shape.currentTextChanged.connect(self._on_shape_changed)
        form.addRow("Shape", self.ed_shape)

        # rect / all share the normalised bounding box; circle uses cx, cy, r.
        self.rect_box = QWidget()
        grid = QGridLayout(self.rect_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        self.ed_x0 = self._spin(0.0, 1.0, 0.01)
        self.ed_y0 = self._spin(0.0, 1.0, 0.01)
        self.ed_x1 = self._spin(0.0, 1.0, 0.01)
        self.ed_y1 = self._spin(0.0, 1.0, 0.01)
        for col, (name, w) in enumerate((("x0", self.ed_x0), ("y0", self.ed_y0),
                                         ("x1", self.ed_x1), ("y1", self.ed_y1))):
            grid.addWidget(QLabel(name), 0, col)
            grid.addWidget(w, 1, col)
        form.addRow("Bounds", self.rect_box)

        self.circle_box = QWidget()
        cgrid = QGridLayout(self.circle_box)
        cgrid.setContentsMargins(0, 0, 0, 0)
        cgrid.setHorizontalSpacing(6)
        self.ed_cx = self._spin(0.0, 1.0, 0.01)
        self.ed_cy = self._spin(0.0, 1.0, 0.01)
        self.ed_r = self._spin(0.01, 1.0, 0.01)
        for col, (name, w) in enumerate((("cx", self.ed_cx), ("cy", self.ed_cy),
                                         ("r", self.ed_r))):
            cgrid.addWidget(QLabel(name), 0, col)
            cgrid.addWidget(w, 1, col)
        form.addRow("Circle", self.circle_box)

        self.poly_box = QWidget()
        pform = QFormLayout(self.poly_box)
        pform.setContentsMargins(0, 0, 0, 0)
        self.ed_points = QLineEdit()
        self.ed_points.setPlaceholderText("0.2,0.2 0.8,0.2 0.5,0.7")
        self.ed_points.setToolTip("Whitespace separated x,y pairs in normalised space")
        self.ed_points.textChanged.connect(self._on_field_changed)
        pform.addRow("Points", self.ed_points)
        form.addRow(self.poly_box)

        # Per-category overrides: the 局部概率化 part.
        self.ov_enabled = QComboBox()
        self.ov_enabled.addItems(["(no category override)"] + self.categories)
        self.ov_enabled.currentTextChanged.connect(self._on_ov_category)
        form.addRow("Category", self.ov_enabled)

        self.ov_mode = QComboBox()
        self.ov_mode.addItems(["count", "density_scale"])
        form.addRow("Override", self.ov_mode)

        self.ov_value = QDoubleSpinBox()
        self.ov_value.setDecimals(3)
        self.ov_value.setRange(0.0, 100000.0)
        self.ov_value.setSingleStep(1.0)
        self.ov_value.setValue(10.0)
        self.ov_value.valueChanged.connect(self._on_field_changed)
        form.addRow("Value", self.ov_value)

        root.addWidget(self.editor)
        self.editor.setEnabled(False)
        self._sync_shape_visibility()

        self._loading = False

    @staticmethod
    def _spin(lo: float, hi: float, step: float) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        return sb

    # -- editing ---------------------------------------------------------

    def _on_shape_changed(self, *_a) -> None:
        self._sync_shape_visibility()
        self._on_field_changed()

    def _sync_shape_visibility(self) -> None:
        shape = self.ed_shape.currentText()
        self.rect_box.setVisible(shape in ("rect", "all"))
        self.circle_box.setVisible(shape == "circle")
        self.poly_box.setVisible(shape == "polygon")

    def _on_ov_category(self, *_a) -> None:
        self.ov_value.setEnabled(self.ov_enabled.currentText() in self.categories)
        self._on_field_changed()

    def _on_field_changed(self, *_a) -> None:
        if getattr(self, "_loading", False):
            return
        row = self.list.currentRow()
        if row < 0:
            return
        self.regions[row] = self._collect()
        self._refresh_item(row)
        self.changed.emit()

    def _current_overrides(self) -> Dict[str, Dict[str, Any]]:
        cat = self.ov_enabled.currentText()
        if cat not in self.categories:
            return {}
        return {cat: {self.ov_mode.currentText(): self.ov_value.value()}}

    def _collect(self) -> Dict[str, Any]:
        shape = self.ed_shape.currentText()
        region: Dict[str, Any] = {
            "id": self.ed_id.text().strip() or "region",
            "shape": shape,
            "priority": int(self.ed_priority.value()),
        }
        if shape == "circle":
            region["bounds"] = {"cx": self.ed_cx.value(), "cy": self.ed_cy.value(),
                                "r": self.ed_r.value()}
        elif shape == "polygon":
            region["bounds"] = {"points": self._parse_points(self.ed_points.text())}
        else:
            region["bounds"] = {"x0": self.ed_x0.value(), "y0": self.ed_y0.value(),
                                "x1": self.ed_x1.value(), "y1": self.ed_y1.value()}
        overrides = self._current_overrides()
        if overrides:
            region["overrides"] = overrides
        return region

    @staticmethod
    def _parse_points(text: str) -> List[List[float]]:
        pts: List[List[float]] = []
        for token in (text or "").replace(",", " ").split():
            try:
                pts.append([float(token)])
            except ValueError:
                continue
        pairs: List[List[float]] = []
        flat: List[float] = []
        for value, _ in pts:
            flat.append(value)
        for i in range(0, len(flat) - 1, 2):
            pairs.append([flat[i], flat[i + 1]])
        return pairs

    def add_region(self, shape: str = "rect") -> None:
        base = "region"
        n = 1
        existing = {r.get("id") for r in self.regions}
        while base in existing:
            n += 1
            base = f"region{n}"
        self.regions.append({
            "id": base,
            "shape": shape,
            # mapgen rejects duplicate priorities, so hand out the next free value
            # rather than letting the designer collide with themselves.
            "priority": self._next_priority(),
            "bounds": ({"cx": 0.5, "cy": 0.5, "r": 0.2} if shape == "circle"
                       else {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.4}),
        })
        self._rebuild_list()
        self.list.setCurrentRow(len(self.regions) - 1)
        self.changed.emit()

    def _next_priority(self) -> int:
        used = {int(r.get("priority", 0) or 0) for r in self.regions}
        candidate = 1
        while candidate in used:
            candidate += 1
        return candidate

    def remove_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.regions.pop(row)
        self._rebuild_list()
        self.editor.setEnabled(False)
        self.changed.emit()

    def _rebuild_list(self) -> None:
        self._loading = True
        self.list.clear()
        for i, region in enumerate(self.regions):
            self._refresh_item(i)
        self._loading = False

    def _refresh_item(self, index: int) -> None:
        region = self.regions[index]
        ov = region.get("overrides") or {}
        bits = []
        for cat, spec in ov.items():
            for k, v in spec.items():
                bits.append(f"{cat}.{k}={v:g}" if isinstance(v, (int, float)) else f"{cat}.{k}={v}")
        text = f"p{int(region.get('priority', 0) or 0):<3d} {region.get('id', '?')}  [{region.get('shape', '?')}]"
        if bits:
            text += "  " + ", ".join(bits)
        if index < self.list.count():
            self.list.item(index).setText(text)
        else:
            self.list.addItem(QListWidgetItem(text))

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self.regions):
            self.editor.setEnabled(False)
            return
        self.editor.setEnabled(True)
        region = self.regions[row]
        self._loading = True
        try:
            self.ed_id.setText(str(region.get("id", "")))
            self.ed_priority.setValue(int(region.get("priority", 0) or 0))
            self.ed_shape.setCurrentText(str(region.get("shape", "rect")))
            bounds = region.get("bounds") or {}
            if "cx" in bounds:
                self.ed_cx.setValue(float(bounds.get("cx", 0.5)))
                self.ed_cy.setValue(float(bounds.get("cy", 0.5)))
                self.ed_r.setValue(float(bounds.get("r", 0.2)))
            else:
                self.ed_x0.setValue(float(bounds.get("x0", 0.0)))
                self.ed_y0.setValue(float(bounds.get("y0", 0.0)))
                self.ed_x1.setValue(float(bounds.get("x1", 0.4)))
                self.ed_y1.setValue(float(bounds.get("y1", 0.4)))
            if "points" in bounds:
                pts = " ".join(f"{p[0]},{p[1]}" for p in bounds["points"] if len(p) >= 2)
                self.ed_points.setText(pts)
            overrides = region.get("overrides") or {}
            if overrides:
                cat = next(iter(overrides))
                spec = overrides[cat]
                self.ov_enabled.setCurrentText(cat)
                mode = next(iter(spec))
                self.ov_mode.setCurrentText(mode)
                self.ov_value.setValue(float(spec[mode]))
            else:
                self.ov_enabled.setCurrentIndex(0)
        finally:
            self._loading = False
        self._sync_shape_visibility()

    def to_list(self) -> List[Dict[str, Any]]:
        """Regions shaped exactly like mapgen's config ``regions`` array."""
        return [copy.deepcopy(r) for r in self.regions]
