"""Parameter controls built from the generator's own metadata.

Every widget is created from one entry of ``--describe-theme``'s ``terrain_schema``:
kind decides the control, minimum/maximum/step bound it, group decides placement and
``default`` pre-fills it from the theme. Nothing theme-specific is hardcoded, so a new
theme or parameter shows up in the GUI without editing this file.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from . import theme


class ParamRow(QWidget):
    """One label + control pair, with an inline reset and a tooltip."""

    changed = pyqtSignal(str, object)

    def __init__(self, spec: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.spec = spec
        self.key = spec["key"]
        self.kind = spec.get("kind", "float")
        self.default = spec.get("default")
        self._loading = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.label = QLabel(spec.get("label") or self.key)
        self.label.setMinimumWidth(170)
        self.label.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        if spec.get("help"):
            self.label.setToolTip(spec["help"])
            self.setToolTip(spec["help"])
        lay.addWidget(self.label)

        self.control = self._make_control()
        lay.addWidget(self.control, 1)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.setToolTip("Restore the theme default")
        self.btn_reset.clicked.connect(self.reset)
        self.btn_reset.setEnabled(False)
        lay.addWidget(self.btn_reset)

    def _make_control(self) -> QWidget:
        spec = self.spec
        if self.kind == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(self.default))
            cb.toggled.connect(self._emit)
            return cb
        if self.kind == "choice":
            cb = QComboBox()
            cb.addItems([str(c) for c in spec.get("choices", [])])
            if self.default is not None:
                cb.setCurrentText(str(self.default))
            cb.currentTextChanged.connect(self._emit)
            return cb
        lo = spec.get("minimum")
        hi = spec.get("maximum")
        step = spec.get("step") or (1 if self.kind == "int" else 0.01)
        if self.kind == "int":
            sb = QSpinBox()
            sb.setRange(int(lo if lo is not None else -1000000),
                        int(hi if hi is not None else 1000000))
            sb.setSingleStep(max(1, int(step)))
            sb.setValue(int(self.default or 0))
            sb.valueChanged.connect(self._emit)
            return sb
        sb = QDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(float(lo if lo is not None else -1e6),
                    float(hi if hi is not None else 1e6))
        sb.setSingleStep(float(step) or 0.01)
        sb.setValue(float(self.default or 0.0))
        sb.valueChanged.connect(self._emit)
        return sb

    def value(self) -> Any:
        c = self.control
        if isinstance(c, QCheckBox):
            return c.isChecked()
        if isinstance(c, QComboBox):
            return c.currentText()
        if isinstance(c, QSpinBox):
            return int(c.value())
        if isinstance(c, QDoubleSpinBox):
            return float(c.value())
        return None

    def set_value(self, value: Any) -> None:
        self._loading = True
        c = self.control
        try:
            if isinstance(c, QCheckBox):
                c.setChecked(bool(value))
            elif isinstance(c, QComboBox):
                c.setCurrentText(str(value))
            elif isinstance(c, QSpinBox):
                c.setValue(int(value))
            elif isinstance(c, QDoubleSpinBox):
                c.setValue(float(value))
        finally:
            self._loading = False
        self.btn_reset.setEnabled(self._differs())

    def reset(self) -> None:
        self.set_value(self.default)
        if not self._loading:
            self.changed.emit(self.key, self.value())

    def _differs(self) -> bool:
        if isinstance(self.control, QCheckBox):
            return self.control.isChecked() != bool(self.default)
        if isinstance(self.control, QComboBox):
            return self.control.currentText() != str(self.default)
        if isinstance(self.control, (QSpinBox, QDoubleSpinBox)):
            return abs(float(self.control.value()) - float(self.default or 0.0)) > 1e-9
        return False

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        self.btn_reset.setEnabled(self._differs())
        self.changed.emit(self.key, self.value())


class ParamForm(QWidget):
    """Renders a whole terrain_schema, grouped, with an advanced toggle.

    ``overrides()`` returns only the values that differ from the theme defaults, which
    is exactly what a mapgen config file wants. Emitting nothing when nothing changed
    keeps saved configs minimal and makes the UI state readable as a diff.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: Dict[str, ParamRow] = {}
        self._groups: Dict[str, QVBoxLayout] = {}
        self._group_boxes: Dict[str, QGroupBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.btn_advanced = QPushButton("Show advanced parameters")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setChecked(False)
        self.btn_advanced.toggled.connect(self._toggle_advanced)
        outer.addWidget(self.btn_advanced)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)
        outer.addStretch(1)

    def load(self, schema: List[Dict[str, Any]]) -> None:
        """Rebuild for a theme's terrain_schema. Clears any previous theme's rows."""
        for row in self.rows.values():
            row.setParent(None)
            row.deleteLater()
        self.rows.clear()
        for box in self._group_boxes.values():
            box.setParent(None)
            box.deleteLater()
        self._group_boxes.clear()
        self._groups.clear()

        for spec in schema:
            group = spec.get("group", "General")
            if group not in self._groups:
                box = QGroupBox(group)
                box.setStyleSheet(
                    "QGroupBox { border:1px solid %s; border-radius:3px; "
                    "margin-top:10px; padding:10px 8px 8px 8px; } "
                    "QGroupBox::title { subcontrol-origin: margin; left:10px; "
                    "padding:0 4px; color:%s; }" % (theme.BORDER, theme.EMBER_LIT))
                lay = QVBoxLayout(box)
                lay.setSpacing(5)
                self._group_boxes[group] = box
                self._groups[group] = lay
                self.body.addWidget(box)

            row = ParamRow(spec)
            row.changed.connect(lambda *_a: self.changed.emit())
            self.rows[spec["key"]] = row
            self._groups[group].addWidget(row)
            if spec.get("advanced"):
                row.setVisible(False)

    def _toggle_advanced(self, on: bool) -> None:
        for row in self.rows.values():
            if row.spec.get("advanced"):
                row.setVisible(on)
        self.btn_advanced.setText("Hide advanced parameters" if on
                                  else "Show advanced parameters")

    def overrides(self) -> Dict[str, Any]:
        """Only values that differ from the theme default."""
        out: Dict[str, Any] = {}
        for key, row in self.rows.items():
            if row._differs():
                out[key] = row.value()
        return out

    def reset_all(self) -> None:
        for row in self.rows.values():
            row.reset()
        self.changed.emit()
