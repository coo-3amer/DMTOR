"""Video downloads (YouTube, Facebook, Instagram, TikTok, ...) via yt-dlp."""
import os
import sys
import shutil

import yt_dlp

from core import Item, safe_name, GLOBAL_LIMIT, resolve_folder

QUALITIES = [
    ("best", "Best available"),
    ("1080", "1080p"),
    ("720", "720p"),
    ("480", "480p"),
    ("360", "360p"),
    ("audio", "Audio only (MP3)"),
]


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ffmpeg_home():
    """Where the on-demand ffmpeg is kept (it isn't bundled, to keep the Setup small)."""
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "MZ-DManager", "ffmpeg")


def ffmpeg_path():
    for c in (os.path.join(app_dir(), "ffmpeg.exe"), os.path.join(ffmpeg_home(), "ffmpeg.exe"),
              os.path.join(app_dir(), "ffmpeg")):
        if os.path.isfile(c):
            return c
    return shutil.which("ffmpeg")


class VideoDownload(Item):
    kind = "video"

    def __init__(self, url, save_dir, quality="best", name="", referrer="", id=None):
        super().__init__(id)
        self.url = url
        self.save_dir = save_dir
        self.quality = quality
        self.name = name or url
        self.referrer = referrer
        self._done = 0
        self.applied_rate = 0     # the limit this run was started with (yt-dlp can't change it mid-run)
        self.restart_pending = False

    def pause(self):
        self.restart_pending = False
        super().pause()

    def effective_rate(self):
        rates = [r for r in (GLOBAL_LIMIT.rate, self.limit * 1024) if r]
        return min(rates) if rates else 0

    @property
    def done(self):
        return self._done

    def _format(self, ff):
        q = self.quality
        if q == "audio":
            return "ba/b"
        if q == "best":
            return "bv*+ba/b" if ff else "b"
        h = int(q)
        if ff:
            return f"bv*[height<={h}]+ba/b[height<={h}]/b"
        return f"b[height<={h}]/b"

    def _hook(self, d):
        if self._stop.is_set():
            raise yt_dlp.utils.DownloadCancelled("paused")
        info = d.get("info_dict") or {}
        if info.get("title"):
            self.name = safe_name(info["title"])
        if d.get("status") == "downloading":
            self.total = d.get("total_bytes") or d.get("total_bytes_estimate") or self.total
            self._done = d.get("downloaded_bytes") or 0
        elif d.get("status") == "finished":
            self._done = d.get("total_bytes") or self._done
            self.total = self._done

    def _run(self):
        ff = ffmpeg_path()
        folder = resolve_folder(self.save_dir, "Music" if self.quality == "audio" else "Video")
        os.makedirs(folder, exist_ok=True)
        opts = {
            "format": self._format(ff),
            "outtmpl": os.path.join(folder, "%(title).150B.%(ext)s"),
            "progress_hooks": [self._hook],
            "noplaylist": True,
            "continuedl": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "windowsfilenames": True,
            "concurrent_fragment_downloads": 4,
            "retries": 10,
            "fragment_retries": 10,
        }
        if ff:
            opts["ffmpeg_location"] = ff
            if self.quality == "audio":
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                           "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                opts["merge_output_format"] = "mp4"
        if self.referrer:
            opts["http_headers"] = {"Referer": self.referrer}
        self.applied_rate = self.effective_rate()
        if self.applied_rate:
            opts["ratelimit"] = self.applied_rate
            opts["concurrent_fragment_downloads"] = 1   # so the limit is the real total
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
        except (yt_dlp.utils.DownloadCancelled, yt_dlp.utils.DownloadError):
            if self._stop.is_set():
                self._ended_by_stop()
                return
            raise
        if self._stop.is_set():
            self._ended_by_stop()
            return
        rd = (info or {}).get("requested_downloads") or []
        if rd:
            self.path = rd[0].get("filepath") or rd[0].get("_filename") or ""
        if self.path:
            self.name = os.path.basename(self.path)
            try:
                self.total = self._done = os.path.getsize(self.path)
            except OSError:
                pass
        self.speed = 0.0
        self.status = "done"

    def delete_files(self):
        super().delete_files()

    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "id", "kind", "url", "save_dir", "quality", "name", "referrer",
            "total", "path", "status", "error", "added", "limit")}

    @classmethod
    def from_dict(cls, d):
        it = cls(d["url"], d["save_dir"], d.get("quality", "best"), d.get("name", ""),
                 d.get("referrer", ""), id=d["id"])
        for k in ("total", "path", "status", "error", "added"):
            if k in d:
                setattr(it, k, d[k])
        if it.status == "done":
            it._done = it.total
        it.set_limit(d.get("limit", 0))
        return it
