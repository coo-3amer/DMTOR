"""MZ-DManager Lite — a small download manager for Windows 7 and newer (files only)."""
import os
import sys
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse, unquote

import core
import probe
import updater
from core import human_size, human_time, fmt_rate, category_of
from engine import Manager
from server import make_server
from version import VERSION, APP_NAME, PORT

# ---------------------------------------------------------------- look
C = {
    "bg": "#0f1117", "panel": "#161922", "panel2": "#1c2030", "line": "#262b3a", "text": "#e7e9ef",
    "muted": "#8d94a6", "faint": "#596074", "acc": "#a855f7", "acc_hi": "#b977f9", "acc2": "#2dd4bf",
    "ok": "#34d399", "warn": "#f5b544", "bad": "#f87171", "sel": "#2a2442", "btn": "#202434", "btn_hi": "#2a2f43",
    "gold": "#d4af37",
}
CAT_COLOR = {"Video": "#f0784f", "Music": "#ec6aa0", "Documents": "#4f9cf0", "Programs": "#a78bfa",
             "Compressed": "#e0a030", "Images": "#3fbf8f", "Other": "#8d94a6", "Torrents": "#2dd4bf"}
FONT = ("Segoe UI", 9)
FONT_B = ("Segoe UI", 9, "bold")
FONT_T = ("Segoe UI", 13, "bold")
STATUS_TEXT = {"downloading": "Downloading", "queued": "Waiting", "pausing": "Stopping…", "paused": "Stopped",
               "done": "Completed", "error": "Failed"}
FILTERS = [("all", "All"), ("active", "Downloading"), ("done", "Completed"), ("paused", "Stopped"),
           ("failed", "Failed")]


def resource(*p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *p)


def app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def matches(it, key):
    if key == "all":
        return True
    if key == "active":
        return it.status in ("downloading", "queued", "pausing")
    if key == "done":
        return it.status == "done"
    if key == "paused":
        return it.status == "paused"
    if key == "failed":
        return it.status == "error"
    return True


def open_path(p):
    try:
        os.startfile(p)
    except Exception:
        pass


def show_in_folder(p):
    if p and os.path.exists(p):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
    elif p:
        open_path(os.path.dirname(p))


def set_startup(on):
    if sys.platform != "win32":
        return
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --minimized')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def get_startup():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def open_guide():
    g = os.path.join(app_dir(), "guide.html")
    open_path(g if os.path.isfile(g) else os.path.join(app_dir(), "extension"))


# ---------------------------------------------------------------- small widgets
class Btn(tk.Label):
    """Flat button with hover; kind = 'acc' | 'soft' | 'danger' | 'ghost'."""

    def __init__(self, parent, text, cmd, kind="soft", padx=12, pady=6, tip=None):
        self.kind = kind
        self.cmd = cmd
        self.enabled = True
        bg, fg = self._colors()
        super().__init__(parent, text=text, bg=bg, fg=fg, font=FONT_B if kind == "acc" else FONT,
                         padx=padx, pady=pady, cursor="hand2")
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: self.enabled and self.cmd())
        if tip:
            Tip(self, tip)

    def _colors(self, hover=False):
        if self.kind == "acc":
            return (C["acc_hi"] if hover else C["acc"]), "#ffffff"
        if self.kind == "ghost":
            return (C["btn"] if hover else C["panel"]), C["text"]
        bg = C["btn_hi"] if hover else C["btn"]
        return bg, (C["bad"] if self.kind == "danger" else C["text"])

    def _hover(self, on):
        if not self.enabled:
            return
        bg, fg = self._colors(on)
        self.configure(bg=bg, fg=fg)

    def set_enabled(self, on):
        if on == self.enabled:
            return
        self.enabled = on
        bg, fg = self._colors()
        self.configure(fg=fg if on else C["faint"], cursor="hand2" if on else "arrow", bg=bg)


class Tip:
    def __init__(self, w, text):
        self.w, self.text, self.top = w, text, None
        w.bind("<Enter>", self.show, add="+")
        w.bind("<Leave>", self.hide, add="+")

    def show(self, e=None):
        if self.top:
            return
        x = self.w.winfo_rootx() + 6
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.top = t = tk.Toplevel(self.w)
        t.wm_overrideredirect(True)
        t.wm_geometry(f"+{x}+{y}")
        tk.Label(t, text=self.text, bg=C["panel2"], fg=C["text"], font=FONT, padx=8, pady=4,
                 highlightthickness=1, highlightbackground=C["line"]).pack()

    def hide(self, e=None):
        if self.top:
            self.top.destroy()
            self.top = None


def bar_image(cache, pct, color, w=64, h=8):
    """A small rounded progress bar (PhotoImage), cached per percent and colour."""
    pct = max(0, min(100, int(pct)))
    key = (pct, color)
    if key in cache:
        return cache[key]
    img = tk.PhotoImage(width=w + 6, height=h + 4)
    fill = int(w * pct / 100)
    rows = []
    for y in range(h + 4):
        row = []
        for x in range(w + 6):
            if y < 2 or y >= h + 2 or x < 3 or x >= w + 3:
                row.append(C["bg"])
                continue
            xx = x - 3
            yy = y - 2
            corner = (xx in (0, w - 1)) and (yy in (0, h - 1))
            if corner:
                row.append(C["bg"])
            elif xx < fill:
                row.append(color)
            else:
                row.append(C["line"])
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    cache[key] = img
    return img


def style_dialog(win, title):
    win.title(title)
    win.configure(bg=C["bg"])
    try:
        win.iconbitmap(resource("assets", "app.ico"))
    except tk.TclError:
        pass
    win.resizable(False, False)


def lbl(parent, text, muted=False, bold=False, size=9, wrap=0, color=None):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color or (C["muted"] if muted else C["text"]),
                    font=("Segoe UI", size, "bold" if bold else "normal"), justify="left", anchor="w",
                    wraplength=wrap)


def entry(parent, var, width=50):
    return tk.Entry(parent, textvariable=var, width=width, bg=C["panel2"], fg=C["text"], insertbackground=C["text"],
                    relief="flat", font=FONT, highlightthickness=1, highlightbackground=C["line"],
                    highlightcolor=C["acc"])


def check(parent, text, var):
    return tk.Checkbutton(parent, text=text, variable=var, bg=parent["bg"], fg=C["text"], selectcolor=C["panel2"],
                          activebackground=parent["bg"], activeforeground=C["text"], font=FONT, anchor="w",
                          highlightthickness=0, bd=0)


def center(win, parent):
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_rooty() + max(30, (parent.winfo_height() - win.winfo_height()) // 3)
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


# ---------------------------------------------------------------- Add dialog
class AddDialog(tk.Toplevel):
    def __init__(self, app, payload=None):
        super().__init__(app.root)
        self.app, self.mgr = app, app.mgr
        payload = payload or {}
        style_dialog(self, "New download")
        self.transient(app.root)
        f = tk.Frame(self, bg=C["bg"], padx=22, pady=18)
        f.pack(fill="both", expand=True)
        lbl(f, "New download", bold=True, size=13).grid(row=0, column=0, columnspan=3, sticky="w")
        lbl(f, "Paste a link to a file.", muted=True).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        self.url = tk.StringVar(value=payload.get("url", "") or self._clip())
        self.name = tk.StringVar(value=payload.get("filename", ""))
        self.folder = tk.StringVar(value=self.mgr.settings["save_dir"])
        self.headers = {}
        if payload.get("cookies"):
            self.headers["Cookie"] = payload["cookies"]
        if payload.get("referrer"):
            self.headers["Referer"] = payload["referrer"]
        if payload.get("userAgent"):
            self.headers["User-Agent"] = payload["userAgent"]
        self.hint_size = int(payload.get("size") or 0)

        for r, (text, var) in enumerate((("Link", self.url), ("File name", self.name), ("Save to", self.folder)), 2):
            lbl(f, text, muted=True).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=5)
            e = entry(f, var, 58)
            e.grid(row=r, column=1, sticky="we", pady=5, ipady=5)
            if text == "Link":
                self.url_entry = e
            if text == "Save to":
                Btn(f, "Browse…", self._browse, padx=10, pady=5).grid(row=r, column=2, padx=(8, 0))

        self.info = tk.Frame(f, bg=C["panel"], padx=14, pady=10, highlightthickness=1,
                             highlightbackground=C["line"])
        self.info.grid(row=5, column=0, columnspan=3, sticky="we", pady=(12, 4))
        self.info_name = lbl(self.info, "", bold=True)
        self.info_name.configure(bg=C["panel"])
        self.info_name.pack(anchor="w")
        self.info_text = lbl(self.info, "", muted=True, wrap=470)
        self.info_text.configure(bg=C["panel"])
        self.info_text.pack(anchor="w")

        row = tk.Frame(f, bg=C["bg"])
        row.grid(row=6, column=0, columnspan=3, sticky="we", pady=(14, 0))
        Btn(row, "Download now", lambda: self._ok(True), kind="acc", padx=16).pack(side="left")
        Btn(row, "Download later", lambda: self._ok(False)).pack(side="left", padx=8)
        Btn(row, "Cancel", self.destroy).pack(side="left")

        self.bind("<Return>", lambda e: self._ok(True))
        self.bind("<Escape>", lambda e: self.destroy())
        self.url.trace_add("write", lambda *a: self._schedule_probe())
        self._gen = 0
        self._after = None
        self._probe()
        center(self, app.root)
        self.grab_set()
        self.url_entry.focus_set()

    def _clip(self):
        try:
            t = self.app.root.clipboard_get().strip()
            return t if t.startswith(("http://", "https://")) and " " not in t else ""
        except tk.TclError:
            return ""

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.folder.get() or self.mgr.settings["save_dir"],
                                    title="Choose download folder")
        if d:
            self.folder.set(os.path.normpath(d))
            self._show(self._last)

    def _schedule_probe(self):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(600, self._probe)

    _last = None

    def _probe(self):
        url = self.url.get().strip()
        self._gen += 1
        gen = self._gen
        if not url.startswith(("http://", "https://")):
            self._last = None
            self.info_name.configure(text="")
            self.info_text.configure(text="Paste a link that starts with http:// or https://")
            return
        self.info_name.configure(text=self.name.get() or os.path.basename(unquote(urlparse(url).path)) or url)
        self.info_text.configure(text="Checking size…")

        def work():
            try:
                res = probe.probe_file(url, self.headers)
            except Exception as e:
                res = {"error": str(e)[:200]}
            self.app.call(lambda: self.winfo_exists() and gen == self._gen and self._show(res))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, info):
        if info is None:
            return
        self._last = info
        folder = self.folder.get().strip() or self.mgr.settings["save_dir"]
        free = probe.free_space(folder)
        if "error" in info:
            self.info_text.configure(text="Couldn't check this link: " + info["error"], fg=C["warn"])
            return
        name = self.name.get().strip() or info.get("name") or ""
        size = info.get("size") or self.hint_size
        parts = [human_size(size) if size else "Unknown size",
                 "Pause & resume: yes" if info.get("resumable") else "Pause & resume: no"]
        if free is not None:
            parts.append(f"{human_size(free)} free on {probe.drive_name(folder)}")
        dest = core.resolve_folder(folder, category_of(name or "x"))
        parts.append("Saves to " + dest)
        color = C["muted"]
        if size and free is not None and size > free:
            parts.append("Not enough space — choose another folder.")
            color = C["bad"]
        if info.get("page"):
            parts.append("This link opens a web page, not a file.")
            color = C["warn"]
        self.info_name.configure(text=name or self.url.get())
        self.info_text.configure(text="   ·   ".join(parts), fg=color)

    def _ok(self, start):
        url = self.url.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning(APP_NAME, "Paste a link that starts with http:// or https://", parent=self)
            return
        folder = self.folder.get().strip()
        default = core._same(folder, self.mgr.settings["save_dir"]) or not folder
        it = self.mgr.new_file(url, self.name.get().strip(), self.headers, None if default else folder)
        if not default:
            it.categorize = False           # a folder you picked gets the file only, no sub-folders
        self.mgr.add(it, start)
        self.app.refresh()
        self.destroy()


# ---------------------------------------------------------------- Settings
class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app, self.mgr = app, app.mgr
        s = self.mgr.settings
        style_dialog(self, "Settings")
        self.transient(app.root)
        f = tk.Frame(self, bg=C["bg"], padx=22, pady=18)
        f.pack(fill="both", expand=True)
        lbl(f, "Settings", bold=True, size=13).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.folder = tk.StringVar(value=s["save_dir"])
        self.sort = tk.BooleanVar(value=s.get("categorize", True))
        self.parallel = tk.IntVar(value=s.get("max_parallel", 3))
        self.segments = tk.IntVar(value=s.get("segments", 8))
        self.limit_on = tk.BooleanVar(value=s.get("limit_on", False))
        self.limit = tk.IntVar(value=s.get("limit_down", 1024))
        self.startup = tk.BooleanVar(value=get_startup())
        self.capture = tk.BooleanVar(value=s.get("capture", True))
        self.auto_update = tk.BooleanVar(value=s.get("auto_update", True))

        r = 1
        lbl(f, "Download folder", muted=True).grid(row=r, column=0, sticky="w", pady=5)
        entry(f, self.folder, 44).grid(row=r, column=1, sticky="we", ipady=5)
        Btn(f, "Browse…", self._browse, padx=10, pady=5).grid(row=r, column=2, padx=(8, 0))
        r += 1
        check(f, "Sort into Music, Videos, Programs, Documents and Others", self.sort).grid(
            row=r, column=1, columnspan=2, sticky="w")
        r += 1

        def spin(var, lo, hi):
            return tk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=6, bg=C["panel2"], fg=C["text"],
                              buttonbackground=C["btn"], relief="flat", font=FONT, insertbackground=C["text"],
                              highlightthickness=1, highlightbackground=C["line"])
        lbl(f, "Downloads at once", muted=True).grid(row=r, column=0, sticky="w", pady=(10, 5))
        spin(self.parallel, 1, 10).grid(row=r, column=1, sticky="w", pady=(10, 5), ipady=3)
        r += 1
        lbl(f, "Connections per file", muted=True).grid(row=r, column=0, sticky="w", pady=5)
        spin(self.segments, 1, 16).grid(row=r, column=1, sticky="w", pady=5, ipady=3)
        r += 1
        lbl(f, "Speed limit", muted=True).grid(row=r, column=0, sticky="w", pady=5)
        lim = tk.Frame(f, bg=C["bg"])
        lim.grid(row=r, column=1, columnspan=2, sticky="w")
        check(lim, "Limit to", self.limit_on).pack(side="left")
        tk.Spinbox(lim, from_=16, to=1024000, increment=64, textvariable=self.limit, width=8, bg=C["panel2"],
                   fg=C["text"], buttonbackground=C["btn"], relief="flat", font=FONT, insertbackground=C["text"],
                   highlightthickness=1, highlightbackground=C["line"]).pack(side="left", padx=6, ipady=3)
        lbl(lim, "KB/s", muted=True).pack(side="left")
        r += 1
        tk.Frame(f, bg=C["line"], height=1).grid(row=r, column=0, columnspan=3, sticky="we", pady=12)
        r += 1
        check(f, "Catch downloads from Chrome / Edge", self.capture).grid(row=r, column=0, columnspan=2, sticky="w")
        Btn(f, "Connect browser…", open_guide, padx=10, pady=4).grid(row=r, column=2, sticky="e")
        r += 1
        check(f, "Start with Windows", self.startup).grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
        r += 1
        check(f, "Check for updates automatically", self.auto_update).grid(row=r, column=0, columnspan=2,
                                                                           sticky="w", pady=(4, 0))
        Btn(f, "Check now", lambda: app.check_updates(manual=True), padx=10, pady=4).grid(row=r, column=2,
                                                                                         sticky="e", pady=(4, 0))
        r += 1
        lbl(f, f"{APP_NAME} {VERSION} — Windows 7 edition. Closing the window keeps it next to the clock.", muted=True).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(12, 0))
        r += 1
        row = tk.Frame(f, bg=C["bg"])
        row.grid(row=r, column=0, columnspan=3, sticky="e", pady=(16, 0))
        Btn(row, "Cancel", self.destroy).pack(side="right")
        Btn(row, "Save", self._save, kind="acc", padx=18).pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, app.root)
        self.grab_set()

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.folder.get(), title="Choose download folder")
        if d:
            self.folder.set(os.path.normpath(d))

    def _save(self):
        s = self.mgr.settings
        try:
            s["max_parallel"] = max(1, min(10, int(self.parallel.get())))
            s["segments"] = max(1, min(16, int(self.segments.get())))
            s["limit_down"] = max(16, int(self.limit.get()))
        except (tk.TclError, ValueError):
            messagebox.showwarning(APP_NAME, "Please type numbers only.", parent=self)
            return
        s["save_dir"] = self.folder.get().strip() or s["save_dir"]
        s["categorize"] = self.sort.get()
        s["limit_on"] = self.limit_on.get()
        s["capture"] = self.capture.get()
        s["auto_update"] = self.auto_update.get()
        if self.startup.get() != get_startup():
            try:
                set_startup(self.startup.get())
                s["startup"] = self.startup.get()
            except OSError as e:
                messagebox.showwarning(APP_NAME, f"Couldn't change start with Windows:\n{e}", parent=self)
        self.mgr.apply_limits()
        self.mgr.apply_folders()
        self.mgr.ensure_folders()
        self.mgr.save()
        self.app.refresh()
        self.app.tray.refresh_menu()
        self.destroy()


# ---------------------------------------------------------------- yes/no with options
class Confirm(tk.Toplevel):
    def __init__(self, app, title, text, options=(), ok_text="Delete", danger=True):
        super().__init__(app.root)
        style_dialog(self, APP_NAME)
        self.transient(app.root)
        self.result = None
        f = tk.Frame(self, bg=C["bg"], padx=22, pady=18)
        f.pack(fill="both", expand=True)
        lbl(f, title, bold=True, size=12).pack(anchor="w")
        if text:
            lbl(f, text, muted=True, wrap=380).pack(anchor="w", pady=(4, 10))
        self.vars = []
        for o in options:
            v = tk.BooleanVar(value=False)
            check(f, o, v).pack(anchor="w")
            self.vars.append(v)
        row = tk.Frame(f, bg=C["bg"])
        row.pack(anchor="e", pady=(16, 0))
        Btn(row, "Cancel", self.destroy).pack(side="right")
        b = Btn(row, ok_text, self._ok, kind="danger" if danger else "acc", padx=16)
        b.pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, app.root)
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = [v.get() for v in self.vars]
        self.destroy()


# ---------------------------------------------------------------- tray icon (next to the clock)
class Tray:
    """Icon next to the clock: keeps the app running (and catching browser downloads) when the window is closed."""

    def __init__(self, app):
        self.app = app
        self.icon = None
        try:
            import pystray
            from PIL import Image
        except Exception:
            return
        img = Image.open(resource("assets", "app.png"))
        M = pystray.MenuItem
        menu = pystray.Menu(
            M("Open MZ-DManager Lite", lambda: app.call(app.show), default=True),
            M("Add download…", lambda: app.call(lambda: (app.show(), app.add_dialog()))),
            pystray.Menu.SEPARATOR,
            M("Catch browser downloads", lambda: app.call(app.toggle_capture),
              checked=lambda item: app.mgr.settings.get("capture", True)),
            M("Limit speed", lambda: app.call(app.toggle_limit),
              checked=lambda item: bool(app.mgr.settings.get("limit_on"))),
            M("Resume all", lambda: app.call(lambda: app._all("resume", everything=True))),
            M("Stop all", lambda: app.call(lambda: app._all("stop", everything=True))),
            pystray.Menu.SEPARATOR,
            M("Exit", lambda: app.call(app.quit)))
        self.icon = pystray.Icon("MZ-DManager Lite", img, APP_NAME, menu)
        self.icon.run_detached()

    @property
    def ok(self):
        return self.icon is not None

    def tip(self, text):
        if self.icon and getattr(self, "_tip", None) != text:
            self._tip = text
            try:
                self.icon.title = text[:120]
            except Exception:
                pass

    def notify(self, text, title=APP_NAME):
        if self.icon:
            try:
                self.icon.notify(text, title)
            except Exception:
                pass

    def refresh_menu(self):
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


# ---------------------------------------------------------------- main window
class App:
    def __init__(self, root, mgr, inbox, minimized=False):
        self.root, self.mgr, self.inbox = root, mgr, inbox
        self._calls = queue.Queue()      # work finished in background threads, run on the UI thread
        self._filter = "all"
        self._bars = {}
        self._rows = []
        root.title(APP_NAME)
        root.configure(bg=C["bg"])
        try:
            root.iconbitmap(default=resource("assets", "app.ico"))
        except tk.TclError:
            pass
        geo = mgr.settings.get("geometry") or "1040x620"
        root.geometry(geo)
        root.minsize(760, 420)
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Control-a>", lambda e: self.select_all())
        root.bind("<Control-n>", lambda e: self.add_dialog())
        root.bind("<Delete>", lambda e: self.delete_selected())
        self.tray = Tray(self)
        self._told_tray = False
        self._prev = {i.id: i.status for i in mgr.items}
        if minimized:
            if self.tray.ok:
                root.withdraw()
            else:
                root.iconify()
        self.refresh()
        self._loop()
        self._pump()
        if mgr.settings.get("auto_update", True) and time.time() - mgr.settings.get("last_update_check", 0) > 6 * 3600:
            root.after(4000, self.check_updates)

    # ---- look ----
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("Treeview", background=C["bg"], fieldbackground=C["bg"], foreground=C["text"], rowheight=30,
                     borderwidth=0, font=FONT)
        st.configure("Treeview.Heading", background=C["panel"], foreground=C["muted"], relief="flat",
                     font=("Segoe UI", 8, "bold"), borderwidth=0, padding=(6, 5))
        st.map("Treeview.Heading", background=[("active", C["panel2"])])
        st.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", "#ffffff")])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Vertical.TScrollbar", background=C["btn"], troughcolor=C["bg"], borderwidth=0,
                     arrowcolor=C["muted"], gripcount=0)

    def _build(self):
        r = self.root
        top = tk.Frame(r, bg=C["panel"], padx=14, pady=10)
        top.pack(fill="x")
        try:
            self._logo = tk.PhotoImage(file=resource("assets", "logo24.png"))
            tk.Label(top, image=self._logo, bg=C["panel"]).pack(side="left", padx=(0, 8))
        except tk.TclError:
            pass
        tk.Label(top, text="MZ-DManager", bg=C["panel"], fg=C["text"], font=FONT_T).pack(side="left")
        tk.Label(top, text=" Lite", bg=C["panel"], fg=C["gold"], font=FONT_T).pack(side="left", padx=(0, 18))
        Btn(top, "＋  Add download", self.add_dialog, kind="acc", padx=14, pady=7,
            tip="Add a link (Ctrl+N)").pack(side="left")
        self.b_resume_all = Btn(top, "▶  Resume all", lambda: self._all("resume"), tip="Resume everything in this list")
        self.b_resume_all.pack(side="left", padx=(14, 4))
        self.b_stop_all = Btn(top, "■  Stop all", lambda: self._all("stop"), tip="Stop everything in this list")
        self.b_stop_all.pack(side="left", padx=4)
        self.b_delete_all = Btn(top, "✕  Delete all", self.delete_all, kind="danger",
                                tip="Delete all downloads in this list")
        self.b_delete_all.pack(side="left", padx=4)
        Btn(top, "⚙  Settings", lambda: SettingsDialog(self), kind="ghost").pack(side="right")
        self.search = tk.StringVar()
        se = entry(top, self.search, 22)
        se.pack(side="right", padx=10, ipady=5)
        se.insert(0, "")
        self.search.trace_add("write", lambda *a: self.refresh(force=True))
        tk.Label(top, text="Search", bg=C["panel"], fg=C["muted"], font=FONT).pack(side="right")

        bar = tk.Frame(r, bg=C["bg"], padx=14, pady=8)
        bar.pack(fill="x")
        self.sel_all = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Select all", variable=self.sel_all, command=self._sel_all_clicked, bg=C["bg"],
                       fg=C["text"], selectcolor=C["panel2"], activebackground=C["bg"], activeforeground=C["text"],
                       font=FONT, highlightthickness=0, bd=0).pack(side="left", padx=(0, 16))
        self.tabs = {}
        for key, text in FILTERS:
            t = tk.Label(bar, text=text, bg=C["bg"], fg=C["muted"], font=FONT, padx=12, pady=5, cursor="hand2")
            t.pack(side="left", padx=2)
            t.bind("<Button-1>", lambda e, k=key: self.set_filter(k))
            self.tabs[key] = (t, text)
        self.sel_info = tk.Label(bar, text="", bg=C["bg"], fg=C["muted"], font=FONT)
        self.sel_info.pack(side="right")

        # selected-items actions
        self.actions = tk.Frame(bar, bg=C["bg"])
        self.actions.pack(side="right", padx=8)
        self.b_resume = Btn(self.actions, "▶ Resume", self.resume_selected, padx=9, pady=4)
        self.b_stop = Btn(self.actions, "■ Stop", self.stop_selected, padx=9, pady=4)
        self.b_folder = Btn(self.actions, "Folder", self.folder_selected, padx=9, pady=4)
        self.b_delete = Btn(self.actions, "Delete", self.delete_selected, kind="danger", padx=9, pady=4)
        for b in (self.b_resume, self.b_stop, self.b_folder, self.b_delete):
            b.pack(side="left", padx=2)

        body = tk.Frame(r, bg=C["bg"], padx=10)
        body.pack(fill="both", expand=True)
        cols = ("size", "progress", "speed", "left", "status")
        t = ttk.Treeview(body, columns=cols, selectmode="extended")
        t.heading("#0", text="  NAME", anchor="w")
        for c, text, w, anchor in (("size", "SIZE", 90, "e"), ("progress", "PROGRESS", 80, "e"),
                                   ("speed", "SPEED", 90, "e"), ("left", "TIME LEFT", 80, "e"),
                                   ("status", "STATUS", 150, "w")):
            t.heading(c, text=text, anchor=anchor)
            t.column(c, width=w, minwidth=60, anchor=anchor, stretch=False)
        t.column("#0", width=420, minwidth=200, stretch=True)
        sb = ttk.Scrollbar(body, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        t.tag_configure("done", foreground=C["text"])
        t.tag_configure("error", foreground=C["bad"])
        t.tag_configure("paused", foreground=C["muted"])
        t.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())
        t.bind("<Double-1>", self._double)
        t.bind("<Button-3>", self._menu)
        self.tree = t

        self.empty = tk.Label(body, text="No downloads yet\n\nClick a download link in Chrome or Edge and it lands "
                                         "here,\nor press  ＋ Add download  to paste a link.",
                              bg=C["bg"], fg=C["muted"], font=("Segoe UI", 10), justify="center")

        bottom = tk.Frame(r, bg=C["panel"], padx=14, pady=6)
        bottom.pack(fill="x", side="bottom")
        self.capture_lbl = tk.Label(bottom, text="", bg=C["panel"], font=FONT, cursor="hand2", padx=10, pady=3)
        self.capture_lbl.pack(side="left")
        self.capture_lbl.bind("<Button-1>", lambda e: self.toggle_capture())
        Tip(self.capture_lbl, "Click to turn catching browser downloads on or off")
        self.limit_lbl = tk.Label(bottom, text="", bg=C["panel"], fg=C["warn"], font=FONT, padx=8, cursor="hand2")
        self.limit_lbl.pack(side="left")
        self.limit_lbl.bind("<Button-1>", lambda e: self.toggle_limit())
        self.disk_lbl = tk.Label(bottom, text="", bg=C["panel"], fg=C["muted"], font=FONT)
        self.disk_lbl.pack(side="right")
        self.speed_lbl = tk.Label(bottom, text="", bg=C["panel"], fg=C["text"], font=FONT_B)
        self.speed_lbl.pack(side="right", padx=16)
        self.update_bar = tk.Frame(r, bg="#1d2a44", padx=14, pady=7)
        self.update_text = tk.Label(self.update_bar, text="", bg="#1d2a44", fg="#cfe0ff", font=FONT)
        self.update_text.pack(side="left")
        Btn(self.update_bar, "Later", lambda: self.update_bar.pack_forget(), padx=10, pady=3).pack(side="right")
        self.update_btn = Btn(self.update_bar, "Update now", self.install_update, kind="acc", padx=12, pady=3)
        self.update_btn.pack(side="right", padx=8)
        self._update_info = None

    # ---- data → screen ----
    def _visible(self):
        q = self.search.get().strip().lower()
        items = [i for i in self.mgr.items if matches(i, self._filter)
                 and (not q or q in (i.name or "").lower() or q in (i.url or "").lower())]
        return sorted(items, key=lambda i: i.added or 0, reverse=True)

    def refresh(self, force=False):
        items = self._visible()
        t = self.tree
        ids = [i.id for i in items]
        if force or ids != self._rows:
            sel = set(t.selection())
            t.delete(*t.get_children())
            for it in items:
                t.insert("", "end", iid=it.id)
            self._rows = ids
            keep = [i for i in ids if i in sel]
            if keep:
                t.selection_set(keep)
        for it in items:
            total, done = it.total or 0, it.done
            pct = 100 * min(done, total) / total if total else (100 if it.status == "done" else 0)
            st = it.status
            color = {"done": C["ok"], "error": C["bad"], "paused": C["faint"], "queued": C["faint"]}.get(
                st, CAT_COLOR.get(category_of(it.name or "x"), C["acc"]))
            speed = left = ""
            if st == "downloading" and it.speed:
                speed = human_size(it.speed) + "/s"
                if total:
                    left = human_time((total - done) / it.speed)
            status = STATUS_TEXT.get(st, st)
            if st == "error" and it.error:
                status = "Failed — " + it.error
            elif st == "done":
                status = "Completed"
            size = human_size(total) if total else (human_size(done) if done else "")
            t.item(it.id, text="  " + (it.name or it.url), image=bar_image(self._bars, pct, color),
                   values=(size, f"{pct:.0f}%" if total or st == "done" else "", speed, left, status),
                   tags=(st,))
        has = bool(self.mgr.items)
        if items:
            self.empty.place_forget()
        else:
            self.empty.configure(text=("No downloads yet\n\nClick a download link in Chrome or Edge and it lands "
                                       "here,\nor press  ＋ Add download  to paste a link.") if not has else
                                 "Nothing here")
            self.empty.place(relx=0.5, rely=0.42, anchor="center")
        for key, (lab, text) in self.tabs.items():
            n = sum(1 for i in self.mgr.items if matches(i, key))
            on = key == self._filter
            lab.configure(text=f"{text}  {n}" if n else text, bg=C["sel"] if on else C["bg"],
                          fg=C["text"] if on else C["muted"], font=FONT_B if on else FONT)
        speed = sum(i.speed for i in self.mgr.items if i.status == "downloading")
        self.speed_lbl.configure(text="↓ " + (human_size(speed) + "/s" if speed else "0 B/s"))
        cap = self.mgr.settings.get("capture", True)
        self.capture_lbl.configure(text=("●  Browser: catching" if cap else "○  Browser: not catching"),
                                   fg=C["ok"] if cap else C["muted"])
        on = self.mgr.settings.get("limit_on")
        self.limit_lbl.configure(text=f"Speed limit: {fmt_rate(self.mgr.settings.get('limit_down', 0))}" if on else "")
        self._update_buttons()

    def _update_buttons(self):
        vis = self._visible()
        self.b_resume_all.set_enabled(any(i.status in ("paused", "error") for i in vis))
        self.b_stop_all.set_enabled(any(i.status in ("downloading", "queued") for i in vis))
        self.b_delete_all.set_enabled(bool(vis))
        sel = self.selected()
        n = len(sel)
        self.sel_info.configure(text=f"{n} selected" if n else "")
        if n:
            self.actions.pack(side="right", padx=8)
            self.b_resume.set_enabled(any(i.status in ("paused", "error") for i in sel))
            self.b_stop.set_enabled(any(i.status in ("downloading", "queued") for i in sel))
        else:
            self.actions.pack_forget()
        self.sel_all.set(bool(vis) and n == len(vis))

    def _update_disk(self):
        free = probe.free_space(self.mgr.settings["save_dir"])
        self.disk_lbl.configure(text=f"{human_size(free)} free" if free is not None else "")

    # ---- loop ----
    def call(self, fn):
        """Run fn on the UI thread (safe to use from any thread)."""
        self._calls.put(fn)

    def _pump(self):
        while True:
            try:
                fn = self._calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        try:
            self.root.after(100, self._pump)
        except tk.TclError:
            pass

    def _loop(self):
        try:
            self.mgr.tick()
            while True:
                try:
                    msg = self.inbox.get_nowait()
                except queue.Empty:
                    break
                self._incoming(msg)
            self.refresh()
            for it in self.mgr.items:
                before = self._prev.get(it.id)
                if before and before != "done" and it.status == "done":
                    self.tray.notify(it.name or it.url, "Download complete")
                elif before and before != "error" and it.status == "error":
                    self.tray.notify((it.name or it.url) + "\n" + (it.error or ""), "Download failed")
            self._prev = {i.id: i.status for i in self.mgr.items}
            active = [i for i in self.mgr.items if i.status == "downloading"]
            sp = sum(i.speed for i in active)
            self.tray.tip(f"{APP_NAME}\n{len(active)} downloading · {human_size(sp)}/s" if active else APP_NAME)
            if int(time.time()) % 10 == 0:
                self._update_disk()
        except Exception:
            pass
        self.root.after(700, self._loop)

    def _incoming(self, msg):
        if msg.get("action") == "show":
            self.show()
            return
        self.show()
        AddDialog(self, msg)

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    # ---- selection ----
    def selected(self):
        return [it for it in (self.mgr.get(i) for i in self.tree.selection()) if it]

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _sel_all_clicked(self):
        if self.sel_all.get():
            self.tree.selection_set(self.tree.get_children())
        else:
            self.tree.selection_remove(self.tree.selection())

    def set_filter(self, key):
        self._filter = key
        self.refresh(force=True)

    # ---- actions ----
    def add_dialog(self, payload=None):
        AddDialog(self, payload)

    def _all(self, what, everything=False):
        for it in (self.mgr.items if everything else self._visible()):
            if what == "resume" and it.status in ("paused", "error"):
                it.resume()
            elif what == "stop" and it.status in ("downloading", "queued", "pausing"):
                it.pause()
        self.refresh()

    def resume_selected(self):
        for it in self.selected():
            if it.status in ("paused", "error"):
                it.resume()
        self.refresh()

    def stop_selected(self):
        for it in self.selected():
            if it.status in ("downloading", "queued"):
                it.pause()
        self.refresh()

    def folder_selected(self):
        sel = self.selected()
        if sel:
            show_in_folder(sel[0].path or "")

    def delete_selected(self):
        sel = self.selected()
        if not sel:
            return
        n = len(sel)
        d = Confirm(self, f"Delete {n} download{'s' if n != 1 else ''}?",
                    "They're removed from the list.", ["Also delete the files from my PC"])
        if d.result is None:
            return
        for it in sel:
            self.mgr.remove(it, delete_file=d.result[0])
        self.refresh(force=True)

    def delete_all(self):
        items = self._visible()
        if not items:
            return
        n_done = sum(1 for i in items if i.status == "done")
        d = Confirm(self, f"Delete all {len(items)} downloads?",
                    "They're removed from the list. Running downloads stop first.",
                    ["Also delete the files from my PC", f"Only finished downloads ({n_done})"], ok_text="Delete all")
        if d.result is None:
            return
        files, only_done = d.result
        for it in items:
            if only_done and it.status != "done":
                continue
            self.mgr.remove(it, delete_file=files)
        self.refresh(force=True)

    def _double(self, e):
        row = self.tree.identify_row(e.y)
        it = self.mgr.get(row) if row else None
        if not it:
            return
        if it.status == "done":
            open_path(it.path)
        elif it.status in ("downloading", "queued"):
            it.pause()
        else:
            it.resume()
        self.refresh()

    def _menu(self, e):
        row = self.tree.identify_row(e.y)
        if not row:
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        sel = self.selected()
        if not sel:
            return
        it = sel[0]
        m = tk.Menu(self.root, tearoff=0, bg=C["panel2"], fg=C["text"], activebackground=C["sel"],
                    activeforeground="#ffffff", bd=0, font=FONT)
        if it.status == "done":
            m.add_command(label="Open file", command=lambda: open_path(it.path))
        m.add_command(label="Show in folder", command=self.folder_selected)
        m.add_separator()
        if any(i.status in ("paused", "error") for i in sel):
            m.add_command(label="Resume", command=self.resume_selected)
        if any(i.status in ("downloading", "queued") for i in sel):
            m.add_command(label="Stop", command=self.stop_selected)
        m.add_command(label="Copy link", command=lambda: self._copy(it.url))
        m.add_separator()
        m.add_command(label="Delete…", command=self.delete_selected)
        m.tk_popup(e.x_root, e.y_root)

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def toggle_capture(self):
        s = self.mgr.settings
        s["capture"] = not s.get("capture", True)
        self.mgr.save()
        self.refresh()
        self.tray.refresh_menu()

    def toggle_limit(self):
        s = self.mgr.settings
        s["limit_on"] = not s.get("limit_on")
        self.mgr.apply_limits()
        self.mgr.save()
        self.refresh()
        self.tray.refresh_menu()

    # ---- updates ----
    def check_updates(self, manual=False):
        def work():
            try:
                info = updater.check_latest()
                err = None
            except Exception as e:
                info, err = None, str(e)
            self.call(lambda: self._update_result(info, err, manual))
        threading.Thread(target=work, daemon=True).start()

    def _update_result(self, info, err, manual):
        self.mgr.settings["last_update_check"] = time.time()
        if err:
            if manual:
                messagebox.showwarning(APP_NAME, f"Couldn't check for updates:\n{err}")
            return
        if not info["newer"]:
            if manual:
                messagebox.showinfo(APP_NAME, f"You have the latest version ({VERSION}).")
            return
        if not manual and self.mgr.settings.get("skip_version") == info["version"]:
            return
        self._update_info = info
        self.update_text.configure(text=f"{APP_NAME} {info['version']} is available — you have {VERSION}.")
        self.update_bar.pack(fill="x", before=self.root.winfo_children()[0])

    def install_update(self):
        info = self._update_info
        if not info:
            return
        self.update_btn.set_enabled(False)
        self.update_text.configure(text="Downloading the update…")

        def work():
            try:
                path = updater.download(info["url"], lambda d, t: self.call(
                    lambda: self.update_text.configure(
                        text=f"Downloading the update… {100 * d // t}%" if t else "Downloading the update…")))
                self.call(lambda: self._run_update(path))
            except Exception as e:
                err = str(e)
                self.call(lambda: (messagebox.showwarning(APP_NAME, f"Update failed:\n{err}"),
                                   self.update_btn.set_enabled(True)))
        threading.Thread(target=work, daemon=True).start()

    def _run_update(self, path):
        self.mgr.shutdown()
        try:
            updater.run_installer(path)
        except OSError as e:
            messagebox.showwarning(APP_NAME, f"The update didn't start:\n{e}")
            self.mgr._shut = False
            self.update_btn.set_enabled(True)
            return
        self.quit()

    # ---- closing ----
    def on_close(self):
        if self.tray.ok:
            try:
                self.mgr.settings["geometry"] = self.root.geometry()
            except tk.TclError:
                pass
            self.root.withdraw()
            if not self._told_tray:
                self._told_tray = True
                self.tray.notify("Still running next to the clock and catching browser downloads.\n"
                                 "Right-click the icon → Exit to close it.")
            return
        active = any(i.status in ("downloading", "queued") for i in self.mgr.items)
        if active and not messagebox.askyesno(
                APP_NAME, "Downloads are still running.\nStop them and close MZ-DManager Lite?\n\n"
                          "(They continue from where they stopped next time.)"):
            return
        self.quit()

    def quit(self):
        try:
            self.mgr.settings["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        self.mgr.shutdown()
        self.tray.stop()
        self.root.destroy()


# ---------------------------------------------------------------- test modes (CI)
def selftest(out):
    lines = []
    ok = True
    try:
        root = tk.Tk()
        root.withdraw()
        lines.append("tk " + str(tk.TkVersion))
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        lines.append("tray ok")
        root.destroy()
        import tempfile
        d = tempfile.mkdtemp()
        mgr = Manager(folder=d)
        mgr.settings["save_dir"] = d
        mgr.settings["categorize"] = False
        it = mgr.add(mgr.new_file("https://github.com/coo-3amer/DMTOR/archive/refs/heads/win7.zip"))
        t0 = time.time()
        while time.time() - t0 < 90 and it.status not in ("done", "error"):
            mgr.tick()
            time.sleep(0.3)
        lines.append(f"download {it.status} {it.done} bytes {it.error or ''}")
        ok = ok and it.status == "done" and it.done > 0 and os.path.isfile(it.path)
    except Exception as e:
        import traceback
        lines.append(traceback.format_exc())
        ok = False
    lines.append("PASS" if ok else "FAIL")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return 0 if ok else 1


def shots(out):
    import importlib
    grab = importlib.import_module("PIL.ImageGrab")
    import tempfile
    os.makedirs(out, exist_ok=True)
    mgr = Manager(folder=tempfile.mkdtemp())
    now = time.time()
    demo = [("Project walkthrough (1080p).mp4", 392_900_000, 0.31, "downloading", 3_100_000),
            ("Setup_v2.exe", 91_600_000, 1.0, "done", 0), ("Report Q3 2026.pdf", 13_400_000, 0.44, "paused", 0),
            ("Archive.zip", 2_200_000_000, 0.12, "paused", 0), ("Broken link.iso", 667_600_000, 0.0, "error", 0),
            ("Soundtrack.mp3", 8_300_000, 0.8, "downloading", 1_100_000), ("Wallpapers.zip", 120_000_000, 1.0, "done", 0)]
    for n, (name, total, frac, st, sp) in enumerate(demo):
        it = mgr.new_file("https://example.com/" + name.replace(" ", "%20"), name)
        it.total = total
        it.parts = [[0, total - 1, int(total * frac)]]
        it.status = st
        it.speed = sp
        it.added = now - n * 3600 * 7
        if st == "error":
            it.error = "The link expired (HTTP 403)"
        mgr.items.append(it)
    mgr.tick = lambda: None
    root = tk.Tk()
    app = App(root, mgr, queue.Queue())
    root.geometry("1040x620+40+40")

    def save(w, name):
        for _ in range(6):
            root.update()
            time.sleep(0.05)
        x, y = w.winfo_rootx(), w.winfo_rooty()
        grab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height())).save(os.path.join(out, name + ".png"))

    app.refresh(force=True)
    save(root, "lite_main")
    app.tree.selection_set([mgr.items[0].id, mgr.items[2].id])
    app.refresh()
    save(root, "lite_selected")
    app.tree.selection_remove(app.tree.selection())
    a = AddDialog(app, {"url": "https://github.com/coo-3amer/DMTOR/archive/refs/heads/win7.zip",
                        "filename": "MZ-DManager-Lite-source.zip"})
    for _ in range(40):
        root.update()
        time.sleep(0.1)
    save(a, "lite_add")
    a.grab_release()
    a.destroy()
    s = SettingsDialog(app)
    save(s, "lite_settings")
    s.destroy()
    app.tray.stop()
    root.destroy()
    return 0


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest.txt"))
    if "--shots" in sys.argv:
        i = sys.argv.index("--shots")
        sys.exit(shots(sys.argv[i + 1] if i + 1 < len(sys.argv) else "shots"))
    if "--init-folders" in sys.argv:
        Manager().ensure_folders()
        return
    if "--unregister" in sys.argv:
        try:
            set_startup(False)
        except OSError:
            pass
        return
    if "--guide" in sys.argv:
        open_guide()
        return
    inbox = queue.Queue()
    mgr = Manager()
    try:
        make_server(inbox, lambda: mgr.settings.get("capture", True))
    except OSError:
        # already running → bring that window up
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/show", data=b"{}",
                                                          method="POST"), timeout=2)
        except Exception:
            pass
        return
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MZ-DManager.Lite")
        except Exception:
            pass
    mgr.ensure_folders()
    root = tk.Tk()
    App(root, mgr, inbox, minimized="--minimized" in sys.argv)
    root.mainloop()


if __name__ == "__main__":
    main()
