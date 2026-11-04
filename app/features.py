"""Scheduler, "when done" actions, clipboard filter and auto-update for DMTOR."""
import os
import re
import sys
import time
import datetime
import subprocess
from urllib.parse import urlparse

import requests

VERSION = "1.6"
REPO = "coo-3amer/DMTOR"

ACTIONS = [("none", "Do nothing"), ("sleep", "Put the computer to sleep"),
           ("shutdown", "Shut down the computer"), ("quit", "Close DMTOR")]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ACTIVE = ("downloading", "queued", "pausing")


# ---------------------------------------------------------------- scheduler
def minutes(hm):
    try:
        h, m = str(hm).split(":")
        return (int(h) % 24) * 60 + int(m) % 60
    except Exception:
        return 0


def in_window(now, start, stop, days):
    """True if `now` is inside start..stop on an allowed day (handles windows that pass midnight)."""
    t = now.hour * 60 + now.minute
    s, e = minutes(start), minutes(stop)
    wd = now.weekday()
    if s == e:
        return False
    if s < e:
        return wd in days and s <= t < e
    return (wd in days and t >= s) or (((wd - 1) % 7) in days and t < e)


class Scheduler:
    """Starts 'scheduled' downloads at the start time, pauses them at the stop time,
    and reports when they're all finished. tick() returns a list of (event, value)."""

    GRACE = 180   # without a stop time: still start if the app opens up to 3 hours late

    def __init__(self, mgr):
        self.mgr = mgr
        self.active = False         # inside a schedule run
        self.started_ids = set()
        self.fired_day = None       # date of the last start (no-stop mode)
        self._was_inside = False

    def _items(self):
        return [i for i in self.mgr.items if getattr(i, "scheduled", False)]

    def tick(self, now=None):
        s = self.mgr.settings
        now = now or datetime.datetime.now()
        ev = []
        if not s.get("schedule_on"):
            self.active = False
            self._was_inside = False
            return ev
        days = s.get("schedule_days", list(range(7)))
        start = s.get("schedule_start", "02:00")
        if s.get("schedule_stop_on", True):
            inside = in_window(now, start, s.get("schedule_stop", "08:00"), days)
            if inside and not self._was_inside:
                ev += self._start()
            elif not inside and self._was_inside:
                ev += self._stop()
            self._was_inside = inside
        else:
            t = now.hour * 60 + now.minute
            st = minutes(start)
            if (now.weekday() in days and st <= t < st + self.GRACE and self.fired_day != now.date()):
                self.fired_day = now.date()
                ev += self._start()
        if self.active:
            mine = [i for i in self._items() if i.id in self.started_ids]
            if not any(i.status in ACTIVE for i in mine):
                self.active = False
                done = sum(1 for i in mine if i.status == "done")
                ev.append(("finished", done))
        return ev

    def _start(self):
        n = 0
        self.started_ids = set()
        for it in self._items():
            if it.status in ("paused", "error", "queued"):
                if it.status != "queued":
                    it.resume()
                self.started_ids.add(it.id)
                n += 1
        self.active = n > 0
        return [("started", n)]

    def _stop(self):
        n = 0
        for it in self._items():
            if it.status in ACTIVE:
                it.pause()
                n += 1
        self.active = False
        return [("stopped", n)]


class WhenDone:
    """One-time 'when all downloads finish' action (Sleep / Shut down / Close)."""

    def __init__(self, mgr):
        self.mgr = mgr
        self.armed = False

    def tick(self):
        action = self.mgr.settings.get("after_done", "none")
        if action == "none":
            self.armed = False
            return None
        busy = any(i.status in ACTIVE for i in self.mgr.items)
        if busy:
            self.armed = True
            return None
        if self.armed:
            self.armed = False
            self.mgr.settings["after_done"] = "none"   # one-time
            return action
        return None


def power_action(action):
    """Sleep or shut down Windows. ('quit' is handled by the app.)"""
    if sys.platform != "win32":
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "0"], creationflags=flags)
    elif action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=flags)


# ---------------------------------------------------------------- clipboard
DOWNLOAD_EXT = set(("exe msi apk dmg pkg deb rpm appx msix zip rar 7z tar gz bz2 xz iso img bin "
                    "mp4 mkv avi mov wmv flv webm m4v 3gp ts mpg mpeg mp3 wav aac flac ogg m4a wma opus "
                    "pdf epub doc docx xls xlsx ppt pptx csv psd torrent").split())


def clip_candidate(text, video_sites=None, include_video=False):
    """Return the link if the copied text is something worth downloading, else ''."""
    text = (text or "").strip()
    if not text or len(text) > 4000 or "\n" in text or " " in text:
        return ""
    low = text.lower()
    if low.startswith("magnet:?"):
        return text
    if not low.startswith(("http://", "https://")):
        return ""
    path = urlparse(text).path.lower()
    ext = os.path.splitext(path)[1].lstrip(".")
    if ext in DOWNLOAD_EXT:
        return text
    if include_video and video_sites is not None and video_sites.search(text):
        return text
    return ""


# ---------------------------------------------------------------- updates
def parse_version(v):
    nums = re.findall(r"\d+", str(v))
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote, local=VERSION):
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def check_latest(timeout=10):
    """{'version', 'url', 'page', 'notes', 'size'} for the latest release. Raises on failure."""
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=timeout,
                     headers={"Accept": "application/vnd.github+json", "User-Agent": f"DMTOR/{VERSION}"})
    if r.status_code == 404:
        raise IOError("No public releases found")
    r.raise_for_status()
    j = r.json()
    asset = next((a for a in j.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    if not asset:
        raise IOError("The latest release has no installer")
    return {"version": j.get("tag_name", "").lstrip("vV"), "url": asset["browser_download_url"],
            "page": j.get("html_url", ""), "notes": j.get("body", "") or "", "size": asset.get("size", 0)}


def download_update(url, dest, progress=None, stop=None):
    tmp = dest + ".part"
    with requests.get(url, stream=True, timeout=30, headers={"User-Agent": f"DMTOR/{VERSION}"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                if stop is not None and stop.is_set():
                    raise IOError("cancelled")
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    os.replace(tmp, dest)
    return dest


def run_installer(path):
    """Start the new Setup silently; it closes DMTOR, updates it and opens it again."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     creationflags=flags, close_fds=True)


def update_due(settings, every_hours=12):
    return settings.get("auto_update", True) and time.time() - settings.get("last_update_check", 0) > every_hours * 3600
