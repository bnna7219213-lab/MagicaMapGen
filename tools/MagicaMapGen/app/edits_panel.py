"""Edits panel: the phase-2 editing closed loop, inside the GUI.

A designer hand-edits the latest generated map and records the changes as an
``edits.json`` of instance-level ops (delete / move / add / paint). "增量重生成"
re-runs ``mapgen --overlay`` against that base; the surrounding map reproduces
deterministically, so only the edited region changes, and the preview reloads.

The ops are stored in memory as a plain list; "写入 edits.json" materialises them
next to the outputs so the run is always reproducible by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .bridge import MapgenBridge


def _op_label(op: dict) -> str:
    kind = op["op"]
    if kind == "delete":
        return f"删除   实例 id={op['id']}"
    if kind == "move":
        return f"移动   实例 id={op['id']} -> ({op['x']}, {op['y']})"
    if kind == "add":
        return (f"添加   {op['cat']}/{op['type']} @({op['x']}, {op['y']}) "
                f"scale={op.get('scale', 1.0)} rot={op.get('rot', 0.0)}")
    if kind == "paint":
        cells = op.get("cells") or []
        return f"涂抹   {len(cells)} 格（禁止生成）"
    return str(op)


class EditsPanel(QWidget):
    """Collect instance-level ops and trigger an overlay regeneration."""

    regenerate = pyqtSignal()

    def __init__(self, bridge: MapgenBridge, parent: QWidget | None = None):
        super().__init__(parent)
        self._bridge = bridge
        self._base_map: Path | None = None
        self._out_dir: Path | None = None
        self._categories: List[dict] = []  # [{category, object_type}]
        self.edit_ops: List[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._base_label = QLabel("尚未生成地图，无法编辑。")
        self._base_label.setWordWrap(True)
        layout.addWidget(self._base_label)

        layout.addWidget(self._build_list())

        layout.addWidget(self._build_delete_group())
        layout.addWidget(self._build_move_group())
        layout.addWidget(self._build_add_group())
        layout.addWidget(self._build_paint_group())

        layout.addWidget(self._build_actions())

    # ---- UI construction --------------------------------------------------
    def _build_list(self) -> QGroupBox:
        box = QGroupBox("编辑操作 (edits.json)")
        v = QVBoxLayout(box)
        self.op_list = QListWidget()
        v.addWidget(self.op_list)
        remove = QPushButton("删除所选操作")
        remove.clicked.connect(self._remove_selected)
        v.addWidget(remove)
        return box

    def _build_delete_group(self) -> QGroupBox:
        box = QGroupBox("删除实例")
        h = QHBoxLayout(box)
        self.del_id = QSpinBox()
        self.del_id.setRange(0, 1_000_000)
        h.addWidget(QLabel("id"))
        h.addWidget(self.del_id)
        btn = QPushButton("删除")
        btn.clicked.connect(self._add_delete)
        h.addWidget(btn)
        return box

    def _build_move_group(self) -> QGroupBox:
        box = QGroupBox("移动实例")
        h = QHBoxLayout(box)
        self.move_id = QSpinBox()
        self.move_id.setRange(0, 1_000_000)
        self.move_x = QSpinBox()
        self.move_x.setRange(0, 4095)
        self.move_y = QSpinBox()
        self.move_y.setRange(0, 4095)
        for w, name in ((self.move_id, "id"), (self.move_x, "x"), (self.move_y, "y")):
            h.addWidget(QLabel(name))
            h.addWidget(w)
        btn = QPushButton("移动")
        btn.clicked.connect(self._add_move)
        h.addWidget(btn)
        return box

    def _build_add_group(self) -> QGroupBox:
        box = QGroupBox("添加实例")
        h = QHBoxLayout(box)
        self.add_cat = QComboBox()
        self.add_cat.currentTextChanged.connect(self._on_cat_changed)
        self.add_type = QLabel("-")
        self.add_x = QSpinBox()
        self.add_x.setRange(0, 4095)
        self.add_y = QSpinBox()
        self.add_y.setRange(0, 4095)
        self.add_scale = QDoubleSpinBox()
        self.add_scale.setRange(0.1, 5.0)
        self.add_scale.setValue(1.0)
        self.add_scale.setSingleStep(0.1)
        h.addWidget(QLabel("类别"))
        h.addWidget(self.add_cat)
        h.addWidget(QLabel("类型"))
        h.addWidget(self.add_type)
        for w, name in ((self.add_x, "x"), (self.add_y, "y"), (self.add_scale, "scale")):
            h.addWidget(QLabel(name))
            h.addWidget(w)
        btn = QPushButton("添加")
        btn.clicked.connect(self._add_add)
        h.addWidget(btn)
        return box

    def _build_paint_group(self) -> QGroupBox:
        box = QGroupBox("涂抹格（禁止在该格生成）")
        h = QHBoxLayout(box)
        self.paint_x = QSpinBox()
        self.paint_x.setRange(0, 4095)
        self.paint_y = QSpinBox()
        self.paint_y.setRange(0, 4095)
        for w, name in ((self.paint_x, "x"), (self.paint_y, "y")):
            h.addWidget(QLabel(name))
            h.addWidget(w)
        btn = QPushButton("涂抹")
        btn.clicked.connect(self._add_paint)
        h.addWidget(btn)
        return box

    def _build_actions(self) -> QGroupBox:
        box = QGroupBox("增量重生成")
        h = QHBoxLayout(box)
        self.write_btn = QPushButton("写入 edits.json")
        self.write_btn.clicked.connect(self._write_edits)
        self.regen_btn = QPushButton("增量重生成")
        self.regen_btn.clicked.connect(self._run_overlay)
        self.clear_btn = QPushButton("清空操作")
        self.clear_btn.clicked.connect(self.clear_ops)
        h.addWidget(self.write_btn)
        h.addWidget(self.regen_btn)
        h.addWidget(self.clear_btn)
        return box

    # ---- data -------------------------------------------------------------
    def set_base(self, map_json: Path, out_dir: Path) -> None:
        self._base_map = Path(map_json)
        self._out_dir = Path(out_dir)
        try:
            doc = json.loads(self._base_map.read_text(encoding="utf-8"))
        except Exception:
            self._base_label.setText("无法读取 base map.json。")
            return
        self._categories = [
            {"category": c["category"], "object_type": c.get("object_type", "")}
            for c in (doc.get("categories") or [])
        ]
        self.add_cat.blockSignals(True)
        self.add_cat.clear()
        for c in self._categories:
            self.add_cat.addItem(f"{c['category']} ({c['object_type']})", c["category"])
        self.add_cat.blockSignals(False)
        self._on_cat_changed(self.add_cat.currentText())

        n = len(doc.get("instances") or [])
        self._base_label.setText(
            f"基准：{self._base_map.name}（{n} 个实例）\n"
            f"输出目录：{self._out_dir}")

    def _on_cat_changed(self, _text: str) -> None:
        idx = self.add_cat.currentIndex()
        if 0 <= idx < len(self._categories):
            self.add_type.setText(self._categories[idx]["object_type"])
        else:
            self.add_type.setText("-")

    def clear_ops(self) -> None:
        self.edit_ops.clear()
        self.op_list.clear()

    def _refresh_list(self) -> None:
        self.op_list.clear()
        for op in self.edit_ops:
            QListWidgetItem(_op_label(op), self.op_list)

    # ---- op handlers ------------------------------------------------------
    def _add_delete(self) -> None:
        self.edit_ops.append({"op": "delete", "id": int(self.del_id.value())})
        self._refresh_list()

    def _add_move(self) -> None:
        self.edit_ops.append({
            "op": "move", "id": int(self.move_id.value()),
            "x": int(self.move_x.value()), "y": int(self.move_y.value()),
        })
        self._refresh_list()

    def _add_add(self) -> None:
        idx = self.add_cat.currentIndex()
        if not (0 <= idx < len(self._categories)):
            return
        cat = self._categories[idx]
        self.edit_ops.append({
            "op": "add", "cat": cat["category"], "type": cat["object_type"],
            "x": int(self.add_x.value()), "y": int(self.add_y.value()),
            "scale": float(self.add_scale.value()), "rot": 0.0,
        })
        self._refresh_list()

    def _add_paint(self) -> None:
        cell = [int(self.paint_x.value()), int(self.paint_y.value())]
        # merge into the last paint op if present, else start a new one
        for op in reversed(self.edit_ops):
            if op["op"] == "paint":
                op.setdefault("cells", []).append(cell)
                self._refresh_list()
                return
        self.edit_ops.append({"op": "paint", "cells": [cell]})
        self._refresh_list()

    def _remove_selected(self) -> None:
        row = self.op_list.currentRow()
        if row >= 0 and row < len(self.edit_ops):
            del self.edit_ops[row]
            self._refresh_list()

    # ---- run --------------------------------------------------------------
    def _edits_path(self) -> Path:
        assert self._out_dir is not None
        return self._out_dir / "edits.json"

    def _write_edits(self) -> None:
        if self._out_dir is None:
            return
        payload = {"schema_version": 1, "ops": self.edit_ops}
        try:
            self._edits_path().write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._base_label.setText(
                f"已写入 {self._edits_path().name}（{len(self.edit_ops)} 个操作）")
        except OSError as exc:
            self._base_label.setText(f"写入失败：{exc}")

    def _run_overlay(self) -> None:
        if self._base_map is None or self._out_dir is None:
            self._base_label.setText("请先生成一张地图作为基准。")
            return
        self._write_edits()
        self.regen_btn.setEnabled(False)
        self._bridge.start_overlay(
            self._base_map, self._edits_path(), self._out_dir, label="overlay")

    def on_finished(self) -> None:
        self.regen_btn.setEnabled(True)
        self._refresh_base_count()

    def _refresh_base_count(self) -> None:
        if self._base_map is None or not self._base_map.exists():
            return
        try:
            doc = json.loads(self._base_map.read_text(encoding="utf-8"))
        except Exception:
            return
        n = len(doc.get("instances") or [])
        self._base_label.setText(
            f"基准：{self._base_map.name}（{n} 个实例）\n"
            f"输出目录：{self._out_dir}")
