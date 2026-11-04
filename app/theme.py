"""Dark theme for DMTOR."""
from PySide6.QtGui import QPalette, QColor

BG = "#15181d"
PANEL = "#1b1f26"
SIDEBAR = "#111418"
BORDER = "#262b33"
TEXT = "#e6e8eb"
MUTED = "#8b93a1"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#5a97f8"
ACCENT_DIM = "#1a2b45"

STATUS = {
    "queued": ("Queued", "#8b93a1"),
    "downloading": ("Downloading", "#5b9cff"),
    "pausing": ("Pausing…", "#f2a93b"),
    "paused": ("Paused", "#f2a93b"),
    "done": ("Completed", "#19a974"),
    "error": ("Failed", "#ef5f57"),
}


def qss(asset):
    return f"""
* {{ outline: 0; }}
QToolTip {{ background:{PANEL}; color:{TEXT}; border:1px solid {BORDER}; padding:6px 8px; border-radius:6px; }}

#SidePanel {{ background:{SIDEBAR}; border-right:1px solid #1f232a; }}
#BrandName {{ font-size:13pt; font-weight:700; color:#ffffff; }}
#BrandSub {{ color:{MUTED}; font-size:8.5pt; }}
#SideFooter {{ color:{MUTED}; font-size:9pt; padding:12px 16px; border-top:1px solid #1f232a; }}
QListWidget#Filters {{ background:transparent; border:none; padding:4px 0; }}
QListWidget#Filters::item {{ color:#b8bec8; padding:8px 10px; margin:1px 10px; border-radius:8px; }}
QListWidget#Filters::item:hover:!selected {{ background:#1a1e24; }}
QListWidget#Filters::item:selected {{ background:{ACCENT_DIM}; color:#ffffff; }}
QListWidget#Filters::item:disabled {{ color:#5b6270; font-size:8pt; font-weight:700; padding:14px 10px 4px; background:transparent; }}

QToolBar#Top {{ background:{BG}; border:none; border-bottom:1px solid #1f232a; padding:10px 12px; spacing:2px; }}
QToolBar#Top QToolButton {{ background:transparent; border:none; border-radius:8px; padding:7px 10px; color:#d8dce2; }}
QToolBar#Top QToolButton:hover {{ background:#222730; }}
QToolBar#Top QToolButton:pressed {{ background:#2a303a; }}
QToolBar#Top QToolButton:disabled {{ color:#4d5460; }}
QToolBar#Top QToolButton#Primary {{ background:{ACCENT}; color:#ffffff; font-weight:600; padding:7px 14px; margin-right:8px; }}
QToolBar#Top QToolButton#Primary:hover {{ background:{ACCENT_HOVER}; }}
QToolBar#Top QFrame#Sep {{ background:{BORDER}; }}
QToolBar#Top QToolButton#Capture {{ color:#9be3c4; }}
QToolBar#Top QToolButton#Speed[on="true"] {{ background:#1a2b40; color:#a9cbff; }}
QToolBar#Top QToolButton#Speed[on="true"]:hover {{ background:#21354e; }}
QToolBar#Top QToolButton::menu-button {{ border:none; width:16px; border-top-right-radius:8px; border-bottom-right-radius:8px; }}
QToolBar#Top QToolButton::menu-button:hover {{ background:#2a303a; }}
QToolBar#Top QToolButton::menu-arrow {{ image:url({asset('chevron-down.png')}); width:10px; height:10px; }}
QToolBar#Top QToolButton[popupMode="1"] {{ padding-right:22px; }}
QToolBar#Top QToolButton#Capture[off="true"] {{ background:#3a2a12; color:#ffd59a; }}
QToolBar#Top QToolButton#Capture[off="true"]:hover {{ background:#4a3516; }}

QTableWidget#List {{ background:{BG}; alternate-background-color:#171a20; border:none;
    selection-background-color:{ACCENT_DIM}; selection-color:#ffffff; }}
QTableWidget#List::item {{ border-bottom:1px solid #1d2127; padding-left:10px; }}
QTableWidget#List::item:selected {{ background:{ACCENT_DIM}; }}
QHeaderView::section {{ background:{BG}; color:{MUTED}; border:none; border-bottom:1px solid {BORDER};
    padding:9px 10px; font-weight:600; font-size:9pt; }}

#EmptyTitle {{ font-size:14pt; font-weight:600; color:#ffffff; }}
#Muted {{ color:{MUTED}; }}
#Title {{ font-size:14pt; font-weight:700; color:#ffffff; }}
#Warn {{ color:#f2a93b; }}

QDialog {{ background:{PANEL}; }}
QLineEdit, QComboBox, QSpinBox {{ background:#0f1216; border:1px solid #2a303a; border-radius:8px;
    padding:7px 10px; color:{TEXT}; selection-background-color:{ACCENT}; selection-color:#ffffff; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border:1px solid {ACCENT}; }}
QComboBox::drop-down {{ border:none; width:26px; }}
QComboBox::down-arrow {{ image:url({asset('chevron-down.png')}); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:{PANEL}; border:1px solid #2a303a; padding:4px;
    selection-background-color:{ACCENT_DIM}; selection-color:#ffffff; }}
QSpinBox::up-button, QSpinBox::down-button {{ border:none; width:20px; background:transparent; }}
QSpinBox::up-arrow {{ image:url({asset('chevron-up.png')}); width:10px; height:10px; }}
QSpinBox::down-arrow {{ image:url({asset('chevron-down.png')}); width:10px; height:10px; }}

QPushButton {{ background:#252a33; border:1px solid #2e343e; border-radius:8px; padding:8px 18px; color:{TEXT}; }}
QPushButton:hover {{ background:#2c323c; }}
QPushButton#Primary {{ background:{ACCENT}; border:none; color:#ffffff; font-weight:600; }}
QPushButton#Primary:hover {{ background:{ACCENT_HOVER}; }}
QPushButton#Danger {{ background:#3a1f1f; border:1px solid #5a2a2a; color:#ffb4ae; }}
QPushButton#Danger:hover {{ background:#4a2525; }}
QToolButton#Icon {{ background:#252a33; border:1px solid #2e343e; border-radius:8px; padding:6px; }}
QToolButton#Icon:hover {{ background:#2c323c; }}

QCheckBox {{ spacing:9px; }}
QCheckBox::indicator {{ width:16px; height:16px; border-radius:4px; border:1px solid #3a414c; background:#0f1216; }}
QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; image:url({asset('check.png')}); }}

QMenu {{ background:{PANEL}; border:1px solid #2a303a; border-radius:8px; padding:6px; }}
QMenu::item {{ padding:7px 26px 7px 12px; border-radius:6px; color:{TEXT}; }}
QMenu::item:selected {{ background:{ACCENT_DIM}; }}
QMenu::separator {{ height:1px; background:{BORDER}; margin:5px 6px; }}

QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:#2a303a; border-radius:4px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:#353c47; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:#2a303a; border-radius:4px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width:0; height:0; background:none; }}
QMessageBox {{ background:{PANEL}; }}
QTreeWidget#Files {{ background:#0f1216; alternate-background-color:#13161b; border:1px solid {BORDER};
    border-radius:10px; padding:4px; selection-background-color:{ACCENT_DIM}; }}
QTreeWidget#Files::item {{ padding:5px 2px; }}
QTreeWidget#Files::item:hover {{ background:#181c22; }}
QTreeWidget#Files::indicator {{ width:15px; height:15px; border-radius:4px; border:1px solid #3a414c; background:#0f1216; }}
QTreeWidget#Files::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; image:url({asset('check.png')}); }}
QTreeWidget#Files::indicator:indeterminate {{ background:{ACCENT_DIM}; border-color:{ACCENT}; image:url({asset('dash.png')}); }}
QPushButton:disabled {{ background:#1d2128; color:#5b6270; border-color:#262b33; }}
"""


def apply(app, asset):
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, "#0f1216"),
        (QPalette.AlternateBase, "#171a20"), (QPalette.ToolTipBase, PANEL), (QPalette.ToolTipText, TEXT),
        (QPalette.Text, TEXT), (QPalette.Button, "#252a33"), (QPalette.ButtonText, TEXT),
        (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#ffffff"),
        (QPalette.PlaceholderText, "#6b7380"), (QPalette.Link, ACCENT),
    ):
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor("#5b6270"))
    app.setPalette(pal)
    app.setStyleSheet(qss(asset))
