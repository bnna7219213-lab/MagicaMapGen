"""Offscreen smoke test for the MagicaMapGen GUI.

Drives the real window through a real generation with no user interaction and asserts
the whole chain: CLI bridge, live progress, contract verdict, map.json parsing and
preview rendering. Also writes a screenshot so the UI can be reviewed without a
display. Safe to run headless via QT_QPA_PLATFORM=offscreen.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# NOTE: the offscreen platform plugin ships with no font database on Windows
# (QFontDatabase.families() comes back empty), so every label renders as tofu boxes
# and the screenshot is useless for reviewing the UI. The native windows plugin works
# headlessly here, so it is the default. Set MMG_OFFSCREEN=1 to force offscreen when
# running somewhere with no window station at all.
if os.environ.get("MMG_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import theme  # noqa: E402
from app.bridge import EXIT_OK, MapSummary  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.preview import render_map  # noqa: E402

WORK = HERE / "_mmg_work"
SHOT = HERE / "docs" / "screenshot_main.png"


def pump(app, ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(theme.build_font(13))
    app.setStyleSheet(theme.QSS)

    win = MainWindow(WORK)
    win.resize(1360, 880)
    win.show()
    pump(app, 400)

    failures = []

    # --- skin layer -------------------------------------------------------
    print("\n-- skin layer --")
    avail = win.skins.available()
    print("skin assets available:", avail)
    if not all(avail.values()):
        failures.append("skin assets missing; run tools/make_skins.py (%r)" % avail)
    skinned = [f for f, _ in win.skins._frames if f.skinned]
    print("panels registered: %d, currently skinned: %d"
          % (len(win.skins._frames), len(skinned)))
    if win.skins._frames and not skinned:
        failures.append("panels registered but none are skinned")
    # Toggling off must fall back to the stylesheet border, not leave a broken frame.
    win._on_toggle_skin(False)
    pump(app, 80)
    if any(f.skinned for f, _ in win.skins._frames):
        failures.append("disabling skins left a frame painted")
    win._on_toggle_skin(True)
    pump(app, 80)
    if not all(f.skinned for f, _ in win.skins._frames):
        failures.append("re-enabling skins did not repaint the frames")
    win.btn_skin.setChecked(True)

    # Regression guard: Qt's QSS parser silently ignored `font-family` and fell back
    # to the system UI face, which rendered every label as tofu boxes. Assert the
    # application font actually resolved, so this cannot come back unnoticed.
    from PyQt6.QtGui import QFontDatabase
    resolved = app.font().family()
    print("app font resolved to:", repr(resolved))
    if resolved not in QFontDatabase.families():
        failures.append("application font %r is not an installed family (tofu risk)" % resolved)
    if resolved == "Microsoft YaHei UI":
        failures.append("font fell back to the system UI face; QSS font-family regression")

    themes = win.bridge.list_themes()
    print("themes discovered:", [t.get("id") for t in themes])
    if len(themes) < 2:
        failures.append("expected >=2 themes, got %d" % len(themes))
    if win.cmb_theme.count() < 2:
        failures.append("theme combo not populated")
    if win.cmb_theme.count() == 0:
        print("RESULT: FAIL -", failures)
        return 1

    win.cmb_theme.setCurrentIndex(0)
    pump(app, 200)
    win.spin_seed.setValue(20261002)
    idx = win.cmb_size.findData(128)
    if idx >= 0:
        win.cmb_size.setCurrentIndex(idx)
    pump(app, 100)

    meta = win.theme_meta or {}
    print("theme meta: id=%s categories=%d checks=%d" % (
        meta.get("id"), len(meta.get("categories", [])),
        len(meta.get("contract_checks", []))))
    if not meta.get("categories"):
        failures.append("describe-theme returned no categories")

    state = {"code": None, "summary": None, "progress": []}
    win.bridge.progress.connect(lambda s, p: state["progress"].append((s, p)))

    def on_done(code, summary):
        state["code"] = code
        state["summary"] = summary

    win.bridge.finished.connect(on_done)

    # --- interactive form: drive it the way a designer would ---------------
    print("\n-- parameter form --")
    print("rows built from terrain_schema:", len(win.form.rows))
    if len(win.form.rows) < 20:
        failures.append("expected the full terrain schema, got %d rows" % len(win.form.rows))
    if win.form.overrides():
        failures.append("freshly loaded form should report no overrides, got %s"
                        % win.form.overrides())

    sea = win.form.rows.get("sea_level")
    if sea is None:
        failures.append("sea_level row missing from the form")
    else:
        sea.set_value(0.30)
        ov = win.form.overrides()
        print("after setting sea_level=0.30 ->", ov)
        if "sea_level" not in ov:
            failures.append("sea_level override not detected")
        sea.reset()
        if "sea_level" in win.form.overrides():
            failures.append("reset did not clear the sea_level override")
        print("after reset ->", win.form.overrides())

    # --- region editor -----------------------------------------------------
    print("\n-- region editor --")
    cats = [c.get("id") for c in (win.theme_meta.get("categories") or [])]
    print("categories offered to regions:", cats)
    if not cats:
        failures.append("region editor got no categories")
    win.region_editor.add_region("rect")
    win.region_editor.add_region("circle")
    win.region_editor.list.setCurrentRow(0)
    pump(app, 100)
    win.region_editor.ed_id.setText("north_taiga")
    win.region_editor.ed_priority.setValue(7)
    win.region_editor.ov_enabled.setCurrentText(cats[0] if cats else "")
    win.region_editor.ov_mode.setCurrentText("count")
    win.region_editor.ov_value.setValue(40)
    pump(app, 100)
    regions = win.region_editor.to_list()
    print("regions:", regions)
    if len(regions) != 2:
        failures.append("expected 2 regions, got %d" % len(regions))
    if regions and regions[0].get("id") != "north_taiga":
        failures.append("region id not applied: %r" % (regions[0].get("id"),))
    if regions and regions[0].get("priority") != 7:
        failures.append("region priority not applied: %r" % (regions[0].get("priority"),))
    if regions and not regions[0].get("overrides"):
        failures.append("category override not applied to region")
    priorities = [r.get("priority") for r in regions]
    if len(set(priorities)) != len(priorities):
        failures.append("auto-assigned priorities collided: %r" % (priorities,))

    config = win._build_config()
    print("\nconfig handed to the generator:")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    if "regions" not in config:
        failures.append("config is missing the regions block")
    if "terrain" in config:
        failures.append("config should not carry terrain overrides after reset")

    win._on_generate()
    waited = 0
    while win.bridge.busy and waited < 120000:
        pump(app, 200)
        waited += 200

    if win.bridge.busy:
        failures.append("generation did not finish in time")
    if state["code"] is None:
        failures.append("finished signal never fired")

    code = state["code"]
    print("exit code:", code)
    print("progress records:", len(state["progress"]))
    for s, p in state["progress"]:
        print("   %-10s %3d%%" % (s, p))
    if not state["progress"]:
        failures.append("no progress records received")

    if code != EXIT_OK:
        failures.append("generation failed with exit %s" % code)
    else:
        s = state["summary"]
        if not isinstance(s, MapSummary):
            failures.append("no MapSummary on success")
        else:
            print("summary: label=%s theme=%s instances=%d contract=%s" % (
                s.label, s.theme_id, s.instance_count, s.contract_passed))
            if s.instance_count <= 0:
                failures.append("instance_count is zero")
            if not s.legend:
                failures.append("biome legend missing")
            img = render_map(s, 900, 700)
            if img is None:
                failures.append("preview render returned None")
            else:
                print("preview rendered: %dx%d" % (img.width(), img.height()))
            if win.lbl_preview.pixmap().isNull():
                failures.append("preview pixmap not set")

    SHOT.parent.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(SHOT))
    print("screenshot:", SHOT, "exists:", SHOT.exists())

    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
