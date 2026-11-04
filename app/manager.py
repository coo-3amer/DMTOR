"""Download queue, scheduling and persistence."""
import os
import json
import time

import core
from core import FileDownload, GLOBAL_LIMIT
from video import VideoDownload
import torrent
from torrent import TorrentDownload


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "EDENLOAD")
    if not os.path.isdir(d):                     # earlier names: carry the download list over once
        for name in ("DMTOR", "EdenDM"):
            old = os.path.join(base, name)
            if os.path.isdir(old):
                import shutil
                try:
                    shutil.copytree(old, d)
                except OSError:
                    pass
                break
    os.makedirs(d, exist_ok=True)
    return d


DEFAULT_SETTINGS = {
    "save_dir": os.path.join(os.path.expanduser("~"), "Downloads", "EDENLOAD Downloads"),
    "max_parallel": 3,
    "segments": 8,
    "categorize": True,
    "startup": False,
    "seed_after": False,
    "torrent_assoc": False,
    "torrent_ask_files": True,
    "capture": True,      # catch downloads from the browser
    # speed limits (KB/s, 0 = no limit for that one); only used while limit_on is True
    "limit_on": False,
    "limit_down": 1024,
    "torrent_down": 1024,
    "torrent_up": 256,
    # look
    "theme": "midnight",
    # folders per category, e.g. {"Video": "D:/Movies"} (missing/empty = default)
    "category_dirs": {},
    # clipboard
    "clipboard": True,
    "clipboard_video": False,
    # scheduler
    "schedule_on": False,
    "schedule_start": "02:00",
    "schedule_stop_on": True,
    "schedule_stop": "08:00",
    "schedule_days": [0, 1, 2, 3, 4, 5, 6],
    "schedule_action": "none",
    "after_done": "none",
    # updates
    "auto_update": True,
    "last_update_check": 0,
    "skip_version": "",
}


class Manager:
    def __init__(self, folder=None):
        self.dir = folder or data_dir()
        self.settings = dict(DEFAULT_SETTINGS)
        self.items = []
        self._last_save = 0.0
        self._last_statuses = {}
        self.load()
        self.settings["after_done"] = "none"     # one-time action never survives a restart
        self.apply_limits()
        self.apply_folders()

    # ---- persistence ----
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
                cls = {"video": VideoDownload, "torrent": TorrentDownload}.get(d.get("kind"), FileDownload)
                it = cls.from_dict(d)
                if it.status in ("downloading", "pausing", "queued"):
                    it.status = "paused"
                it.scheduled = bool(d.get("scheduled", False))
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
            self._write("downloads.json", [dict(i.to_dict(), scheduled=getattr(i, "scheduled", False))
                                           for i in self.items])
            self._last_save = time.time()
        except OSError:
            pass

    # ---- creating items ----
    def new_file(self, url, name="", headers=None, save_dir=None):
        return FileDownload(url, save_dir or self.settings["save_dir"], name, headers,
                            self.settings["segments"], self.settings["categorize"])

    def new_video(self, url, quality="best", save_dir=None, referrer=""):
        return VideoDownload(url, save_dir or self.settings["save_dir"], quality, referrer=referrer)

    def new_torrent(self, source, save_dir=None, headers=None):
        return TorrentDownload(source, save_dir or self.settings["save_dir"], headers=headers,
                               seed=self.settings.get("seed_after", False),
                               ask_files=self.settings.get("torrent_ask_files", True))

    def add(self, item, start=True):
        item.status = "queued" if start else "paused"
        self.items.append(item)
        self.save()
        return item

    def get(self, id):
        return next((i for i in self.items if i.id == id), None)

    def remove(self, item, delete_file=False):
        item.stop_for_remove()
        if item.kind == "torrent" and torrent.Engine._inst is not None:
            torrent.Engine._inst.remove(item, delete_file)
        if delete_file:
            if item.is_alive() and item._thread:
                item._thread.join(timeout=3)
            item.delete_files()
        if item in self.items:
            self.items.remove(item)
        self.save()

    def apply_folders(self):
        core.DEFAULT_DIR["path"] = self.settings["save_dir"]
        core.CATEGORY_DIRS.clear()
        core.CATEGORY_DIRS.update({k: v for k, v in (self.settings.get("category_dirs") or {}).items() if v})

    # ---- speed limits ----
    def effective_limits(self):
        """(downloads, torrent down, torrent up) in KB/s that are in force right now."""
        s = self.settings
        if not s.get("limit_on"):
            return 0, 0, 0
        return s.get("limit_down", 0), s.get("torrent_down", 0), s.get("torrent_up", 0)

    def apply_limits(self):
        down, t_down, t_up = self.effective_limits()
        GLOBAL_LIMIT.set_rate(down * 1024)
        torrent.set_session_limits(t_down * 1024, t_up * 1024)

    def _restart_videos_if_needed(self):
        # yt-dlp can't change its limit mid-download, so restart (it resumes where it was).
        for it in self.items:
            if it.kind != "video":
                continue
            if it.status == "downloading" and it.is_alive() and it.effective_rate() != it.applied_rate:
                it.pause()
                it.restart_pending = True   # set after pause(): a pause by the user clears it
            elif it.restart_pending and it.status == "paused" and not it.is_alive():
                it.restart_pending = False
                it.resume()

    # ---- scheduling ----
    def tick(self):
        running = sum(1 for i in self.items if i.status in ("downloading", "pausing") or
                      (i.status == "queued" and i.is_alive()))
        for it in self.items:
            if running >= self.settings["max_parallel"]:
                break
            if it.status == "queued" and not it.is_alive():
                if it.start():
                    running += 1
        if torrent.Engine._inst is not None:
            torrent.Engine._inst.pump()
        self._restart_videos_if_needed()
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
        if torrent.Engine._inst is not None:
            torrent.Engine._inst.save_all_and_wait(5)
        deadline = time.time() + 4
        for it in self.items:
            if it._thread:
                it._thread.join(timeout=max(0.1, deadline - time.time()))
        for it in self.items:
            if it.status in ("downloading", "pausing", "queued"):
                it.status = "paused"
        self.save()
