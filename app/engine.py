"""Download list, queue, speed limit and saving — files only (no videos, no torrents)."""
import os
import sys
import json
import time

import core
from core import FileDownload, GLOBAL_LIMIT
from video import VideoDownload


def downloads_dir():
    """The user's real Downloads folder (it can be moved, e.g. to D:\\)."""
    if sys.platform == "win32":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
            g = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")     # FOLDERID_Downloads
            guid = GUID(g.fields[0], g.fields[1], g.fields[2], (ctypes.c_ubyte * 8)(*g.bytes[8:]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path:
                    return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "MZ-DManager Lite")
    os.makedirs(d, exist_ok=True)
    return d


DEFAULT_SETTINGS = {
    "save_dir": downloads_dir(),
    "max_parallel": 3,
    "segments": 8,
    "categorize": True,
    "startup": False,
    "capture": True,          # catch downloads from the browser
    "limit_on": False,
    "limit_down": 1024,       # KB/s
    "auto_update": True,
    "last_update_check": 0,
    "skip_version": "",
    "geometry": "",
}


class Manager:
    def __init__(self, folder=None):
        self.dir = folder or data_dir()
        self.settings = dict(DEFAULT_SETTINGS)
        self.items = []
        self._last_save = 0.0
        self._last_statuses = {}
        self.load()
        self.apply_limits()
        self.apply_folders()

    def _path(self, name):
        return os.path.join(self.dir, name)

    def load(self):
        try:
            with open(self._path("settings.json"), encoding="utf-8") as f:
                self.settings.update(json.load(f))
        except (OSError, ValueError):
            pass
        try:
            with open(self._path("downloads.json"), encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, ValueError):
            rows = []
        for d in rows:
            try:
                it = (VideoDownload if d.get("kind") == "video" else FileDownload).from_dict(d)
                if it.status in ("downloading", "pausing", "queued"):
                    it.status = "paused"
                self.items.append(it)
            except Exception:
                continue

    def _write(self, name, obj):
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path(name))

    def save(self):
        try:
            self._write("settings.json", self.settings)
            self._write("downloads.json", [i.to_dict() for i in self.items])
            self._last_save = time.time()
        except OSError:
            pass

    def new_file(self, url, name="", headers=None, save_dir=None):
        return FileDownload(url, save_dir or self.settings["save_dir"], name, headers,
                            self.settings["segments"], self.settings["categorize"])

    def new_video(self, url, quality="best", title="", save_dir=None, cookie_list=None):
        return VideoDownload(url, save_dir or self.settings["save_dir"], quality, title,
                             self.settings["categorize"], cookie_list=cookie_list)

    def add(self, item, start=True):
        item.status = "queued" if start else "paused"
        self.items.append(item)
        self.save()
        return item

    def get(self, id):
        return next((i for i in self.items if i.id == id), None)

    def remove(self, item, delete_file=False):
        item.stop_for_remove()
        if delete_file:
            if item.is_alive() and item._thread:
                item._thread.join(timeout=3)
            item.delete_files()
        if item in self.items:
            self.items.remove(item)
        self.save()

    def apply_folders(self):
        core.DEFAULT_DIR["path"] = self.settings["save_dir"]
        core.SORT["on"] = bool(self.settings.get("categorize", True))

    def ensure_folders(self):
        """Music, Videos, Programs, Documents and Others inside the download folder."""
        if not self.settings.get("categorize", True):
            return
        for name in core.DEFAULT_FOLDERS:
            try:
                os.makedirs(os.path.join(self.settings["save_dir"], name), exist_ok=True)
            except OSError:
                pass

    def apply_limits(self):
        s = self.settings
        GLOBAL_LIMIT.set_rate((s.get("limit_down", 0) if s.get("limit_on") else 0) * 1024)

    def tick(self):
        running = sum(1 for i in self.items if i.status in ("downloading", "pausing") or
                      (i.status == "queued" and i.is_alive()))
        for it in self.items:
            if running >= self.settings["max_parallel"]:
                break
            if it.status == "queued" and not it.is_alive():
                if it.start():
                    running += 1
        changed = False
        for it in self.items:
            it.update_speed()
            if self._last_statuses.get(it.id) != it.status:
                changed = True
        self._last_statuses = {i.id: i.status for i in self.items}
        if changed or time.time() - self._last_save > 3:
            self.save()

    def pause_all(self):
        for it in self.items:
            it.pause()

    def resume_all(self):
        for it in self.items:
            it.resume()

    def shutdown(self):
        if getattr(self, "_shut", False):
            return
        self._shut = True
        self.pause_all()
        deadline = time.time() + 4
        for it in self.items:
            if it._thread:
                it._thread.join(timeout=max(0.1, deadline - time.time()))
            if getattr(it, "_kill", None):
                it._kill()
        for it in self.items:
            if it.status in ("downloading", "pausing", "queued"):
                it.status = "paused"
        self.save()
