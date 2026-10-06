"""MagicaMapGen main window - skeleton wired to a real generation.

Layout: a left rail of framed panels (theme, parameters, contract) and a right
preview area. Every parameter control is built from the generator's own
``--describe-theme`` output, so adding a theme or a category on the Python side makes
the form appear here with no GUI change.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from . import theme
from .bridge import EXIT_MEANING, EXIT_OK, MapgenBridge, MapSummary
from .param_form import ParamForm
from .preview import render_map
from .region_editor import RegionEditor
from .skin import SkinnedFrame, SkinManager

APP_NAME = "MagicaMapGen"

SIZES = (64, 96, 128, 256, 384, 512)


def _panel(title: str = "", skins: SkinManager = None) -> SkinnedFrame:
    """A framed panel. Registered with the skin manager so skins can be toggled."""
    f = SkinnedFrame()
    if skins is not None:
        skins.register(f, "panel")
    return f


def _divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    d.setFixedHeight(1)
    return d


def _label(text: str, obj: str = "") -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    return lb


class MainWindow(QMainWindow):
    def __init__(self, workdir: Path):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - game map prototype design")
        self.resize(1360, 880)

        self.workdir = Path(workdir)
        self.out_dir = self.workdir / "output"
        self.bridge = MapgenBridge(self.workdir, self)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.log.connect(self._append_log)

        self.themes: list = []
        self.theme_meta: dict = {}
        self.summary: Optional[MapSummary] = None
        # Skins are optional: if the generated frames are absent the manager leaves
        # every panel on the plain QSS border, so a clean checkout still works.
        self.skins = SkinManager(enabled=True)

        # Built here because the parameter form and region editor both need to exist
        # before _build_ui() wires them into the tab widget.
        self.form = ParamForm()
        self.region_editor = RegionEditor()
        self.region_editor.changed.connect(self._on_form_changed)
        self.form.changed.connect(self._on_form_changed)

        self._build_ui()
        self._load_themes()

    def _on_form_changed(self) -> None:
        n = len(self.form.overrides())
        r = len(self.region_editor.to_list())
        bits = []
        if n:
            bits.append(f"{n} parameter override(s)")
        if r:
            bits.append(f"{r} region(s)")
        self.lbl_override_count.setText(", ".join(bits) if bits
                                          else "no overrides - using theme defaults")

    # ---- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_left_rail())
        split.addWidget(self._build_preview_area())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([430, 900])
        root.addWidget(split, 1)

        self.setCentralWidget(central)

    def _build_header(self) -> QWidget:
        head = QFrame()
        head.setObjectName("Header")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(14, 10, 14, 10)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(_label(APP_NAME, "Title"))
        titles.addWidget(_label(
            "Deterministic prototype map designer - theme, category and distribution "
            "under a hard contract", "Subtitle"))
        lay.addLayout(titles)
        lay.addStretch(1)

        self.btn_generate = QPushButton("Generate Map")
        self.btn_generate.setObjectName("Primary")
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._on_generate)
        lay.addWidget(self.btn_generate)

        avail = self.skins.available()
        have_all = all(avail.values())
        self.btn_skin = QPushButton("Ornate frame: on" if have_all else "Ornate frame: n/a")
        self.btn_skin.setCheckable(True)
        self.btn_skin.setChecked(have_all)
        self.btn_skin.setEnabled(have_all)
        self.btn_skin.setToolTip("Toggle the generated nine-patch frame on the panels")
        self.btn_skin.toggled.connect(self._on_toggle_skin)
        lay.addWidget(self.btn_skin)
        return head

    def _build_left_rail(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(10)

        lay.addWidget(self._build_theme_panel())
        lay.addWidget(self._build_param_panel())
        lay.addWidget(self._build_contract_panel())
        lay.addWidget(self._build_log_panel())
        lay.addStretch(1)

        scroll.setWidget(host)
        scroll.setMinimumWidth(400)
        return scroll

    def _build_theme_panel(self) -> QFrame:
        f = _panel(skins=self.skins)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        lay.addWidget(_label("Theme", "SectionLabel"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        lay.addWidget(self.cmb_theme)

        self.lbl_theme_desc = _label("", "Hint")
        self.lbl_theme_desc.setWordWrap(True)
        lay.addWidget(self.lbl_theme_desc)

        lay.addWidget(_divider())
        lay.addWidget(_label("Output", "SectionLabel"))
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(_label("Seed", "Hint"), 0, 0)
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(1, 2_147_483_647)
        self.spin_seed.setValue(20261002)
        grid.addWidget(self.spin_seed, 0, 1)
        grid.addWidget(_label("Grid", "Hint"), 1, 0)
        self.cmb_size = QComboBox()
        for s in SIZES:
            self.cmb_size.addItem(f"{s} x {s}", s)
        self.cmb_size.setCurrentIndex(SIZES.index(128))
        grid.addWidget(self.cmb_size, 1, 1)
        lay.addLayout(grid)

        self.chk_instances = QCheckBox("Show instances")
        self.chk_instances.setChecked(True)
        self.chk_instances.toggled.connect(self._refresh_preview)
        lay.addWidget(self.chk_instances)
        return f

    def _build_param_panel(self) -> QFrame:
        """Interactive terrain parameters + region editor, both metadata-driven."""
        f = _panel(skins=self.skins)
        outer = QVBoxLayout(f)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        tabs = QTabWidget()
        tabs.setMinimumHeight(360)
        tabs.addTab(self._wrap_scroll(self.form), "Parameters")
        self.region_host = QWidget()
        tabs.addTab(self._wrap_scroll(self.region_host), "Regions")
        outer.addWidget(tabs)

        row = QHBoxLayout()
        self.lbl_override_count = _label("", "Hint")
        row.addWidget(self.lbl_override_count)
        row.addStretch(1)
        btn_reset = QPushButton("Reset all")
        btn_reset.clicked.connect(self._on_reset_overrides)
        row.addWidget(btn_reset)
        outer.addLayout(row)

        self.lbl_forbidden = _label("", "Hint")
        self.lbl_forbidden.setWordWrap(True)
        outer.addWidget(self.lbl_forbidden)
        return f

    @staticmethod
    def _wrap_scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        widget.setParent(area)
        area.setWidget(widget)
        return area

    def _build_contract_panel(self) -> QFrame:
        f = _panel(skins=self.skins)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)
        lay.addWidget(_label("Contract", "SectionLabel"))

        self.lbl_contract = _label("Not run yet", "StatBig")
        lay.addWidget(self.lbl_contract)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.lbl_stat_land = self._stat("Land", row)
        self.lbl_stat_inst = self._stat("Instances", row)
        self.lbl_stat_lakes = self._stat("Lakes", row)
        lay.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("idle")
        lay.addWidget(self.progress)

        self.lbl_meta = _label("", "Hint")
        self.lbl_meta.setWordWrap(True)
        lay.addWidget(self.lbl_meta)
        return f

    def _stat(self, name: str, row: QHBoxLayout) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(0)
        big = _label("-", "StatBig")
        row.addLayout(box)
        box.addWidget(big)
        box.addWidget(_label(name, "StatName"))
        return big

    def _build_log_panel(self) -> QFrame:
        f = _panel(skins=self.skins)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)
        lay.addWidget(_label("Generator Log", "SectionLabel"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(120)
        self.txt_log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.txt_log)
        return f

    def _build_preview_area(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(_label("Preview", "SectionLabel"))
        head.addStretch(1)
        self.lbl_legend = _label("", "Hint")
        head.addWidget(self.lbl_legend)
        lay.addLayout(head)

        self.lbl_preview = QLabel("No map generated yet.")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumSize(640, 520)
        self.lbl_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_preview.setStyleSheet(
            f"background:#0d0b0a; border:1px solid {theme.BORDER}; border-radius:3px;")
        lay.addWidget(self.lbl_preview, 1)

        row = QHBoxLayout()
        row.addWidget(_label("Contract checks", "SectionLabel"))
        row.addStretch(1)
        self.btn_open = QPushButton("Reveal Output Folder")
        self.btn_open.clicked.connect(self._on_reveal)
        self.btn_open.setEnabled(False)
        row.addWidget(self.btn_open)
        lay.addLayout(row)

        self.txt_contract = QTextEdit()
        self.txt_contract.setReadOnly(True)
        self.txt_contract.setMaximumHeight(150)
        self.txt_contract.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.txt_contract)
        return wrap

    # ---- data ------------------------------------------------------------

    def _load_themes(self) -> None:
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.clear()
        for t in self.bridge.list_themes():
            self.themes.append(t)
            self.cmb_theme.addItem(f"{t.get('display_name', t.get('id'))}", t.get("id"))
        self.cmb_theme.blockSignals(False)
        if self.cmb_theme.count():
            self._on_theme_changed(0)

    def _on_theme_changed(self, _index: int) -> None:
        theme_id = self.cmb_theme.currentData()
        if not theme_id:
            return
        meta = self.bridge.describe_theme(theme_id)
        self.theme_meta = meta or {}
        self.lbl_theme_desc.setText(self.theme_meta.get("description", ""))
        self.btn_generate.setEnabled(True)

        # Rebuild the interactive controls from this theme's own metadata.
        self.form.load(self.theme_meta.get("terrain_schema", []))
        categories = [c.get("id") for c in self.theme_meta.get("categories", [])]
        self.region_editor.categories = [c for c in categories if c]
        self.region_editor.ov_enabled.blockSignals(True)
        self.region_editor.ov_enabled.clear()
        self.region_editor.ov_enabled.addItems(["(no category override)"] + self.region_editor.categories)
        self.region_editor.ov_enabled.blockSignals(False)
        self.region_editor.regions = []
        self.region_editor._rebuild_list()
        self.region_editor.editor.setEnabled(False)

        forbidden = self.theme_meta.get("forbidden_biomes", [])
        checks = len(self.theme_meta.get("contract_checks", []))
        self.lbl_forbidden.setText(
            f"Contract checks: {checks}. Forbidden biomes (never emitted): "
            f"{', '.join(forbidden) if forbidden else 'none'}")
        self._on_form_changed()

    # ---- run -------------------------------------------------------------

    def _on_toggle_skin(self, on: bool) -> None:
        self.skins.set_enabled(on)
        self.btn_skin.setText("Ornate frame: on" if on else "Ornate frame: off")
        self._append_log("ornate frame %s" % ("enabled" if on else "disabled"))

    def _on_reset_overrides(self) -> None:
        self.form.reset_all()
        self.region_editor.regions = []
        self.region_editor._rebuild_list()
        self.region_editor.editor.setEnabled(False)
        self._on_form_changed()

    def _build_config(self) -> dict:
        """The run request, shaped exactly like a mapgen config file.

        Only values the designer actually changed are emitted, so the saved file
        doubles as a readable record of what this map is doing differently from the
        theme default.
        """
        size = int(self.cmb_size.currentData())
        config = {
            "theme": self.cmb_theme.currentData(),
            "seed": self.spin_seed.value(),
            "width": size,
            "height": size,
        }
        terrain = self.form.overrides()
        if terrain:
            config["terrain"] = terrain
        regions = self.region_editor.to_list()
        if regions:
            config["regions"] = regions
        return config

    def _on_generate(self) -> None:
        theme_id = self.cmb_theme.currentData()
        if not theme_id:
            return
        self.summary = None
        self.btn_generate.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("starting...")
        self.lbl_contract.setText("Running")
        self.lbl_contract.setStyleSheet("color:%s;" % theme.EMBER_LIT)
        self.txt_contract.clear()

        config = self._build_config()
        self._last_config = config
        self._append_log("--- request ---")
        self._append_log(json.dumps(config, ensure_ascii=False, indent=2))
        self.bridge.start_with_config(config, self.out_dir)

    def _on_progress(self, stage: str, percent: int) -> None:
        self.progress.setValue(percent)
        self.progress.setFormat(f"{stage} - {percent}%")

    def _on_finished(self, code: int, summary) -> None:
        self.btn_generate.setEnabled(True)
        self.progress.setValue(100 if code == EXIT_OK else 0)
        self.progress.setFormat("done" if code == EXIT_OK else "failed")
        self.lbl_contract.setText(EXIT_MEANING.get(code, f"Exit {code}"))
        if code == EXIT_OK:
            self.lbl_contract.setStyleSheet(f"color:{theme.RUNE};")
        elif code == 1:
            self.lbl_contract.setStyleSheet(f"color:{theme.WARN};")
        else:
            self.lbl_contract.setStyleSheet(f"color:{theme.DANGER};")

        if summary is not None:
            self.summary = summary
            self.btn_open.setEnabled(True)
            self._apply_summary(summary)
        self._fill_contract_text(code, summary)

    def _apply_summary(self, s: MapSummary) -> None:
        stats = s.stats
        self.lbl_stat_land.setText(f"{(stats.get('land_fraction', 0) or 0) * 100:.1f}%")
        self.lbl_stat_inst.setText(str(s.instance_count))
        self.lbl_stat_lakes.setText(str(stats.get("lake_count", 0)))
        bits = [f"schema v{s.schema_version}", f"gen {s.generator_version}",
                f"seed {s.seed}", f"{s.grid.get('width')}x{s.grid.get('height')}"]
        if s.height_source:
            bits.append(f"height: {s.height_source}")
        self.lbl_meta.setText("  |  ".join(bits))

        keys = [e.get("key") for e in s.legend if e.get("key")]
        self.lbl_legend.setText("biomes: " + ", ".join(keys))
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self.summary is None:
            return
        img = render_map(self.summary, 900, 700,
                         show_instances=self.chk_instances.isChecked())
        if img is None:
            self.lbl_preview.setText("Preview unavailable for this document.")
            return
        self.lbl_preview.setPixmap(QPixmap.fromImage(img))
        self.lbl_preview.setText("")

    def _fill_contract_text(self, code: int, summary) -> None:
        lines = [f"exit code: {code} - {EXIT_MEANING.get(code, 'unknown')}"]
        if summary is None:
            lines.append("No summary: see the generator log for the reason.")
        else:
            lines.append(f"label: {summary.label}")
            lines.append(f"contract passed: {summary.contract_passed}")
            lines.append(f"hard failures: {len(summary.hard_failures)}")
            lines.append(f"warnings: {len(summary.warnings)}")
            for f in summary.hard_failures:
                lines.append(f"  [FAIL] {f.get('kind')}: {f.get('message')}")
            for w in summary.warnings:
                lines.append(f"  [warn] {w.get('kind')}: {w.get('message')}")
            by_cat = summary.stats.get("instances_by_category", {})
            if by_cat:
                lines.append("instances: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(by_cat.items())))
        self.txt_contract.setPlainText("\n".join(lines))

    def _append_log(self, line: str) -> None:
        self.txt_log.append(line)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def _on_reveal(self) -> None:
        import subprocess
        target = str(self.out_dir.resolve())
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            self._append_log(f"Could not open folder: {exc}")


def run(workdir: Path) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(theme.build_font(13))
    app.setStyleSheet(theme.QSS)
    win = MainWindow(workdir)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "_mmg_work"))
