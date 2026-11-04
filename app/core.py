"""DMTOR - core segmented downloader with pause/resume."""
import os
import re
import time
import uuid
import threading
import mimetypes
from urllib.parse import urlparse, unquote

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
CHUNK = 256 * 1024
SMALL_CHUNK = 16 * 1024     # read size while a speed limit is active (smoother pacing)
MIN_SEGMENT = 1024 * 1024  # 1 MB minimum per segment
_PATH_LOCK = threading.Lock()


class RateLimiter:
    """Thread-safe pacing limiter. rate = bytes per second, 0 = unlimited."""

    def __init__(self, rate=0):
        self._lock = threading.Lock()
        self.rate = 0
        self._next = 0.0
        self.set_rate(rate)

    def set_rate(self, rate):
        with self._lock:
            rate = max(0, int(rate or 0))
            if rate != self.rate:
                self.rate = rate
                self._next = time.monotonic()   # forget old reservations at the old speed

    def consume(self, n, stop=None):
        with self._lock:
            rate = self.rate
            if rate <= 0:
                return
            now = time.monotonic()
            self._next = max(self._next, now - 0.25)   # allow a tiny burst, never a big one
            self._next += n / rate
            wait = self._next - now
        if wait > 0:
            if stop is not None:
                stop.wait(wait)
            else:
                time.sleep(wait)


# One limiter shared by every normal (http) download = the global "Downloads" speed limit.
GLOBAL_LIMIT = RateLimiter()


def fmt_rate(kb):
    """KB/s → '512 KB/s', '1 MB/s', '1.5 MB/s'; 0 → 'No limit'."""
    if not kb:
        return "No limit"
    if kb < 1024:
        return f"{kb} KB/s"
    mb = kb / 1024
    return f"{mb:.0f} MB/s" if mb == int(mb) else f"{mb:.1f} MB/s"

CATEGORIES = {
    "Video": "mp4 mkv avi mov wmv flv webm m4v 3gp ts mpg mpeg",
    "Music": "mp3 wav aac flac ogg m4a wma opus",
    "Programs": "exe msi apk dmg pkg deb rpm appx msix",
    "Compressed": "zip rar 7z tar gz bz2 xz iso",
    "Documents": "pdf doc docx xls xlsx ppt pptx txt csv odt rtf epub",
    "Images": "jpg jpeg png gif webp bmp svg heic tiff",
}


# Per-category folders chosen in Settings → Folders, e.g. {"Video": "D:/Movies"}.
CATEGORY_DIRS = {}
DEFAULT_DIR = {"path": ""}   # the default download folder (category folders apply only to that one)


def resolve_folder(save_dir, category, sub=True):
    """Where a download of this category goes."""
    custom = CATEGORY_DIRS.get(category)
    same_default = os.path.normcase(os.path.abspath(save_dir or "")) == \
        os.path.normcase(os.path.abspath(DEFAULT_DIR["path"] or "")) if DEFAULT_DIR["path"] else True
    if custom and same_default:
        return custom
    return os.path.join(save_dir, category) if sub else save_dir


def category_of(name):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for cat, exts in CATEGORIES.items():
        if ext in exts.split():
            return cat
    return "Other"


def human_size(n):
    if not n:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def human_time(sec):
    if sec is None or sec < 0:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "").strip(" .")
    return name[:200] or "download"


def unique_path(path):
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(path) or os.path.exists(path + ".part"):
        path = f"{base} ({i}){ext}"
        i += 1
    return path


def filename_from_response(r, url):
    cd = r.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", cd, re.I)
    if m:
        try:
            return unquote(m.group(2).strip().strip('"'), encoding=m.group(1) or "utf-8")
        except Exception:
            pass
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
    if m:
        name = m.group(1).strip()
        try:
            name = name.encode("latin-1").decode("utf-8")
        except Exception:
            pass
        return name
    name = unquote(os.path.basename(urlparse(r.url).path)) or \
        unquote(os.path.basename(urlparse(url).path)) or "download"
    if "." not in name:
        ct = r.headers.get("Content-Type", "").split(";")[0].strip()
        if ct and ct != "application/octet-stream":
            ext = mimetypes.guess_extension(ct)
            if ext:
                name += ext
    return name


class Item:
    """Base class shared by file and video downloads."""
    kind = "?"

    def __init__(self, id=None):
        self.id = id or uuid.uuid4().hex[:12]
        self.status = "queued"   # queued | downloading | pausing | paused | done | error | removed
        self.error = ""
        self.total = 0
        self.path = ""
        self.name = ""
        self.added = time.time()
        self.speed = 0.0
        self._last_done = None
        self._last_t = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.scheduled = False          # part of the scheduler's queue
        self.limit = 0                  # this download's own limit, KB/s (0 = none)
        self.limiter = RateLimiter()

    @property
    def done(self):
        return 0

    def set_limit(self, kb):
        self.limit = max(0, int(kb or 0))
        self.limiter.set_rate(self.limit * 1024)

    def _throttle(self, n):
        GLOBAL_LIMIT.consume(n, self._stop)
        if not self._stop.is_set():
            self.limiter.consume(n, self._stop)

    def _limited(self):
        return bool(GLOBAL_LIMIT.rate or self.limiter.rate)

    def is_alive(self):
        return bool(self._thread and self._thread.is_alive())

    def update_speed(self):
        now = time.time()
        d = self.done
        if self.status != "downloading":
            self.speed = 0.0
            self._last_done = None
            return
        if self._last_done is None:
            self._last_done, self._last_t = d, now
            return
        dt = now - self._last_t
        if dt >= 1.0:
            inst = max(0.0, (d - self._last_done) / dt)
            self.speed = inst if self.speed == 0 else self.speed * 0.6 + inst * 0.4
            self._last_done, self._last_t = d, now

    def start(self):
        if self.is_alive():
            return False
        self._stop.clear()
        self.status = "downloading"
        self.error = ""
        self._thread = threading.Thread(target=self._safe_run, daemon=True)
        self._thread.start()
        return True

    def _safe_run(self):
        try:
            self._run()
        except Exception as e:
            if self._stop.is_set():
                self._ended_by_stop()
            else:
                self.status = "error"
                self.error = str(e)[:300]
                self.speed = 0.0

    def _ended_by_stop(self):
        self.speed = 0.0
        if self.status in ("pausing", "downloading"):
            self.status = "paused"

    def pause(self):
        if self.status == "downloading":
            self.status = "pausing"
            self._stop.set()
        elif self.status == "queued":
            self.status = "paused"

    def resume(self):
        if self.status in ("paused", "error", "pausing"):
            self.status = "queued"

    def stop_for_remove(self):
        self.status = "removed"
        self._stop.set()

    def _run(self):
        raise NotImplementedError

    def delete_files(self):
        for p in (self.path, self.path + ".part" if self.path else ""):
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass


class FileDownload(Item):
    kind = "file"

    def __init__(self, url, save_dir, filename="", headers=None, segments=8,
                 categorize=True, id=None):
        super().__init__(id)
        self.url = url
        self.real_url = ""
        self.save_dir = save_dir
        self.name = safe_name(filename) if filename else ""
        self.headers = headers or {}
        self.segments = segments
        self.categorize = categorize
        self.resumable = False
        self.parts = []          # [start, end, downloaded]; end == -1 means unknown/streamed
        self._lock = threading.Lock()
        self._errors = []
        self._single_complete = False

    @property
    def done(self):
        return sum(p[2] for p in self.parts)

    # ---- network helpers ----
    def _session(self):
        s = requests.Session()
        s.headers["User-Agent"] = UA
        for k, v in self.headers.items():
            if v:
                s.headers[k] = v
        return s

    def _probe(self):
        s = self._session()
        r = s.get(self.url, headers={"Range": "bytes=0-"}, stream=True, timeout=30)
        try:
            r.raise_for_status()
            self.real_url = r.url
            if not self.name:
                self.name = safe_name(filename_from_response(r, self.url))
            if r.status_code == 206:
                m = re.search(r"/(\d+)", r.headers.get("Content-Range", ""))
                self.total = int(m.group(1)) if m else 0
                self.resumable = self.total > 0
            else:
                self.total = int(r.headers.get("Content-Length") or 0)
                self.resumable = False
        finally:
            r.close()

    def _part_complete(self, p):
        if p[1] == -1:
            return self._single_complete
        return p[2] >= p[1] - p[0] + 1

    # ---- main run ----
    def _run(self):
        if not self.path:
            self._probe()
            folder = resolve_folder(self.save_dir, category_of(self.name), self.categorize)
            os.makedirs(folder, exist_ok=True)
            with _PATH_LOCK:   # two downloads with the same name must not grab the same path
                self.path = unique_path(os.path.join(folder, self.name))
                open(self.path + ".part", "wb").close()
            self.name = os.path.basename(self.path)
            self.parts = []
        part_file = self.path + ".part"

        if not self.resumable or not self.parts or not os.path.exists(part_file):
            if self.resumable:
                n = max(1, min(self.segments, self.total // MIN_SEGMENT or 1))
                size = self.total // n
                self.parts = [[i * size, self.total - 1 if i == n - 1 else (i + 1) * size - 1, 0]
                              for i in range(n)]
            else:
                self.parts = [[0, -1, 0]]
            with open(part_file, "wb") as f:
                if self.resumable:
                    f.truncate(self.total)

        self._errors = []
        self._single_complete = False
        threads = [threading.Thread(target=self._worker, args=(p, part_file), daemon=True)
                   for p in self.parts if not self._part_complete(p)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if self._stop.is_set():
            self._ended_by_stop()
            return
        if all(self._part_complete(p) for p in self.parts):
            os.replace(part_file, self.path)
            if not self.total:
                self.total = self.done
            self.speed = 0.0
            self.status = "done"
        else:
            self.status = "error"
            self.speed = 0.0
            self.error = (self._errors or ["Download did not complete"])[-1]

    def _worker(self, part, part_file):
        start, end = part[0], part[1]
        s = self._session()
        url = self.real_url or self.url
        tries = 0
        while not self._stop.is_set():
            if end != -1 and self._part_complete(part):
                return
            try:
                headers = {}
                if end != -1:
                    headers["Range"] = f"bytes={start + part[2]}-{end}"
                else:
                    with self._lock:
                        part[2] = 0      # non-resumable: restart from the beginning
                with s.get(url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    if end != -1 and r.status_code != 206:
                        raise IOError("Server refused a ranged request")
                    with open(part_file, "r+b") as f:
                        f.seek(start + part[2])
                        if end == -1:
                            f.truncate()
                        for chunk in r.iter_content(SMALL_CHUNK if self._limited() else CHUNK):
                            if self._stop.is_set():
                                return
                            if not chunk:
                                continue
                            self._throttle(len(chunk))
                            if self._stop.is_set():
                                return
                            if end != -1:
                                remaining = end - (start + part[2]) + 1
                                chunk = chunk[:remaining]
                            f.write(chunk)
                            with self._lock:
                                part[2] += len(chunk)
                            if end != -1 and self._part_complete(part):
                                return
                if end == -1:
                    if self.total and part[2] < self.total:
                        raise IOError("Connection dropped before the file finished")
                    self._single_complete = True
                    return
                tries = 0  # stream ended early but made progress: loop resumes from new offset
            except Exception as e:
                tries += 1
                if tries > 6:
                    self._errors.append(str(e)[:300])
                    return
                self._stop.wait(min(2 * tries, 10))

    # ---- persistence ----
    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "id", "kind", "url", "real_url", "save_dir", "name", "headers", "segments",
            "categorize", "resumable", "parts", "total", "path", "status", "error", "added", "limit")}

    @classmethod
    def from_dict(cls, d):
        it = cls(d["url"], d["save_dir"], d.get("name", ""), d.get("headers"),
                 d.get("segments", 8), d.get("categorize", True), id=d["id"])
        for k in ("real_url", "resumable", "parts", "total", "path", "status", "error", "added"):
            if k in d:
                setattr(it, k, d[k])
        it.name = d.get("name", "")
        it.set_limit(d.get("limit", 0))
        return it
