"""EDENLOAD - main window."""
import os
import re
import sys
import queue
import time
import tempfile
import threading
import subprocess
import urllib.request
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, QPoint, QObject, Signal, QEvent
from PySide6.QtGui import (QIcon, QFont, QPainter, QColor, QKeySequence, QShortcut, QPixmap, QPen, QBrush,
                           QLinearGradient, QConicalGradient, QPainterPath, QActionGroup)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QToolBar, QToolButton,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QComboBox,
    QLabel, QFileDialog, QSpinBox, QCheckBox, QMessageBox, QSystemTrayIcon, QMenu,
    QHeaderView, QAbstractItemView, QWidget, QFrame, QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator, QTabWidget, QTimeEdit, QProgressBar, QScrollArea, QGridLayout,
    QStyle, QMenuBar,
)
from PySide6.QtCore import QTime

import theme
import features
import core
import probe
from features import ACTIONS, DAYS
from icons import icon, pixmap, CATEGORY_ICON
from core import human_size, human_time, category_of, fmt_rate
from manager import Manager
from server import make_server, PORT
from video import QUALITIES, ffmpeg_path
import torrent
from torrent import is_torrent_source

APP_NAME = "EDENLOAD"
LEGACIES = ("DMTOR", "EdenDM")   # names of earlier versions; cleaned up from the registry
VIDEO_SITES = re.compile(
    r"(youtube\.com|youtu\.be|facebook\.com|fb\.watch|instagram\.com|tiktok\.com|twitter\.com|"
    r"(^|//|\.)x\.com|vimeo\.com|dailymotion\.com|twitch\.tv|reddit\.com|soundcloud\.com)", re.I)


T = theme.c   # T("icon") → color of the active theme


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.normpath(os.path.join(base, "assets", name))


def app_icon_path():
    p = resource(f"app_{theme.KEY}.png")
    return p if os.path.isfile(p) else resource("app.png")


def asset_url(name):
    return resource(name).replace("\\", "/")


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path):
    if sys.platform == "win32" and os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)


def launch_cmd(arg):
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {arg}'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}" {arg}'


def set_startup(enabled):
    if sys.platform != "win32":
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        if enabled:
            winreg.SetValueEx(key, "EDENLOAD", 0, winreg.REG_SZ, launch_cmd("--tray"))
        else:
            try:
                winreg.DeleteValue(key, "EDENLOAD")
            except FileNotFoundError:
                pass
        for old in LEGACIES:
            try:
                winreg.DeleteValue(key, old)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def set_torrent_assoc(enabled):
    """Open magnet: links and .torrent files with EDENLOAD (per-user, no admin needed)."""
    if sys.platform != "win32":
        return
    import winreg
    base = "Software\\Classes\\"
    exe_icon = f'"{sys.executable}",0'
    cmd = launch_cmd('"%1"')

    def put(path, values):
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + path)
        for name, val in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.CloseKey(k)

    def drop(path):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + path, 0, winreg.KEY_ALL_ACCESS)
        except OSError:
            return
        while True:
            try:
                sub = winreg.EnumKey(k, 0)
            except OSError:
                break
            drop(path + "\\" + sub)
        winreg.CloseKey(k)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + path)
        except OSError:
            pass

    if enabled:
        put("magnet", {"": "URL:Magnet link", "URL Protocol": ""})
        put("magnet\\DefaultIcon", {"": exe_icon})
        put("magnet\\shell\\open\\command", {"": cmd})
        for old in LEGACIES:
            drop(old + ".torrent")
        put("EDENLOAD.torrent", {"": "Torrent file"})
        put("EDENLOAD.torrent\\DefaultIcon", {"": exe_icon})
        put("EDENLOAD.torrent\\shell\\open\\command", {"": cmd})
        put(".torrent", {"": "EDENLOAD.torrent"})
        put(".torrent\\OpenWithProgids", {"EDENLOAD.torrent": ""})
    else:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + "magnet\\shell\\open\\command")
            current = winreg.QueryValueEx(k, "")[0]
            winreg.CloseKey(k)
        except OSError:
            current = ""
        if any(n in current for n in ("EDENLOAD",) + LEGACIES) or sys.executable in current:
            drop("magnet")
        drop("EDENLOAD.torrent")
        for old in LEGACIES:
            drop(old + ".torrent")
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + ".torrent", 0, winreg.KEY_ALL_ACCESS)
            if winreg.QueryValueEx(k, "")[0] in tuple(n + ".torrent" for n in ("EDENLOAD",) + LEGACIES):
                winreg.DeleteValue(k, "")
            winreg.CloseKey(k)
        except OSError:
            pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def args_to_payloads(argv):
    out = []
    for a in argv:
        if a.startswith("--"):
            continue
        if a.lower().startswith("magnet:"):
            out.append({"type": "torrent", "url": a})
        elif a.lower().endswith(".torrent") and os.path.isfile(a):
            out.append({"type": "torrent", "url": os.path.abspath(a)})
        elif a.lower().startswith(("http://", "https://")):
            out.append({"type": "torrent" if is_torrent_source(a) else "file", "url": a})
    return out


def item_category(it):
    if it.kind == "torrent":
        return "Torrents"
    if it.kind == "video":
        return "Music" if getattr(it, "quality", "") == "audio" else "Video"
    return category_of(it.name) if it.name else "Other"


def clipboard_url():
    text = (QApplication.clipboard().text() or "").strip()
    return text if re.match(r"^(https?://|magnet:\?)\S+$", text, re.I) else ""


def primary(btn):
    btn.setObjectName("Primary")
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def label(text, name=None, wrap=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


# ---------------------------------------------------------------- table painters
TYPE_LABEL = {"Video": "Video", "Music": "Music", "Programs": "Program", "Documents": "Document",
              "Compressed": "Archive", "Images": "Image", "Torrents": "Torrent", "Other": "File"}


class RowDelegate(QStyledItemDelegate):
    """Paints the rounded row background (hover / selected / checked) — every column uses it."""

    def __init__(self, table, first=False, last=False):
        super().__init__(table)
        self.table, self.first, self.last = table, first, last

    def row_bg(self, p, opt, idx):
        row = idx.row()
        sel = bool(opt.state & QStyle.State_Selected)
        hover = self.table.property("hoverRow") == row
        if not (sel or hover):
            return
        r = QRectF(opt.rect).adjusted(0, 4, 0, -4)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T("row_sel") if sel else T("row_hover")))
        rad = 12
        path = QPainterPath()
        left = r.adjusted(-rad if not self.first else 0, 0, 0, 0)
        right = left.adjusted(0, 0, rad if not self.last else 0, 0)
        path.addRoundedRect(right, rad, rad)
        p.setClipRect(opt.rect)
        p.drawPath(path)
        p.restore()

    def paint(self, p, opt, idx):
        self.row_bg(p, opt, idx)
        text = idx.data(Qt.DisplayRole) or ""
        p.save()
        p.setPen(QColor(T("text")))
        p.drawText(QRectF(opt.rect).adjusted(10, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.restore()


class CheckDelegate(RowDelegate):
    def paint(self, p, opt, idx):
        self.row_bg(p, opt, idx)
        on = bool(idx.data(Qt.UserRole))
        r = QRectF(0, 0, 18, 18)
        r.moveCenter(QRectF(opt.rect).center())
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if on:
            p.setPen(Qt.NoPen)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(T("acc2")))
            g.setColorAt(1, QColor(T("acc")))
            p.setBrush(g)
            p.drawRoundedRect(r, 5, 5)
            pen = QPen(QColor(T("on_acc")), 2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            c = r.center()
            p.drawPolyline([QPointF(c.x() - 4.2, c.y() + 0.3), QPointF(c.x() - 1.2, c.y() + 3.2),
                            QPointF(c.x() + 4.4, c.y() - 3.2)])
        else:
            p.setPen(QPen(QColor(T("faint")), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), 5, 5)
        p.restore()


class NameDelegate(RowDelegate):
    def paint(self, p, opt, idx):
        self.row_bg(p, opt, idx)
        name, sub, ic_name = idx.data(Qt.UserRole) or ("", "", "other")
        r = QRectF(opt.rect)
        p.save()
        pm = pixmap(ic_name, T("icon"), 24)
        p.drawPixmap(int(r.left() + 6), int(r.center().y() - 12), pm)
        x = r.left() + 46
        f = QFont(opt.font)
        f.setPointSizeF(f.pointSizeF() + 0.8)
        p.setFont(f)
        p.setPen(QColor(T("strong")))
        fm = p.fontMetrics()
        p.drawText(QRectF(x, r.top() + 8, r.width() - 56, r.height() / 2 - 4), Qt.AlignLeft | Qt.AlignBottom,
                   fm.elidedText(name, Qt.ElideMiddle, int(r.width() - 60)))
        f2 = QFont(opt.font)
        f2.setPointSizeF(max(7.5, f2.pointSizeF() - 1.2))
        p.setFont(f2)
        p.setPen(QColor(T("muted")))
        p.drawText(QRectF(x, r.center().y() + 3, r.width() - 56, r.height() / 2 - 8), Qt.AlignLeft | Qt.AlignTop, sub)
        p.restore()


class StatusDelegate(RowDelegate):
    def paint(self, p, opt, idx):
        self.row_bg(p, opt, idx)
        status, frac, top, right, extra = idx.data(Qt.UserRole) or ("queued", 0.0, "", "", "")
        r = QRectF(opt.rect).adjusted(10, 0, -12, 0)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        small = QFont(opt.font)
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1.2))
        if status in ("downloading", "pausing") or (status == "paused" and frac > 0):
            bar = QRectF(r.left(), r.center().y() + 4, min(170.0, r.width()), 6)
            p.setPen(QColor(T("text") if status == "downloading" else T("muted")))
            label_txt = top if status == "downloading" else f"Paused  ·  {top}"
            p.drawText(QRectF(r.left(), r.top(), r.width(), r.height() / 2 - 2), Qt.AlignLeft | Qt.AlignBottom,
                       label_txt)
            if right:
                p.setFont(small)
                p.setPen(QColor(T("muted")))
                p.drawText(QRectF(bar.left(), r.top(), bar.width(), r.height() / 2 - 2),
                           Qt.AlignRight | Qt.AlignBottom, right)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T("track")))
            p.drawRoundedRect(bar, 3, 3)
            if frac > 0:
                fill = QRectF(bar)
                fill.setWidth(max(6.0, bar.width() * min(frac, 1.0)))
                if status == "downloading":
                    g = QLinearGradient(bar.topLeft(), bar.topRight())
                    g.setColorAt(0, QColor(T("acc2")))
                    g.setColorAt(1, QColor(T("acc")))
                    p.setBrush(g)
                else:
                    p.setBrush(QColor(T("faint")))
                p.drawRoundedRect(fill, 3, 3)
        else:
            text, color = theme.status(status)
            if status == "done":
                text, color = "Complete", T("text")
            if status == "paused":
                box = QRectF(r.left(), r.center().y() - 7, 14, 14)
                p.setPen(QPen(QColor(T("muted")), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(box.adjusted(0.75, 0.75, -0.75, -0.75), 3, 3)
                r = r.adjusted(22, 0, 0, 0)
                color = T("muted")
            p.setPen(QColor(color))
            p.drawText(r, Qt.AlignVCenter | Qt.AlignLeft, text + (f"  {extra}" if extra else ""))
        if extra and status in ("downloading", "pausing"):
            p.setFont(small)
            p.setPen(QColor(T("muted")))
            p.drawText(QRectF(r.left(), r.center().y() + 13, r.width(), 16), Qt.AlignLeft | Qt.AlignTop, extra)
        p.restore()


class DiskGauge(QWidget):
    """Half-circle gauge for the disk-space card."""

    def __init__(self):
        super().__init__()
        self.frac = 0.0
        self.setFixedHeight(96)

    def set_value(self, frac):
        self.frac = max(0.0, min(1.0, frac))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        d = min(w - 40, 2 * (h - 14))
        rect = QRectF((w - d) / 2, 10, d, d)
        pen = QPen(QColor(T("track")), 12)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 180 * 16, -180 * 16)
        g = QConicalGradient(rect.center(), 180)
        g.setColorAt(0.0, QColor(T("acc2")))
        g.setColorAt(0.25, QColor(T("acc")))
        g.setColorAt(0.5, QColor("#ef4466") if self.frac > 0.85 else QColor(T("acc")))
        g.setColorAt(1.0, QColor(T("acc2")))
        pen = QPen(QBrush(g), 12)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        if self.frac > 0:
            p.drawArc(rect, 180 * 16, int(-180 * 16 * self.frac))
        p.setPen(QColor(T("muted")))
        f = QFont(self.font())
        f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
        p.setFont(f)
        p.drawText(QRectF(rect.left() - 20, rect.center().y() + 4, 40, 18), Qt.AlignCenter, "0%")
        p.drawText(QRectF(rect.right() - 20, rect.center().y() + 4, 40, 18), Qt.AlignCenter, "100%")
        p.end()


class _Relay(QObject):
    """Carries a result from a worker thread back to the UI thread."""
    done = Signal(object)


class InfoCard(QFrame):
    """'What is this download?' — name, size, resume support, free space."""

    def __init__(self):
        super().__init__()
        self.setObjectName("InfoCard")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(14)
        self.ic = QLabel()
        self.ic.setFixedSize(40, 40)
        self.ic.setAlignment(Qt.AlignCenter)
        h.addWidget(self.ic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        self.name = QLabel()
        self.name.setObjectName("InfoName")
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.size = QLabel()
        self.size.setObjectName("InfoSize")
        top.addWidget(self.name, 1)
        top.addWidget(self.size, 0, Qt.AlignRight)
        col.addLayout(top)
        self.detail = label("", "Muted", True)
        col.addWidget(self.detail)
        self.warn = label("", "Warn", True)
        col.addWidget(self.warn)
        h.addLayout(col, 1)

    def set(self, ic, color, name, size, detail, warn=""):
        self.ic.setPixmap(pixmap(ic, color, 30))
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(name, Qt.ElideMiddle, 360))
        self.name.setToolTip(name)
        self.size.setText(size)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.warn.setText(warn)
        self.warn.setVisible(bool(warn))


class AddDialog(QDialog):
    def __init__(self, parent, mgr, data=None):
        super().__init__(parent)
        data = data or {}
        self.mgr = mgr
        self.choice = None
        self.setWindowTitle("New download")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(600)

        url_text = data.get("url", "") or (clipboard_url() if not data else "")
        self.url = QLineEdit(url_text)
        self.url.setPlaceholderText("https://…   or   magnet:?…")
        paste = QToolButton()
        paste.setObjectName("Icon")
        paste.setIcon(icon("link", T("icon"), 18))
        paste.setIconSize(QSize(18, 18))
        paste.setToolTip("Paste from clipboard")
        paste.setCursor(Qt.PointingHandCursor)
        paste.clicked.connect(lambda: self.url.setText(QApplication.clipboard().text().strip()))
        urow = QHBoxLayout()
        urow.setSpacing(8)
        urow.addWidget(self.url)
        urow.addWidget(paste)
        pick = QToolButton()
        pick.setObjectName("Icon")
        pick.setText(" .torrent file…")
        pick.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        pick.setIcon(icon("magnet", T("teal"), 18))
        pick.setIconSize(QSize(18, 18))
        pick.setToolTip("Open a .torrent file")
        pick.setCursor(Qt.PointingHandCursor)
        pick.clicked.connect(self._pick_torrent)
        urow.addWidget(pick)

        self.kind = QComboBox()
        self.kind.addItems(["File", "Video (YouTube, Facebook, Instagram, TikTok…)",
                            "Torrent (magnet link or .torrent file)"])
        self.quality = QComboBox()
        for key, text in QUALITIES:
            self.quality.addItem(text, key)
        self.name = QLineEdit(data.get("filename", ""))
        self.name.setPlaceholderText("Optional — taken from the server")
        self.folder = QLineEdit(mgr.settings["save_dir"])
        browse = QToolButton()
        browse.setObjectName("Icon")
        browse.setIcon(icon("folder", T("icon"), 18))
        browse.setIconSize(QSize(18, 18))
        browse.setToolTip("Choose folder")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        frow = QHBoxLayout()
        frow.setSpacing(8)
        frow.addWidget(self.folder)
        frow.addWidget(browse)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow(label("URL", "Muted"), urow)
        self.card = InfoCard()
        form.addRow(self.card)
        form.addRow(label("Type", "Muted"), self.kind)
        self.q_label = label("Quality", "Muted")
        form.addRow(self.q_label, self.quality)
        self.n_label = label("File name", "Muted")
        form.addRow(self.n_label, self.name)
        form.addRow(label("Save to", "Muted"), frow)
        self._hint_size = data.get("size") or 0
        self.t_note = None
        if not torrent.AVAILABLE:
            self.t_note = label("Torrent support isn't installed in this build. Rebuild with Python 3.13 "
                                "(see the guide).", "Warn", wrap=True)
            form.addRow(self.t_note)
        self.ff_note = None
        if not ffmpeg_path():
            self.ff_note = label("ffmpeg not found — videos will download as a single file "
                                 "(usually up to 720p).", "Warn", wrap=True)
            form.addRow(self.ff_note)

        sch = mgr.settings
        self.sched = QCheckBox(f"Add to the schedule (starts at {sch.get('schedule_start', '02:00')})")
        self.sched.setVisible(bool(sch.get("schedule_on")))
        form.addRow(self.sched)
        now = primary(QPushButton("Download now"))
        now.setDefault(True)
        later = QPushButton("Download later")
        cancel = QPushButton("Cancel")
        now.clicked.connect(lambda: self._finish("now"))
        later.clicked.connect(lambda: self._finish("later"))
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(later)
        btns.addWidget(now)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)
        lay.addWidget(label("New download", "Title"))
        lay.addWidget(label("Paste a link to a file, a video page, or a magnet link.", "Muted"))
        lay.addSpacing(14)
        lay.addLayout(form)
        lay.addSpacing(18)
        lay.addLayout(btns)

        self.headers = {}
        if data.get("referrer"):
            self.headers["Referer"] = data["referrer"]
        if data.get("cookies"):
            self.headers["Cookie"] = data["cookies"]
        if data.get("userAgent"):
            self.headers["User-Agent"] = data["userAgent"]
        self.referrer = data.get("referrer", "")

        self.kind.setCurrentIndex(self._guess_kind(self.url.text(), data.get("type")))
        self.kind.currentIndexChanged.connect(self._sync)
        self.url.textChanged.connect(self._auto_kind)

        # look the download up (size etc.) a moment after the link stops changing
        self._info = None
        self._gen = 0
        self._relay = _Relay()
        self._relay.done.connect(self._probe_done)
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._start_probe)
        self.url.textChanged.connect(lambda *_: self._probe_timer.start(600))
        self.kind.currentIndexChanged.connect(lambda *_: self._probe_timer.start(150))
        self.folder.textChanged.connect(lambda *_: self._render_info())
        self.quality.currentIndexChanged.connect(lambda *_: self._render_info())
        self._sync()
        self._start_probe()

    # ---- looking the download up ----
    def _start_probe(self):
        self._gen += 1
        gen = self._gen
        self._info = None
        url = self.url.text().strip()
        kind = self.kind.currentIndex()
        valid = url.lower().startswith(("http://", "https://", "magnet:")) or (
            url.lower().endswith(".torrent") and os.path.isfile(url))
        if not valid:
            self.card.hide()
            self.adjustSize()
            return
        self._render_info(checking=True)
        headers, referrer = dict(self.headers), self.referrer
        has_ff = bool(ffmpeg_path())

        def work():
            try:
                if kind == 2:
                    res = probe.probe_torrent(url, headers)
                elif kind == 1:
                    res = probe.probe_video(url, referrer, has_ff)
                else:
                    res = probe.probe_file(url, headers)
            except Exception as e:
                res = {"error": str(e).split("\n")[0][:200]}
            self._relay.done.emit((gen, res))
        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, payload):
        gen, res = payload
        if gen != self._gen:
            return              # the link changed meanwhile
        self._info = res
        if res.get("kind") == "file" and res.get("name") and not self.name.text().strip():
            self.name.setPlaceholderText(res["name"])
        if res.get("kind") == "video":
            sizes = res.get("sizes") or {}
            for i in range(self.quality.count()):
                key = self.quality.itemData(i)
                base = dict(QUALITIES)[key]
                sz = sizes.get(key)
                self.quality.setItemText(i, f"{base}   —   {'~' + human_size(sz) if sz else 'size unknown'}")
        self._render_info()

    def _render_info(self, checking=False):
        if self._gen == 0:
            return
        kind = self.kind.currentIndex()
        url = self.url.text().strip()
        info = self._info
        folder = self.folder.text().strip() or self.mgr.settings["save_dir"]
        free = probe.free_space(folder)
        free_txt = f"{human_size(free)} free on {probe.drive_name(folder)}" if free is not None else ""
        guess = os.path.basename(urlparse(url).path) if url.lower().startswith("http") else ""
        if kind == 2:
            ic, color = "magnet", T("teal")
        elif kind == 1:
            ic, color = CATEGORY_ICON["Video"]
        else:
            ic, color = CATEGORY_ICON.get(category_of(guess or "x"), CATEGORY_ICON["Other"])
        self.card.show()
        if checking or info is None:
            hint = f"{human_size(self._hint_size)}" if self._hint_size else ""
            self.card.set(ic, color, guess or url, hint, "Checking size…  " + free_txt)
            self.adjustSize()
            return
        if "error" in info:
            self.card.set(ic, color, guess or url, "", free_txt,
                          f"Couldn't check this link: {info['error']}")
            self.adjustSize()
            return
        size = None
        details = []
        warn = ""
        name = info.get("name") or guess or url
        if info["kind"] == "file":
            size = info.get("size") or self._hint_size or None
            ic, color = CATEGORY_ICON.get(category_of(name), CATEGORY_ICON["Other"])
            if not size:
                details.append("The server didn't say how big it is")
            details.append("Pause & resume: yes" if info.get("resumable") else
                           "Pause & resume: no — if paused it starts over")
            if info.get("page"):
                warn = "This link opens a web page, not a file. For a video on it, choose Type → Video."
        elif info["kind"] == "video":
            size = (info.get("sizes") or {}).get(self.quality.currentData())
            if info.get("duration"):
                details.append(f"Length {human_time(info['duration'])}")
            if info.get("site"):
                details.append(info["site"])
            if size:
                details.append("size is an estimate")
        else:
            if info.get("magnet"):
                details.append("The size appears once the torrent connects — you'll pick the files then")
            elif info.get("files"):
                details.append(f"{info['files']} file{'s' if info['files'] != 1 else ''}")
        if info["kind"] == "torrent":
            cat = "Torrents"
        elif info["kind"] == "video":
            cat = "Music" if self.quality.currentData() == "audio" else "Video"
        else:
            cat = category_of(self.name.text().strip() or name)
        dest = core.resolve_folder(folder, cat)
        parts = os.path.normpath(dest).split(os.sep)
        details.append("Saves to " + ("…" + os.sep + os.sep.join(parts[-2:]) if len(parts) > 2 else dest))
        if free_txt:
            details.append(free_txt)
        if size and free is not None and size > free:
            warn = (f"Not enough space on {probe.drive_name(folder)} — it needs {human_size(size)}, "
                    f"only {human_size(free)} is free. Choose another folder below.")
        size_txt = ("~" if info["kind"] == "video" and size else "") + (human_size(size) if size else "Unknown size")
        self.card.set(ic, color, name, size_txt, "  ·  ".join(details), warn)
        self.adjustSize()

    @staticmethod
    def _guess_kind(text, hint=None):
        if hint == "torrent" or is_torrent_source(text):
            return 2
        if hint == "video" or VIDEO_SITES.search(text or ""):
            return 1
        return 0

    def _auto_kind(self, text):
        k = self._guess_kind(text)
        if k:
            self.kind.setCurrentIndex(k)

    def _pick_torrent(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open torrent file", "", "Torrent files (*.torrent)")
        if f:
            self.url.setText(f)
            self.kind.setCurrentIndex(2)

    def _sync(self):
        k = self.kind.currentIndex()
        for w in (self.q_label, self.quality):
            w.setVisible(k == 1)
        for w in (self.n_label, self.name):
            w.setVisible(k == 0)
        if self.ff_note:
            self.ff_note.setVisible(k == 1)
        if self.t_note:
            self.t_note.setVisible(k == 2)
        self.adjustSize()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _finish(self, choice):
        text = self.url.text().strip()
        ok = text.lower().startswith(("http://", "https://"))
        if self.kind.currentIndex() == 2:
            ok = ok or text.lower().startswith("magnet:") or (
                text.lower().endswith(".torrent") and os.path.isfile(text))
        if not ok:
            QMessageBox.warning(self, APP_NAME, "Please enter a valid link (http://, https:// or magnet:)")
            return
        self.choice = choice
        if self.sched.isChecked():
            self.choice = "later"     # it waits for the schedule
        self.accept()

    def make_item(self):
        url = self.url.text().strip()
        folder = self.folder.text().strip() or self.mgr.settings["save_dir"]
        if self.kind.currentIndex() == 2:
            return self.mgr.new_torrent(url, folder, self.headers)
        if self.kind.currentIndex() == 1:
            return self.mgr.new_video(url, self.quality.currentData(), folder, self.referrer)
        return self.mgr.new_file(url, self.name.text().strip(), self.headers, folder)


class FilesDialog(QDialog):
    """Pick which files of a torrent to download."""

    def __init__(self, parent, item, files, priorities=None, new=True):
        super().__init__(parent)
        self.files = files
        self.n_total = max((i for i, _, _ in files), default=-1) + 1
        self.result_priorities = None
        self.setWindowTitle("Choose files")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(760, 580)

        title = label(item.name or "Torrent", "Title")
        title.setWordWrap(True)
        total = sum(sz for _, _, sz in files)
        sub = label(f"{len(files)} files · {human_size(total)}  —  untick what you don't want.", "Muted")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter files…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        b_all = QPushButton("Select all")
        b_none = QPushButton("Select none")
        b_vid = QPushButton("Videos only")
        # with a filter typed, these act only on the files you can see
        b_all.clicked.connect(lambda: self._set_all(True, bool(self.search.text().strip())))
        b_none.clicked.connect(lambda: self._set_all(False, bool(self.search.text().strip())))
        b_vid.clicked.connect(self._videos_only)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.search, 1)
        top.addWidget(b_all)
        top.addWidget(b_none)
        top.addWidget(b_vid)

        tree = QTreeWidget()
        tree.setObjectName("Files")
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Name", "Size"])
        tree.setIconSize(QSize(18, 18))
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        hh = tree.header()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        tree.setColumnWidth(1, 110)
        self.tree = tree
        self._build(files, priorities)
        tree.itemChanged.connect(lambda *_: self._update_footer())

        self.footer = label("", "Muted")
        cancel = QPushButton("Remove torrent" if new else "Cancel")
        cancel.clicked.connect(self.reject)
        self.ok = primary(QPushButton("Download selected" if new else "Apply"))
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._accept)
        btns = QHBoxLayout()
        btns.addWidget(self.footer, 1)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(12)
        lay.addLayout(top)
        lay.addSpacing(6)
        lay.addWidget(tree, 1)
        lay.addSpacing(10)
        lay.addLayout(btns)
        self._update_footer()

    def _build(self, files, priorities):
        parts_list = [p.split("/") for _, p, _ in files]
        # drop the shared top folder (the torrent's own name) to keep the tree shallow
        strip = 1 if parts_list and all(len(p) > 1 for p in parts_list) and \
            len({p[0] for p in parts_list}) == 1 else 0
        folders = {}
        self.tree.blockSignals(True)
        for (idx, path, size), parts in zip(files, parts_list):
            parts = parts[strip:]
            parent = None
            key = ()
            for folder in parts[:-1]:
                key += (folder,)
                node = folders.get(key)
                if node is None:
                    node = QTreeWidgetItem([folder, ""])
                    node.setIcon(0, icon("folder", T("folder"), 18))
                    node.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    node.setData(1, Qt.UserRole, 0)
                    (parent.addChild(node) if parent else self.tree.addTopLevelItem(node))
                    node.setCheckState(0, Qt.Checked)
                    folders[key] = node
                parent = node
            leaf = QTreeWidgetItem([parts[-1], human_size(size)])
            ic_name, ic_color = CATEGORY_ICON.get(category_of(parts[-1]), CATEGORY_ICON["Other"])
            leaf.setIcon(0, icon(ic_name, ic_color, 18))
            leaf.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            leaf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            leaf.setData(0, Qt.UserRole, idx)
            leaf.setData(1, Qt.UserRole, size)
            (parent.addChild(leaf) if parent else self.tree.addTopLevelItem(leaf))
            on = True if not priorities or idx >= len(priorities) else priorities[idx] > 0
            leaf.setCheckState(0, Qt.Checked if on else Qt.Unchecked)   # after adding: updates folder ticks
            p = parent
            while p is not None:   # folder sizes
                p.setData(1, Qt.UserRole, p.data(1, Qt.UserRole) + size)
                p.setText(1, human_size(p.data(1, Qt.UserRole)))
                p.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                p = p.parent()
        self.tree.blockSignals(False)
        if len(files) <= 300:
            self.tree.expandAll()
        else:
            self.tree.expandToDepth(0)
        self.tree.sortItems(0, Qt.AscendingOrder)

    def _leaves(self):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            node = it.value()
            if node.childCount() == 0:
                yield node
            it += 1

    def _set_all(self, on, only_visible=False):
        state = Qt.Checked if on else Qt.Unchecked
        for leaf in self._leaves():
            if not only_visible or not leaf.isHidden():
                leaf.setCheckState(0, state)

    def _videos_only(self):
        for leaf in self._leaves():
            is_video = category_of(leaf.text(0)) == "Video" and "sample" not in leaf.text(0).lower()
            leaf.setCheckState(0, Qt.Checked if is_video else Qt.Unchecked)

    def _filter(self, text):
        text = text.strip().lower()

        def walk(node):
            if node.childCount() == 0:
                show = not text or text in node.text(0).lower()
            else:
                show = False
                for i in range(node.childCount()):
                    show = walk(node.child(i)) or show
            node.setHidden(not show)
            return show

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        if text:
            self.tree.expandAll()

    def _update_footer(self):
        n = size = 0
        for leaf in self._leaves():
            if leaf.checkState(0) == Qt.Checked:
                n += 1
                size += leaf.data(1, Qt.UserRole) or 0
        self.footer.setText(f"Selected: {n} of {len(self.files)} files · {human_size(size) if size else '0 B'}")
        self.ok.setEnabled(n > 0)

    def _accept(self):
        prios = [0] * self.n_total
        for leaf in self._leaves():
            if leaf.checkState(0) == Qt.Checked:
                prios[leaf.data(0, Qt.UserRole)] = 4
        self.result_priorities = prios
        self.accept()


PRESETS = [0, 128, 256, 512, 1024, 2048, 5120, 10240]   # KB/s


class RateField(QWidget):
    """Number + KB/s|MB/s picker. 0 = no limit."""

    def __init__(self, kb=0):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.num = QSpinBox()
        self.num.setRange(0, 999999)
        self.num.setSpecialValueText("No limit")
        self.num.setMinimumWidth(130)
        self.unit = QComboBox()
        self.unit.addItems(["KB/s", "MB/s"])
        h.addWidget(self.num)
        h.addWidget(self.unit)
        h.addStretch()
        self.set_kb(kb)

    def set_kb(self, kb):
        kb = int(kb or 0)
        if kb and kb % 1024 == 0:
            self.unit.setCurrentIndex(1)
            self.num.setValue(kb // 1024)
        else:
            self.unit.setCurrentIndex(0)
            self.num.setValue(kb)

    def kb(self):
        return self.num.value() * (1024 if self.unit.currentIndex() == 1 else 1)


class RateDialog(QDialog):
    """Ask for a single speed (used by "Custom…")."""

    def __init__(self, parent, title, kb):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.field = RateField(kb or 1024)
        ok = primary(QPushButton("Set limit"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.addWidget(label(title, "Title"))
        lay.addWidget(label("Set 0 for no limit.", "Muted"))
        lay.addSpacing(12)
        lay.addWidget(self.field)
        lay.addSpacing(16)
        lay.addLayout(btns)

    @staticmethod
    def ask(parent, title, kb):
        d = RateDialog(parent, title, kb)
        return d.field.kb() if d.exec() == QDialog.Accepted else None


class SpeedDialog(QDialog):
    """The global speed limits."""

    def __init__(self, parent, mgr):
        super().__init__(parent)
        self.mgr = mgr
        s = mgr.settings
        self.setWindowTitle("Speed limits")
        self.setMinimumWidth(520)
        self.on = QCheckBox("Limit speed  (Ctrl+L turns this on and off)")
        self.on.setChecked(s.get("limit_on", False))
        self.down = RateField(s.get("limit_down", 0))
        self.t_down = RateField(s.get("torrent_down", 0))
        self.t_up = RateField(s.get("torrent_up", 0))
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow(label("Downloads (all together)", "Muted"), self.down)
        form.addRow(label("Torrent download", "Muted"), self.t_down)
        form.addRow(label("Torrent upload", "Muted"), self.t_up)
        self.form_box = QWidget()
        self.form_box.setLayout(form)
        self.on.toggled.connect(self.form_box.setEnabled)
        self.form_box.setEnabled(self.on.isChecked())

        ok = primary(QPushButton("Save"))
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)
        lay.addWidget(label("Speed limits", "Title"))
        lay.addWidget(label("Keep some internet for everyone else. A single download can also get its own "
                            "limit from right-click → Limit speed.", "Muted", wrap=True))
        lay.addSpacing(14)
        lay.addWidget(self.on)
        lay.addSpacing(8)
        lay.addWidget(self.form_box)
        lay.addSpacing(18)
        lay.addLayout(btns)

    def _save(self):
        s = self.mgr.settings
        s["limit_on"] = self.on.isChecked()
        s["limit_down"] = self.down.kb()
        s["torrent_down"] = self.t_down.kb()
        s["torrent_up"] = self.t_up.kb()
        self.mgr.apply_limits()
        self.mgr.save()
        self.accept()


class CountdownDialog(QDialog):
    """'Shutting down in 60 s' with Cancel / Do it now."""
    WORDS = {"sleep": ("Going to sleep", "sleep"), "shutdown": ("Shutting down", "shut down"),
             "quit": ("Closing EDENLOAD", "close")}

    def __init__(self, parent, action, why, seconds=60):
        super().__init__(parent)
        self.left = seconds
        self.total = seconds
        title, verb = self.WORDS.get(action, ("Finishing", "continue"))
        self.title = title
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(420)
        ic = QLabel()
        ic.setPixmap(pixmap("power", T("acc"), 40))
        self.big = label("", "Big")
        self.bar = QProgressBar()
        self.bar.setRange(0, seconds)
        self.bar.setValue(seconds)
        cancel = primary(QPushButton("Cancel"))
        cancel.setDefault(True)
        cancel.clicked.connect(self.reject)
        now = QPushButton(f"{verb.capitalize()} now")
        now.clicked.connect(self.accept)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(now)
        btns.addWidget(cancel)
        top = QHBoxLayout()
        top.addWidget(ic)
        top.addSpacing(10)
        col = QVBoxLayout()
        col.addWidget(label(why, "Muted"))
        col.addWidget(self.big)
        top.addLayout(col, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.addLayout(top)
        lay.addSpacing(12)
        lay.addWidget(self.bar)
        lay.addSpacing(16)
        lay.addLayout(btns)
        self._tick()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _tick(self):
        self.big.setText(f"{self.title} in {self.left} s")
        self.bar.setValue(self.left)
        if self.left <= 0:
            self.timer.stop()
            self.accept()
        self.left -= 1


def theme_swatch(key):
    """Small round icon in the theme's accent color (for the theme picker)."""
    if key == "system":
        return icon("palette", T("icon"), 18)
    b = theme.THEMES[key][1]
    pm = QPixmap(36, 36)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(theme.mix(b["bg"], b["text"], 0.25)))
    p.setBrush(QColor(b["bg"]))
    p.drawEllipse(2, 2, 32, 32)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(b["acc"]))
    p.drawEllipse(11, 11, 14, 14)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def folder_row(edit, parent, title):
    browse = QToolButton()
    browse.setObjectName("Icon")
    browse.setIcon(icon("folder", T("icon"), 18))
    browse.setIconSize(QSize(18, 18))
    browse.setToolTip("Choose folder")
    browse.setCursor(Qt.PointingHandCursor)

    def pick():
        d = QFileDialog.getExistingDirectory(parent, title, edit.text() or os.path.expanduser("~"))
        if d:
            edit.setText(os.path.normpath(d))
    browse.clicked.connect(pick)
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(edit, 1)
    row.addWidget(browse)
    return row


def page(*rows):
    """A settings tab: a scrollable column of widgets/layouts ("" = spacer)."""
    inner = QWidget()
    v = QVBoxLayout(inner)
    v.setContentsMargins(4, 18, 12, 8)
    v.setSpacing(10)
    for r in rows:
        if r == "":
            v.addSpacing(6)
        elif isinstance(r, QWidget):
            v.addWidget(r)
        else:
            v.addLayout(r)
    v.addStretch()
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setWidget(inner)
    return sc


def form(*pairs):
    f = QFormLayout()
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(12)
    f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for a, b in pairs:
        f.addRow(label(a, "Muted"), b)
    return f


def hbox(*ws, stretch=True):
    h = QHBoxLayout()
    h.setSpacing(8)
    for w in ws:
        h.addWidget(w) if isinstance(w, QWidget) else h.addLayout(w)
    if stretch:
        h.addStretch()
    return h


CATEGORY_FOLDERS = [("Video", "Video"), ("Music", "Music"), ("Programs", "Programs"), ("Documents", "Documents"),
                    ("Compressed", "Archives"), ("Images", "Images"), ("Torrents", "Torrents"), ("Other", "Other")]


class CleanerDialog(QDialog):
    """Find leftovers of cancelled/removed downloads (.part etc.) and delete them."""
    LEFTOVER = (".part", ".ytdl", ".part-frag", ".temp")

    def __init__(self, parent, mgr):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("Disk Cleaner")
        self.setMinimumSize(620, 480)
        self.found = self._scan()
        total = sum(sz for _, sz in self.found)
        lst = QTreeWidget()
        lst.setObjectName("Files")
        lst.setHeaderLabels(["File", "Size"])
        lst.setRootIsDecorated(False)
        lst.header().setSectionResizeMode(0, QHeaderView.Stretch)
        lst.header().setSectionResizeMode(1, QHeaderView.Fixed)
        lst.setColumnWidth(1, 100)
        for path, sz in self.found:
            it = QTreeWidgetItem([path, human_size(sz)])
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            lst.addTopLevelItem(it)
        done = [i for i in mgr.items if i.status == "done"]
        self.clear_done = QCheckBox(f"Also remove {len(done)} finished download{'s' if len(done) != 1 else ''} "
                                    "from the list (the files stay on your disk)")
        self.clear_done.setVisible(bool(done))
        ok = QPushButton(f"Delete {len(self.found)} leftover{'s' if len(self.found) != 1 else ''}"
                         f" ({human_size(total) if total else '0 B'})" if self.found else "Clean the list")
        ok.setObjectName("Gradient")
        ok.setEnabled(bool(self.found) or bool(done))
        ok.clicked.connect(self._clean)
        cancel = QPushButton("Close")
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.addWidget(label("Disk Cleaner", "Title"))
        lay.addWidget(label("Leftover pieces of downloads that were cancelled or removed from the list. "
                            "Downloads still in your list are never touched.", "Muted", True))
        lay.addSpacing(8)
        if self.found:
            lay.addWidget(lst, 1)
        else:
            lay.addWidget(label("Nothing to clean — no leftovers found. ✓", "Title"))
            lay.addStretch()
        lay.addWidget(self.clear_done)
        lay.addSpacing(8)
        lay.addLayout(btns)

    def _scan(self):
        keep = set()
        for it in self.mgr.items:
            if it.path:
                keep.add(os.path.normcase(it.path + ".part"))
                keep.add(os.path.normcase(it.path))
        roots = {self.mgr.settings["save_dir"]} | {v for v in core.CATEGORY_DIRS.values() if v}
        roots |= {os.path.join(self.mgr.settings["save_dir"], n) for n in core.DEFAULT_FOLDERS}
        # downloads not finished yet (videos write "<title>.f137.mp4.part" etc. before they know their path)
        unfinished = [os.path.splitext(i.name or "")[0].lower() for i in self.mgr.items
                      if i.status != "done" and i.name]
        found, seen = [], set()
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                names = os.listdir(root)
            except OSError:
                continue
            for n in names:
                p = os.path.join(root, n)
                key = os.path.normcase(p)
                if key in seen or key in keep or not os.path.isfile(p):
                    continue
                low = n.lower()
                if any(u and low.startswith(u) for u in unfinished):
                    continue
                if low.endswith(self.LEFTOVER) or ".part-frag" in low:
                    seen.add(key)
                    try:
                        found.append((p, os.path.getsize(p)))
                    except OSError:
                        pass
        return sorted(found)

    def _clean(self):
        n = 0
        for p, _ in self.found:
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
        if self.clear_done.isChecked():
            for it in [i for i in self.mgr.items if i.status == "done"]:
                self.mgr.remove(it, delete_file=False)
        self.mgr.save()
        QMessageBox.information(self, "Disk Cleaner", f"Done — deleted {n} leftover file{'s' if n != 1 else ''}.")
        self.accept()


class SettingsDialog(QDialog):
    TABS = ["General", "Downloads", "Folders", "Schedule", "Torrents", "Updates"]

    def __init__(self, parent, mgr, tab=None):
        super().__init__(parent)
        self.mgr = mgr
        self.win = parent
        s = mgr.settings
        self._orig_theme = s.get("theme", "aurora")
        self.setWindowTitle("Settings")
        self.resize(660, 600)

        # ---------- General
        self.theme = QComboBox()
        self.theme.setIconSize(QSize(18, 18))
        for key, text in theme.CHOICES:
            self.theme.addItem(theme_swatch(key), text, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self._orig_theme)))
        self.theme.currentIndexChanged.connect(self._preview_theme)
        self.startup = QCheckBox("Start with Windows (runs next to the clock)")
        self.startup.setChecked(s.get("startup", False))
        self.startup.setEnabled(sys.platform == "win32")
        self.clip = QCheckBox("Watch the clipboard — offer to download copied links")
        self.clip.setChecked(s.get("clipboard", False))
        self.clip_video = QCheckBox("Also for video pages (YouTube, Facebook, TikTok…)")
        self.clip_video.setChecked(s.get("clipboard_video", False))
        self.clip_video.setEnabled(self.clip.isChecked())
        self.clip.toggled.connect(self.clip_video.setEnabled)
        ind = QHBoxLayout()
        ind.addSpacing(26)
        ind.addWidget(self.clip_video)
        guide_btn = QPushButton("  Connect browser…")
        guide_btn.setIcon(icon("link", T("icon"), 16))
        guide_btn.clicked.connect(open_browser_guide)
        general = page(
            form(("Theme", self.theme)),
            label("System follows Windows: light during the day if Windows is light, dark otherwise.", "Muted", True),
            "", label("STARTUP", "Section"), self.startup,
            "", label("CLIPBOARD", "Section"), self.clip, ind,
            label("Copy a link to a file (.exe, .zip, .mp4, .pdf…) or a magnet link anywhere, "
                  "and EDENLOAD asks if you want to download it.", "Muted", True),
            "", label("BROWSER", "Section"), hbox(guide_btn))

        # ---------- Downloads
        self.folder = QLineEdit(s["save_dir"])
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 10)
        self.parallel.setValue(s["max_parallel"])
        self.segments = QSpinBox()
        self.segments.setRange(1, 32)
        self.segments.setValue(s["segments"])
        self.categorize = QCheckBox("Sort downloads into Music, Videos, Programs, Documents, Torrents and Others")
        self.categorize.setChecked(s["categorize"])
        speed_btn = QPushButton("  Speed limits…")
        speed_btn.setIcon(icon("gauge", T("icon"), 16))
        speed_btn.clicked.connect(lambda: SpeedDialog(self, self.mgr).exec())
        downloads = page(
            form(("Download folder", folder_row(self.folder, self, "Choose download folder")),
                 ("Simultaneous downloads", hbox(self.parallel)),
                 ("Connections per file", hbox(self.segments))),
            self.categorize,
            "", label("SPEED", "Section"), hbox(speed_btn))

        # ---------- Folders
        dirs = s.get("category_dirs") or {}
        self.cat_edits = {}
        rows = []
        for key, text in CATEGORY_FOLDERS:
            e = QLineEdit(dirs.get(key, ""))
            e.setClearButtonEnabled(True)
            e.setPlaceholderText("Default")
            self.cat_edits[key] = e
            ic_name, ic_color = CATEGORY_ICON[key]
            lab = QLabel()
            lab.setPixmap(pixmap(ic_name, ic_color, 18))
            rows.append(hbox(lab, label(text)))
            rows.append(folder_row(e, self, f"Folder for {text}"))
        self.folder_hint = label("", "Muted", True)
        self.folder.textChanged.connect(self._folder_hint)
        self.categorize.toggled.connect(self._folder_hint)
        self._folder_hint()
        folders = page(label("Choose where each kind of download is saved. Leave empty to use the default.",
                             "Muted", True), self.folder_hint, "", *rows)

        # ---------- Schedule
        self.sch_on = QCheckBox("Turn on the scheduler")
        self.sch_on.setChecked(s.get("schedule_on", False))
        self.sch_start = QTimeEdit(QTime.fromString(s.get("schedule_start", "02:00"), "HH:mm"))
        self.sch_start.setDisplayFormat("hh:mm AP")
        self.sch_stop_on = QCheckBox("Stop at")
        self.sch_stop_on.setChecked(s.get("schedule_stop_on", True))
        self.sch_stop = QTimeEdit(QTime.fromString(s.get("schedule_stop", "08:00"), "HH:mm"))
        self.sch_stop.setDisplayFormat("hh:mm AP")
        self.sch_stop.setEnabled(self.sch_stop_on.isChecked())
        self.sch_stop_on.toggled.connect(self.sch_stop.setEnabled)
        self.day_btns = []
        days_row = QHBoxLayout()
        days_row.setSpacing(6)
        on_days = s.get("schedule_days", list(range(7)))
        for i, d in enumerate(DAYS):
            b = QPushButton(d)
            b.setCheckable(True)
            b.setChecked(i in on_days)
            b.setFixedSize(52, 34)
            b.setStyleSheet("padding:0;")
            self.day_btns.append(b)
            days_row.addWidget(b)
        days_row.addStretch()
        self.sch_action = QComboBox()
        for key, text in ACTIONS:
            self.sch_action.addItem(text, key)
        self.sch_action.setCurrentIndex(max(0, self.sch_action.findData(s.get("schedule_action", "none"))))
        self.sch_box = QWidget()
        sb = QVBoxLayout(self.sch_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(10)
        sb.addLayout(form(("Start at", hbox(self.sch_start)),
                          ("", hbox(self.sch_stop_on, self.sch_stop)),
                          ("Days", days_row),
                          ("When they finish", hbox(self.sch_action))))
        self.sch_box.setEnabled(self.sch_on.isChecked())
        self.sch_on.toggled.connect(self.sch_box.setEnabled)
        schedule = page(
            label("Download at night or whenever the internet is free. Downloads you add with "
                  "“Add to the schedule” (or right-click → Add to schedule) start at the start time "
                  "and pause at the stop time.", "Muted", True),
            "", self.sch_on, self.sch_box,
            "", label("TIP", "Section"),
            label("For a one-time action — like shutting down after the downloads that are running now — "
                  "use the “When done” button at the top of the window.", "Muted", True))

        # ---------- Torrents
        self.ask_files = QCheckBox("Let me choose which files to download")
        self.ask_files.setChecked(s.get("torrent_ask_files", True))
        self.seed = QCheckBox("Keep seeding torrents after they finish")
        self.seed.setChecked(s.get("seed_after", False))
        self.assoc = QCheckBox("Open magnet links and .torrent files with EDENLOAD")
        self.assoc.setChecked(s.get("torrent_assoc", False))
        self.assoc.setEnabled(sys.platform == "win32")
        torrents = page(self.ask_files, self.seed, self.assoc)

        # ---------- Updates
        self.auto_up = QCheckBox("Check for updates automatically")
        self.auto_up.setChecked(s.get("auto_update", True))
        check = QPushButton("  Check now")
        check.setIcon(icon("update", T("icon"), 16))
        check.clicked.connect(self._check_now)
        self.up_status = label(getattr(parent, "update_status", "") or "", "Muted", True)
        updates = page(form(("Installed version", label(features.VERSION))), self.auto_up,
                       hbox(check), self.up_status,
                       label("When a new version is out, a bar appears at the top of EDENLOAD with an "
                             "“Update now” button. Your downloads and settings are kept.", "Muted", True))

        self.tabs = QTabWidget()
        for w, name in zip((general, downloads, folders, schedule, torrents, updates), self.TABS):
            self.tabs.addTab(w, name)
        if tab in self.TABS:
            self.tabs.setCurrentIndex(self.TABS.index(tab))

        ok = primary(QPushButton("Save"))
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)
        lay.addWidget(label("Settings", "Title"))
        lay.addWidget(self.tabs, 1)
        lay.addSpacing(8)
        lay.addLayout(btns)

    def _folder_hint(self, *_):
        base = self.folder.text().strip() or self.mgr.settings["save_dir"]
        sort = self.categorize.isChecked()
        for key, e in self.cat_edits.items():
            e.setPlaceholderText("Default: " + (os.path.join(base, core.CATEGORY_FOLDER.get(key, "Others"))
                                                if sort else base))
        self.folder_hint.setText("These apply to the default download folder. If you pick another folder "
                                 "when adding a download, the file goes straight into that folder.")

    def _preview_theme(self, *_):
        if hasattr(self.win, "apply_theme"):
            self.win.apply_theme(self.theme.currentData())

    def _check_now(self):
        self.up_status.setText("Checking…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            info = features.check_latest()
            if features.is_newer(info["version"]):
                self.up_status.setText(f"Version {info['version']} is available — use “Update now” "
                                       "in the bar at the top of EDENLOAD.")
                self.win._update_result = ("ok", info, True)
            else:
                self.up_status.setText(f"You have the latest version ({features.VERSION}).")
        except Exception as e:
            self.up_status.setText(f"Couldn't check for updates: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        self.mgr.settings["last_update_check"] = time.time()

    def reject(self):
        if self.theme.currentData() != self._orig_theme and hasattr(self.win, "apply_theme"):
            self.win.apply_theme(self._orig_theme)       # undo the live preview
        super().reject()

    def _save(self):
        s = self.mgr.settings
        s["theme"] = self.theme.currentData()
        s["clipboard"] = self.clip.isChecked()
        s["clipboard_video"] = self.clip_video.isChecked()
        s["save_dir"] = self.folder.text().strip() or s["save_dir"]
        s["max_parallel"] = self.parallel.value()
        s["segments"] = self.segments.value()
        s["categorize"] = self.categorize.isChecked()
        s["category_dirs"] = {k: e.text().strip() for k, e in self.cat_edits.items() if e.text().strip()}
        s["schedule_on"] = self.sch_on.isChecked()
        s["schedule_start"] = self.sch_start.time().toString("HH:mm")
        s["schedule_stop_on"] = self.sch_stop_on.isChecked()
        s["schedule_stop"] = self.sch_stop.time().toString("HH:mm")
        s["schedule_days"] = [i for i, b in enumerate(self.day_btns) if b.isChecked()]
        s["schedule_action"] = self.sch_action.currentData()
        s["auto_update"] = self.auto_up.isChecked()
        s["startup"] = self.startup.isChecked()
        s["seed_after"] = self.seed.isChecked()
        s["torrent_ask_files"] = self.ask_files.isChecked()
        assoc_changed = self.assoc.isChecked() != s.get("torrent_assoc", False)
        s["torrent_assoc"] = self.assoc.isChecked()
        try:
            set_startup(s["startup"])
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Couldn't update the Windows startup setting:\n{e}")
        if assoc_changed:
            try:
                set_torrent_assoc(s["torrent_assoc"])
            except Exception as e:
                QMessageBox.warning(self, APP_NAME, f"Couldn't register magnet / .torrent handling:\n{e}")
        self.mgr.apply_folders()
        self.mgr.ensure_folders()
        if s["schedule_on"] and hasattr(self.win, "scheduler"):
            self.win.scheduler._was_inside = False       # re-evaluate the window with the new times
        self.mgr.save()
        self.accept()


# ---------------------------------------------------------------- main window
COLS = ["", "Name", "Size", "Status", "Time Left", "Added"]
SORT_KEYS = {1: "name", 2: "size", 3: "status", 4: "eta", 5: "added"}

# sidebar: (key, label, icon, children)
NAV = [
    ("all", "All Downloads", "stack", [
        ("Music", "Music", "music"), ("Compressed", "Archives", "compressed"), ("Video", "Videos", "video"),
        ("Programs", "Programs", "programs"), ("Documents", "Documents", "documents"),
        ("Images", "Images", "images"), ("Torrents", "Torrents", "magnet"), ("Other", "Others", "other")]),
    ("unfinished", "Unfinished", "unfinished", [
        ("active", "Downloading", "active"), ("paused", "Paused", "paused"),
        ("failed", "Failed", "error"), ("scheduled", "Scheduled", "clock")]),
    ("done", "Finished", "finished", []),
]


def matches(it, key):
    if key == "all":
        return True
    if key == "unfinished":
        return it.status != "done"
    if key == "active":
        return it.status in ("downloading", "queued", "pausing")
    if key == "done":
        return it.status == "done"
    if key == "paused":
        return it.status == "paused"
    if key == "failed":
        return it.status == "error"
    if key == "scheduled":
        return getattr(it, "scheduled", False) and it.status != "done"
    return item_category(it) == key


def added_text(ts):
    import datetime as _dt
    d = _dt.datetime.fromtimestamp(ts or 0).date()
    today = _dt.date.today()
    if d == today:
        return "Today"
    if d == today - _dt.timedelta(days=1):
        return "Yesterday"
    return d.strftime("%Y/%m/%d")


STATUS_ORDER = {"downloading": 0, "pausing": 1, "queued": 2, "paused": 3, "error": 4, "done": 5}


def sort_value(it, key):
    if key == "name":
        return (it.name or it.url).lower()
    if key == "size":
        return it.total or 0
    if key == "status":
        return (STATUS_ORDER.get(it.status, 9), -(it.done / it.total if it.total else 0))
    if key == "eta":
        return (it.total - it.done) / it.speed if it.status == "downloading" and it.speed and it.total else 1e12
    return it.added or 0


class MainWindow(QMainWindow):
    def __init__(self, mgr, inbox):
        super().__init__()
        self.mgr = mgr
        self.inbox = inbox
        self._row_ids = []
        self._dialog_open = False
        self._quitting = False
        self._tray_hint_shown = False
        self._filter = "all"
        self._search = ""
        self._sort = ("added", True)        # newest first
        self._checked = set()
        self._notified = {i.id for i in mgr.items if i.status == "done"}

        self._ignore_clip = False
        self._last_clip = ""
        self._update_info = None
        self._update_result = None
        self._update_progress = None
        self._update_stop = threading.Event()
        self._theme_poll = 0
        self._disk_poll = 0
        self.update_status = ""
        self.scheduler = features.Scheduler(mgr)
        self.when_done = features.WhenDone(mgr)

        self.setWindowTitle(APP_NAME)
        app_icon = QIcon(app_icon_path())
        self.setWindowIcon(app_icon)
        scr = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        self.resize(min(1360, scr.width() - 40) if scr else 1360, min(780, scr.height() - 60) if scr else 780)
        self.setMinimumSize(980, 560)

        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        body = QWidget()
        body.setObjectName("Body")
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        line = QFrame()
        line.setObjectName("VLine")
        line.setFixedWidth(1)
        h.addWidget(line)
        right = QWidget()
        right.setObjectName("Right")
        v = QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_toolbar())
        v.addWidget(self._build_banner())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_table())
        self.stack.addWidget(self._build_empty())
        v.addWidget(self.stack, 1)
        v.addWidget(self._build_bottom())
        h.addWidget(right, 1)
        outer.addWidget(body, 1)
        self.setCentralWidget(root)
        self.setAcceptDrops(True)

        # keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_dialog)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_torrent_files)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence.Paste, self, activated=self._paste_shortcut)
        QShortcut(QKeySequence.Delete, self, activated=self.remove_selected)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_selected)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.toggle_capture)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_limit)

        # tray
        self.tray = QSystemTrayIcon(app_icon, self)
        self.tray.setToolTip(APP_NAME)
        self.tray_menu = QMenu()
        self._build_tray_menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(
            lambda r: self.bring_front() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.app_icon = app_icon
        QApplication.clipboard().dataChanged.connect(self._on_clipboard)
        QTimer.singleShot(8000, lambda: self.check_updates(manual=False))
        self._apply_capture_ui()
        self._apply_limit_ui()
        self._apply_when_ui()
        self._update_disk()
        self.refresh()
        self._update_buttons()

    def _build_tray_menu(self):
        menu = self.tray_menu
        menu.clear()
        menu.addAction(icon("all", T("icon"), 16), "Open EDENLOAD", self.bring_front)
        menu.addAction(icon("add", T("icon"), 16), "Add URL…", self.add_dialog)
        menu.addAction(icon("magnet", T("teal"), 16), "Open torrent file…", self.open_torrent_files)
        menu.addAction(icon("link", T("icon"), 16), "Connect browser…", open_browser_guide)
        menu.addSeparator()
        self.tray_capture = menu.addAction("Catch browser downloads")
        self.tray_capture.setCheckable(True)
        self.tray_capture.triggered.connect(lambda *_: self.toggle_capture())
        self.tray_limit = menu.addAction("Limit speed")
        self.tray_limit.setCheckable(True)
        self.tray_limit.triggered.connect(lambda *_: self.toggle_limit())
        when = menu.addMenu(icon("power", T("icon"), 16), "When downloads finish")
        when.aboutToShow.connect(lambda: self._fill_when_menu(when))
        menu.addSeparator()
        menu.addAction(icon("resume_all", T("icon"), 16), "Resume all", self.mgr.resume_all)
        menu.addAction(icon("pause_all", T("icon"), 16), "Pause all", self.mgr.pause_all)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)

    # ---- themes ----
    def apply_theme(self, key=None):
        key = key or self.mgr.settings.get("theme", "aurora")
        theme.apply(QApplication.instance(), asset_url, key)
        app_ic = QIcon(app_icon_path())
        self.setWindowIcon(app_ic)
        QApplication.instance().setWindowIcon(app_ic)
        self._logo.setPixmap(QPixmap(app_icon_path()).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for key_, ic in self._btn_icons.items():
            self.buttons[key_].setIcon(icon(ic, T("icon"), 24, 1.7))
        self._nav_icons()
        self._disk_icon.setPixmap(pixmap("disk", T("icon"), 20))
        self._disk_more.setIcon(icon("dots", T("icon"), 18))
        self._pill_icon.setPixmap(pixmap("link_add", T("muted"), 22))
        self._go.setIcon(icon("cloud_dl", T("on_acc"), 24, 2.1))
        self.search.removeAction(self._search_action)
        self._search_action = self.search.addAction(icon("search", T("muted"), 18), QLineEdit.LeadingPosition)
        self._speed_icon.setPixmap(pixmap("gauge", T("acc"), 22))
        self._down_icon.setPixmap(pixmap("active", T("muted"), 18))
        self._up_icon.setPixmap(pixmap("upload", T("muted"), 18))
        self._empty_art.setPixmap(pixmap("cloud_dl", T("faint"), 72))
        self._banner_icon.setPixmap(pixmap("update", T("info_fg"), 20))
        self._build_tray_menu()
        self._apply_capture_ui()
        self._apply_limit_ui()
        self._apply_when_ui()
        self.gauge.update()
        self.table.viewport().update()
        self.refresh()

    # ---- when downloads finish ----
    def _fill_when_menu(self, m):
        m.clear()
        cur = self.mgr.settings.get("after_done", "none")
        hdr = m.addAction("WHEN ALL DOWNLOADS FINISH")
        hdr.setEnabled(False)
        for key, text in ACTIONS:
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(key == cur)
            a.triggered.connect(lambda _=False, k=key: self.set_after_done(k))
        m.addSeparator()
        m.addAction(icon("clock", T("icon"), 16), "Schedule…", lambda: self.settings_dialog("Schedule"))

    def set_after_done(self, key):
        self.mgr.settings["after_done"] = key
        self.when_done.armed = any(i.status in features.ACTIVE for i in self.mgr.items)
        self._apply_when_ui()
        if key != "none":
            text = dict(ACTIONS)[key]
            busy = self.when_done.armed
            self.tray.showMessage(APP_NAME, f"{text} when all downloads finish." if busy else
                                  f"{text} once the next downloads finish.", QSystemTrayIcon.Information, 3000)

    def _apply_when_ui(self):
        key = self.mgr.settings.get("after_done", "none")
        b = self.buttons["when_done"]
        short = {"none": "When done", "sleep": "Sleep", "shutdown": "Shut down", "quit": "Close"}
        b.setText(short.get(key, "When done"))
        b.setIcon(icon("power", T("info_fg") if key != "none" else T("icon"), 24, 1.7))
        self._btn_icons.pop("when_done", None)
        b.setProperty("on", key != "none")
        b.style().unpolish(b)
        b.style().polish(b)

    def run_finish_action(self, action, why):
        if action in (None, "none"):
            return
        if self._dialog_open:     # try again on a later tick
            QTimer.singleShot(5000, lambda: self.run_finish_action(action, why))
            return
        self._dialog_open = True
        try:
            go = CountdownDialog(self, action, why).exec() == QDialog.Accepted
        finally:
            self._dialog_open = False
        if not go:
            return
        self.mgr.save()
        if action == "quit":
            self.quit_app()
        elif action == "shutdown":
            self.mgr.shutdown()
            features.power_action("shutdown")
            self.quit_app()
        elif action == "sleep":
            features.power_action("sleep")

    # ---- clipboard ----
    def _on_clipboard(self):
        s = self.mgr.settings
        if self._ignore_clip:
            self._ignore_clip = False
            return
        if not s.get("clipboard", False) or self._dialog_open:
            return
        url = features.clip_candidate(QApplication.clipboard().text(), VIDEO_SITES, s.get("clipboard_video", False))
        if not url or url == self._last_clip:
            return
        self._last_clip = url
        if any(i.url == url and i.status != "done" for i in self.mgr.items):
            return
        kind = "torrent" if is_torrent_source(url) else ("video" if VIDEO_SITES.search(url) else "file")
        self.inbox.put({"url": url, "type": kind, "from": "clipboard"})

    # ---- updates ----
    def _build_banner(self):
        f = QFrame()
        f.setObjectName("Banner")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 8, 12, 8)
        h.setSpacing(10)
        self._banner_icon = QLabel()
        self._banner_icon.setPixmap(pixmap("update", T("info_fg"), 20))
        h.addWidget(self._banner_icon)
        self._banner_text = QLabel("")
        h.addWidget(self._banner_text, 1)
        self._banner_bar = QProgressBar()
        self._banner_bar.setFixedWidth(180)
        self._banner_bar.setRange(0, 1000)
        self._banner_bar.hide()
        h.addWidget(self._banner_bar)
        self._banner_go = primary(QPushButton("Update now"))
        self._banner_go.clicked.connect(self.start_update)
        self._banner_skip = QPushButton("Skip this version")
        self._banner_skip.clicked.connect(self._skip_update)
        self._banner_later = QPushButton("Later")
        self._banner_later.clicked.connect(lambda: f.hide())
        for b in (self._banner_go, self._banner_skip, self._banner_later):
            h.addWidget(b)
        f.hide()
        self.banner = f
        return f

    def check_updates(self, manual=False):
        """Background check. manual=True ignores 'skip' and the 12-hour timer."""
        if not manual and not features.update_due(self.mgr.settings):
            return
        self.mgr.settings["last_update_check"] = time.time()

        def work():
            try:
                self._update_result = ("ok", features.check_latest(), manual)
            except Exception as e:
                self._update_result = ("error", str(e), manual)
        threading.Thread(target=work, daemon=True).start()

    def _handle_update_result(self):
        res, self._update_result = self._update_result, None
        kind, data, manual = res
        if kind == "error":
            if manual:
                self.tray.showMessage(APP_NAME, f"Couldn't check for updates: {data}", QSystemTrayIcon.Warning, 4000)
            self.update_status = f"Couldn't check: {data}"
            return
        if features.is_newer(data["version"]) and (manual or data["version"] != self.mgr.settings.get("skip_version")):
            self._update_info = data
            self.update_status = f"Version {data['version']} is available."
            self._banner_text.setText(f"<b>EDENLOAD {data['version']}</b> is available — you have {features.VERSION}.")
            self._banner_bar.hide()
            for b in (self._banner_go, self._banner_skip, self._banner_later):
                b.show()
                b.setEnabled(True)
            self.banner.show()
            self.tray.showMessage(APP_NAME, f"EDENLOAD {data['version']} is available. Open EDENLOAD to update.",
                                  QSystemTrayIcon.Information, 5000)
        else:
            self.update_status = f"You have the latest version ({features.VERSION})."
            if manual:
                self.tray.showMessage(APP_NAME, self.update_status, QSystemTrayIcon.Information, 3000)

    def _skip_update(self):
        if self._update_info:
            self.mgr.settings["skip_version"] = self._update_info["version"]
            self.mgr.save()
        self.banner.hide()

    def start_update(self):
        info = self._update_info
        if not info:
            return
        self._banner_text.setText(f"Downloading EDENLOAD {info['version']}…")
        self._banner_bar.setValue(0)
        self._banner_bar.show()
        self._banner_go.setEnabled(False)
        self._banner_skip.hide()
        self._banner_later.setText("Cancel")
        self._banner_later.clicked.disconnect()
        self._banner_later.clicked.connect(self._cancel_update)
        self._update_stop.clear()
        dest = os.path.join(tempfile.gettempdir(), f"EDENLOAD-Setup-{info['version']}.exe")

        def prog(done, total):
            self._update_progress = (done, total, None)

        def work():
            try:
                features.download_update(info["url"], dest, prog, self._update_stop)
                self._update_progress = (1, 1, dest)
            except Exception as e:
                self._update_progress = (0, 0, "error:" + str(e))
        threading.Thread(target=work, daemon=True).start()

    def _cancel_update(self):
        self._update_stop.set()
        self.banner.hide()
        self._banner_later.setText("Later")
        self._banner_later.clicked.disconnect()
        self._banner_later.clicked.connect(lambda: self.banner.hide())

    def _handle_update_progress(self):
        done, total, result = self._update_progress
        if total:
            self._banner_bar.setValue(int(1000 * done / total))
        if result is None:
            return
        self._update_progress = None
        if result.startswith("error:"):
            if not self._update_stop.is_set():
                self._banner_text.setText("The update couldn't be downloaded: " + result[6:])
                self._banner_bar.hide()
                self._banner_go.setEnabled(True)
            return
        self._banner_text.setText("Installing the update — EDENLOAD will reopen by itself…")
        QApplication.processEvents()
        self.mgr.shutdown()
        try:
            features.run_installer(result)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Couldn't start the installer:\n{e}")
            return
        self.quit_app()

    # ---- speed limits ----
    def toggle_limit(self):
        s = self.mgr.settings
        s["limit_on"] = not s.get("limit_on", False)
        if s["limit_on"] and not any(s.get(k) for k in ("limit_down", "torrent_down", "torrent_up")):
            s["limit_down"] = 1024     # turned on with nothing set: use a sensible default
        self._limits_changed()

    def _limits_changed(self):
        self.mgr.apply_limits()
        self.mgr.save()
        self._apply_limit_ui()

    def _apply_limit_ui(self):
        s = self.mgr.settings
        on = s.get("limit_on", False)
        b = self.buttons["speed"]
        down, t_down, t_up = self.mgr.effective_limits()
        b.setText(fmt_rate(down) if on and down else ("Limited" if on else "Speed"))
        b.setIcon(icon("gauge", T("info_fg") if on else T("icon"), 24, 1.7))
        self._btn_icons.pop("speed", None)
        if on:
            tip = (f"Speed limit ON\nDownloads: {fmt_rate(down)}\nTorrents: ↓ {fmt_rate(t_down)}"
                   f"   ↑ {fmt_rate(t_up)}\nClick for options (Ctrl+L turns it off)")
        else:
            tip = "No speed limit — click for options (Ctrl+L turns it on)"
        b.setToolTip(tip)
        b.setProperty("on", on)
        b.style().unpolish(b)
        b.style().polish(b)
        self.tray_limit.setChecked(on)

    def _preset_menu(self, parent_menu, title, current, on_pick, ask_title):
        sub = parent_menu.addMenu(title) if title else parent_menu
        group = []
        for kb in PRESETS:
            a = sub.addAction(fmt_rate(kb))
            a.setCheckable(True)
            a.setChecked(kb == current)
            a.triggered.connect(lambda _=False, v=kb: on_pick(v))
            group.append(a)
        sub.addSeparator()
        is_custom = current > 0 and current not in PRESETS     # current == -1: mixed selection
        custom = sub.addAction(f"Custom ({fmt_rate(current)})…" if is_custom else "Custom…")
        custom.setCheckable(True)
        custom.setChecked(is_custom)
        start = current if current > 0 else 1024
        custom.triggered.connect(lambda _=False: self._ask_rate(ask_title, start, on_pick))
        return sub

    def _ask_rate(self, title, current, on_pick):
        self._dialog_open = True
        try:
            v = RateDialog.ask(self, title, current)
        finally:
            self._dialog_open = False
        if v is not None:
            on_pick(v)

    def _fill_speed_menu(self, m):
        m.clear()
        s = self.mgr.settings
        on = m.addAction("Limit speed")
        on.setCheckable(True)
        on.setChecked(s.get("limit_on", False))
        on.setShortcut(QKeySequence("Ctrl+L"))
        on.triggered.connect(lambda _=False: self.toggle_limit())
        m.addSeparator()

        def setter(key):
            def pick(kb):
                s[key] = kb
                if kb:
                    s["limit_on"] = True
                self._limits_changed()
            return pick

        hdr = m.addAction("DOWNLOADS")
        hdr.setEnabled(False)
        self._preset_menu(m, None, s.get("limit_down", 0), setter("limit_down"), "Download speed limit")
        m.addSeparator()
        self._preset_menu(m, f"Torrent download  ({fmt_rate(s.get('torrent_down', 0))})",
                          s.get("torrent_down", 0), setter("torrent_down"), "Torrent download limit")
        self._preset_menu(m, f"Torrent upload  ({fmt_rate(s.get('torrent_up', 0))})",
                          s.get("torrent_up", 0), setter("torrent_up"), "Torrent upload limit")
        m.addSeparator()
        m.addAction(icon("gauge", T("icon"), 16), "Speed limits…", self.speed_dialog)

    def speed_dialog(self):
        self._dialog_open = True
        try:
            if SpeedDialog(self, self.mgr).exec() == QDialog.Accepted:
                self._apply_limit_ui()
        finally:
            self._dialog_open = False

    def _set_item_limit(self, items, kb, upload=False):
        for it in items:
            if upload:
                if it.kind == "torrent":
                    it.set_upload_limit(kb)
            else:
                it.set_limit(kb)
        self.mgr.save()
        self.refresh()

    # ---- browser catching on/off ----
    def toggle_capture(self):
        s = self.mgr.settings
        s["capture"] = not s.get("capture", True)
        self.mgr.save()
        self._apply_capture_ui()
        self.tray.showMessage(APP_NAME, "Catching browser downloads is ON." if s["capture"] else
                              "Catching is OFF — your browser will download files itself.",
                              QSystemTrayIcon.Information, 3000)

    def _apply_capture_ui(self):
        on = self.mgr.settings.get("capture", True)
        b = self.capture_btn
        b.setText("Browser: catching" if on else "Browser: not catching")
        b.setIcon(icon("catch" if on else "catch_off", T("ok") if on else T("warn_text"), 16))
        b.setToolTip(("Catching downloads from the browser — click to turn off" if on else
                      "Not catching — the browser downloads files itself. Click to turn on")
                     + "  (Ctrl+Shift+C)")
        b.setProperty("off", not on)
        b.style().unpolish(b)
        b.style().polish(b)
        self.tray_capture.setChecked(on)
        self.tray.setIcon(QIcon(app_icon_path()) if on else QIcon(resource("app_off.png")))

    # ---- building ----
    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("Header")
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 10, 18, 10)
        h.setSpacing(10)
        logo = QLabel()
        self._logo = logo
        logo.setPixmap(QPixmap(app_icon_path()).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(logo)
        h.addWidget(label("EDENLOAD", "HeaderBrand"))
        h.addSpacing(18)
        mb = QMenuBar()
        mb.setObjectName("MainMenu")
        mb.setNativeMenuBar(False)
        self._menus = {}
        for name in ("Tasks", "File", "Downloads", "View", "Help"):
            m = mb.addMenu(name)
            self._menus[name] = m
            m.aboutToShow.connect(lambda m=m, n=name: self._fill_main_menu(n, m))
        h.addWidget(mb)
        h.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search in the list")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(icon("search", T("muted"), 18), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._search_changed)
        self.search.setFixedWidth(340)
        h.addWidget(self.search)
        return bar

    def _fill_main_menu(self, name, m):
        m.clear()
        c = T("icon")
        sel = self._selected()
        if name == "Tasks":
            m.addAction(icon("link_add", c, 16), "Add URL…\tCtrl+N", self.add_dialog)
            m.addAction(icon("magnet", T("teal"), 16), "Open torrent file…\tCtrl+O", self.open_torrent_files)
            m.addSeparator()
            m.addAction(icon("resume_all", c, 16), "Resume all", self.mgr.resume_all)
            m.addAction(icon("stop_all", c, 16), "Stop all", self.mgr.pause_all)
            m.addSeparator()
            m.addAction("Quit EDENLOAD", self.quit_app)
        elif name == "File":
            for text, ic, slot, ok in (
                    ("Open file", "open", self.open_selected, any(i.status == "done" for i in sel)),
                    ("Show in folder", "folder", self.folder_selected, True),
                    ("Copy link", "link", self.copy_link, bool(sel))):
                a = m.addAction(icon(ic, c, 16), text, slot)
                a.setEnabled(ok)
            m.addSeparator()
            a = m.addAction(icon("trash", T("danger_icon"), 16), "Delete…\tDel", self.remove_selected)
            a.setEnabled(bool(sel))
        elif name == "Downloads":
            m.addAction(icon("gauge", c, 16), "Speed limits…", self.speed_dialog)
            lim = m.addAction("Limit speed\tCtrl+L", self.toggle_limit)
            lim.setCheckable(True)
            lim.setChecked(self.mgr.settings.get("limit_on", False))
            when = m.addMenu(icon("power", c, 16), "When downloads finish")
            self._fill_when_menu(when)
            m.addAction(icon("calendar", c, 16), "Scheduler…", lambda: self.settings_dialog("Schedule"))
            m.addSeparator()
            cap = m.addAction("Catch browser downloads\tCtrl+Shift+C", self.toggle_capture)
            cap.setCheckable(True)
            cap.setChecked(self.mgr.settings.get("capture", True))
            m.addAction(icon("broom", c, 16), "Disk Cleaner…", self.disk_cleaner)
        elif name == "View":
            tm = m.addMenu(icon("palette", c, 16), "Theme")
            grp = QActionGroup(tm)
            cur = self.mgr.settings.get("theme", "aurora")
            for key, text in theme.CHOICES:
                a = tm.addAction(theme_swatch(key), text)
                a.setCheckable(True)
                a.setChecked(key == cur)
                grp.addAction(a)
                a.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            m.addSeparator()
            m.addAction(icon("gear", c, 16), "Options…", self.settings_dialog)
        elif name == "Help":
            m.addAction(icon("link", c, 16), "Connect browser…", open_browser_guide)
            m.addAction(icon("update", c, 16), "Check for updates", lambda: self.check_updates(manual=True))
            m.addSeparator()
            m.addAction(f"About EDENLOAD {features.VERSION}", lambda: QMessageBox.about(
                self, APP_NAME, f"<b>EDENLOAD {features.VERSION}</b><br>Download manager for files, videos "
                                "and torrents."))

    def _set_theme(self, key):
        self.mgr.settings["theme"] = key
        self.mgr.save()
        self.apply_theme(key)

    def _build_sidebar(self):
        col = QWidget()
        col.setObjectName("Body")
        col.setFixedWidth(272)
        v = QVBoxLayout(col)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(10, 10, 10, 10)
        nav = QTreeWidget()
        nav.setObjectName("Nav")
        nav.setColumnCount(2)
        nav.setHeaderHidden(True)
        nav.setRootIsDecorated(False)
        nav.setIndentation(26)
        nav.setIconSize(QSize(20, 20))
        nav.setFocusPolicy(Qt.NoFocus)
        nav.setExpandsOnDoubleClick(False)
        nav.header().setStretchLastSection(False)
        nav.header().setSectionResizeMode(0, QHeaderView.Stretch)
        nav.header().setSectionResizeMode(1, QHeaderView.Fixed)
        nav.setColumnWidth(1, 40)
        self._filter_items = {}
        for key, text, ic, kids in NAV:
            top = QTreeWidgetItem([text, ""])
            top.setData(0, Qt.UserRole, key)
            top.setData(0, Qt.UserRole + 1, text)
            top.setData(0, Qt.UserRole + 2, ic)
            f = top.font(0)
            f.setPointSizeF(f.pointSizeF() + 0.6)
            f.setWeight(QFont.DemiBold)
            top.setFont(0, f)
            nav.addTopLevelItem(top)
            self._filter_items[key] = top
            for k, t, i in kids:
                ch = QTreeWidgetItem([t, ""])
                ch.setData(0, Qt.UserRole, k)
                ch.setData(0, Qt.UserRole + 1, t)
                ch.setData(0, Qt.UserRole + 2, i)
                ch.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                top.addChild(ch)
                self._filter_items[k] = ch
        nav.topLevelItem(0).setExpanded(True)
        nav.itemClicked.connect(self._nav_clicked)
        nav.currentItemChanged.connect(self._filter_changed)
        nav.itemExpanded.connect(lambda *_: self._nav_icons())
        nav.itemCollapsed.connect(lambda *_: self._nav_icons())
        nav.setCurrentItem(self._filter_items["all"])
        self.nav = nav
        self._nav_icons()
        cv.addWidget(nav)
        v.addWidget(card, 1)

        disk = QFrame()
        disk.setObjectName("Card")
        dv = QVBoxLayout(disk)
        dv.setContentsMargins(16, 14, 16, 16)
        dv.setSpacing(4)
        top = QHBoxLayout()
        self._disk_icon = QLabel()
        self._disk_icon.setPixmap(pixmap("disk", T("icon"), 20))
        top.addWidget(self._disk_icon)
        top.addWidget(label("Disk Space", "CardTitle"))
        top.addStretch()
        more = QToolButton()
        more.setObjectName("Flat")
        more.setIcon(icon("dots", T("icon"), 18))
        more.setPopupMode(QToolButton.InstantPopup)
        dm = QMenu(more)
        dm.addAction("Open download folder", lambda: (os.makedirs(self.mgr.settings["save_dir"], exist_ok=True),
                                                       open_path(self.mgr.settings["save_dir"])))
        dm.addAction("Change download folder…", lambda: self.settings_dialog("Downloads"))
        more.setMenu(dm)
        self._disk_more = more
        top.addWidget(more)
        dv.addLayout(top)
        self.gauge = DiskGauge()
        dv.addWidget(self.gauge)
        self.disk_pct = label("", "GaugeText")
        self.disk_pct.setAlignment(Qt.AlignCenter)
        dv.addWidget(self.disk_pct)
        self.disk_path = label("", "Muted")
        self.disk_path.setAlignment(Qt.AlignCenter)
        dv.addWidget(self.disk_path)
        dv.addSpacing(10)
        clean = QPushButton("Disk Cleaner")
        clean.setObjectName("Gradient")
        clean.setCursor(Qt.PointingHandCursor)
        clean.setToolTip("Delete leftovers of downloads that were cancelled or removed")
        clean.clicked.connect(self.disk_cleaner)
        dv.addWidget(clean)
        v.addWidget(disk)
        return col

    def _nav_icons(self):
        for key, it in self._filter_items.items():
            ic = it.data(0, Qt.UserRole + 2)
            top = it.parent() is None
            color = T("strong") if top else T("side_text")
            it.setIcon(0, icon(ic, color, 20 if top else 18))
            if top and it.childCount():
                it.setIcon(1, icon("chev_up" if it.isExpanded() else "chev_down", T("muted"), 16))

    def _nav_clicked(self, item, col):
        if item.parent() is None and item.childCount() and col == 1:
            item.setExpanded(not item.isExpanded())

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setObjectName("Tools")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))
        self.buttons = {}
        self._btn_icons = {}

        pill = QFrame()
        pill.setObjectName("AddPill")
        pill.setFixedWidth(330)
        ph = QHBoxLayout(pill)
        ph.setContentsMargins(14, 6, 6, 6)
        ph.setSpacing(8)
        self._pill_icon = QLabel()
        self._pill_icon.setPixmap(pixmap("link_add", T("muted"), 22))
        ph.addWidget(self._pill_icon)
        self.url_box = QLineEdit()
        self.url_box.setPlaceholderText("Add Url")
        self.url_box.returnPressed.connect(self._add_from_box)
        ph.addWidget(self.url_box, 1)
        go = QToolButton()
        go.setObjectName("Go")
        go.setFixedSize(46, 40)
        go.setIcon(icon("cloud_dl", "#ffffff", 24, 2.1))
        go.setIconSize(QSize(24, 24))
        go.setCursor(Qt.PointingHandCursor)
        go.setToolTip("Download this link (Enter)")
        go.clicked.connect(self._add_from_box)
        self._go = go
        ph.addWidget(go)
        tb.addWidget(pill)

        def sep():
            f = QFrame()
            f.setObjectName("VLine")
            f.setFixedSize(1, 40)
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(10, 0, 10, 0)
            l.addWidget(f)
            tb.addWidget(w)

        def btn(key, text, ic, slot, tip):
            b = QToolButton()
            b.setText(text)
            b.setIcon(icon(ic, T("icon"), 24, 1.7))
            self._btn_icons[key] = ic
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            if slot:
                b.clicked.connect(lambda checked=False, s=slot: s())
            tb.addWidget(b)
            self.buttons[key] = b
            return b

        sep()
        btn("resume", "Resume", "play", self.resume_selected, "Resume selected (Space)")
        btn("pause", "Stop", "stop", self.pause_selected, "Stop selected (Space)")
        btn("pause_all", "Stop All", "stop_all", self.mgr.pause_all, "Stop all downloads")
        sep()
        btn("delete", "Delete", "trash", self.remove_selected, "Delete selected (Del)")
        btn("open_torrent", "Torrent", "magnet", self.open_torrent_files, "Open .torrent files (Ctrl+O)")
        sp = btn("speed", "Speed", "gauge", None, "Speed limits")
        sp.setPopupMode(QToolButton.InstantPopup)
        self.speed_menu = QMenu(sp)
        self.speed_menu.aboutToShow.connect(lambda: self._fill_speed_menu(self.speed_menu))
        sp.setMenu(self.speed_menu)
        wd = btn("when_done", "When done", "power", None,
                 "Sleep, shut down or close EDENLOAD when all downloads finish")
        wd.setPopupMode(QToolButton.InstantPopup)
        self.when_menu = QMenu(wd)
        self.when_menu.aboutToShow.connect(lambda: self._fill_when_menu(self.when_menu))
        wd.setMenu(self.when_menu)
        btn("scheduler", "Scheduler", "calendar", lambda: self.settings_dialog("Schedule"), "Scheduler")
        btn("options", "Options", "gear", self.settings_dialog, "Options")
        btn("share", "Share", "share", self.copy_link, "Copy the download link")
        return tb

    def _add_from_box(self):
        text = self.url_box.text().strip()
        self.url_box.clear()
        if not text:
            self.add_dialog()
            return
        payloads = args_to_payloads([text]) or [{"url": text}]
        self.add_dialog(payloads[0])

    def _build_table(self):
        t = QTableWidget(0, len(COLS))
        t.setObjectName("List")
        t.setHorizontalHeaderLabels(COLS)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setShowGrid(False)
        t.setWordWrap(False)
        t.setFocusPolicy(Qt.NoFocus)
        t.setMouseTracking(True)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(64)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh = t.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False)
        hh.setSectionsClickable(True)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c, w in ((0, 52), (2, 110), (3, 230), (4, 110), (5, 120)):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            t.setColumnWidth(c, w)
        hh.sectionClicked.connect(self._sort_clicked)
        t.setItemDelegateForColumn(0, CheckDelegate(t, first=True))
        t.setItemDelegateForColumn(1, NameDelegate(t))
        t.setItemDelegateForColumn(2, RowDelegate(t))
        t.setItemDelegateForColumn(3, StatusDelegate(t))
        t.setItemDelegateForColumn(4, RowDelegate(t))
        t.setItemDelegateForColumn(5, RowDelegate(t, last=True))
        t.doubleClicked.connect(lambda *_: self._double_click())
        t.clicked.connect(self._cell_clicked)
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._row_menu)
        t.itemSelectionChanged.connect(self._update_buttons)
        t.viewport().installEventFilter(self)
        self.table = t
        self._update_header_labels()
        return t

    def eventFilter(self, obj, ev):
        if getattr(self, "table", None) is not None and obj is self.table.viewport():
            if ev.type() == QEvent.MouseMove:
                row = self.table.rowAt(int(ev.position().y()))
                if self.table.property("hoverRow") != row:
                    self.table.setProperty("hoverRow", row)
                    self.table.viewport().update()
            elif ev.type() == QEvent.Leave:
                self.table.setProperty("hoverRow", -1)
                self.table.viewport().update()
        return super().eventFilter(obj, ev)

    def _sort_clicked(self, col):
        key = SORT_KEYS.get(col)
        if not key:
            return
        cur, desc = self._sort
        self._sort = (key, not desc if cur == key else key in ("size", "added"))
        self._update_header_labels()
        self._row_ids = []
        self.refresh()

    def _update_header_labels(self):
        key, desc = self._sort
        for col, name in enumerate(COLS):
            k = SORT_KEYS.get(col)
            mark = (" ↓" if desc else " ↑") if k == key else (" ⇅" if k else "")
            self.table.horizontalHeaderItem(col).setText(name + mark) if self.table.horizontalHeaderItem(col) \
                else self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name + mark))

    def _cell_clicked(self, idx):
        if idx.column() != 0 or idx.row() >= len(self._row_ids):
            return
        i = self._row_ids[idx.row()]
        self._checked.symmetric_difference_update({i})
        self.refresh()

    def _build_bottom(self):
        bar = QFrame()
        bar.setObjectName("Bottom")
        h = QHBoxLayout(bar)
        h.setContentsMargins(22, 10, 22, 10)
        h.setSpacing(14)
        self.select_all = QCheckBox("Select All")
        self.select_all.setTristate(False)
        self.select_all.clicked.connect(self._select_all_clicked)
        h.addWidget(self.select_all)
        self.sel_info = label("", "Muted")
        h.addWidget(self.sel_info)
        h.addStretch()
        cap = QToolButton()
        cap.setObjectName("CatchPill")
        cap.setCursor(Qt.PointingHandCursor)
        cap.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        cap.clicked.connect(self.toggle_capture)
        self.capture_btn = cap
        h.addWidget(cap)
        h.addSpacing(10)
        self._speed_icon = QLabel()
        self._speed_icon.setPixmap(pixmap("gauge", T("acc"), 22))
        h.addWidget(self._speed_icon)
        h.addWidget(QLabel("Speed :"))
        self._down_icon = QLabel()
        self._down_icon.setPixmap(pixmap("active", T("muted"), 18))
        h.addWidget(self._down_icon)
        self.down_val = label("0 B/s", "SpeedVal")
        h.addWidget(self.down_val)
        h.addSpacing(8)
        self._up_icon = QLabel()
        self._up_icon.setPixmap(pixmap("upload", T("muted"), 18))
        h.addWidget(self._up_icon)
        self.up_val = label("0 B/s", "SpeedVal")
        h.addWidget(self.up_val)
        return bar

    def _select_all_clicked(self, *_):
        vis = [i.id for i in self._visible_items()]
        if vis and all(i in self._checked for i in vis):
            self._checked.difference_update(vis)
        else:
            self._checked.update(vis)
        self.refresh()

    def _update_disk(self):
        folder = self.mgr.settings["save_dir"]
        p = folder
        while p and not os.path.exists(p):
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
        try:
            import shutil as _sh
            u = _sh.disk_usage(p)
            frac = u.used / u.total if u.total else 0
            self.gauge.set_value(frac)
            self.disk_pct.setText(f"{frac * 100:.0f}%")
            self.disk_path.setText(f"{folder}\n{human_size(u.free)} free of {human_size(u.total)}")
            self.disk_path.setToolTip(folder)
        except OSError:
            self.disk_pct.setText("—")
            self.disk_path.setText(folder)

    def disk_cleaner(self):
        self._dialog_open = True
        try:
            CleanerDialog(self, self.mgr).exec()
        finally:
            self._dialog_open = False
        self._update_disk()
        self.refresh()

    def _build_empty(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch()
        art = QLabel()
        art.setPixmap(pixmap("cloud_dl", T("faint"), 72))
        self._empty_art = art
        art.setAlignment(Qt.AlignCenter)
        v.addWidget(art)
        v.addSpacing(10)
        self.empty_title = label("No downloads yet", "EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty_title)
        self.empty_text = label("Click a download link in Chrome or Edge and it lands here.\n"
                                "Or paste a link in “Add Url” above, or drop a .torrent file here.", "Muted")
        self.empty_text.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty_text)
        v.addStretch()
        return w

    # ---- loop ----
    def tick(self):
        if not self._dialog_open:
            while True:
                try:
                    data = self.inbox.get_nowait()
                except queue.Empty:
                    break
                self.handle_incoming(data)
                if self._dialog_open:
                    break
        self.mgr.tick()
        for ev, n in self.scheduler.tick():
            if ev == "started":
                self.tray.showMessage("Schedule", f"Started {n} scheduled download{'s' if n != 1 else ''}."
                                      if n else "Schedule started — nothing waiting in the queue.",
                                      QSystemTrayIcon.Information, 4000)
            elif ev == "stopped" and n:
                self.tray.showMessage("Schedule", f"Paused {n} scheduled download{'s' if n != 1 else ''} "
                                      "(stop time reached).", QSystemTrayIcon.Information, 4000)
            elif ev == "finished":
                act = self.mgr.settings.get("schedule_action", "none")
                self.tray.showMessage("Schedule", "All scheduled downloads finished.", QSystemTrayIcon.Information, 4000)
                QTimer.singleShot(0, lambda a=act: self.run_finish_action(a, "Scheduled downloads finished."))
        act = self.when_done.tick()
        if act:
            self._apply_when_ui()
            QTimer.singleShot(0, lambda a=act: self.run_finish_action(a, "All downloads finished."))
        if self._update_result:
            self._handle_update_result()
        if self._update_progress:
            self._handle_update_progress()
        self._theme_poll += 1
        if self._theme_poll >= 20:          # every ~10 s
            self._theme_poll = 0
            if self.mgr.settings.get("theme") == "system" and theme.resolve("system") != theme.KEY:
                self.apply_theme()
            if self.mgr.settings.get("auto_update", True) and features.update_due(self.mgr.settings):
                self.check_updates(manual=False)
        if not self._dialog_open:
            for it in list(self.mgr.items):
                if it.kind == "torrent" and it.awaiting_files and it.status == "downloading":
                    self.choose_files(it, new=True)
                    break
        for it in self.mgr.items:
            if it.status == "done" and it.id not in self._notified:
                self._notified.add(it.id)
                self.tray.showMessage("Download complete", it.name, QSystemTrayIcon.Information, 4000)
        self.refresh()

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        items = []
        for u in md.urls():
            items.append(u.toLocalFile() if u.isLocalFile() else u.toString())
        if not items and md.hasText():
            items = [md.text().strip()]
        payloads = args_to_payloads(items)
        e.acceptProposedAction()
        for p in payloads:
            self.inbox.put(p)

    def handle_incoming(self, data):
        if data.get("action") == "show":
            self.bring_front()
            return
        url = str(data.get("url", ""))
        if data.get("type") == "torrent" and url.lower().endswith(".torrent") and os.path.isfile(url):
            # a .torrent file on this computer (dropped, double-clicked, opened with…): add it straight away
            self.bring_front()
            self.mgr.add(self.mgr.new_torrent(url), start=True)
            self._select_filter("Torrents")
            self.refresh()
            return
        self.add_dialog(data)

    def _visible_items(self):
        q = self._search.lower()
        items = [i for i in self.mgr.items if matches(i, self._filter)
                 and (not q or q in (i.name or "").lower() or q in (i.url or "").lower())]
        key, desc = self._sort
        items.sort(key=lambda i: sort_value(i, key), reverse=desc)
        return items

    def _search_changed(self, text):
        self._search = text.strip()
        self.refresh()

    def refresh(self):
        items = self._visible_items()
        ids = [i.id for i in items]
        t = self.table
        self._checked &= {i.id for i in self.mgr.items}
        if ids != self._row_ids:
            selected = set(self._selected_row_ids())
            t.setRowCount(len(items))
            for r in range(len(items)):
                for c in range(len(COLS)):
                    if not t.item(r, c):
                        t.setItem(r, c, QTableWidgetItem())
            self._row_ids = ids
            t.clearSelection()
            for r, i in enumerate(ids):
                if i in selected:
                    t.selectRow(r)
        for r, it in enumerate(items):
            done, total = it.done, it.total
            cat = item_category(it)
            ic_name = CATEGORY_ICON.get(cat, CATEGORY_ICON["Other"])[0]
            t.item(r, 0).setData(Qt.UserRole, it.id in self._checked)
            sub = TYPE_LABEL.get(cat, "File")
            if getattr(it, "scheduled", False) and it.status != "done":
                sub += "  ·  scheduled"
            if it.limit or getattr(it, "limit_up", 0):
                sub += f"  ·  max {fmt_rate(it.limit)}" if it.limit else "  ·  upload limited"
            name = t.item(r, 1)
            name.setData(Qt.UserRole, (it.name or it.url, sub, ic_name))
            name.setToolTip(f"{it.name}\n{it.url}")
            t.item(r, 2).setText(human_size(total) if total else "—")
            frac = min(done, total) / total if total else (1.0 if it.status == "done" else 0.0)
            pct = f"{100 * frac:.0f}%" if total else (human_size(done) if done else "")
            running = it.status == "downloading"
            right = f"{human_size(it.speed)}/s" if running and it.speed else ""
            extra = ""
            if it.kind == "torrent":
                if it.status == "downloading" and it.awaiting_files:
                    extra = "choose files"
                elif it.status == "downloading":
                    extra = {"metadata": "getting info", "checking": "checking"}.get(it.phase, f"{it.peers} peers")
                    if it.upload:
                        extra += f"  ·  ↑ {human_size(it.upload)}/s"
                elif it.status == "done" and it.seeding:
                    extra = "· seeding"
            restart = (it.status == "paused" and it.kind == "file" and not getattr(it, "resumable", True) and done)
            if restart:
                pct += "  · restarts"
            t.item(r, 3).setData(Qt.UserRole, (it.status, frac, pct, right, extra))
            t.item(r, 3).setToolTip(it.error or ("This server doesn't support resume, so it will start over."
                                                 if restart else ""))
            eta = (total - done) / it.speed if running and it.speed and total else None
            t.item(r, 4).setText(human_time(eta) if eta is not None else ("0 Sec" if it.status == "done" else "—"))
            t.item(r, 5).setText(added_text(it.added))
        t.viewport().update()

        # empty state
        if items:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)
            if self.mgr.items:
                self.empty_title.setText("Nothing here")
                self.empty_text.setText("No downloads match this view" + (" or search." if self._search else "."))
            else:
                self.empty_title.setText("No downloads yet")
                self.empty_text.setText("Click a download link in Chrome or Edge and it lands here.\n"
                                        "Or paste a link in “Add Url” above, or drop a .torrent file here.")

        # sidebar counts
        for key, li in self._filter_items.items():
            n = sum(1 for i in self.mgr.items if matches(i, key))
            if li.parent() is not None or not li.childCount():
                li.setText(1, str(n) if n else "")
        # bottom bar
        vis_ids = set(ids)
        n_checked = len(self._checked & vis_ids)
        self.select_all.setChecked(bool(vis_ids) and n_checked == len(vis_ids))
        self.sel_info.setText(f"{n_checked} selected" if n_checked else "")
        active = [i for i in self.mgr.items if i.status == "downloading"]
        speed = sum(i.speed for i in active)
        up = sum(getattr(i, "upload", 0.0) or 0.0 for i in self.mgr.items)
        self.down_val.setText(f"{human_size(speed)}/s" if speed else "0 B/s")
        self.up_val.setText(f"{human_size(up)}/s" if up else "0 B/s")
        if active:
            self.tray.setToolTip(f"{APP_NAME}\n{len(active)} downloading · {human_size(speed)}/s")
        else:
            self.tray.setToolTip(APP_NAME)
        self._update_buttons()

    def _filter_changed(self, cur, _prev):
        if not hasattr(self, "stack"):
            return
        if cur is not None and cur.data(0, Qt.UserRole):
            self._filter = cur.data(0, Qt.UserRole)
            self._row_ids = []
            self.refresh()

    # ---- selection helpers ----
    def _selected_row_ids(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._row_ids[r] for r in rows if r < len(self._row_ids)]

    def _selected_ids(self):
        """Ticked rows if any are ticked, otherwise the highlighted rows."""
        ticked = [i for i in self._row_ids if i in self._checked]
        return ticked or self._selected_row_ids()

    def _selected(self):
        return [it for it in (self.mgr.get(i) for i in self._selected_ids()) if it]

    def _update_buttons(self):
        sel = self._selected()
        b = self.buttons
        b["resume"].setEnabled(any(i.status in ("paused", "error", "pausing") for i in sel))
        b["pause"].setEnabled(any(i.status in ("downloading", "queued") for i in sel))
        b["delete"].setEnabled(bool(sel))
        b["share"].setEnabled(bool(sel))
        b["pause_all"].setEnabled(any(i.status in ("downloading", "queued") for i in self.mgr.items))

    def _row_menu(self, pos):
        sel = self._selected()
        if not sel:
            return
        m = QMenu(self)
        c = T("icon")
        m.addAction(icon("play", c, 16), "Resume", self.resume_selected)
        m.addAction(icon("pause", c, 16), "Pause", self.pause_selected)
        m.addSeparator()
        m.addAction(icon("open", c, 16), "Open file", self.open_selected)
        m.addAction(icon("folder", c, 16), "Show in folder", self.folder_selected)
        m.addAction(icon("link", c, 16), "Copy link", self.copy_link)
        t = sel[0]
        if len(sel) == 1 and t.kind == "torrent" and t.has_metadata():
            m.addAction(icon("magnet", T("teal"), 16), "Choose files…",
                        lambda: self.choose_files(t, new=t.awaiting_files))
        if self.mgr.settings.get("schedule_on") or any(getattr(i, "scheduled", False) for i in sel):
            in_sched = all(getattr(i, "scheduled", False) for i in sel)
            m.addAction(icon("clock", c, 16), "Remove from schedule" if in_sched else "Add to schedule",
                        lambda items=sel, v=not in_sched: self._set_scheduled(items, v))
        m.addSeparator()
        cur = sel[0].limit if all(i.limit == sel[0].limit for i in sel) else -1
        lim = self._preset_menu(m, "Limit speed", cur,
                                lambda kb, items=sel: self._set_item_limit(items, kb),
                                "Speed limit for this download")
        lim.setIcon(icon("gauge", c, 16))
        torrents = [i for i in sel if i.kind == "torrent"]
        if torrents:
            cur_up = torrents[0].limit_up if all(i.limit_up == torrents[0].limit_up for i in torrents) else -1
            up = self._preset_menu(m, "Limit upload", cur_up,
                                   lambda kb, items=torrents: self._set_item_limit(items, kb, upload=True),
                                   "Upload limit for this torrent")
            up.setIcon(icon("upload", c, 16))
        m.addSeparator()
        m.addAction(icon("trash", T("danger_icon"), 16), "Delete…", self.remove_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ---- actions ----
    def _set_scheduled(self, items, on):
        for it in items:
            it.scheduled = on
            if on and it.status in ("queued",) and not it.is_alive():
                it.status = "paused"      # wait for the start time
        self.mgr.save()
        self.refresh()

    def open_torrent_files(self):
        start = self.mgr.settings.get("last_torrent_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
        self.bring_front()
        self._dialog_open = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(self, "Open torrent files", start,
                                                    "Torrent files (*.torrent);;All files (*)")
        finally:
            self._dialog_open = False
        if not paths:
            return
        self.mgr.settings["last_torrent_dir"] = os.path.dirname(paths[0])
        for path in paths:
            if not path.lower().endswith(".torrent"):
                continue
            # straight in; the "Choose files" window opens by itself for multi-file torrents
            self.mgr.add(self.mgr.new_torrent(path), start=True)
        self._select_filter("Torrents")
        self.refresh()

    def _select_filter(self, key):
        li = self._filter_items.get(key)
        if li is not None and self._filter not in ("all", key):
            self.nav.setCurrentItem(li)

    def _paste_shortcut(self):
        if clipboard_url():
            self.add_dialog({"url": clipboard_url()})
        else:
            self.add_dialog()

    def add_dialog(self, data=None):
        if data is not None and not isinstance(data, dict):
            data = None
        self.bring_front()
        self._dialog_open = True
        try:
            dlg = AddDialog(self, self.mgr, data)
            dlg.raise_()
            dlg.activateWindow()
            if dlg.exec() == QDialog.Accepted:
                item = dlg.make_item()
                item.scheduled = dlg.sched.isChecked()
                self.mgr.add(item, start=dlg.choice == "now")
                self.refresh()
        finally:
            self._dialog_open = False

    def choose_files(self, item, new=False):
        files = item.files()
        if not files:
            return
        self.bring_front()
        self._dialog_open = True
        try:
            prios = None if new else item.current_priorities()
            dlg = FilesDialog(self, item, files, prios, new=new)
            dlg.raise_()
            dlg.activateWindow()
            if dlg.exec() == QDialog.Accepted and dlg.result_priorities:
                item.apply_selection(dlg.result_priorities)
            elif new:
                self.mgr.remove(item, delete_file=True)
            self.refresh()
        finally:
            self._dialog_open = False

    def resume_selected(self):
        for it in self._selected():
            it.resume()

    def pause_selected(self):
        for it in self._selected():
            it.pause()

    def toggle_selected(self):
        for it in self._selected():
            if it.status in ("downloading", "queued"):
                it.pause()
            else:
                it.resume()

    def _double_click(self):
        sel = self._selected()
        if not sel:
            return
        if sel[0].status == "done":
            self.open_selected()
        else:
            self.toggle_selected()

    def remove_selected(self):
        items = self._selected()
        if not items:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete")
        box.setIconPixmap(pixmap("trash", T("danger_icon"), 40))
        n = len(items)
        box.setText(f"<b>Remove {n} download{'s' if n > 1 else ''}?</b>")
        box.setInformativeText("You can keep the file on disk or delete it too.")
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        only = box.addButton("Remove from list", QMessageBox.AcceptRole)
        also = box.addButton("Delete file too", QMessageBox.DestructiveRole)
        also.setObjectName("Danger")
        box.setDefaultButton(only)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (only, also):
            return
        for it in items:
            self.mgr.remove(it, delete_file=clicked is also)
        self.refresh()

    def open_selected(self):
        for it in self._selected()[:1]:
            if it.status == "done" and it.path and os.path.exists(it.path):
                open_path(it.path)

    def folder_selected(self):
        items = self._selected()
        if items:
            it = items[0]
            if it.path and os.path.exists(it.path):
                p = it.path
            elif it.path and os.path.exists(it.path + ".part"):
                p = it.path + ".part"
            else:
                os.makedirs(it.save_dir, exist_ok=True)
                p = it.save_dir
            show_in_folder(p)
        else:
            os.makedirs(self.mgr.settings["save_dir"], exist_ok=True)
            open_path(self.mgr.settings["save_dir"])

    def copy_link(self):
        items = self._selected()
        if items:
            self._ignore_clip = True
            QApplication.clipboard().setText(items[0].url)

    def settings_dialog(self, tab=None):
        if tab is not None and not isinstance(tab, str):
            tab = None
        self._dialog_open = True
        try:
            SettingsDialog(self, self.mgr, tab).exec()
            self._apply_limit_ui()
            self._apply_when_ui()
        finally:
            self._dialog_open = False

    def bring_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if self._quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(APP_NAME, "Still running in the tray and catching browser downloads.\n"
                                  "Right-click the tray icon → Quit to exit.",
                                  QSystemTrayIcon.Information, 5000)

    def quit_app(self):
        self._quitting = True
        self.timer.stop()
        self.tray.hide()
        self.mgr.shutdown()
        QApplication.quit()


def selftest(out_path):
    """Used by the automatic build to prove every part made it into the exe."""
    lines = []
    for mod in ("PySide6.QtWidgets", "PySide6.QtSvg", "requests", "yt_dlp", "libtorrent"):
        try:
            m = __import__(mod, fromlist=["x"])
            lines.append(f"OK   {mod} {getattr(m, '__version__', '')}")
        except Exception as e:
            lines.append(f"FAIL {mod}: {e}")
    lines.append(f"{'OK  ' if torrent.AVAILABLE else 'FAIL'} torrent engine")
    for name in ("app.png", "app.ico", "check.png"):
        lines.append(f"{'OK  ' if os.path.isfile(resource(name)) else 'FAIL'} asset {name}")
    lines.append(f"{'OK  ' if ffmpeg_path() else 'WARN'} ffmpeg {ffmpeg_path() or ''}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if any(l.startswith("FAIL") for l in lines) else 0


def install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # project folder when run from source


def open_browser_guide():
    """Open the 'connect your browser' page and the extension folder next to it."""
    base = install_dir()
    guide = next((p for p in (os.path.join(base, "guide.html"), os.path.join(base, "installer", "guide.html"))
                  if os.path.isfile(p)), None)
    ext = os.path.join(base, "extension")
    if os.path.isdir(ext):
        open_path(ext)
    if guide:
        open_path(guide)


def shots(out):
    """Build-time visual check: render the real windows with demo data in every theme and save PNGs."""
    os.makedirs(out, exist_ok=True)
    os.environ["APPDATA"] = tempfile.mkdtemp()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    theme.apply(app, asset_url, "aurora")
    mgr = Manager()
    mgr.settings.update(schedule_on=True, limit_on=True, limit_down=2048, after_done="shutdown")
    mgr.apply_limits()
    import torrent as tmod
    from core import FileDownload
    from video import VideoDownload

    def f(name, total, frac, status, speed=0.0, limit=0, scheduled=False):
        it = FileDownload("https://example.com/" + name, mgr.settings["save_dir"], name)
        it.name, it.total, it.status, it.speed = name, total, status, speed
        it.parts = [[0, total - 1, int(total * frac)]]
        it.resumable = True
        it.set_limit(limit)
        it.scheduled = scheduled
        mgr.items.append(it)
    t = tmod.TorrentDownload("magnet:?xt=urn:btih:abc&dn=Ubuntu", mgr.settings["save_dir"], ask_files=False)
    t.name, t.total, t._done, t.status, t.speed, t.upload, t.peers = \
        "ubuntu-24.04.1-desktop-amd64.iso", 6_114_656_256, 3_791_087_000, "downloading", 8.4e6, 4.1e5, 48
    mgr.items.append(t)
    v = VideoDownload("https://youtube.com/watch?v=x", mgr.settings["save_dir"], "1080")
    v.name, v.total, v._done, v.status, v.speed = "Project walkthrough (1080p).mp4", 412_000_000, 128_000_000, \
        "downloading", 3.1e6
    mgr.items.append(v)
    f("Setup_v2.exe", 96_000_000, 1.0, "done")
    f("Report Q3 2026.pdf", 14_000_000, 0.44, "paused", scheduled=True)
    f("Archive.zip", 2_400_000_000, 0.12, "paused", limit=512)
    f("Broken link.iso", 700_000_000, 0.05, "error")
    f("Soundtrack.mp3", 8_700_000, 0.8, "downloading", speed=1.2e6)
    f("Wallpapers_UltraHD.jpg", 284_000_000, 1.0, "done")
    import time as _t
    for k, it in enumerate(mgr.items):
        it.added = _t.time() - k * 40000

    w = MainWindow(mgr, queue.Queue())
    w.timer.stop()
    w.setMinimumSize(1360, 780)
    w.resize(1360, 780)
    w.show()
    w._update_info = {"version": "1.7", "url": "", "page": "", "notes": "", "size": 0}
    w._banner_text.setText(f"<b>EDENLOAD 1.7</b> is available — you have {features.VERSION}.")
    w.banner.show()
    w.table.selectRow(2)
    w._checked.update({mgr.items[1].id, mgr.items[3].id})
    w.table.setProperty("hoverRow", 4)

    def save(widget, name):
        for _ in range(3):
            app.processEvents()
        widget.grab().save(os.path.join(out, name + ".png"))

    for key in theme.THEMES:
        w.apply_theme(key)
        w.refresh()
        save(w, f"main_{key}")
    w.apply_theme("aurora")
    w.refresh()
    w.banner.hide()
    save(w, "main_nobanner")
    w.setMinimumSize(980, 560)
    w.resize(1100, 640)
    save(w, "main_small")
    w.setMinimumSize(1360, 780)
    w.resize(1360, 780)
    w._fill_main_menu("Downloads", w._menus["Downloads"])
    w._menus["Downloads"].popup(w.mapToGlobal(w.rect().topLeft()) + QPoint(160, 40))
    save(w._menus["Downloads"], "menu_downloads")
    w._menus["Downloads"].hide()
    cd = CleanerDialog(w, mgr)
    cd.show()
    save(cd, "dialog_cleaner")
    cd.hide()
    w.refresh()
    w.when_menu.popup(w.buttons["when_done"].mapToGlobal(w.buttons["when_done"].rect().bottomLeft()))
    save(w.when_menu, "menu_when_done")
    w.when_menu.hide()
    for key in ("aurora", "daylight"):
        w.apply_theme(key)
        dlg = SettingsDialog(w, mgr)
        dlg.theme.blockSignals(True)
        dlg.show()
        for i, name in enumerate(SettingsDialog.TABS):
            dlg.tabs.setCurrentIndex(i)
            save(dlg, f"settings_{key}_{i}_{name.lower()}")
        dlg.hide()
    w.apply_theme("aurora")
    def fake(dlg, res):
        dlg._probe_timer.stop()
        dlg._gen += 1
        dlg._probe_done((dlg._gen, res))
    a = AddDialog(w, mgr, {"url": "https://example.com/tools/EdenSetup-2.4.exe"})
    a.show()
    fake(a, {"kind": "file", "name": "EdenSetup-2.4.exe", "size": 87_400_000, "resumable": True,
             "mime": "application/octet-stream", "final_url": ""})
    save(a, "dialog_add_file")
    a.hide()
    a = AddDialog(w, mgr, {"url": "https://www.youtube.com/watch?v=abc", "type": "video"})
    a.show()
    fake(a, {"kind": "video", "name": "Product walkthrough (1080p)", "duration": 754, "site": "Youtube",
             "sizes": {"best": 912_000_000, "1080": 412_000_000, "720": 198_000_000, "480": 96_000_000,
                       "360": 52_000_000, "audio": 18_000_000}})
    a.quality.setCurrentIndex(1)
    save(a, "dialog_add_video")
    a.hide()
    a = AddDialog(w, mgr, {"url": "https://example.com/big.iso"})
    a.show()
    fake(a, {"kind": "file", "name": "big.iso", "size": 50 * 1024 ** 4, "resumable": False,
             "mime": "application/octet-stream", "final_url": ""})
    save(a, "dialog_add_nospace")
    a.hide()
    cd = CountdownDialog(w, "shutdown", "All downloads finished.")
    cd.timer.stop()
    cd.show()
    save(cd, "dialog_countdown")
    cd.hide()
    w.tray.hide()
    return 0


def unregister():
    """Run by the uninstaller: remove start-with-Windows and magnet/.torrent registration."""
    for fn in (set_startup, set_torrent_assoc):
        try:
            fn(False)
        except Exception:
            pass


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest.txt"))
    if "--shots" in sys.argv:
        i = sys.argv.index("--shots")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "shots"
        try:
            code = shots(out)
        except Exception:
            import traceback
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "error.txt"), "w", encoding="utf-8") as fh:
                fh.write(traceback.format_exc())
            code = 1
        sys.exit(code)
    if "--unregister" in sys.argv:
        unregister()
        return
    if "--init-folders" in sys.argv:          # run by the installer
        Manager().ensure_folders()
        return
    if "--guide" in sys.argv:
        open_browser_guide()
        return
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EDENLOAD.DownloadManager")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(resource("app.png")))
    theme.apply(app, asset_url)

    inbox = queue.Queue()
    incoming = args_to_payloads(sys.argv[1:])
    shared = {"capture": lambda: True}
    try:
        server = make_server(inbox, lambda: shared["capture"]())
    except OSError:
        # Already running: hand over what we were opened with (magnet link, .torrent, URL).
        try:
            import json
            for p in incoming or [None]:
                path, body = ("/add", json.dumps(p).encode()) if p else ("/show", b"{}")
                req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=body, method="POST",
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2)
        except Exception:
            QMessageBox.warning(None, APP_NAME, f"Port {PORT} is already used by another program.")
        return
    mgr = Manager()
    theme.apply(app, asset_url, mgr.settings.get("theme", "aurora"))
    mgr.ensure_folders()
    flag = os.path.join(mgr.dir, "startup.flag")      # left by the installer's "Start with Windows" box
    if os.path.isfile(flag):
        mgr.settings["startup"] = True
        mgr.save()
        try:
            os.remove(flag)
        except OSError:
            pass
    if sys.platform == "win32":
        for key, fn in (("startup", set_startup), ("torrent_assoc", set_torrent_assoc)):
            if mgr.settings.get(key):
                try:
                    fn(True)
                except Exception:
                    pass
    shared["capture"] = lambda: mgr.settings.get("capture", True)
    w = MainWindow(mgr, inbox)
    app.aboutToQuit.connect(mgr.shutdown)
    for p in incoming:
        inbox.put(p)
    if "--tray" not in sys.argv or incoming:
        w.show()
    code = app.exec()
    server.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
