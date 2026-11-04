"""Themes for DMTOR. Every color in the app comes from the active palette here."""
import sys

from PySide6.QtGui import QPalette, QColor

# key: (label, base colors). Everything else is derived from these.
THEMES = {
    "midnight": ("Midnight", dict(bg="#15181d", text="#e6e8eb", muted="#8b93a1", acc="#3b82f6", on_acc="#ffffff")),
    "graphite": ("Graphite", dict(bg="#161616", text="#ececec", muted="#8f8f8f", acc="#f97316", on_acc="#1a0b00")),
    "daylight": ("Daylight", dict(bg="#ffffff", text="#111827", muted="#6b7280", acc="#2563eb", on_acc="#ffffff",
                                  light=True)),
    "neon": ("Neon", dict(bg="#140f1f", text="#efe9ff", muted="#9d92bf", acc="#c026d3", on_acc="#ffffff")),
    "emerald": ("Emerald", dict(bg="#121816", text="#e4ece8", muted="#87968f", acc="#10b981", on_acc="#04140d")),
    "ocean": ("Ocean", dict(bg="#1f2633", text="#e5e9f0", muted="#94a0b4", acc="#14b8a6", on_acc="#03201c")),
}
CHOICES = [("system", "System (follow Windows)")] + [(k, v[0]) for k, v in THEMES.items()]

_STATUS_TEXT = {"queued": "Queued", "downloading": "Downloading", "pausing": "Pausing…",
                "paused": "Paused", "done": "Completed", "error": "Failed"}
_STATUS_DARK = {"queued": None, "downloading": "#5b9cff", "pausing": "#f2a93b", "paused": "#f2a93b",
                "done": "#19a974", "error": "#ef5f57"}
_STATUS_LIGHT = {"queued": None, "downloading": "#2563eb", "pausing": "#b45309", "paused": "#b45309",
                 "done": "#059669", "error": "#dc2626"}

C = {}          # the active palette
KEY = "midnight"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend color a toward b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def system_is_light():
    if sys.platform != "win32":
        return False
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v = winreg.QueryValueEx(k, "AppsUseLightTheme")[0]
        winreg.CloseKey(k)
        return bool(v)
    except OSError:
        return False


def resolve(key):
    if key == "system":
        return "daylight" if system_is_light() else "midnight"
    return key if key in THEMES else "midnight"


def build(key):
    b = dict(THEMES[key][1])
    bg, tx, acc = b["bg"], b["text"], b["acc"]
    light = b.get("light", False)
    m = lambda t: mix(bg, tx, t)   # noqa: E731  (step from background toward text)
    c = dict(b)
    c.update(
        light=light,
        side=m(0.035) if light else mix(bg, "#000000", 0.22),
        panel=bg if light else m(0.03),
        line=m(0.10), line2=m(0.06), row_line=m(0.05) if light else m(0.045),
        hover=m(0.05), press=m(0.09), alt=m(0.018) if light else m(0.012),
        field="#ffffff" if light else mix(bg, "#000000", 0.3),
        field_border=m(0.16) if light else m(0.11),
        btn=m(0.05) if light else m(0.08), btn_border=m(0.14) if light else m(0.12), btn_hover=m(0.09) if light else m(0.11),
        track=m(0.10), scroll=m(0.16) if light else m(0.12), scroll_hover=m(0.25) if light else m(0.17),
        icon=m(0.80) if light else m(0.88), side_text=m(0.72) if light else m(0.75),
        faint=m(0.32) if light else m(0.30), strong="#0b1220" if light else "#ffffff",
        progress_text=m(0.75) if light else m(0.82), placeholder=m(0.45),
        acc_hover=mix(acc, "#000000", 0.12) if light else mix(acc, "#ffffff", 0.18),
        acc_dim=mix(bg, acc, 0.14) if light else mix(bg, acc, 0.22),
        info_bg=mix(bg, acc, 0.12) if light else mix(bg, acc, 0.16),
        info_fg=mix(acc, "#000000", 0.2) if light else mix(acc, "#ffffff", 0.45),
        warn_bg="#fff1db" if light else "#3a2a12", warn_fg="#9a5b00" if light else "#ffd59a",
        warn_text="#b45309" if light else "#f2a93b",
        danger_bg="#fde8e8" if light else "#3a1f1f", danger_border="#f5b5b0" if light else "#5a2a2a",
        danger_fg="#b42318" if light else "#ffb4ae", danger_icon="#dc2626" if light else "#ef8f89",
        ok="#059669" if light else "#19a974",
        teal="#0d9488" if light else "#2dd4bf", folder="#d39b1f" if light else "#e8c26a",
    )
    return c


def status(name):
    table = _STATUS_LIGHT if C.get("light") else _STATUS_DARK
    return _STATUS_TEXT.get(name, name), table.get(name) or C["muted"]


def c(name):
    return C[name]


def qss(asset):
    c = C
    return f"""
* {{ outline: 0; }}
QToolTip {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; padding:6px 8px; border-radius:6px; }}

#SidePanel {{ background:{c['side']}; border-right:1px solid {c['line2']}; }}
#BrandName {{ font-size:13pt; font-weight:700; color:{c['strong']}; }}
#BrandSub {{ color:{c['muted']}; font-size:8.5pt; }}
#SideFooter {{ color:{c['muted']}; font-size:9pt; padding:12px 16px; border-top:1px solid {c['line2']}; }}
QListWidget#Filters {{ background:transparent; border:none; padding:4px 0; }}
QListWidget#Filters::item {{ color:{c['side_text']}; padding:8px 10px; margin:1px 10px; border-radius:8px; }}
QListWidget#Filters::item:hover:!selected {{ background:{c['hover']}; }}
QListWidget#Filters::item:selected {{ background:{c['acc_dim']}; color:{c['strong']}; }}
QListWidget#Filters::item:disabled {{ color:{c['faint']}; font-size:8pt; font-weight:700; padding:14px 10px 4px; background:transparent; }}

#Banner {{ background:{c['info_bg']}; border-bottom:1px solid {c['line2']}; }}
#Banner QLabel {{ color:{c['text']}; }}

QToolBar#Top {{ background:{c['bg']}; border:none; border-bottom:1px solid {c['line2']}; padding:10px 12px; spacing:2px; }}
QToolBar#Top QToolButton {{ background:transparent; border:none; border-radius:8px; padding:7px 10px; color:{c['icon']}; }}
QToolBar#Top QToolButton:hover {{ background:{c['hover']}; }}
QToolBar#Top QToolButton:pressed {{ background:{c['press']}; }}
QToolBar#Top QToolButton:disabled {{ color:{c['faint']}; }}
QToolBar#Top QToolButton#Primary {{ background:{c['acc']}; color:{c['on_acc']}; font-weight:600; padding:7px 14px; margin-right:8px; }}
QToolBar#Top QToolButton#Primary:hover {{ background:{c['acc_hover']}; }}
QToolBar#Top QFrame#Sep {{ background:{c['line']}; }}
QToolBar#Top QToolButton#Speed[on="true"], QToolBar#Top QToolButton#WhenDone[on="true"] {{ background:{c['info_bg']}; color:{c['info_fg']}; }}
QToolBar#Top QToolButton::menu-button {{ border:none; width:16px; border-top-right-radius:8px; border-bottom-right-radius:8px; }}
QToolBar#Top QToolButton::menu-button:hover {{ background:{c['press']}; }}
QToolBar#Top QToolButton::menu-arrow {{ image:url({asset('chevron-down.png')}); width:10px; height:10px; }}
QToolBar#Top QToolButton::menu-indicator {{ image:none; width:0; }}
QToolBar#Top QToolButton[popupMode="1"] {{ padding-right:22px; }}
QToolBar#Top QToolButton#Capture[off="true"] {{ background:{c['warn_bg']}; color:{c['warn_fg']}; }}

QTableWidget#List {{ background:{c['bg']}; alternate-background-color:{c['alt']}; border:none; color:{c['text']};
    selection-background-color:{c['acc_dim']}; selection-color:{c['strong']}; }}
QTableWidget#List::item {{ border-bottom:1px solid {c['row_line']}; padding-left:10px; }}
QTableWidget#List::item:selected {{ background:{c['acc_dim']}; color:{c['strong']}; }}
QHeaderView::section {{ background:{c['bg']}; color:{c['muted']}; border:none; border-bottom:1px solid {c['line']};
    padding:9px 10px; font-weight:600; font-size:9pt; }}

#EmptyTitle {{ font-size:14pt; font-weight:600; color:{c['strong']}; }}
#Muted {{ color:{c['muted']}; }}
#Section {{ color:{c['muted']}; font-size:8pt; font-weight:700; padding-top:6px; }}
#Title {{ font-size:14pt; font-weight:700; color:{c['strong']}; }}
#Warn {{ color:{c['warn_text']}; }}
#Big {{ font-size:22pt; font-weight:700; color:{c['strong']}; }}

QDialog {{ background:{c['panel']}; }}
QTabWidget::pane {{ border:none; border-top:1px solid {c['line']}; top:-1px; }}
QTabBar::tab {{ background:transparent; color:{c['muted']}; padding:8px 14px; border:none;
    border-bottom:2px solid transparent; margin-right:2px; }}
QTabBar::tab:hover {{ color:{c['text']}; }}
QTabBar::tab:selected {{ color:{c['strong']}; border-bottom:2px solid {c['acc']}; font-weight:600; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:none; }}

QLineEdit, QComboBox, QSpinBox, QTimeEdit {{ background:{c['field']}; border:1px solid {c['field_border']}; border-radius:8px;
    padding:7px 10px; color:{c['text']}; selection-background-color:{c['acc']}; selection-color:{c['on_acc']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {{ border:1px solid {c['acc']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTimeEdit:disabled {{ color:{c['faint']}; }}
QComboBox::drop-down {{ border:none; width:26px; }}
QComboBox::down-arrow {{ image:url({asset('chevron-down.png')}); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:{c['panel']}; border:1px solid {c['field_border']}; padding:4px; color:{c['text']};
    selection-background-color:{c['acc_dim']}; selection-color:{c['strong']}; }}
QSpinBox::up-button, QSpinBox::down-button, QTimeEdit::up-button, QTimeEdit::down-button {{ border:none; width:20px; background:transparent; }}
QSpinBox::up-arrow, QTimeEdit::up-arrow {{ image:url({asset('chevron-up.png')}); width:10px; height:10px; }}
QSpinBox::down-arrow, QTimeEdit::down-arrow {{ image:url({asset('chevron-down.png')}); width:10px; height:10px; }}

QPushButton {{ background:{c['btn']}; border:1px solid {c['btn_border']}; border-radius:8px; padding:8px 18px; color:{c['text']}; }}
QPushButton:hover {{ background:{c['btn_hover']}; }}
QPushButton:checked {{ background:{c['acc_dim']}; border-color:{c['acc']}; color:{c['strong']}; }}
QPushButton#Primary {{ background:{c['acc']}; border:none; color:{c['on_acc']}; font-weight:600; }}
QPushButton#Primary:hover {{ background:{c['acc_hover']}; }}
QPushButton#Danger {{ background:{c['danger_bg']}; border:1px solid {c['danger_border']}; color:{c['danger_fg']}; }}
QPushButton:disabled {{ background:{c['hover']}; color:{c['faint']}; border-color:{c['line']}; }}
QToolButton#Icon {{ background:{c['btn']}; border:1px solid {c['btn_border']}; border-radius:8px; padding:6px; color:{c['text']}; }}
QToolButton#Icon:hover {{ background:{c['btn_hover']}; }}

QCheckBox, QRadioButton {{ spacing:9px; color:{c['text']}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color:{c['faint']}; }}
QCheckBox::indicator {{ width:16px; height:16px; border-radius:4px; border:1px solid {c['field_border']}; background:{c['field']}; }}
QCheckBox::indicator:checked {{ background:{c['acc']}; border-color:{c['acc']}; image:url({asset('check.png')}); }}
QRadioButton::indicator {{ width:16px; height:16px; border-radius:8px; border:1px solid {c['field_border']}; background:{c['field']}; }}
QRadioButton::indicator:checked {{ border:5px solid {c['acc']}; background:{c['on_acc']}; }}

QMenu {{ background:{c['panel']}; border:1px solid {c['field_border']}; border-radius:8px; padding:6px; }}
QMenu::item {{ padding:7px 26px 7px 12px; border-radius:6px; color:{c['text']}; }}
QMenu::item:selected {{ background:{c['acc_dim']}; color:{c['strong']}; }}
QMenu::item:disabled {{ color:{c['faint']}; }}
QMenu::separator {{ height:1px; background:{c['line']}; margin:5px 6px; }}

QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{c['scroll']}; border-radius:4px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{c['scroll_hover']}; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{c['scroll']}; border-radius:4px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width:0; height:0; background:none; }}
QMessageBox {{ background:{c['panel']}; }}
QMessageBox QLabel {{ color:{c['text']}; }}
QProgressBar {{ background:{c['track']}; border:none; border-radius:4px; height:8px; color:transparent; }}
QProgressBar::chunk {{ background:{c['acc']}; border-radius:4px; }}
QTreeWidget#Files {{ background:{c['field']}; alternate-background-color:{c['alt']}; border:1px solid {c['line']}; color:{c['text']};
    border-radius:10px; padding:4px; selection-background-color:{c['acc_dim']}; selection-color:{c['strong']}; }}
QTreeWidget#Files::item {{ padding:5px 2px; }}
QTreeWidget#Files::item:hover {{ background:{c['hover']}; }}
QTreeWidget#Files::indicator {{ width:15px; height:15px; border-radius:4px; border:1px solid {c['field_border']}; background:{c['field']}; }}
QTreeWidget#Files::indicator:checked {{ background:{c['acc']}; border-color:{c['acc']}; image:url({asset('check.png')}); }}
QTreeWidget#Files::indicator:indeterminate {{ background:{c['acc_dim']}; border-color:{c['acc']}; image:url({asset('dash.png')}); }}
"""


def apply(app, asset, key="midnight"):
    """Activate a theme (key may be 'system'). Returns the concrete theme key in use."""
    global KEY
    KEY = resolve(key)
    C.clear()
    C.update(build(KEY))
    c = C
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, c["bg"]), (QPalette.WindowText, c["text"]), (QPalette.Base, c["field"]),
        (QPalette.AlternateBase, c["alt"]), (QPalette.ToolTipBase, c["panel"]), (QPalette.ToolTipText, c["text"]),
        (QPalette.Text, c["text"]), (QPalette.Button, c["btn"]), (QPalette.ButtonText, c["text"]),
        (QPalette.Highlight, c["acc"]), (QPalette.HighlightedText, c["on_acc"]),
        (QPalette.PlaceholderText, c["placeholder"]), (QPalette.Link, c["acc"]),
        (QPalette.BrightText, c["strong"]),
    ):
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor(c["faint"]))
    app.setPalette(pal)
    app.setStyleSheet(qss(asset))
    return KEY


# load something sensible before apply() is called (e.g. in tests)
C.update(build("midnight"))
