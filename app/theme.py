"""Themes for MZ-DManager. Every color in the app comes from the active palette here."""
import sys

from PySide6.QtGui import QPalette, QColor

# key: (label, base colors). Everything else is derived from these.
THEMES = {
    "aurora": ("Aurora", dict(bg="#101219", text="#e7e8ee", muted="#8d92a6", acc="#a855f7", acc2="#14b8a6",
                              on_acc="#ffffff")),
    "glass": ("Glass", dict(bg="#070d1c", text="#e6f1ff", muted="#8ea3c2", acc="#22d3ee", acc2="#3b82f6",
                            on_acc="#03131c")),
    "midnight": ("Midnight", dict(bg="#15181d", text="#e6e8eb", muted="#8b93a1", acc="#3b82f6", acc2="#22d3ee",
                                  on_acc="#ffffff")),
    "graphite": ("Graphite", dict(bg="#161616", text="#ececec", muted="#8f8f8f", acc="#f97316", acc2="#facc15",
                                  on_acc="#1a0b00")),
    "daylight": ("Daylight", dict(bg="#f6f7fb", text="#111827", muted="#6b7280", acc="#7c3aed", acc2="#0d9488",
                                  on_acc="#ffffff", light=True)),
    "neon": ("Neon", dict(bg="#140f1f", text="#efe9ff", muted="#9d92bf", acc="#c026d3", acc2="#6366f1",
                          on_acc="#ffffff")),
    "emerald": ("Emerald", dict(bg="#121816", text="#e4ece8", muted="#87968f", acc="#10b981", acc2="#a3e635",
                                on_acc="#04140d")),
    "ocean": ("Ocean", dict(bg="#1f2633", text="#e5e9f0", muted="#94a0b4", acc="#14b8a6", acc2="#38bdf8",
                            on_acc="#03201c")),
}
CHOICES = [("system", "System (follow Windows)")] + [(k, v[0]) for k, v in THEMES.items()]

_STATUS_TEXT = {"queued": "Queued", "downloading": "Downloading", "pausing": "Pausing…",
                "paused": "Paused", "done": "Completed", "error": "Failed"}
_STATUS_DARK = {"queued": None, "downloading": "#5b9cff", "pausing": "#f2a93b", "paused": "#f2a93b",
                "done": "#19a974", "error": "#ef5f57"}
_STATUS_LIGHT = {"queued": None, "downloading": "#2563eb", "pausing": "#b45309", "paused": "#b45309",
                 "done": "#059669", "error": "#dc2626"}

C = {}          # the active palette
KEY = "aurora"


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
        return "daylight" if system_is_light() else "aurora"
    return key if key in THEMES else "aurora"


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
        card="#ffffff" if light else m(0.035), card_border=m(0.09) if light else m(0.07),
        row_hover=m(0.04) if light else m(0.045), row_sel=mix(bg, acc, 0.10) if light else mix(bg, acc, 0.13),
        card_hi="#ffffff" if light else mix(m(0.06), acc, 0.05), card_in=m(0.025) if light else m(0.05),
        glow_border=mix(m(0.1), acc, 0.35) if light else mix(m(0.08), acc, 0.32),
    )
    c["grad"] = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['acc2']}, stop:1 {c['acc']})"
    a2h, ah = mix(c["acc2"], "#ffffff", 0.12), mix(c["acc"], "#ffffff", 0.12)
    c["grad_h"] = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {a2h}, stop:1 {ah})"
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
QToolButton#SideBtn {{ background:transparent; border:none; border-radius:8px; color:{c['side_text']};
    padding:8px 10px; margin:0 10px 8px 10px; text-align:left; }}
QToolButton#SideBtn:hover {{ background:{c['hover']}; color:{c['strong']}; }}
#SideFooter {{ color:{c['muted']}; font-size:9pt; padding:12px 16px; border-top:1px solid {c['line2']}; }}
QListWidget#Filters {{ background:transparent; border:none; padding:4px 0; }}
QListWidget#Filters::item {{ color:{c['side_text']}; padding:8px 10px; margin:1px 10px; border-radius:8px; }}
QListWidget#Filters::item:hover:!selected {{ background:{c['hover']}; }}
QListWidget#Filters::item:selected {{ background:{c['acc_dim']}; color:{c['strong']}; }}
QListWidget#Filters::item:disabled {{ color:{c['faint']}; font-size:8pt; font-weight:700; padding:14px 10px 4px; background:transparent; }}

#Banner {{ background:{c['info_bg']}; border-bottom:1px solid {c['line2']}; }}
#Banner QLabel {{ color:{c['text']}; }}

QToolBar#Top {{ background:{c['bg']}; border:none; border-bottom:1px solid {c['line2']}; padding:10px 10px; spacing:1px; }}
QToolBar#Top QToolButton {{ background:transparent; border:none; border-radius:8px; padding:7px 9px; color:{c['icon']}; }}
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
QToolBar#Top QToolButton#qt_toolbar_ext_button {{ background:{c['btn']}; border-radius:6px; padding:2px; }}
QToolBar#Top QToolButton[popupMode="1"] {{ padding-right:22px; }}
QToolBar#Top QToolButton#Capture[off="true"] {{ background:{c['warn_bg']}; color:{c['warn_fg']}; }}

/* ---------- new main window ---------- */
#Root, #Body, #Right {{ background:{c['bg']}; }}
#Header {{ background:{c['bg']}; border-bottom:1px solid {c['line2']}; }}
#HeaderBrand {{ color:{c['strong']}; font-weight:700; font-size:11pt; }}
QMenuBar#MainMenu {{ background:transparent; color:{c['muted']}; spacing:6px; }}
QMenuBar#MainMenu::item {{ background:transparent; padding:6px 12px; border-radius:7px; color:{c['muted']}; }}
QMenuBar#MainMenu::item:selected {{ background:{c['hover']}; color:{c['strong']}; }}
QLineEdit#Search {{ background:{c['card']}; border:1px solid {c['card_border']}; border-radius:14px;
    padding:8px 12px; min-width:260px; }}
QLineEdit#Search:focus {{ border:1px solid {c['acc']}; }}
#VLine {{ background:{c['line2']}; }}
QFrame#Card {{ background:{c['card']}; border:1px solid {c['card_border']}; border-radius:16px; }}
QTreeWidget#Nav {{ background:transparent; border:none; color:{c['side_text']}; outline:0; }}
QTreeWidget#Nav::item {{ padding:5px 4px; border-radius:8px; margin:0; }}
QTreeWidget#Nav::item:hover {{ background:{c['hover']}; }}
QTreeWidget#Nav::item:selected {{ background:{c['row_sel']}; color:{c['strong']}; }}
QTreeWidget#Nav::branch {{ background:transparent; image:none; border:none; }}
#CardTitle {{ color:{c['strong']}; font-weight:600; }}
#GaugeText {{ color:{c['strong']}; font-size:17pt; font-weight:700; }}
QPushButton#Gradient {{ background:{c['grad']}; border:none; border-radius:14px; color:{c['on_acc']};
    font-weight:600; padding:11px 18px; }}
QPushButton#Gradient:hover {{ background:{c['grad_h']}; }}
QToolButton#Flat {{ background:transparent; border:none; border-radius:8px; padding:4px; }}
QToolButton#Flat::menu-indicator {{ image:none; width:0; }}
QToolButton#Flat:hover {{ background:{c['hover']}; }}

QToolBar#Tools {{ background:{c['bg']}; border:none; border-bottom:1px solid {c['line2']}; padding:12px 10px; spacing:0px; }}
QToolBar#Tools QToolButton {{ background:transparent; border:none; border-radius:10px; padding:6px 3px;
    color:{c['muted']}; min-width:54px; }}
QToolBar#Tools QToolButton:hover {{ background:{c['hover']}; color:{c['strong']}; }}
QToolBar#Tools QToolButton:pressed {{ background:{c['press']}; }}
QToolBar#Tools QToolButton:disabled {{ color:{c['faint']}; }}
QToolBar#Tools QToolButton[on="true"] {{ color:{c['info_fg']}; }}
QToolBar#Tools QToolButton::menu-indicator {{ image:none; width:0; }}
QToolBar#Tools QToolButton::menu-button {{ border:none; width:0; }}
QToolBar#Tools QFrame#VLine {{ background:{c['line']}; }}
QFrame#AddPill {{ background:{c['card']}; border:1px solid {c['card_border']}; border-radius:16px; }}
QFrame#AddPill QLineEdit {{ background:transparent; border:none; padding:6px 4px; font-size:11pt; }}
QToolBar#Tools QToolButton#Go {{ background:{c['grad']}; border:none; border-radius:14px; min-width:0; padding:0; }}
QToolBar#Tools QToolButton#Go:hover {{ background:{c['grad_h']}; }}

#Bottom {{ background:{c['bg']}; border-top:1px solid {c['line2']}; }}
#Bottom QLabel {{ color:{c['muted']}; }}
#SpeedVal {{ color:{c['strong']}; font-weight:600; }}
QToolButton#CatchPill {{ background:{c['card']}; border:1px solid {c['card_border']}; border-radius:12px;
    padding:5px 12px; color:{c['muted']}; }}
QToolButton#CatchPill:hover {{ color:{c['strong']}; }}
QToolButton#CatchPill[off="true"] {{ background:{c['warn_bg']}; color:{c['warn_fg']}; border-color:{c['warn_bg']}; }}

/* ---------- simple layout ---------- */
QFrame#Rail {{ background:{c['side']}; border-right:1px solid {c['line2']}; }}
QToolButton#RailBtn {{ background:transparent; border:none; border-radius:10px; padding:0 10px; text-align:left;
    color:{c['side_text']}; }}
QToolButton#RailBtn:hover {{ background:{c['hover']}; color:{c['strong']}; }}
QToolButton#RailBtn:checked {{ background:{c['row_sel']}; color:{c['strong']}; font-weight:600; }}
QToolButton#RailBtn[on="true"] {{ background:{c['info_bg']}; color:{c['info_fg']}; }}
QToolButton#RailBtn::menu-indicator {{ image:none; width:0; }}
QToolButton#RailAdd {{ background:{c['acc']}; border:none; border-radius:12px; padding:0 12px; color:{c['on_acc']};
    font-weight:600; text-align:left; }}
QToolButton#RailAdd:hover {{ background:{c['acc_hover']}; }}
#RailSection {{ color:{c['faint']}; font-size:8pt; font-weight:700; padding:4px 12px 2px; }}
QLabel#RailBadge {{ background:{c['hover']}; color:{c['muted']}; border-radius:9px; font-size:8pt; font-weight:600; }}
QLabel#RailBadge[kind="acc"] {{ background:{c['acc']}; color:{c['on_acc']}; }}
QLabel#RailBadge[kind="danger"] {{ background:{c['danger_icon']}; color:#ffffff; }}
QToolButton#Chip {{ background:transparent; border:1px solid {c['card_border']}; border-radius:14px; padding:5px 12px;
    color:{c['muted']}; }}
QToolButton#Chip:hover {{ color:{c['strong']}; background:{c['hover']}; }}
QToolButton#Chip:checked {{ background:{c['row_sel']}; border-color:{c['glow_border']}; color:{c['strong']}; }}
QPushButton#Soft, QPushButton#SoftDanger {{ background:{c['btn']}; border:1px solid {c['btn_border']}; border-radius:10px;
    padding:7px 13px; color:{c['text']}; }}
QPushButton#Soft:hover {{ background:{c['btn_hover']}; }}
QPushButton#SoftDanger {{ color:{c['danger_fg']}; }}
QPushButton#SoftDanger:hover {{ background:{c['danger_bg']}; border-color:{c['danger_border']}; }}
QPushButton#Soft:disabled, QPushButton#SoftDanger:disabled {{ color:{c['faint']}; background:transparent; border-color:{c['line2']}; }}
QToolButton#LinkBtn::menu-indicator {{ image:url({asset('chevron-down.png')}); width:10px; height:10px; subcontrol-position:right center; }}
QToolButton#LinkBtn {{ padding-right:16px; }}
QFrame#SelBar {{ background:{c['card_hi']}; border:1px solid {c['glow_border']}; border-radius:14px; }}
#SelText {{ color:{c['strong']}; font-weight:600; }}
QToolButton#SelBtn, QToolButton#SelBtnDanger {{ background:transparent; border:none; border-radius:9px; padding:6px 10px; color:{c['text']}; }}
QToolButton#SelBtn:hover {{ background:{c['hover']}; }}
QToolButton#SelBtn:disabled {{ color:{c['faint']}; }}
QToolButton#SelBtnDanger {{ color:{c['danger_fg']}; }}
QToolButton#SelBtnDanger:hover {{ background:{c['danger_bg']}; }}

/* ---------- dashboard layout ---------- */
QFrame#GCard {{ background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['card_hi']}, stop:1 {c['card']});
    border:1px solid {c['glow_border']}; border-radius:18px; }}
QFrame#GInner {{ background:{c['card_in']}; border:1px solid {c['card_border']}; border-radius:14px; }}
QFrame#GRow {{ background:{c['card_in']}; border:1px solid {c['card_border']}; border-radius:12px; }}
QFrame#GRow:hover {{ border:1px solid {c['glow_border']}; }}
QFrame#GRow[sel="true"] {{ border:1px solid {c['acc']}; background:{c['row_sel']}; }}
QFrame#GBottom {{ background:transparent; border-top:1px solid {c['line2']}; }}
#BrandBig {{ color:{c['strong']}; font-size:16pt; font-weight:700; }}
#PageTitle {{ color:{c['strong']}; font-size:17pt; font-weight:700; }}
#SectionTitle {{ color:{c['strong']}; font-size:12.5pt; font-weight:700; }}
#StatValue {{ color:{c['strong']}; font-size:18pt; font-weight:700; }}
QLabel#StatIcon {{ background:{c['row_sel']}; border-radius:22px; }}
#RowName {{ color:{c['strong']}; font-weight:600; }}
#RowMeta {{ color:{c['text']}; }}
#DetailVal {{ color:{c['strong']}; }}
#NetDown {{ color:{c['acc']}; font-weight:700; font-size:11pt; }}
#NetUp {{ color:{c['acc2']}; font-weight:700; font-size:11pt; }}
QLabel#NavBadge {{ background:{c['acc']}; color:{c['on_acc']}; border-radius:11px; font-weight:700; }}
QToolButton#NavBtn {{ background:transparent; border:1px solid transparent; border-radius:12px; padding:8px 12px;
    color:{c['text']}; text-align:left; font-size:11pt; }}
QToolButton#NavBtn:hover {{ background:{c['hover']}; }}
QToolButton#NavBtn:checked {{ background:{c['row_sel']}; border:1px solid {c['glow_border']}; color:{c['strong']};
    font-weight:600; }}
QToolButton#RoundBtn {{ background:{c['btn']}; border:1px solid {c['btn_border']}; border-radius:17px; }}
QToolButton#RoundBtn:hover {{ background:{c['btn_hover']}; }}
QToolButton#SquareBtn {{ background:{c['card_in']}; border:1px solid {c['card_border']}; border-radius:12px; }}
QToolButton#SquareBtn:hover {{ border-color:{c['glow_border']}; }}
QToolButton#PillBtn {{ background:{c['btn']}; border:1px solid {c['btn_border']}; border-radius:10px; padding:6px 12px;
    color:{c['text']}; }}
QToolButton#PillBtn:hover {{ background:{c['btn_hover']}; }}
QToolButton#LinkBtn {{ background:transparent; border:none; color:{c['text']}; padding:4px 6px; }}
QToolButton#LinkBtn:hover {{ color:{c['acc']}; }}
QToolButton#DirBtn {{ background:{c['card_in']}; border:1px solid {c['card_border']}; border-radius:12px;
    padding:8px 14px; color:{c['text']}; min-width:260px; text-align:left; }}
QToolButton#DirBtn::menu-indicator {{ image:url({asset('chevron-down.png')}); subcontrol-position:right center;
    right:10px; width:12px; height:12px; }}

QTableWidget#List {{ background:{c['bg']}; alternate-background-color:{c['alt']}; border:none; color:{c['text']};
    selection-background-color:{c['acc_dim']}; selection-color:{c['strong']}; }}
QTableWidget#List::item {{ border:none; padding-left:10px; }}
QTableWidget#List::item:selected {{ background:transparent; color:{c['strong']}; }}
QHeaderView::section {{ background:{c['bg']}; color:{c['muted']}; border:none; border-bottom:1px solid {c['line2']};
    padding:12px 10px; font-size:10pt; }}
QHeaderView::up-arrow, QHeaderView::down-arrow {{ width:0; height:0; image:none; }}

#InfoCard {{ background:{c['field']}; border:1px solid {c['line']}; border-radius:12px; }}
#InfoName {{ color:{c['strong']}; font-weight:600; }}
#InfoSize {{ color:{c['acc']}; font-size:15pt; font-weight:700; }}
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


def apply(app, asset, key="aurora"):
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
C.update(build("aurora"))
