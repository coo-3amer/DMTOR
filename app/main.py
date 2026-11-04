"""DMTOR - main window."""
import os
import re
import sys
import queue
import subprocess
import urllib.request

from PySide6.QtCore import Qt, QTimer, QSize, QRectF
from PySide6.QtGui import QIcon, QFont, QPainter, QColor, QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QToolBar, QToolButton,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QComboBox,
    QLabel, QFileDialog, QSpinBox, QCheckBox, QMessageBox, QSystemTrayIcon, QMenu,
    QHeaderView, QAbstractItemView, QWidget, QFrame, QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

import theme
from icons import icon, pixmap, CATEGORY_ICON
from core import human_size, human_time, category_of, fmt_rate
from manager import Manager
from server import make_server, PORT
from video import QUALITIES, ffmpeg_path
import torrent
from torrent import is_torrent_source

APP_NAME = "DMTOR"
LEGACY = "EdenDM"   # name of earlier versions; cleaned up from the registry
VIDEO_SITES = re.compile(
    r"(youtube\.com|youtu\.be|facebook\.com|fb\.watch|instagram\.com|tiktok\.com|twitter\.com|"
    r"(^|//|\.)x\.com|vimeo\.com|dailymotion\.com|twitch\.tv|reddit\.com|soundcloud\.com)", re.I)


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.normpath(os.path.join(base, "assets", name))


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
            winreg.SetValueEx(key, "DMTOR", 0, winreg.REG_SZ, launch_cmd("--tray"))
        else:
            try:
                winreg.DeleteValue(key, "DMTOR")
            except FileNotFoundError:
                pass
        try:
            winreg.DeleteValue(key, LEGACY)
        except FileNotFoundError:
            pass
    finally:
        winreg.CloseKey(key)


def set_torrent_assoc(enabled):
    """Open magnet: links and .torrent files with DMTOR (per-user, no admin needed)."""
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
        drop(LEGACY + ".torrent")
        put("DMTOR.torrent", {"": "Torrent file"})
        put("DMTOR.torrent\\DefaultIcon", {"": exe_icon})
        put("DMTOR.torrent\\shell\\open\\command", {"": cmd})
        put(".torrent", {"": "DMTOR.torrent"})
        put(".torrent\\OpenWithProgids", {"DMTOR.torrent": ""})
    else:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + "magnet\\shell\\open\\command")
            current = winreg.QueryValueEx(k, "")[0]
            winreg.CloseKey(k)
        except OSError:
            current = ""
        if "DMTOR" in current or LEGACY in current or sys.executable in current:
            drop("magnet")
        drop("DMTOR.torrent")
        drop(LEGACY + ".torrent")
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + ".torrent", 0, winreg.KEY_ALL_ACCESS)
            if winreg.QueryValueEx(k, "")[0] in ("DMTOR.torrent", LEGACY + ".torrent"):
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
class ProgressDelegate(QStyledItemDelegate):
    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        frac, status, text = idx.data(Qt.UserRole) or (0.0, "queued", "")
        color = QColor(theme.STATUS.get(status, ("", theme.MUTED))[1])
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(12, 0, -12, 0)
        tw = 58
        bar = QRectF(r.left(), r.center().y() - 3, max(10, r.width() - tw - 10), 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#262b33"))
        p.drawRoundedRect(bar, 3, 3)
        if frac > 0:
            fill = QRectF(bar)
            fill.setWidth(max(6.0, bar.width() * min(frac, 1.0)))
            p.setBrush(color)
            p.drawRoundedRect(fill, 3, 3)
        p.setPen(QColor("#c9ced6"))
        p.drawText(QRectF(r.right() - tw, r.top(), tw, r.height()), Qt.AlignVCenter | Qt.AlignRight, text)
        p.restore()


class StatusDelegate(QStyledItemDelegate):
    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        status = idx.data(Qt.UserRole) or "queued"
        text, color = theme.STATUS.get(status, (status, theme.MUTED))
        extra = idx.data(Qt.UserRole + 1)
        if extra:
            text = f"{text} {extra}"
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(12, 0, -8, 0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(r.left(), r.center().y() - 3.5, 7, 7))
        p.setPen(QColor(color))
        p.drawText(QRectF(r.left() + 15, r.top(), r.width() - 15, r.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, text)
        p.restore()


# ---------------------------------------------------------------- dialogs
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
        paste.setIcon(icon("link", "#d8dce2", 18))
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
        pick.setIcon(icon("magnet", "#2dd4bf", 18))
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
        browse.setIcon(icon("folder", "#d8dce2", 18))
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
        form.addRow(label("Type", "Muted"), self.kind)
        self.q_label = label("Quality", "Muted")
        form.addRow(self.q_label, self.quality)
        self.n_label = label("File name", "Muted")
        form.addRow(self.n_label, self.name)
        form.addRow(label("Save to", "Muted"), frow)
        size = data.get("size") or 0
        if size:
            form.addRow(label("Size", "Muted"), QLabel(human_size(size)))
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
        self._sync()

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
                    node.setIcon(0, icon("folder", "#e8c26a", 18))
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


class SettingsDialog(QDialog):
    def __init__(self, parent, mgr):
        super().__init__(parent)
        self.mgr = mgr
        s = mgr.settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        self.folder = QLineEdit(s["save_dir"])
        browse = QToolButton()
        browse.setObjectName("Icon")
        browse.setIcon(icon("folder", "#d8dce2", 18))
        browse.setIconSize(QSize(18, 18))
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.folder)
        row.addWidget(browse)
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 10)
        self.parallel.setValue(s["max_parallel"])
        self.segments = QSpinBox()
        self.segments.setRange(1, 32)
        self.segments.setValue(s["segments"])
        self.categorize = QCheckBox("Sort files into folders (Video, Music, Programs, Documents…)")
        self.categorize.setChecked(s["categorize"])
        self.startup = QCheckBox("Start with Windows (runs in the tray)")
        self.startup.setChecked(s.get("startup", False))
        self.startup.setEnabled(sys.platform == "win32")
        self.ask_files = QCheckBox("Let me choose which files to download")
        self.ask_files.setChecked(s.get("torrent_ask_files", True))
        self.seed = QCheckBox("Keep seeding torrents after they finish")
        self.seed.setChecked(s.get("seed_after", False))
        self.assoc = QCheckBox("Open magnet links and .torrent files with DMTOR")
        self.assoc.setChecked(s.get("torrent_assoc", False))
        self.assoc.setEnabled(sys.platform == "win32")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow(label("Download folder", "Muted"), row)
        form.addRow(label("Simultaneous downloads", "Muted"), self.parallel)
        form.addRow(label("Connections per file", "Muted"), self.segments)
        speed_btn = QPushButton("  Speed limits…")
        speed_btn.setIcon(icon("gauge", "#d8dce2", 16))
        speed_btn.clicked.connect(lambda: SpeedDialog(self, self.mgr).exec())
        srow = QHBoxLayout()
        srow.addWidget(speed_btn)
        srow.addStretch()
        form.addRow(label("Speed", "Muted"), srow)
        guide_btn = QPushButton("  Connect browser…")
        guide_btn.setIcon(icon("link", "#d8dce2", 16))
        guide_btn.clicked.connect(open_browser_guide)
        grow = QHBoxLayout()
        grow.addWidget(guide_btn)
        grow.addStretch()
        form.addRow(label("Chrome / Edge", "Muted"), grow)

        ok = primary(QPushButton("Save"))
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
        lay.addWidget(label("Settings", "Title"))
        lay.addSpacing(14)
        lay.addLayout(form)
        lay.addSpacing(10)
        lay.addWidget(self.categorize)
        lay.addWidget(self.startup)
        lay.addSpacing(8)
        lay.addWidget(label("TORRENTS", "Muted"))
        lay.addWidget(self.ask_files)
        lay.addWidget(self.seed)
        lay.addWidget(self.assoc)
        lay.addSpacing(18)
        lay.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _save(self):
        s = self.mgr.settings
        s["save_dir"] = self.folder.text().strip() or s["save_dir"]
        s["max_parallel"] = self.parallel.value()
        s["segments"] = self.segments.value()
        s["categorize"] = self.categorize.isChecked()
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
        self.mgr.save()
        self.accept()


# ---------------------------------------------------------------- main window
COLS = ["Name", "Size", "Progress", "Speed", "Time left", "Status"]
FILTERS = [
    ("all", "All downloads", "all"),
    ("active", "Downloading", "active"),
    ("done", "Completed", "done"),
    ("paused", "Paused & failed", "paused"),
    None,
    ("Torrents", "Torrents", "magnet"),
    ("Video", "Video", "video"),
    ("Music", "Music", "music"),
    ("Programs", "Programs", "programs"),
    ("Documents", "Documents", "documents"),
    ("Compressed", "Archives", "compressed"),
    ("Images", "Images", "images"),
    ("Other", "Other", "other"),
]


def matches(it, key):
    if key == "all":
        return True
    if key == "active":
        return it.status in ("downloading", "queued", "pausing")
    if key == "done":
        return it.status == "done"
    if key == "paused":
        return it.status in ("paused", "error")
    return item_category(it) == key


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
        self._notified = {i.id for i in mgr.items if i.status == "done"}

        self.setWindowTitle(APP_NAME)
        app_icon = QIcon(resource("app.png"))
        self.setWindowIcon(app_icon)
        self.resize(1180, 640)
        self.setMinimumSize(900, 480)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_toolbar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_table())
        self.stack.addWidget(self._build_empty())
        v.addWidget(self.stack)
        h.addWidget(right, 1)
        self.setCentralWidget(root)
        self.setAcceptDrops(True)

        # keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_dialog)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_torrent_files)
        QShortcut(QKeySequence.Paste, self, activated=self._paste_shortcut)
        QShortcut(QKeySequence.Delete, self, activated=self.remove_selected)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_selected)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.toggle_capture)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_limit)

        # tray
        self.tray = QSystemTrayIcon(app_icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction(icon("all", "#d8dce2", 16), "Open DMTOR", self.bring_front)
        menu.addAction(icon("add", "#d8dce2", 16), "Add URL…", self.add_dialog)
        menu.addAction(icon("magnet", "#2dd4bf", 16), "Open torrent file…", self.open_torrent_files)
        menu.addAction(icon("link", "#d8dce2", 16), "Connect browser…", open_browser_guide)
        menu.addSeparator()
        self.tray_capture = menu.addAction("Catch browser downloads")
        self.tray_capture.setCheckable(True)
        self.tray_capture.triggered.connect(lambda *_: self.toggle_capture())
        self.tray_limit = menu.addAction("Limit speed")
        self.tray_limit.setCheckable(True)
        self.tray_limit.triggered.connect(lambda *_: self.toggle_limit())
        menu.addSeparator()
        menu.addAction(icon("resume_all", "#d8dce2", 16), "Resume all", self.mgr.resume_all)
        menu.addAction(icon("pause_all", "#d8dce2", 16), "Pause all", self.mgr.pause_all)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.bring_front() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.app_icon = app_icon
        self._apply_capture_ui()
        self._apply_limit_ui()
        self.refresh()
        self._update_buttons()

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
        b.setText(f"Max {fmt_rate(down)}" if on and down else ("Limited" if on else "Unlimited"))
        b.setIcon(icon("gauge", "#7fb2ff" if on else "#d8dce2", 18))
        if on:
            tip = (f"Speed limit ON\nDownloads: {fmt_rate(down)}\nTorrents: ↓ {fmt_rate(t_down)}"
                   f"   ↑ {fmt_rate(t_up)}\nClick to turn off (Ctrl+L) · arrow for options")
        else:
            tip = "No speed limit — click to turn it on (Ctrl+L) · arrow for options"
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
        m.addAction(icon("gauge", "#d8dce2", 16), "Speed limits…", self.speed_dialog)

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
        b = self.buttons["capture"]
        b.setText("Catching on" if on else "Catching off")
        b.setIcon(icon("catch" if on else "catch_off", "#19a974" if on else "#f2a93b", 18))
        b.setToolTip(("Catching downloads from the browser — click to turn off" if on else
                      "Not catching — the browser downloads files itself. Click to turn on")
                     + "  (Ctrl+Shift+C)")
        b.setProperty("off", not on)
        b.style().unpolish(b)
        b.style().polish(b)
        self.tray_capture.setChecked(on)
        self.tray.setIcon(self.app_icon if on else QIcon(resource("app_off.png")))

    # ---- building ----
    def _build_sidebar(self):
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(230)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        brand = QWidget()
        bh = QHBoxLayout(brand)
        bh.setContentsMargins(18, 20, 18, 16)
        bh.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(resource("app.png")).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        bh.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("DMTOR", "BrandName"))
        names.addWidget(label("Download Manager", "BrandSub"))
        bh.addLayout(names)
        bh.addStretch()
        v.addWidget(brand)

        self.filters = QListWidget()
        self.filters.setObjectName("Filters")
        self.filters.setIconSize(QSize(18, 18))
        self.filters.setFocusPolicy(Qt.NoFocus)
        self._filter_items = {}
        for f in FILTERS:
            if f is None:
                sep = QListWidgetItem("CATEGORIES")
                sep.setFlags(Qt.NoItemFlags)
                self.filters.addItem(sep)
                continue
            key, text, ic = f
            color = CATEGORY_ICON[key][1] if key in CATEGORY_ICON else "#b8bec8"
            it = QListWidgetItem(icon(ic, color, 18), text)
            it.setData(Qt.UserRole, key)
            it.setData(Qt.UserRole + 1, text)
            self.filters.addItem(it)
            self._filter_items[key] = it
        self.filters.setCurrentItem(self._filter_items["all"])
        self.filters.currentItemChanged.connect(self._filter_changed)
        v.addWidget(self.filters, 1)

        self.footer = label("", "SideFooter")
        v.addWidget(self.footer)
        return panel

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setObjectName("Top")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.buttons = {}

        def btn(key, text, ic, slot, tip, prim=False):
            b = QToolButton()
            b.setText(text)
            b.setIcon(icon(ic, "#ffffff" if prim else "#d8dce2", 18, 2.1 if prim else 1.9))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda checked=False, s=slot: s())
            if prim:
                b.setObjectName("Primary")
            tb.addWidget(b)
            self.buttons[key] = b
            return b

        def sep():
            f = QFrame()
            f.setObjectName("Sep")
            f.setFixedSize(1, 22)
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(8, 0, 8, 0)
            l.addWidget(f)
            tb.addWidget(w)

        btn("add", "Add URL", "add", self.add_dialog, "Add a new download (Ctrl+N)", prim=True)
        ot = btn("open_torrent", "Open torrent", "magnet", self.open_torrent_files,
                 "Open .torrent files from your computer (Ctrl+O)")
        ot.setIcon(icon("magnet", "#2dd4bf", 18))
        btn("resume", "Resume", "play", self.resume_selected, "Resume selected (Space)")
        btn("pause", "Pause", "pause", self.pause_selected, "Pause selected (Space)")
        btn("delete", "Delete", "trash", self.remove_selected, "Remove selected (Del)")
        sep()
        btn("resume_all", "Resume all", "resume_all", self.mgr.resume_all, "Resume every download")
        btn("pause_all", "Pause all", "pause_all", self.mgr.pause_all, "Pause every download")
        sep()
        btn("open", "Open", "open", self.open_selected, "Open the downloaded file")
        btn("folder", "Show in folder", "folder", self.folder_selected, "Show in folder")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        sp = btn("speed", "Speed", "gauge", self.toggle_limit, "")
        sp.setObjectName("Speed")
        sp.setPopupMode(QToolButton.MenuButtonPopup)
        self.speed_menu = QMenu(sp)
        self.speed_menu.aboutToShow.connect(lambda: self._fill_speed_menu(self.speed_menu))
        sp.setMenu(self.speed_menu)
        cap = btn("capture", "Catching on", "catch", self.toggle_capture,
                  "Catch downloads from the browser — click to turn off (Ctrl+Shift+C)")
        cap.setObjectName("Capture")
        btn("settings", "Settings", "settings", self.settings_dialog, "Settings")
        return tb

    def _build_table(self):
        t = QTableWidget(0, len(COLS))
        t.setObjectName("List")
        t.setHorizontalHeaderLabels(COLS)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setShowGrid(False)
        t.setWordWrap(False)
        t.setAlternatingRowColors(True)
        t.setIconSize(QSize(20, 20))
        t.setFocusPolicy(Qt.NoFocus)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(46)
        hh = t.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 95), (2, 230), (3, 105), (4, 90), (5, 150)):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            t.setColumnWidth(c, w)
        t.setItemDelegateForColumn(2, ProgressDelegate(t))
        t.setItemDelegateForColumn(5, StatusDelegate(t))
        t.doubleClicked.connect(lambda *_: self._double_click())
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._row_menu)
        t.itemSelectionChanged.connect(self._update_buttons)
        self.table = t
        return t

    def _build_empty(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch()
        art = QLabel()
        art.setPixmap(pixmap("active", "#3a414c", 72))
        art.setAlignment(Qt.AlignCenter)
        v.addWidget(art)
        v.addSpacing(10)
        self.empty_title = label("No downloads yet", "EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty_title)
        self.empty_text = label("Download anything in Chrome or Edge and it lands here.\n"
                                "Or press Ctrl+V to paste a link, or drop a .torrent file here.", "Muted")
        self.empty_text.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty_text)
        v.addSpacing(16)
        row = QHBoxLayout()
        row.addStretch()
        b = primary(QPushButton("  Add URL"))
        b.setIcon(icon("add", "#ffffff", 18, 2.1))
        b.clicked.connect(lambda: self.add_dialog())
        row.addWidget(b)
        b2 = QPushButton("  Open torrent file")
        b2.setIcon(icon("magnet", "#2dd4bf", 18))
        b2.setCursor(Qt.PointingHandCursor)
        b2.clicked.connect(lambda: self.open_torrent_files())
        row.addWidget(b2)
        row.addStretch()
        v.addLayout(row)
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
        return [i for i in self.mgr.items if matches(i, self._filter)]

    def refresh(self):
        items = self._visible_items()
        ids = [i.id for i in items]
        t = self.table
        if ids != self._row_ids:
            selected = set(self._selected_ids())
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
            ic_name, ic_color = CATEGORY_ICON.get(cat, CATEGORY_ICON["Other"])
            name = t.item(r, 0)
            name.setText(it.name or it.url)
            name.setIcon(icon(ic_name, ic_color, 20))
            name.setToolTip(f"{it.name}\n{it.url}")
            t.item(r, 1).setText(human_size(total) if total else "—")
            if total:
                frac = min(done, total) / total
                text = f"{100 * frac:.1f}%" if frac < 1 else "100%"
            elif it.status == "done":
                frac, text = 1.0, "100%"
            else:
                frac, text = 0.0, (human_size(done) if done else "")
            t.item(r, 2).setData(Qt.UserRole, (frac, it.status, text))
            running = it.status == "downloading"
            spd = f"{human_size(it.speed)}/s" if running and it.speed else ""
            if it.kind == "torrent" and it.upload:
                spd = (spd + "  " if spd else "") + f"↑ {human_size(it.upload)}/s"
            sp_item = t.item(r, 3)
            sp_item.setText(spd)
            lim_up = getattr(it, "limit_up", 0)
            if it.limit or lim_up:
                sp_item.setIcon(icon("gauge", "#7fb2ff", 14))
                tip = []
                if it.limit:
                    tip.append(f"Limited to {fmt_rate(it.limit)}")
                if lim_up:
                    tip.append(f"Upload limited to {fmt_rate(lim_up)}")
                sp_item.setToolTip("\n".join(tip))
            else:
                sp_item.setIcon(QIcon())
                sp_item.setToolTip("")
            eta = (total - done) / it.speed if running and it.speed and total else None
            t.item(r, 4).setText(human_time(eta) if eta is not None else "")
            st = t.item(r, 5)
            st.setData(Qt.UserRole, it.status)
            restart = (it.status == "paused" and it.kind == "file"
                       and not getattr(it, "resumable", True) and done)
            extra = "· restarts" if restart else ""
            if it.kind == "torrent":
                if it.status == "downloading" and it.awaiting_files:
                    extra = "· choose files"
                elif it.status == "downloading":
                    extra = {"metadata": "· getting info", "checking": "· checking"}.get(
                        it.phase, f"· {it.peers} peers")
                elif it.status == "done" and it.seeding:
                    extra = "· seeding"
            st.setData(Qt.UserRole + 1, extra)
            st.setToolTip(it.error or ("This server doesn't support resume, so it will start over."
                                       if restart else ""))

        # empty state
        if items:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)
            if self.mgr.items:
                self.empty_title.setText("Nothing here")
                self.empty_text.setText("No downloads match this view.")
            else:
                self.empty_title.setText("No downloads yet")
                self.empty_text.setText("Download anything in Chrome or Edge and it lands here.\n"
                                        "Or press Ctrl+V to paste a link, or drop a .torrent file here.")

        # sidebar counts + footer
        for key, li in self._filter_items.items():
            n = sum(1 for i in self.mgr.items if matches(i, key))
            base = li.data(Qt.UserRole + 1)
            li.setText(f"{base}    {n}" if n else base)
        active = [i for i in self.mgr.items if i.status == "downloading"]
        speed = sum(i.speed for i in active)
        if active:
            self.footer.setText(f"↓  {human_size(speed)}/s   ·   {len(active)} active")
            self.tray.setToolTip(f"{APP_NAME}\n{len(active)} downloading · {human_size(speed)}/s")
        else:
            self.footer.setText(f"Idle   ·   {len(self.mgr.items)} in list")
            self.tray.setToolTip(APP_NAME)
        down, t_down, t_up = self.mgr.effective_limits()
        if self.mgr.settings.get("limit_on"):
            parts = []
            if down:
                parts.append(f"{fmt_rate(down)}")
            if t_down or t_up:
                parts.append(f"torrent ↓{fmt_rate(t_down)} ↑{fmt_rate(t_up)}")
            self.footer.setText(self.footer.text() + "\nSpeed limit: " + (" · ".join(parts) or "on"))
        if not self.mgr.settings.get("capture", True):
            self.footer.setText(self.footer.text() + "\nBrowser catching is off")
        self._update_buttons()

    def _filter_changed(self, cur, _prev):
        if cur is not None and cur.data(Qt.UserRole):
            self._filter = cur.data(Qt.UserRole)
            self.refresh()

    # ---- selection helpers ----
    def _selected_ids(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._row_ids[r] for r in rows if r < len(self._row_ids)]

    def _selected(self):
        return [it for it in (self.mgr.get(i) for i in self._selected_ids()) if it]

    def _update_buttons(self):
        sel = self._selected()
        b = self.buttons
        b["resume"].setEnabled(any(i.status in ("paused", "error", "pausing") for i in sel))
        b["pause"].setEnabled(any(i.status in ("downloading", "queued") for i in sel))
        b["delete"].setEnabled(bool(sel))
        b["open"].setEnabled(any(i.status == "done" for i in sel))
        b["resume_all"].setEnabled(any(i.status in ("paused", "error") for i in self.mgr.items))
        b["pause_all"].setEnabled(any(i.status in ("downloading", "queued") for i in self.mgr.items))

    def _row_menu(self, pos):
        sel = self._selected()
        if not sel:
            return
        m = QMenu(self)
        c = "#d8dce2"
        m.addAction(icon("play", c, 16), "Resume", self.resume_selected)
        m.addAction(icon("pause", c, 16), "Pause", self.pause_selected)
        m.addSeparator()
        m.addAction(icon("open", c, 16), "Open file", self.open_selected)
        m.addAction(icon("folder", c, 16), "Show in folder", self.folder_selected)
        m.addAction(icon("link", c, 16), "Copy link", self.copy_link)
        t = sel[0]
        if len(sel) == 1 and t.kind == "torrent" and t.has_metadata():
            m.addAction(icon("magnet", "#2dd4bf", 16), "Choose files…",
                        lambda: self.choose_files(t, new=t.awaiting_files))
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
        m.addAction(icon("trash", "#ef8f89", 16), "Delete…", self.remove_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ---- actions ----
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
            self.filters.setCurrentItem(li)

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
                self.mgr.add(dlg.make_item(), start=dlg.choice == "now")
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
        box.setIconPixmap(pixmap("trash", "#ef8f89", 40))
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
            QApplication.clipboard().setText(items[0].url)

    def settings_dialog(self):
        self._dialog_open = True
        try:
            SettingsDialog(self, self.mgr).exec()
            self._apply_limit_ui()
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
    if "--unregister" in sys.argv:
        unregister()
        return
    if "--guide" in sys.argv:
        open_browser_guide()
        return
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DMTOR.DownloadManager")
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
