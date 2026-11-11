"""EDENLOAD — the 'Dashboard' layout (glass look): stats, active download cards, recent files, preview."""
import os
import subprocess
import threading
import time
from collections import deque

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, Signal, QObject
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QPen, QPixmap,
                           QFont, QIcon)
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QToolButton,
                               QPushButton, QLineEdit, QSizePolicy, QScrollArea, QMenu, QStackedWidget,
                               QCheckBox)

import theme
from icons import icon, pixmap, CATEGORY_ICON
from core import human_size, human_time, category_of

T = theme.c
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".ts"}


def lbl(text="", name=None, wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def card(name="GCard"):
    f = QFrame()
    f.setObjectName(name)
    return f


# ---------------------------------------------------------------- small painted widgets
class Sparkline(QWidget):
    """Smooth speed wave with a glowing fill."""

    def __init__(self, height=60, samples=60):
        super().__init__()
        self.data = deque([0.0] * samples, maxlen=samples)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(height)

    def push(self, v):
        self.data.append(float(v or 0))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        vals = list(self.data)
        top = max(max(vals), 1.0)
        n = len(vals)
        pts = [QPointF(i * (w - 1) / (n - 1), h - 6 - (v / top) * (h - 14)) for i, v in enumerate(vals)]
        path = QPainterPath(pts[0])
        for a, b in zip(pts, pts[1:]):
            mx = (a.x() + b.x()) / 2
            path.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
        fill = QPainterPath(path)
        fill.lineTo(w, h)
        fill.lineTo(0, h)
        fill.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        c1 = QColor(T("acc"))
        c1.setAlpha(110)
        c2 = QColor(T("acc"))
        c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillPath(fill, g)
        glow = QColor(T("acc"))
        glow.setAlpha(60)
        p.setPen(QPen(glow, 6))
        p.drawPath(path)
        p.setPen(QPen(QColor(T("acc")), 2.2))
        p.drawPath(path)
        p.end()


class GlowBar(QWidget):
    def __init__(self):
        super().__init__()
        self.frac = 0.0
        self.paused = False
        self.setFixedHeight(10)

    def set(self, frac, paused=False):
        self.frac, self.paused = max(0.0, min(1.0, frac)), paused
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, self.width() - 2, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T("track")))
        p.drawRoundedRect(r, 3, 3)
        if self.frac > 0:
            f = QRectF(r)
            f.setWidth(max(6.0, r.width() * self.frac))
            if self.paused:
                p.setBrush(QColor(T("faint")))
            else:
                g = QLinearGradient(f.topLeft(), f.topRight())
                g.setColorAt(0, QColor(T("acc2")))
                g.setColorAt(1, QColor(T("acc")))
                p.setBrush(g)
                glow = QColor(T("acc"))
                glow.setAlpha(70)
                p.setPen(QPen(glow, 4))
            p.drawRoundedRect(f, 3, 3)
        p.end()


class Thumb(QLabel):
    """Rounded thumbnail: a picture, a video frame or a big category icon on a tinted tile."""

    def __init__(self, w, h, radius=10):
        super().__init__()
        self.setFixedSize(w, h)
        self.radius = radius
        self.pm = None
        self.ic = ("other", "#9aa3af")
        self.play = False
        self.badge = ""

    def set_item(self, pm, ic, play=False, badge=""):
        self.pm, self.ic, self.play, self.badge = pm, ic, play, badge
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(r, self.radius, self.radius)
        p.setClipPath(clip)
        if self.pm and not self.pm.isNull():
            pm = self.pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(int((self.width() - pm.width()) / 2), int((self.height() - pm.height()) / 2), pm)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(theme.mix(T("card"), self.ic[1], 0.18)))
            g.setColorAt(1, QColor(theme.mix(T("card"), self.ic[1], 0.06)))
            p.fillRect(r, g)
            s = int(min(self.width(), self.height()) * 0.5)
            p.drawPixmap(int((self.width() - s) / 2), int((self.height() - s) / 2), pixmap(self.ic[0], self.ic[1], s))
        if self.play:
            d = min(self.width(), self.height()) * 0.34
            c = r.center()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawEllipse(c, d / 2, d / 2)
            p.setBrush(QColor("#ffffff"))
            tri = QPainterPath()
            tri.moveTo(c.x() - d * 0.13, c.y() - d * 0.2)
            tri.lineTo(c.x() - d * 0.13, c.y() + d * 0.2)
            tri.lineTo(c.x() + d * 0.22, c.y())
            tri.closeSubpath()
            p.drawPath(tri)
        if self.badge:
            f = QFont(self.font())
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self.badge) + 12
            b = QRectF(self.width() - tw - 6, 6, tw, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(b, 5, 5)
            p.setPen(QColor("#ffffff"))
            p.drawText(b, Qt.AlignCenter, self.badge)
        p.end()


class Switch(QCheckBox):
    """iOS-style toggle."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, 42, 22)
        p.setPen(Qt.NoPen)
        if self.isChecked():
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, QColor(T("acc2")))
            g.setColorAt(1, QColor(T("acc")))
            p.setBrush(g)
        else:
            p.setBrush(QColor(T("track")))
        p.drawRoundedRect(r, 11, 11)
        p.setBrush(QColor("#ffffff"))
        x = 23 if self.isChecked() else 3
        p.drawEllipse(QRectF(x, 3, 18, 18))
        p.end()

    def hitButton(self, pos):
        return self.rect().contains(pos)


class GlassBackground(QWidget):
    """Window background: deep color with two soft glows."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T("bg")))
        for cx, cy, rad, alpha in ((0.78, -0.05, 0.55, 70), (0.05, 1.0, 0.45, 40)):
            g = QRadialGradient(self.width() * cx, self.height() * cy, self.width() * rad)
            c = QColor(T("acc"))
            c.setAlpha(alpha if not T("light") else alpha // 3)
            g.setColorAt(0, c)
            c2 = QColor(T("acc"))
            c2.setAlpha(0)
            g.setColorAt(1, c2)
            p.fillRect(self.rect(), g)
        p.end()


class _Relay(QObject):
    done = Signal(str)


# ---------------------------------------------------------------- thumbnails (images + video frames)
class Thumbs:
    def __init__(self, folder, ffmpeg):
        self.dir = os.path.join(folder, "thumbs")
        os.makedirs(self.dir, exist_ok=True)
        self.ffmpeg = ffmpeg
        self.cache = {}
        self.busy = set()
        self.relay = _Relay()

    def get(self, it):
        """QPixmap for a finished image/video, or None (a video frame is made in the background)."""
        path = it.path
        if not path or it.status != "done" or not os.path.isfile(path):
            return None
        if it.id in self.cache:
            return self.cache[it.id]
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXT:
            pm = QPixmap(path)
            if not pm.isNull():
                pm = pm.scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cache[it.id] = pm
            return pm
        if ext in VIDEO_EXT and self.ffmpeg:
            out = os.path.join(self.dir, it.id + ".jpg")
            if os.path.isfile(out):
                self.cache[it.id] = QPixmap(out)
                return self.cache[it.id]
            if it.id not in self.busy:
                self.busy.add(it.id)
                threading.Thread(target=self._frame, args=(it.id, path, out), daemon=True).start()
        return None

    def _frame(self, item_id, path, out):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for at in ("5", "1", "0"):
            try:
                subprocess.run([self.ffmpeg, "-y", "-ss", at, "-i", path, "-frames:v", "1", "-vf", "scale=480:-2",
                                out], capture_output=True, timeout=20, creationflags=flags)
            except Exception:
                pass
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                break
        self.relay.done.emit(item_id)

    def take(self, item_id):
        out = os.path.join(self.dir, item_id + ".jpg")
        self.busy.discard(item_id)
        if os.path.isfile(out):
            self.cache[item_id] = QPixmap(out)


# ---------------------------------------------------------------- pieces of the dashboard
class StatCard(QFrame):
    def __init__(self, ic, title, wave=False):
        super().__init__()
        self.setObjectName("GCard")
        self.ic_name = ic
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(12)
        self.ic = QLabel()
        self.ic.setFixedSize(44, 44)
        self.ic.setAlignment(Qt.AlignCenter)
        self.ic.setObjectName("StatIcon")
        h.addWidget(self.ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = lbl("0", "StatValue")
        col.addWidget(self.value)
        col.addWidget(lbl(title, "Muted"))
        h.addLayout(col)
        self.wave = None
        if wave:
            self.wave = Sparkline(48)
            h.addWidget(self.wave, 1)
        else:
            h.addStretch()
        self.retheme()

    def retheme(self):
        self.ic.setPixmap(pixmap(self.ic_name, T("acc"), 26))


class ActiveRow(QFrame):
    def __init__(self, dash, it):
        super().__init__()
        self.dash = dash
        self.item_id = it.id
        self.setObjectName("GRow")
        self.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 10, 6)
        h.setSpacing(12)
        self.thumb = Thumb(78, 46, 8)
        h.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.name = lbl("", "RowName")
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(self.name)
        sub = QHBoxLayout()
        self.size = lbl("", "Muted")
        self.pct = lbl("", "Muted")
        sub.addWidget(self.size)
        sub.addStretch()
        sub.addWidget(self.pct)
        col.addLayout(sub)
        self.bar = GlowBar()
        col.addWidget(self.bar)
        h.addLayout(col, 1)
        h.addSpacing(10)
        self.speed = lbl("", "RowMeta")
        self.speed.setFixedWidth(110)
        h.addWidget(self.speed)
        self.eta = lbl("", "RowMeta")
        self.eta.setFixedWidth(92)
        h.addWidget(self.eta)
        self.pp = QToolButton()
        self.pp.setObjectName("RoundBtn")
        self.pp.setFixedSize(34, 34)
        self.pp.clicked.connect(self._toggle)
        h.addWidget(self.pp)
        self.x = QToolButton()
        self.x.setObjectName("RoundBtn")
        self.x.setFixedSize(34, 34)
        self.x.setToolTip("Cancel and remove")
        self.x.clicked.connect(lambda: dash.win.remove_items([dash.win.mgr.get(self.item_id)]))
        h.addWidget(self.x)

    def mousePressEvent(self, e):
        self.dash.select(self.item_id)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        it = self.dash.win.mgr.get(self.item_id)
        if it and it.status == "done":
            self.dash.win.open_item(it)

    def _toggle(self):
        it = self.dash.win.mgr.get(self.item_id)
        if not it:
            return
        if it.status in ("downloading", "queued"):
            it.pause()
        else:
            it.resume()
        self.dash.refresh()

    def update_from(self, it, selected):
        cat = self.dash.win.category(it)
        self.thumb.set_item(None, CATEGORY_ICON.get(cat, CATEGORY_ICON["Other"]))
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(it.name or it.url, Qt.ElideMiddle, max(120, self.name.width())))
        self.name.setToolTip(it.name or it.url)
        frac = min(it.done, it.total) / it.total if it.total else 0.0
        self.size.setText(f"{human_size(it.done)} / {human_size(it.total)}" if it.total else human_size(it.done))
        paused = it.status not in ("downloading", "queued", "pausing")
        state = {"paused": "Paused", "error": "Failed", "queued": "Queued"}.get(it.status, "")
        self.pct.setText((state + "  ·  " if state else "") + (f"{frac * 100:.0f}%" if it.total else ""))
        self.bar.set(frac, paused)
        run = it.status == "downloading"
        self.speed.setText(f"↓  {human_size(it.speed)}/s" if run and it.speed else "↓  —")
        eta = (it.total - it.done) / it.speed if run and it.speed and it.total else None
        self.eta.setText("◷  " + (human_time(eta) if eta is not None else "—"))
        self.pp.setIcon(icon("play" if paused else "pause", T("text"), 16))
        self.pp.setToolTip("Resume" if paused else "Pause")
        self.x.setIcon(icon("close", T("text"), 16))
        self.setProperty("sel", selected)
        self.style().unpolish(self)
        self.style().polish(self)


class RecentTile(QFrame):
    def __init__(self, dash, it):
        super().__init__()
        self.dash = dash
        self.item_id = it.id
        self.setObjectName("GRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(176)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        self.thumb = Thumb(160, 78, 8)
        v.addWidget(self.thumb)
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = lbl("", "RowName")
        self.size = lbl("", "Muted")
        col.addWidget(self.name)
        col.addWidget(self.size)
        row.addLayout(col, 1)
        self.ok = QLabel()
        row.addWidget(self.ok, 0, Qt.AlignBottom)
        v.addLayout(row)

    def mousePressEvent(self, e):
        self.dash.select(self.item_id)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        it = self.dash.win.mgr.get(self.item_id)
        if it:
            self.dash.win.open_item(it)

    def update_from(self, it, selected):
        cat = self.dash.win.category(it)
        pm = self.dash.thumbs.get(it)
        ext = os.path.splitext(it.path or it.name or "")[1].lower()
        self.thumb.set_item(pm, CATEGORY_ICON.get(cat, CATEGORY_ICON["Other"]), play=ext in VIDEO_EXT)
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(it.name or "", Qt.ElideMiddle, 130))
        self.name.setToolTip(it.name)
        self.size.setText(human_size(it.total) if it.total else "")
        self.ok.setPixmap(pixmap("done", T("ok"), 20))
        self.setProperty("sel", selected)
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------- the dashboard
NAV = [("home", "Home", "home"), ("downloads", "Downloads", "active"), ("queue", "Queue", "all"),
       ("library", "Library", "folder"), ("browser", "Browser", "globe"), ("schedule", "Schedule", "calendar"),
       ("tools", "Tools", "broom"), ("themes", "Themes", "palette"), ("settings", "Settings", "gear")]


class Dashboard(GlassBackground):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.mgr = win.mgr
        self.selected = None
        self.rows = {}
        self.tiles = {}
        self._tick = 0
        from video import ffmpeg_path
        from manager import data_dir
        self.thumbs = Thumbs(data_dir(), ffmpeg_path())
        self.thumbs.relay.done.connect(self._thumb_ready)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())
        body = QHBoxLayout()
        body.setContentsMargins(16, 6, 16, 10)
        body.setSpacing(16)
        body.addWidget(self._nav())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._home())
        self.list_page = QWidget()
        lp = QVBoxLayout(self.list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(10)
        top = QHBoxLayout()
        self.list_title = lbl("Downloads", "PageTitle")
        top.addWidget(self.list_title)
        top.addStretch()
        lp.addLayout(top)
        self.list_holder = card("GCard")
        self.list_holder_lay = QVBoxLayout(self.list_holder)
        self.list_holder_lay.setContentsMargins(6, 6, 6, 6)
        lp.addWidget(self.list_holder, 1)
        self.pages.addWidget(self.list_page)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        outer.addWidget(self._bottom())
        self.retheme()

    # ---------- building
    def _header(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(22, 14, 22, 8)
        h.setSpacing(12)
        self.logo = QLabel()
        h.addWidget(self.logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QHBoxLayout()
        t.setSpacing(8)
        t.addWidget(lbl("EDENLOAD", "BrandBig"))
        t.addStretch()
        col.addLayout(t)
        col.addWidget(lbl("Fast  •  Smart  •  All Media", "Muted"))
        h.addLayout(col)
        h.addStretch()
        return w

    def _nav(self):
        c = card("GCard")
        c.setFixedWidth(250)
        v = QVBoxLayout(c)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(2)
        self.nav_btns = {}
        for key, text, ic in NAV:
            b = QToolButton()
            b.setObjectName("NavBtn")
            b.setText("   " + text)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIconSize(QSize(22, 22))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("ic", ic)
            b.clicked.connect(lambda _=False, k=key: self._nav_click(k))
            v.addWidget(b)
            self.nav_btns[key] = b
        self.badge = lbl("", "NavBadge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(26, 22)
        self.badge.setParent(self.nav_btns["downloads"])
        self.badge.move(186, 9)
        v.addStretch()
        net = card("GInner")
        nv = QVBoxLayout(net)
        nv.setContentsMargins(14, 12, 14, 8)
        top = QHBoxLayout()
        self.net_ic = QLabel()
        top.addWidget(self.net_ic)
        top.addWidget(lbl("Network speed", "CardTitle"))
        top.addStretch()
        nv.addLayout(top)
        sp = QHBoxLayout()
        self.net_down = lbl("↓ 0 B/s", "NetDown")
        self.net_up = lbl("↑ 0 B/s", "NetUp")
        sp.addWidget(self.net_down)
        sp.addStretch()
        sp.addWidget(self.net_up)
        nv.addLayout(sp)
        self.net_wave = Sparkline(52)
        nv.addWidget(self.net_wave)
        v.addWidget(net)
        self.nav_btns["home"].setChecked(True)
        return c

    def _home(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(14)

        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(lbl("Welcome back 👋", "PageTitle"))
        col.addWidget(lbl("Manage your downloads quickly and easily", "Muted"))
        top.addLayout(col)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search downloads or library…")
        self.search.setFixedWidth(380)
        self.search.setClearButtonEnabled(True)
        self.search_act = None
        self.search.returnPressed.connect(self._search)
        top.addWidget(self.search)
        self.filter_btn = QToolButton()
        self.filter_btn.setObjectName("SquareBtn")
        self.filter_btn.setFixedSize(42, 42)
        self.filter_btn.setToolTip("Show the full list")
        self.filter_btn.clicked.connect(lambda: self.show_list("all", "All downloads"))
        top.addWidget(self.filter_btn)
        top.addSpacing(10)
        add = QPushButton("  Add link")
        add.setObjectName("Gradient")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(lambda: self.win.add_dialog())
        self.add_btn = add
        top.addWidget(add)
        g.addLayout(top, 0, 0, 1, 2)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.st_active = StatCard("active", "Active downloads")
        self.st_done = StatCard("done", "Completed")
        self.st_queue = StatCard("clock", "In queue")
        self.st_speed = StatCard("gauge", "Current speed", wave=True)
        for w, s in ((self.st_active, 1), (self.st_done, 1), (self.st_queue, 1), (self.st_speed, 2)):
            stats.addWidget(w, s)
        g.addLayout(stats, 1, 0, 1, 2)

        # active downloads
        act = card("GCard")
        av = QVBoxLayout(act)
        av.setContentsMargins(14, 12, 14, 14)
        av.setSpacing(8)
        ah = QHBoxLayout()
        self.act_ic = QLabel()
        ah.addWidget(self.act_ic)
        self.act_title = lbl("Active downloads", "SectionTitle")
        ah.addWidget(self.act_title)
        ah.addStretch()
        self.pause_all = QToolButton()
        self.pause_all.setObjectName("PillBtn")
        self.pause_all.setText("Pause all")
        self.pause_all.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.pause_all.clicked.connect(lambda: (self.mgr.pause_all(), self.refresh()))
        ah.addWidget(self.pause_all)
        av.addLayout(ah)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.rows_lay = QVBoxLayout(inner)
        self.rows_lay.setContentsMargins(0, 0, 4, 0)
        self.rows_lay.setSpacing(8)
        self.rows_lay.addStretch()
        sc.setWidget(inner)
        av.addWidget(sc, 1)
        self.act_empty = lbl("Nothing downloading right now. Click a download link in your browser, "
                             "or “Add link”.", "Muted", True)
        av.addWidget(self.act_empty)
        g.addWidget(act, 2, 0)

        # recently completed
        rec = card("GCard")
        rec.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        rv = QVBoxLayout(rec)
        rv.setContentsMargins(14, 12, 14, 14)
        rh = QHBoxLayout()
        self.rec_ic = QLabel()
        rh.addWidget(self.rec_ic)
        self.rec_title = lbl("Recently completed", "SectionTitle")
        rh.addWidget(self.rec_title)
        rh.addStretch()
        va = QToolButton()
        va.setObjectName("LinkBtn")
        va.setText("View all  →")
        va.clicked.connect(lambda: self.show_list("done", "Library"))
        rh.addWidget(va)
        rv.addLayout(rh)
        self.tiles_lay = QHBoxLayout()
        self.tiles_lay.setSpacing(10)
        self.tiles_lay.addStretch()
        rv.addLayout(self.tiles_lay)
        self.rec_empty = lbl("Finished downloads show up here.", "Muted")
        rv.addWidget(self.rec_empty)
        g.addWidget(rec, 3, 0)

        # preview + details
        side = card("GCard")
        side.setFixedWidth(340)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 12, 14, 14)
        sv.setSpacing(10)
        ph = QHBoxLayout()
        ph.addWidget(lbl("Preview", "SectionTitle"))
        ph.addStretch()
        self.open_btn = QToolButton()
        self.open_btn.setObjectName("Flat")
        self.open_btn.setToolTip("Open file")
        self.open_btn.clicked.connect(self._open_selected)
        fb = QToolButton()
        fb.setObjectName("Flat")
        fb.setToolTip("Show in folder")
        fb.clicked.connect(self._show_folder)
        self.folder_btn = fb
        ph.addWidget(fb)
        ph.addWidget(self.open_btn)
        sv.addLayout(ph)
        self.preview = Thumb(310, 150, 12)
        self.preview.mouseDoubleClickEvent = lambda e: self._open_selected()
        sv.addWidget(self.preview, 0, Qt.AlignHCenter)
        det = card("GInner")
        dv = QVBoxLayout(det)
        dv.setContentsMargins(12, 8, 12, 8)
        dv.setSpacing(3)
        dh = QHBoxLayout()
        dh.addWidget(lbl("File details", "CardTitle"))
        dh.addStretch()
        dv.addLayout(dh)
        self.details = {}
        for key in ("Name", "Type", "Size", "Downloaded", "Speed", "Time left", "Save to"):
            row = QHBoxLayout()
            k = lbl(key, "Muted")
            k.setFixedWidth(84)
            row.addWidget(k)
            val = lbl("—", "DetailVal")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setMinimumHeight(20)
            k.setMinimumHeight(20)
            row.addWidget(val, 1)
            dv.addLayout(row)
            self.details[key] = val
        dv.addStretch()
        sv.addWidget(det, 1)
        g.addWidget(side, 2, 1, 2, 1)
        g.setRowStretch(2, 1)
        g.setRowStretch(3, 0)
        g.setColumnStretch(0, 1)
        return page

    def _bottom(self):
        bar = QFrame()
        bar.setObjectName("GBottom")
        h = QHBoxLayout(bar)
        h.setContentsMargins(22, 10, 22, 12)
        h.setSpacing(12)
        self.dir_btn = QToolButton()
        self.dir_btn.setObjectName("DirBtn")
        self.dir_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.dir_btn.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.dir_btn)
        m.addAction("Open download folder", lambda: self.win.open_download_folder())
        m.addAction("Change download folder…", lambda: self.win.settings_dialog("Downloads"))
        m.addAction("Disk Cleaner…", lambda: self.win.disk_cleaner())
        self.dir_btn.setMenu(m)
        h.addWidget(self.dir_btn)
        h.addStretch()
        self.space_lbl = lbl("", "Muted")
        h.addWidget(self.space_lbl)
        self.space_bar = GlowBar()
        self.space_bar.setFixedWidth(360)
        h.addWidget(self.space_bar)
        self.open_dir = QToolButton()
        self.open_dir.setObjectName("SquareBtn")
        self.open_dir.setFixedSize(36, 32)
        self.open_dir.setToolTip("Open download folder")
        self.open_dir.clicked.connect(lambda: self.win.open_download_folder())
        h.addWidget(self.open_dir)
        h.addStretch()
        self.turbo = Switch()
        self.turbo.setToolTip("Turbo: 16 connections per download and no speed limit")
        self.turbo.setChecked(bool(self.mgr.settings.get("turbo")))
        self.turbo.toggled.connect(self._turbo)
        h.addWidget(self.turbo)
        h.addWidget(lbl("Turbo mode", "CardTitle"))
        return bar

    # ---------- behaviour
    def _nav_click(self, key):
        w = self.win
        pages = {"downloads": ("unfinished", "Downloads"), "queue": ("scheduled", "Queue"),
                 "library": ("done", "Library")}
        if key == "home":
            self._page_key = "home"
            self.pages.setCurrentIndex(0)
        elif key in pages:
            self.show_list(*pages[key])
            return
        # the other buttons open something; keep the current page highlighted
        for k, b in self.nav_btns.items():
            b.setChecked(k == getattr(self, "_page_key", "home"))
        if key == "browser":
            w.open_browser_guide()
        elif key == "schedule":
            w.settings_dialog("Schedule")
        elif key in ("tools", "themes"):
            m = QMenu(self)
            if key == "tools":
                m.addAction("Speed limits…", w.speed_dialog)
                m.addAction("Open torrent file…", w.open_torrent_files)
                m.addAction("Disk Cleaner…", w.disk_cleaner)
                m.addAction("Connect browser…", w.open_browser_guide)
                m.addSeparator()
                m.addAction("Switch to Classic layout", lambda: (w.apply_layout("classic"), w.mgr.save()))
            else:
                w.fill_theme_menu(m)
            b = self.nav_btns[key]
            m.exec(b.mapToGlobal(b.rect().topRight()))
        elif key == "settings":
            w.settings_dialog()

    def show_list(self, key, title):
        self._page_key = {"unfinished": "downloads", "scheduled": "queue", "done": "library"}.get(key, "downloads")
        self.list_title.setText(title)
        self.win.embed_list(self.list_holder_lay)
        self.win.set_filter(key)
        self.pages.setCurrentIndex(1)
        for k, b in self.nav_btns.items():
            b.setChecked(k == self._page_key)

    def _search(self):
        text = self.search.text().strip()
        self.show_list("all", f"Search: {text}" if text else "All downloads")
        self.win.search.setText(text)

    def _turbo(self, on):
        s = self.mgr.settings
        s["turbo"] = on
        if on:
            s["limit_on"] = False
        self.win._limits_changed()
        self.mgr.save()

    def select(self, item_id):
        self.selected = item_id
        self.refresh()

    def _open_selected(self):
        it = self.mgr.get(self.selected) if self.selected else None
        if it:
            self.win.open_item(it)

    def _show_folder(self):
        it = self.mgr.get(self.selected) if self.selected else None
        if it:
            self.win.show_item_folder(it)

    def _thumb_ready(self, item_id):
        self.thumbs.take(item_id)
        self.refresh()

    def retheme(self):
        self.logo.setPixmap(QPixmap(self.win.app_icon_file()).scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for b in self.nav_btns.values():
            b.setIcon(icon(b.property("ic"), T("text"), 22, 1.7))
        self.net_ic.setPixmap(pixmap("wifi", T("acc"), 22))
        for st in (self.st_active, self.st_done, self.st_queue, self.st_speed):
            st.retheme()
        self.act_ic.setPixmap(pixmap("active", T("text"), 22))
        self.rec_ic.setPixmap(pixmap("done", T("acc"), 22))
        self.pause_all.setIcon(icon("pause", T("text"), 14))
        self.filter_btn.setIcon(icon("settings", T("text"), 20))
        self.add_btn.setIcon(icon("link", T("on_acc"), 18, 2.1))
        self.open_btn.setIcon(icon("open", T("text"), 18))
        self.folder_btn.setIcon(icon("folder", T("text"), 18))
        self.dir_btn.setIcon(icon("folder", T("text"), 20))
        self.open_dir.setIcon(icon("folder", T("text"), 18))
        if self.search_act:
            self.search.removeAction(self.search_act)
        self.search_act = self.search.addAction(icon("search", T("muted"), 18), QLineEdit.LeadingPosition)
        self.update()
        self.refresh(force=True)

    def tick(self):
        self._tick += 1
        if self._tick % 2 == 0:        # once a second
            down = sum(i.speed for i in self.mgr.items if i.status == "downloading")
            up = sum(getattr(i, "upload", 0.0) or 0.0 for i in self.mgr.items)
            self.net_wave.push(down)
            self.st_speed.wave.push(down)
            self.net_down.setText(f"↓ {human_size(down)}/s" if down else "↓ 0 B/s")
            self.net_up.setText(f"↑ {human_size(up)}/s" if up else "↑ 0 B/s")
        if self.isVisible():
            self.refresh()

    def refresh(self, force=False):
        mgr = self.mgr
        items = mgr.items
        active = [i for i in items if i.status in ("downloading", "queued", "pausing", "paused", "error")]
        active.sort(key=lambda i: ({"downloading": 0, "pausing": 1, "queued": 2, "paused": 3, "error": 4}[i.status],
                                   -(i.added or 0)))
        done = sorted([i for i in items if i.status == "done"], key=lambda i: -(i.added or 0))
        running = [i for i in items if i.status in ("downloading", "queued", "pausing")]
        queued = [i for i in items if i.status != "done" and (getattr(i, "scheduled", False) or i.status == "queued")]
        speed = sum(i.speed for i in items if i.status == "downloading")
        self.st_active.value.setText(str(len(running)))
        self.st_done.value.setText(str(len(done)))
        self.st_queue.value.setText(str(len(queued)))
        self.st_speed.value.setText(f"{human_size(speed)}/s" if speed else "0 B/s")
        self.badge.setText(str(len(running)))
        self.badge.setVisible(bool(running))
        self.act_title.setText(f"Active downloads  ({len(active)})")
        self.rec_title.setText(f"Recently completed  ({len(done)})")
        self.pause_all.setEnabled(bool(running))

        if self.selected is None or not mgr.get(self.selected):
            self.selected = (active[0].id if active else done[0].id if done else None)

        # active rows (rebuild only when the set changes)
        show = active[:30]
        ids = [i.id for i in show]
        if force or ids != list(self.rows.keys()):
            for r in self.rows.values():
                r.setParent(None)
                r.deleteLater()
            self.rows = {}
            for it in show:
                row = ActiveRow(self, it)
                self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
                self.rows[it.id] = row
        for it in show:
            self.rows[it.id].update_from(it, it.id == self.selected)
        self.act_empty.setVisible(not show)

        recent = done[:5]
        rids = [i.id for i in recent]
        if force or rids != list(self.tiles.keys()):
            for t in self.tiles.values():
                t.setParent(None)
                t.deleteLater()
            self.tiles = {}
            for it in recent:
                tile = RecentTile(self, it)
                self.tiles_lay.insertWidget(self.tiles_lay.count() - 1, tile)
                self.tiles[it.id] = tile
        for it in recent:
            self.tiles[it.id].update_from(it, it.id == self.selected)
        self.rec_empty.setVisible(not recent)

        self._details(mgr.get(self.selected) if self.selected else None)
        self._space()

    def _details(self, it):
        d = self.details
        if not it:
            for v in d.values():
                v.setText("—")
            self.preview.set_item(None, ("cloud_dl", T("acc")))
            return
        cat = self.win.category(it)
        ic = CATEGORY_ICON.get(cat, CATEGORY_ICON["Other"])
        pm = self.thumbs.get(it)
        ext = os.path.splitext(it.path or it.name or "")[1].lower()
        badge = ""
        if ext in VIDEO_EXT:
            badge = ext.lstrip(".").upper()
        self.preview.set_item(pm, ic, play=(it.status == "done" and ext in VIDEO_EXT), badge=badge)
        fm = d["Name"].fontMetrics()
        d["Name"].setText(fm.elidedText(it.name or it.url, Qt.ElideMiddle, 185))
        d["Name"].setToolTip(it.name or it.url)
        d["Type"].setText(f"{cat}" + (f"  ({ext.lstrip('.').upper()})" if ext else ""))
        d["Size"].setText(human_size(it.total) if it.total else "—")
        frac = min(it.done, it.total) / it.total if it.total else (1.0 if it.status == "done" else 0)
        d["Downloaded"].setText(f"{human_size(it.done)}  ({frac * 100:.0f}%)" if it.total else human_size(it.done))
        run = it.status == "downloading"
        d["Speed"].setText(f"{human_size(it.speed)}/s" if run and it.speed else "—")
        eta = (it.total - it.done) / it.speed if run and it.speed and it.total else None
        d["Time left"].setText(human_time(eta) if eta is not None else ("Done" if it.status == "done" else "—"))
        where = os.path.dirname(it.path) if it.path else it.save_dir
        d["Save to"].setText(fm.elidedText(where, Qt.ElideMiddle, 185))
        d["Save to"].setToolTip(where)
        self.open_btn.setEnabled(it.status == "done")

    def _space(self):
        folder = self.mgr.settings["save_dir"]
        self.dir_btn.setText("  " + folder)
        p = folder
        while p and not os.path.exists(p):
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
        try:
            import shutil
            u = shutil.disk_usage(p)
            self.space_lbl.setText(f"Free space:  {human_size(u.free)} of {human_size(u.total)}")
            self.space_bar.set(u.used / u.total if u.total else 0)
        except OSError:
            self.space_lbl.setText("")
