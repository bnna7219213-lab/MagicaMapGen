"""Dark-fantasy QSS theme for MagicaMapGen.

Pure stylesheet: no image assets, so the UI is functional before any border
material is sourced. CC0-only PNG nine-patch skins layer on later without touching
widget code (see assets/skins/README.md).

Palette: near-black parchment ground, aged-bronze structure, ember accent, kept
low-saturation so the map preview stays the brightest thing on screen.
"""

BG_DEEP = "#12100e"
BG_PANEL = "#1b1815"
BG_RAISED = "#241f1a"
BG_HOVER = "#2e2822"

BORDER = "#4a3f33"
BORDER_LIT = "#6b5a45"
BORDER_FOCUS = "#c08a3e"

TEXT = "#e8dcc8"
TEXT_DIM = "#a2937c"
TEXT_DISABLED = "#6b6154"

EMBER = "#c96a2b"
EMBER_LIT = "#e08a45"
RUNE = "#5b8a72"
WARN = "#c9a227"
DANGER = "#a63a2e"

#: Font stack for the dark-fantasy look. This is applied through QFont.setFamilies
#: rather than a QSS `font-family` rule: Qt's stylesheet parser silently ignored
#: `font-family` here and fell back to the system UI face, which rendered every
#: string as tofu boxes. Setting it on the QApplication is honoured reliably, and
#: setFamilies gives a real fallback chain instead of a single name.
FONT_STACK = [
    "Palatino Linotype",
    "Book Antiqua",
    "Georgia",
    "Segoe UI",
    "Times New Roman",
    "serif",
]


def build_font(size: int = 13):
    """The application font, with a genuine fallback chain."""
    from PyQt6.QtGui import QFont
    font = QFont("Palatino Linotype")
    font.setFamilies(FONT_STACK)
    font.setPointSize(size)
    return font


_SHEET = """
QWidget {
    background-color: %(BG_DEEP)s;
    color: %(TEXT)s;
    font-size: 13px;
}
QFrame#Panel {
    background-color: %(BG_PANEL)s;
    border: 1px solid %(BORDER)s;
    border-radius: 3px;
}
QFrame#Card {
    background-color: %(BG_RAISED)s;
    border: 1px solid %(BORDER)s;
    border-radius: 3px;
}
QFrame#Header {
    background-color: %(BG_PANEL)s;
    border: none;
    border-bottom: 2px solid %(BORDER_LIT)s;
}
QFrame#Divider {
    background-color: %(BORDER)s;
    max-height: 1px; min-height: 1px; border: none;
}
QLabel#Title {
    color: %(TEXT)s; font-size: 20px; font-weight: bold; letter-spacing: 1px;
}
QLabel#Subtitle { color: %(TEXT_DIM)s; font-size: 12px; }
QLabel#SectionLabel {
    color: %(EMBER_LIT)s; font-size: 12px; font-weight: bold; letter-spacing: 2px;
}
QLabel#Hint { color: %(TEXT_DIM)s; font-size: 11px; }
QLabel#StatBig { color: %(TEXT)s; font-size: 22px; font-weight: bold; }
QLabel#StatName { color: %(TEXT_DIM)s; font-size: 11px; }
QPushButton {
    background-color: %(BG_RAISED)s;
    border: 1px solid %(BORDER_LIT)s;
    border-radius: 3px; padding: 7px 16px; color: %(TEXT)s;
}
QPushButton:hover { background-color: %(BG_HOVER)s; border-color: %(EMBER)s; }
QPushButton:pressed { background-color: %(BG_DEEP)s; }
QPushButton:disabled {
    color: %(TEXT_DISABLED)s; border-color: %(BORDER)s;
    background-color: %(BG_PANEL)s;
}
QPushButton#Primary {
    background-color: %(EMBER)s; border: 1px solid %(EMBER_LIT)s;
    color: #1a1208; font-weight: bold; padding: 9px 22px;
}
QPushButton#Primary:hover { background-color: %(EMBER_LIT)s; }
QPushButton#Primary:disabled {
    background-color: %(BG_RAISED)s; color: %(TEXT_DISABLED)s;
    border-color: %(BORDER)s;
}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: %(BG_DEEP)s; border: 1px solid %(BORDER)s;
    border-radius: 3px; padding: 5px 8px; color: %(TEXT)s;
    selection-background-color: %(EMBER)s;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: %(BORDER_FOCUS)s;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: %(TEXT_DISABLED)s; background-color: %(BG_PANEL)s;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid %(EMBER_LIT)s;
}
QComboBox QAbstractItemView {
    background-color: %(BG_RAISED)s; border: 1px solid %(BORDER_LIT)s;
    selection-background-color: %(EMBER)s; color: %(TEXT)s;
}
QListWidget, QTreeWidget {
    background-color: %(BG_DEEP)s; border: 1px solid %(BORDER)s;
    border-radius: 3px; color: %(TEXT)s; outline: none;
}
QListWidget::item, QTreeWidget::item {
    padding: 5px 4px; border-bottom: 1px solid #1f1a16;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: %(EMBER)s; color: #1a1208;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background-color: %(BG_HOVER)s;
}
QTabWidget::pane {
    border: 1px solid %(BORDER)s; border-radius: 3px; top: -1px;
}
QTabBar::tab {
    background-color: %(BG_PANEL)s; border: 1px solid %(BORDER)s;
    border-bottom: none; padding: 7px 16px; margin-right: 1px;
    color: %(TEXT_DIM)s;
}
QTabBar::tab:selected {
    background-color: %(BG_RAISED)s; color: %(EMBER_LIT)s;
    border-top: 2px solid %(EMBER)s;
}
QTabBar::tab:hover:!selected { color: %(TEXT)s; }
QProgressBar {
    background-color: %(BG_DEEP)s; border: 1px solid %(BORDER)s;
    border-radius: 3px; height: 18px; text-align: center;
    color: %(TEXT)s; font-size: 11px;
}
QProgressBar::chunk { background-color: %(EMBER)s; border-radius: 2px; }
QScrollBar:vertical { background: %(BG_DEEP)s; width: 11px; border: none; }
QScrollBar::handle:vertical {
    background: %(BORDER_LIT)s; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(EMBER)s; }
QScrollBar:horizontal { background: %(BG_DEEP)s; height: 11px; border: none; }
QScrollBar::handle:horizontal {
    background: %(BORDER_LIT)s; border-radius: 5px; min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {
    background-color: %(BG_RAISED)s; color: %(TEXT)s;
    border: 1px solid %(EMBER)s; padding: 4px 6px;
}
"""

QSS = _SHEET % globals()
